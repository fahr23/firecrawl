"""Follow journal identities, recent publications, and official submission evidence."""

import asyncio
from datetime import date
import logging
import re
from typing import Literal, Optional
from urllib.parse import urljoin, urlsplit

import requests
from fastapi import APIRouter, Depends, HTTPException, Query, Response
from fastapi.concurrency import run_in_threadpool
from pydantic import BaseModel, Field

from . import special_issues, submission_sources
from .journal_favorites_store import clock, journal_issns, normalize_issn


logger = logging.getLogger(__name__)
PAPER_WINDOW = 30

_PUBLICATION_ERROR = {"status": "failed", "message": "OpenAlex could not check this journal."}
_PUBLISHER_ERROR = {"status": "unavailable", "message": "The publisher page could not be read."}


class FavoriteRequest(BaseModel):
    provider: Literal["openalex", "web-of-science", "scopus", "ubyt"] = "openalex"
    journal_id: str = Field(min_length=1, max_length=160)


class SeenRequest(BaseModel):
    library_id: Optional[int] = Field(default=None, ge=1)


def _safe_homepage(journal):
    url = (journal.get("homepage_url") or "").strip()
    if url.startswith("http://"):
        url = "https://" + url[7:]
    if not submission_sources.public_url(url):
        return ""
    parsed = urlsplit(url)
    if parsed.hostname == "www.springer.com" and re.fullmatch(r"/journal/\d+/?", parsed.path):
        return "https://link.springer.com" + parsed.path
    return url


def _publisher(journal):
    homepage = _safe_homepage(journal)
    notice = None
    if not homepage:
        homepage, notice = special_issues.dergipark_homepage(journal["display_name"])
    if not homepage or not submission_sources.official_page(homepage):
        return None, {"status": "manual", "message": "Check the journal’s own site for its submission policies."}, []
    notice = notice or special_issues._try_read(homepage)
    if not notice:
        return None, _PUBLISHER_ERROR, []
    fields = submission_sources._labeled_links(notice, homepage)
    result = {"homepage_url": homepage, **fields, "article_types": "", "fees": "", "scope": "",
              "status": "unverified", "evidence": "", "policy_url": ""}
    # Journal homepages can mention a special issue in a banner. Only use
    # an identified author policy page to infer regular submission status.
    guide = fields.get("guidelines_url", "")
    scope = fields.get("scope_url", "")
    root = urlsplit(homepage)
    policy_path = root.path.rstrip("/") + "/"
    for url, criterion in ((guide, "policy"), (scope, "scope")):
        if (not submission_sources.official_page(url) or urlsplit(url).hostname != root.hostname
                or not urlsplit(url).path.startswith(policy_path)):
            continue
        page = special_issues._try_read(url)
        if not page:
            continue
        info = submission_sources.parse_notice(url, page, follow_calls=False, journal_policy=criterion == "policy")
        if criterion == "policy":
            result.update(policy_url=url, status=info["status"], evidence=info["evidence"],
                          article_types=info["article_types"], fees=info["fees"])
            for key in ("submission_url", "fees_url"):
                if info.get(key):
                    result.setdefault(key, info[key])
        else:
            result["scope"] = info["scope"]

    venue_host = root.hostname
    publisher = next((key for key, hosts in special_issues._SOURCE_HOSTS.items() if venue_host in hosts), None)
    candidates = {}
    if publisher:
        links = list(notice.links)
        listing_paths = {policy_path + suffix for suffix in (
            "announcements", "calls-for-papers", "about/call-for-papers", "call-for-papers",
        )}
        listing = next((url for href, _ in notice.links if submission_sources.official_page(url := urljoin(homepage, href))
                        and urlsplit(url).hostname == root.hostname and urlsplit(url).path.rstrip("/") in listing_paths), "")
        if listing:
            result["calls_url"] = listing
            page = special_issues._try_read(listing)
            if page:
                links.extend((urljoin(listing, href), label) for href, label in page.links)
        for href, label in links:
            if not special_issues._CALL_TITLE.search(label):
                continue
            url = special_issues._call_url(publisher, homepage, href)
            if url:
                # DergiPark hosts different journals on the same domain.
                # Require this journal's slug on linked notices.
                if publisher == "dergipark" and not urlsplit(url).path.startswith(policy_path):
                    continue
                candidates.setdefault(url, label)
    calls = []
    for url, title in list(candidates.items())[:3]:
        item = special_issues._details(publisher, url, homepage, title)
        if item:
            if not item.get("venue"):
                item["venue"] = journal["display_name"]
            calls.append(item)
    return result, {"status": "checked"}, calls


def _journal_calls(store, journal):
    issns = journal_issns(journal)
    name = special_issues._tokens(journal["display_name"])
    today = clock().date().isoformat()
    calls = []
    for row in store.publishing.calls(list(special_issues.PUBLISHERS)):
        known_issn = normalize_issn(row.get("issn"))
        matches = known_issn in issns if known_issn and issns else special_issues._tokens(row.get("venue") or "") == name
        if matches and row["status"] == "open" and (not row["deadline"] or row["deadline"] >= today):
            calls.append(row)
    return sorted(calls, key=lambda item: (not item["deadline"], item["deadline"], item["title"]))


def _papers(store, favorite, searcher, serialize):
    if not favorite["openalex_id"]:
        return None, {"status": "unsupported", "message": "This catalog record has no OpenAlex journal match for papers."}
    through = clock().date()
    result = searcher.search_journal(
        favorite["openalex_id"], favorite["journal"]["display_name"], "", PAPER_WINDOW,
        published_through=through.isoformat(),
    )
    outcome = result.provider_outcomes[0].to_dict() if result.provider_outcomes else _PUBLICATION_ERROR
    if outcome["status"] not in {"responded", "empty"}:
        return None, outcome
    papers = []
    for article in result.articles:
        paper = serialize(article)
        if not paper:
            continue
        try:
            publication_date = date.fromisoformat(paper.get("publication_date") or "")
        except (TypeError, ValueError):
            publication_date = None
        if publication_date and publication_date > through:
            continue
        raw = article.raw_data or {}
        primary_topic = raw.get("primary_topic") or {}
        if isinstance(primary_topic, dict) and isinstance(primary_topic.get("display_name"), str):
            paper["primary_topic"] = primary_topic["display_name"][:200]
        if isinstance(raw.get("type"), str):
            paper["work_type"] = raw["type"][:60]
        papers.append(paper)
    store.literature.observe(papers, result.timestamp)
    indexed = []
    for paper in papers:
        work_id = store.workflow.identify_paper(paper["url"], paper.get("doi"))
        if work_id is not None:
            indexed.append({**paper, "library_id": str(work_id)})
    return indexed, outcome


def refresh(store, favorite_id, searcher, serialize):
    favorite = store.journal_favorites.get(favorite_id)
    if not favorite:
        raise HTTPException(404, "Followed journal not found.")
    token = store.journal_favorites.claim(favorite_id)
    if not token:
        raise HTTPException(409, "This journal is already being refreshed.")
    try:
        try:
            papers, paper_status = _papers(store, favorite, searcher, serialize)
        except (requests.RequestException, OSError):
            papers, paper_status = None, _PUBLICATION_ERROR
        try:
            publisher, publisher_status, calls = _publisher(favorite["journal"])
        except (requests.RequestException, OSError, ValueError):
            publisher, publisher_status, calls = None, _PUBLISHER_ERROR, []
        store.publishing.cache_calls(calls)
        added = store.journal_favorites.finish(favorite_id, token, papers, paper_status, publisher, publisher_status)
        return {"added": added, "favorite": store.journal_favorites.get(favorite_id)}
    finally:
        store.journal_favorites.release(favorite_id, token)


async def scheduler(store, get_searcher, serialize):
    while True:
        await asyncio.sleep(45)
        for favorite_id in store.journal_favorites.due():
            try:
                await run_in_threadpool(refresh, store, favorite_id, get_searcher(), serialize)
            except HTTPException as exc:
                if exc.status_code not in {404, 409}:
                    logger.warning("A followed journal could not be refreshed (%s)", exc.status_code)
            except Exception:
                logger.exception("A followed journal could not be refreshed")


def journal_favorites_router(get_store, get_catalog, get_searcher, serialize):
    router = APIRouter(prefix="/api/v1/journal-favorites", tags=["Followed journals"])

    def required(store, favorite_id):
        favorite = store.journal_favorites.get(favorite_id)
        if not favorite:
            raise HTTPException(404, "Followed journal not found.")
        return favorite

    @router.get("")
    def list_journals(response: Response, store=Depends(get_store)):
        response.headers["Cache-Control"] = "no-store"
        return {"items": store.journal_favorites.all()}

    @router.post("", status_code=201)
    def follow(request: FavoriteRequest, store=Depends(get_store), catalog=Depends(get_catalog)):
        existing = store.journal_favorites.restore_by_catalog(request.provider, request.journal_id)
        if existing and existing["openalex_id"]:
            return existing
        try:
            result = catalog.resolve(request.provider, request.journal_id)
        except (requests.RequestException, OSError):
            if existing:
                return existing
            raise HTTPException(503, "The journal catalog could not be reached.") from None
        journal = result.get("journal")
        if not journal:
            if existing:
                return existing
            status = result.get("provider_status", {}).get("status")
            raise HTTPException(404 if status in {"empty", "not_found"} else 503, "This journal could not be resolved.")
        if journal.get("type") != "journal":
            raise HTTPException(422, "Choose a journal from a journal catalog.")
        return store.journal_favorites.follow(journal, request.provider, request.journal_id)

    @router.get("/{favorite_id}")
    def feed(favorite_id: str, response: Response, limit: int = Query(12, ge=1, le=40),
             offset: int = Query(0, ge=0), unread_only: bool = False, store=Depends(get_store)):
        response.headers["Cache-Control"] = "no-store"
        favorite = required(store, favorite_id)
        papers, more = store.journal_favorites.papers(favorite_id, limit, offset, unread_only)
        return {"favorite": favorite, "papers": papers, "has_more": more,
                "homepage_url": _safe_homepage(favorite["journal"]),
                "calls": _journal_calls(store, favorite["journal"])}

    @router.post("/{favorite_id}/refresh")
    def refresh_one(favorite_id: str, store=Depends(get_store), searcher=Depends(get_searcher)):
        return refresh(store, favorite_id, searcher, serialize)

    @router.post("/{favorite_id}/seen")
    def mark_seen(favorite_id: str, request: SeenRequest, store=Depends(get_store)):
        required(store, favorite_id)
        return {"marked": store.journal_favorites.mark_seen(favorite_id, request.library_id)}

    @router.delete("/{favorite_id}")
    def unfollow(favorite_id: str, store=Depends(get_store)):
        if not store.journal_favorites.unfollow(favorite_id):
            raise HTTPException(404, "Followed journal not found.")
        return {"followed": False}

    return router
