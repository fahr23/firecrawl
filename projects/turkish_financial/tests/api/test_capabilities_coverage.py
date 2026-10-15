"""
Tests for GET /capabilities' coverage block (FA-16 §3.6).

Each served kind reports instruments_served, earliest/latest as_of, and median
observations per instrument from a real aggregate query over that kind's table;
a query failure degrades to a zero/null coverage entry rather than breaking the
whole /capabilities response.
"""
from datetime import date
from unittest.mock import patch

from fastapi import FastAPI
from fastapi.testclient import TestClient

from api.dependencies import get_db_manager
from api.routers import external_analysis
from database.db_manager import DatabaseManager


class FakeDB:
    PoolExhaustedError = DatabaseManager.PoolExhaustedError

    def __init__(self, rows_by_kind=None, raise_for=None):
        self.rows_by_kind = rows_by_kind or {}
        self.raise_for = raise_for or set()

    def query(self, sql, params=None):
        for kind, table in {
            "fundamental": "kap_fundamentals",
            "market": "isyatirim_market_history",
            "ownership": "isyatirim_ownership_history",
            "sentiment": "kap_disclosure_sentiment",
        }.items():
            if table in sql:
                if kind in self.raise_for:
                    raise RuntimeError(f"boom:{kind}")
                return self.rows_by_kind.get(kind, [])
        return []


def make_client(db: FakeDB) -> TestClient:
    app = FastAPI()
    app.include_router(external_analysis.router, prefix="/api/external/v1")
    app.dependency_overrides[get_db_manager] = lambda: db
    return TestClient(app)


_OFFLINE_FIRECRAWL = {"status": "unavailable", "operations": [], "document_parse": False}


class TestCapabilitiesCoverage:
    def test_coverage_block_present_for_every_kind(self):
        db = FakeDB()
        client = make_client(db)
        with patch.object(external_analysis, "_firecrawl_capabilities_cache", _OFFLINE_FIRECRAWL):
            body = client.get("/api/external/v1/capabilities").json()

        assert set(body["coverage"].keys()) == {
            "fundamental", "market", "ownership", "sentiment",
            "events", "corporate_actions", "classification",
        }
        for entry in body["coverage"].values():
            assert entry["instruments_served"] == 0
            assert entry["earliest_as_of"] is None
            assert entry["median_observations_per_instrument"] is None

    def test_coverage_aggregates_real_rows(self):
        db = FakeDB(rows_by_kind={
            "market": [
                {"instrument": "THYAO", "earliest": date(2026, 1, 2), "latest": date(2026, 5, 8), "observations": 90},
                {"instrument": "AKBNK", "earliest": date(2026, 1, 5), "latest": date(2026, 5, 8), "observations": 88},
            ],
        })
        client = make_client(db)
        with patch.object(external_analysis, "_firecrawl_capabilities_cache", _OFFLINE_FIRECRAWL):
            body = client.get("/api/external/v1/capabilities").json()

        market = body["coverage"]["market"]
        assert market["instruments_served"] == 2
        assert market["earliest_as_of"].startswith("2026-01-02")
        assert market["latest_as_of"].startswith("2026-05-08")
        assert market["median_observations_per_instrument"] == 89.0

    def test_one_kind_query_failure_does_not_break_other_kinds(self):
        db = FakeDB(
            rows_by_kind={"market": [{"instrument": "THYAO", "earliest": date(2026, 1, 1), "latest": date(2026, 1, 2), "observations": 2}]},
            raise_for={"fundamental"},
        )
        client = make_client(db)
        with patch.object(external_analysis, "_firecrawl_capabilities_cache", _OFFLINE_FIRECRAWL):
            r = client.get("/api/external/v1/capabilities")

        assert r.status_code == 200
        body = r.json()
        assert body["coverage"]["fundamental"]["instruments_served"] == 0
        assert body["coverage"]["market"]["instruments_served"] == 1

    def test_last_collection_run_omitted_when_collector_never_ran(self):
        db = FakeDB()
        client = make_client(db)
        with patch.object(external_analysis, "_firecrawl_capabilities_cache", _OFFLINE_FIRECRAWL):
            body = client.get("/api/external/v1/capabilities").json()
        assert "last_collection_run" not in body["coverage"]["fundamental"]
