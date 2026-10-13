"""
Tests for the External Analysis Provider — events kind (FA-07 §4).

Drives the events history endpoint end-to-end through FastAPI with a mocked
database: envelope shape, payload fields, pagination, honest empty history for
unsupported market / unknown ticker.
"""
from datetime import datetime, timezone

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
        if "kap_events" in sql:
            return self.rows
        return []


def _row(published_at=None, **over):
    row = {
        "event_type": "bonus_issue",
        "mapping_version": "1",
        "title": "Bedelsiz Sermaye Artırımı",
        "disclosure_index": "1234567",
        "published_at": published_at or datetime(2026, 5, 8, 9, 0, tzinfo=timezone.utc),
        "available_at": None,
    }
    row.update(over)
    return row


def make_client(db: FakeDB) -> TestClient:
    app = FastAPI()
    app.include_router(external_analysis.router, prefix="/api/external/v1")
    app.dependency_overrides[get_db_manager] = lambda: db
    return TestClient(app)


class TestHistory:
    def test_items_and_shape(self):
        client = make_client(FakeDB(rows=[_row()]))
        body = client.get(
            "/api/external/v1/events/THYAO/history?market=bist"
        ).json()

        assert body["kind"] == "events"
        assert len(body["items"]) == 1
        item = body["items"][0]
        assert item["payload"]["event_type"] == "bonus_issue"
        assert item["payload"]["mapping_version"] == "1"
        assert item["payload"]["source_disclosure_index"] == "1234567"

    def test_pagination(self):
        rows = [_row(disclosure_index=str(i), published_at=datetime(2026, 5, i, tzinfo=timezone.utc)) for i in range(1, 4)]
        client = make_client(FakeDB(rows=rows))
        body = client.get(
            "/api/external/v1/events/THYAO/history?market=bist&limit=2"
        ).json()
        assert len(body["items"]) == 2
        assert body["next_cursor"] is not None

    def test_unsupported_market_is_empty(self):
        client = make_client(FakeDB(rows=[_row()]))
        body = client.get(
            "/api/external/v1/events/AAPL/history?market=usa"
        ).json()
        assert body["items"] == []
        assert body["next_cursor"] is None

    def test_contract_1_1_adds_published_available_fetched(self):
        client = make_client(FakeDB(rows=[_row()]))
        body = client.get(
            "/api/external/v1/events/THYAO/history?market=bist&contract_version=1.1"
        ).json()
        item = body["items"][0]
        assert "published_at" in item
        assert "fetched_at" in item
