"""Schedules, editions, and trend suggestions for daily academic reading."""

import asyncio
from datetime import date
import logging
from typing import Optional
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from fastapi import APIRouter, Depends, HTTPException, Response
from fastapi.concurrency import run_in_threadpool
from pydantic import BaseModel, Field, field_validator

from . import daily_store, discovery


logger = logging.getLogger(__name__)
PAPER_SCAN_LIMIT = 75


class DailySettings(BaseModel):
    q: str = Field(min_length=2, max_length=300)
    providers: str = Field(default="openalex", min_length=1, max_length=250)
    start_on: date
    local_time: str = Field(default="08:00", pattern=r"^(?:[01][0-9]|2[0-3]):[0-5][0-9]$")
    timezone: str = Field(default="UTC", max_length=120)
    papers_per_day: int = Field(default=3, ge=1, le=10)
    enabled: bool = True

    @field_validator("timezone")
    @classmethod
    def valid_zone(cls, value):
        try:
            ZoneInfo(value)
        except (ValueError, ZoneInfoNotFoundError):
            raise ValueError("Use an IANA time zone such as Europe/Istanbul.") from None
        return value

    @field_validator("start_on")
    @classmethod
    def valid_start(cls, value):
        if not 1900 <= value.year <= 2200:
            raise ValueError("Enter a start date between 1900 and 2200.")
        return value


def _reading_candidates(papers, day):
    eligible = []
    for paper in papers:
        if paper.get("is_retracted") is True:
            continue
        try:
            published = date.fromisoformat(paper.get("publication_date") or "")
        except (ValueError, TypeError):
            published = None
        try:
            year = int(paper.get("year") or 0)
        except (TypeError, ValueError):
            year = 0
        if (published and published > day) or (not published and year > day.year):
            continue
        eligible.append(((published.year if published else year, published or date.min), paper))
    return [paper for _, paper in sorted(eligible, key=lambda item: item[0], reverse=True)]


async def build_edition(store, project_id, get_engine, get_openalex, fetch_literature, *, manual=False):
    run = await run_in_threadpool(store.daily.claim, project_id, daily_store.clock(), manual=manual)
    if not run:
        return
    settings = run["settings"]
    day = date.fromisoformat(run["day"])
    query, providers = settings["q"], settings["provider_names"]

    async def papers():
        if not run["need_papers"]:
            return None
        return await fetch_literature(
            store, get_engine(), query, "all", providers, None, None, 1, PAPER_SCAN_LIMIT, for_watch=True,
        )

    async def topics():
        if not run["need_trend"]:
            return None
        return await run_in_threadpool(discovery.daily_trends, get_openalex(), query, day)

    try:
        search, trend = await asyncio.gather(papers(), topics(), return_exceptions=True)
        if isinstance(search, BaseException):
            logger.warning("Daily paper check failed (%s)", type(search).__name__)
            search = {"results": [], "provider_coverage": [
                {"provider": name, "status": "failed", "error_code": "daily_provider_error"} for name in providers
            ]}
        if isinstance(trend, BaseException):
            logger.warning("Daily trend check failed (%s)", type(trend).__name__)
            trend = {"provider": "OpenAlex", "topics": [], "periods": [],
                     "errors": {"check": {"code": "daily_provider_error"}}}
        saved = []
        live = search["results"] if search else []
        if run["need_papers"]:
            saved = await run_in_threadpool(
                store.literature.search, query, "all", providers, None, day.year, PAPER_SCAN_LIMIT, 0, for_daily=True,
            )
        await run_in_threadpool(
            store.daily.finish, project_id, run, _reading_candidates(live, day), _reading_candidates(saved, day),
            search["provider_coverage"] if search is not None else None, trend, daily_store.clock(),
        )
    finally:
        await run_in_threadpool(store.daily.release, project_id, run["day"], run["token"])


async def daily_scheduler(store, get_engine, get_openalex, fetch_literature):
    while True:
        await asyncio.sleep(30)
        projects = await run_in_threadpool(store.daily.due)
        for project_id in projects:
            try:
                await build_edition(store, project_id, get_engine, get_openalex, fetch_literature)
            except Exception:
                logger.exception("Daily research edition could not complete")


def daily_router(get_store, get_engine, get_openalex, parse_filters, fetch_literature):
    router = APIRouter(prefix="/api/v1", tags=["Daily research"])

    def project_store(project_id: str, store=Depends(get_store)):
        if not store.get_project(project_id):
            raise HTTPException(404, "Research topic not found")
        return store

    @router.get("/daily-reading")
    def overview(response: Response, store=Depends(get_store)):
        response.headers["Cache-Control"] = "no-store"
        return {"items": store.daily.overview()}

    @router.get("/projects/{project_id}/daily-reading")
    def get_edition(project_id: str, response: Response, day: Optional[date] = None, store=Depends(project_store)):
        response.headers["Cache-Control"] = "no-store"
        return store.daily.view(project_id, day.isoformat() if day else None)

    @router.put("/projects/{project_id}/daily-reading")
    def save_settings(project_id: str, settings: DailySettings, store=Depends(project_store)):
        query, providers = parse_filters(settings.q, "all", settings.providers, None, None)
        if not providers:
            raise HTTPException(422, "Select at least one source for daily papers.")
        data = settings.model_dump(mode="json")
        data.update(q=query, provider_names=list(dict.fromkeys(providers)))
        store.daily.save_settings(project_id, data)
        return store.daily.view(project_id)

    @router.post("/projects/{project_id}/daily-reading/check")
    async def check(project_id: str, store=Depends(project_store), engine=Depends(get_engine), searcher=Depends(get_openalex)):
        current = await run_in_threadpool(store.daily.view, project_id)
        if not current["settings"]:
            raise HTTPException(422, "Save a daily reading schedule first.")
        if current["today"] < current["settings"]["start_on"]:
            raise HTTPException(409, "This reading schedule starts on a later date.")
        await build_edition(store, project_id, lambda: engine, lambda: searcher, fetch_literature, manual=True)
        return await run_in_threadpool(store.daily.view, project_id)

    return router
