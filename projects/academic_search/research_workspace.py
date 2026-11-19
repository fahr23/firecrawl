"""Project-scoped discovery, reading, submission, writing, and dossier API."""

from datetime import date, datetime, time, timedelta, timezone
from hashlib import sha256
from typing import Any, Dict, Literal, Optional
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import Response
from pydantic import BaseModel, Field, ValidationError

from . import discovery, submission_sources
from .project_store import ProjectStore, WorkspaceConflict
from .submission_calendar import calendar_entries, calendar_export
from .workspace_models import (
    DiscoveryRequest, DossierActivity, DossierProfile, DossierRule, Manuscript,
    ReadingNotes, ReadingSource, ResearchIdea, SubmissionOpportunity, SubmissionTracking,
)
from .workspace_reports import (
    OUTLINES, dossier_export, draft_export, draft_reference_ids, reference_export, review_manuscript, word_export,
)


Section = Literal["reading", "ideas", "submissions", "manuscripts", "dossier-profile",
                  "dossier-activities", "dossier-rules", "discovery", "submission-tracking"]
_MODELS = {
    "ideas": ResearchIdea, "submissions": SubmissionOpportunity, "manuscripts": Manuscript,
    "dossier-profile": DossierProfile, "dossier-activities": DossierActivity, "dossier-rules": DossierRule,
    "submission-tracking": SubmissionTracking,
}


class WorkspaceWrite(BaseModel):
    revision: int = Field(default=0, ge=0)
    autosave_version: Optional[int] = Field(default=None, ge=0)
    data: Dict[str, Any]


def _item(store, project_id, section, item_id, required=True):
    history = store.workspace_history(project_id, section, item_id, limit=1)
    if history:
        return history[0]
    if required:
        raise HTTPException(404, "Workspace item not found")
    return None


def _write(store, project_id, section, data, item_id=None, revision=0, autosave_version=None):
    try:
        return store.put_workspace_item(project_id, section, data, item_id, revision, autosave_version)
    except WorkspaceConflict as exc:
        raise HTTPException(409, str(exc)) from exc


def _validate(model, data):
    try:
        return model.model_validate(data).model_dump(mode="json")
    except ValidationError as exc:
        errors = exc.errors(include_input=False, include_url=False, include_context=False)
        message = " ".join(
            f'{" / ".join(map(str, error["loc"])) or "Form"} — {error["msg"]}' for error in errors[:3]
        )
        raise HTTPException(422, message) from None


def _reading(store, project_id, ids):
    records = {}
    for key in dict.fromkeys(ids):
        entry = _item(store, project_id, "reading", key, required=False)
        if entry is None:
            raise HTTPException(422, "A selected reference is not on this topic’s reading shortlist.")
        records[key] = entry["data"]
    return records


def _display_status(data):
    status = data["status"]
    now = datetime.now(timezone.utc)
    zone = ZoneInfo(data["timezone"]) if data.get("timezone") else None
    local = now.astimezone(zone) if zone else now
    deadline = data.get("deadline")
    if deadline:
        if zone and data.get("deadline_time"):
            end = datetime.combine(date.fromisoformat(deadline), time.fromisoformat(data["deadline_time"]), tzinfo=zone)
            if local > end:
                return "closed"
        elif deadline < (local if zone else now - timedelta(hours=14)).date().isoformat():
            return "closed"
    if data.get("opens") and data["opens"] > local.date().isoformat() and status != "closed":
        return "upcoming"
    return status


def _public_submission(entry, store=None):
    data = entry["data"]
    call = store.publishing.watched_call(entry["project_id"], entry["id"]) if store else None
    if call:
        if call["deadline"] != (data.get("deadline") or ""):
            data = {**data, "deadline_time": "", "timezone": ""}
        data = {**data, **{key: call[key] for key in ("status", "deadline", "checked_at", "evidence")
                           if key in call}}
        data["verification"] = "publisher_page"
        entry = {**entry, "data": data, "call_id": call["id"]}
    checked_at = data.get("checked_at")
    needs_recheck = bool(checked_at and data["status"] in {"open", "upcoming"} and
                         datetime.now(timezone.utc) - datetime.fromisoformat(checked_at) >= timedelta(days=7))
    return {**entry, "display_status": _display_status(data), "needs_recheck": needs_recheck}


def _apply_publisher_check(data, notice):
    updated = {**data}
    for key in ("venue", "submission_url", "guidelines_url", "issn", "article_types", "scope", "fees", "fees_url"):
        if notice.get(key) and not updated.get(key):
            updated[key] = notice[key]
    if notice.get("deadline") and notice["deadline"] != updated.get("deadline"):
        updated.update(deadline=notice["deadline"], deadline_time="", timezone="")
    if updated.get("opens") and updated.get("deadline") and updated["opens"] > updated["deadline"]:
        updated["opens"] = None
    updated.update(status=notice["status"], evidence=notice.get("evidence", ""),
                   verification=notice["verification"], checked_at=notice["checked_at"],
                   verification_error=notice.get("error", ""))
    return updated


def _load_origin(store, project_id, selection):
    if selection.kind == "library":
        paper = store.literature.paper(selection.run_id, selection.paper_url)
        snapshot = {"papers": [paper], "retrieved_at": paper["library_observed_at"]} if paper else {}
        return snapshot, "papers"
    if selection.kind == "search":
        run = store.get_search(project_id, selection.run_id)
        return run or {}, "results"
    if selection.kind == "journal":
        run = store.get_journal_search(selection.run_id)
        return (run if run and run["project_id"] == project_id else {}), "papers"
    entry = _item(store, project_id, selection.kind, selection.run_id, required=False)
    return ((entry or {}).get("data", {}), "results" if selection.kind == "search-page" else "papers")


def _active_dossier_profile(store, project_id):
    profile = _item(store, project_id, "dossier-profile", "target", required=False)
    if not profile:
        raise HTTPException(422, "Save the application target first.")
    return profile


def _dossier_status(store, project_id, rule):
    if rule["status"] != "reviewed":
        return rule["status"]
    reviewed = rule.get("activity_revisions", {})
    for key in rule["activity_ids"]:
        entry = _item(store, project_id, "dossier-activities", key)
        if reviewed.get(key) != entry["revision"]:
            return "in_review"
    shared = rule.get("portfolio_revisions", {})
    for key in rule.get("portfolio_activity_ids", []):
        entry = store.workflow.portfolio_item(key)
        if not entry or shared.get(key) != entry["revision"]:
            return "in_review"
    return "reviewed"


def _suggest_gaps(reading):
    grouped = []
    for entry in reading:
        data = entry["data"]
        note, paper = data["notes"], data["paper"]
        if note["status"] == "excluded" or not (note["limitations"] or note["conflicts"]):
            continue
        target = (note["population"] or paper["title"])[:650]
        question = (f"How could follow-up research address the documented limitation in {target}?"
                    if note["limitations"] else f"What study or data differences could explain the conflicting findings in {target}?")
        rationale = note["limitations"] or note["findings"] or "The reading notes link a paper with conflicting evidence."
        method = (f'Assess whether the original method can test this question. Recorded method: {note["method"][:600]}'
                  if note["method"] else "Compare the designs and methods in the cited studies, then choose a test that addresses the documented difference.")
        data_source = (f'Check access and coverage for the recorded dataset: {note["dataset"][:700]}'
                       if note["dataset"] else "Identify a dataset that covers the missing or conflicting setting and verify access before choosing the design.")
        grouped.append({
            "question": question, "rationale": rationale, "method": method, "data_source": data_source,
            "evidence": [entry["id"]], "counterevidence": note["conflicts"], "status": "candidate",
            "source_title": paper["title"], "source_url": paper["url"], "locator": note["locator"],
        })
    return grouped[:10]


def _filename(content, filename, media_type):
    return Response(content, media_type=media_type, headers={
        "Content-Disposition": f'attachment; filename="{filename}"',
    })


def _draft_evidence(store, project_id, item_id):
    entry = _item(store, project_id, "manuscripts", item_id)
    draft = current_draft(store, entry)
    references = {}
    for key in draft_reference_ids(draft):
        record = _item(store, project_id, "reading", key, required=False)
        if record:
            references[key] = record["data"]["paper"]
    target = _item(store, project_id, "submissions", draft["submission_id"])["data"] if draft["submission_id"] else None
    checks = review_manuscript(draft, references, target)
    return draft, references, target, checks


def current_draft(store, entry):
    recovery = store.publishing.autosave(entry["project_id"], entry["id"])
    return recovery["data"] if recovery and recovery["base_revision"] == entry["revision"] else entry["data"]


def validate_draft_links(store, project_id, data):
    if data["submission_id"]:
        _item(store, project_id, "submissions", data["submission_id"])
    _reading(store, project_id, [key for claim in data["claims"] for key in claim["references"]])
    _reading(store, project_id, data.get("inline_citations", {}).values())


def account_router(get_store):
    router = APIRouter(prefix="/api/v1", tags=["Academic planning"])

    @router.get("/submission-calendar")
    def deadlines(project_id: Optional[str] = None, store=Depends(get_store)):
        entries = calendar_entries(store, lambda entry: _public_submission(entry, store))
        return {"items": [item for item in entries if not project_id or item["project_id"] == project_id]}

    @router.get("/submission-calendar/export")
    def export_deadlines(project_id: Optional[str] = None, store=Depends(get_store)):
        entries = deadlines(project_id, store)["items"]
        return _filename(calendar_export(entries), "submission-calendar.ics", "text/calendar")

    @router.get("/portfolio/targets")
    def portfolio_targets(store=Depends(get_store)):
        rules_by_project = {}
        for rule in store.all_workspace_items("dossier-rules"):
            rules_by_project.setdefault(rule["project_id"], []).append(rule)
        targets = []
        for target in store.all_workspace_items("dossier-profile"):
            states = [
                _dossier_status(store, target["project_id"], item["data"])
                for item in rules_by_project.get(target["project_id"], [])
                if item["data"]["profile_revision"] == target["revision"]
            ]
            targets.append({**target, "criteria_count": len(states), "reviewed_count": states.count("reviewed"),
                            "needs_evidence": states.count("needs_evidence")})
        return {"items": targets}

    return router


def workspace_router(get_store, get_openalex, serialize_paper):
    router = APIRouter(prefix="/api/v1/projects/{project_id}/workspace", tags=["Publishing workspace"])

    def project_store(project_id: str, store: ProjectStore = Depends(get_store)) -> ProjectStore:
        if not store.get_project(project_id):
            raise HTTPException(404, "Research topic not found")
        return store

    @router.post("/discover", status_code=201)
    async def discover_topic(project_id: str, request: DiscoveryRequest, store=Depends(project_store),
                             searcher=Depends(get_openalex)):
        data = await run_in_threadpool(discovery.discover, searcher, request.query, request.field,
                                       request.include_preprints, serialize_paper)
        await run_in_threadpool(store.literature.observe, data["papers"], data["retrieved_at"])
        return _write(store, project_id, "discovery", data)

    @router.post("/discover/{run_id}/topics/{topic_id}", status_code=201)
    async def discover_representatives(project_id: str, run_id: str, topic_id: str, store=Depends(project_store),
                                       searcher=Depends(get_openalex)):
        snapshot = _item(store, project_id, "discovery", run_id)["data"]
        if not any(row["id"] == topic_id for row in snapshot["trends"]):
            raise HTTPException(404, "Subtopic not present in this discovery snapshot.")
        data = await run_in_threadpool(discovery.representative_papers, searcher, snapshot, topic_id, serialize_paper)
        await run_in_threadpool(store.literature.observe, data["papers"], data["retrieved_at"])
        return _write(store, project_id, "discovery-papers", data)

    @router.get("/discover/gaps")
    async def gap_suggestions(project_id: str, store=Depends(project_store)):
        return {"items": _suggest_gaps(store.workspace_items(project_id, "reading", 250))}

    @router.get("/submission-search")
    async def search_submissions(q: str = Query(min_length=2, max_length=160), store=Depends(project_store),
                                 searcher=Depends(get_openalex)):
        return await run_in_threadpool(submission_sources.find_calls, q.strip(), searcher)

    @router.post("/submissions/{item_id}/verify")
    async def verify_submission(project_id: str, item_id: str, store=Depends(project_store)):
        current = _item(store, project_id, "submissions", item_id)
        call = store.publishing.watched_call(project_id, item_id)
        if call:
            from .special_issues import recheck

            await run_in_threadpool(recheck, store, call["id"])
            return _public_submission(current, store)
        data = current["data"]
        if not submission_sources.official_page(data["source_url"]):
            raise HTTPException(422, "Automatic verification is unavailable for this URL. Save a manual check from the official page.")
        notice = await run_in_threadpool(submission_sources.verify_notice, data["source_url"])
        saved = _write(store, project_id, "submissions", _apply_publisher_check(data, notice), item_id, current["revision"])
        return _public_submission(saved)

    @router.post("/reading/from-source", status_code=201)
    async def shortlist_paper(project_id: str, selection: ReadingSource, store=Depends(project_store)):
        origin, field = _load_origin(store, project_id, selection)
        paper = next((row for row in origin.get(field, []) if row["url"] == selection.paper_url), None)
        if paper is None:
            raise HTTPException(404, "Paper not found in this topic’s saved source result.")
        identity = (paper.get("doi") or "").strip().lower().removeprefix("https://doi.org/")
        key = sha256((identity or paper["url"]).encode()).hexdigest()[:32]
        existing = _item(store, project_id, "reading", key, required=False)
        if existing:
            return existing
        data = {"paper": paper, "origin": selection.model_dump(), "retrieved_at": origin.get("retrieved_at"),
                "notes": ReadingNotes().model_dump()}
        try:
            return store.put_workspace_item(project_id, "reading", data, key)
        except WorkspaceConflict:
            return _item(store, project_id, "reading", key)

    @router.get("/manuscripts/{item_id}/review")
    async def review_draft(project_id: str, item_id: str, store=Depends(project_store)):
        return _draft_evidence(store, project_id, item_id)[3]

    @router.get("/manuscripts/{item_id}/autosave")
    def get_autosave(project_id: str, item_id: str, store=Depends(project_store)):
        _item(store, project_id, "manuscripts", item_id)
        return {"item": store.publishing.autosave(project_id, item_id)}

    @router.put("/manuscripts/{item_id}/autosave")
    def write_autosave(project_id: str, item_id: str, payload: WorkspaceWrite, store=Depends(project_store)):
        _item(store, project_id, "manuscripts", item_id)
        data = _validate(Manuscript, payload.data)
        validate_draft_links(store, project_id, data)
        if data["idea_id"]:
            _item(store, project_id, "ideas", data["idea_id"])
        result = store.publishing.save_draft(project_id, item_id, payload.revision, payload.autosave_version or 0, data)
        if not result:
            raise HTTPException(409, "This draft changed in another tab. Reopen it to load the latest autosave.")
        return result

    @router.get("/manuscripts/{item_id}/export")
    async def export_draft(project_id: str, item_id: str, format: Literal["markdown", "bibtex", "ris", "docx"] = "markdown",
                           store=Depends(project_store)):
        draft, refs, target, checks = _draft_evidence(store, project_id, item_id)
        if format == "markdown":
            return _filename(draft_export(draft, refs, checks, target), "manuscript.md", "text/markdown")
        if format == "docx":
            content = await run_in_threadpool(word_export, draft, refs)
            return _filename(content, "manuscript.docx", "application/vnd.openxmlformats-officedocument.wordprocessingml.document")
        return _filename(reference_export(refs.values(), format), "references.bib" if format == "bibtex" else "references.ris",
                         "text/plain")

    @router.get("/dossier/export")
    async def export_dossier(project_id: str, store=Depends(project_store)):
        profile = _active_dossier_profile(store, project_id)
        rules = [{**entry["data"], "status": _dossier_status(store, project_id, entry["data"])}
                 for entry in store.workspace_items(project_id, "dossier-rules", 1000)
                 if entry["data"]["profile_revision"] == profile["revision"]]
        activities = {entry["id"]: entry["data"] for entry in store.workspace_items(project_id, "dossier-activities", 1000)}
        keys = {key for rule in rules for key in rule["activity_ids"]}
        for key in keys - activities.keys():
            activities[key] = _item(store, project_id, "dossier-activities", key)["data"]
        for rule in rules:
            for key in rule.get("portfolio_activity_ids", []):
                entry = store.workflow.portfolio_item(key)
                if entry:
                    activities[key] = entry["data"]
                    rule["activity_ids"] = [*rule["activity_ids"], key]
        reading = {key: entry["paper"] for key, entry in _reading(
            store, project_id, [activity["reading_id"] for activity in activities.values() if activity["reading_id"]],
        ).items()}
        return _filename(dossier_export(profile["data"], rules, activities, reading), "academic-dossier.md", "text/markdown")

    @router.get("/{section}")
    async def list_items(project_id: str, section: Section, limit: int = Query(100, ge=1, le=250), store=Depends(project_store)):
        records = store.workspace_items(project_id, section, limit)
        if section == "submissions":
            records = [_public_submission(record, store) for record in records]
        if section == "dossier-rules":
            records = [{**record, "display_status": _dossier_status(store, project_id, record["data"])}
                       for record in records]
        return {"items": records}

    @router.get("/{section}/{item_id}/history")
    async def item_history(project_id: str, section: Section, item_id: str, store=Depends(project_store)):
        return {"items": store.workspace_history(project_id, section, item_id)}

    @router.post("/{section}", status_code=201)
    async def create_item(project_id: str, section: Section, payload: WorkspaceWrite, store=Depends(project_store)):
        if section not in _MODELS or payload.revision != 0:
            raise HTTPException(422, "Create this item using its workspace action.")
        item_id = "target" if section == "dossier-profile" else None
        return await save_item(store, project_id, section, item_id, payload, None)

    @router.put("/{section}/{item_id}")
    async def update_item(project_id: str, section: Section, item_id: str, payload: WorkspaceWrite, store=Depends(project_store)):
        if section == "discovery":
            raise HTTPException(422, "Discovery snapshots are read-only.")
        current = _item(store, project_id, section, item_id)
        if current["revision"] != payload.revision:
            raise HTTPException(409, "This item changed. Reload the latest version before saving.")
        return await save_item(store, project_id, section, item_id, payload, current["data"])

    async def save_item(store, project_id, section, item_id, payload, current):
        if section == "reading":
            notes = _validate(ReadingNotes, payload.data)
            if item_id in notes["conflicts"]:
                raise HTTPException(422, "Select a different paper for conflicting evidence.")
            _reading(store, project_id, notes["conflicts"])
            data = {**current, "notes": notes}
        else:
            data = _validate(_MODELS[section], payload.data)

        if section == "ideas":
            _reading(store, project_id, data["evidence"] + data["counterevidence"])
        elif section == "submissions":
            tracked = store.publishing.watched_call(project_id, item_id) if item_id else None
            if tracked and data["source_url"] != tracked["source_url"]:
                raise HTTPException(422, "Save a different publisher URL as a separate submission opportunity.")
            automatic = data.pop("verify_from_source")
            if automatic:
                notice = await run_in_threadpool(submission_sources.verify_notice, data["source_url"])
                data = _apply_publisher_check(data, notice)
            else:
                data.update(verification="researcher" if data["status"] != "unverified" else "unverified",
                            checked_at=datetime.now(timezone.utc).isoformat() if data["status"] != "unverified" else "",
                            verification_error="")
        elif section == "submission-tracking":
            if data["manuscript_id"]:
                _item(store, project_id, "manuscripts", data["manuscript_id"])
            if data["opportunity_id"]:
                _item(store, project_id, "submissions", data["opportunity_id"])
        elif section == "manuscripts":
            idea = _item(store, project_id, "ideas", data["idea_id"])["data"] if data["idea_id"] else None
            validate_draft_links(store, project_id, data)
            if not data["sections"]:
                data["sections"] = [{"heading": heading, "text": ""} for heading in OUTLINES[data["article_type"]]]
                if idea and "Introduction" in OUTLINES[data["article_type"]]:
                    data["sections"][1]["text"] = idea["question"]
        elif section == "dossier-activities" and data["reading_id"]:
            _reading(store, project_id, [data["reading_id"]])
        elif section == "dossier-profile" and data == current:
            return _item(store, project_id, section, item_id)
        elif section == "dossier-rules":
            profile = _active_dossier_profile(store, project_id)
            data["profile_revision"] = profile["revision"]
            selected = [_item(store, project_id, "dossier-activities", key) for key in data["activity_ids"]]
            shared = [store.workflow.portfolio_item(key) for key in dict.fromkeys(data["portfolio_activity_ids"])]
            if any(entry is None for entry in shared):
                raise HTTPException(422, "A selected portfolio activity could not be found.")
            activities = [entry["data"] for entry in selected + shared]
            if data["status"] == "reviewed" and (not activities or any(
                not activity["evidence_date"] or not (
                    activity["evidence_url"] or activity["reading_id"] or (activity.get("paper") or {}).get("url")
                )
                for activity in activities
            )):
                raise HTTPException(422, "Reviewed criteria require dated, linked evidence for each selected activity.")
            data["activity_revisions"] = {entry["id"]: entry["revision"] for entry in selected}
            data["portfolio_revisions"] = {entry["id"]: entry["revision"] for entry in shared}
        published = _write(store, project_id, section, data, item_id, payload.revision, payload.autosave_version)
        return _public_submission(published, store) if section == "submissions" else published

    return router
