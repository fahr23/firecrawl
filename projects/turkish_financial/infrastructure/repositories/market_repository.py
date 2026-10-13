"""
Market repository — FA-05 §4 "market" kind (contract 1.1 §3.2).

Reads the existing `isyatirim_market_history` table (ticker, market_date, data
JSONB — already populated by `scrapers/isyatirim_market_data.py` and kept via
`DatabaseManager.upsert_isyatirim_market_history`) and normalises rows into the
common envelope. No new storage: FA-05 is a contract-shaped read over data this
provider already persists idempotently per `(ticker, market_date)`.

`market_date` IS the trading date, so for daily market observations
`as_of == published_at == available_at == period_end` — the whole point of a
trading-session value is that the market already knew it by the close of that
session. Only the BIST market is served; other markets return `unavailable`.
"""
from __future__ import annotations

import logging
from datetime import date, datetime
from typing import Any, Dict, List, Optional

from infrastructure.contracts.instrument_identity_map import supports_market
from infrastructure.repositories.external_analysis_repository import (
    _to_iso_utc,
    _freshness_seconds,
)

logger = logging.getLogger(__name__)

KIND = "market"
PROVIDER_ID = "isyatirim-public-data"

# Payload fields read straight from the stored JSONB row (scrapers/isyatirim_market_data.py
# `_row()`), renamed where the contract (FA-05 / provider-wait-list §2) uses a different
# name. `open_try` has no upstream source and is intentionally absent — never fabricated.
_FIELD_MAP: tuple[tuple[str, str], ...] = (
    ("close_try", "close_try"),
    ("high_try", "high_try"),
    ("low_try", "low_try"),
    ("vwap_try", "average_price_try"),
    ("volume_try", "volume_try"),
    ("shares_outstanding", "shares_outstanding"),
    ("market_cap_try", "market_cap_try"),
    ("free_float_market_cap_try", "free_float_market_cap_try"),
    ("usd_try", "usd_try"),
    ("close_usd", "close_usd"),
)


def _parse_trading_date(raw: Any) -> Optional[date]:
    """The stored row's `trading_date` is the source's own "DD-MM-YYYY" string."""
    if isinstance(raw, date):
        return raw
    try:
        return datetime.strptime(str(raw), "%d-%m-%Y").date()
    except (TypeError, ValueError):
        return None


class MarketRepository:
    """Fetches/normalises İş Yatırım daily market observations (FA-05)."""

    def __init__(self, db_manager):
        self._db = db_manager

    # ── reads (contract §6.1 / §6.3) ──────────────────────────────────────────
    def get_point(
        self,
        instrument: str,
        market: str,
        as_of: Optional[str] = None,
        contract_version: str = "1.0",
    ) -> Dict[str, Any]:
        code = self._resolve(instrument, market)
        if code is None:
            return self._unavailable(instrument, market, contract_version)

        where = ["ticker = %s"]
        params: List[Any] = [code]
        if as_of:
            where.append("market_date <= %s")
            params.append(as_of)

        query = f"""
            SELECT data, market_date
            FROM isyatirim_market_history
            WHERE {' AND '.join(where)}
            ORDER BY market_date DESC
            LIMIT 1
        """
        rows = self._db.query(query, tuple(params))
        if not rows or not isinstance(rows[0].get("data"), dict):
            return self._unavailable(instrument, market, contract_version)
        return self._envelope(instrument, market, rows[0], contract_version)

    def get_history(
        self,
        instrument: str,
        market: str,
        date_from: Optional[str] = None,
        date_to: Optional[str] = None,
        limit: int = 100,
        cursor: Optional[str] = None,
        contract_version: str = "1.0",
    ) -> Dict[str, Any]:
        code = self._resolve(instrument, market)
        if code is None:
            return {"instrument": instrument, "market": market, "items": [], "next_cursor": None}

        where = ["ticker = %s"]
        params: List[Any] = [code]
        if date_from:
            where.append("market_date >= %s")
            params.append(date_from)
        if date_to:
            where.append("market_date <= %s")
            params.append(date_to)
        if cursor:
            where.append("market_date < %s")
            params.append(cursor)

        fetch = max(1, min(limit, 1000))
        query = f"""
            SELECT data, market_date
            FROM isyatirim_market_history
            WHERE {' AND '.join(where)}
            ORDER BY market_date DESC
            LIMIT %s
        """
        params.append(fetch + 1)
        rows = self._db.query(query, tuple(params))

        next_cursor = None
        if len(rows) > fetch:
            rows = rows[:fetch]
            next_cursor = _to_iso_utc(rows[-1].get("market_date"))

        items = [
            self._history_item(r, contract_version)
            for r in rows
            if isinstance(r.get("data"), dict)
        ]
        return {
            "instrument": instrument,
            "market": market,
            "items": items,
            "next_cursor": next_cursor,
        }

    # ── shaping helpers ───────────────────────────────────────────────────────
    def _resolve(self, instrument: str, market: str) -> Optional[str]:
        if not supports_market(market):
            return None
        code = (instrument or "").strip().upper()
        return code or None

    def _as_of(self, row: Dict[str, Any]) -> Optional[date]:
        market_date = row.get("market_date")
        if market_date is not None:
            return market_date if isinstance(market_date, date) else _parse_trading_date(market_date)
        return _parse_trading_date(row.get("data", {}).get("trading_date"))

    def _payload(self, data: Dict[str, Any]) -> Dict[str, Any]:
        payload: Dict[str, Any] = {}
        for payload_field, source_field in _FIELD_MAP:
            value = data.get(source_field)
            if value is not None:
                payload[payload_field] = value
        return payload

    def _field_status(self, data: Dict[str, Any]) -> Dict[str, str]:
        status = {
            payload_field: ("reported" if data.get(source_field) is not None else "unavailable")
            for payload_field, source_field in _FIELD_MAP
        }
        # Never sourced from İş Yatırım's daily row — honest absence, not a guess.
        status["open_try"] = "unavailable"
        return status

    def _envelope(
        self,
        instrument: str,
        market: str,
        row: Dict[str, Any],
        contract_version: str = "1.0",
    ) -> Dict[str, Any]:
        trading_date = self._as_of(row)
        as_of_iso = _to_iso_utc(trading_date)
        envelope = {
            "contract_version": contract_version,
            "instrument": instrument,
            "market": market,
            "kind": KIND,
            "as_of": as_of_iso,
            "provider": PROVIDER_ID,
            "source": "isyatirim-web",
            "freshness_seconds": _freshness_seconds(trading_date),
            "status": "ok",
            "payload": self._payload(row["data"]),
        }
        if contract_version != "1.0":
            envelope.update({
                "published_at": as_of_iso,
                "available_at": as_of_iso,
                "period_end": as_of_iso,
                "fetched_at": as_of_iso,
                "revision_id": f"isyatirim:{instrument}:{trading_date.isoformat()}" if trading_date else None,
                "field_status": self._field_status(row["data"]),
            })
        return envelope

    def _history_item(self, row: Dict[str, Any], contract_version: str = "1.0") -> Dict[str, Any]:
        trading_date = self._as_of(row)
        as_of_iso = _to_iso_utc(trading_date)
        item = {"as_of": as_of_iso, "payload": self._payload(row["data"])}
        if contract_version != "1.0":
            item.update({
                "published_at": as_of_iso,
                "available_at": as_of_iso,
                "period_end": as_of_iso,
                "fetched_at": as_of_iso,
                "status": "ok",
                "field_status": self._field_status(row["data"]),
            })
        return item

    def _unavailable(
        self, instrument: str, market: str, contract_version: str = "1.0"
    ) -> Dict[str, Any]:
        return {
            "contract_version": contract_version,
            "instrument": instrument,
            "market": market,
            "kind": KIND,
            "as_of": None,
            "provider": PROVIDER_ID,
            "source": "isyatirim-web",
            "freshness_seconds": 0,
            "status": "unavailable",
            "payload": None,
        }
