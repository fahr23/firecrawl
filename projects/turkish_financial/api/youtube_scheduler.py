"""
Background YouTube collection scheduler — module-level singleton.

Mirrors api/news_scheduler.py but targets YouTube channels instead of news portals.

Two modes:
  manual   — collection only happens when POST /youtube-sentiment/collect is called.
  interval — a background asyncio task fires every `interval_minutes`.
"""
import asyncio
import logging
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


class YouTubeScheduler:
    def __init__(self) -> None:
        self.mode: str = "manual"
        self.interval_minutes: int = 60
        self.channels: List[str] = []  # populated from config at first use
        self.days_back: int = 7
        self.limit_per_channel: int = 50

        self.last_run: Optional[datetime] = None
        self.next_run: Optional[datetime] = None
        self.last_result: Optional[Dict[str, Any]] = None
        self.is_running: bool = False

        self._task: Optional[asyncio.Task] = None

    # ── public status ─────────────────────────────────────────────────────────
    def status(self) -> Dict[str, Any]:
        return {
            "mode": self.mode,
            "interval_minutes": self.interval_minutes,
            "channels": self.channels,
            "days_back": self.days_back,
            "limit_per_channel": self.limit_per_channel,
            "is_running": self.is_running,
            "last_run": self.last_run.isoformat() + "Z" if self.last_run else None,
            "next_run": self.next_run.isoformat() + "Z" if self.next_run else None,
            "last_result": self.last_result,
        }

    # ── mode switch ───────────────────────────────────────────────────────────
    def configure(
        self,
        mode: str,
        interval_minutes: int = 60,
        channels: Optional[List[str]] = None,
        days_back: int = 7,
        limit_per_channel: int = 50,
    ) -> None:
        self.mode = mode
        self.interval_minutes = max(5, interval_minutes)
        if channels:
            self.channels = channels
        self.days_back = max(1, days_back)
        self.limit_per_channel = max(1, limit_per_channel)

        if mode == "interval":
            self._start_loop()
        else:
            self._stop_loop()

    def _seed_channels_from_config(self) -> None:
        """Lazy-load seed channels from config when the list is still empty."""
        if self.channels:
            return
        try:
            from config import config as app_config
            self.channels = list(app_config.youtube.channels)
        except Exception:
            pass

    # ── background loop ───────────────────────────────────────────────────────
    def _start_loop(self) -> None:
        if self._task and not self._task.done():
            self._task.cancel()
        self._task = asyncio.create_task(self._loop())
        logger.info(f"YouTubeScheduler: interval mode — every {self.interval_minutes} min")

    def _stop_loop(self) -> None:
        if self._task and not self._task.done():
            self._task.cancel()
        self._task = None
        self.next_run = None
        logger.info("YouTubeScheduler: stopped (manual mode)")

    async def _loop(self) -> None:
        while True:
            self.next_run = datetime.utcnow() + timedelta(minutes=self.interval_minutes)
            logger.info(f"YouTubeScheduler: next run at {self.next_run.isoformat()}Z")
            await asyncio.sleep(self.interval_minutes * 60)
            await self.run_collect()

    # ── collection ────────────────────────────────────────────────────────────
    async def run_collect(self) -> Dict[str, Any]:
        """Run the scrape→analyse→persist pipeline."""
        if self.is_running:
            logger.warning("YouTubeScheduler: collect already running, skipping")
            return {"skipped": True, "reason": "already_running"}

        self._seed_channels_from_config()

        self.is_running = True
        self.last_run = datetime.utcnow()
        try:
            from database.db_manager import DatabaseManager
            from scrapers.youtube_scraper import YouTubeScraper
            from application.use_cases.collect_youtube_sentiment_use_case import (
                CollectYouTubeSentimentUseCase,
            )
            from api.routers.news_sentiment import _build_sentiment_analyzer

            db = DatabaseManager()
            scraper = YouTubeScraper(db_manager=db)
            analyzer = _build_sentiment_analyzer()
            use_case = CollectYouTubeSentimentUseCase(scraper, analyzer, db)
            result = await use_case.execute(
                channel_urls=self.channels,
                days_back=self.days_back,
                limit_per_channel=self.limit_per_channel,
            )
            self.last_result = {**result, "triggered_at": self.last_run.isoformat() + "Z"}
            logger.info(
                f"YouTubeScheduler: done — scraped={result.get('scraped', 0)} "
                f"saved={result.get('saved', 0)} analyzed={result.get('analyzed', 0)}"
            )
            return self.last_result
        except Exception as exc:
            logger.error(f"YouTubeScheduler: collect failed: {exc}", exc_info=True)
            self.last_result = {"error": str(exc), "triggered_at": self.last_run.isoformat() + "Z"}
            return self.last_result
        finally:
            self.is_running = False

    def shutdown(self) -> None:
        self._stop_loop()


# ── module-level singleton ────────────────────────────────────────────────────
scheduler = YouTubeScheduler()
