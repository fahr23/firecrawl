"""
Tests for the External Analysis Provider — fundamental kind (Data Contract v1.0 §3).

Drives the fundamental endpoints end-to-end through FastAPI with a mocked database:
  - envelope shape + FundamentalPayload validation (§1, §3)
  - null ratios dropped from the payload (§5)
  - instrument resolves directly to stock_code; market gating (§0)
  - point / history (pagination) / batch endpoints (§6.1–§6.3)
  - honest unavailable + DB-error degradation (§5)
"""
from datetime import datetime, timezone, timedelta

from fastapi import FastAPI
from fastapi.testclient import TestClient

from api.dependencies import get_db_manager
from api.routers import external_analysis
from database.db_manager import DatabaseManager
from domain.entities.external_analysis import FundamentalPayload, ProviderEnvelope
from infrastructure.repositories.fundamental_repository import _RATIO_FIELDS


# ── fake database ─────────────────────────────────────────────────────────────
class FakeDB:
    """Minimal db_manager stand-in. Routes fundamental queries by SQL substring."""

    PoolExhaustedError = DatabaseManager.PoolExhaustedError

    def __init__(self, point_rows=None, history_rows=None, raise_on_query=False):
        self.point_rows = point_rows or []
        self.history_rows = history_rows or []
        self.raise_on_query = raise_on_query

    def query(self, sql, params=None):
        if self.raise_on_query:
            raise RuntimeError("boom")
        if "kap_fundamentals" in sql:
            return self.point_rows if "LIMIT 1" in sql else self.history_rows
        return []


def _row(period="2026-Q1", effective_at=None, **over):
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
        "effective_at": effective_at
        or (datetime.now(timezone.utc) - timedelta(seconds=3600)),
    }
    # populate ratio fields with deterministic values
    for f in _RATIO_FIELDS:
        row[f] = None
    row.update({
        "gross_margin": 0.4,
        "operating_margin": 0.2,
        "net_margin": 0.15,
        "roe": 0.1875,
        "roa": 0.075,
        "debt_to_equity": 0.5,
        "current_ratio": 2.0,
        "revenue": 1000.0,
        "ebitda": 250.0,
        "net_income": 150.0,
        "data_completeness": 0.82,
    })
    row.update(over)
    return row


def make_client(db: FakeDB) -> TestClient:
    app = FastAPI()
    app.include_router(external_analysis.router, prefix="/api/external/v1")
    app.dependency_overrides[get_db_manager] = lambda: db
    return TestClient(app)


# ════════════════════════════════════════════════════════════════════════════
# Point endpoint (§6.1)
# ════════════════════════════════════════════════════════════════════════════
class TestPoint:
    def test_ok_envelope_shape(self):
        client = make_client(FakeDB(point_rows=[_row()]))
        r = client.get("/api/external/v1/fundamental/THYAO?market=bist")
        assert r.status_code == 200
        body = r.json()

        env = ProviderEnvelope(**body)
        assert env.contract_version == "1.0"
        assert env.instrument == "THYAO"
        assert env.market.value == "bist"
        assert env.kind.value == "fundamental"
        assert env.provider == "kap-scraper"
        assert env.status.value == "ok"
        assert env.freshness_seconds >= 3500

        payload = FundamentalPayload(**body["payload"])
        assert payload.period == "2026-Q1"
        assert payload.currency == "TRY"
        assert payload.gross_margin == 0.4
        assert payload.roe == 0.1875
        assert payload.revenue == 1000.0

    def test_null_ratios_dropped(self):
        client = make_client(FakeDB(point_rows=[_row()]))
        payload = client.get("/api/external/v1/fundamental/THYAO?market=bist").json()["payload"]
        # peg_ratio/eps etc. were None in the row and must be absent (not null-valued)
        assert "peg_ratio" not in payload
        assert "eps" not in payload
        assert "gross_margin" in payload

    def test_no_data_is_unavailable(self):
        client = make_client(FakeDB(point_rows=[]))
        body = client.get("/api/external/v1/fundamental/THYAO?market=bist").json()
        assert body["status"] == "unavailable"
        assert body["payload"] is None
        assert body["as_of"] is None
        assert body["kind"] == "fundamental"

    def test_unsupported_market_is_unavailable(self):
        client = make_client(FakeDB(point_rows=[_row()]))
        body = client.get("/api/external/v1/fundamental/AAPL?market=usa").json()
        assert body["status"] == "unavailable"
        assert body["payload"] is None

    def test_db_error_returns_503(self):
        client = make_client(FakeDB(raise_on_query=True))
        r = client.get("/api/external/v1/fundamental/THYAO?market=bist")
        assert r.status_code == 503
        assert r.json()["error_code"] == "UPSTREAM_DB_ERROR"


# ════════════════════════════════════════════════════════════════════════════
# History endpoint (§6.3)
# ════════════════════════════════════════════════════════════════════════════
class TestHistory:
    def test_items_and_no_cursor(self):
        rows = [_row(period=f"2026-Q{i}", effective_at=datetime.now(timezone.utc) - timedelta(days=i))
                for i in range(1, 4)]
        client = make_client(FakeDB(history_rows=rows))
        body = client.get(
            "/api/external/v1/fundamental/THYAO/history?market=bist&limit=10"
        ).json()
        assert body["kind"] == "fundamental"
        assert len(body["items"]) == 3
        assert body["next_cursor"] is None
        assert "as_of" in body["items"][0]
        assert "gross_margin" in body["items"][0]["payload"]

    def test_pagination_sets_cursor(self):
        rows = [_row(period=f"2026-Q{i}", effective_at=datetime.now(timezone.utc) - timedelta(days=i))
                for i in range(1, 4)]
        client = make_client(FakeDB(history_rows=rows))
        body = client.get(
            "/api/external/v1/fundamental/THYAO/history?market=bist&limit=2"
        ).json()
        assert len(body["items"]) == 2
        assert body["next_cursor"] is not None

    def test_unsupported_market_empty(self):
        client = make_client(FakeDB(history_rows=[_row()]))
        body = client.get("/api/external/v1/fundamental/AAPL/history?market=usa").json()
        assert body["items"] == []
        assert body["next_cursor"] is None


# ════════════════════════════════════════════════════════════════════════════
# Batch endpoint (§6.2)
# ════════════════════════════════════════════════════════════════════════════
class TestBatch:
    def test_items_echoed(self):
        client = make_client(FakeDB(point_rows=[_row()]))
        r = client.post(
            "/api/external/v1/fundamental/batch",
            json={"market": "bist", "instruments": ["THYAO", "AKBNK"]},
        )
        assert r.status_code == 200
        body = r.json()
        assert body["contract_version"] == "1.0"
        assert len(body["items"]) == 2
        assert body["items"][0]["instrument"] == "THYAO"
        assert body["items"][1]["instrument"] == "AKBNK"
        assert all(it["kind"] == "fundamental" for it in body["items"])

    def test_empty_instruments_rejected(self):
        client = make_client(FakeDB())
        r = client.post(
            "/api/external/v1/fundamental/batch",
            json={"market": "bist", "instruments": []},
        )
        assert r.status_code == 422
