"""Reading activity, saved searches, and shared portfolio HTTP routes."""

import asyncio
import logging
from typing import Literal, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from .workspace_models import DossierActivity


logger = logging.getLogger(__name__)


class WatchSettings(BaseModel):
    label: str = Field(default="", max_length=120)
    interval_hours: Literal[0, 24, 168] = 0


class WatchCreate(WatchSettings):
    q: str = Field(min_length=2, max_length=300)
    category: str = Field(default="all", max_length=120)
    providers: Optional[str] = Field(default=None, max_length=250)
    year_min: Optional[int] = Field(default=None, ge=1800, le=2200)
    year_max: Optional[int] = Field(default=None, ge=1800, le=2200)
    limit: int = Field(default=20, ge=1, le=50)


class PaperRef(BaseModel):
    url: str = Field(min_length=8, max_length=4000)
    doi: Optional[str] = Field(default=None, max_length=4000)


class PaperBatch(BaseModel):
    papers: list[PaperRef] = Field(max_length=100)


class PaperOpen(PaperRef):
    event_id: UUID


class PaperRead(PaperRef):
    read: bool


class Seen(BaseModel):
    library_id: Optional[int] = Field(default=None, ge=1)


class SharedActivity(DossierActivity):
    reading_id: Literal[""] = ""


async def refresh_watch(store, engine, project_id, watch_id, fetch_search):
    workflow = store.workflow
    watch = workflow.watch(project_id, watch_id)
    if not watch:
        raise HTTPException(404, "Saved search not found")
    token = workflow.claim_watch(project_id, watch_id)
    if not token:
        raise HTTPException(409, "This search is already being checked")
    payload = None
    try:
        f = watch["filters"]
        payload = await fetch_search(
            store, engine, f["q"], f["category"], f["provider_names"], f["year_min"], f["year_max"],
            1, 50, for_watch=True,
        )
    finally:
        coverage = payload["provider_coverage"] if payload else [{"provider": "Search", "status": "failed"}]
        added = workflow.finish_watch(
            watch_id, token, payload["results"] if payload else [], coverage,
            bool(payload and not payload["pagination"]["partial"]),
            payload["new_work_ids"] if payload else (),
        )
    return {"added": added, "watch": workflow.watch(project_id, watch_id)}


async def watch_scheduler(store, get_engine, fetch_search):
    while True:
        await asyncio.sleep(30)
        for project_id, watch_id in store.workflow.due():
            try:
                await refresh_watch(store, get_engine(), project_id, watch_id, fetch_search)
            except HTTPException as error:
                if error.status_code not in (404, 409):
                    logger.warning("Scheduled academic search could not complete (%s)", error.status_code)
            except Exception:
                logger.exception("Scheduled academic search could not complete")


def workflow_router(get_store, get_engine, filters, fetch_search):
    router = APIRouter(prefix="/api/v1", tags=["Research workflow"])

    def in_project(project_id: str, store=Depends(get_store)):
        if not store.get_project(project_id):
            raise HTTPException(404, "Research topic not found")
        return store

    def paper_id(store, ref):
        known = store.workflow.identify_paper(ref.url, ref.doi)
        if not known:
            raise HTTPException(404, "Paper is unavailable in the local library")
        return known

    @router.get("/watches")
    def list_watches(project_id: Optional[str] = None, store=Depends(get_store)):
        return {"items": store.workflow.watches(project_id), "unread_by_topic": store.workflow.unread_counts()}

    @router.post("/projects/{project_id}/watches", status_code=201)
    def save_watch(project_id: str, request: WatchCreate, store=Depends(in_project)):
        query, providers = filters(request.q, request.category, request.providers, request.year_min, request.year_max)
        signature = store.literature.signature(query, request.category, providers, request.year_min, request.year_max)
        baseline = store.literature.cached_page(signature, 1, request.limit) or {}
        return store.workflow.save_watch(
            project_id, signature, request.label.strip() or query,
            {"q": query, "category": request.category, "provider_names": providers,
             "year_min": request.year_min, "year_max": request.year_max},
            request.interval_hours, baseline.get("results", []),
        )

    @router.patch("/projects/{project_id}/watches/{watch_id}")
    def configure(project_id: str, watch_id: str, request: WatchSettings, store=Depends(in_project)):
        current = store.workflow.watch(project_id, watch_id)
        if not current:
            raise HTTPException(404, "Saved search not found")
        return store.workflow.configure_watch(
            project_id, watch_id, request.label.strip() or current["filters"]["q"], request.interval_hours,
        )

    @router.delete("/projects/{project_id}/watches/{watch_id}")
    def remove_watch(project_id: str, watch_id: str, store=Depends(in_project)):
        if not store.workflow.delete_watch(project_id, watch_id):
            raise HTTPException(404, "Saved search not found")
        return {"removed": True}

    @router.post("/projects/{project_id}/watches/{watch_id}/refresh")
    async def check(project_id: str, watch_id: str, store=Depends(in_project), engine=Depends(get_engine)):
        return await refresh_watch(store, engine, project_id, watch_id, fetch_search)

    @router.post("/projects/{project_id}/watches/{watch_id}/seen")
    def mark_seen(project_id: str, watch_id: str, request: Seen, store=Depends(in_project)):
        if not store.workflow.watch(project_id, watch_id):
            raise HTTPException(404, "Saved search not found")
        return {"marked": store.workflow.mark_seen(project_id, watch_id, request.library_id)}

    @router.get("/inbox")
    def inbox(project_id: Optional[str] = None, unread_only: bool = False,
              limit: int = Query(75, ge=1, le=100), store=Depends(get_store)):
        return {"items": store.workflow.inbox(project_id, limit, unread_only)}

    @router.post("/library/activity/lookup")
    def lookup(request: PaperBatch, store=Depends(get_store)):
        items = []
        for ref in request.papers:
            work_id = store.workflow.identify_paper(ref.url, ref.doi)
            items.append(store.workflow.paper_state(work_id) if work_id else None)
        return {"items": items}

    @router.post("/library/activity/open")
    def open_paper(request: PaperOpen, store=Depends(get_store)):
        return store.workflow.open_paper(paper_id(store, request), request.url, str(request.event_id))

    @router.post("/library/activity/read")
    def mark_read(request: PaperRead, store=Depends(get_store)):
        return store.workflow.mark_read(paper_id(store, request), request.read)

    @router.get("/library/activity")
    def history(limit: int = Query(30, ge=1, le=100), offset: int = Query(0, ge=0),
                q: str = Query("", max_length=4000), store=Depends(get_store)):
        return {"items": store.workflow.reading_history(limit, offset, q)}

    @router.get("/portfolio/activities")
    def portfolio(store=Depends(get_store)):
        return {"items": store.workflow.portfolio()}

    @router.post("/portfolio/activities", status_code=201)
    def add_activity(request: SharedActivity, store=Depends(get_store)):
        return store.workflow.save_activity(request.model_dump(mode="json"))

    @router.put("/portfolio/activities/{item_id}")
    def edit_activity(item_id: str, request: SharedActivity, revision: int = Query(ge=1), store=Depends(get_store)):
        current = store.workflow.portfolio_item(item_id)
        if not current:
            raise HTTPException(404, "Portfolio activity not found")
        data = request.model_dump(mode="json")
        if current["data"].get("paper"):
            data["paper"] = current["data"]["paper"]
        result = store.workflow.save_activity(data, item_id, revision)
        if not result:
            raise HTTPException(409, "This activity changed. Reload it before saving.")
        return result

    @router.get("/portfolio/activities/{item_id}/history")
    def history_activity(item_id: str, store=Depends(get_store)):
        if not store.workflow.portfolio_item(item_id):
            raise HTTPException(404, "Portfolio activity not found")
        return {"items": store.workflow.portfolio_history(item_id)}

    return router
