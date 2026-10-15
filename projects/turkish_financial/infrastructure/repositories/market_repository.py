"""
Market repository — FA-05 §4 "market" kind (contract 1.1 §3.2), multi-market.

Reads one of three source tables depending on `market`, each already
populated idempotently by its own scraper adapter:

  - bist:  `isyatirim_market_history` (scrapers/isyatirim_market_data.py)
  - usa:   `yahoo_market_history`     (scrapers/yahoo_market_data.py)
  - coin:  `coingecko_market_history` (scrapers/coingecko_market_data.py)

Each market's native row shape differs (BIST has no `open`; coin has no
`high`/`low` at all — CoinGecko's free daily endpoint doesn't serve them), so
payload field names and `field_status` are computed per market rather than
forced into one shared column set. `market_date` IS the trading date for all
three, so `as_of == published_at == available_at == period_end` — the whole
point of a daily market observation is that the market already knew it by
the close of that session.
"""
from __future__ import annotations

import logging
from datetime import date, datetime
from typing import Any, Dict, List, NamedTuple, Optional

from infrastructure.contracts.instrument_identity_map import supports_market
from infrastructure.repositories.external_analysis_repository import (
    _to_iso_utc,
    _freshness_seconds,
)

logger = logging.getLogger(__name__)

KIND = "market"


class _MarketConfig(NamedTuple):
    table: str
    instrument_column: str  # "ticker" (bist/usa) or "coin_id" (coin)
    date_format: str  # strptime format the adapter stores trading_date in
    provider_id: str
    source: str
    field_map: tuple[tuple[str, str], ...]  # (payload_field, source_field)
    always_unavailable: tuple[str, ...]  # fields this market's source never has
    normalize_instrument: Any  # str -> str


_BIST_FIELDS = (
    ("close_try", "close_try"), ("high_try", "high_try"), ("low_try", "low_try"),
    ("vwap_try", "average_price_try"), ("volume_try", "volume_try"),
    ("shares_outstanding", "shares_outstanding"), ("market_cap_try", "market_cap_try"),
    ("free_float_market_cap_try", "free_float_market_cap_try"),
    ("usd_try", "usd_try"), ("close_usd", "close_usd"),
)
_USA_FIELDS = (
    ("open", "open"), ("high", "high"), ("low", "low"),
    ("close", "close"), ("volume", "volume"),
)
_COIN_FIELDS = (
    ("close", "close"), ("market_cap", "market_cap"), ("volume", "volume"),
)

_MARKET_CONFIG: Dict[str, _MarketConfig] = {
    "bist": _MarketConfig(
        table="isyatirim_market_history", instrument_column="ticker",
        date_format="%d-%m-%Y", provider_id="isyatirim-public-data",
        source="isyatirim-web", field_map=_BIST_FIELDS,
        always_unavailable=("open_try",),
        normalize_instrument=lambda s: s.strip().upper(),
    ),
    "usa": _MarketConfig(
        table="yahoo_market_history", instrument_column="ticker",
        date_format="%Y-%m-%d", provider_id="yahoo-finance-public",
        source="yahoo-finance-chart", field_map=_USA_FIELDS,
        always_unavailable=(),
        normalize_instrument=lambda s: s.strip().upper(),
    ),
    "coin": _MarketConfig(
        table="coingecko_market_history", instrument_column="coin_id",
        date_format="%Y-%m-%d", provider_id="coingecko-public",
        source="coingecko-market-chart", field_map=_COIN_FIELDS,
        always_unavailable=("high", "low", "open"),
        normalize_instrument=lambda s: s.strip().lower(),
    ),
}


def _parse_trading_date(raw: Any, date_format: str) -> Optional[date]:
    if isinstance(raw, date):
        return raw
    try:
        return datetime.strptime(str(raw), date_format).date()
    except (TypeError, ValueError):
        return None


class MarketRepository:
    """Fetches/normalises daily market observations across bist/usa/coin (FA-05)."""

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
        config = self._config(market)
        code = self._resolve(instrument, market)
        if config is None or code is None:
            return self._unavailable(instrument, market, contract_version)

        where = [f"{config.instrument_column} = %s"]
        params: List[Any] = [code]
        if as_of:
            where.append("market_date <= %s")
            params.append(as_of)

        query = f"""
            SELECT data, market_date
            FROM {config.table}
            WHERE {' AND '.join(where)}
            ORDER BY market_date DESC
            LIMIT 1
        """
        rows = self._db.query(query, tuple(params))
        if not rows or not isinstance(rows[0].get("data"), dict):
            return self._unavailable(instrument, market, contract_version)
        return self._envelope(instrument, market, config, rows[0], contract_version)

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
        config = self._config(market)
        code = self._resolve(instrument, market)
        if config is None or code is None:
            return {"instrument": instrument, "market": market, "items": [], "next_cursor": None}

        where = [f"{config.instrument_column} = %s"]
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
            FROM {config.table}
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
            self._history_item(config, r, contract_version)
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
    def _config(self, market: str) -> Optional[_MarketConfig]:
        return _MARKET_CONFIG.get((market or "").strip().lower())

    def _resolve(self, instrument: str, market: str) -> Optional[str]:
        if not supports_market(market):
            return None
        config = self._config(market)
        if config is None or not instrument:
            return None
        return config.normalize_instrument(instrument) or None

    def _as_of(self, config: _MarketConfig, row: Dict[str, Any]) -> Optional[date]:
        market_date = row.get("market_date")
        if market_date is not None:
            return market_date if isinstance(market_date, date) else _parse_trading_date(market_date, config.date_format)
        return _parse_trading_date((row.get("data") or {}).get("trading_date"), config.date_format)

    def _payload(
        self, config: _MarketConfig, data: Dict[str, Any], trading_date: Optional[date]
    ) -> Dict[str, Any]:
        # provider-wait-list.md §2/§7 C3: every market payload must carry its
        # own trading_date — the row IS a daily observation, so this is always
        # known whenever the envelope is "ok", never a source-dependent field.
        payload: Dict[str, Any] = {}
        if trading_date is not None:
            payload["trading_date"] = trading_date.isoformat()
        for payload_field, source_field in config.field_map:
            value = data.get(source_field)
            if value is not None:
                # Stored as float8; Postgres renders whole numbers without ".0", so
                # coerce back to float to keep the served type stable.
                if isinstance(value, int) and not isinstance(value, bool):
                    value = float(value)
                payload[payload_field] = value
        return payload

    def _field_status(
        self, config: _MarketConfig, data: Dict[str, Any], trading_date: Optional[date]
    ) -> Dict[str, str]:
        status = {
            "trading_date": "reported" if trading_date is not None else "unavailable",
            **{
                payload_field: ("reported" if data.get(source_field) is not None else "unavailable")
                for payload_field, source_field in config.field_map
            },
        }
        # Fields this market's source never provides at all — honest absence,
        # not a guess (e.g. coin has no OHLC high/low on the free daily tier).
        for field in config.always_unavailable:
            status[field] = "unavailable"
        return status

    def _envelope(
        self,
        instrument: str,
        market: str,
        config: _MarketConfig,
        row: Dict[str, Any],
        contract_version: str = "1.0",
    ) -> Dict[str, Any]:
        trading_date = self._as_of(config, row)
        as_of_iso = _to_iso_utc(trading_date)
        envelope = {
            "contract_version": contract_version,
            "instrument": instrument,
            "market": market,
            "kind": KIND,
            "as_of": as_of_iso,
            "provider": config.provider_id,
            "source": config.source,
            "freshness_seconds": _freshness_seconds(trading_date),
            "status": "ok",
            "payload": self._payload(config, row["data"], trading_date),
        }
        if contract_version != "1.0":
            envelope.update({
                "published_at": as_of_iso,
                "available_at": as_of_iso,
                "period_end": as_of_iso,
                "fetched_at": as_of_iso,
                "revision_id": f"{market}:{instrument}:{trading_date.isoformat()}" if trading_date else None,
                "field_status": self._field_status(config, row["data"], trading_date),
            })
        return envelope

    def _history_item(
        self, config: _MarketConfig, row: Dict[str, Any], contract_version: str = "1.0"
    ) -> Dict[str, Any]:
        trading_date = self._as_of(config, row)
        as_of_iso = _to_iso_utc(trading_date)
        item = {"as_of": as_of_iso, "payload": self._payload(config, row["data"], trading_date)}
        if contract_version != "1.0":
            item.update({
                "published_at": as_of_iso,
                "available_at": as_of_iso,
                "period_end": as_of_iso,
                "fetched_at": as_of_iso,
                "status": "ok",
                "field_status": self._field_status(config, row["data"], trading_date),
            })
        return item

    def _unavailable(
        self, instrument: str, market: str, contract_version: str = "1.0"
    ) -> Dict[str, Any]:
        config = self._config(market)
        return {
            "contract_version": contract_version,
            "instrument": instrument,
            "market": market,
            "kind": KIND,
            "as_of": None,
            "provider": config.provider_id if config else "turkish-financial-api",
            "source": config.source if config else "unknown",
            "freshness_seconds": 0,
            "status": "unavailable",
            "payload": None,
        }
