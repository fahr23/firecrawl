"""Workspace overview, publisher calls, and optional evidence-based assistance."""

from datetime import date
import re
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from fastapi.concurrency import run_in_threadpool
from pydantic import BaseModel, Field

from . import special_issues, workspace_assistant
from .project_store import WorkspaceConflict
from .research_workspace import _item, _public_submission, current_draft
from .submission_calendar import calendar_entries
from .workspace_models import SubmissionOpportunity


class SaveCall(BaseModel):
    project_id: str = Field(min_length=1, max_length=90)
    draft_id: str = Field(default="", max_length=90)

class VerifyCall(BaseModel):
    url: str = Field(min_length=10, max_length=1500)


def _evidence(store, project_id, settings):
    records = []
    drafts = _item(store, project_id, "manuscripts", settings.draft_id) if settings.draft_id else None
    idea = _item(store, project_id, "ideas", settings.idea_id) if settings.idea_id else None
    call = store.publishing.get_call(settings.call_id) if settings.call_id else None
    if settings.call_id and not call:
        raise HTTPException(404, "Special issue not found.")
    if settings.action == "draft" and not drafts:
        raise HTTPException(422, "Open a saved manuscript first.")
    if settings.action == "call" and (not call or not (drafts or idea)):
        raise HTTPException(422, "Choose a saved manuscript or research brief to compare with the call.")
    if settings.reading_ids:
        reading = [_item(store, project_id, "reading", key) for key in dict.fromkeys(settings.reading_ids)]
    elif drafts:
        from .workspace_reports import draft_reference_ids

        ids = draft_reference_ids(current_draft(store, drafts))
        reading = [_item(store, project_id, "reading", key, False) for key in ids[:8]]
    elif idea:
        ids = list(dict.fromkeys(idea["data"]["evidence"] + idea["data"]["counterevidence"]))
        reading = [_item(store, project_id, "reading", key, False) for key in ids[:8]]
    else:
        reading = store.workspace_items(project_id, "reading", 8)
    for row in filter(None, reading):
        paper, notes = row["data"]["paper"], row["data"]["notes"]
        records.append({"id": f"P{len(records) + 1}", "title": paper["title"], "url": paper["url"],
                        "abstract": (paper.get("abstract") or "")[:1800],
                        "researcher_notes": {key: str(notes.get(key) or "")[:450] for key in (
                            "method", "findings", "limitations", "locator", "dataset",
                        )}})
    if settings.action == "evidence" and not records:
        raise HTTPException(422, "Save papers to this topic’s reading shortlist before asking for a comparison.")
    if idea:
        data = idea["data"]
        records.append({"id": "B1", "title": data["question"],
                        "research_brief": {key: data.get(key) for key in ("method", "data_source", "data_access", "constraints")}})
    if drafts:
        data = current_draft(store, drafts)
        sections = data["sections"]
        if settings.action == "call":
            sections = [section for section in sections if section["heading"].casefold() == "abstract"]
        records.append({"id": "D1", "title": data["title"], "article_type": data["article_type"],
                        "saved_sections": [{"heading": s["heading"], "text": s["text"][:1800]} for s in sections[:10]],
                        "requirements": data.get("requirements", {})})
    if call:
        records.append({"id": "C1", "title": call["title"], "url": call["source_url"],
                        **{key: call.get(key) for key in ("venue", "scope", "deadline", "evidence", "article_types", "checked_at")}})
    return records


def router_for_publishing(get_store, get_openalex):
    router = APIRouter(prefix="/api/v1", tags=["Academic assistant workspace"])

    @router.get("/today")
    def today(response: Response, store=Depends(get_store)):
        response.headers["Cache-Control"] = "no-store"
        manuscripts = []
        for entry in store.all_workspace_items("manuscripts"):
            draft = current_draft(store, entry)
            if draft.get("stage") == "published":
                continue
            blank = next((section["heading"] for section in draft["sections"] if not section["text"].strip()), "")
            manuscripts.append({
                **{key: entry[key] for key in ("id", "project_id", "project_name", "updated_at")},
                "title": draft["title"], "stage": draft.get("stage", "outline"), "due": draft.get("action_due"),
                "next_action": draft.get("next_action") or (f"Draft {blank.lower()}" if blank else "Review claims and citations"),
            })
        schedule = calendar_entries(store, lambda entry: _public_submission(entry, store))
        followed = [{"id": item["id"], "name": item["journal"]["display_name"], "unread": item["unread"]}
                    for item in store.journal_favorites.all()]
        return {"manuscripts": sorted(manuscripts, key=lambda row: (not row["due"], row["due"] or "")),
                "reading": store.daily.overview(), "deadlines": [item for item in schedule if item["days_left"] <= 30],
                "unread_by_topic": store.workflow.unread_counts(), "alerts": store.publishing.alerts(),
                "followed_journals": followed}

    @router.get("/special-issues")
    def find_special_issues(q: str = Query("", max_length=160), journal: str = Query("", max_length=160),
                            deadline_from: Optional[date] = None, deadline_to: Optional[date] = None,
                            open_only: bool = True, publisher: Optional[str] = None, refresh: bool = False,
                            store=Depends(get_store), openalex=Depends(get_openalex)):
        earliest = deadline_from.isoformat() if deadline_from else None
        latest = deadline_to.isoformat() if deadline_to else None
        if earliest and latest and earliest > latest:
            raise HTTPException(422, "Choose a deadline end date on or after the start date.")
        if publisher and publisher not in special_issues.PUBLISHERS:
            raise HTTPException(422, "Choose a supported publisher.")
        journal = journal.strip()
        if re.fullmatch(r"\d{4}-?\d{3}[0-9Xx]", journal):
            resolved = openalex.resolve_journal_by_issn(journal) or {}
            journal = resolved.get("display_name") or journal
        return special_issues.search(store, q.strip(), journal, earliest, latest, open_only,
                                     [publisher] if publisher else list(special_issues.PUBLISHERS), refresh, openalex)

    @router.post("/special-issues/verify")
    def verify_special_issue(payload: VerifyCall, store=Depends(get_store)):
        row = special_issues.verify_url(store, payload.url.strip())
        if not row:
            raise HTTPException(422, "The public call could not be verified. Open the publisher page to check it.")
        return row

    @router.post("/special-issues/{call_id}/save", status_code=201)
    def save_special_issue(call_id: str, payload: SaveCall, store=Depends(get_store)):
        project_id = payload.project_id
        if not store.get_project(project_id):
            raise HTTPException(404, "Research topic not found.")
        call = store.publishing.get_call(call_id)
        if not call:
            raise HTTPException(404, "Special issue not found.")
        if payload.draft_id:
            _item(store, project_id, "manuscripts", payload.draft_id)
        item_id = f"call-{call_id}"
        current = _item(store, project_id, "submissions", item_id, False)
        if not current:
            fields = {key: value for key, value in call.items() if key in SubmissionOpportunity.model_fields and value}
            fields["kind"] = "special_issue"
            fields["status"] = fields.get("status", "unverified") if fields.get("evidence") else "unverified"
            data = SubmissionOpportunity.model_validate(fields).model_dump(mode="json")
            data.update(checked_at=call["checked_at"], verification="publisher_page", verification_error="")
            try:
                current = store.put_workspace_item(project_id, "submissions", data, item_id)
            except WorkspaceConflict:
                current = _item(store, project_id, "submissions", item_id)
        store.publishing.watch(project_id, item_id, call_id)
        if payload.draft_id:
            # Serialize with other draft writes. Carry forward the current
            # server autosave before creating the new target-linked version.
            with store._lock:
                draft = _item(store, project_id, "manuscripts", payload.draft_id)
                data = current_draft(store, draft)
                if data["submission_id"] != item_id:
                    store.put_workspace_item(project_id, "manuscripts", {**data, "submission_id": item_id},
                                             draft["id"], draft["revision"])
        return _public_submission(current, store)

    @router.get("/special-issue-alerts")
    def alerts(project_id: Optional[str] = None, store=Depends(get_store)):
        return {"items": store.publishing.alerts(project_id)}

    @router.post("/special-issue-alerts/{alert_id}/dismiss")
    def dismiss(alert_id: int, store=Depends(get_store)):
        if not store.publishing.dismiss(alert_id):
            raise HTTPException(404, "Alert not found.")
        return {"dismissed": True}

    @router.get("/assistant/providers")
    def model_providers():
        return {"items": workspace_assistant.providers()}

    @router.post("/projects/{project_id}/assistant")
    async def ask(project_id: str, settings: workspace_assistant.AssistantRequest, store=Depends(get_store)):
        project = store.get_project(project_id)
        if not project:
            raise HTTPException(404, "Research topic not found.")
        # This is the only model-call route. The client invokes it after the user
        # selects a provider and submits an explicit assistant action.
        records = await run_in_threadpool(_evidence, store, project_id, settings)
        topic = {key: project[key] for key in ("name", "research_question")}
        return await run_in_threadpool(workspace_assistant.suggest, settings, topic, records)

    return router
