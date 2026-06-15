"""
Fundamental repository — Data Contract v1.0 §3 fetching + persistence layer.

Reads the `kap_fundamentals` table (computed from KAP "Finansal Tablolar") and
normalises rows into the contract's common envelope with `kind = "fundamental"`.
Also owns the upsert writers the scrape pipeline calls to persist raw statements and
the ratios derived from them.

Fundamentals are keyed by `stock_code` (we always know the ticker we fetched), so
instrument resolution is a direct, case-insensitive match — no company_name patterns
needed (unlike the sentiment side). Only the BIST market is carried; other markets
return an honest `unavailable` envelope (§5).
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from infrastructure.contracts.instrument_identity_map import supports_market
from infrastructure.repositories.external_analysis_repository import (
    PROVIDER_ID,
    _to_iso_utc,
    _freshness_seconds,
)

logger = logging.getLogger(__name__)

KIND = "fundamental"

# Numeric payload columns mirrored 1:1 from the contract FundamentalPayload (§3).
_RATIO_FIELDS: tuple[str, ...] = (
    "pe_ratio", "pb_ratio", "ps_ratio", "ev_ebitda", "peg_ratio",
    "eps", "book_value_per_share", "dividend_per_share", "dividend_yield",
    "gross_margin", "operating_margin", "net_margin", "roe", "roa", "roic",
    "debt_to_equity", "net_debt_to_ebitda", "current_ratio", "quick_ratio",
    "interest_coverage",
    "revenue", "ebitda", "net_income", "free_cash_flow",
    "revenue_growth_yoy", "eps_growth_yoy",
    "data_completeness",
)

# Columns selected for every read. Kept in one place so point/history stay in sync.
_SELECT_COLUMNS = (
    "stock_code, company_name, period, fiscal_period, currency, reporting_standard, "
    + ", ".join(_RATIO_FIELDS)
    + ", is_estimated, restated, source_disclosure_index, effective_at"
)


class FundamentalRepository:
    """Fetches/normalises KAP fundamentals and persists computed ratios."""

    def __init__(self, db_manager):
        self._db = db_manager

    # ── reads (contract §6.1 / §6.3) ──────────────────────────────────────────
    def get_point(
        self, instrument: str, market: str, as_of: Optional[str] = None
    ) -> Dict[str, Any]:
        """Latest fundamentals at/<= as_of for the instrument."""
        code = self._resolve(instrument, market)
        if code is None:
            return self._unavailable(instrument, market)

        where = ["UPPER(stock_code) = %s"]
        params: List[Any] = [code]
        if as_of:
            where.append("effective_at <= %s")
            params.append(as_of)

        query = f"""
            SELECT {_SELECT_COLUMNS}
            FROM kap_fundamentals
            WHERE {' AND '.join(where)}
            ORDER BY effective_at DESC NULLS LAST
            LIMIT 1
        """
        rows = self._db.query(query, tuple(params))
        if not rows:
            return self._unavailable(instrument, market)
        return self._envelope(instrument, market, rows[0])

    def get_history(
        self,
        instrument: str,
        market: str,
        date_from: Optional[str] = None,
        date_to: Optional[str] = None,
        limit: int = 100,
        cursor: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Time series of fundamental snapshots with cursor pagination."""
        code = self._resolve(instrument, market)
        if code is None:
            return {"instrument": instrument, "market": market, "items": [], "next_cursor": None}

        where = ["UPPER(stock_code) = %s"]
        params: List[Any] = [code]
        if date_from:
            where.append("effective_at >= %s")
            params.append(date_from)
        if date_to:
            where.append("effective_at <= %s")
            params.append(date_to)
        if cursor:
            where.append("effective_at < %s")
            params.append(cursor)

        fetch = max(1, min(limit, 1000))
        query = f"""
            SELECT {_SELECT_COLUMNS}
            FROM kap_fundamentals
            WHERE {' AND '.join(where)}
            ORDER BY effective_at DESC NULLS LAST
            LIMIT %s
        """
        params.append(fetch + 1)
        rows = self._db.query(query, tuple(params))

        next_cursor = None
        if len(rows) > fetch:
            rows = rows[:fetch]
            next_cursor = _to_iso_utc(rows[-1].get("effective_at"))

        items = [
            {"as_of": _to_iso_utc(r.get("effective_at")), "payload": self._payload(r)}
            for r in rows
        ]
        return {
            "instrument": instrument,
            "market": market,
            "items": items,
            "next_cursor": next_cursor,
        }

    # ── writes (used by the scrape pipeline) ──────────────────────────────────
    def upsert_statement(
        self,
        *,
        stock_code: str,
        period: str,
        facts: Dict[str, Any],
        company_name: Optional[str] = None,
        fiscal_period: Optional[str] = None,
        currency: Optional[str] = None,
        reporting_standard: Optional[str] = None,
        disclosure_index: Optional[str] = None,
    ) -> bool:
        """Persist raw canonical facts for an instrument/period (idempotent)."""
        from psycopg2.extras import Json

        query = """
            INSERT INTO kap_financial_statements
                (stock_code, company_name, period, fiscal_period, currency,
                 reporting_standard, disclosure_index, facts)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (stock_code, period) DO UPDATE SET
                company_name = EXCLUDED.company_name,
                fiscal_period = EXCLUDED.fiscal_period,
                currency = EXCLUDED.currency,
                reporting_standard = EXCLUDED.reporting_standard,
                disclosure_index = EXCLUDED.disclosure_index,
                facts = EXCLUDED.facts,
                scraped_at = CURRENT_TIMESTAMP
        """
        return self._db.execute(
            query,
            (
                stock_code.upper(), company_name, period, fiscal_period, currency,
                reporting_standard, disclosure_index, Json(facts),
            ),
        )

    def upsert_fundamentals(
        self,
        *,
        stock_code: str,
        period: str,
        payload: Dict[str, Any],
        company_name: Optional[str] = None,
        fiscal_period: Optional[str] = None,
        currency: Optional[str] = None,
        reporting_standard: Optional[str] = None,
        source_disclosure_index: Optional[str] = None,
        effective_at: Optional[Any] = None,
    ) -> bool:
        """Persist computed ratios for an instrument/period (idempotent upsert)."""
        columns = [
            "stock_code", "company_name", "period", "fiscal_period", "currency",
            "reporting_standard", "source_disclosure_index", "effective_at",
            "is_estimated", "restated",
            *_RATIO_FIELDS,
        ]
        values: List[Any] = [
            stock_code.upper(), company_name, period, fiscal_period, currency,
            reporting_standard, source_disclosure_index,
            effective_at or datetime.now(timezone.utc),
            bool(payload.get("is_estimated", False)),
            bool(payload.get("restated", False)),
            *[payload.get(f) for f in _RATIO_FIELDS],
        ]
        # Refresh every non-key column on conflict.
        updatable = [c for c in columns if c not in ("stock_code", "period")]
        set_clause = ", ".join(f"{c} = EXCLUDED.{c}" for c in updatable)
        placeholders = ", ".join(["%s"] * len(columns))
        query = (
            f"INSERT INTO kap_fundamentals ({', '.join(columns)}) "
            f"VALUES ({placeholders}) "
            f"ON CONFLICT (stock_code, period) DO UPDATE SET {set_clause}, "
            f"computed_at = CURRENT_TIMESTAMP"
        )
        return self._db.execute(query, tuple(values))

    # ── shaping helpers ───────────────────────────────────────────────────────
    def _resolve(self, instrument: str, market: str) -> Optional[str]:
        """BIST-only; the instrument *is* the stock_code we store under."""
        if not supports_market(market):
            return None
        code = (instrument or "").strip().upper()
        return code or None

    def _payload(self, row: Dict[str, Any]) -> Dict[str, Any]:
        """Normalise a row into a FundamentalPayload dict, dropping null ratios (§5)."""
        payload: Dict[str, Any] = {"period": row.get("period")}
        for meta in ("fiscal_period", "currency", "reporting_standard"):
            if row.get(meta) is not None:
                payload[meta] = row[meta]
        for field in _RATIO_FIELDS:
            value = row.get(field)
            if value is not None:
                payload[field] = round(float(value), 6)
        for flag in ("is_estimated", "restated"):
            if row.get(flag) is not None:
                payload[flag] = bool(row[flag])
        return payload

    def _envelope(self, instrument: str, market: str, row: Dict[str, Any]) -> Dict[str, Any]:
        effective = row.get("effective_at")
        return {
            "contract_version": "1.0",
            "instrument": instrument,
            "market": market,
            "kind": KIND,
            "as_of": _to_iso_utc(effective),
            "provider": PROVIDER_ID,
            "source": "external-db",
            "freshness_seconds": _freshness_seconds(effective),
            "status": "ok",
            "payload": self._payload(row),
        }

    def _unavailable(self, instrument: str, market: str) -> Dict[str, Any]:
        return {
            "contract_version": "1.0",
            "instrument": instrument,
            "market": market,
            "kind": KIND,
            "as_of": None,
            "provider": PROVIDER_ID,
            "source": "external-db",
            "freshness_seconds": 0,
            "status": "unavailable",
            "payload": None,
        }
