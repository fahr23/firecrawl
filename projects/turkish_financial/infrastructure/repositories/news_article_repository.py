"""
Aggregated sentiment repositories — Data Contract v1.0 surface for portal/social news.

Reads the daily `aggregated_ticker_sentiment` rollup (computed by the collect use cases
from individual articles/posts) and normalises it into the contract's common envelope
with `kind = "sentiment"`. Three column-bound views share one generic implementation:

  - NewsArticleRepository      → `news_score`     (provider "news-portal-scraper")
  - SocialSentimentRepository  → `social_score`   (provider "social-media-scraper")
  - CombinedSentimentRepository→ `combined_score` (provider "news+social")

The stored score is already a signed −1..+1 scalar, so we map it straight onto the
contract `score` and derive `overall_sentiment` from its sign and `confidence` from its
magnitude (§2). The router stays thin; on no-data we return an honest `unavailable`
envelope (§5).
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

PROVIDER_ID = "news-portal-scraper"  # default provider (news view)

# Below this magnitude the day's aggregate is treated as neutral.
_NEUTRAL_BAND = 0.05

_SELECT = (
    "ticker, period_date, news_score, news_count, "
    "social_score, social_count, combined_score, computed_at"
)


def _sentiment_from_score(score: float) -> str:
    if score > _NEUTRAL_BAND:
        return "positive"
    if score < -_NEUTRAL_BAND:
        return "negative"
    return "neutral"


class AggregateSentimentRepository:
    """Column-bound view over aggregated_ticker_sentiment → contract envelopes."""

    # score column read for this view; sample_size sums these count columns.
    _SCORE_COL = "combined_score"
    _COUNT_COLS = ("news_count", "social_count")
    _PROVIDER = "news+social"

    def __init__(self, db_manager):
        self._db = db_manager

    # ── point (latest aggregate at/<= as_of) ──────────────────────────────────
    def get_point(
        self, instrument: str, market: str, as_of: Optional[str] = None
    ) -> Dict[str, Any]:
        ticker = (instrument or "").strip().upper()
        if not supports_market(market) or not ticker:
            return self._unavailable(instrument, market)

        # _SCORE_COL is a controlled class constant, never user input.
        where = ["ticker = %s", f"{self._SCORE_COL} IS NOT NULL"]
        params: List[Any] = [ticker]
        if as_of:
            where.append("period_date <= %s")
            params.append(as_of)

        rows = self._db.query(
            f"SELECT {_SELECT} FROM aggregated_ticker_sentiment "
            f"WHERE {' AND '.join(where)} "
            "ORDER BY period_date DESC NULLS LAST LIMIT 1",
            tuple(params),
        )
        if not rows:
            return self._unavailable(instrument, market)
        return self._envelope(ticker, market, rows[0])

    # ── history (cursor-paginated, newest first) ──────────────────────────────
    def get_history(
        self,
        instrument: str,
        market: str,
        date_from: Optional[str] = None,
        date_to: Optional[str] = None,
        limit: int = 100,
        cursor: Optional[str] = None,
    ) -> Dict[str, Any]:
        ticker = (instrument or "").strip().upper()
        if not supports_market(market) or not ticker:
            return {"instrument": instrument, "market": market, "items": [], "next_cursor": None}

        where = ["ticker = %s", f"{self._SCORE_COL} IS NOT NULL"]
        params: List[Any] = [ticker]
        if date_from:
            where.append("period_date >= %s")
            params.append(date_from)
        if date_to:
            where.append("period_date <= %s")
            params.append(date_to)
        if cursor:
            where.append("period_date < %s")
            params.append(cursor)

        fetch = max(1, min(limit, 1000))
        rows = self._db.query(
            f"SELECT {_SELECT} FROM aggregated_ticker_sentiment "
            f"WHERE {' AND '.join(where)} "
            "ORDER BY period_date DESC NULLS LAST LIMIT %s",
            tuple(params + [fetch + 1]),
        )

        next_cursor = None
        if len(rows) > fetch:
            rows = rows[:fetch]
            next_cursor = str(rows[-1].get("period_date")) if rows[-1].get("period_date") else None

        items = [
            {"as_of": _to_iso_utc(r.get("period_date")), "payload": self._payload(r)}
            for r in rows
        ]
        return {
            "instrument": ticker,
            "market": market,
            "items": items,
            "next_cursor": next_cursor,
        }

    # ── shaping helpers ───────────────────────────────────────────────────────
    def _payload(self, row: Dict[str, Any]) -> Dict[str, Any]:
        score = row.get(self._SCORE_COL)
        if score is None:
            score = 0.0
        score = max(-1.0, min(1.0, float(score)))
        sentiment = _sentiment_from_score(score)

        sample = sum(int(row.get(c) or 0) for c in self._COUNT_COLS)
        return {
            "overall_sentiment": sentiment,
            "score": round(score, 4),
            "confidence": round(abs(score), 4),
            "analyzer": self._PROVIDER,
            "sample_size": sample,
        }

    def _envelope(self, ticker: str, market: str, row: Dict[str, Any]) -> Dict[str, Any]:
        effective = row.get("period_date") or row.get("computed_at")
        return {
            "contract_version": "1.0",
            "instrument": ticker,
            "market": market,
            "kind": "sentiment",
            "as_of": _to_iso_utc(effective),
            "provider": self._PROVIDER,
            "source": "external-db",
            "freshness_seconds": _freshness_seconds(effective),
            "status": "ok",
            "payload": self._payload(row),
        }

    def _unavailable(self, instrument: str, market: str) -> Dict[str, Any]:
        return {
            "contract_version": "1.0",
            "instrument": instrument,
            "market": market,
            "kind": "sentiment",
            "as_of": None,
            "provider": self._PROVIDER,
            "source": "external-db",
            "freshness_seconds": 0,
            "status": "unavailable",
            "payload": None,
        }


class NewsArticleRepository(AggregateSentimentRepository):
    """News-only view (news_score)."""

    _SCORE_COL = "news_score"
    _COUNT_COLS = ("news_count",)
    _PROVIDER = "news-portal-scraper"


class SocialSentimentRepository(AggregateSentimentRepository):
    """Social-only view (social_score)."""

    _SCORE_COL = "social_score"
    _COUNT_COLS = ("social_count",)
    _PROVIDER = "social-media-scraper"


class CombinedSentimentRepository(AggregateSentimentRepository):
    """Blended view (combined_score = 0.6·news + 0.4·social)."""

    _SCORE_COL = "combined_score"
    _COUNT_COLS = ("news_count", "social_count")
    _PROVIDER = "news+social"
