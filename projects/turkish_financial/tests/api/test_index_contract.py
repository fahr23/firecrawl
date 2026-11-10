"""FA-05 index kind: XU100 from the END_DEGER value on İş Yatırım daily rows."""
from datetime import date, datetime, timezone

from fastapi import FastAPI
from fastapi.testclient import TestClient

from api.dependencies import get_db_manager
from api.routers import external_analysis
from database.db_manager import DatabaseManager
from infrastructure.repositories.index_repository import IndexRepository


class FakeDB:
    PoolExhaustedError = DatabaseManager.PoolExhaustedError

    def __init__(self, rows=None):
        self.rows = rows or []
        self.sql = []
        self.upserts = []

    def query(self, sql, params=None):
        self.sql.append((sql, params))
        return self.rows

    def upsert_isyatirim_market_history(self, ticker, series):
        self.upserts.append((ticker, series))


def _agg(day, close=11721.72, distinct=1, observations=551):
    return {"market_date": day, "distinct_values": distinct, "close": close, "observations": observations,
            "first_fetched_at": datetime(2026, 10, 17, 4, 15, tzinfo=timezone.utc)}


def make_client(db):
    app = FastAPI()
    app.include_router(external_analysis.router, prefix="/api/external/v1")
    app.dependency_overrides[get_db_manager] = lambda: db
    return TestClient(app)


def test_xu100_serves_one_level_per_trading_date_with_provenance():
    db = FakeDB([_agg(date(2026, 10, 16)), _agg(date(2026, 10, 15), close=12070.17)])
    body = make_client(db).get("/api/external/v1/index/XU100/history?market=bist&limit=2").json()
    assert body["status"] == "ok" and body["kind"] == "index" and body["instrument"] == "XU100"
    assert body["items"][0] == {
        "as_of": "2026-10-16", "available_at": "2026-10-17T04:15:00+00:00", "status": "ok",
        "payload": {"trading_date": "2026-10-16", "close": 11721.72, "observations": 551,
                    "source_field": "END_DEGER"},
    }
    assert "END_DEGER" in body["method"]


def test_dates_whose_rows_disagree_are_dropped_not_averaged():
    data = IndexRepository(FakeDB([_agg(date(2026, 10, 16)), _agg(date(2026, 10, 15), distinct=2)])).get_history("XU100")
    assert [item["as_of"] for item in data["items"]] == ["2026-10-16"]
    assert data["dropped_dates"] == 1


def test_xu100_without_stored_levels_is_unavailable():
    body = make_client(FakeDB([])).get("/api/external/v1/index/XU100/history").json()
    assert body["status"] == "unavailable" and body["items"] == []


def test_date_filters_reach_the_query():
    db = FakeDB([_agg(date(2026, 10, 16))])
    make_client(db).get("/api/external/v1/index/XU100/history?from=2026-01-01&to=2026-10-16&limit=5")
    sql, params = db.sql[-1]
    assert "market_date >= %s" in sql and "market_date <= %s" in sql
    assert params == ("2026-01-01", "2026-10-16", 5)


def test_collect_backfills_from_the_first_member_that_answers(monkeypatch):
    calls = []

    def fake_fetch(ticker, days):
        calls.append((ticker, days))
        if ticker == "THYAO":
            raise RuntimeError("upstream timeout")
        return {"series": [{"trading_date": "16-10-2026", "close_try": 1.0, "index_value": 11721.72},
                           {"trading_date": "15-10-2026", "close_try": 1.0, "index_value": None}]}

    monkeypatch.setattr(external_analysis, "fetch_market_history", fake_fetch)
    db = FakeDB()
    body = make_client(db).post("/api/external/v1/index/collect", json={"days": 400}).json()
    assert calls == [("THYAO", 400), ("GARAN", 400)]
    assert body == {"status": "ok", "code": "XU100", "source_instrument": "GARAN", "sessions": 2,
                    "sessions_with_index": 1}
    assert db.upserts[0][0] == "GARAN"


def test_collect_reports_unavailable_when_no_member_answers(monkeypatch):
    def failing(ticker, days):
        raise RuntimeError("blocked")

    monkeypatch.setattr(external_analysis, "fetch_market_history", failing)
    response = make_client(FakeDB()).post("/api/external/v1/index/collect", json={})
    assert response.status_code == 502 and response.json()["status"] == "unavailable"
