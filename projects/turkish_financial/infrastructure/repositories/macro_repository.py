"""
Macro repository — FA-11 §4 "macro" kind (contract 1.1 §3.2).

Reads `tcmb_macro_data` by `series_alias` (FA-11). Every row the contract
serves MUST carry a `release_date` — a row without one is ignored outright
(provider-wait-list §2: "rows without it are ignored"). Today no row can ever
satisfy that because:

  1. `domain.services.macro_series_registry` has no EVDS series code verified
     yet for any F23 alias (placeholder `evds_code=None`), so nothing is
     fetched/written under a `series_alias` in the first place.
  2. Even once a code is verified, EVDS's basic series endpoint returns only
     the observation date (`Tarih`), not the statistic's actual release date
     — that needs TÜİK/TCMB's own release calendar, not implemented here.

Both gaps are tracked in `macro_series_registry.py` and this module's own
`_MISSING_RELEASE_DATE_TRACKING` constant. Until they close, `get_history`
honestly returns an empty series for every alias — never a guessed
`release_date`, per §3.4.
"""
from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from domain.services.macro_series_registry import get_spec, supports_alias
from infrastructure.repositories.external_analysis_repository import _to_iso_utc

logger = logging.getLogger(__name__)

KIND = "macro"
PROVIDER_ID = "tcmb-evds"

# See module docstring — release_date is not sourced anywhere yet, so every
# query filters it out even if a row somehow existed without one.
_MISSING_RELEASE_DATE_TRACKING = True


class MacroRepository:
    """Fetches/normalises TCMB EVDS macro observations (FA-11)."""

    def __init__(self, db_manager):
        self._db = db_manager

    def get_history(
        self,
        alias: str,
        date_from: Optional[str] = None,
        date_to: Optional[str] = None,
        limit: int = 100,
        cursor: Optional[str] = None,
        contract_version: str = "1.0",
    ) -> Dict[str, Any]:
        alias = (alias or "").strip().upper()
        if not supports_alias(alias):
            return {"series": alias, "items": [], "next_cursor": None}

        where = ["series_alias = %s", "release_date IS NOT NULL"]
        params: List[Any] = [alias]
        if date_from:
            where.append("release_date >= %s")
            params.append(date_from)
        if date_to:
            where.append("release_date <= %s")
            params.append(date_to)
        if cursor:
            where.append("release_date < %s")
            params.append(cursor)

        fetch = max(1, min(limit, 1000))
        query = f"""
            SELECT reference_period, value, release_date, indicator_code,
                   unit, frequency, publisher, revision_id
            FROM tcmb_macro_data
            WHERE {' AND '.join(where)}
            ORDER BY release_date DESC
            LIMIT %s
        """
        params.append(fetch + 1)
        rows = self._db.query(query, tuple(params))

        next_cursor = None
        if len(rows) > fetch:
            rows = rows[:fetch]
            next_cursor = _to_iso_utc(rows[-1].get("release_date"))

        items = [self._history_item(r, contract_version) for r in rows]
        return {"series": alias, "items": items, "next_cursor": next_cursor}

    def list_series(self) -> List[Dict[str, Any]]:
        """FA-11 `GET /macro/series` — metadata for every supported alias."""
        from domain.services.macro_series_registry import SUPPORTED_ALIASES

        items = []
        for alias in SUPPORTED_ALIASES:
            spec = get_spec(alias)
            items.append({
                "alias": alias,
                "unit": spec.unit,
                "frequency": spec.frequency,
                "publisher": spec.publisher,
                "verified": spec.evds_code is not None,
            })
        return items

    # ── shaping helpers ───────────────────────────────────────────────────────
    def _payload(self, row: Dict[str, Any]) -> Dict[str, Any]:
        payload: Dict[str, Any] = {
            "reference_period": row.get("reference_period"),
            "value": row.get("value"),
            "unit": row.get("unit"),
            "frequency": row.get("frequency"),
            "publisher": row.get("publisher"),
            "source_series_code": row.get("indicator_code"),
        }
        if row.get("revision_id") is not None:
            payload["revision_id"] = row["revision_id"]
        return payload

    def _history_item(self, row: Dict[str, Any], contract_version: str = "1.0") -> Dict[str, Any]:
        release_iso = _to_iso_utc(row.get("release_date"))
        item = {"as_of": release_iso, "payload": self._payload(row)}
        if contract_version != "1.0":
            item.update({
                "published_at": release_iso,
                "available_at": release_iso,
                "fetched_at": release_iso,
                "status": "ok",
            })
        return item
