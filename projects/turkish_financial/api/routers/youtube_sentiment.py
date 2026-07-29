"""
YouTube channel sentiment — Data Contract v1.0 HTTP surface.

Exposes sentiment derived from Turkish finance YouTube channels, aggregated daily per
BIST ticker. Same envelope shape (§1/§2) as the KAP/news/social sentiment endpoints,
but `provider = "youtube-scraper"`.

    POST {base}/youtube-sentiment/collect          trigger a scrape+analyse+aggregate run
    GET  {base}/youtube-sentiment/schedule         get scheduler status
    POST {base}/youtube-sentiment/schedule         configure scheduler mode/interval
    GET  {base}/youtube-sentiment/{instrument}     latest point
    GET  {base}/youtube-sentiment/{instrument}/history

Mounted at `/api/external/v1` (see api/main.py).
"""
import logging
from typing import List, Optional

from fastapi import APIRouter, Depends, Query
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from api.dependencies import get_db_manager
from database.db_manager import DatabaseManager
from domain.entities.external_analysis import CONTRACT_VERSION, Market
from infrastructure.repositories.news_article_repository import YouTubeSentimentRepository
from api.routers.news_sentiment import _build_sentiment_analyzer, _serve_point, _serve_history

logger = logging.getLogger(__name__)

router = APIRouter(tags=["youtube-sentiment"])


def _db_error(detail: str) -> JSONResponse:
    return JSONResponse(
        status_code=503,
        content={
            "contract_version": CONTRACT_VERSION,
            "status": "unavailable",
            "error_code": "UPSTREAM_DB_ERROR",
            "detail": detail,
        },
    )


def _repo(db_manager: DatabaseManager) -> YouTubeSentimentRepository:
    return YouTubeSentimentRepository(db_manager)


# ── Pydantic models ───────────────────────────────────────────────────────────

class YouTubeCollectRequest(BaseModel):
    channels: Optional[List[str]] = Field(
        default=None,
        description="Channel URLs to scrape. Defaults to the config seed list when omitted.",
    )
    days_back: int = Field(default=7, ge=1, le=90)
    limit_per_channel: int = Field(default=50, ge=1, le=200)
    stored_only: bool = Field(
        default=False,
        description="Analyse cached local Whisper/caption transcripts without contacting YouTube.",
    )


class YouTubeScheduleConfigRequest(BaseModel):
    mode: str = Field(..., pattern="^(manual|interval)$")
    interval_minutes: int = Field(default=60, ge=5, le=1440)
    channels: Optional[List[str]] = None
    days_back: int = Field(default=7, ge=1, le=30)
    limit_per_channel: int = Field(default=50, ge=1, le=200)


# ── schedule ──────────────────────────────────────────────────────────────────

@router.get("/youtube-sentiment/schedule")
async def get_youtube_schedule():
    """Return the current YouTube collection schedule and configured channels."""
    from api.youtube_scheduler import scheduler
    # Status is also used by the UI and operations checks.  Seed here so a
    # read-only request accurately reports configured defaults before the
    # first collection run.
    scheduler._seed_channels_from_config()
    return {"contract_version": CONTRACT_VERSION, **scheduler.status()}


@router.post("/youtube-sentiment/schedule")
async def set_youtube_schedule(request: YouTubeScheduleConfigRequest):
    """Switch between manual and interval collection modes for YouTube channels."""
    from api.youtube_scheduler import scheduler
    scheduler.configure(
        mode=request.mode,
        interval_minutes=request.interval_minutes,
        channels=request.channels,
        days_back=request.days_back,
        limit_per_channel=request.limit_per_channel,
    )
    return {
        "contract_version": CONTRACT_VERSION,
        "ok": True,
        "message": (
            f"Scheduler set to interval mode — runs every {request.interval_minutes} min"
            if request.mode == "interval"
            else "Scheduler set to manual mode"
        ),
        **scheduler.status(),
    }


# ── collect trigger ───────────────────────────────────────────────────────────

@router.post("/youtube-sentiment/collect")
async def youtube_sentiment_collect(
    request: YouTubeCollectRequest,
    db_manager: DatabaseManager = Depends(get_db_manager),
):
    """
    Trigger one YouTube sentiment collection run.

    When `channels` is omitted the config seed list is used (set via YOUTUBE_CHANNELS
    env var or POST /youtube-sentiment/schedule).
    """
    from api.youtube_scheduler import scheduler
    from scrapers.youtube_scraper import YouTubeScraper
    from application.use_cases.collect_youtube_sentiment_use_case import (
        CollectYouTubeSentimentUseCase,
    )

    channels = request.channels or scheduler.channels
    if not channels:
        # lazy-load from config
        scheduler._seed_channels_from_config()
        channels = scheduler.channels

    try:
        scraper = YouTubeScraper(db_manager=db_manager)
        analyzer = _build_sentiment_analyzer()
        use_case = CollectYouTubeSentimentUseCase(scraper, analyzer, db_manager)

        scheduler.is_running = True
        from datetime import datetime
        scheduler.last_run = datetime.utcnow()
        try:
            result = await use_case.execute(
                channel_urls=channels,
                days_back=request.days_back,
                limit_per_channel=request.limit_per_channel,
                stored_only=request.stored_only,
            )
        finally:
            scheduler.is_running = False

        scheduler.last_result = {**result, "triggered_at": scheduler.last_run.isoformat() + "Z"}
        return {"contract_version": CONTRACT_VERSION, **result}

    except DatabaseManager.PoolExhaustedError:
        return _db_error("database temporarily unavailable")
    except Exception as e:  # noqa: BLE001
        logger.error(f"YouTube sentiment collect failed: {e}", exc_info=True)
        return JSONResponse(
            status_code=500,
            content={"contract_version": CONTRACT_VERSION, "status": "error", "detail": str(e)},
        )


# ── read endpoints ────────────────────────────────────────────────────────────

@router.get("/youtube-sentiment/{instrument}/history")
async def youtube_sentiment_history(
    instrument: str,
    market: Market = Query(...),
    date_from: Optional[str] = Query(None, alias="from"),
    date_to: Optional[str] = Query(None, alias="to"),
    limit: int = Query(100, ge=1, le=1000),
    cursor: Optional[str] = Query(None),
    db_manager: DatabaseManager = Depends(get_db_manager),
):
    return _serve_history(
        _repo(db_manager), instrument, market, date_from, date_to, limit, cursor,
    )


@router.get("/youtube-sentiment/{instrument}")
async def youtube_sentiment_point(
    instrument: str,
    market: Market = Query(...),
    as_of: Optional[str] = Query(None),
    db_manager: DatabaseManager = Depends(get_db_manager),
):
    return _serve_point(_repo(db_manager), instrument, market, as_of)
