"""Thin adapter for Yahoo Finance's public daily US-equity chart JSON.

No API key: the `/v8/finance/chart` endpoint is Yahoo's public, unauthenticated
quote-chart data feed (used by finance.yahoo.com itself). Verified live
2026-10-13: returns real OHLCV for NASDAQ/NYSE tickers with no auth header
beyond a browser-like User-Agent.
"""
from __future__ import annotations

import re
from datetime import date, datetime, timezone
from typing import Any

import requests

BASE_URL = "https://query1.finance.yahoo.com/v8/finance/chart/{ticker}"
TICKER_RE = re.compile(r"^[A-Z0-9.\-]{1,12}$")

_RANGE_FOR_DAYS = (
    (7, "7d"), (30, "1mo"), (90, "3mo"), (180, "6mo"),
    (365, "1y"), (730, "2y"), (1825, "5y"),
)


def _range_for_days(days: int) -> str:
    for limit, label in _RANGE_FOR_DAYS:
        if days <= limit:
            return label
    return "10y"


def _row(ts: int, quote: dict[str, list], index: int) -> dict[str, Any] | None:
    """Build one daily row from the chart's parallel timestamp/OHLCV arrays.

    A None entry in any OHLCV array means Yahoo had no trade data for that
    session (e.g. a market holiday slipped into the requested range) — the
    whole row is skipped rather than persisting a partially-null day.
    """
    close = quote.get("close", [None] * (index + 1))[index]
    if close is None:
        return None
    trading_date = datetime.fromtimestamp(ts, tz=timezone.utc).date()
    return {
        "trading_date": trading_date.isoformat(),
        "open": quote.get("open", [None])[index],
        "high": quote.get("high", [None])[index],
        "low": quote.get("low", [None])[index],
        "close": close,
        "volume": quote.get("volume", [None])[index],
    }


def fetch_market_history(instrument: str, days: int = 30) -> dict[str, Any]:
    """Fetch and normalize a bounded daily OHLCV series for a US equity ticker.

    This is observational market data: it does not provide a trading signal
    or recommendation.
    """
    ticker = instrument.strip().upper()
    if not TICKER_RE.fullmatch(ticker):
        raise ValueError("invalid USA instrument")
    days = max(1, min(int(days), 3650))

    response = requests.get(
        BASE_URL.format(ticker=ticker),
        params={"range": _range_for_days(days), "interval": "1d"},
        headers={"User-Agent": "Mozilla/5.0 (TurkishFinancialResearch/1.0)"},
        timeout=15,
    )
    response.raise_for_status()
    document = response.json()

    chart = document.get("chart") or {}
    if chart.get("error"):
        raise RuntimeError(chart["error"].get("description") or "Yahoo Finance returned an error")
    results = chart.get("result")
    if not results:
        raise LookupError(f"Yahoo Finance has no chart data for '{ticker}'")

    result = results[0]
    timestamps = result.get("timestamp") or []
    quote = (result.get("indicators") or {}).get("quote", [{}])[0]
    meta = result.get("meta") or {}

    series = [
        row for i, ts in enumerate(timestamps)
        if (row := _row(ts, quote, i)) is not None
    ]
    series = series[-days:]
    if not series:
        raise LookupError(f"Yahoo Finance returned no usable sessions for '{ticker}'")

    return {
        "currency": meta.get("currency") or "USD",
        "exchange": meta.get("fullExchangeName"),
        "upstream": "yahoo-finance-public-chart",
        "series": series,
    }
