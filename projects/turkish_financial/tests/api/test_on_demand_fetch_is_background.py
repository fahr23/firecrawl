"""
Regression tests for provider-wait-list.md §7 P1/P2/P5:

  P1: a fundamental/market cache miss used to await a live scrape inline in
      the request, blocking the single event loop for 45s+ and taking the
      whole pod's readiness probe down with it. A cache miss must now return
      the current (unavailable) envelope immediately and fire the scrape as
      a detached background task instead.
  P2: the on-demand fundamental fetch used to try KAP's dead `member/filter`
      POST (confirmed live 404) before falling back to the working GET-based
      OID resolution — wasting a 45s+ proxy cascade on every miss. It must
      now go straight to the GET fallback.

These drive the real FastAPI endpoints end-to-end (not just the helper
functions) so a regression in either router would be caught here, while
mocking the scraper/fetchers themselves so no live network call is made.
"""
import asyncio
import time
from unittest.mock import AsyncMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from api.dependencies import get_db_manager
from api.routers import external_analysis
from database.db_manager import DatabaseManager


class FakeDB:
    PoolExhaustedError = DatabaseManager.PoolExhaustedError

    def __init__(self):
        pass

    def query(self, sql, params=None):
        return []  # always a cache miss


def make_client(db) -> TestClient:
    app = FastAPI()
    app.include_router(external_analysis.router, prefix="/api/external/v1")
    app.dependency_overrides[get_db_manager] = lambda: db
    return TestClient(app)


# A spawned background task outlives the request (that's the point of the
# fix), so it also outlives the short-lived event loop TestClient creates per
# call. A long real `asyncio.sleep` would get cancelled when that loop closes
# underneath it, which is harmless for the app but noisy (and, left running
# across many tests, can disturb unrelated sync asyncio tests elsewhere in
# the suite). A short, fixed sleep proves the same thing — the request must
# return well before it — while keeping orphaned tasks short-lived.
_SLOW_FETCH_SECONDS = 0.3


@pytest.fixture(autouse=True)
def _clear_in_flight():
    external_analysis._on_demand_fetch_in_flight.clear()
    yield
    external_analysis._on_demand_fetch_in_flight.clear()


class TestFundamentalCacheMissDoesNotBlock:
    def test_point_returns_fast_without_awaiting_the_scrape(self):
        """P1: a slow KAP scrape must not make the request wait for it."""
        slow_scrape = AsyncMock(side_effect=lambda *a, **k: asyncio.sleep(_SLOW_FETCH_SECONDS))
        with patch.object(
            external_analysis, "_fetch_fundamental_in_background", slow_scrape
        ):
            client = make_client(FakeDB())
            t0 = time.monotonic()
            r = client.get("/api/external/v1/fundamental/THYAO?market=bist")
            elapsed = time.monotonic() - t0

        assert r.status_code == 200
        assert r.json()["status"] == "unavailable"
        assert elapsed < _SLOW_FETCH_SECONDS, f"request blocked for {elapsed}s waiting on the scrape"

    def test_batch_returns_fast_without_awaiting_the_scrape(self):
        slow_scrape = AsyncMock(side_effect=lambda *a, **k: asyncio.sleep(_SLOW_FETCH_SECONDS))
        with patch.object(
            external_analysis, "_fetch_fundamental_in_background", slow_scrape
        ):
            client = make_client(FakeDB())
            t0 = time.monotonic()
            r = client.post(
                "/api/external/v1/fundamental/batch",
                json={"market": "bist", "instruments": ["THYAO", "AKBNK"]},
            )
            elapsed = time.monotonic() - t0

        assert r.status_code == 200
        assert elapsed < _SLOW_FETCH_SECONDS, f"batch request blocked for {elapsed}s waiting on the scrape"

    def test_concurrent_health_is_not_blocked_by_a_slow_fundamental_fetch(self):
        """The actual P1 symptom: a fundamental miss must not starve /health."""
        slow_scrape = AsyncMock(side_effect=lambda *a, **k: asyncio.sleep(_SLOW_FETCH_SECONDS))
        with patch.object(external_analysis, "_fetch_fundamental_in_background", slow_scrape):
            client = make_client(FakeDB())
            fundamental_resp = client.get("/api/external/v1/fundamental/THYAO?market=bist")
            assert fundamental_resp.json()["status"] == "unavailable"

            t0 = time.monotonic()
            health_resp = client.get("/api/external/v1/health")
            elapsed = time.monotonic() - t0

        assert health_resp.status_code == 200
        assert elapsed < _SLOW_FETCH_SECONDS, f"/health blocked for {elapsed}s behind the fundamental fetch"


class TestFundamentalOidResolutionSkipsDeadPost:
    def test_skips_member_filter_post_and_goes_straight_to_get_fallback(self):
        """P2: `refresh_member_oids` (the dead POST) must never be called from
        the on-demand path — only the working GET-based fallback.

        Driven through the real `/fundamental/{instrument}` endpoint (via
        TestClient, not a bare `asyncio.run`, which was observed to corrupt
        the default event loop policy for unrelated legacy-style async tests
        elsewhere in the suite) so the spawned background task actually runs
        before the assertions below.
        """
        from scrapers.kap_scraper import KAPScraper

        post_based = AsyncMock()
        get_based = AsyncMock(return_value={"success": True, "resolved": 1})
        scrape_statements = AsyncMock()

        with patch.object(KAPScraper, "refresh_member_oids", post_based), \
             patch.object(KAPScraper, "refresh_member_oids_via_get", get_based), \
             patch.object(KAPScraper, "scrape_financial_statements", scrape_statements), \
             patch(
                 "infrastructure.contracts.instrument_identity_map.resolve_member_oid",
                 return_value=None,
             ):
            client = make_client(FakeDB())
            client.get("/api/external/v1/fundamental/THYAO?market=bist")
            for _ in range(50):
                if get_based.await_count or post_based.call_count:
                    break
                time.sleep(0.02)

        post_based.assert_not_called()
        get_based.assert_awaited_once()


class TestMarketCacheMissDoesNotBlock:
    def test_point_returns_fast_without_awaiting_the_fetch(self):
        slow_fetch = AsyncMock(side_effect=lambda *a, **k: asyncio.sleep(_SLOW_FETCH_SECONDS))
        with patch.object(external_analysis, "_fetch_market_in_background", slow_fetch):
            client = make_client(FakeDB())
            t0 = time.monotonic()
            r = client.get("/api/external/v1/market/AAPL?market=usa")
            elapsed = time.monotonic() - t0

        assert r.status_code == 200
        assert r.json()["status"] == "unavailable"
        assert elapsed < _SLOW_FETCH_SECONDS, f"request blocked for {elapsed}s waiting on the fetch"


class TestInFlightDedup:
    def test_concurrent_requests_for_same_instrument_spawn_only_one_fetch(self):
        """Production concurrency is many coroutines on uvicorn's single event
        loop (not threads), so this drives `_spawn_on_demand_fetch` directly
        with `asyncio.gather` to reproduce two truly-concurrent requests
        racing to resolve the same (kind, market, instrument) key.

        Runs on a brand-new loop in a background thread (via
        `asyncio.new_event_loop` + `run_until_complete`, never touching this
        thread's default loop) rather than `asyncio.run` in the main thread:
        the latter was observed to leave the default event loop policy in a
        state that broke unrelated legacy `asyncio.get_event_loop()` tests
        later in the same pytest process.
        """
        import threading

        call_count = 0

        async def scenario():
            nonlocal call_count

            async def counted_fetch():
                nonlocal call_count
                call_count += 1
                await asyncio.sleep(0.2)

            key = ("fundamental", "bist", "THYAO")

            async def spawn():
                external_analysis._spawn_on_demand_fetch(key, counted_fetch)

            await asyncio.gather(spawn(), spawn(), spawn())
            await asyncio.sleep(0.4)  # let the spawned tasks finish

        def _run_in_isolated_loop():
            loop = asyncio.new_event_loop()
            try:
                loop.run_until_complete(scenario())
            finally:
                loop.close()

        t = threading.Thread(target=_run_in_isolated_loop)
        t.start()
        t.join(timeout=5)

        assert call_count == 1, f"expected exactly one fetch, got {call_count}"
