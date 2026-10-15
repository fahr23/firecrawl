"""
Pre-collection runs (provider-wait-list §7 C5 + fundamental coverage):

  POST /market/collect       BIST market history for the universe, then FA-06
                             corporate-action detection per ticker
  POST /fundamental/collect  bounded batch of KAP financial statements,
                             never-collected tickers first

Both start a background task, refuse a concurrent run with 409, and expose a
collection-status endpoint. Fetchers/scrapers are mocked — no network.
"""
import time
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from api.dependencies import get_db_manager
from api.routers import external_analysis
from database.db_manager import DatabaseManager


class FakeDB:
    PoolExhaustedError = DatabaseManager.PoolExhaustedError

    def __init__(self, queue_rows=None):
        self.queue_rows = queue_rows or []
        self.market_upserts = []
        self.queries = []

    def query(self, sql, params=None):
        self.queries.append((sql, params))
        if "kap_fundamentals" in sql and "bist_companies" in sql:
            return self.queue_rows
        return []

    def upsert_isyatirim_market_history(self, ticker, series):
        self.market_upserts.append((ticker, series))
        return True


def make_client(db) -> TestClient:
    """Use as a context manager when a test waits on a background run: only
    then does TestClient keep one event loop alive across requests, so the
    task isn't cancelled the moment the triggering response returns."""
    app = FastAPI()
    app.include_router(external_analysis.router, prefix="/api/external/v1")
    app.dependency_overrides[get_db_manager] = lambda: db
    return TestClient(app)


def _wait(state, timeout=3.0):
    deadline = time.monotonic() + timeout
    while state["status"] == "running" and time.monotonic() < deadline:
        time.sleep(0.02)


@pytest.fixture(autouse=True)
def _reset_collectors():
    """Collector state is module-global; restore it so runs started here never
    leak into other tests (e.g. /capabilities' last_collection_run)."""
    saved = {
        name: dict(getattr(external_analysis, name))
        for name in ("_market_collection_state", "_kap_fundamental_collection_state")
    }
    external_analysis._market_collection_task = None
    external_analysis._kap_fundamental_collection_task = None
    yield
    for name, value in saved.items():
        state = getattr(external_analysis, name)
        state.clear()
        state.update(value)
    external_analysis._market_collection_task = None
    external_analysis._kap_fundamental_collection_task = None


class TestMarketCollect:
    def test_collects_history_and_detects_corporate_actions(self):
        db = FakeDB()
        detect = MagicMock(return_value={"detected": 1})
        repo = MagicMock(detect_and_persist=detect)
        with patch.object(external_analysis, "_active_bist_tickers", return_value=["THYAO", "AKBNK"]), \
             patch.object(external_analysis, "fetch_market_history", return_value={"series": [{"close_try": 1.0}]}) as fetch, \
             patch.object(external_analysis, "_corporate_action_repo", return_value=repo), \
             patch.dict("os.environ", {"ISYATIRIM_MARKET_COLLECTION_DELAY_SECONDS": "0.1"}):
            with make_client(db) as client:
                r = client.post("/api/external/v1/market/collect", json={"days": 30})
                assert r.status_code == 200
                assert r.json()["status"] == "started"
                _wait(external_analysis._market_collection_state)
                state = client.get("/api/external/v1/market/collection-status").json()

        assert state["status"] == "completed"
        assert state["fetched"] == 2
        assert state["corporate_actions_detected"] == 2
        assert [u[0] for u in db.market_upserts] == ["THYAO", "AKBNK"]
        fetch.assert_any_call("THYAO", 30)
        assert detect.call_count == 2

    def test_one_failing_ticker_does_not_stop_the_run(self):
        db = FakeDB()

        def flaky(ticker, days):
            if ticker == "THYAO":
                raise LookupError("no data")
            return {"series": []}

        with patch.object(external_analysis, "_active_bist_tickers", return_value=["THYAO", "AKBNK"]), \
             patch.object(external_analysis, "fetch_market_history", side_effect=flaky), \
             patch.object(external_analysis, "_corporate_action_repo", return_value=MagicMock(detect_and_persist=MagicMock(return_value={}))), \
             patch.dict("os.environ", {"ISYATIRIM_MARKET_COLLECTION_DELAY_SECONDS": "0.1"}):
            with make_client(db) as client:
                client.post("/api/external/v1/market/collect", json={})
                _wait(external_analysis._market_collection_state)

        state = external_analysis._market_collection_state
        assert state["failed"] == 1
        assert state["fetched"] == 1
        assert state["completed"] == 2

    def test_concurrent_run_is_refused(self):
        running = MagicMock()
        running.done.return_value = False
        external_analysis._market_collection_task = running
        r = make_client(FakeDB()).post("/api/external/v1/market/collect", json={})
        assert r.status_code == 409

    def test_days_out_of_range_rejected(self):
        r = make_client(FakeDB()).post("/api/external/v1/market/collect", json={"days": 0})
        assert r.status_code == 422


class TestFundamentalCollect:
    def test_queue_prefers_db_order_and_resolves_oid_via_get(self):
        from scrapers.kap_scraper import KAPScraper

        db = FakeDB(queue_rows=[{"code": "ASELS"}, {"code": "THYAO"}])
        via_get = AsyncMock(return_value={"success": True})
        via_post = AsyncMock()
        statements = AsyncMock(return_value={"success": True, "processed": 1})
        with patch.object(KAPScraper, "refresh_member_oids_via_get", via_get), \
             patch.object(KAPScraper, "refresh_member_oids", via_post), \
             patch.object(KAPScraper, "scrape_financial_statements", statements), \
             patch.object(KAPScraper, "KAP_PAGE_DELAY_S", 0.0), \
             patch("infrastructure.contracts.instrument_identity_map.resolve_member_oid", return_value=None):
            with make_client(db) as client:
                r = client.post("/api/external/v1/fundamental/collect", json={"max_instruments": 2})
                assert r.status_code == 200
                assert r.json()["tickers"] == ["ASELS", "THYAO"]
                _wait(external_analysis._kap_fundamental_collection_state)
                state = client.get("/api/external/v1/fundamental/collection-status").json()

        assert state["status"] == "completed"
        assert state["fetched"] == 2
        assert via_get.await_count == 2
        via_post.assert_not_called()  # member/filter POST is dead

    def test_explicit_tickers_are_capped(self):
        from scrapers.kap_scraper import KAPScraper

        with patch.object(KAPScraper, "scrape_financial_statements", AsyncMock(return_value={"processed": 0})), \
             patch.object(KAPScraper, "KAP_PAGE_DELAY_S", 0.0), \
             patch("infrastructure.contracts.instrument_identity_map.resolve_member_oid", return_value="oid"):
            with make_client(FakeDB()) as client:
                r = client.post(
                    "/api/external/v1/fundamental/collect",
                    json={"tickers": ["thyao", "akbnk", "asels"], "max_instruments": 2},
                )
                _wait(external_analysis._kap_fundamental_collection_state)

        assert r.json()["tickers"] == ["THYAO", "AKBNK"]
        assert external_analysis._kap_fundamental_collection_state["failed"] == 2  # nothing parsed, never faked

    def test_concurrent_run_is_refused(self):
        running = MagicMock()
        running.done.return_value = False
        external_analysis._kap_fundamental_collection_task = running
        r = make_client(FakeDB()).post("/api/external/v1/fundamental/collect", json={})
        assert r.status_code == 409


def test_capabilities_reports_the_run_that_writes_each_kinds_table():
    states = external_analysis._collection_states()
    assert states["fundamental"] is external_analysis._kap_fundamental_collection_state
    assert states["market"] is external_analysis._market_collection_state
    assert states["corporate_actions"] is external_analysis._market_collection_state
