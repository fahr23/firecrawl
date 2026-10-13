"""
Tests for the External Analysis Provider — earnings_calendar kind (FA-08 §4).

Derived entirely from kap_fundamentals' existing FA-02 point-in-time columns —
no new storage.
"""
from datetime import date, datetime, timezone

from fastapi import FastAPI
from fastapi.testclient import TestClient

from api.dependencies import get_db_manager
from api.routers import external_analysis
from database.db_manager import DatabaseManager


class FakeDB:
    PoolExhaustedError = DatabaseManager.PoolExhaustedError

    def __init__(self, rows=None):
        self.rows = rows or []

    def query(self, sql, params=None):
        if "kap_fundamentals" in sql:
            return self.rows
        return []


def _row(**over):
    row = {
        "period": "2026-Q1",
        "period_end": date(2026, 3, 31),
        "published_at": datetime(2026, 5, 8, 15, 12, tzinfo=timezone.utc),
        "available_at": datetime(2026, 5, 11, 7, 0, tzinfo=timezone.utc),
        "effective_at": datetime(2026, 10, 12, 9, 0, tzinfo=timezone.utc),
        "revision_id": "kap:1234567",
    }
    row.update(over)
    return row


def make_client(db: FakeDB) -> TestClient:
    app = FastAPI()
    app.include_router(external_analysis.router, prefix="/api/external/v1")
    app.dependency_overrides[get_db_manager] = lambda: db
    return TestClient(app)


class TestHistory:
    def test_items_carry_both_timestamps_distinctly(self):
        client = make_client(FakeDB(rows=[_row()]))
        body = client.get(
            "/api/external/v1/earnings_calendar/THYAO/history?market=bist"
        ).json()
        payload = body["items"][0]["payload"]
        assert payload["report_published_at"] != payload["report_available_at"]
        assert payload["period_end"] == "2026-03-31T00:00:00Z"

    def test_unsupported_market_is_empty(self):
        client = make_client(FakeDB(rows=[_row()]))
        body = client.get(
            "/api/external/v1/earnings_calendar/AAPL/history?market=usa"
        ).json()
        assert body["items"] == []

    def test_contract_1_1_adds_revision_id(self):
        client = make_client(FakeDB(rows=[_row()]))
        body = client.get(
            "/api/external/v1/earnings_calendar/THYAO/history?market=bist&contract_version=1.1"
        ).json()
        assert body["items"][0]["revision_id"] == "kap:1234567"
