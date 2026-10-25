"""
Index repository — FA-05 "index" kind, BIST 100 (XU100) only.

Source: İş Yatırım's per-ticker daily JSON (`HisseTekil`) carries `END_DEGER` on
every stock row, and `isyatirim_market_data` stores it as `index_value`. It is
the BIST 100 close for that trading date: verified on 2026-10-20 against the
published year-end level (31-12-2024: 9830.56 on THYAO's row). İş Yatırım does
not serve index codes themselves (XU100, XU100.E, BIST100 return empty series),
so other indices stay honestly unavailable.

One level per trading date is served only when every stored row for that date
agrees; a date whose rows disagree is dropped rather than averaged.
`available_at` is the first time this provider stored that date's value -- its
true knowledge time, never an assumed publication time.
"""
from __future__ import annotations

import logging
from datetime import date
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

KIND = "index"
PROVIDER_ID = "isyatirim-public-data"
VERIFIED_CODES = {"XU100"}
SOURCE_FIELD = "END_DEGER"
METHOD = "index_value carried on İş Yatırım daily stock rows (END_DEGER); one agreeing value per trading date"


def _iso(value: Any) -> Optional[str]:
    if value is None:
        return None
    return value.isoformat() if hasattr(value, "isoformat") else str(value)


class IndexRepository:
    def __init__(self, db_manager) -> None:
        self._db = db_manager

    def get_history(
        self,
        code: str,
        date_from: Optional[str] = None,
        date_to: Optional[str] = None,
        limit: int = 300,
    ) -> Dict[str, Any]:
        code = (code or "").strip().upper()
        if code not in VERIFIED_CODES:
            return {"code": code, "items": [], "dropped_dates": 0}
        where = ["(data->>'index_value') IS NOT NULL"]
        params: List[Any] = []
        if date_from:
            where.append("market_date >= %s")
            params.append(date_from)
        if date_to:
            where.append("market_date <= %s")
            params.append(date_to)
        params.append(int(limit))
        rows = self._db.query(
            f"""
            SELECT market_date,
                   COUNT(DISTINCT round((data->>'index_value')::numeric, 2)) AS distinct_values,
                   MIN((data->>'index_value')::float8) AS close,
                   COUNT(*) AS observations,
                   MIN(fetched_at) AS first_fetched_at
            FROM isyatirim_market_history
            WHERE {' AND '.join(where)}
            GROUP BY market_date
            ORDER BY market_date DESC
            LIMIT %s
            """,
            tuple(params),
        )
        items, dropped = [], 0
        for row in rows:
            if int(row.get("distinct_values") or 0) != 1:
                dropped += 1
                continue
            trading_date = row["market_date"]
            # Same envelope as the other history-backed series kinds (macro): the
            # observation in `payload`, point-in-time fields beside it.
            items.append({
                "as_of": _iso(trading_date),
                "available_at": _iso(row.get("first_fetched_at")),
                "status": "ok",
                "payload": {
                    "trading_date": _iso(trading_date),
                    "close": float(row["close"]),
                    "observations": int(row.get("observations") or 0),
                    "source_field": SOURCE_FIELD,
                },
            })
        if dropped:
            logger.warning("Index %s: %d trading date(s) dropped for disagreeing values", code, dropped)
        return {"code": code, "items": items, "dropped_dates": dropped}


def latest_trading_date(items: List[Dict[str, Any]]) -> Optional[date]:
    return date.fromisoformat(items[0]["as_of"]) if items else None
