"""
Dividend repository — FA-08 §4 "dividends" kind.

Reads `kap_events` where `event_type = 'cash_dividend'` (FA-07) for the
`ex_date`. `payment_date` and `cash_per_share_gross/net` are NOT available
yet — they require the KAP disclosure's structured tables (the same gap
documented in `corporate_action_pricing.py` for rights-issue/dividend price
factors), not just the disclosure title FA-07 classifies on. Every item is
honestly incomplete rather than guessed: `ex_date` + `source_disclosure_index`
are real, the rest is null with `field_status: "unavailable"`.
"""
from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from infrastructure.contracts.instrument_identity_map import supports_kap_market
from infrastructure.repositories.external_analysis_repository import _to_iso_utc

logger = logging.getLogger(__name__)

KIND = "dividends"
PROVIDER_ID = "kap-scraper"

_UNAVAILABLE_FIELDS = ("payment_date", "cash_per_share_gross", "cash_per_share_net")


class DividendRepository:
    """Fetches/normalises cash-dividend events (FA-08) from kap_events."""

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

        where = ["stock_code = %s", "event_type = 'cash_dividend'"]
        params: List[Any] = [code]
        if cursor:
            where.append("published_at < %s")
            params.append(cursor)

        fetch = max(1, min(limit, 1000))
        query = f"""
            SELECT published_at AS ex_date, disclosure_index AS source_disclosure_index
            FROM kap_events
            WHERE {' AND '.join(where)}
            ORDER BY published_at DESC NULLS LAST
            LIMIT %s
        """
        params.append(fetch + 1)
        rows = self._db.query(query, tuple(params))

        next_cursor = None
        if len(rows) > fetch:
            rows = rows[:fetch]
            next_cursor = _to_iso_utc(rows[-1].get("ex_date"))

        items = [self._history_item(r, contract_version) for r in rows]
        return {"instrument": instrument, "market": market, "items": items, "next_cursor": next_cursor}

    # ── shaping helpers ───────────────────────────────────────────────────────
    def _resolve(self, instrument: str, market: str) -> Optional[str]:
        if not supports_kap_market(market):
            return None
        code = (instrument or "").strip().upper()
        return code or None

    def _payload(self, row: Dict[str, Any]) -> Dict[str, Any]:
        return {
            "ex_date": _to_iso_utc(row.get("ex_date")),
            "source_disclosure_index": row.get("source_disclosure_index"),
        }

    def _field_status(self) -> Dict[str, str]:
        status = {f: "unavailable" for f in _UNAVAILABLE_FIELDS}
        status["ex_date"] = "reported"
        return status

    def _history_item(self, row: Dict[str, Any], contract_version: str = "1.0") -> Dict[str, Any]:
        as_of_iso = _to_iso_utc(row.get("ex_date"))
        item = {"as_of": as_of_iso, "payload": self._payload(row)}
        if contract_version != "1.0":
            item.update({
                "published_at": as_of_iso,
                "available_at": as_of_iso,
                "fetched_at": as_of_iso,
                "status": "partial",
                "field_status": self._field_status(),
            })
        return item
