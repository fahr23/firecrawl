"""
Tests for the External Analysis Provider — corporate_actions kind (FA-06 §4).

Drives the detect + history endpoints end-to-end through FastAPI with a
mocked database.
"""
from datetime import date

from fastapi import FastAPI
from fastapi.testclient import TestClient

from api.dependencies import get_db_manager
from api.routers import external_analysis
from database.db_manager import DatabaseManager


class FakeDB:
    PoolExhaustedError = DatabaseManager.PoolExhaustedError

    def __init__(self, market_rows=None, event_rows=None, history_rows=None):
        self.market_rows = market_rows or []
        self.event_rows = event_rows or []
        self.history_rows = history_rows or []

    def query(self, sql, params=None):
        if "isyatirim_market_history" in sql:
            return self.market_rows
        if "kap_events" in sql:
            return self.event_rows
        if "corporate_actions" in sql:
            return self.history_rows
        return []

    def upsert_corporate_action(self, action):
        return True


def make_client(db: FakeDB) -> TestClient:
    app = FastAPI()
    app.include_router(external_analysis.router, prefix="/api/external/v1")
    app.dependency_overrides[get_db_manager] = lambda: db
    return TestClient(app)


class TestDetect:
    def test_runs_detection_and_returns_summary(self):
        db = FakeDB(
            market_rows=[
                {"data": {"trading_date": "01-05-2026", "shares_outstanding": 1_000_000, "close_try": 100.0}},
                {"data": {"trading_date": "08-05-2026", "shares_outstanding": 1_200_000, "close_try": 85.0}},
            ],
            event_rows=[{"event_type": "bonus_issue", "published_at": date(2026, 5, 7), "source_disclosure_index": "111"}],
        )
        client = make_client(db)
        r = client.post("/api/external/v1/corporate_actions/THYAO/detect")
        assert r.status_code == 200
        body = r.json()
        assert body["detected"] == 1
        assert body["matched"] == 1
        assert body["priced"] == 1

    def test_unsupported_market_rejected(self):
        client = make_client(FakeDB())
        r = client.post("/api/external/v1/corporate_actions/AAPL/detect?market=usa")
        assert r.status_code == 400


class TestHistory:
    def test_items_and_shape(self):
        rows = [{
            "ex_date": date(2026, 5, 8),
            "event_type": "bonus_issue",
            "ratio": 0.2,
            "subscription_price": None,
            "cash_amount": None,
            "price_factor": 0.8333,
            "source_disclosure_index": "111",
            "method_version": "1",
            "match_status": "matched",
        }]
        client = make_client(FakeDB(history_rows=rows))
        body = client.get(
            "/api/external/v1/corporate_actions/THYAO/history?market=bist"
        ).json()
        assert body["kind"] == "corporate_actions"
        assert len(body["items"]) == 1
        payload = body["items"][0]["payload"]
        assert payload["event_type"] == "bonus_issue"
        assert payload["match_status"] == "matched"
        assert "subscription_price" not in payload  # null fields dropped
