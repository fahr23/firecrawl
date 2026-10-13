"""
Event repository — FA-07 §4 "events" kind (contract 1.1 §3.2).

Reads `kap_events` (populated by `domain.services.kap_event_classifier` as
`scrapers.kap_scraper.scrape_and_save_disclosures` saves each disclosure) and
normalises rows into the common envelope. `published_at` is the disclosure's
own publish timestamp; `available_at` is left null until session-calendar
logic assigns it (not derivable from the disclosure alone — §3.2).
"""
from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from infrastructure.contracts.instrument_identity_map import supports_kap_market
from infrastructure.repositories.external_analysis_repository import (
    _to_iso_utc,
    _freshness_seconds,
)

logger = logging.getLogger(__name__)

KIND = "events"
PROVIDER_ID = "kap-scraper"


class EventRepository:
    """Fetches/normalises classified KAP events (FA-07)."""

    def __init__(self, db_manager):
        self._db = db_manager

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

        where = ["stock_code = %s"]
        params: List[Any] = [code]
        if date_from:
            where.append("published_at >= %s")
            params.append(date_from)
        if date_to:
            where.append("published_at <= %s")
            params.append(date_to)
        if cursor:
            where.append("published_at < %s")
            params.append(cursor)

        fetch = max(1, min(limit, 1000))
        query = f"""
            SELECT event_type, mapping_version, title, published_at, available_at,
                   disclosure_index
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
            next_cursor = _to_iso_utc(rows[-1].get("published_at"))

        items = [self._history_item(r, contract_version) for r in rows]
        return {
            "instrument": instrument,
            "market": market,
            "items": items,
            "next_cursor": next_cursor,
        }

    # ── shaping helpers ───────────────────────────────────────────────────────
    def _resolve(self, instrument: str, market: str) -> Optional[str]:
        if not supports_kap_market(market):
            return None
        code = (instrument or "").strip().upper()
        return code or None

    def _payload(self, row: Dict[str, Any]) -> Dict[str, Any]:
        return {
            "event_type": row.get("event_type"),
            "mapping_version": row.get("mapping_version"),
            "source_disclosure_index": row.get("disclosure_index"),
            "title": row.get("title"),
        }

    def _history_item(self, row: Dict[str, Any], contract_version: str = "1.0") -> Dict[str, Any]:
        published_at = row.get("published_at")
        as_of_iso = _to_iso_utc(published_at)
        item = {"as_of": as_of_iso, "payload": self._payload(row)}
        if contract_version != "1.0":
            item.update({
                "published_at": as_of_iso,
                "available_at": _to_iso_utc(row.get("available_at")),
                "fetched_at": as_of_iso,
                "status": "ok",
            })
        return item
