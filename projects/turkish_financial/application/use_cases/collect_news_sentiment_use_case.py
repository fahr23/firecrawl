"""
Collect News Sentiment Use Case.

Orchestrates the news-portal sentiment pipeline:
  1. scrape articles from Turkish financial portals (NewsPortalScraper)
  2. analyse each article's sentiment (SentimentAnalyzerService — reused unchanged)
  3. persist article + per-article sentiment (DatabaseManager helpers)
  4. recompute the daily per-ticker rollup (aggregated_ticker_sentiment)

Sentiment is analysed with the same LLM pipeline used for KAP disclosures, so the
contract `analyzer` provenance and Turkish-prompt behaviour stay consistent. Articles
with no ticker (macro/sector headlines) are still stored and analysed, but only
ticker-tagged articles contribute to the per-ticker aggregate.
"""
from __future__ import annotations

import logging
from collections import defaultdict
from datetime import datetime
from typing import Any, Dict, List, Optional

from domain.entities.news_article import NewsArticle
from domain.services.sentiment_analyzer_service import ISentimentAnalyzer
from domain.value_objects.sentiment import SentimentAnalysis

logger = logging.getLogger(__name__)


class CollectNewsSentimentUseCase:
    """Coordinate scrape → analyse → persist → aggregate for portal news."""

    def __init__(
        self,
        scraper,
        sentiment_analyzer: ISentimentAnalyzer,
        db_manager,
    ):
        self._scraper = scraper
        self._analyzer = sentiment_analyzer
        self._db = db_manager

    async def execute(
        self,
        tickers: Optional[List[str]] = None,
        days_back: int = 7,
        sources: Optional[List[str]] = None,
        include_investing_comments: bool = True,
    ) -> Dict[str, Any]:
        """
        Run the full pipeline.

        Returns a summary dict: scraped/analyzed/saved counts, aggregated tickers,
        and the per-source breakdown from the scraper.
        """
        scrape_result = await self._scraper.scrape_all(
            tickers=tickers,
            days_back=days_back,
            sources=sources,
            include_investing_comments=include_investing_comments,
        )
        articles: List[NewsArticle] = scrape_result.get("articles", [])

        analyzed = 0
        saved = 0
        # Collect (score, confidence) per ticker per day for the rollup.
        buckets: Dict[tuple, List[float]] = defaultdict(list)

        for article in articles:
            sentiment = await self._analyze(article)
            if sentiment is None:
                continue
            analyzed += 1

            if self._persist(article, sentiment):
                saved += 1

            if article.ticker:
                day = (article.published_at or article.scraped_at).date()
                buckets[(article.ticker, day)].append(
                    sentiment.to_score() * sentiment.confidence.value
                )

        aggregated = self._aggregate(buckets)

        return {
            "success": True,
            "scraped": scrape_result.get("total", len(articles)),
            "analyzed": analyzed,
            "saved": saved,
            "aggregated_tickers": aggregated,
            "by_source": scrape_result.get("by_source", {}),
        }

    # ── steps ─────────────────────────────────────────────────────────────────
    async def _analyze(self, article: NewsArticle) -> Optional[SentimentAnalysis]:
        try:
            return await self._analyzer.analyze(article.text_for_analysis())
        except Exception as e:  # noqa: BLE001 - one bad article must not abort the run
            logger.error(f"Sentiment analysis failed for {article.article_id}: {e}")
            return None

    def _persist(self, article: NewsArticle, sentiment: SentimentAnalysis) -> bool:
        """Save the article then its sentiment. Returns True when both succeed."""
        if self._db is None:
            return False
        article_pk = self._db.upsert_news_article(article.to_db_row())
        if not article_pk:
            return False
        return self._db.upsert_news_article_sentiment(
            article_pk,
            {
                "overall_sentiment": sentiment.overall_sentiment.value,
                "sentiment_score": sentiment.to_score(),
                "confidence": sentiment.confidence.value,
                "key_drivers": ", ".join(sentiment.key_drivers) or None,
                "tone_descriptors": ", ".join(sentiment.tone_descriptors) or None,
                "analyzer": "news-portal-scraper",
            },
        )

    def _aggregate(self, buckets: Dict[tuple, List[float]]) -> int:
        """Recompute daily per-ticker news aggregates and upsert them. Returns row count.

        combined_score blends with any existing social score so the result is
        independent of whether news or social was collected first (see
        collect_social_sentiment_use_case.blend_scores).
        """
        if self._db is None:
            return 0
        from application.use_cases.collect_social_sentiment_use_case import blend_scores

        count = 0
        for (ticker, day), scores in buckets.items():
            if not scores:
                continue
            news_score = round(sum(scores) / len(scores), 4)

            existing = self._db.get_aggregated_ticker_sentiment(ticker, day) or {}
            social_score = existing.get("social_score")
            combined = blend_scores(news_score, social_score)

            ok = self._db.upsert_aggregated_ticker_sentiment(
                {
                    "ticker": ticker,
                    "period_date": day,
                    "news_score": news_score,
                    "news_count": len(scores),
                    "combined_score": combined,
                }
            )
            if ok:
                count += 1
        return count
