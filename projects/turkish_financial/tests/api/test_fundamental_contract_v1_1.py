"""
Tests for the External Analysis Provider — fundamental kind, Data Contract v1.1
(FA-01 §3.2 additive envelope, FA-03 statement line items).

Drives the fundamental endpoints end-to-end through FastAPI with a mocked database:
  - default / unspecified contract_version stays byte-identical to 1.0 (back-compat)
  - ?contract_version=1.1 adds published_at/available_at/period_end/fetched_at/
    revision_id/field_status without touching any 1.0 field
  - as_of resolves to available_at (falling back to published_at, then effective_at)
    for 1.1, never to fetched_at — point-in-time correctness (§3.2)
  - field_status marks every FundamentalPayload numeric field reported/unavailable
  - an unrecognised contract_version degrades to the compatible 1.0 default
"""
from datetime import datetime, timezone, timedelta

from fastapi import FastAPI
from fastapi.testclient import TestClient

from api.dependencies import get_db_manager
from api.routers import external_analysis
from database.db_manager import DatabaseManager
from infrastructure.repositories.fundamental_repository import _RATIO_FIELDS, _STATEMENT_FIELDS


class FakeDB:
    """Minimal db_manager stand-in. Routes fundamental queries by SQL substring."""

    PoolExhaustedError = DatabaseManager.PoolExhaustedError

    def __init__(self, point_rows=None, history_rows=None):
        self.point_rows = point_rows or []
        self.history_rows = history_rows or []

    def query(self, sql, params=None):
        if "kap_fundamentals" in sql:
            return self.point_rows if "LIMIT 1" in sql else self.history_rows
        return []


def _row(period="2026-Q1", **over):
    now = datetime.now(timezone.utc)
    row = {
        "stock_code": "THYAO",
        "company_name": "Türk Hava Yolları A.O.",
        "period": period,
        "fiscal_period": "interim",
        "currency": "TRY",
        "reporting_standard": "TFRS",
        "is_estimated": False,
        "restated": False,
        "source_disclosure_index": "123456",
        # fetched_at (scrape time) is intentionally much later than published/available —
        # a backfill scraped "today" for a report that came out months ago.
        "effective_at": now,
        "published_at": now - timedelta(days=90),
        "available_at": now - timedelta(days=90) + timedelta(hours=15),
        "period_end": (now - timedelta(days=90)).date(),
        "revision_id": "kap:123456:v1",
        "consolidation": "consolidated",
        "statement_template": "industrial",
        "flow_basis": "ytd",
    }
    for f in (*_RATIO_FIELDS, *_STATEMENT_FIELDS):
        row[f] = None
    row.update({
        "gross_margin": 0.4,
        "revenue": 1000.0,
        "net_income": 150.0,
        "total_assets": 5000.0,
        "trade_receivables": 200.0,
    })
    row.update(over)
    return row


def make_client(db: FakeDB) -> TestClient:
    app = FastAPI()
    app.include_router(external_analysis.router, prefix="/api/external/v1")
    app.dependency_overrides[get_db_manager] = lambda: db
    return TestClient(app)


class TestBackwardCompatibility:
    def test_default_contract_version_is_1_0_and_omits_1_1_fields(self):
        client = make_client(FakeDB(point_rows=[_row()]))
        body = client.get("/api/external/v1/fundamental/THYAO?market=bist").json()

        assert body["contract_version"] == "1.0"
        for field in ("published_at", "available_at", "period_end", "fetched_at", "revision_id", "field_status"):
            assert field not in body

    def test_explicit_1_0_matches_default(self):
        client = make_client(FakeDB(point_rows=[_row()]))
        explicit = client.get(
            "/api/external/v1/fundamental/THYAO?market=bist&contract_version=1.0"
        ).json()
        default = client.get("/api/external/v1/fundamental/THYAO?market=bist").json()
        assert explicit == default

    def test_unrecognised_version_degrades_to_1_0(self):
        client = make_client(FakeDB(point_rows=[_row()]))
        body = client.get(
            "/api/external/v1/fundamental/THYAO?market=bist&contract_version=9.9"
        ).json()
        assert body["contract_version"] == "1.0"
        assert "field_status" not in body


class TestContract1_1Point:
    def test_envelope_carries_additive_fields(self):
        client = make_client(FakeDB(point_rows=[_row()]))
        body = client.get(
            "/api/external/v1/fundamental/THYAO?market=bist&contract_version=1.1"
        ).json()

        assert body["contract_version"] == "1.1"
        assert body["published_at"] is not None
        assert body["available_at"] is not None
        assert body["period_end"] is not None
        assert body["fetched_at"] is not None
        assert body["revision_id"] == "kap:123456:v1"

    def test_as_of_is_available_at_not_fetched_at(self):
        row = _row()
        client = make_client(FakeDB(point_rows=[row]))
        body = client.get(
            "/api/external/v1/fundamental/THYAO?market=bist&contract_version=1.1"
        ).json()

        # as_of must track the point-in-time field, not the scrape/fetch time —
        # the whole point of FA-02/FA-01 is that these two differ for disclosed data.
        assert body["as_of"] == body["available_at"]
        assert body["as_of"] != body["fetched_at"]

    def test_field_status_marks_reported_and_unavailable(self):
        client = make_client(FakeDB(point_rows=[_row()]))
        body = client.get(
            "/api/external/v1/fundamental/THYAO?market=bist&contract_version=1.1"
        ).json()

        field_status = body["field_status"]
        assert field_status["revenue"] == "reported"
        assert field_status["trade_receivables"] == "reported"
        # eps was left None in the fixture row.
        assert field_status["eps"] == "unavailable"

    def test_statement_line_items_present_in_payload(self):
        client = make_client(FakeDB(point_rows=[_row()]))
        body = client.get(
            "/api/external/v1/fundamental/THYAO?market=bist&contract_version=1.1"
        ).json()

        assert body["payload"]["total_assets"] == 5000.0
        assert body["payload"]["trade_receivables"] == 200.0

    def test_unavailable_envelope_keeps_requested_version(self):
        client = make_client(FakeDB(point_rows=[]))
        body = client.get(
            "/api/external/v1/fundamental/THYAO?market=bist&contract_version=1.1"
        ).json()
        assert body["contract_version"] == "1.1"
        assert body["status"] == "unavailable"
        assert body["payload"] is None


class TestContract1_1History:
    def test_history_items_carry_additive_fields(self):
        rows = [_row(period=f"2026-Q{i}") for i in range(1, 3)]
        client = make_client(FakeDB(history_rows=rows))
        body = client.get(
            "/api/external/v1/fundamental/THYAO/history?market=bist&contract_version=1.1&limit=10"
        ).json()

        assert body["contract_version"] == "1.1"
        assert len(body["items"]) == 2
        for item in body["items"]:
            assert "revision_id" in item
            assert "field_status" in item

    def test_history_default_version_omits_additive_fields(self):
        rows = [_row(period="2026-Q1")]
        client = make_client(FakeDB(history_rows=rows))
        body = client.get(
            "/api/external/v1/fundamental/THYAO/history?market=bist&limit=10"
        ).json()

        assert body["contract_version"] == "1.0"
        assert "revision_id" not in body["items"][0]


class TestContract1_1Batch:
    def test_batch_honours_contract_version(self):
        client = make_client(FakeDB(point_rows=[_row()]))
        r = client.post(
            "/api/external/v1/fundamental/batch",
            json={"market": "bist", "instruments": ["THYAO"], "contract_version": "1.1"},
        )
        body = r.json()
        assert body["contract_version"] == "1.1"
        assert body["items"][0]["revision_id"] == "kap:123456:v1"
