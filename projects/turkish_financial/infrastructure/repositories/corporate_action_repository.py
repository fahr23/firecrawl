"""
Corporate-action repository — FA-06 §4 "corporate_actions" kind.

Reads/writes `corporate_actions` (detected share-count changes, matched to a
KAP bonus_issue/rights_issue event where possible, with a back-adjustment
`price_factor` computed per `domain.services.corporate_action_pricing`).

The detection job (`detect_and_persist`) ties three already-collected sources
together: `isyatirim_market_history` (SERMAYE / shares_outstanding, FA-05),
`kap_events` (classified disclosures, FA-07), and the pricing formulas. It
never fabricates a factor it cannot compute (§3.4):

  - bonus_issue / split / reverse_split: `price_factor` is exact — it only
    needs the market-data-verified `implied_ratio`, no disclosure parsing.
  - rights_issue / cash_dividend: computing `price_factor` additionally needs
    `subscription_price` / `cash_amount` from the KAP disclosure's own
    structured tables, which this provider does not parse yet (tracked
    separately — see module docstring in `corporate_action_pricing.py`).
    These rows persist with `match_status: "matched"`, a null `price_factor`,
    and `ratio` from the verified share-count change; they are never silently
    dropped, just honestly incomplete.
"""
from __future__ import annotations

import logging
from datetime import datetime
from typing import Any, Dict, List, Optional

from domain.services.corporate_action_detector import (
    detect_share_count_changes,
    match_detected_change,
)
from domain.services.corporate_action_pricing import compute_price_factor
from infrastructure.contracts.instrument_identity_map import supports_market
from infrastructure.repositories.external_analysis_repository import _to_iso_utc

logger = logging.getLogger(__name__)

KIND = "corporate_actions"
PROVIDER_ID = "turkish-financial-api"

# Exact from market data alone; no disclosure-body parsing required.
_EXACT_FROM_MARKET_DATA = frozenset({"bonus_issue", "split", "reverse_split"})


class CorporateActionRepository:
    """Detects, prices, persists, and serves FA-06 corporate actions."""

    def __init__(self, db_manager):
        self._db = db_manager

    # ── detection job ──────────────────────────────────────────────────────────
    def detect_and_persist(self, ticker: str) -> Dict[str, Any]:
        """
        Run FA-06 detection for one ticker over its full stored market history.
        Idempotent (upserted on (ticker, ex_date, event_type)). Returns a
        summary: ``{ticker, detected, matched, priced}``.
        """
        code = ticker.strip().upper()
        market_rows = self._db.query(
            "SELECT data FROM isyatirim_market_history WHERE ticker = %s ORDER BY market_date ASC",
            (code,),
        )
        series = [r["data"] for r in market_rows if isinstance(r.get("data"), dict)]
        # Normalize market history's string trading_date into a comparable form
        # for the detector (it only needs ordering + equality, not real dates).
        changes = detect_share_count_changes(series)
        if not changes:
            return {"ticker": code, "detected": 0, "matched": 0, "priced": 0}

        event_rows = self._db.query(
            "SELECT event_type, published_at, available_at, disclosure_index AS source_disclosure_index "
            "FROM kap_events WHERE stock_code = %s",
            (code,),
        )

        matched_count = 0
        priced_count = 0
        for change in changes:
            matched = match_detected_change(change, event_rows)
            ex_date = self._normalize_date(change.get("ex_date"))
            if ex_date is None:
                continue  # an unparseable trading_date is a data issue, not an action

            price_factor: Optional[float] = None
            event_type = matched.get("event_type", "unmatched")
            if matched["match_status"] == "matched":
                matched_count += 1
                if event_type in _EXACT_FROM_MARKET_DATA:
                    price_factor = compute_price_factor(event_type, ratio=change["implied_ratio"])
                # rights_issue / cash_dividend need subscription_price/cash_amount
                # from the disclosure body, which is not parsed yet — honest null.
                if price_factor is not None:
                    priced_count += 1

            self._db.upsert_corporate_action({
                "ticker": code,
                "ex_date": ex_date,
                "event_type": event_type,
                "ratio": change.get("implied_ratio"),
                "price_factor": price_factor,
                "source_disclosure_index": matched.get("source_disclosure_index"),
                "match_status": matched["match_status"],
            })

        return {"ticker": code, "detected": len(changes), "matched": matched_count, "priced": priced_count}

    def _normalize_date(self, value: Any):
        """isyatirim_market_history stores trading_date as "DD-MM-YYYY"."""
        if value is None:
            return None
        try:
            return datetime.strptime(str(value), "%d-%m-%Y").date()
        except ValueError:
            return None

    # ── reads ──────────────────────────────────────────────────────────────────
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
            where.append("ex_date >= %s")
            params.append(date_from)
        if date_to:
            where.append("ex_date <= %s")
            params.append(date_to)
        if cursor:
            where.append("ex_date < %s")
            params.append(cursor)

        fetch = max(1, min(limit, 1000))
        query = f"""
            SELECT ex_date, event_type, ratio, subscription_price, cash_amount,
                   price_factor, source_disclosure_index, method_version, match_status
            FROM corporate_actions
            WHERE {' AND '.join(where)}
            ORDER BY ex_date DESC
            LIMIT %s
        """
        params.append(fetch + 1)
        rows = self._db.query(query, tuple(params))

        next_cursor = None
        if len(rows) > fetch:
            rows = rows[:fetch]
            next_cursor = _to_iso_utc(rows[-1].get("ex_date"))

        items = [self._history_item(r, contract_version) for r in rows]
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

    def _payload(self, row: Dict[str, Any]) -> Dict[str, Any]:
        payload: Dict[str, Any] = {
            "ex_date": _to_iso_utc(row.get("ex_date")),
            "event_type": row.get("event_type"),
            "method_version": row.get("method_version"),
            "match_status": row.get("match_status"),
        }
        for field in ("ratio", "subscription_price", "cash_amount", "price_factor", "source_disclosure_index"):
            if row.get(field) is not None:
                payload[field] = row[field]
        return payload

    def _history_item(self, row: Dict[str, Any], contract_version: str = "1.0") -> Dict[str, Any]:
        as_of_iso = _to_iso_utc(row.get("ex_date"))
        item = {"as_of": as_of_iso, "payload": self._payload(row)}
        if contract_version != "1.0":
            item.update({
                "published_at": as_of_iso,
                "available_at": as_of_iso,
                "fetched_at": as_of_iso,
                "status": "ok",
            })
        return item
