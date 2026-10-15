"""
Regression: on 2026-10-15 a POST /youtube-sentiment/collect froze the whole
server (yt_dlp / transcript calls are blocking I/O inside async code), /health
timed out and the readiness probe pulled the pod from the Service.

Collection pipelines now run via api.off_loop.run_off_loop, so a blocking
pipeline stalls only its worker thread. These tests make the pipeline block with
time.sleep (as yt_dlp does) and assert /health still answers meanwhile.
"""
import time
from unittest.mock import patch

from fastapi import FastAPI
from fastapi.testclient import TestClient

from api.dependencies import get_db_manager
from api.off_loop import run_off_loop
from api.routers import external_analysis, youtube_sentiment
from database.db_manager import DatabaseManager

BLOCK_SECONDS = 1.5


class FakeDB:
    PoolExhaustedError = DatabaseManager.PoolExhaustedError

    def get_connection(self):
        class _Cur:
            def execute(self, *_): pass
            def fetchone(self): return (1,)

        class _Conn:
            def cursor(self): return _Cur()
        return _Conn()

    def return_connection(self, _):
        pass

    def query(self, *_a, **_k):
        return []


class BlockingUseCase:
    def __init__(self, *_a, **_k):
        pass

    async def execute(self, **_k):
        time.sleep(BLOCK_SECONDS)  # synchronous I/O inside async code, like yt_dlp
        return {"scraped": 0, "saved": 0, "analyzed": 0}


def _app():
    app = FastAPI()
    app.include_router(external_analysis.router, prefix="/api/external/v1")
    app.include_router(youtube_sentiment.router, prefix="/api/external/v1")
    app.dependency_overrides[get_db_manager] = lambda: FakeDB()
    return app


def test_run_off_loop_returns_the_pipeline_result():
    async def pipeline():
        return 42

    import asyncio
    loop = asyncio.new_event_loop()
    try:
        assert loop.run_until_complete(run_off_loop(pipeline)) == 42
    finally:
        loop.close()


def test_youtube_collect_returns_at_once_and_health_answers_while_it_runs():
    """F23 gives up after 8s, so the collect must answer at once and run in the
    background; /health must stay fast while the blocking pipeline runs."""
    from api.youtube_scheduler import scheduler

    scheduler.is_running = False
    with patch("application.use_cases.collect_youtube_sentiment_use_case.CollectYouTubeSentimentUseCase", BlockingUseCase), \
         patch("scrapers.youtube_scraper.YouTubeScraper", lambda **_k: None), \
         patch.object(youtube_sentiment, "_build_sentiment_analyzer", lambda: None), \
         TestClient(_app()) as client:
        t0 = time.monotonic()
        started = client.post(
            "/api/external/v1/youtube-sentiment/collect",
            json={"channels": ["https://www.youtube.com/@x/videos"], "days_back": 1, "limit_per_channel": 1},
        )
        post_elapsed = time.monotonic() - t0
        second = client.post("/api/external/v1/youtube-sentiment/collect", json={"days_back": 1})

        t0 = time.monotonic()
        health = client.get("/api/external/v1/health")
        health_elapsed = time.monotonic() - t0

        deadline = time.monotonic() + 10
        while scheduler.is_running and time.monotonic() < deadline:
            time.sleep(0.05)
        schedule = client.get("/api/external/v1/youtube-sentiment/schedule").json()

    assert started.status_code == 200 and started.json()["status"] == "started"
    assert post_elapsed < 0.5, f"collect held the request for {post_elapsed:.2f}s"
    assert second.status_code == 409
    assert health.status_code == 200
    assert health_elapsed < 0.5, f"/health waited {health_elapsed:.2f}s behind a blocking collect"
    assert schedule["is_running"] is False
    assert schedule["last_result"]["scraped"] == 0


def test_fundamental_miss_skips_kap_fetch_while_firecrawl_sleeps():
    spawned = []
    with patch.object(external_analysis, "_firecrawl_capabilities_cache", {"status": "unavailable"}), \
         patch.object(external_analysis, "_spawn_on_demand_fetch", lambda *a, **k: spawned.append(a)):
        r = TestClient(_app()).get("/api/external/v1/fundamental/THYAO?market=bist")
    assert r.json()["status"] == "unavailable"
    assert spawned == []
