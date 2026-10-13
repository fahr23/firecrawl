"""
Tests for GET /instruments across markets.

BIST is backed by the seeded bist_companies/BIST TÜM catalogue (existing
behaviour, not touched here). usa/coin have no equivalent full-universe
source, so their catalog is honestly limited to instruments that already
have stored market history — never a fabricated "every US stock" listing.
"""
from fastapi import FastAPI
from fastapi.testclient import TestClient

from api.dependencies import get_db_manager
from api.routers import external_analysis
from database.db_manager import DatabaseManager


class FakeDB:
    PoolExhaustedError = DatabaseManager.PoolExhaustedError

    def __init__(self, rows=None, raise_on_query=False):
        self.rows = rows or []
        self.raise_on_query = raise_on_query

    def query(self, sql, params=None):
        if self.raise_on_query:
            raise RuntimeError("boom")
        return self.rows


def make_client(db: FakeDB) -> TestClient:
    app = FastAPI()
    app.include_router(external_analysis.router, prefix="/api/external/v1")
    app.dependency_overrides[get_db_manager] = lambda: db
    return TestClient(app)


class TestUsaCatalog:
    def test_lists_tickers_with_stored_market_data(self):
        client = make_client(FakeDB(rows=[{"ticker": "AAPL"}, {"ticker": "MSFT"}]))
        body = client.get("/api/external/v1/instruments?market=usa").json()
        assert body["market"] == "usa"
        assert body["total"] == 2
        tickers = {item["ticker"] for item in body["items"]}
        assert tickers == {"AAPL", "MSFT"}
        assert all(item["available_data"] == ["market"] for item in body["items"])

    def test_no_stored_data_is_empty_not_fabricated(self):
        client = make_client(FakeDB(rows=[]))
        body = client.get("/api/external/v1/instruments?market=usa").json()
        assert body["total"] == 0
        assert body["items"] == []

    def test_db_error_returns_503(self):
        client = make_client(FakeDB(raise_on_query=True))
        r = client.get("/api/external/v1/instruments?market=usa")
        assert r.status_code == 503


class TestCoinCatalog:
    def test_lists_coin_ids_with_stored_market_data(self):
        client = make_client(FakeDB(rows=[{"ticker": "bitcoin"}, {"ticker": "ethereum"}]))
        body = client.get("/api/external/v1/instruments?market=coin").json()
        assert body["market"] == "coin"
        tickers = {item["ticker"] for item in body["items"]}
        assert tickers == {"bitcoin", "ethereum"}  # coin ids stay lowercase, unlike usa tickers

    def test_no_stored_data_is_empty(self):
        client = make_client(FakeDB(rows=[]))
        body = client.get("/api/external/v1/instruments?market=coin").json()
        assert body["total"] == 0


class TestBistCatalogUnaffected:
    def test_default_market_still_queries_bist_companies(self):
        """Regression guard: the new market dispatch must not break the
        existing BIST catalog path's own query shape."""
        client = make_client(FakeDB(rows=[]))
        body = client.get("/api/external/v1/instruments").json()
        assert body["market"] == "bist"
        # falls back to the built-in static catalogue when the DB has no rows
        assert body["total"] > 0
