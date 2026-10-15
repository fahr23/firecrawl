"""
Tests for the External Analysis Provider — market kind (FA-05 §4).

Drives the market endpoints end-to-end through FastAPI with a mocked database:
  - envelope shape for contract 1.0 and 1.1 (point-in-time fields all equal the
    trading date — the whole point of a daily market observation)
  - field renaming from the stored İş Yatırım JSONB shape to the contract shape
  - open_try is always unavailable (no upstream source for it)
  - point / history (pagination) / batch endpoints
  - honest unavailable for unknown ticker / unsupported market
  - the index kind is an explicit unavailable stub (no verified data source yet)
"""
from datetime import date

from fastapi import FastAPI
from fastapi.testclient import TestClient

from api.dependencies import get_db_manager
from api.routers import external_analysis
from database.db_manager import DatabaseManager


class FakeDB:
    """Minimal db_manager stand-in. Routes market queries by SQL substring."""

    PoolExhaustedError = DatabaseManager.PoolExhaustedError

    def __init__(self, point_rows=None, history_rows=None):
        self.point_rows = point_rows or []
        self.history_rows = history_rows or []

    def query(self, sql, params=None):
        if "isyatirim_market_history" in sql:
            return self.point_rows if "LIMIT 1" in sql else self.history_rows
        return []


def _row(market_date=date(2026, 5, 8), **over):
    data = {
        "trading_date": market_date.strftime("%d-%m-%Y"),
        "close_try": 285.5,
        "average_price_try": 284.2,
        "low_try": 282.0,
        "high_try": 288.0,
        "volume_try": 1_250_000_000.0,
        "usd_try": 40.1,
        "close_usd": 7.12,
        "index_value": 10234.5,
        "market_cap_try": 390_000_000_000.0,
        "market_cap_usd": 9_724_438_902.0,
        "free_float_market_cap_try": 150_000_000_000.0,
        "free_float_market_cap_usd": 3_740_000_000.0,
        "shares_outstanding": 1_365_000_000.0,
    }
    data.update(over)
    return {"data": data, "market_date": market_date}


def make_client(db: FakeDB) -> TestClient:
    app = FastAPI()
    app.include_router(external_analysis.router, prefix="/api/external/v1")
    app.dependency_overrides[get_db_manager] = lambda: db
    return TestClient(app)


class TestPoint:
    def test_ok_envelope_shape_default_is_1_1(self):
        """provider-wait-list.md §7 C1: 1.1 is the server default now, not an
        opt-in — a bare request already carries field_status etc."""
        client = make_client(FakeDB(point_rows=[_row()]))
        body = client.get("/api/external/v1/market/THYAO?market=bist").json()

        assert body["contract_version"] == "1.1"
        assert body["instrument"] == "THYAO"
        assert body["kind"] == "market"
        assert body["status"] == "ok"
        assert body["as_of"] == "2026-05-08T00:00:00Z"
        assert "field_status" in body

    def test_explicit_1_0_still_opts_out_to_the_legacy_shape(self):
        client = make_client(FakeDB(point_rows=[_row()]))
        body = client.get(
            "/api/external/v1/market/THYAO?market=bist&contract_version=1.0"
        ).json()

        assert body["contract_version"] == "1.0"
        assert body["instrument"] == "THYAO"
        assert body["kind"] == "market"
        assert body["status"] == "ok"
        assert body["as_of"] == "2026-05-08T00:00:00Z"
        assert "field_status" not in body

    def test_field_renaming_and_values(self):
        client = make_client(FakeDB(point_rows=[_row()]))
        payload = client.get("/api/external/v1/market/THYAO?market=bist").json()["payload"]

        assert payload["close_try"] == 285.5
        assert payload["vwap_try"] == 284.2  # renamed from average_price_try
        assert payload["high_try"] == 288.0
        assert payload["low_try"] == 282.0
        assert payload["shares_outstanding"] == 1_365_000_000.0
        assert payload["market_cap_try"] == 390_000_000_000.0
        assert payload["free_float_market_cap_try"] == 150_000_000_000.0
        assert payload["usd_try"] == 40.1
        assert payload["close_usd"] == 7.12
        assert "open_try" not in payload  # no upstream source — never fabricated

    def test_payload_carries_trading_date(self):
        """provider-wait-list.md §7 C3: every market payload must carry its
        own trading_date, not just the envelope's as_of."""
        client = make_client(FakeDB(point_rows=[_row(market_date=date(2026, 5, 8))]))
        payload = client.get("/api/external/v1/market/THYAO?market=bist").json()["payload"]
        assert payload["trading_date"] == "2026-05-08"

    def test_open_try_is_unavailable_not_fabricated(self):
        """C3's other half: open_try belongs in the field list, but İş Yatırım
        has no upstream source for it — field_status must say so rather than
        silently omitting the field from both payload and field_status."""
        client = make_client(FakeDB(point_rows=[_row()]))
        body = client.get(
            "/api/external/v1/market/THYAO?market=bist&contract_version=1.1"
        ).json()
        assert "open_try" not in body["payload"]
        assert body["field_status"]["open_try"] == "unavailable"

    def test_contract_1_1_point_in_time_fields_equal_trading_date(self):
        client = make_client(FakeDB(point_rows=[_row()]))
        body = client.get(
            "/api/external/v1/market/THYAO?market=bist&contract_version=1.1"
        ).json()

        assert body["contract_version"] == "1.1"
        assert body["as_of"] == body["published_at"] == body["available_at"] == body["period_end"]
        assert body["revision_id"] == "bist:THYAO:2026-05-08"
        assert body["field_status"]["open_try"] == "unavailable"
        assert body["field_status"]["close_try"] == "reported"

    def test_no_data_is_unavailable(self):
        client = make_client(FakeDB(point_rows=[]))
        body = client.get("/api/external/v1/market/THYAO?market=bist").json()
        assert body["status"] == "unavailable"
        assert body["payload"] is None

    def test_unsupported_market_is_unavailable(self):
        client = make_client(FakeDB(point_rows=[_row()]))
        body = client.get("/api/external/v1/market/AAPL?market=usa").json()
        assert body["status"] == "unavailable"

    def test_db_error_returns_503(self):
        class RaisingDB(FakeDB):
            def query(self, sql, params=None):
                raise RuntimeError("boom")

        client = make_client(RaisingDB())
        r = client.get("/api/external/v1/market/THYAO?market=bist")
        assert r.status_code == 503


class TestHistory:
    def test_items_and_pagination(self):
        rows = [_row(market_date=date(2026, 5, d)) for d in range(1, 4)]
        client = make_client(FakeDB(history_rows=rows))
        body = client.get(
            "/api/external/v1/market/THYAO/history?market=bist&limit=2"
        ).json()
        assert body["kind"] == "market"
        assert len(body["items"]) == 2
        assert body["next_cursor"] is not None

    def test_items_carry_trading_date(self):
        rows = [_row(market_date=date(2026, 5, d)) for d in range(1, 3)]
        client = make_client(FakeDB(history_rows=rows))
        body = client.get(
            "/api/external/v1/market/THYAO/history?market=bist&limit=10"
        ).json()
        dates = {item["payload"]["trading_date"] for item in body["items"]}
        assert dates == {"2026-05-01", "2026-05-02"}


class TestBatch:
    def test_items_echoed(self):
        client = make_client(FakeDB(point_rows=[_row()]))
        r = client.post(
            "/api/external/v1/market/batch",
            json={"market": "bist", "instruments": ["THYAO", "AKBNK"]},
        )
        assert r.status_code == 200
        body = r.json()
        assert len(body["items"]) == 2
        assert all(it["kind"] == "market" for it in body["items"])

    def test_empty_instruments_rejected(self):
        client = make_client(FakeDB())
        r = client.post(
            "/api/external/v1/market/batch",
            json={"market": "bist", "instruments": []},
        )
        assert r.status_code == 422


class TestIndexStub:
    def test_known_code_is_unavailable_not_error(self):
        client = make_client(FakeDB())
        body = client.get("/api/external/v1/index/XU100/history").json()
        assert body["status"] == "unavailable"
        assert body["items"] == []
        assert "data source" in body["detail"]

    def test_unknown_code_is_unavailable_with_distinct_detail(self):
        client = make_client(FakeDB())
        body = client.get("/api/external/v1/index/NOTREAL/history").json()
        assert body["status"] == "unavailable"
        assert "Unsupported index code" in body["detail"]


def test_whole_number_values_are_served_as_floats():
    """market_daily is float8; Postgres renders 395025000000.0 as 395025000000."""
    client = make_client(FakeDB(point_rows=[_row(market_cap_try=395025000000, close_try=348)]))
    payload = client.get("/api/external/v1/market/THYAO?market=bist").json()["payload"]
    assert isinstance(payload["market_cap_try"], float) and payload["market_cap_try"] == 395025000000.0
    assert isinstance(payload["close_try"], float)
