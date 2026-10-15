"""
External Analysis Provider — Data Contract v1.0 entities.

This is the provider side of the contract documented in
`External Analysis Provider — Data Contract v1.0` (2026-06-14). `strategy_management`
is the only consumer; it pulls these envelopes over HTTP, keeps the fields below and
discards anything else.

This service is the **sentiment** provider (`provider = "kap-scraper"`). The KAP
disclosures stored in our own database are normalised into the common envelope here.
We never share a DB handle or schema with the consumer.

References:
  - §1 common response envelope
  - §2 sentiment payload
  - §3 fundamental payload (modelled for completeness; this provider only emits sentiment)
  - §7 Pydantic shapes
"""
from __future__ import annotations

from enum import Enum
from typing import Dict, List, Optional

from pydantic import BaseModel, Field


CONTRACT_VERSION_1_0 = "1.0"
CONTRACT_VERSION_1_1 = "1.1"
SUPPORTED_CONTRACT_VERSIONS = (CONTRACT_VERSION_1_0, CONTRACT_VERSION_1_1)
# Server default: 1.1 is the baseline shape every consumer should get unless it
# explicitly asks for the legacy 1.0 envelope (point-in-time fields, revision_id,
# field_status). provider-wait-list.md §1's example envelope is 1.1, and FA-01
# frames it as something consumers are waiting to receive, not opt into per call.
CONTRACT_VERSION = CONTRACT_VERSION_1_1


# ── enums ───────────────────────────────────────────────────────────────────
class Market(str, Enum):
    BIST = "bist"
    USA = "usa"
    COIN = "coin"


class Kind(str, Enum):
    SENTIMENT = "sentiment"
    FUNDAMENTAL = "fundamental"


class ProviderStatus(str, Enum):
    OK = "ok"
    PARTIAL = "partial"
    UNAVAILABLE = "unavailable"


class OverallSentiment(str, Enum):
    POSITIVE = "positive"
    NEUTRAL = "neutral"
    NEGATIVE = "negative"


class ImpactHorizon(str, Enum):
    SHORT_TERM = "short_term"
    MEDIUM_TERM = "medium_term"
    LONG_TERM = "long_term"


class RiskLevel(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class FieldStatus(str, Enum):
    """Contract 1.1 §3.2 — per-payload-field provenance (FA-01)."""

    REPORTED = "reported"
    DERIVED = "derived"
    ESTIMATED = "estimated"
    UNAVAILABLE = "unavailable"


# ── payloads ─────────────────────────────────────────────────────────────────
class SentimentPayload(BaseModel):
    """§2 — normalises the existing KAP sentiment shape."""

    overall_sentiment: OverallSentiment
    score: float = Field(..., ge=-1.0, le=1.0, description="Canonical scalar, -1..+1")
    confidence: float = Field(..., ge=0.0, le=1.0)
    impact_horizon: Optional[ImpactHorizon] = None
    key_drivers: Optional[List[str]] = None
    risk_flags: Optional[List[str]] = None
    risk_level: Optional[RiskLevel] = None
    tone_descriptors: Optional[List[str]] = None
    sample_size: Optional[int] = Field(default=None, ge=0)
    analyzer: Optional[str] = Field(default=None, description="keyword | huggingface | llm:<model>")


class FundamentalPayload(BaseModel):
    """§3 — modelled for contract completeness; this provider does not emit it."""

    period: str
    fiscal_period: Optional[str] = None
    currency: Optional[str] = None
    reporting_standard: Optional[str] = None

    pe_ratio: Optional[float] = None
    pb_ratio: Optional[float] = None
    ps_ratio: Optional[float] = None
    ev_ebitda: Optional[float] = None
    peg_ratio: Optional[float] = None

    eps: Optional[float] = None
    book_value_per_share: Optional[float] = None
    dividend_per_share: Optional[float] = None
    dividend_yield: Optional[float] = None

    gross_margin: Optional[float] = None
    operating_margin: Optional[float] = None
    net_margin: Optional[float] = None
    roe: Optional[float] = None
    roa: Optional[float] = None
    roic: Optional[float] = None

    debt_to_equity: Optional[float] = None
    net_debt_to_ebitda: Optional[float] = None
    current_ratio: Optional[float] = None
    quick_ratio: Optional[float] = None
    interest_coverage: Optional[float] = None

    revenue: Optional[float] = None
    ebitda: Optional[float] = None
    net_income: Optional[float] = None
    free_cash_flow: Optional[float] = None
    revenue_growth_yoy: Optional[float] = None
    eps_growth_yoy: Optional[float] = None

    is_estimated: Optional[bool] = None
    restated: Optional[bool] = None
    data_completeness: Optional[float] = None

    # — FA-03 statement line items (contract 1.1 §3.2; additive, all optional) —
    consolidation: Optional[str] = None  # "consolidated" | "solo"
    statement_template: Optional[str] = None  # industrial | bank | insurance | leasing | factoring
    flow_basis: Optional[str] = None  # "ytd" (KAP default) | "quarter"

    # income statement
    cost_of_sales: Optional[float] = None
    gross_profit: Optional[float] = None
    operating_profit: Optional[float] = None
    ebit: Optional[float] = None
    depreciation_amortization: Optional[float] = None
    interest_expense: Optional[float] = None
    net_finance_expense: Optional[float] = None
    tax_expense: Optional[float] = None
    pretax_profit: Optional[float] = None
    net_income_parent: Optional[float] = None

    # balance sheet
    total_assets: Optional[float] = None
    current_assets: Optional[float] = None
    cash_and_equivalents: Optional[float] = None
    trade_receivables: Optional[float] = None
    inventories: Optional[float] = None
    current_liabilities: Optional[float] = None
    trade_payables: Optional[float] = None
    short_term_financial_debt: Optional[float] = None
    long_term_financial_debt: Optional[float] = None
    total_liabilities: Optional[float] = None
    total_equity: Optional[float] = None
    equity_parent: Optional[float] = None
    minority_interest: Optional[float] = None
    retained_earnings: Optional[float] = None

    # cash flow
    operating_cash_flow: Optional[float] = None
    capex: Optional[float] = None
    dividends_paid: Optional[float] = None
    interest_paid: Optional[float] = None
    taxes_paid: Optional[float] = None

    # shares (period end)
    shares_outstanding: Optional[float] = None


# ── envelope ─────────────────────────────────────────────────────────────────
class ProviderEnvelope(BaseModel):
    """§1 — every point endpoint returns one of these.

    Fields below `status` and above `payload` are additive, contract-1.1-only
    (FA-01 §3.2): a `1.0` response omits them entirely. `field_status` keys
    mirror `payload` keys and are 1.1-only as well.
    """

    contract_version: str = CONTRACT_VERSION
    instrument: str
    market: Market
    kind: Kind
    as_of: Optional[str] = None  # ISO-8601 UTC; null only when status != ok
    provider: str
    source: str = "external-db"
    freshness_seconds: int = Field(..., ge=0)
    status: ProviderStatus

    # — contract 1.1 additive fields (§3.2) —
    published_at: Optional[str] = None
    available_at: Optional[str] = None
    period_end: Optional[str] = None
    fetched_at: Optional[str] = None
    revision_id: Optional[str] = None

    payload: Optional[dict] = None  # SentimentPayload | FundamentalPayload | null
    field_status: Optional[Dict[str, FieldStatus]] = None


class BatchEnvelope(BaseModel):
    """§4 batch — wraps many envelopes; per-item status allows `partial`."""

    contract_version: str = CONTRACT_VERSION
    items: List[ProviderEnvelope]


class HistoryItem(BaseModel):
    as_of: Optional[str] = None
    payload: Optional[dict] = None

    # — contract 1.1 additive fields (§3.2 / §3.5), same rule as ProviderEnvelope —
    published_at: Optional[str] = None
    available_at: Optional[str] = None
    period_end: Optional[str] = None
    fetched_at: Optional[str] = None
    revision_id: Optional[str] = None
    status: Optional[ProviderStatus] = None
    field_status: Optional[Dict[str, FieldStatus]] = None


class HistoryEnvelope(BaseModel):
    """§4 history — cursor-paginated time series."""

    contract_version: str = CONTRACT_VERSION
    instrument: str
    market: Market
    kind: Kind
    items: List[HistoryItem]
    next_cursor: Optional[str] = None


class ErrorEnvelope(BaseModel):
    """§5 / §6.7 — honest error/unavailable body."""

    contract_version: str = CONTRACT_VERSION
    status: ProviderStatus = ProviderStatus.UNAVAILABLE
    error_code: str
    detail: str


class HealthEnvelope(BaseModel):
    """§6.8 — connectivity/freshness badge."""

    status: str
    contract_version: str = CONTRACT_VERSION
    provider: str


# ── score derivation (§2 fallback rule) ──────────────────────────────────────
def derive_score(overall_sentiment: str, confidence: float) -> float:
    """
    Derive the canonical −1..+1 score from sentiment direction × confidence.

    positive → +confidence, negative → −confidence, neutral → 0.0.
    Used when the stored row does not already carry a signed score.
    """
    try:
        c = max(0.0, min(1.0, float(confidence)))
    except (TypeError, ValueError):
        c = 0.0

    s = (overall_sentiment or "").lower()
    if s == OverallSentiment.POSITIVE.value:
        return round(c, 4)
    if s == OverallSentiment.NEGATIVE.value:
        return round(-c, 4)
    return 0.0
