"""
Classification repository — FA-10 §4 "classification" kind + index membership.

Reads `stock_classification_history` and `index_membership_history` (both
dated change-logs — see `database/db_manager.py`'s
`record_stock_classification` / `record_index_membership`). No scraper writes
these yet (the existing `bist_companies.sector` column and
`bist_index_members` snapshot table have no populating writer either), so
every read is an honest `unclassified` / empty membership list today — the
read/write contract shape is real and ready for a classification source to
be wired in later.
"""
from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from infrastructure.contracts.instrument_identity_map import supports_kap_market
from infrastructure.repositories.external_analysis_repository import _to_iso_utc

logger = logging.getLogger(__name__)

KIND = "classification"
PROVIDER_ID = "turkish-financial-api"


class ClassificationRepository:
    """Fetches/normalises dated sector/industry classification (FA-10)."""

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

        where = ["stock_code = %s"]
        params: List[Any] = [code]
        if cursor:
            where.append("valid_from < %s")
            params.append(cursor)

        fetch = max(1, min(limit, 1000))
        query = f"""
            SELECT sector, industry, taxonomy, valid_from, valid_to
            FROM stock_classification_history
            WHERE {' AND '.join(where)}
            ORDER BY valid_from DESC
            LIMIT %s
        """
        params.append(fetch + 1)
        rows = self._db.query(query, tuple(params))

        next_cursor = None
        if len(rows) > fetch:
            rows = rows[:fetch]
            next_cursor = _to_iso_utc(rows[-1].get("valid_from"))

        if not rows:
            return {
                "instrument": instrument, "market": market,
                "items": [{"as_of": None, "payload": {"sector": None, "industry": None, "status": "unclassified"}}],
                "next_cursor": None,
            }

        items = [self._history_item(r, contract_version) for r in rows]
        return {"instrument": instrument, "market": market, "items": items, "next_cursor": next_cursor}

    def get_index_members(self, index_code: str, as_of: Optional[str] = None) -> Dict[str, Any]:
        """FA-10 `GET /index/{code}/members?as_of=` — current or point-in-time
        membership list. Never fabricated: an index with no recorded rows
        returns an empty list, not a guessed roster."""
        idx = index_code.strip().upper()
        if as_of:
            rows = self._db.query(
                """SELECT stock_code, valid_from, valid_to FROM index_membership_history
                   WHERE index_code = %s AND valid_from <= %s
                   AND (valid_to IS NULL OR valid_to > %s)""",
                (idx, as_of, as_of),
            )
        else:
            rows = self._db.query(
                """SELECT stock_code, valid_from, valid_to FROM index_membership_history
                   WHERE index_code = %s AND valid_to IS NULL""",
                (idx,),
            )
        members = [
            {"stock_code": r["stock_code"], "valid_from": _to_iso_utc(r.get("valid_from"))}
            for r in rows
        ]
        return {"index_code": idx, "as_of": as_of, "members": members}

    # ── shaping helpers ───────────────────────────────────────────────────────
    def _resolve(self, instrument: str, market: str) -> Optional[str]:
        if not supports_kap_market(market):
            return None
        code = (instrument or "").strip().upper()
        return code or None

    def _payload(self, row: Dict[str, Any]) -> Dict[str, Any]:
        return {
            "sector": row.get("sector"),
            "industry": row.get("industry"),
            "taxonomy": row.get("taxonomy"),
            "valid_from": _to_iso_utc(row.get("valid_from")),
            "valid_to": _to_iso_utc(row.get("valid_to")),
        }

    def _history_item(self, row: Dict[str, Any], contract_version: str = "1.0") -> Dict[str, Any]:
        as_of_iso = _to_iso_utc(row.get("valid_from"))
        item = {"as_of": as_of_iso, "payload": self._payload(row)}
        if contract_version != "1.0":
            item.update({
                "published_at": as_of_iso,
                "available_at": as_of_iso,
                "fetched_at": as_of_iso,
                "status": "ok",
            })
        return item
