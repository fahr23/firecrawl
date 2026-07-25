"""
Collect YouTube Sentiment Use Case.

Orchestrates the YouTube finance channel sentiment pipeline:
  1. Scrape video transcripts from channel URLs (YouTubeScraper)
  2. Detect all BIST tickers mentioned in each transcript (detect_instruments)
  3. For each (video, ticker) pair: extract the relevant text window, analyse sentiment
  4. Persist video + per-(video, ticker) sentiment rows
  5. Update the youtube_* columns of the daily aggregated_ticker_sentiment rollup
     and recompute combined_score by blending news + social + youtube.

One bad video or one bad ticker must not abort the run (same discipline as
CollectSocialSentimentUseCase). Multi-ticker per transcript is the key difference
from the social use case where every post has exactly one ticker.
"""
from __future__ import annotations

import logging
from collections import defaultdict
from typing import Any, Dict, List, Optional

from domain.entities.youtube_video import YouTubeVideo
from domain.services.sentiment_analyzer_service import ISentimentAnalyzer
from domain.value_objects.sentiment import SentimentAnalysis
from infrastructure.contracts.instrument_identity_map import (
    detect_instruments,
    resolve_name_patterns,
)

logger = logging.getLogger(__name__)


class CollectYouTubeSentimentUseCase:
    """Coordinate scrape → detect → analyse → persist → aggregate for YouTube channels."""

    def __init__(self, scraper, sentiment_analyzer: ISentimentAnalyzer, db_manager):
        self._scraper = scraper
        self._analyzer = sentiment_analyzer
        self._db = db_manager

    async def execute(
        self,
        channel_urls: List[str],
        days_back: int = 7,
        limit_per_channel: int = 50,
    ) -> Dict[str, Any]:
        scrape_result = await self._scraper.scrape_all(
            channel_urls=channel_urls,
            days_back=days_back,
            limit_per_channel=limit_per_channel,
        )
        videos: List[YouTubeVideo] = scrape_result.get("videos", [])

        analyzed = 0
        saved = 0
        # (ticker, date) → list of weighted scores
        buckets: Dict[tuple, List[float]] = defaultdict(list)

        for video in videos:
            tickers = self._detect_tickers(video)
            if not tickers:
                logger.debug(f"No BIST tickers found in {video.video_id}: skipping")
                continue

            video_db_id = self._persist_video(video)
            if video_db_id is None and self._db is not None:
                logger.warning(f"Could not persist video {video.video_id}")

            for ticker in tickers:
                sentiment = await self._analyze_for_ticker(video, ticker)
                if sentiment is None:
                    continue
                analyzed += 1

                if self._persist_sentiment(video_db_id, ticker, sentiment):
                    saved += 1

                day = (video.published_at or video.scraped_at).date()
                buckets[(ticker, day)].append(
                    sentiment.to_score() * sentiment.confidence.value
                )

        aggregated = self._aggregate(buckets)

        return {
            "success": True,
            "scraped": scrape_result.get("total", len(videos)),
            "analyzed": analyzed,
            "saved": saved,
            "aggregated_tickers": aggregated,
            "by_channel": scrape_result.get("by_channel", {}),
        }

    # ── steps ──────────────────────────────────────────────────────────────────

    def _detect_tickers(self, video: YouTubeVideo) -> List[str]:
        try:
            full_text = video.text_for_analysis()
            return detect_instruments(full_text)
        except Exception as e:
            logger.error(f"Instrument detection failed for {video.video_id}: {e}")
            return []

    async def _analyze_for_ticker(
        self, video: YouTubeVideo, ticker: str
    ) -> Optional[SentimentAnalysis]:
        try:
            patterns = resolve_name_patterns(ticker, "bist", self._db)
            text = video.tickers_text_window(patterns)
            return await self._analyzer.analyze(text)
        except Exception as e:  # noqa: BLE001 — one bad (video, ticker) must not abort
            logger.error(
                f"Sentiment analysis failed for {video.video_id}/{ticker}: {e}"
            )
            return None

    def _persist_video(self, video: YouTubeVideo) -> Optional[int]:
        if self._db is None:
            return None
        try:
            return self._db.upsert_youtube_video(video.to_db_row())
        except Exception as e:
            logger.error(f"upsert_youtube_video failed for {video.video_id}: {e}")
            return None

    def _persist_sentiment(
        self,
        video_db_id: Optional[int],
        ticker: str,
        sentiment: SentimentAnalysis,
    ) -> bool:
        if self._db is None or video_db_id is None:
            return False
        try:
            return self._db.upsert_youtube_video_sentiment(
                video_db_id,
                ticker,
                {
                    "overall_sentiment": sentiment.overall_sentiment.value,
                    "sentiment_score": sentiment.to_score(),
                    "confidence": sentiment.confidence.value,
                    "analyzer": "youtube-scraper",
                },
            )
        except Exception as e:
            logger.error(
                f"upsert_youtube_video_sentiment failed for video {video_db_id}/{ticker}: {e}"
            )
            return False

    def _aggregate(self, buckets: Dict[tuple, List[float]]) -> int:
        """Recompute youtube_score per ticker/day and blend with existing news+social."""
        if self._db is None:
            return 0

        from application.use_cases.collect_social_sentiment_use_case import blend_sources

        count = 0
        for (ticker, day), scores in buckets.items():
            if not scores:
                continue
            youtube_score = round(sum(scores) / len(scores), 4)

            existing = self._db.get_aggregated_ticker_sentiment(ticker, day) or {}
            combined = blend_sources({
                "news": existing.get("news_score"),
                "social": existing.get("social_score"),
                "youtube": youtube_score,
            })

            ok = self._db.upsert_aggregated_ticker_sentiment(
                {
                    "ticker": ticker,
                    "period_date": day,
                    "youtube_score": youtube_score,
                    "youtube_count": len(scores),
                    "combined_score": combined,
                }
            )
            if ok:
                count += 1
        return count
