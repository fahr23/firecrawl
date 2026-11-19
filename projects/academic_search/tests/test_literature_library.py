"""Search refresh, outage fallback, and migration through the public service."""

import sqlite3
from unittest.mock import Mock

import requests
from fastapi.testclient import TestClient

from academic_search import Article, Config, SearchResult
from academic_search.models import ProviderOutcome
from academic_search.project_store import ProjectStore
from academic_search.service import create_app, get_search_engine
from academic_search.tests.test_reproducibility import FixtureSearcher, fixture_engine
from academic_search.tests.test_service import make_client


def paper(key, *, source="OpenAlex", doi=None, year="2025"):
    return Article(
        title=f"Solar forecasting study {key}", url=f"https://example.org/{key}",
        doi=doi, year=year, source=source, authors="Ada Researcher",
        journal="Energy Research", abstract="Calibrates photovoltaic storage using satellite sensors.",
    )


def result(*articles, failed=None):
    names = list(dict.fromkeys(article.source for article in articles))
    outcomes = [ProviderOutcome(name, "responded") for name in names]
    if failed:
        outcomes.append(ProviderOutcome(failed, "rate_limited", error_code="rate_limited"))
    if not outcomes:
        outcomes = [ProviderOutcome("OpenAlex", "empty")]
    return SearchResult("solar forecasting", articles=list(articles), sources=names, provider_outcomes=outcomes)


def search(client, **params):
    response = client.get("/api/v1/search", params={"q": "solar forecasting", **params})
    assert response.status_code == 200, response.text
    assert response.headers["cache-control"] == "no-store"
    return response.json()


def titles(payload):
    return [paper["title"] for paper in payload["results"]]


def test_repeat_query_refreshes_ranked_cache_and_keeps_older_papers_locally():
    original = paper("original", doi="10.1234/solar", year="2024")
    fresh = paper("new", year="2026")
    engine = Mock()
    engine.search.side_effect = [result(original), result(fresh), result()]
    client, _, _ = make_client(engine)

    assert search(client)["cache"]["kind"] == "live"
    assert titles(search(client, mode="cache")) == [original.title]
    assert engine.search.call_count == 1
    assert titles(search(client)) == [fresh.title]
    assert titles(search(client, mode="cache")) == [fresh.title]

    local = search(client, mode="local", q='"satellite sensors" Researcher')
    assert sorted(titles(local)) == sorted([original.title, fresh.title])
    assert all(record["retrieval_kind"] == "saved" for record in local["results"])
    assert titles(search(client, mode="local", q="https://doi.org/10.1234/SOLAR")) == [original.title]
    assert titles(search(client, mode="local", year_min=2026)) == [fresh.title]
    assert titles(search(client, mode="local", year_max=2024)) == [original.title]
    assert len(client.get("/api/v1/projects").json()["projects"]) == 0
    assert engine.search.call_count == 2

    assert search(client)["cache"]["live_count"] == 0
    assert search(client, mode="cache")["results"] == []
    assert len(search(client, mode="local")["results"]) == 2
    assert engine.search.call_count == 3


def test_each_provider_observation_survives_online_deduplication():
    openalex = paper("alex", doi="10.1234/solar")
    pubmed = paper("pubmed", source="PubMed", doi="10.1234/SOLAR")
    config = Config()
    engine = fixture_engine(
        FixtureSearcher(config, "OpenAlex", [openalex]), FixtureSearcher(config, "PubMed", [pubmed]),
    )
    client, _, _ = make_client(engine)

    found = search(client, providers="openalex,pubmed")
    assert found["returned"] == 1
    status = client.get("/api/v1/library/status").json()
    assert (status["works"], status["observations"]) == (1, 2)
    local_paper = search(client, mode="local", providers="pubmed")["results"][0]
    assert local_paper["source"] == "PubMed"
    assert local_paper["library_id"] == found["results"][0]["library_id"]


def test_rate_limit_preserves_prior_cache_and_shows_fresh_results_first():
    original = paper("original")
    peer = paper("peer", source="PubMed")
    fresh = paper("fresh", source="PubMed")
    engine = Mock()
    engine.search.side_effect = [result(original, peer), result(fresh, failed="OpenAlex"), requests.ConnectionError()]
    client, _, _ = make_client(engine)
    params = {"providers": "openalex,pubmed"}

    first = search(client, **params)
    mixed = search(client, **params)
    assert titles(mixed) == [fresh.title, original.title]
    assert [row.get("retrieval_kind") for row in mixed["results"]] == [None, "saved"]
    assert [row["status"] for row in mixed["provider_coverage"]] == ["rate_limited", "responded"]
    assert mixed["cache"] == {
        "kind": "mixed", "source": "query_cache",
        "fetched_at": search(client, mode="cache", **params)["cache"]["fetched_at"],
        "checked_at": mixed["retrieved_at"], "live_count": 1, "saved_count": 1,
    }
    assert titles(search(client, mode="cache", **params)) == titles(first)
    unavailable = search(client, q='"photovoltaic storage"', **params)
    assert unavailable["cache"]["kind"] == "fallback"
    assert unavailable["cache"]["source"] == "library"
    assert {row["error_code"] for row in unavailable["provider_coverage"]} == {"transport_error"}
    assert sorted(titles(unavailable)) == sorted([original.title, peer.title, fresh.title])
    assert engine.search.call_count == 3


def test_library_paper_can_be_shortlisted_by_id_and_verified_url():
    client, _, _ = make_client()
    project_id = client.post("/api/v1/projects", json={"name": "Literature topic"}).json()["id"]
    search(client)
    saved = search(client, q="reliable computing", mode="local")["results"][0]
    route = f"/api/v1/projects/{project_id}/workspace/reading/from-source"
    origin = {"kind": "library", "run_id": saved["library_id"], "paper_url": saved["url"]}

    assert client.post(route, json={**origin, "paper_url": "https://example.org/different"}).status_code == 404
    shortlisted = client.post(route, json=origin)
    assert shortlisted.status_code == 201
    assert shortlisted.json()["data"]["origin"] == origin
    assert shortlisted.json()["data"]["paper"]["title"] == saved["title"]


def test_existing_project_evidence_is_backfilled_once_and_queryable_after_restart(tmp_path):
    path = str(tmp_path / "projects.db")
    store = ProjectStore(path)
    engine = Mock()
    engine.search.return_value = result(paper("historical"))
    app = create_app(store)
    app.dependency_overrides[get_search_engine] = lambda: engine
    client = TestClient(app)
    project_id = client.post("/api/v1/projects", json={"name": "Existing project"}).json()["id"]
    run_id = search(client, project_id=project_id)["search_run_id"]
    before = store.get_search(project_id, run_id)

    # Simulate a copy of the project database taken before the library migration.
    with sqlite3.connect(path) as connection:
        tables = connection.execute(
            "SELECT name FROM sqlite_master WHERE type IN ('table', 'trigger') AND name LIKE 'literature_%'"
        ).fetchall()
        objects = {name for (name,) in tables}
        for name in ("literature_works_insert", "literature_works_update", "literature_works_delete"):
            assert name in objects
            connection.execute(f"DROP TRIGGER {name}")
        for name in ("query_hits", "query_pages", "queries", "observations", "urls", "fts", "works", "migrations"):
            connection.execute(f"DROP TABLE literature_{name}")

    migrated = ProjectStore(path)
    open_again = ProjectStore(path)
    assert migrated.get_search(project_id, run_id) == before
    assert migrated.literature.status() == open_again.literature.status()
    assert migrated.literature.status()["works"] == 1
    [stored] = open_again.literature.search("satellite", "all", [], None, None, 10, 0)
    assert stored["title"] == "Solar forecasting study historical"
    assert len(open_again.list_searches(project_id)) == 1
