"""
Tests for the External Analysis Provider — classification kind (FA-10 §4).

Documents the current honest state: no scraper populates
stock_classification_history / index_membership_history yet, so every
instrument reads as "unclassified" and every index has an empty member list
— never a fabricated sector or roster.
"""
from datetime import date

from fastapi import FastAPI
from fastapi.testclient import TestClient

from api.dependencies import get_db_manager
from api.routers import external_analysis
from database.db_manager import DatabaseManager


class FakeDB:
    PoolExhaustedError = DatabaseManager.PoolExhaustedError

    def __init__(self, classification_rows=None, membership_rows=None):
        self.classification_rows = classification_rows or []
        self.membership_rows = membership_rows or []

    def query(self, sql, params=None):
        if "stock_classification_history" in sql:
            return self.classification_rows
        if "index_membership_history" in sql:
            return self.membership_rows
        return []


def make_client(db: FakeDB) -> TestClient:
    app = FastAPI()
    app.include_router(external_analysis.router, prefix="/api/external/v1")
    app.dependency_overrides[get_db_manager] = lambda: db
    return TestClient(app)


class TestClassificationHistory:
    def test_no_rows_is_unclassified_not_empty(self):
        client = make_client(FakeDB())
        body = client.get(
            "/api/external/v1/classification/THYAO/history?market=bist"
        ).json()
        assert len(body["items"]) == 1
        assert body["items"][0]["payload"]["status"] == "unclassified"

    def test_rows_present_are_returned_with_dates(self):
        rows = [{
            "sector": "Transportation", "industry": "Airlines", "taxonomy": "kap",
            "valid_from": date(2026, 1, 1), "valid_to": None,
        }]
        client = make_client(FakeDB(classification_rows=rows))
        body = client.get(
            "/api/external/v1/classification/THYAO/history?market=bist"
        ).json()
        payload = body["items"][0]["payload"]
        assert payload["sector"] == "Transportation"
        assert payload["valid_to"] is None

    def test_unsupported_market_is_empty(self):
        client = make_client(FakeDB())
        body = client.get(
            "/api/external/v1/classification/AAPL/history?market=usa"
        ).json()
        assert body["items"] == []


class TestIndexMembers:
    def test_no_members_is_empty_list(self):
        client = make_client(FakeDB())
        body = client.get("/api/external/v1/index/XU100/members").json()
        assert body["members"] == []
        assert body["index_code"] == "XU100"

    def test_current_members_listed(self):
        rows = [{"stock_code": "THYAO", "valid_from": date(2026, 1, 1), "valid_to": None}]
        client = make_client(FakeDB(membership_rows=rows))
        body = client.get("/api/external/v1/index/XU100/members").json()
        assert body["members"] == [{"stock_code": "THYAO", "valid_from": "2026-01-01T00:00:00Z"}]
