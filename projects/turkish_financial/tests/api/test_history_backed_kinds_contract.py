"""
C6: point / batch reads for history-backed kinds, honest unavailable (never 404)
for unsourced kinds, and series scopes (macro=tr, index=bist).
"""
from unittest.mock import patch

from fastapi import FastAPI
from fastapi.testclient import TestClient

from api.dependencies import get_db_manager
from api.routers import external_analysis, history_backed_kinds as hbk
from database.db_manager import DatabaseManager

B = "/api/external/v1"


class FakeDB:
    PoolExhaustedError = DatabaseManager.PoolExhaustedError

    def query(self, *_a, **_k):
        return []


def make_client() -> TestClient:
    app = FastAPI()
    app.include_router(external_analysis.router, prefix=B)
    app.include_router(hbk.router, prefix=B)
    app.dependency_overrides[get_db_manager] = lambda: FakeDB()
    return TestClient(app)


def _item(as_of, **payload):
    return {"as_of": as_of, "payload": payload or {"x": 1}, "published_at": as_of,
            "available_at": as_of, "revision_id": f"rev:{as_of}", "status": "ok"}


class DatedRepo:
    """Accepts date_to, like EventRepository / CorporateActionRepository."""

    def __init__(self, items):
        self.items, self.calls = items, []

    def get_history(self, instrument, market, date_from=None, date_to=None, limit=100, cursor=None, contract_version="1.0"):
        self.calls.append(date_to)
        items = [i for i in self.items if date_to is None or i["as_of"] <= date_to + "T99"]
        return {"instrument": instrument, "market": market, "items": items[:limit], "next_cursor": None}


class PagedRepo:
    """No date filter (dividends/earnings/classification); two pages, newest first."""

    def __init__(self, pages):
        self.pages = pages

    def get_history(self, instrument, market, limit=100, cursor=None, contract_version="1.0"):
        idx = int(cursor or 0)
        nxt = str(idx + 1) if idx + 1 < len(self.pages) else None
        return {"instrument": instrument, "market": market, "items": self.pages[idx], "next_cursor": nxt}


def _with_kind(kind, repo, date_filter):
    spec = hbk._Kind(lambda _db: repo, "kap-scraper", "kap", date_filter)
    return patch.dict(hbk._INSTRUMENT_KINDS, {kind: spec})


class TestInstrumentPoint:
    def test_point_is_newest_item_with_1_1_fields(self):
        repo = DatedRepo([_item("2026-05-08T00:00:00Z", event_type="cash_dividend"), _item("2026-04-01T00:00:00Z")])
        with _with_kind("events", repo, True):
            body = make_client().get(f"{B}/events/THYAO?market=bist").json()
        assert body["status"] == "ok"
        assert body["kind"] == "events"
        assert body["contract_version"] == "1.1"
        assert body["as_of"] == "2026-05-08T00:00:00Z"
        assert body["payload"] == {"event_type": "cash_dividend"}
        assert body["revision_id"] == "rev:2026-05-08T00:00:00Z"

    def test_as_of_is_passed_as_date_filter(self):
        repo = DatedRepo([_item("2026-04-01T00:00:00Z")])
        with _with_kind("corporate_actions", repo, True):
            body = make_client().get(f"{B}/corporate_actions/THYAO?market=bist&as_of=2026-04-15").json()
        assert repo.calls == ["2026-04-15"]
        assert body["as_of"] == "2026-04-01T00:00:00Z"

    def test_as_of_scans_pages_when_repo_cannot_filter_by_date(self):
        repo = PagedRepo([
            [_item("2026-09-01T00:00:00Z"), _item("2026-06-01T00:00:00Z")],
            [_item("2026-03-01T00:00:00Z")],
        ])
        with _with_kind("dividends", repo, False):
            body = make_client().get(f"{B}/dividends/THYAO?market=bist&as_of=2026-04-01").json()
        assert body["as_of"] == "2026-03-01T00:00:00Z"

    def test_no_data_is_200_unavailable_not_404(self):
        with _with_kind("classification", PagedRepo([[]]), False):
            r = make_client().get(f"{B}/classification/THYAO?market=bist")
        assert r.status_code == 200
        assert r.json()["status"] == "unavailable"
        assert r.json()["payload"] is None

    def test_contract_1_0_omits_point_in_time_fields(self):
        with _with_kind("events", DatedRepo([_item("2026-05-08T00:00:00Z")]), True):
            body = make_client().get(f"{B}/events/THYAO?market=bist&contract_version=1.0").json()
        assert body["contract_version"] == "1.0"
        assert "revision_id" not in body and "published_at" not in body

    def test_existing_history_route_still_served(self):
        with patch.object(external_analysis, "_event_repo") as repo:
            repo.return_value.get_history.return_value = {"instrument": "THYAO", "market": "bist", "items": [], "next_cursor": None}
            r = make_client().get(f"{B}/events/THYAO/history?market=bist")
        assert r.status_code == 200
        assert r.json()["kind"] == "events"


class TestInstrumentBatch:
    def test_one_envelope_per_instrument(self):
        with _with_kind("earnings_calendar", PagedRepo([[_item("2026-05-08T00:00:00Z")]]), False):
            body = make_client().post(f"{B}/earnings_calendar/batch",
                                      json={"market": "bist", "instruments": ["THYAO", "AKBNK"]}).json()
        assert [i["instrument"] for i in body["items"]] == ["THYAO", "AKBNK"]
        assert all(i["kind"] == "earnings_calendar" for i in body["items"])

    def test_more_than_100_instruments_rejected(self):
        r = make_client().post(f"{B}/events/batch", json={"market": "bist", "instruments": [f"T{i}" for i in range(101)]})
        assert r.status_code == 422


class TestUnsourcedKinds:
    def test_footnotes_point_history_batch_are_unavailable(self):
        c = make_client()
        point = c.get(f"{B}/footnotes/ASELS?market=bist")
        history = c.get(f"{B}/footnotes/ASELS/history?market=bist")
        batch = c.post(f"{B}/fund_holdings/batch", json={"market": "bist", "instruments": ["ASELS"]})
        assert point.status_code == history.status_code == batch.status_code == 200
        assert point.json()["status"] == "unavailable" and "FA-14" in point.json()["detail"]
        assert history.json()["items"] == [] and history.json()["status"] == "unavailable"
        assert batch.json()["items"][0]["status"] == "unavailable"


class TestSeriesKinds:
    def test_macro_point_accepts_market_tr(self):
        repo = DatedRepo([])
        repo.get_history = lambda *a, **k: {"series": "CPI_INDEX", "items": [_item("2026-09-03T00:00:00Z", value=3000.1)], "next_cursor": None}
        with patch.object(external_analysis, "_macro_repo", return_value=repo):
            body = make_client().get(f"{B}/macro/cpi_index?market=tr").json()
        assert body["status"] == "ok"
        assert body["instrument"] == "CPI_INDEX"
        assert body["market"] == "tr"
        assert body["payload"] == {"value": 3000.1}

    def test_macro_history_accepts_market_tr(self):
        with patch.object(external_analysis, "_macro_repo") as repo:
            repo.return_value.get_history.return_value = {"series": "CPI_INDEX", "items": [], "next_cursor": None}
            r = make_client().get(f"{B}/macro/CPI_INDEX/history?market=tr")
        assert r.status_code == 200

    def test_index_point_and_batch_are_unavailable(self):
        c = make_client()
        point = c.get(f"{B}/index/XU100?market=bist").json()
        batch = c.post(f"{B}/index/batch", json={"market": "bist", "instruments": ["XU100", "NOPE"]}).json()
        assert point["status"] == "unavailable" and "data source" in point["detail"]
        assert "Unsupported index code" in batch["items"][1]["detail"]
