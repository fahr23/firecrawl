"""
Tests for the market kind across usa/coin (multi-market support), parallel to
test_market_contract.py's bist coverage.

Each market dispatches to its own source table and field map:
  - usa:  yahoo_market_history, full OHLCV
  - coin: coingecko_market_history, close/market_cap/volume only — no
    high/low/open, honestly absent rather than guessed from the close.
"""
from datetime import date

from fastapi import FastAPI
from fastapi.testclient import TestClient

from api.dependencies import get_db_manager
from api.routers import external_analysis
from database.db_manager import DatabaseManager


class FakeDB:
    PoolExhaustedError = DatabaseManager.PoolExhaustedError

    def __init__(self, point_rows=None, history_rows=None, table_hint=None):
        self.point_rows = point_rows or []
        self.history_rows = history_rows or []
        self.table_hint = table_hint

    def query(self, sql, params=None):
        if self.table_hint and self.table_hint in sql:
            return self.point_rows if "LIMIT 1" in sql else self.history_rows
        return []


def _usa_row(trading_date="2026-05-08", **over):
    data = {"trading_date": trading_date, "open": 344.6, "high": 348.1, "low": 341.1, "close": 346.0, "volume": 14000000}
    data.update(over)
    return {"data": data, "market_date": date.fromisoformat(trading_date)}


def _coin_row(trading_date="2026-05-08", **over):
    data = {"trading_date": trading_date, "close": 83000.0, "market_cap": 1.6e12, "volume": 3.2e10}
    data.update(over)
    return {"data": data, "market_date": date.fromisoformat(trading_date)}


def make_client(db: FakeDB) -> TestClient:
    app = FastAPI()
    app.include_router(external_analysis.router, prefix="/api/external/v1")
    app.dependency_overrides[get_db_manager] = lambda: db
    return TestClient(app)


class TestUsaMarket:
    def test_point_envelope_shape(self):
        client = make_client(FakeDB(point_rows=[_usa_row()], table_hint="yahoo_market_history"))
        body = client.get("/api/external/v1/market/AAPL?market=usa").json()

        assert body["status"] == "ok"
        assert body["provider"] == "yahoo-finance-public"
        assert body["payload"]["open"] == 344.6
        assert body["payload"]["close"] == 346.0
        assert body["payload"]["volume"] == 14000000

    def test_no_data_is_unavailable(self):
        client = make_client(FakeDB(point_rows=[], table_hint="yahoo_market_history"))
        body = client.get("/api/external/v1/market/AAPL?market=usa").json()
        assert body["status"] == "unavailable"
        assert body["provider"] == "yahoo-finance-public"

    def test_history(self):
        rows = [_usa_row(trading_date=f"2026-05-0{d}") for d in range(1, 4)]
        client = make_client(FakeDB(history_rows=rows, table_hint="yahoo_market_history"))
        body = client.get("/api/external/v1/market/AAPL/history?market=usa").json()
        assert body["kind"] == "market"
        assert len(body["items"]) == 3


class TestCoinMarket:
    def test_point_envelope_shape(self):
        client = make_client(FakeDB(point_rows=[_coin_row()], table_hint="coingecko_market_history"))
        body = client.get("/api/external/v1/market/bitcoin?market=coin").json()

        assert body["status"] == "ok"
        assert body["provider"] == "coingecko-public"
        assert body["payload"]["close"] == 83000.0
        assert body["payload"]["market_cap"] == 1.6e12

    def test_high_low_open_absent_not_fabricated(self):
        client = make_client(FakeDB(point_rows=[_coin_row()], table_hint="coingecko_market_history"))
        body = client.get(
            "/api/external/v1/market/bitcoin?market=coin&contract_version=1.1"
        ).json()
        assert "high" not in body["payload"]
        assert "low" not in body["payload"]
        assert body["field_status"]["high"] == "unavailable"
        assert body["field_status"]["low"] == "unavailable"

    def test_coin_id_normalized_lowercase(self):
        client = make_client(FakeDB(point_rows=[_coin_row()], table_hint="coingecko_market_history"))
        body = client.get("/api/external/v1/market/BITCOIN?market=coin").json()
        assert body["status"] == "ok"

    def test_no_data_is_unavailable(self):
        client = make_client(FakeDB(point_rows=[], table_hint="coingecko_market_history"))
        body = client.get("/api/external/v1/market/dogecoin?market=coin").json()
        assert body["status"] == "unavailable"


class TestUnknownMarket:
    def test_market_outside_the_contract_enum_is_rejected(self):
        """market is a closed enum (bist/usa/coin) — an unknown value is a 422
        at the FastAPI layer, never reaches the repository."""
        client = make_client(FakeDB())
        r = client.get("/api/external/v1/market/XYZ?market=tokyo")
        assert r.status_code == 422
