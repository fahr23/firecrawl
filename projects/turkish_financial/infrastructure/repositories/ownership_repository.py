"""
Ownership repository — FA-09 §4 "ownership" kind (contract 1.1 §3.2).

Reads `isyatirim_ownership_history` (ticker, snapshot_date, foreign_ownership_pct,
free_float_pct) — one row per ticker per day a collection ran. The public İş
Yatırım company card only ever exposes the CURRENT percentage (no upstream
history endpoint), so this history accrues forward from whenever collection
started; there is no backfill. `snapshot_date` is the trading day the snapshot
was taken, so as_of == published_at == available_at for this kind too.
"""
from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from infrastructure.contracts.instrument_identity_map import supports_market
from infrastructure.repositories.external_analysis_repository import (
    _to_iso_utc,
    _freshness_seconds,
)

logger = logging.getLogger(__name__)

KIND = "ownership"
PROVIDER_ID = "isyatirim-public-data"


class OwnershipRepository:
    """Fetches/normalises daily ownership snapshots (FA-09)."""

    def __init__(self, db_manager):
        self._db = db_manager

    # ── reads ──────────────────────────────────────────────────────────────────
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
            where.append("snapshot_date <= %s")
            params.append(as_of)

        query = f"""
            SELECT snapshot_date, foreign_ownership_pct, free_float_pct
            FROM isyatirim_ownership_history
            WHERE {' AND '.join(where)}
            ORDER BY snapshot_date DESC
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
        code = self._resolve(instrument, market)
        if code is None:
            return {"instrument": instrument, "market": market, "items": [], "next_cursor": None}

        where = ["ticker = %s"]
        params: List[Any] = [code]
        if date_from:
            where.append("snapshot_date >= %s")
            params.append(date_from)
        if date_to:
            where.append("snapshot_date <= %s")
            params.append(date_to)
        if cursor:
            where.append("snapshot_date < %s")
            params.append(cursor)

        fetch = max(1, min(limit, 1000))
        query = f"""
            SELECT snapshot_date, foreign_ownership_pct, free_float_pct
            FROM isyatirim_ownership_history
            WHERE {' AND '.join(where)}
            ORDER BY snapshot_date DESC
            LIMIT %s
        """
        params.append(fetch + 1)
        rows = self._db.query(query, tuple(params))

        next_cursor = None
        if len(rows) > fetch:
            rows = rows[:fetch]
            next_cursor = _to_iso_utc(rows[-1].get("snapshot_date"))

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
        payload: Dict[str, Any] = {}
        if row.get("foreign_ownership_pct") is not None:
            payload["foreign_ownership_pct"] = row["foreign_ownership_pct"]
        if row.get("free_float_pct") is not None:
            payload["free_float_pct"] = row["free_float_pct"]
        return payload

    def _field_status(self, row: Dict[str, Any]) -> Dict[str, str]:
        return {
            field: ("reported" if row.get(field) is not None else "unavailable")
            for field in ("foreign_ownership_pct", "free_float_pct")
        }

    def _envelope(
        self,
        instrument: str,
        market: str,
        row: Dict[str, Any],
        contract_version: str = "1.0",
    ) -> Dict[str, Any]:
        snapshot_date = row.get("snapshot_date")
        as_of_iso = _to_iso_utc(snapshot_date)
        envelope = {
            "contract_version": contract_version,
            "instrument": instrument,
            "market": market,
            "kind": KIND,
            "as_of": as_of_iso,
            "provider": PROVIDER_ID,
            "source": "isyatirim-web",
            "freshness_seconds": _freshness_seconds(snapshot_date),
            "status": "ok",
            "payload": self._payload(row),
        }
        if contract_version != "1.0":
            envelope.update({
                "published_at": as_of_iso,
                "available_at": as_of_iso,
                "period_end": as_of_iso,
                "fetched_at": as_of_iso,
                "revision_id": f"isyatirim:{instrument}:{snapshot_date}" if snapshot_date else None,
                "field_status": self._field_status(row),
            })
        return envelope

    def _history_item(self, row: Dict[str, Any], contract_version: str = "1.0") -> Dict[str, Any]:
        as_of_iso = _to_iso_utc(row.get("snapshot_date"))
        item = {"as_of": as_of_iso, "payload": self._payload(row)}
        if contract_version != "1.0":
            item.update({
                "published_at": as_of_iso,
                "available_at": as_of_iso,
                "period_end": as_of_iso,
                "fetched_at": as_of_iso,
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
            "source": "isyatirim-web",
            "freshness_seconds": 0,
            "status": "unavailable",
            "payload": None,
        }
