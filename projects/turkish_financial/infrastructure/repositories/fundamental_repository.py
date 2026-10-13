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

# FA-03 raw statement line items, additive to FundamentalPayload (contract 1.1 §3.2).
_STATEMENT_FIELDS: tuple[str, ...] = (
    "cost_of_sales", "gross_profit", "operating_profit", "ebit",
    "depreciation_amortization", "interest_expense", "net_finance_expense",
    "tax_expense", "pretax_profit", "net_income_parent",
    "total_assets", "current_assets", "cash_and_equivalents", "trade_receivables",
    "inventories", "current_liabilities", "trade_payables",
    "short_term_financial_debt", "long_term_financial_debt", "total_liabilities",
    "total_equity", "equity_parent", "minority_interest", "retained_earnings",
    "operating_cash_flow", "capex", "dividends_paid", "interest_paid", "taxes_paid",
    "shares_outstanding",
)

# Columns selected for every read. Kept in one place so point/history stay in sync.
_SELECT_COLUMNS = (
    "stock_code, company_name, period, fiscal_period, currency, reporting_standard, "
    + ", ".join(_RATIO_FIELDS)
    + ", " + ", ".join(_STATEMENT_FIELDS)
    + ", is_estimated, restated, source_disclosure_index, effective_at"
    + ", consolidation, revision_id, published_at, available_at, period_end,"
    " statement_template, flow_basis"
)


class FundamentalRepository:
    """Fetches/normalises KAP fundamentals and persists computed ratios."""

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
        """Latest fundamentals at/<= as_of for the instrument.

        Contract 1.1 §3.5: `as_of` filters on the point-in-time field
        (`available_at`, falling back to `published_at`, then `effective_at`)
        so a caller never sees a revision the market could not yet have known.
        """
        code = self._resolve(instrument, market)
        if code is None:
            return self._unavailable(instrument, market, contract_version)

        where = ["UPPER(stock_code) = %s"]
        params: List[Any] = [code]
        if as_of:
            where.append("COALESCE(available_at, published_at, effective_at) <= %s")
            params.append(as_of)

        query = f"""
            SELECT {_SELECT_COLUMNS}
            FROM kap_fundamentals
            WHERE {' AND '.join(where)}
            ORDER BY COALESCE(available_at, published_at, effective_at) DESC NULLS LAST
            LIMIT 1
        """
        rows = self._db.query(query, tuple(params))
        if not rows:
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
        """Time series of fundamental snapshots with cursor pagination.

        Every KAP period/consolidation revision is a distinct row (FA-02), so the
        series naturally includes every restatement; the newest revision of each
        period sorts first.
        """
        code = self._resolve(instrument, market)
        if code is None:
            return {"instrument": instrument, "market": market, "items": [], "next_cursor": None}

        order_col = "COALESCE(available_at, published_at, effective_at)"
        where = ["UPPER(stock_code) = %s"]
        params: List[Any] = [code]
        if date_from:
            where.append(f"{order_col} >= %s")
            params.append(date_from)
        if date_to:
            where.append(f"{order_col} <= %s")
            params.append(date_to)
        if cursor:
            where.append(f"{order_col} < %s")
            params.append(cursor)

        fetch = max(1, min(limit, 1000))
        query = f"""
            SELECT {_SELECT_COLUMNS}
            FROM kap_fundamentals
            WHERE {' AND '.join(where)}
            ORDER BY {order_col} DESC NULLS LAST
            LIMIT %s
        """
        params.append(fetch + 1)
        rows = self._db.query(query, tuple(params))

        next_cursor = None
        if len(rows) > fetch:
            rows = rows[:fetch]
            next_cursor = _to_iso_utc(rows[-1].get("available_at") or rows[-1].get("published_at") or rows[-1].get("effective_at"))

        items = [self._history_item(r, contract_version) for r in rows]
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
        consolidation: str = "consolidated",
        revision_id: Optional[str] = None,
        published_at: Optional[Any] = None,
        available_at: Optional[Any] = None,
        period_end: Optional[Any] = None,
        statement_template: str = "industrial",
        flow_basis: str = "ytd",
    ) -> bool:
        """Persist raw canonical facts for an instrument/period/revision (idempotent).

        FA-02: a restatement (new `revision_id`) is a NEW row, never an overwrite of
        the first-published one — only re-running the SAME revision is idempotent.
        """
        from psycopg2.extras import Json

        revision_id = revision_id or disclosure_index or "unrevisioned"
        query = """
            INSERT INTO kap_financial_statements
                (stock_code, company_name, period, fiscal_period, currency,
                 reporting_standard, disclosure_index, facts,
                 consolidation, revision_id, published_at, available_at,
                 period_end, statement_template, flow_basis)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (stock_code, period, consolidation, revision_id) DO UPDATE SET
                company_name = EXCLUDED.company_name,
                fiscal_period = EXCLUDED.fiscal_period,
                currency = EXCLUDED.currency,
                reporting_standard = EXCLUDED.reporting_standard,
                disclosure_index = EXCLUDED.disclosure_index,
                facts = EXCLUDED.facts,
                published_at = EXCLUDED.published_at,
                available_at = EXCLUDED.available_at,
                period_end = EXCLUDED.period_end,
                statement_template = EXCLUDED.statement_template,
                flow_basis = EXCLUDED.flow_basis,
                scraped_at = CURRENT_TIMESTAMP
        """
        return self._db.execute(
            query,
            (
                stock_code.upper(), company_name, period, fiscal_period, currency,
                reporting_standard, disclosure_index, Json(facts),
                consolidation, revision_id, published_at, available_at,
                period_end, statement_template, flow_basis,
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
        consolidation: str = "consolidated",
        revision_id: Optional[str] = None,
        published_at: Optional[Any] = None,
        available_at: Optional[Any] = None,
        period_end: Optional[Any] = None,
        statement_template: str = "industrial",
        flow_basis: str = "ytd",
    ) -> bool:
        """Persist computed ratios + statement line items for an instrument/period/
        revision (idempotent upsert).

        FA-02: keyed on (stock_code, period, consolidation, revision_id) — a
        restatement (new revision_id) inserts a new row and leaves the
        first-published revision intact.
        """
        revision_id = revision_id or source_disclosure_index or "unrevisioned"
        columns = [
            "stock_code", "company_name", "period", "fiscal_period", "currency",
            "reporting_standard", "source_disclosure_index", "effective_at",
            "is_estimated", "restated",
            "consolidation", "revision_id", "published_at", "available_at",
            "period_end", "statement_template", "flow_basis",
            *_RATIO_FIELDS,
            *_STATEMENT_FIELDS,
        ]
        values: List[Any] = [
            stock_code.upper(), company_name, period, fiscal_period, currency,
            reporting_standard, source_disclosure_index,
            effective_at or datetime.now(timezone.utc),
            bool(payload.get("is_estimated", False)),
            bool(payload.get("restated", False)),
            consolidation, revision_id, published_at, available_at,
            period_end, statement_template, flow_basis,
            *[payload.get(f) for f in _RATIO_FIELDS],
            *[payload.get(f) for f in _STATEMENT_FIELDS],
        ]
        # Refresh every non-key column on conflict.
        key_columns = {"stock_code", "period", "consolidation", "revision_id"}
        updatable = [c for c in columns if c not in key_columns]
        set_clause = ", ".join(f"{c} = EXCLUDED.{c}" for c in updatable)
        placeholders = ", ".join(["%s"] * len(columns))
        query = (
            f"INSERT INTO kap_fundamentals ({', '.join(columns)}) "
            f"VALUES ({placeholders}) "
            f"ON CONFLICT (stock_code, period, consolidation, revision_id) DO UPDATE SET {set_clause}, "
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
        for meta in ("consolidation", "statement_template", "flow_basis"):
            if row.get(meta) is not None:
                payload[meta] = row[meta]
        for field in (*_RATIO_FIELDS, *_STATEMENT_FIELDS):
            value = row.get(field)
            if value is not None:
                payload[field] = round(float(value), 6)
        for flag in ("is_estimated", "restated"):
            if row.get(flag) is not None:
                payload[flag] = bool(row[flag])
        return payload

    def _field_status(self, row: Dict[str, Any]) -> Dict[str, str]:
        """Contract 1.1 §3.2 — `reported` when present, `unavailable` when null.

        Covers every FundamentalPayload numeric field; this provider never
        derives/estimates fundamental figures, so only those two states occur.
        """
        return {
            field: ("reported" if row.get(field) is not None else "unavailable")
            for field in (*_RATIO_FIELDS, *_STATEMENT_FIELDS)
        }

    def _point_in_time(self, row: Dict[str, Any]) -> Any:
        return row.get("available_at") or row.get("published_at") or row.get("effective_at")

    def _envelope(
        self,
        instrument: str,
        market: str,
        row: Dict[str, Any],
        contract_version: str = "1.0",
    ) -> Dict[str, Any]:
        as_of = self._point_in_time(row)
        envelope = {
            "contract_version": contract_version,
            "instrument": instrument,
            "market": market,
            "kind": KIND,
            "as_of": _to_iso_utc(as_of),
            "provider": PROVIDER_ID,
            "source": "external-db",
            "freshness_seconds": _freshness_seconds(as_of),
            "status": "ok",
            "payload": self._payload(row),
        }
        if contract_version != "1.0":
            envelope.update({
                "published_at": _to_iso_utc(row.get("published_at")),
                "available_at": _to_iso_utc(row.get("available_at")),
                "period_end": _to_iso_utc(row.get("period_end")),
                "fetched_at": _to_iso_utc(row.get("effective_at")),
                "revision_id": row.get("revision_id"),
                "field_status": self._field_status(row),
            })
        return envelope

    def _history_item(self, row: Dict[str, Any], contract_version: str = "1.0") -> Dict[str, Any]:
        as_of = self._point_in_time(row)
        item = {"as_of": _to_iso_utc(as_of), "payload": self._payload(row)}
        if contract_version != "1.0":
            item.update({
                "published_at": _to_iso_utc(row.get("published_at")),
                "available_at": _to_iso_utc(row.get("available_at")),
                "period_end": _to_iso_utc(row.get("period_end")),
                "fetched_at": _to_iso_utc(row.get("effective_at")),
                "revision_id": row.get("revision_id"),
                "status": "ok",
                "field_status": self._field_status(row),
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
            "source": "external-db",
            "freshness_seconds": 0,
            "status": "unavailable",
            "payload": None,
        }
