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
from typing import List, Optional

from pydantic import BaseModel, Field


CONTRACT_VERSION = "1.0"


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


# ── envelope ─────────────────────────────────────────────────────────────────
class ProviderEnvelope(BaseModel):
    """§1 — every point endpoint returns one of these."""

    contract_version: str = CONTRACT_VERSION
    instrument: str
    market: Market
    kind: Kind
    as_of: Optional[str] = None  # ISO-8601 UTC; null only when status != ok
    provider: str
    source: str = "external-db"
    freshness_seconds: int = Field(..., ge=0)
    status: ProviderStatus
    payload: Optional[dict] = None  # SentimentPayload | FundamentalPayload | null


class BatchEnvelope(BaseModel):
    """§4 batch — wraps many envelopes; per-item status allows `partial`."""

    contract_version: str = CONTRACT_VERSION
    items: List[ProviderEnvelope]


class HistoryItem(BaseModel):
    as_of: Optional[str] = None
    payload: Optional[dict] = None


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
