"""
Unit tests for the FundamentalAnalyzer domain service (Data Contract v1.0 §3).

Pure math over canonical facts — no DB, no network. Verifies each ratio family,
price-multiple derivation, YoY growth, honest nulls on missing/zero inputs, and the
data_completeness score.
"""
import math

import pytest

from domain.services.fundamental_analyzer_service import FundamentalAnalyzer


CURRENT = {
    "revenue": 1000.0,
    "gross_profit": 400.0,
    "operating_profit": 200.0,
    "net_income": 150.0,
    "total_assets": 2000.0,
    "total_equity": 800.0,
    "depreciation_amortization": 50.0,
    "interest_expense": 40.0,
    "current_assets": 500.0,
    "current_liabilities": 250.0,
    "inventories": 100.0,
    "short_term_debt": 100.0,
    "long_term_debt": 300.0,
    "cash_and_equivalents": 100.0,
    "operating_cash_flow": 180.0,
    "capex": 80.0,
    "dividends_paid": 30.0,
}
PRIOR = {"revenue": 800.0, "net_income": 120.0}
MARKET = {"price": 10.0, "shares_outstanding": 100.0}


def approx(a, b):
    return a is not None and math.isclose(a, b, rel_tol=1e-3, abs_tol=1e-4)


class TestStatementRatios:
    def setup_method(self):
        self.p = FundamentalAnalyzer().analyze(CURRENT)

    def test_margins(self):
        assert approx(self.p["gross_margin"], 0.4)
        assert approx(self.p["operating_margin"], 0.2)
        assert approx(self.p["net_margin"], 0.15)

    def test_returns(self):
        assert approx(self.p["roe"], 0.1875)
        assert approx(self.p["roa"], 0.075)
        assert approx(self.p["roic"], 200 / 1200)

    def test_leverage_and_coverage(self):
        assert approx(self.p["debt_to_equity"], 0.5)
        assert approx(self.p["net_debt_to_ebitda"], 300 / 250)
        assert approx(self.p["interest_coverage"], 5.0)

    def test_liquidity(self):
        assert approx(self.p["current_ratio"], 2.0)
        assert approx(self.p["quick_ratio"], 1.6)

    def test_absolute_figures(self):
        assert approx(self.p["ebitda"], 250.0)
        assert approx(self.p["free_cash_flow"], 100.0)
        assert approx(self.p["revenue"], 1000.0)
        assert approx(self.p["net_income"], 150.0)


class TestGrowthAndPerShare:
    def test_yoy_growth(self):
        p = FundamentalAnalyzer().analyze(CURRENT, prior_facts=PRIOR)
        assert approx(p["revenue_growth_yoy"], 0.25)
        # eps growth uses prior shares == current shares fallback (none given) -> None
        assert p.get("eps_growth_yoy") is None

    def test_per_share_and_multiples(self):
        p = FundamentalAnalyzer().analyze(CURRENT, prior_facts=PRIOR, market=MARKET)
        assert approx(p["eps"], 1.5)
        assert approx(p["book_value_per_share"], 8.0)
        assert approx(p["dividend_per_share"], 0.3)
        assert approx(p["pe_ratio"], 10 / 1.5)
        assert approx(p["pb_ratio"], 1.25)
        assert approx(p["ps_ratio"], 1.0)
        assert approx(p["ev_ebitda"], 1300 / 250)
        assert approx(p["dividend_yield"], 0.03)
        assert approx(p["eps_growth_yoy"], 0.25)
        assert approx(p["peg_ratio"], (10 / 1.5) / 25.0)


class TestHonestNulls:
    def test_zero_denominator_is_none(self):
        p = FundamentalAnalyzer().analyze({"revenue": 0.0, "net_income": 50.0})
        assert p["net_margin"] is None

    def test_missing_inputs_are_none_not_zero(self):
        p = FundamentalAnalyzer().analyze({"revenue": 1000.0})
        assert p["net_margin"] is None
        assert p["roe"] is None
        assert p["ebitda"] is None
        # no exception, and completeness is low
        assert p["data_completeness"] < 0.2

    def test_no_price_means_no_multiples(self):
        p = FundamentalAnalyzer().analyze(CURRENT)  # no market
        assert p.get("pe_ratio") is None
        assert p.get("ev_ebitda") is None

    def test_gross_profit_derived_from_cost_of_sales(self):
        p = FundamentalAnalyzer().analyze({"revenue": 1000.0, "cost_of_sales": 600.0})
        assert approx(p["gross_margin"], 0.4)


class TestCompleteness:
    def test_full_statement_is_complete(self):
        # With prior period + market data every completeness field can be filled.
        p = FundamentalAnalyzer().analyze(CURRENT, prior_facts=PRIOR, market=MARKET)
        assert approx(p["data_completeness"], 1.0)

    def test_statement_only_is_near_complete(self):
        # Without shares, eps_growth_yoy can't be derived -> 16/17 of the set.
        p = FundamentalAnalyzer().analyze(CURRENT, prior_facts=PRIOR)
        assert approx(p["data_completeness"], 16 / 17)

    def test_empty_is_zero(self):
        p = FundamentalAnalyzer().analyze({})
        assert p["data_completeness"] == 0.0
