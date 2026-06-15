"""
Fundamental analysis calculator — canonical facts → ratios (Data Contract v1.0 §3).

Pure domain logic: given the canonical financial facts produced by
`scrapers.kap_financial_parser.normalize_facts` (current period and, optionally, the
prior comparable period), plus optional market data (price, shares outstanding),
compute the FundamentalPayload metrics.

Design rules:
  - Honest nulls. Any ratio whose inputs are missing or whose denominator is zero is
    left as None — we never fabricate or zero-fill (contract §5).
  - Statement-only ratios (margins, returns, leverage, liquidity, growth) are always
    attempted. Price multiples (P/E, P/B, P/S, EV/EBITDA, PEG, dividend yield) need
    market data and stay None unless `market` supplies it.
  - `data_completeness` reports the fraction of the targeted ratio set we filled, so
    consumers can weight the payload.

No I/O, so this is trivially unit-testable.
"""
from __future__ import annotations

from typing import Any, Dict, Mapping, Optional

# Ratio fields whose presence defines "completeness". Price multiples are excluded
# because they depend on out-of-band market data and would otherwise unfairly drag
# the score down for a perfectly complete statement.
_COMPLETENESS_FIELDS: tuple[str, ...] = (
    "gross_margin",
    "operating_margin",
    "net_margin",
    "roe",
    "roa",
    "roic",
    "debt_to_equity",
    "net_debt_to_ebitda",
    "current_ratio",
    "quick_ratio",
    "interest_coverage",
    "revenue",
    "ebitda",
    "net_income",
    "free_cash_flow",
    "revenue_growth_yoy",
    "eps_growth_yoy",
)


def _num(facts: Mapping[str, Any], key: str) -> Optional[float]:
    value = facts.get(key)
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _safe_div(
    numerator: Optional[float],
    denominator: Optional[float],
    *,
    ndigits: int = 4,
) -> Optional[float]:
    """Divide, returning None on missing inputs or a zero/near-zero denominator."""
    if numerator is None or denominator is None:
        return None
    if abs(denominator) < 1e-9:
        return None
    return round(numerator / denominator, ndigits)


def _ebitda(facts: Mapping[str, Any]) -> Optional[float]:
    """EBITDA ≈ operating profit + D&A; fall back to EBIT + D&A when needed."""
    operating = _num(facts, "operating_profit")
    if operating is None:
        operating = _num(facts, "ebit")
    if operating is None:
        return None
    dna = _num(facts, "depreciation_amortization") or 0.0
    return operating + dna


def _total_debt(facts: Mapping[str, Any]) -> Optional[float]:
    """Total interest-bearing debt from an explicit total or the maturity split."""
    total = _num(facts, "total_debt")
    if total is not None:
        return total
    short = _num(facts, "short_term_debt")
    long = _num(facts, "long_term_debt")
    if short is None and long is None:
        return None
    return (short or 0.0) + (long or 0.0)


def _equity(facts: Mapping[str, Any]) -> Optional[float]:
    """Prefer parent-only equity (matches net income attributable to parent)."""
    return _num(facts, "equity_parent") if facts.get("equity_parent") is not None \
        else _num(facts, "total_equity")


class FundamentalAnalyzer:
    """Computes the contract §3 fundamental metrics from canonical facts."""

    def analyze(
        self,
        facts: Mapping[str, Any],
        prior_facts: Optional[Mapping[str, Any]] = None,
        market: Optional[Mapping[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        Return a FundamentalPayload-shaped dict (excluding period metadata).

        Args:
            facts: canonical facts for the reporting period.
            prior_facts: canonical facts for the prior comparable period (YoY growth).
            market: optional {"price", "shares_outstanding", ...} for price multiples.
        """
        market = market or {}
        revenue = _num(facts, "revenue")
        gross_profit = _num(facts, "gross_profit")
        operating_profit = _num(facts, "operating_profit")
        net_income = _num(facts, "net_income")
        total_assets = _num(facts, "total_assets")
        equity = _equity(facts)
        ebitda = _ebitda(facts)
        total_debt = _total_debt(facts)
        cash = _num(facts, "cash_and_equivalents")
        interest_expense = _num(facts, "interest_expense")

        # cost-of-sales derived gross profit when KAP omits the subtotal
        if gross_profit is None and revenue is not None:
            cos = _num(facts, "cost_of_sales")
            if cos is not None:
                # cost of sales is usually stored as a positive magnitude
                gross_profit = revenue - abs(cos)

        net_debt = None
        if total_debt is not None:
            net_debt = total_debt - (cash or 0.0)

        operating_cf = _num(facts, "operating_cash_flow")
        capex = _num(facts, "capex")
        free_cash_flow = None
        if operating_cf is not None:
            free_cash_flow = operating_cf - abs(capex) if capex is not None else operating_cf

        ebit = operating_profit if operating_profit is not None else _num(facts, "ebit")

        payload: Dict[str, Any] = {
            # profitability margins
            "gross_margin": _safe_div(gross_profit, revenue),
            "operating_margin": _safe_div(operating_profit, revenue),
            "net_margin": _safe_div(net_income, revenue),
            # returns
            "roe": _safe_div(net_income, equity),
            "roa": _safe_div(net_income, total_assets),
            "roic": _safe_div(
                ebit,
                (equity + total_debt) if (equity is not None and total_debt is not None) else None,
            ),
            # leverage
            "debt_to_equity": _safe_div(total_debt, equity),
            "net_debt_to_ebitda": _safe_div(net_debt, ebitda),
            "interest_coverage": _safe_div(ebit, abs(interest_expense) if interest_expense is not None else None),
            # liquidity
            "current_ratio": _safe_div(
                _num(facts, "current_assets"), _num(facts, "current_liabilities")
            ),
            "quick_ratio": self._quick_ratio(facts),
            # absolute figures
            "revenue": revenue,
            "ebitda": round(ebitda, 4) if ebitda is not None else None,
            "net_income": net_income,
            "free_cash_flow": round(free_cash_flow, 4) if free_cash_flow is not None else None,
        }

        # year-over-year growth
        if prior_facts:
            prior_revenue = _num(prior_facts, "revenue")
            payload["revenue_growth_yoy"] = self._growth(revenue, prior_revenue)

        # per-share + price multiples (need shares outstanding / price)
        shares = self._num_market(market, "shares_outstanding") or _num(facts, "shares_outstanding")
        price = self._num_market(market, "price")
        eps = _safe_div(net_income, shares)
        bvps = _safe_div(equity, shares)
        payload["eps"] = eps
        payload["book_value_per_share"] = bvps

        dividends_paid = _num(facts, "dividends_paid")
        dps = _safe_div(abs(dividends_paid) if dividends_paid is not None else None, shares)
        payload["dividend_per_share"] = dps

        if price is not None:
            payload["pe_ratio"] = _safe_div(price, eps)
            payload["pb_ratio"] = _safe_div(price, bvps)
            payload["ps_ratio"] = _safe_div(
                price * shares if (price is not None and shares is not None) else None, revenue
            )
            payload["dividend_yield"] = _safe_div(dps, price)
            if ebitda is not None and shares is not None:
                market_cap = price * shares
                ev = market_cap + (net_debt or 0.0)
                payload["ev_ebitda"] = _safe_div(ev, ebitda)

        if prior_facts:
            prior_net_income = _num(prior_facts, "net_income")
            prior_shares = self._num_market(market, "prior_shares_outstanding") or _num(
                prior_facts, "shares_outstanding"
            ) or shares
            prior_eps = _safe_div(prior_net_income, prior_shares)
            eps_growth = self._growth(eps, prior_eps)
            payload["eps_growth_yoy"] = eps_growth
            if payload.get("pe_ratio") is not None and eps_growth not in (None, 0.0):
                # PEG uses growth in percentage points.
                payload["peg_ratio"] = _safe_div(payload["pe_ratio"], eps_growth * 100.0)

        payload["data_completeness"] = self._completeness(payload)
        return payload

    # ── helpers ───────────────────────────────────────────────────────────────
    @staticmethod
    def _num_market(market: Mapping[str, Any], key: str) -> Optional[float]:
        value = market.get(key)
        if value is None:
            return None
        try:
            return float(value)
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _quick_ratio(facts: Mapping[str, Any]) -> Optional[float]:
        ca = _num(facts, "current_assets")
        cl = _num(facts, "current_liabilities")
        inv = _num(facts, "inventories")
        if ca is None or cl is None:
            return None
        return _safe_div(ca - (inv or 0.0), cl)

    @staticmethod
    def _growth(current: Optional[float], prior: Optional[float]) -> Optional[float]:
        """YoY growth as a fraction; None if prior is missing/zero. Uses |prior| as base
        so a shrinking loss vs. a prior profit keeps a sensible sign."""
        if current is None or prior is None or abs(prior) < 1e-9:
            return None
        return round((current - prior) / abs(prior), 4)

    @staticmethod
    def _completeness(payload: Mapping[str, Any]) -> float:
        filled = sum(1 for f in _COMPLETENESS_FIELDS if payload.get(f) is not None)
        return round(filled / len(_COMPLETENESS_FIELDS), 4)
