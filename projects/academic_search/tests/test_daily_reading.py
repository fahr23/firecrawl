"""Daily schedules, provider-backed editions, and shared reading state."""

import asyncio
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, Mock
from uuid import uuid4

from fastapi.testclient import TestClient

from academic_search import daily_api, daily_store
from academic_search.project_store import ProjectStore
from academic_search.service import create_app, get_journal_searcher, get_search_engine
from academic_search.tests.test_literature_library import paper, result, search
from academic_search.tests.test_research_workflow import topic


def path(project_id):
    return f"/api/v1/projects/{project_id}/daily-reading"


def settings(query="solar forecasting", **extra):
    return {"q": query, "start_on": "2026-08-01", "local_time": "08:00", "timezone": "Europe/Istanbul",
            "papers_per_day": 2, **extra}


def fixture(store):
    app = create_app(store)
    engine = Mock()
    trends = Mock(BASE_URL="https://api.openalex.org", email="")
    trends.last_failure = None
    trend_filters = []

    def grouped(url, params):
        assert url == "https://api.openalex.org/works"
        assert params["group_by"] == "primary_topic.id"
        trend_filters.append(params["filter"])
        count = 32 if len(trend_filters) % 2 == 0 else 12
        return {"meta": {"count": 100}, "group_by": [
            {"key": "https://openalex.org/T123", "key_display_name": "Battery storage", "count": count}
        ]}

    trends._make_request.side_effect = grouped
    app.dependency_overrides[get_search_engine] = lambda: engine
    app.dependency_overrides[get_journal_searcher] = lambda: trends
    return TestClient(app), engine, trends, trend_filters


def article(key, published, doi=None, **metadata):
    source = paper(key, doi=doi, year=published[:4])
    source.raw_data = {"publication_date": published, **metadata}
    return source


def recommended(edition):
    return [item["paper"]["title"] for item in edition["papers"]]


def test_daily_editions_exclude_prior_suggestions_across_topics_and_keep_read_history(tmp_path, monkeypatch):
    target = str(tmp_path / "projects.db")
    client, engine, _, filters = fixture(ProjectStore(target))
    now = datetime(2026, 9, 1, 10, tzinfo=timezone.utc)
    monkeypatch.setattr(daily_store, "clock", lambda: now)
    first_id = topic(client, "Solar")
    second_id = topic(client, "Energy markets")
    overlap = article("overlap", "2026-08-31", doi="10.1234/shared")
    alternate = article("alternate", "2026-08-31", doi="10.1234/SHARED")
    older = article("older", "2026-08-28")
    fresh = article("fresh", "2026-08-30")
    third = article("third", "2026-09-01")
    next_day = article("tomorrow", "2026-09-02")
    future = article("future", "2026-11-08")
    retracted = article("withdrawn", "2026-09-01", is_retracted=True)
    engine.search.side_effect = [
        result(older, overlap, future, retracted), result(alternate, fresh, third), result(overlap, older, next_day),
    ]
    assert client.put(path(first_id), json=settings()).status_code == 200
    assert client.put(path(second_id), json=settings("energy market", timezone="UTC", local_time="15:30")).status_code == 200
    first = client.post(path(first_id) + "/check").json()["edition"]
    assert first["day"] == "2026-09-01"
    assert recommended(first) == [overlap.title, older.title]
    assert first["trend"]["topics"][0]["change_pp"] == 20
    assert "from_publication_date:2026-07-03,to_publication_date:2026-08-01" in filters[0]
    assert "from_publication_date:2026-08-02,to_publication_date:2026-08-31" in filters[1]
    assert client.post(path(first_id) + "/check").json()["edition"] == first
    assert engine.search.call_count == 1

    second = client.post(path(second_id) + "/check").json()["edition"]
    assert recommended(second) == [third.title, fresh.title]
    ref = {"url": overlap.url, "doi": overlap.doi}
    client.post("/api/v1/library/activity/open", json={**ref, "event_id": str(uuid4())})
    assert client.get(path(first_id)).json()["history"][0]["read"] == 0
    client.post("/api/v1/library/activity/read", json={**ref, "read": True})
    assert client.get(path(first_id)).json()["history"][0]["read"] == 1

    now += timedelta(days=1)
    day_two = client.post(path(first_id) + "/check").json()["edition"]
    assert recommended(day_two) == [next_day.title]
    reopened = ProjectStore(target)
    previous = reopened.daily.view(first_id, "2026-09-01")["edition"]
    assert recommended(previous) == [overlap.title, older.title]
    assert previous["papers"][0]["read_at"] and not previous["papers"][1]["read_at"]
    client.post("/api/v1/library/activity/read", json={**ref, "read": False})
    assert client.get(path(first_id), params={"day": "2026-09-01"}).json()["history"][-1]["read"] == 0
    assert len(client.get("/api/v1/daily-reading").json()["items"]) == 2


def test_different_times_timezones_start_dates_and_pause(monkeypatch):
    store = ProjectStore(":memory:")
    client, engine, _, _ = fixture(store)
    now = datetime(2026, 9, 1, 5, tzinfo=timezone.utc)
    monkeypatch.setattr(daily_store, "clock", lambda: now)
    local_id = topic(client, "Local time")
    utc_id = topic(client, "Other time")
    later_id = topic(client, "Later start")
    paused_id = topic(client, "Paused")
    for project_id, data in [
        (local_id, settings()), (utc_id, settings(timezone="UTC", local_time="08:30")),
        (later_id, settings(start_on="2026-09-02")), (paused_id, settings(enabled=False)),
    ]:
        assert client.put(path(project_id), json=data).status_code == 200

    assert store.daily.due() == [local_id]
    assert client.get(path(utc_id)).json()["next_run_at"] == "2026-09-01T08:30:00+00:00"
    assert client.get(path(later_id)).json()["next_run_at"] == "2026-09-02T05:00:00+00:00"
    assert client.get(path(paused_id)).json()["next_run_at"] is None
    assert client.post(path(later_id) + "/check").status_code == 409
    assert engine.search.call_count == 0
    assert client.put(path(later_id), json=settings(timezone="Bad/Zone")).status_code == 422
    assert client.put(path(later_id), json=settings(local_time="25:00")).status_code == 422
    assert client.put(path(later_id), json=settings(providers=" , ")).status_code == 422
    lease = store.daily.claim(local_id, now)
    assert lease["day"] == "2026-09-01"
    assert store.daily.claim(local_id, now, manual=True) is None
    assert local_id not in store.daily.due()
    store.daily.release(local_id, lease["day"], lease["token"])
    now += timedelta(hours=4)
    assert set(store.daily.due()) == {local_id, utc_id}


def test_failed_provider_uses_unseen_local_papers_and_retries_missing_trends(monkeypatch):
    store = ProjectStore(":memory:")
    client, engine, openalex, _ = fixture(store)
    now = datetime(2026, 9, 1, 10, tzinfo=timezone.utc)
    monkeypatch.setattr(daily_store, "clock", lambda: now)
    unread = article("unread", "2026-08-29")
    already_opened = article("opened", "2026-08-30")
    already_read = article("read", "2026-08-24")
    engine.search.side_effect = [result(already_opened, already_read, unread), result(failed="OpenAlex")]
    topic_id = topic(client, "Solar")
    search(client)
    client.post("/api/v1/library/activity/open", json={"url": already_opened.url, "event_id": str(uuid4())})
    client.post("/api/v1/library/activity/read", json={"url": already_read.url, "read": True})
    openalex.last_failure = {"code": "rate_limited"}
    openalex._make_request.side_effect = [None, None, {"meta": {"count": 0}, "group_by": []},
                                           {"meta": {"count": 0}, "group_by": []}]
    assert client.put(path(topic_id), json=settings(papers_per_day=1)).status_code == 200
    partial = client.post(path(topic_id) + "/check").json()
    edition = partial["edition"]
    assert recommended(edition) == [unread.title]
    assert edition["papers"][0]["source"] == "library"
    assert edition["status"] == "partial" and edition["coverage"][0]["status"] == "rate_limited"
    assert edition["trend"]["topics"] == []
    assert partial["next_run_at"] == "2026-09-01T12:00:00+00:00"
    assert store.daily.due() == []
    now += timedelta(hours=2)
    assert store.daily.due() == [topic_id]
    retried = client.post(path(topic_id) + "/check").json()
    assert recommended(retried["edition"]) == [unread.title]
    assert retried["edition"]["trend"]["errors"] == {}
    assert retried["next_run_at"] == "2026-09-02T05:00:00+00:00"
    assert engine.search.call_count == 2


def test_running_service_builds_due_editions_without_a_browser(monkeypatch):
    store = ProjectStore(":memory:")
    client, _, _, _ = fixture(store)
    now = datetime(2026, 9, 1, 10, tzinfo=timezone.utc)
    monkeypatch.setattr(daily_store, "clock", lambda: now)
    project_id = topic(client, "Due today")
    future_id = topic(client, "Starting tomorrow")
    client.put(path(project_id), json=settings())
    client.put(path(future_id), json=settings(start_on="2026-09-02"))
    fetch = AsyncMock(return_value={"results": [], "provider_coverage": []})
    trends = Mock()
    trends._make_request.return_value = {"meta": {"count": 0}, "group_by": []}
    monkeypatch.setattr(daily_api.asyncio, "sleep", AsyncMock(side_effect=[None, asyncio.CancelledError]))

    async def run():
        try:
            await daily_api.daily_scheduler(store, lambda: object(), lambda: trends, fetch)
        except asyncio.CancelledError:
            pass

    asyncio.run(run())
    assert fetch.await_count == 1
    assert store.daily.view(project_id)["edition"]["status"] == "ready"
    assert store.daily.view(future_id)["edition"] is None
