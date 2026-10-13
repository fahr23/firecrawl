"""
Corporate-action price-adjustment factors — FA-06 §4 "corporate_actions" kind.

F23's BIST prices carry no adjustment factor (`adjclose == close`), so a bonus
or rights issue looks like a price crash to every indicator and label. This
module computes the standard back-adjustment `price_factor` for each FA-06
event type from the event's own terms plus (for rights issues and cash
dividends) the closing price on the last session before the ex-date.

Convention: `price_factor` is the multiplier applied to every price STRICTLY
BEFORE `ex_date` so the adjusted series is continuous across the event
(adjusted_price_before = raw_price_before * price_factor). Prices on/after
`ex_date` are never adjusted for this event (though they may be scaled by a
LATER event's factor, compounding is the caller's job, not this module's).

No I/O: pure arithmetic over already-known inputs, so it is cheap to unit-test
and does not depend on DB/network access.
"""
from __future__ import annotations

from typing import Optional

# Kept in sync with domain.services.kap_event_classifier's taxonomy subset that
# actually changes share count / entitles cash — the other event types never
# produce a corporate action row.
CORPORATE_ACTION_EVENT_TYPES: tuple[str, ...] = (
    "bonus_issue",
    "rights_issue",
    "cash_dividend",
    "split",
    "reverse_split",
)


def bonus_issue_factor(ratio: float) -> Optional[float]:
    """
    Bonus issue (bedelsiz): `ratio` new shares issued per 1 old share (e.g. a
    20% bonus issue is 0.20). Existing holders pay nothing — the share count
    grows and the price mechanically drops in proportion, so
    `price_factor = 1 / (1 + ratio)`.
    """
    if ratio is None or ratio <= 0:
        return None
    return round(1.0 / (1.0 + ratio), 8)


def split_factor(ratio: float) -> Optional[float]:
    """
    Split (ratio > 1, e.g. 2.0 for a 2-for-1 split) or reverse split
    (0 < ratio < 1, e.g. 0.5 for a 1-for-2 reverse split).
    `price_factor = 1 / ratio` either way.
    """
    if ratio is None or ratio <= 0:
        return None
    return round(1.0 / ratio, 8)


def rights_issue_factor(
    ratio: float, subscription_price: float, close_before: float
) -> Optional[float]:
    """
    Rights issue (bedelli): `ratio` new shares offered per 1 old share at
    `subscription_price`, `close_before` = closing price on the last session
    before the ex-date.

    Standard theoretical-ex-rights-price (TERP) adjustment:
        TERP = (close_before + ratio * subscription_price) / (1 + ratio)
        price_factor = TERP / close_before

    Returns None when any input is missing/non-positive — never a fabricated
    factor (§3.4 honest absence); the caller then reports `match_status:
    "unmatched"` with no factor.
    """
    if ratio is None or ratio <= 0 or close_before is None or close_before <= 0:
        return None
    if subscription_price is None or subscription_price < 0:
        return None
    terp = (close_before + ratio * subscription_price) / (1.0 + ratio)
    return round(terp / close_before, 8)


def cash_dividend_factor(cash_amount: float, close_before: float) -> Optional[float]:
    """
    Cash dividend: `cash_amount` per share, `close_before` = closing price on
    the last session before the ex-date.
        price_factor = (close_before - cash_amount) / close_before

    Returns None when the dividend exceeds (or equals) the pre-event close —
    a factor of zero or negative is not a valid back-adjustment.
    """
    if cash_amount is None or cash_amount <= 0:
        return None
    if close_before is None or close_before <= cash_amount:
        return None
    return round((close_before - cash_amount) / close_before, 8)


def compute_price_factor(
    event_type: str,
    *,
    ratio: Optional[float] = None,
    subscription_price: Optional[float] = None,
    cash_amount: Optional[float] = None,
    close_before: Optional[float] = None,
) -> Optional[float]:
    """Dispatch to the right formula by `event_type`; None for anything else
    or when required inputs are missing (honest absence, not a guess)."""
    if event_type == "bonus_issue":
        return bonus_issue_factor(ratio)
    if event_type in ("split", "reverse_split"):
        return split_factor(ratio)
    if event_type == "rights_issue":
        return rights_issue_factor(ratio, subscription_price, close_before)
    if event_type == "cash_dividend":
        return cash_dividend_factor(cash_amount, close_before)
    return None
