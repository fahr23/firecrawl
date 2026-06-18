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

NEWS_WEIGHT = 0.6
SOCIAL_WEIGHT = 0.4


def blend_scores(news: Optional[float], social: Optional[float]) -> Optional[float]:
    """Weighted blend of news/social scores, tolerating a missing side."""
    if news is not None and social is not None:
        return round(NEWS_WEIGHT * news + SOCIAL_WEIGHT * social, 4)
    if news is not None:
        return round(news, 4)
    if social is not None:
        return round(social, 4)
    return None


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
            news_score = existing.get("news_score")
            combined = blend_scores(news_score, social_score)

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
