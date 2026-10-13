"""
Unit tests for FA-06 corporate-action price-adjustment factors.

Pure arithmetic — no DB, no network. Each test checks the formula against a
hand-computed scenario, including the accept criterion from the requirements
doc: a bonus issue's factor removes the false price drop it would otherwise
cause in an unadjusted series.
"""
import math

from domain.services.corporate_action_pricing import (
    bonus_issue_factor,
    cash_dividend_factor,
    compute_price_factor,
    rights_issue_factor,
    split_factor,
)


def approx(a, b, tol=1e-6):
    return a is not None and math.isclose(a, b, rel_tol=tol, abs_tol=tol)


class TestBonusIssue:
    def test_20_percent_bonus_issue_factor(self):
        # 20% bonus issue: 1.2 shares outstanding per 1 before. Price should be
        # expected to fall ~1/1.2 = 0.8333 mechanically (not a real loss).
        factor = bonus_issue_factor(0.20)
        assert approx(factor, 1 / 1.2)

    def test_factor_removes_the_false_price_crash(self):
        """Accept criterion: applying the factor to the pre-event close makes
        it continuous with the post-event close, instead of showing a crash."""
        close_before = 100.0
        ratio = 0.20
        factor = bonus_issue_factor(ratio)
        adjusted_close_before = close_before * factor
        # The post-event close for an unchanged company value is close_before / (1+ratio).
        expected_post_event_close = close_before / (1 + ratio)
        assert approx(adjusted_close_before, expected_post_event_close)

    def test_zero_or_negative_ratio_is_none(self):
        assert bonus_issue_factor(0) is None
        assert bonus_issue_factor(-0.1) is None
        assert bonus_issue_factor(None) is None


class TestSplit:
    def test_two_for_one_split(self):
        assert approx(split_factor(2.0), 0.5)

    def test_reverse_split(self):
        assert approx(split_factor(0.5), 2.0)

    def test_invalid_ratio_is_none(self):
        assert split_factor(0) is None
        assert split_factor(-1) is None


class TestRightsIssue:
    def test_terp_adjustment(self):
        # 1 new share per 4 old (ratio=0.25) at subscription price 10, close 20.
        # TERP = (20 + 0.25*10) / 1.25 = 22.5 / 1.25 = 18.0
        factor = rights_issue_factor(ratio=0.25, subscription_price=10.0, close_before=20.0)
        assert approx(factor, 18.0 / 20.0)

    def test_subscription_price_equal_to_market_price_yields_factor_near_one(self):
        # Rights priced at market: no dilution benefit, factor should be ~1.
        factor = rights_issue_factor(ratio=0.25, subscription_price=20.0, close_before=20.0)
        assert approx(factor, 1.0)

    def test_missing_close_before_is_none(self):
        assert rights_issue_factor(ratio=0.25, subscription_price=10.0, close_before=None) is None

    def test_zero_close_before_is_none(self):
        assert rights_issue_factor(ratio=0.25, subscription_price=10.0, close_before=0) is None


class TestCashDividend:
    def test_dividend_adjustment(self):
        factor = cash_dividend_factor(cash_amount=2.0, close_before=40.0)
        assert approx(factor, 38.0 / 40.0)

    def test_dividend_exceeding_close_is_none(self):
        # A dividend larger than the share price is not a valid back-adjustment input.
        assert cash_dividend_factor(cash_amount=50.0, close_before=40.0) is None

    def test_zero_dividend_is_none(self):
        assert cash_dividend_factor(cash_amount=0, close_before=40.0) is None


class TestDispatch:
    def test_compute_price_factor_routes_by_event_type(self):
        assert approx(compute_price_factor("bonus_issue", ratio=0.2), 1 / 1.2)
        assert approx(compute_price_factor("split", ratio=2.0), 0.5)
        assert approx(
            compute_price_factor("rights_issue", ratio=0.25, subscription_price=10.0, close_before=20.0),
            18.0 / 20.0,
        )
        assert approx(
            compute_price_factor("cash_dividend", cash_amount=2.0, close_before=40.0),
            38.0 / 40.0,
        )

    def test_unknown_event_type_is_none(self):
        assert compute_price_factor("insider_trade", ratio=0.2) is None

    def test_missing_required_input_is_none_not_a_guess(self):
        # rights_issue without subscription_price must not silently assume 0.
        assert compute_price_factor("rights_issue", ratio=0.25, close_before=20.0) is None
