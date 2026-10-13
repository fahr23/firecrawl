"""
Tests for the External Analysis Provider — dividends kind (FA-08 §4).

Derived from FA-07's cash_dividend kap_events rows: ex_date is real,
payment_date/cash_per_share are honestly unavailable (not parsed from the
disclosure body yet).
"""
from datetime import date

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


def make_client(db: FakeDB) -> TestClient:
    app = FastAPI()
    app.include_router(external_analysis.router, prefix="/api/external/v1")
    app.dependency_overrides[get_db_manager] = lambda: db
    return TestClient(app)


class TestHistory:
    def test_ex_date_present_other_fields_null(self):
        rows = [{"ex_date": date(2026, 6, 1), "source_disclosure_index": "999"}]
        client = make_client(FakeDB(rows=rows))
        body = client.get(
            "/api/external/v1/dividends/THYAO/history?market=bist"
        ).json()
        payload = body["items"][0]["payload"]
        assert payload["ex_date"] == "2026-06-01T00:00:00Z"
        assert payload["source_disclosure_index"] == "999"
        assert "cash_per_share_gross" not in payload

    def test_contract_1_1_marks_status_partial_and_unavailable_fields(self):
        rows = [{"ex_date": date(2026, 6, 1), "source_disclosure_index": "999"}]
        client = make_client(FakeDB(rows=rows))
        body = client.get(
            "/api/external/v1/dividends/THYAO/history?market=bist&contract_version=1.1"
        ).json()
        item = body["items"][0]
        assert item["status"] == "partial"
        assert item["field_status"]["ex_date"] == "reported"
        assert item["field_status"]["payment_date"] == "unavailable"
        assert item["field_status"]["cash_per_share_gross"] == "unavailable"

    def test_no_events_is_empty(self):
        client = make_client(FakeDB(rows=[]))
        body = client.get(
            "/api/external/v1/dividends/THYAO/history?market=bist"
        ).json()
        assert body["items"] == []
