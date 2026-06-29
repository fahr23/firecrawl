"""
Background news collection scheduler — module-level singleton.

Two modes:
  manual   — collection only happens when POST /collect is called explicitly.
  interval — a background asyncio task fires every `interval_minutes`.

Both modes share the same state (last_run, last_result) so the status endpoint
always reflects the most recent collection regardless of how it was triggered.
"""
import asyncio
import logging
import os
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


class NewsScheduler:
    def __init__(self) -> None:
        self.mode: str = "manual"
        self.interval_minutes: int = 30
        self.sources: List[str] = ["bloomberght", "haberturk", "ntv"]
        self.days_back: int = 1
        self.include_investing_comments: bool = False

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
            "sources": self.sources,
            "days_back": self.days_back,
            "include_investing_comments": self.include_investing_comments,
            "is_running": self.is_running,
            "last_run": self.last_run.isoformat() + "Z" if self.last_run else None,
            "next_run": self.next_run.isoformat() + "Z" if self.next_run else None,
            "last_result": self.last_result,
        }

    # ── mode switch ───────────────────────────────────────────────────────────
    def configure(
        self,
        mode: str,
        interval_minutes: int = 30,
        sources: Optional[List[str]] = None,
        days_back: int = 1,
        include_investing_comments: bool = False,
    ) -> None:
        self.mode = mode
        self.interval_minutes = max(5, interval_minutes)
        if sources:
            self.sources = sources
        self.days_back = max(1, days_back)
        self.include_investing_comments = include_investing_comments

        if mode == "interval":
            self._start_loop()
        else:
            self._stop_loop()

    # ── background loop ───────────────────────────────────────────────────────
    def _start_loop(self) -> None:
        if self._task and not self._task.done():
            self._task.cancel()
        self._task = asyncio.create_task(self._loop())
        logger.info(f"NewsScheduler: interval mode — every {self.interval_minutes} min")

    def _stop_loop(self) -> None:
        if self._task and not self._task.done():
            self._task.cancel()
        self._task = None
        self.next_run = None
        logger.info("NewsScheduler: stopped (manual mode)")

    async def _loop(self) -> None:
        while True:
            self.next_run = datetime.utcnow() + timedelta(minutes=self.interval_minutes)
            logger.info(f"NewsScheduler: next run at {self.next_run.isoformat()}Z")
            await asyncio.sleep(self.interval_minutes * 60)
            await self.run_collect()

    # ── collection (shared by both modes) ────────────────────────────────────
    async def run_collect(self) -> Dict[str, Any]:
        """Run the scrape→analyse→persist pipeline. Called by the loop and by POST /collect."""
        if self.is_running:
            logger.warning("NewsScheduler: collect already running, skipping")
            return {"skipped": True, "reason": "already_running"}

        self.is_running = True
        self.last_run = datetime.utcnow()
        try:
            from database.db_manager import DatabaseManager
            from scrapers.news_portal_scraper import NewsPortalScraper
            from application.use_cases.collect_news_sentiment_use_case import CollectNewsSentimentUseCase
            from api.routers.news_sentiment import _build_sentiment_analyzer

            db = DatabaseManager()
            scraper = NewsPortalScraper(db_manager=db)
            analyzer = _build_sentiment_analyzer()
            use_case = CollectNewsSentimentUseCase(scraper, analyzer, db)
            result = await use_case.execute(
                days_back=self.days_back,
                sources=self.sources,
                include_investing_comments=self.include_investing_comments,
            )
            self.last_result = {**result, "triggered_at": self.last_run.isoformat() + "Z"}
            logger.info(
                f"NewsScheduler: done — scraped={result.get('scraped',0)} "
                f"saved={result.get('saved',0)} analyzed={result.get('analyzed',0)}"
            )
            return self.last_result
        except Exception as exc:
            logger.error(f"NewsScheduler: collect failed: {exc}", exc_info=True)
            self.last_result = {"error": str(exc), "triggered_at": self.last_run.isoformat() + "Z"}
            return self.last_result
        finally:
            self.is_running = False

    def shutdown(self) -> None:
        self._stop_loop()


# ── module-level singleton ────────────────────────────────────────────────────
scheduler = NewsScheduler()
