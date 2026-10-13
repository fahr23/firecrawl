"""
Tests for the External Analysis Provider — ownership kind (FA-09 §4).

Drives the ownership endpoints end-to-end through FastAPI with a mocked database:
  - envelope shape for contract 1.0 and 1.1
  - point-in-time fields all equal the snapshot date (a daily % reading, no lag)
  - honest unavailable for no data / unsupported market
  - point / history (pagination) / batch endpoints
  - the collection trigger starts a background task and reports its status
"""
from datetime import date

from fastapi import FastAPI
from fastapi.testclient import TestClient

from api.dependencies import get_db_manager
from api.routers import external_analysis
from database.db_manager import DatabaseManager


class FakeDB:
    """Minimal db_manager stand-in. Routes ownership queries by SQL substring."""

    PoolExhaustedError = DatabaseManager.PoolExhaustedError

    def __init__(self, point_rows=None, history_rows=None):
        self.point_rows = point_rows or []
        self.history_rows = history_rows or []

    def query(self, sql, params=None):
        if "isyatirim_ownership_history" in sql:
            return self.point_rows if "LIMIT 1" in sql else self.history_rows
        return []


def _row(snapshot_date=date(2026, 5, 8), foreign=0.42, free_float=0.65):
    return {
        "snapshot_date": snapshot_date,
        "foreign_ownership_pct": foreign,
        "free_float_pct": free_float,
    }


def make_client(db: FakeDB) -> TestClient:
    app = FastAPI()
    app.include_router(external_analysis.router, prefix="/api/external/v1")
    app.dependency_overrides[get_db_manager] = lambda: db
    return TestClient(app)


class TestPoint:
    def test_ok_envelope_shape(self):
        client = make_client(FakeDB(point_rows=[_row()]))
        body = client.get("/api/external/v1/ownership/THYAO?market=bist").json()

        assert body["contract_version"] == "1.0"
        assert body["kind"] == "ownership"
        assert body["status"] == "ok"
        assert body["payload"]["foreign_ownership_pct"] == 0.42
        assert body["payload"]["free_float_pct"] == 0.65

    def test_contract_1_1_point_in_time_fields_equal_snapshot_date(self):
        client = make_client(FakeDB(point_rows=[_row()]))
        body = client.get(
            "/api/external/v1/ownership/THYAO?market=bist&contract_version=1.1"
        ).json()

        assert body["as_of"] == body["published_at"] == body["available_at"]
        assert body["field_status"]["foreign_ownership_pct"] == "reported"

    def test_no_data_is_unavailable(self):
        client = make_client(FakeDB(point_rows=[]))
        body = client.get("/api/external/v1/ownership/THYAO?market=bist").json()
        assert body["status"] == "unavailable"
        assert body["payload"] is None

    def test_unsupported_market_is_unavailable(self):
        client = make_client(FakeDB(point_rows=[_row()]))
        body = client.get("/api/external/v1/ownership/AAPL?market=usa").json()
        assert body["status"] == "unavailable"


class TestHistory:
    def test_items_and_pagination(self):
        rows = [_row(snapshot_date=date(2026, 5, d)) for d in range(1, 4)]
        client = make_client(FakeDB(history_rows=rows))
        body = client.get(
            "/api/external/v1/ownership/THYAO/history?market=bist&limit=2"
        ).json()
        assert body["kind"] == "ownership"
        assert len(body["items"]) == 2
        assert body["next_cursor"] is not None


class TestBatch:
    def test_items_echoed(self):
        client = make_client(FakeDB(point_rows=[_row()]))
        r = client.post(
            "/api/external/v1/ownership/batch",
            json={"market": "bist", "instruments": ["THYAO", "AKBNK"]},
        )
        assert r.status_code == 200
        assert len(r.json()["items"]) == 2


class TestCollectionTrigger:
    def test_start_then_status(self):
        client = make_client(FakeDB())
        r = client.post("/api/external/v1/ownership/collect")
        assert r.status_code == 200
        assert r.json()["status"] == "started"

        status = client.get("/api/external/v1/ownership/collection-status").json()
        assert status["contract_version"] == "1.0"
        assert "total" in status
