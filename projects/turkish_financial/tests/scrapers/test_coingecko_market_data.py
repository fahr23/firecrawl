from unittest.mock import Mock, patch

import pytest

from scrapers.coingecko_market_data import fetch_market_history


def _response(document, status=200):
    response = Mock()
    response.status_code = status
    response.json.return_value = document
    response.raise_for_status = Mock()
    return response


def test_fetch_market_history_zips_parallel_series():
    document = {
        "prices": [[1700000000000, 50000.0], [1700086400000, 51000.0]],
        "market_caps": [[1700000000000, 1.0e12], [1700086400000, 1.02e12]],
        "total_volumes": [[1700000000000, 2.0e10], [1700086400000, 2.1e10]],
    }
    with patch("scrapers.coingecko_market_data.requests.get", return_value=_response(document)) as get:
        result = fetch_market_history("bitcoin", days=30)

    assert get.call_args.kwargs["params"]["vs_currency"] == "usd"
    assert result["currency"] == "USD"
    assert len(result["series"]) == 2
    assert result["series"][-1]["close"] == 51000.0
    assert result["series"][-1]["market_cap"] == 1.02e12
    assert result["series"][-1]["volume"] == 2.1e10


def test_no_high_low_fields_are_fabricated():
    document = {
        "prices": [[1700000000000, 50000.0]],
        "market_caps": [[1700000000000, 1.0e12]],
        "total_volumes": [[1700000000000, 2.0e10]],
    }
    with patch("scrapers.coingecko_market_data.requests.get", return_value=_response(document)):
        result = fetch_market_history("bitcoin")

    assert "high" not in result["series"][0]
    assert "low" not in result["series"][0]


def test_rejects_invalid_coin_id_without_contacting_upstream():
    with patch("scrapers.coingecko_market_data.requests.get") as get:
        with pytest.raises(ValueError, match="invalid coin instrument id"):
            fetch_market_history("Bitcoin; DROP")
    get.assert_not_called()


def test_unknown_coin_id_raises_lookup_error():
    with patch("scrapers.coingecko_market_data.requests.get", return_value=_response({}, status=404)):
        with pytest.raises(LookupError, match="no coin with id"):
            fetch_market_history("not-a-real-coin")


def test_empty_prices_raises_lookup_error():
    with patch("scrapers.coingecko_market_data.requests.get", return_value=_response({"prices": []})):
        with pytest.raises(LookupError, match="no price series"):
            fetch_market_history("bitcoin")
