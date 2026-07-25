"""
Collect Social Sentiment Use Case (Phase 2).

Orchestrates the X/FinTwit sentiment pipeline:
  1. scrape posts per ticker (SocialMediaScraper — Firecrawl Playwright)
  2. analyse each post's sentiment (SentimentAnalyzerService — reused unchanged)
  3. persist post + per-post sentiment (DatabaseManager helpers)
  4. update the social_* columns of the daily per-ticker rollup and recompute
     combined_score by blending the existing news score with the new social score.

Blend rule (matches the data-contract plan):
    combined = 0.6·news + 0.4·social   when both are present
             = news                     when only news exists
             = social                   when only social exists
"""
from __future__ import annotations

import logging
from collections import defaultdict
from typing import Any, Dict, List, Optional

from domain.entities.social_post import SocialPost
from domain.services.sentiment_analyzer_service import ISentimentAnalyzer
from domain.value_objects.sentiment import SentimentAnalysis

logger = logging.getLogger(__name__)

# Base weights for each source. When a source is absent its weight is dropped and the
# remaining weights are renormalized — so news+social collapses to exactly 0.6/0.4,
# which preserves the pre-YouTube combined_score behaviour.
_BASE_WEIGHTS: Dict[str, float] = {
    "news": 0.6,
    "social": 0.4,
    "youtube": 0.25,
}


def blend_sources(scores: Dict[str, Optional[float]]) -> Optional[float]:
    """
    Weighted blend across any subset of {news, social, youtube} score sources.

    Missing or None sides are excluded; the remaining weights are renormalized.
    Returns None when no side has a value.

    Backward-compat: news+social only → exactly 0.6·news + 0.4·social (same as before).
    """
    present = {k: v for k, v in scores.items() if v is not None}
    if not present:
        return None
    total_w = sum(_BASE_WEIGHTS.get(k, 0.0) for k in present)
    if total_w == 0.0:
        return None
    combined = sum(_BASE_WEIGHTS.get(k, 0.0) * v for k, v in present.items()) / total_w
    return round(combined, 4)


def blend_scores(news: Optional[float], social: Optional[float]) -> Optional[float]:
    """Backward-compat two-source blend (news + social). Delegates to blend_sources."""
    return blend_sources({"news": news, "social": social})


class CollectSocialSentimentUseCase:
    """Coordinate scrape → analyse → persist → blended aggregate for X/FinTwit."""

    def __init__(self, scraper, sentiment_analyzer: ISentimentAnalyzer, db_manager):
        self._scraper = scraper
        self._analyzer = sentiment_analyzer
        self._db = db_manager

    async def execute(
        self,
        tickers: List[str],
        days_back: int = 7,
        limit_per_ticker: int = 30,
    ) -> Dict[str, Any]:
        scrape_result = await self._scraper.scrape_all(
            tickers=tickers,
            days_back=days_back,
            limit_per_ticker=limit_per_ticker,
        )
        posts: List[SocialPost] = scrape_result.get("posts", [])

        analyzed = 0
        saved = 0
        buckets: Dict[tuple, List[float]] = defaultdict(list)

        for post in posts:
            sentiment = await self._analyze(post)
            if sentiment is None:
                continue
            analyzed += 1
            if self._persist(post, sentiment):
                saved += 1

            day = (post.posted_at or post.scraped_at).date()
            buckets[(post.ticker, day)].append(
                sentiment.to_score() * sentiment.confidence.value
            )

        aggregated = self._aggregate(buckets)

        return {
            "success": True,
            "scraped": scrape_result.get("total", len(posts)),
            "analyzed": analyzed,
            "saved": saved,
            "aggregated_tickers": aggregated,
            "by_ticker": scrape_result.get("by_ticker", {}),
        }

    # ── steps ─────────────────────────────────────────────────────────────────
    async def _analyze(self, post: SocialPost) -> Optional[SentimentAnalysis]:
        try:
            return await self._analyzer.analyze(post.text_for_analysis())
        except Exception as e:  # noqa: BLE001 - one bad post must not abort the run
            logger.error(f"Sentiment analysis failed for {post.post_id}: {e}")
            return None

    def _persist(self, post: SocialPost, sentiment: SentimentAnalysis) -> bool:
        if self._db is None:
            return False
        post_pk = self._db.upsert_social_post(post.to_db_row())
        if not post_pk:
            return False
        return self._db.upsert_social_post_sentiment(
            post_pk,
            {
                "overall_sentiment": sentiment.overall_sentiment.value,
                "sentiment_score": sentiment.to_score(),
                "confidence": sentiment.confidence.value,
                "analyzer": "social-media-scraper",
            },
        )

    def _aggregate(self, buckets: Dict[tuple, List[float]]) -> int:
        """Recompute social_score per ticker/day and blend with existing news_score."""
        if self._db is None:
            return 0
        count = 0
        for (ticker, day), scores in buckets.items():
            if not scores:
                continue
            social_score = round(sum(scores) / len(scores), 4)

            existing = self._db.get_aggregated_ticker_sentiment(ticker, day) or {}
            combined = blend_sources({
                "news": existing.get("news_score"),
                "social": social_score,
                "youtube": existing.get("youtube_score"),
            })

            ok = self._db.upsert_aggregated_ticker_sentiment(
                {
                    "ticker": ticker,
                    "period_date": day,
                    "social_score": social_score,
                    "social_count": len(scores),
                    "combined_score": combined,
                }
            )
            if ok:
                count += 1
        return count
