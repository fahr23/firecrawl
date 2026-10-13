"""Thin adapter for CoinGecko's public daily coin market-chart JSON.

No API key: the `/api/v3/coins/{id}/market_chart` endpoint is CoinGecko's free
public tier (rate-limited, not authenticated). Verified live 2026-10-13:
returns real daily price/market-cap/volume for bitcoin/ethereum.

CoinGecko's market_chart endpoint has no OHLC high/low — only a closing price
per day (its `/ohlc` endpoint exists but only covers short ranges and is a
different granularity contract). `high`/`low` are therefore intentionally
absent from every coin row rather than faked from the close.
"""
from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Any

import requests

BASE_URL = "https://api.coingecko.com/api/v3/coins/{coin_id}/market_chart"
# CoinGecko coin ids are lowercase slugs (e.g. "bitcoin", "ethereum") — looser
# than a ticker symbol, so allow lowercase letters, digits, and hyphens.
COIN_ID_RE = re.compile(r"^[a-z0-9\-]{1,64}$")


def _rows_from_series(prices: list, market_caps: list, volumes: list) -> list[dict[str, Any]]:
    """CoinGecko returns three parallel [timestamp_ms, value] arrays — zip them
    into one row per day keyed on timestamp."""
    by_ts: dict[int, dict[str, Any]] = {}
    for ts_ms, value in prices:
        by_ts.setdefault(ts_ms, {})["close"] = value
    for ts_ms, value in market_caps:
        by_ts.setdefault(ts_ms, {})["market_cap"] = value
    for ts_ms, value in volumes:
        by_ts.setdefault(ts_ms, {})["volume"] = value

    rows = []
    for ts_ms in sorted(by_ts):
        trading_date = datetime.fromtimestamp(ts_ms / 1000, tz=timezone.utc).date()
        row = {"trading_date": trading_date.isoformat(), **by_ts[ts_ms]}
        rows.append(row)
    return rows


def fetch_market_history(coin_id: str, days: int = 30, vs_currency: str = "usd") -> dict[str, Any]:
    """Fetch and normalize a bounded daily price/market-cap/volume series for
    a CoinGecko coin id.

    This is observational market data: it does not provide a trading signal
    or recommendation.
    """
    coin = coin_id.strip().lower()
    if not COIN_ID_RE.fullmatch(coin):
        raise ValueError("invalid coin instrument id")
    days = max(1, min(int(days), 3650))

    response = requests.get(
        BASE_URL.format(coin_id=coin),
        params={"vs_currency": vs_currency, "days": days, "interval": "daily"},
        headers={"Accept": "application/json"},
        timeout=15,
    )
    if response.status_code == 404:
        raise LookupError(f"CoinGecko has no coin with id '{coin}'")
    response.raise_for_status()
    document = response.json()

    prices = document.get("prices")
    if not prices:
        raise LookupError(f"CoinGecko returned no price series for '{coin}'")

    series = _rows_from_series(
        prices, document.get("market_caps") or [], document.get("total_volumes") or []
    )
    return {
        "currency": vs_currency.upper(),
        "upstream": "coingecko-public-market-chart",
        "series": series,
    }
