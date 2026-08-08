from unittest.mock import Mock, patch

import pytest

from scrapers.isyatirim_market_data import fetch_market_history


def _upstream_row(day, close, volume=1000):
    return {
        "HGDG_TARIH": day,
        "HGDG_KAPANIS": close,
        "HGDG_AOF": close - 0.5,
        "HGDG_MIN": close - 2,
        "HGDG_MAX": close + 2,
        "HGDG_HACIM": volume,
        "DD_DEGER": 40.2,
        "DOLAR_BAZLI_FIYAT": close / 40.2,
        "END_DEGER": 10000,
        "PD": 5000000,
        "PD_USD": 124378,
        "HAO_PD": 2500000,
        "HAO_PD_USD": 62189,
        "SERMAYE": 100000,
    }


def _response(document):
    response = Mock()
    response.json.return_value = document
    return response


def test_fetch_market_history_normalizes_public_daily_json_and_calculates_metrics():
    document = {
        "ok": True,
        "value": [
            _upstream_row("2026-07-30T00:00:00", 100, 800),
            _upstream_row("2026-07-31T00:00:00", 110, 1200),
        ],
    }
    with patch("scrapers.isyatirim_market_data.requests.get", return_value=_response(document)) as get:
        result = fetch_market_history("thyao", days=30)

    assert get.call_args.kwargs["params"]["hisse"] == "THYAO"
    assert result["currency"] == "TRY"
    assert result["latest"]["close_try"] == 110.0
    assert result["latest"]["market_cap_try"] == 5000000.0
    assert result["metrics"] == {
        "daily_change_percent": 10.0,
        "window_change_percent": 10.0,
        "average_volume_try": 1000.0,
        "trading_days": 2,
    }


def test_fetch_market_history_rejects_invalid_ticker_without_contacting_upstream():
    with patch("scrapers.isyatirim_market_data.requests.get") as get:
        with pytest.raises(ValueError, match="invalid BIST instrument"):
            fetch_market_history("THYAO;DROP")
    get.assert_not_called()


def test_fetch_market_history_fails_on_upstream_error_document():
    with patch(
        "scrapers.isyatirim_market_data.requests.get",
        return_value=_response({"ok": False, "errorDescription": "not found"}),
    ):
        with pytest.raises(RuntimeError, match="not found"):
            fetch_market_history("THYAO")
