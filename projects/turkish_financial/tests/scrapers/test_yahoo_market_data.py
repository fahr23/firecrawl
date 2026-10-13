from unittest.mock import Mock, patch

import pytest

from scrapers.yahoo_market_data import fetch_market_history


def _chart_document(timestamps, opens, highs, lows, closes, volumes, currency="USD"):
    return {
        "chart": {
            "result": [{
                "meta": {"currency": currency, "fullExchangeName": "NasdaqGS"},
                "timestamp": timestamps,
                "indicators": {
                    "quote": [{
                        "open": opens, "high": highs, "low": lows,
                        "close": closes, "volume": volumes,
                    }]
                },
            }],
            "error": None,
        }
    }


def _response(document, status=200):
    response = Mock()
    response.status_code = status
    response.json.return_value = document
    response.raise_for_status = Mock()
    return response


def test_fetch_market_history_normalizes_ohlcv():
    document = _chart_document(
        timestamps=[1700000000, 1700086400],
        opens=[335.0, 340.0], highs=[338.0, 342.0], lows=[332.0, 338.0],
        closes=[336.0, 341.0], volumes=[1000000, 1200000],
    )
    with patch("scrapers.yahoo_market_data.requests.get", return_value=_response(document)) as get:
        result = fetch_market_history("aapl", days=30)

    assert get.call_args.args[0] == "https://query1.finance.yahoo.com/v8/finance/chart/AAPL"
    assert result["currency"] == "USD"
    assert result["exchange"] == "NasdaqGS"
    assert len(result["series"]) == 2
    assert result["series"][-1]["close"] == 341.0
    assert result["series"][-1]["volume"] == 1200000


def test_rows_with_null_close_are_skipped_not_fabricated():
    document = _chart_document(
        timestamps=[1700000000, 1700086400],
        opens=[335.0, None], highs=[338.0, None], lows=[332.0, None],
        closes=[336.0, None], volumes=[1000000, None],
    )
    with patch("scrapers.yahoo_market_data.requests.get", return_value=_response(document)):
        result = fetch_market_history("aapl", days=30)

    assert len(result["series"]) == 1


def test_rejects_invalid_ticker_without_contacting_upstream():
    with patch("scrapers.yahoo_market_data.requests.get") as get:
        with pytest.raises(ValueError, match="invalid USA instrument"):
            fetch_market_history("AAPL; DROP TABLE")
    get.assert_not_called()


def test_unknown_ticker_raises_lookup_error():
    document = {"chart": {"result": None, "error": None}}
    with patch("scrapers.yahoo_market_data.requests.get", return_value=_response(document)):
        with pytest.raises(LookupError, match="no chart data"):
            fetch_market_history("NOTATICKER")


def test_upstream_error_payload_raises_runtime_error():
    document = {"chart": {"result": None, "error": {"description": "No data found"}}}
    with patch("scrapers.yahoo_market_data.requests.get", return_value=_response(document)):
        with pytest.raises(RuntimeError, match="No data found"):
            fetch_market_history("AAPL")
