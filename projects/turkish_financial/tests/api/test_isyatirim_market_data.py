from unittest.mock import patch

from tests.api.test_external_analysis_contract import FakeDB, make_client


def _payload():
    return {
        "currency": "TRY",
        "upstream": "isyatirim-public-market-history",
        "fields": {"close_try": "Daily closing price in TRY"},
        "latest": {"trading_date": "2026-07-31T00:00:00", "close_try": 314.0},
        "metrics": {"daily_change_percent": 1.2, "trading_days": 30},
        "series": [{"trading_date": "2026-07-31T00:00:00", "close_try": 314.0}],
    }


def test_market_history_route_returns_a_normalized_bist_envelope():
    client = make_client(FakeDB())
    with patch("api.routers.external_analysis.fetch_market_history", return_value=_payload()) as fetch:
        response = client.get("/api/external/v1/isyatirim/thyao/market-history?market=bist&days=30")

    assert response.status_code == 200
    fetch.assert_called_once_with("THYAO", 30)
    body = response.json()
    assert body["status"] == "ok"
    assert body["instrument"] == "THYAO"
    assert body["provider"] == "isyatirim-public-data"
    assert body["payload"]["latest"]["close_try"] == 314.0


def test_market_history_route_rejects_non_bist_requests_without_fetching():
    client = make_client(FakeDB())
    with patch("api.routers.external_analysis.fetch_market_history") as fetch:
        response = client.get("/api/external/v1/isyatirim/AAPL/market-history?market=usa")

    assert response.status_code == 400
    assert response.json()["status"] == "unavailable"
    fetch.assert_not_called()


def test_market_history_route_hides_upstream_error_details():
    client = make_client(FakeDB())
    with patch("api.routers.external_analysis.fetch_market_history", side_effect=RuntimeError("private upstream detail")):
        response = client.get("/api/external/v1/isyatirim/THYAO/market-history?market=bist")

    assert response.status_code == 502
    assert response.json()["detail"] == "İş Yatırım market data is temporarily unavailable."


def test_market_history_route_uses_a_fresh_database_cache_before_contacting_source():
    class CachedDB(FakeDB):
        def get_isyatirim_market_history(self, ticker, days, max_age_seconds):
            assert (ticker, days) == ("THYAO", 1)
            return {"fresh": True, "age_seconds": 12, "series": [_payload()["latest"]]}

    with patch("api.routers.external_analysis.fetch_market_history") as fetch:
        response = make_client(CachedDB()).get(
            "/api/external/v1/isyatirim/THYAO/market-history?market=bist&days=1"
        )

    assert response.status_code == 200
    assert response.json()["freshness_seconds"] == 12
    assert response.json()["payload"]["cache"]["status"] == "database_cache"
    fetch.assert_not_called()


def _fundamentals_payload():
    return {
        "currency": "TRY", "statement_unit": "million TRY",
        "reported_periods": ["2026/3", "2025/12"],
        "one_year_statement_history": [{"report_period": "2026/3", "unit": "TRY", "items": []}],
        "statement_snapshot": {"equity_million_try": 966388.0, "net_income_million_try": 9915.0},
        "current_valuation": {"price_to_earnings": 3.1, "price_to_book": 0.5},
    }


def test_fundamentals_route_returns_source_reported_fundamental_envelope():
    with patch("api.routers.external_analysis.fetch_fundamentals", return_value=_fundamentals_payload()) as fetch:
        response = make_client(FakeDB()).get("/api/external/v1/isyatirim/THYAO/fundamentals?market=bist")

    assert response.status_code == 200
    fetch.assert_called_once_with("THYAO")
    body = response.json()
    assert body["kind"] == "fundamentals"
    assert body["as_of"] == "2026/3"
    assert body["payload"]["cache"]["status"] == "fetched"


def test_fundamentals_route_uses_fresh_database_snapshot_before_source():
    class CachedDB(FakeDB):
        def get_isyatirim_fundamentals(self, ticker, max_age_seconds):
            assert ticker == "THYAO"
            return {"fresh": True, "age_seconds": 30, "payload": _fundamentals_payload()}

    with patch("api.routers.external_analysis.fetch_fundamentals") as fetch:
        response = make_client(CachedDB()).get("/api/external/v1/isyatirim/THYAO/fundamentals?market=bist")

    assert response.status_code == 200
    assert response.json()["freshness_seconds"] == 30
    assert response.json()["payload"]["cache"]["status"] == "database_cache"
    fetch.assert_not_called()


def test_fundamentals_search_reads_only_locally_stored_snapshots():
    class SearchDB(FakeDB):
        def list_isyatirim_fundamentals(self, query_text, limit):
            assert query_text == "THY"
            return [{
                "ticker": "THYAO", "report_period": "2026/3", "age_seconds": 10,
                "data": _fundamentals_payload(),
            }]

    response = make_client(SearchDB()).get("/api/external/v1/isyatirim/fundamentals?query=THY")
    assert response.status_code == 200
    assert response.json()["items"] == [{
        "ticker": "THYAO", "report_period": "2026/3", "age_seconds": 10,
        "price_to_earnings": 3.1, "price_to_book": 0.5, "net_income_million_try": 9915.0,
    }]
