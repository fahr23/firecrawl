"""A research project keeps its evidence as it moves from reading to submission."""

from datetime import date, datetime, timedelta, timezone
from io import BytesIO
import json
from unittest.mock import Mock
from uuid import uuid4

from docx import Document
from fastapi.testclient import TestClient

from academic_search import submission_sources, workspace_assistant
from academic_search.config import Config
from academic_search.project_store import ProjectStore
from academic_search.providers import OpenAlexSearcher
from academic_search.service import create_app, get_journal_catalog_service, get_journal_searcher, get_search_engine
from academic_search.tests.test_daily_reading import article
from academic_search.tests.test_editorial_workspace import notice
from academic_search.tests.test_journal_favorites import CALL, GUIDE, HOME, fetched, journal
from academic_search.tests.test_literature_library import result
from academic_search.tests.test_service import FakeJournalCatalog, FakeJournalSearcher


def fixture_app(store, monkeypatch):
    today = datetime.now(timezone.utc).date()
    deadline = (today + timedelta(days=14)).isoformat()
    seed = article("baseline", (today - timedelta(days=3)).isoformat(), "10.1234/baseline")
    latest = article("new", (today - timedelta(days=1)).isoformat(), "10.1234/new")
    daily = article("daily", today.isoformat(), "10.1234/daily")
    pages = {
        HOME: notice(f'<a href="{GUIDE}">Writing Rules</a><a href="{CALL}">Special Issue on Solar Forecasting</a>'),
        GUIDE: notice('<p>Open for submissions</p><p>Accepted article types: Original research.</p>'),
        CALL: notice('<h1>Energy Research Quarterly</h1><h1>Special Issue on Solar Forecasting</h1>'
                     f'<p>Invites original research papers.</p><p>Submission deadline: {deadline}</p>'),
    }
    monkeypatch.setattr(submission_sources, "_read", lambda url, params=None: pages.get(url))

    class Catalog(FakeJournalCatalog):
        def journals(self, provider, *args, **kwargs):
            return {**super().journals(provider, *args, **kwargs), "journals": [journal(provider)]}

        def resolve(self, provider, journal_id):
            return {"provider_status": {"status": "responded"}, "journal": journal(provider, journal_id)}

    class Alex(OpenAlexSearcher):
        def suggest_journals(self, query, limit=8):
            return [journal()]

        def resolve_journal_by_issn(self, issn):
            return journal()

        def search_journal(self, journal_id, journal_name, query, max_results=25, year_min=None, year_max=None,
                           *, published_through=None):
            if published_through:
                return fetched(seed, latest)
            return sample.search_journal(journal_id, journal_name, query, max_results, year_min, year_max)

        def _make_request(self, url, params):
            if "group_by" in params:
                filters = params["filter"]
                recent = str(today.year - 1) in filters if "publication_year:" in filters else (
                    f"to_publication_date:{today - timedelta(days=1)}" in filters
                )
                return {"meta": {"count": 100}, "group_by": [
                    {"key": "https://openalex.org/T10001", "key_display_name": "Solar forecasting",
                     "count": 30 if recent else 10},
                ]}
            if "filter" in params and params["filter"].startswith("primary_topic.field.id:"):
                return {"results": []}
            return {"results": [{
                "id": "https://openalex.org/W10001", "title": "Solar forecasting across regions",
                "publication_date": today.isoformat(), "publication_year": today.year, "type": "article",
            }]}

    def search_for(query, max_results, *args, **kwargs):
        if "daily" in query:
            return result(daily, latest)
        if max_results >= 50:
            return result(seed, latest)
        return result(seed)

    engine = Mock()
    engine.search.side_effect = search_for
    sample = FakeJournalSearcher()
    searcher = Alex(Config())
    app = create_app(store)
    app.dependency_overrides[get_search_engine] = lambda: engine
    app.dependency_overrides[get_journal_catalog_service] = Catalog
    app.dependency_overrides[get_journal_searcher] = lambda: searcher
    return app, engine, seed, latest, daily, deadline


def expect(response, status=200):
    assert response.status_code == status, response.text
    return response.json()


def test_research_journey_from_daily_paper_to_draft_submission_and_portfolio(monkeypatch, tmp_path):
    db_path = str(tmp_path / "journey.db")
    today = datetime.now(timezone.utc).date().isoformat()
    app, engine, seed, latest, daily, deadline = fixture_app(ProjectStore(db_path), monkeypatch)
    client = TestClient(app)
    api = "/api/v1"
    topic = expect(client.post(f"{api}/projects", json={"name": "Solar forecasting"}), 201)["id"]
    another = expect(client.post(f"{api}/projects", json={"name": "Grid reliability"}), 201)["id"]
    project = f"{api}/projects/{topic}"
    work = f"{project}/workspace"

    filters = {"q": "solar forecasting", "providers": "openalex", "project_id": topic}
    baseline = expect(client.get(f"{api}/search", params=filters))
    assert [row["title"] for row in baseline["results"]] == [seed.title]
    watch = expect(client.post(f"{project}/watches", json={"q": filters["q"], "providers": "openalex"}), 201)
    assert expect(client.post(f"{project}/watches/{watch['id']}/refresh"))["added"] == 1
    [hit] = expect(client.get(f"{api}/inbox", params={"project_id": topic, "unread_only": True}))["items"]
    assert hit["paper"]["title"] == latest.title

    favorite = expect(client.post(f"{api}/journal-favorites", json={"journal_id": "S321"}), 201)
    journal_path = f"{api}/journal-favorites/{favorite['id']}"
    assert expect(client.post(f"{journal_path}/refresh"))["added"] == 2
    feed = expect(client.get(journal_path))
    [call] = feed["calls"]
    assert call["deadline"] == deadline
    assert next(p for p in feed["papers"] if p["title"] == latest.title)["library_id"] == hit["paper"]["library_id"]
    opened = {"url": latest.url, "doi": latest.doi, "event_id": str(uuid4())}
    assert expect(client.post(f"{api}/library/activity/open", json=opened))["open_count"] == 1
    assert expect(client.post(f"{api}/library/activity/open", json=opened))["open_count"] == 1
    expect(client.post(f"{api}/library/activity/read", json={**opened, "read": True}))
    assert expect(client.get(f"{api}/inbox", params={"project_id": topic, "unread_only": True}))["items"] == []
    assert expect(client.get(journal_path))["favorite"]["unread"] == 1

    daily_path = f"{project}/daily-reading"
    expect(client.put(daily_path, json={"q": "solar daily", "start_on": today, "timezone": "UTC",
                                       "local_time": "13:45", "papers_per_day": 2, "enabled": False}))
    edition = expect(client.post(f"{daily_path}/check"))["edition"]
    [daily_entry] = edition["papers"]
    assert daily_entry["paper"]["title"] == daily.title
    assert edition["trend"]["topics"][0]["change_pp"] == 20
    retried_edition = expect(client.post(f"{daily_path}/check"))["edition"]
    assert retried_edition["papers"] == edition["papers"]

    paper_ref = {"kind": "library", "run_id": daily_entry["paper"]["library_id"], "paper_url": daily.url}
    record = expect(client.post(f"{work}/reading/from-source", json=paper_ref), 201)
    brief = expect(client.post(f"{work}/ideas", json={"data": {
        "question": "Do results transfer between regions?", "evidence": [record["id"]],
        "method": "Hold out a region", "data_access": "to_check", "next_step": "Find a second region",
    }}), 201)
    draft = expect(client.post(f"{work}/manuscripts", json={"data": {
        "title": "Regional forecasting", "article_type": "original", "idea_id": brief["id"],
    }}), 201)
    draft_path = f"{work}/manuscripts/{draft['id']}"
    data = {**draft["data"], "next_action": "Check the sample", "sections": [
        {"heading": "Introduction", "text": "The earlier study used sensors [@ref1]."},
    ], "inline_citations": {"ref1": record["id"]}}
    expect(client.put(f"{draft_path}/autosave", json={"revision": 1, "autosave_version": 0, "data": data}))
    saved = expect(client.post(f"{api}/special-issues/{call['id']}/save",
                               json={"project_id": topic, "draft_id": draft["id"]}), 201)
    assert expect(client.get(f"{draft_path}/autosave"))["item"] is None

    target = {"route": "docentlik", "field": "Engineering", "period": "2027 March",
              "criteria_url": "https://example.org/official-criteria"}
    expect(client.post(f"{work}/dossier-profile", json={"data": target}), 201)
    evidence = expect(client.post(f"{api}/portfolio/activities", json={
        "kind": "publication", "title": "Previous published research", "evidence_date": today,
        "evidence_url": "https://example.org/publication",
    }), 201)
    expect(client.post(f"{work}/dossier-rules", json={"data": {
        "title": "Indexed original publication", "clause": "Table 1", "status": "reviewed",
        "official_url": target["criteria_url"], "portfolio_activity_ids": [evidence["id"]],
    }}), 201)

    reopened = TestClient(create_app(ProjectStore(db_path)))
    assert expect(reopened.get(f"{project}/searches"))["searches"][0]["id"] == baseline["search_run_id"]
    assert expect(reopened.get(f"{api}/projects/{another}/workspace/manuscripts"))["items"] == []
    assert expect(reopened.get(daily_path))["edition"] == retried_edition
    assert expect(reopened.get(journal_path))["calls"][0]["id"] == call["id"]
    today_page = expect(reopened.get(f"{api}/today"))
    assert today_page["followed_journals"][0]["unread"] == 1
    assert today_page["reading"][0]["total"] == 1
    assert today_page["manuscripts"][0]["next_action"] == "Check the sample"
    assert today_page["deadlines"][0]["date"] == deadline
    [draft_after] = expect(reopened.get(f"{work}/manuscripts"))["items"]
    assert draft_after["data"]["submission_id"] == saved["id"]
    document = reopened.get(f"{draft_path}/export", params={"format": "docx"})
    assert document.status_code == 200
    paragraphs = [p.text for p in Document(BytesIO(document.content)).paragraphs]
    assert "The earlier study used sensors [1]." in paragraphs
    assert any(daily.title in paragraph for paragraph in paragraphs)
    dossier = reopened.get(f"{work}/dossier/export")
    assert dossier.status_code == 200 and evidence["data"]["evidence_url"] in dossier.text
    assert engine.search.call_count == 4


def test_brief_assistant_uses_only_the_selected_topics_evidence(monkeypatch):
    app, _, _, _, _, _ = fixture_app(ProjectStore(":memory:"), monkeypatch)
    client = TestClient(app)
    for header in ("OPENAI_API_KEY", "ANTHROPIC_API_KEY"):
        monkeypatch.delenv(header, raising=False)
    first_topic = expect(client.post("/api/v1/projects", json={"name": "First topic"}), 201)
    second_topic = expect(client.post("/api/v1/projects", json={"name": "Second topic"}), 201)
    first = f"/api/v1/projects/{first_topic['id']}"
    second = f"/api/v1/projects/{second_topic['id']}"
    found = expect(client.get("/api/v1/search", params={"q": "solar forecasting", "providers": "openalex"}))
    [paper] = found["results"]
    reference = expect(client.post(f"{first}/workspace/reading/from-source", json={
        "kind": "library", "run_id": paper["library_id"], "paper_url": paper["url"],
    }), 201)
    brief = expect(client.post(f"{first}/workspace/ideas", json={"data": {
        "question": "Do results transfer between regions?", "evidence": [reference["id"]],
    }}), 201)
    request = {"provider": "openai", "action": "brief", "idea_id": brief["id"]}
    post = Mock()
    monkeypatch.setattr(workspace_assistant.requests, "post", post)

    assert client.post(f"{first}/assistant", json=request).status_code == 503
    assert client.post(f"{second}/assistant", json=request).status_code == 404
    post.assert_not_called()
    monkeypatch.setenv("OPENAI_API_KEY", "fixture-key")
    monkeypatch.setenv("ACADEMIC_OPENAI_MODEL", "fixture-model")
    response = {"suggestions": [{"text": "Compare other regions.", "source_ids": ["P1"]}], "gaps": []}
    post.return_value = Mock(status_code=200, json=Mock(return_value={"output": [
        {"type": "message", "content": [{"type": "output_text", "text": json.dumps(response)}]},
    ]}))
    output = expect(client.post(f"{first}/assistant", json=request))
    assert any(source.get("url") == paper["url"] for source in output["sources"])
    assert expect(client.get(f"{first}/workspace/ideas"))["items"] == [brief]
    post.assert_called_once()
