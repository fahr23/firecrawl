"""
Earnings calendar repository — FA-08 §4 "earnings_calendar" kind.

Fully derivable from `kap_fundamentals` today: every FA-02 revision already
carries `period_end`, `published_at` (report_published_at), `available_at`
(report_available_at), and `revision_id`. No new storage or scraper work
needed — this is a contract-shaped read over FA-02's existing rows.
"""
from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from infrastructure.contracts.instrument_identity_map import supports_market
from infrastructure.repositories.external_analysis_repository import _to_iso_utc

logger = logging.getLogger(__name__)

KIND = "earnings_calendar"
PROVIDER_ID = "kap-scraper"


class EarningsCalendarRepository:
    """Fetches/normalises the earnings-report calendar (FA-08) from kap_fundamentals."""

    def __init__(self, db_manager):
        self._db = db_manager

    def get_history(
        self,
        instrument: str,
        market: str,
        limit: int = 100,
        cursor: Optional[str] = None,
        contract_version: str = "1.0",
    ) -> Dict[str, Any]:
        code = self._resolve(instrument, market)
        if code is None:
            return {"instrument": instrument, "market": market, "items": [], "next_cursor": None}

        where = ["UPPER(stock_code) = %s"]
        params: List[Any] = [code]
        if cursor:
            where.append("COALESCE(published_at, effective_at) < %s")
            params.append(cursor)

        fetch = max(1, min(limit, 1000))
        query = f"""
            SELECT period_end, published_at, available_at, effective_at, revision_id, period
            FROM kap_fundamentals
            WHERE {' AND '.join(where)}
            ORDER BY COALESCE(published_at, effective_at) DESC NULLS LAST
            LIMIT %s
        """
        params.append(fetch + 1)
        rows = self._db.query(query, tuple(params))

        next_cursor = None
        if len(rows) > fetch:
            rows = rows[:fetch]
            next_cursor = _to_iso_utc(rows[-1].get("published_at") or rows[-1].get("effective_at"))

        items = [self._history_item(r, contract_version) for r in rows]
        return {"instrument": instrument, "market": market, "items": items, "next_cursor": next_cursor}

    # ── shaping helpers ───────────────────────────────────────────────────────
    def _resolve(self, instrument: str, market: str) -> Optional[str]:
        if not supports_market(market):
            return None
        code = (instrument or "").strip().upper()
        return code or None

    def _payload(self, row: Dict[str, Any]) -> Dict[str, Any]:
        payload: Dict[str, Any] = {"period": row.get("period")}
        if row.get("period_end") is not None:
            payload["period_end"] = _to_iso_utc(row["period_end"])
        payload["report_published_at"] = _to_iso_utc(row.get("published_at"))
        payload["report_available_at"] = _to_iso_utc(row.get("available_at"))
        if row.get("revision_id") is not None:
            payload["revision_id"] = row["revision_id"]
        return payload

    def _history_item(self, row: Dict[str, Any], contract_version: str = "1.0") -> Dict[str, Any]:
        as_of = row.get("published_at") or row.get("effective_at")
        as_of_iso = _to_iso_utc(as_of)
        item = {"as_of": as_of_iso, "payload": self._payload(row)}
        if contract_version != "1.0":
            item.update({
                "published_at": _to_iso_utc(row.get("published_at")),
                "available_at": _to_iso_utc(row.get("available_at")),
                "period_end": _to_iso_utc(row.get("period_end")),
                "fetched_at": _to_iso_utc(row.get("effective_at")),
                "revision_id": row.get("revision_id"),
                "status": "ok",
            })
        return item
