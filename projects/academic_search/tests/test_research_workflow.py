"""API and persistence coverage for the research inbox and publishing follow-up."""

import asyncio
from datetime import date, timedelta
from unittest.mock import AsyncMock, Mock
from uuid import uuid4

from academic_search import Config
from academic_search.project_store import ProjectStore
from academic_search.providers import OpenAlexSearcher
from academic_search.service import create_app, get_search_engine
from academic_search import workflow_api
from academic_search.tests.test_literature_library import paper, result, search
from academic_search.tests.test_reproducibility import fixture_engine
from academic_search.tests.test_service import make_client
from fastapi.testclient import TestClient


def topic(client, name):
    return client.post("/api/v1/projects", json={"name": name}).json()["id"]


def workspace(client, project, section, data, entry=None):
    url = f"/api/v1/projects/{project}/workspace/{section}"
    if entry:
        return client.put(f"{url}/{entry['id']}", json={"data": data, "revision": entry["revision"]})
    return client.post(url, json={"data": data})


def test_watched_search_preserves_baseline_deduplicates_and_survives_429(tmp_path):
    store_path = str(tmp_path / "projects.db")
    baseline = paper("baseline")
    recent = paper("recent")
    recent.raw_data = {"publication_date": date.today().isoformat()}
    old = paper("older")
    engine = Mock()
    engine.search.side_effect = [result(baseline), result(baseline, old, recent), result(failed="OpenAlex")]
    app = create_app(ProjectStore(store_path))
    app.dependency_overrides[get_search_engine] = lambda: engine
    client = TestClient(app)
    pid = topic(client, "Solar capacity")
    other = topic(client, "Energy systems")
    search(client, q="solar storage", project_id=pid)
    path = f"/api/v1/projects/{pid}/watches"
    created = client.post(path, json={"q": " solar storage ", "providers": "openalex"})
    watch = created.json()
    assert created.status_code == 201
    assert client.post(path, json={"q": "solar storage"}).json()["id"] == watch["id"]
    assert client.get("/api/v1/inbox").json() == {"items": []}
    base = f"{path}/{watch['id']}"
    assert client.post(f"/api/v1/projects/{other}/watches/{watch['id']}/refresh").status_code == 404

    refreshed = client.post(f"{base}/refresh").json()
    assert refreshed["added"] == 2 and refreshed["watch"]["unread"] == 2
    success = refreshed["watch"]["last_success_at"]
    feed = client.get("/api/v1/inbox", params={"project_id": pid, "unread_only": True}).json()["items"]
    assert {row["paper"]["title"]: row["freshness"] for row in feed} == {
        old.title: "discovered", recent.title: "recent",
    }

    failed = client.post(f"{base}/refresh").json()
    assert failed["added"] == 0
    assert failed["watch"]["last_success_at"] == success
    assert failed["watch"]["coverage"][0]["status"] == "rate_limited"
    assert engine.search.call_count == 3
    assert client.get("/api/v1/watches").json()["unread_by_topic"] == {pid: 2}
    assert client.post(f"{base}/seen", json={"library_id": int(feed[0]["paper"]["library_id"])}).json() == {"marked": 1}
    assert ProjectStore(store_path).workflow.watch(pid, watch["id"])["unread"] == 1


def test_watch_schedule_and_claims_prevent_overlapping_checks():
    store = ProjectStore(":memory:")
    client = TestClient(create_app(store))
    pid = topic(client, "Storage")
    base = f"/api/v1/projects/{pid}/watches"
    created = client.post(base, json={"q": "battery storage", "interval_hours": 24}).json()
    watch_id = created["id"]
    assert store.workflow.due() == [(pid, watch_id)]
    token = store.workflow.claim_watch(pid, watch_id)
    assert token
    assert store.workflow.claim_watch(pid, watch_id) is None
    assert client.post(f"{base}/{watch_id}/refresh").status_code == 409
    assert store.workflow.due() == []
    assert store.workflow.finish_watch(watch_id, token, [], [], True) == 0
    assert store.workflow.due() == []
    scheduled = client.patch(f"{base}/{watch_id}", json={"label": "Storage", "interval_hours": 168}).json()
    assert scheduled["interval_hours"] == 168 and scheduled["label"] == "Storage"
    assert scheduled["due_at"] > scheduled["last_success_at"]
    assert client.delete(f"{base}/{watch_id}").status_code == 200
    assert store.workflow.watch(pid, watch_id) is None


def test_scheduler_refreshes_due_watches_without_a_browser(monkeypatch):
    store = ProjectStore(":memory:")
    client = TestClient(create_app(store))
    pid = topic(client, "Scheduled topic")
    base = f"/api/v1/projects/{pid}/watches"
    manual = client.post(base, json={"q": "manual query"}).json()
    daily = client.post(base, json={"q": "daily query", "interval_hours": 24}).json()
    fetch = AsyncMock(return_value={"provider_coverage": [], "results": [], "new_work_ids": set(),
                                   "pagination": {"partial": False}})
    monkeypatch.setattr(workflow_api.asyncio, "sleep", AsyncMock(side_effect=[None, asyncio.CancelledError]))

    async def advance():
        try:
            await workflow_api.watch_scheduler(store, lambda: None, fetch)
        except asyncio.CancelledError:
            pass

    asyncio.run(advance())
    assert fetch.await_count == 1 and fetch.call_args.args[2] == "daily query"
    assert store.workflow.watch(pid, daily["id"])["last_success_at"]
    assert store.workflow.watch(pid, manual["id"])["last_attempt_at"] is None


def test_watch_requests_publication_date_order_without_replacing_exact_cache(monkeypatch):
    provider = OpenAlexSearcher(Config())
    calls = []

    def upstream(url, params):
        calls.append(params["sort"])
        return {"meta": {"count": 1}, "results": [{
            "id": "https://openalex.org/W1", "title": "Battery storage",
            "publication_year": 2025, "publication_date": "2025-10-18",
        }]}

    monkeypatch.setattr(provider, "_make_request", upstream)
    client, _, _ = make_client(fixture_engine(provider))
    pid = topic(client, "Watching dates")
    search(client, q="storage")
    base = f"/api/v1/projects/{pid}/watches"
    watch_id = client.post(base, json={"q": "storage"}).json()["id"]

    assert client.post(f"{base}/{watch_id}/refresh").json()["added"] == 0
    assert calls == ["relevance_score:desc", "publication_date:desc"]
    assert client.get("/api/v1/search", params={"q": "storage", "mode": "cache"}).json()["results"][0]["publication_date"] == "2025-10-18"


def test_paper_history_keeps_doi_alias_counts_and_explicit_read_state():
    engine = Mock()
    doi = "10.1234/storage"
    original = paper("storage", doi=doi)
    engine.search.return_value = result(original)
    client, _, _ = make_client(engine)
    pid = topic(client, "Grid")
    watch = client.post(f"/api/v1/projects/{pid}/watches", json={"q": "storage"}).json()
    client.post(f"/api/v1/projects/{pid}/watches/{watch['id']}/refresh")
    refs = [{"url": original.url, "doi": doi}, {"url": f"https://doi.org/{doi}", "doi": doi}]
    path = "/api/v1/library/activity"
    event = str(uuid4())

    assert client.post(f"{path}/open", json={**refs[0], "event_id": event}).json()["open_count"] == 1
    assert client.post(f"{path}/open", json={**refs[0], "event_id": event}).json()["open_count"] == 1
    assert client.post(f"{path}/open", json={**refs[1], "event_id": str(uuid4())}).json()["read_at"] is None
    status = client.post(f"{path}/read", json={**refs[1], "read": True}).json()
    assert status["open_count"] == 2 and status["read_at"]
    assert client.get("/api/v1/watches").json()["unread_by_topic"] == {}
    rows = client.post(f"{path}/lookup", json={"papers": refs}).json()["items"]
    assert rows == [status, status]
    history = client.get(path).json()["items"]
    assert len(history) == 1 and history[0]["doi"] == doi
    assert {row["url"]: row["open_count"] for row in history[0]["urls"]} == {
        original.url: 1, f"https://doi.org/{doi}": 1,
    }
    assert client.get(path, params={"q": doi.upper()}).json()["items"] == history
    assert client.get(path, params={"q": "https://example.org/storage"}).json()["items"] == history
    assert client.get(path, params={"q": "different DOI"}).json()["items"] == []
    assert client.post(f"{path}/read", json={**refs[0], "read": False}).json()["read_at"] is None
    assert client.post(f"{path}/open", json={**refs[0], "url": "https://example.org/not-a-paper",
                                           "event_id": str(uuid4())}).status_code == 404


def test_submissions_track_reviewer_history_and_export_calendar():
    client, _, _ = make_client()
    pid = topic(client, "Forecasting")
    other = topic(client, "Sustainability")
    call_date = (date.today() + timedelta(days=5)).isoformat()
    revision_date = (date.today() + timedelta(days=4)).isoformat()
    call = workspace(client, other, "submissions", {
        "title": "Open energy call", "source_url": "https://example.org/call",
        "status": "open", "deadline": call_date, "deadline_time": "20:30", "timezone": "Europe/Istanbul",
        "evidence": "Submissions are open until the listed deadline.",
    }).json()
    assert workspace(client, pid, "submission-tracking", {
        "title": "Other topic call", "opportunity_id": call["id"],
    }).status_code == 404
    initial = {"title": "Manuscript, v1", "status": "submitted", "submitted_on": date.today().isoformat()}
    tracker = workspace(client, pid, "submission-tracking", initial).json()
    update = {**initial, "status": "revision_requested", "revision_due": revision_date,
              "reviewer_comments": "Compare with the seasonal baseline."}
    revised = workspace(client, pid, "submission-tracking", update, tracker).json()
    entries = client.get("/api/v1/submission-calendar").json()["items"]
    assert [(entry["kind"], entry["date"]) for entry in entries] == [("revision", revision_date), ("call", call_date)]
    calendar = client.get("/api/v1/submission-calendar/export")
    assert calendar.status_code == 200
    assert "BEGIN:VCALENDAR\r\n" in calendar.text and "TRIGGER:-P7D" in calendar.text
    assert f"DTSTART:{call_date.replace('-', '')}T173000Z" in calendar.text
    assert r"Manuscript\, v1" in calendar.text
    assert len(client.get("/api/v1/submission-calendar", params={"project_id": pid}).json()["items"]) == 1

    history = client.get(f"/api/v1/projects/{pid}/workspace/submission-tracking/{tracker['id']}/history").json()
    assert [item["data"]["status"] for item in history["items"]] == ["revision_requested", "submitted"]
    assert history["items"][0]["data"]["reviewer_comments"] == update["reviewer_comments"]
    assert workspace(client, pid, "submission-tracking", {**update, "status": "resubmitted"}, revised).status_code == 200
    assert [item["kind"] for item in client.get("/api/v1/submission-calendar").json()["items"]] == ["call"]


def test_same_portfolio_evidence_can_support_multiple_targets_and_reopen_review():
    client, _, _ = make_client()
    projects = [topic(client, "Energy systems"), topic(client, "Teaching")]
    profile = {"route": "docentlik", "field": "Engineering", "period": "March 2027",
               "criteria_url": "https://example.org/criteria"}
    evidence = {"title": "Teaching record", "kind": "teaching", "evidence_url": "https://example.org/teaching",
                "evidence_date": "2026-10-08"}
    route = "/api/v1/portfolio/activities"
    activity = client.post(route, json=evidence).json()
    for pid in projects:
        assert workspace(client, pid, "dossier-profile", profile).status_code == 201
        criterion = {"title": "Teaching", "clause": "Section 1", "official_url": profile["criteria_url"],
                     "status": "reviewed", "portfolio_activity_ids": [activity["id"]]}
        assert workspace(client, pid, "dossier-rules", criterion).status_code == 201
        export = client.get(f"/api/v1/projects/{pid}/workspace/dossier/export")
        assert export.status_code == 200 and "Teaching record" in export.text
        assert evidence["evidence_url"] in export.text
    targets = client.get("/api/v1/portfolio/targets").json()["items"]
    assert len(targets) == 2 and all(row["reviewed_count"] == 1 for row in targets)

    assert client.put(f"{route}/{activity['id']}?revision=1", json={**evidence, "notes": "New proof"}).status_code == 200
    assert client.put(f"{route}/{activity['id']}?revision=1", json=evidence).status_code == 409
    assert all(row["reviewed_count"] == 0 for row in client.get("/api/v1/portfolio/targets").json()["items"])
    history = client.get(f"{route}/{activity['id']}/history").json()["items"]
    assert [item["revision"] for item in history] == [2, 1]
    assert [item["data"]["notes"] for item in history] == ["New proof", ""]


def test_previous_dossier_evidence_is_imported_once(tmp_path):
    path = str(tmp_path / "projects.db")
    first = ProjectStore(path)
    pid = first.create_project({"name": "Earlier topic"})["id"]
    previous = first.put_workspace_item(pid, "dossier-activities", {"title": "Earlier activity", "kind": "project",
                                        "reading_id": "", "evidence_url": "https://example.org/proof"})
    reopened = ProjectStore(path)
    [item] = reopened.workflow.portfolio()
    assert item["source_project_id"] == pid and item["source_item_id"] == previous["id"]
    assert ProjectStore(path).workflow.portfolio() == [item]
