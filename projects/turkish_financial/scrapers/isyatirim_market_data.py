"""Thin adapter for İş Yatırım's public daily BIST market-history JSON."""
from __future__ import annotations

import re
from datetime import date, timedelta
from typing import Any

import requests


BASE_URL = "https://www.isyatirim.com.tr/_layouts/15/IsYatirim.WebSite/Common/Data.aspx/HisseTekil"
TICKER_RE = re.compile(r"^[A-Z0-9.]{1,12}$")


def _number(value: Any) -> float | None:
    return float(value) if isinstance(value, (int, float)) else None


def _row(raw: dict[str, Any]) -> dict[str, Any]:
    """Keep the documented/observed daily fields with stable English names."""
    return {
        "trading_date": raw.get("HGDG_TARIH"),
        "close_try": _number(raw.get("HGDG_KAPANIS")),
        "average_price_try": _number(raw.get("HGDG_AOF")),
        "low_try": _number(raw.get("HGDG_MIN")),
        "high_try": _number(raw.get("HGDG_MAX")),
        "volume_try": _number(raw.get("HGDG_HACIM")),
        "usd_try": _number(raw.get("DD_DEGER")),
        "close_usd": _number(raw.get("DOLAR_BAZLI_FIYAT")),
        "index_value": _number(raw.get("END_DEGER")),
        "market_cap_try": _number(raw.get("PD")),
        "market_cap_usd": _number(raw.get("PD_USD")),
        "free_float_market_cap_try": _number(raw.get("HAO_PD")),
        "free_float_market_cap_usd": _number(raw.get("HAO_PD_USD")),
        "shares_outstanding": _number(raw.get("SERMAYE")),
    }


def build_market_history_payload(series: list[dict[str, Any]], days: int) -> dict[str, Any]:
    """Build the stable response shape from source or database rows."""
    series = [item for item in series if item.get("trading_date") and item.get("close_try") is not None]
    series = series[-days:]
    if not series:
        raise LookupError("No İş Yatırım market data is available for this instrument/window")
    latest = series[-1]
    previous = series[-2] if len(series) > 1 else None
    first = series[0]
    close = latest["close_try"]
    metrics = {
        "daily_change_percent": round(((close / previous["close_try"]) - 1) * 100, 4)
        if previous and previous["close_try"] else None,
        "window_change_percent": round(((close / first["close_try"]) - 1) * 100, 4)
        if first["close_try"] else None,
        "average_volume_try": round(sum(item.get("volume_try") or 0 for item in series) / len(series), 2),
        "trading_days": len(series),
    }
    return {
        "currency": "TRY",
        "upstream": "isyatirim-public-market-history",
        "fields": {
            "close_try": "Daily closing price in TRY",
            "average_price_try": "Daily weighted average price in TRY",
            "volume_try": "Daily traded value in TRY",
            "market_cap_try": "Market value in TRY",
            "free_float_market_cap_try": "Free-float market value in TRY",
            "close_usd": "Dollar-based closing price supplied by İş Yatırım",
            "usd_try": "USD/TRY rate supplied with the daily row",
            "index_value": "Associated index value supplied with the daily row",
        },
        "latest": latest,
        "metrics": metrics,
        "series": series,
    }


def fetch_market_history(instrument: str, days: int = 30) -> dict[str, Any]:
    """Fetch and normalize a bounded public price-history response.

    This is observational market data: it does not provide a trading signal or
    recommendation.  The upstream response is validated before being exposed
    through the finance service.
    """
    ticker = instrument.strip().upper()
    if not TICKER_RE.fullmatch(ticker):
        raise ValueError("invalid BIST instrument")
    days = max(1, min(int(days), 730))
    end = date.today()
    start = end - timedelta(days=days * 2)  # accommodates weekends and holidays
    response = requests.get(
        BASE_URL,
        params={
            "hisse": ticker,
            "startdate": start.strftime("%d-%m-%Y"),
            "enddate": end.strftime("%d-%m-%Y"),
        },
        headers={"Accept": "application/json", "User-Agent": "TurkishFinancialResearch/1.0"},
        timeout=15,
    )
    response.raise_for_status()
    document = response.json()
    if not isinstance(document, dict) or document.get("ok") is not True:
        detail = document.get("errorDescription") if isinstance(document, dict) else None
        raise RuntimeError(detail or "İş Yatırım did not return market data")
    values = document.get("value")
    if not isinstance(values, list):
        raise RuntimeError("İş Yatırım returned an unexpected JSON shape")

    return build_market_history_payload([_row(item) for item in values if isinstance(item, dict)], days)
