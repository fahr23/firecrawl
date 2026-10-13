"""
Tests for the External Analysis Provider — macro kind (FA-11 §4).

Documents the current honest-unavailable state: every alias is recognized
(the registry and envelope shape are real) but every history query returns an
empty series, because no row can ever have a non-null release_date yet (no
EVDS series code is verified, and EVDS's basic endpoint has no release-date
field anyway). /macro/series lists the alias catalog with its verification
state so a caller can tell this apart from "unknown alias".
"""
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
        if "tcmb_macro_data" in sql:
            return self.rows
        return []


def make_client(db: FakeDB) -> TestClient:
    app = FastAPI()
    app.include_router(external_analysis.router, prefix="/api/external/v1")
    app.dependency_overrides[get_db_manager] = lambda: db
    return TestClient(app)


class TestSeriesCatalog:
    def test_lists_all_five_aliases_unverified(self):
        client = make_client(FakeDB())
        body = client.get("/api/external/v1/macro/series").json()
        aliases = {item["alias"] for item in body["items"]}
        assert aliases == {"CPI_INDEX", "POLICY_RATE", "USD_TRY", "EUR_TRY", "GOLD_TRY_GRAM"}
        assert all(item["verified"] is False for item in body["items"])


class TestHistory:
    def test_known_alias_is_empty_not_an_error(self):
        client = make_client(FakeDB(rows=[]))
        body = client.get("/api/external/v1/macro/CPI_INDEX/history").json()
        assert body["kind"] == "macro"
        assert body["instrument"] == "CPI_INDEX"
        assert body["items"] == []
        assert body["next_cursor"] is None

    def test_unknown_alias_is_also_empty(self):
        client = make_client(FakeDB())
        body = client.get("/api/external/v1/macro/NOT_REAL/history").json()
        assert body["items"] == []

    def test_lowercase_alias_normalized(self):
        client = make_client(FakeDB(rows=[]))
        body = client.get("/api/external/v1/macro/cpi_index/history").json()
        assert body["instrument"] == "CPI_INDEX"
