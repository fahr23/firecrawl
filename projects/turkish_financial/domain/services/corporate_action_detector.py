"""
Corporate-action detection — FA-06 §4 "corporate_actions" kind.

Detects a share-count change (`shares_outstanding`, i.e. İş Yatırım's `SERMAYE`)
between two consecutive trading sessions and derives the implicit ratio a
bonus/rights issue (or split) of that size would imply. Matching that ratio to
a specific KAP disclosure — and therefore to `subscription_price`/`cash_amount`
and a verified `event_type` — is a separate step (`match_detected_change`)
because the detector alone cannot tell a bonus issue from a rights issue; only
the matched KAP disclosure's title can.

Pure functions, no I/O: cheap to unit-test against fixtures.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

# A share-count change below this relative threshold is treated as rounding/
# data noise, not a corporate action — avoids false positives from upstream
# formatting differences.
_MIN_RELATIVE_CHANGE = 0.001


def detect_share_count_changes(
    series: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    """
    Scan a chronologically-ordered market-history series (each item carrying
    `trading_date` and `shares_outstanding`) for share-count jumps.

    Returns a list of ``{ex_date, shares_before, shares_after, implied_ratio}``
    — `ex_date` is the first session where the new share count is observed,
    `implied_ratio` is ``(shares_after / shares_before) - 1`` (the ratio a pure
    bonus/rights issue of this size would carry; a real match may differ if
    the change was actually a buyback, cancellation, or data gap).
    """
    changes: List[Dict[str, Any]] = []
    prior: Optional[Dict[str, Any]] = None

    for item in series:
        shares = item.get("shares_outstanding")
        if shares is None:
            continue
        if prior is not None and prior.get("shares_outstanding"):
            before = prior["shares_outstanding"]
            if before > 0:
                relative_change = (shares - before) / before
                if abs(relative_change) >= _MIN_RELATIVE_CHANGE:
                    changes.append({
                        "ex_date": item.get("trading_date"),
                        "shares_before": before,
                        "shares_after": shares,
                        "implied_ratio": round(relative_change, 8),
                    })
        prior = item

    return changes


def match_detected_change(
    change: Dict[str, Any],
    candidate_events: List[Dict[str, Any]],
    *,
    date_window_days: int = 10,
    ratio_tolerance: float = 0.02,
) -> Dict[str, Any]:
    """
    Match one detected share-count change to the closest-dated bonus_issue or
    rights_issue KAP event within `date_window_days` of the change's `ex_date`.

    `candidate_events` items must carry `event_type`, `published_at` (or
    `available_at`), and `source_disclosure_index`. Returns the change dict
    extended with ``match_status`` (``"matched"`` / ``"unmatched"``) and, when
    matched, ``event_type`` + ``source_disclosure_index``. Never fabricates a
    match when no candidate is close enough in time — §3.4 honest absence.
    """
    from datetime import date, datetime, timedelta

    def _as_date(value: Any) -> Optional[date]:
        if isinstance(value, date):
            return value
        if isinstance(value, datetime):
            return value.date()
        text = str(value)
        try:
            return datetime.fromisoformat(text).date()
        except (TypeError, ValueError):
            pass
        try:
            # isyatirim_market_history stores trading_date as "DD-MM-YYYY".
            return datetime.strptime(text, "%d-%m-%Y").date()
        except (TypeError, ValueError):
            return None

    ex_date = _as_date(change.get("ex_date"))
    if ex_date is None:
        return {**change, "match_status": "unmatched"}

    best: Optional[Dict[str, Any]] = None
    best_delta: Optional[int] = None
    for event in candidate_events:
        if event.get("event_type") not in ("bonus_issue", "rights_issue"):
            continue
        event_date = _as_date(event.get("published_at") or event.get("available_at"))
        if event_date is None:
            continue
        delta = abs((event_date - ex_date).days)
        if delta > date_window_days:
            continue
        if best_delta is None or delta < best_delta:
            best, best_delta = event, delta

    if best is None:
        return {**change, "match_status": "unmatched"}

    return {
        **change,
        "match_status": "matched",
        "event_type": best["event_type"],
        "source_disclosure_index": best.get("source_disclosure_index"),
    }
