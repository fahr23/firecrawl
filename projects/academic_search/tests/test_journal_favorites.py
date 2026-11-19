"""Persistent favorite journals, latest works, and publisher status through the service."""

import asyncio
from datetime import date, timedelta
from unittest.mock import AsyncMock, Mock
from uuid import uuid4

from fastapi.testclient import TestClient

from academic_search import journal_favorites, submission_sources
from academic_search.config import Config
from academic_search.models import Article, ProviderOutcome, SearchResult
from academic_search.project_store import ProjectStore
from academic_search.providers import OpenAlexSearcher
from academic_search.service import create_app, get_journal_catalog_service, get_journal_searcher
from academic_search.tests.test_editorial_workspace import notice


BASE = "/api/v1/journal-favorites"
HOME = "https://dergipark.org.tr/en/pub/energy-example"
GUIDE = HOME + "/writing-rules"
CALLS = HOME + "/announcements"
CALL = CALLS + "/54"


def journal(provider="openalex", journal_id="S321", home=HOME, **attrs):
    return {
        "id": "S321", "display_name": "Energy Research Quarterly", "type": "journal",
        "identifiers": {"openalex": "S321"}, "issn_l": "1721-4320", "issns": ["1721-4320"],
        "catalog_provider": provider, "provider_id": journal_id, "homepage_url": home, **attrs,
    }


def client_for(store, sources=None, searcher=None):
    app = create_app(store)
    if sources is None:
        sources = Mock()
        sources.resolve.side_effect = lambda provider, journal_id: {"journal": journal(provider, journal_id)}
    if searcher:
        app.dependency_overrides[get_journal_searcher] = lambda: searcher
    app.dependency_overrides[get_journal_catalog_service] = lambda: sources
    return TestClient(app), sources


def paper(title, key, published, doi):
    return Article(title=title, url=f"https://example.org/{key}", doi=doi, source="OpenAlex",
                   journal="Energy Research Quarterly", year=str(published.year), raw_data={
                       "publication_date": published.isoformat(), "type": "article",
                       "primary_topic": {"display_name": "Energy storage"},
                   })


def fetched(*articles, status="responded"):
    return SearchResult(query="", articles=list(articles),
                        provider_outcomes=[ProviderOutcome("OpenAlex", status, returned_count=len(articles))])


def follow(client, provider="openalex", journal_id="S321"):
    response = client.post(BASE, json={"provider": provider, "journal_id": journal_id})
    assert response.status_code == 201, response.text
    return response.json()


def test_follow_refreshes_reading_feed_and_keeps_saved_publisher_data_after_429(monkeypatch, tmp_path):
    path = str(tmp_path / "journals.db")
    store = ProjectStore(path)
    searcher = Mock()
    a = paper("Earlier article", "a", date.today() - timedelta(days=2), "10.1234/earlier")
    same = paper("Earlier article", "a-copy", date.today() - timedelta(days=2), "10.1234/EARLIER")
    b = paper("New review", "b", date.today(), "10.1234/latest")
    searcher.search_journal.side_effect = [fetched(a), fetched(same, b), fetched(status="rate_limited")]
    client, _ = client_for(store, searcher=searcher)
    deadline = (date.today() + timedelta(days=8)).isoformat()
    pages = {
        HOME: notice('<h1>Energy Research Quarterly</h1><a href="' + GUIDE + '">Author Guidelines</a>'
                     '<a href="' + CALLS + '">All announcements</a>'),
        CALLS: notice('<a href="' + CALL + '">Special Issue on Storage</a>'),
        GUIDE: notice('<h1>Author guidelines</h1><p>Open for submissions</p>'
                      '<p>Accepted article types: Original research and review articles.</p>'
                      '<a href="https://example.org/submit">Submit article</a>'),
        CALL: notice('<h1>Energy Research Quarterly</h1><h1>Special Issue on Storage</h1>'
                     f'<p>Invites original research papers.</p><p>Submission deadline: {deadline}</p>'),
    }
    monkeypatch.setattr(submission_sources, "_read", lambda url, params=None: pages.get(url))
    favorite = follow(client)
    assert favorite["id"] == follow(client, "scopus", "1234")["id"]
    route = f"{BASE}/{favorite['id']}"
    assert client.post(route + "/refresh").json()["added"] == 1
    first = client.get(route).json()
    assert first["favorite"]["submission"]["article_types"] == "Original research and review articles"
    assert first["favorite"]["submission"]["calls_url"] == CALLS
    assert first["calls"][0]["deadline"] == deadline
    assert first["favorite"]["submission"]["status"] == "open"
    assert first["papers"][0]["primary_topic"] == "Energy storage"
    client.post("/api/v1/library/activity/open", json={"url": a.url, "event_id": str(uuid4())})

    assert client.post(route + "/refresh").json()["added"] == 1
    second = client.get(route).json()
    assert [item["title"] for item in second["papers"]] == [b.title, a.title]
    assert second["favorite"]["unread"] == 1
    assert len(client.get(route, params={"unread_only": True}).json()["papers"]) == 1
    limited = client.get(route, params={"limit": 1}).json()
    assert limited["has_more"] and limited["papers"][0]["title"] == b.title
    assert client.get("/api/v1/today").json()["followed_journals"][0]["unread"] == 1
    pages.clear()
    assert client.post(route + "/refresh").status_code == 200
    fallback = client.get(route).json()
    assert fallback["papers"] == second["papers"]
    assert fallback["favorite"]["paper_status"]["status"] == "rate_limited"
    assert fallback["favorite"]["papers_checked_at"] == second["favorite"]["papers_checked_at"]
    assert fallback["favorite"]["publisher_checked_at"] == second["favorite"]["publisher_checked_at"]
    assert fallback["favorite"]["submission"]["submission_url"] == "https://example.org/submit"

    assert client.post(route + "/seen", json={}).status_code == 200
    assert client.get(route).json()["favorite"]["unread"] == 0
    assert ProjectStore(path).journal_favorites.get(favorite["id"])["unread"] == 0
    assert client.get("/api/v1/search", params={"q": "10.1234/latest", "mode": "local"}).json()["results"][0]["title"] == b.title


def test_unfollow_is_reversible_and_does_not_require_a_catalog_recheck(monkeypatch):
    store = ProjectStore(":memory:")
    searcher = Mock()
    searcher.search_journal.return_value = fetched(paper("One paper", "one", date.today(), "10.1234/one"))
    client, sources = client_for(store, searcher=searcher)
    monkeypatch.setattr(submission_sources, "_read", Mock(return_value=None))
    favorite = follow(client)
    route = f"{BASE}/{favorite['id']}"
    assert client.post(route + "/refresh").status_code == 200
    assert client.delete(route).status_code == 200
    assert client.get(BASE).json()["items"] == []
    assert client.get(route).status_code == 404
    sources.resolve.side_effect = AssertionError("An existing favorite should be restored locally")
    assert follow(client)["id"] == favorite["id"]
    assert client.get(route).json()["papers"][0]["title"] == "One paper"


def test_publication_feed_filters_exact_openalex_source_and_includes_papers_without_abstracts(monkeypatch):
    searcher = OpenAlexSearcher(Config())
    latest = Mock(return_value={"meta": {"count": 1}, "results": [
        {"id": "https://openalex.org/W987", "title": "Latest editorial", "type": "editorial",
         "publication_year": date.today().year, "publication_date": date.today().isoformat()},
    ]})
    monkeypatch.setattr(searcher, "_make_request", latest)
    client, _ = client_for(ProjectStore(":memory:"), searcher=searcher)
    monkeypatch.setattr(submission_sources, "_read", Mock(return_value=None))
    favorite = follow(client)
    route = f"{BASE}/{favorite['id']}"
    assert client.post(route + "/refresh").status_code == 200
    args = latest.call_args.args
    assert args[0].endswith("/works")
    assert args[1]["filter"] == f"primary_location.source.id:S321,to_publication_date:{date.today()}"
    assert args[1]["sort"] == "publication_date:desc"
    assert "search" not in args[1]
    assert client.get(route).json()["papers"][0]["work_type"] == "editorial"


def test_publisher_links_are_independent_of_paper_crosswalk_and_never_guessed_open(monkeypatch):
    store = ProjectStore(":memory:")
    searcher = Mock()
    sources = Mock()
    sources.resolve.return_value = {"journal": journal("ubyt", "1721-4320", id="ISSN:1721-4320",
                                                      identifiers={}, search_supported=False)}
    client, _ = client_for(store, sources, searcher)
    pages = {
        HOME: notice(f'<h1>Energy Research Quarterly</h1><a href="{GUIDE}">Author guidelines</a>'),
        GUIDE: notice('<h1>Author guidelines</h1><p>A special issue is open for submissions.</p>'),
    }
    monkeypatch.setattr(submission_sources, "_read", lambda url, params=None: pages.get(url))
    route = f"{BASE}/{follow(client, 'ubyt', '1721-4320')['id']}"
    updated = client.post(route + "/refresh")
    assert updated.status_code == 200
    favorite = updated.json()["favorite"]
    assert favorite["paper_status"]["status"] == "unsupported"
    assert favorite["publisher_status"]["status"] == "checked"
    assert favorite["submission"]["status"] == "unverified"
    assert favorite["submission"]["guidelines_url"] == GUIDE
    searcher.search_journal.assert_not_called()


def test_scheduler_refreshes_a_due_followed_journal_without_a_browser(monkeypatch):
    store = ProjectStore(":memory:")
    client, _ = client_for(store)
    favorite = follow(client)
    check = Mock()
    searcher = object()
    serializer = object()
    monkeypatch.setattr(journal_favorites, "refresh", check)
    monkeypatch.setattr(journal_favorites.asyncio, "sleep", AsyncMock(side_effect=[None, asyncio.CancelledError]))

    async def run():
        try:
            await journal_favorites.scheduler(store, lambda: searcher, serializer)
        except asyncio.CancelledError:
            pass

    asyncio.run(run())
    check.assert_called_once_with(store, favorite["id"], searcher, serializer)
