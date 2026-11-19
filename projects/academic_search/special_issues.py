"""Publisher-sourced call discovery, searchable snapshots, and deadline alerts."""

import asyncio
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from hashlib import sha256
import logging
import re
from urllib.parse import quote, urljoin, urlsplit, urlunsplit

import requests
from fastapi.concurrency import run_in_threadpool

from . import submission_sources as sources
logger = logging.getLogger(__name__)


PUBLISHERS = {
    "springer": ("Springer Nature", sources.SPRINGER_SEARCH, r"/collections/[a-z0-9]+"),
    "sage": ("Sage", "https://journals.sagepub.com/open-call-for-papers", r"/(?:page/|pb-assets/cmscontent/).+"),
    "taylor": ("Taylor & Francis", "https://authorservices.taylorandfrancis.com/call-for-papers/", r"/special_issues/[a-z0-9-]+"),
    "elsevier": ("Elsevier", "https://www.sciencedirect.com/browse/calls-for-papers",
                 r"/journal/[a-z0-9-]+/(?:about/)?call-for-papers/(?:\d+/)?[a-z0-9-]+"),
    "dergipark": ("DergiPark", "https://dergipark.org.tr/en/pub/explore/journals",
                  r"/(?:en|tr)/(?:pub/)?[a-z0-9-]+/announcements/\d+"),
}
_SOURCE_HOSTS = {
    "springer": {"link.springer.com", "www.nature.com"},
    "sage": {"journals.sagepub.com"},
    "taylor": {"think.taylorandfrancis.com", "callforpapers.taylorandfrancis.com"},
    "elsevier": {"www.sciencedirect.com"},
    "dergipark": {"dergipark.org.tr"},
}
_DERGI_HOME = re.compile(r"/(?:en|tr)/(?:pub/)?([a-z0-9-]+)")
_CALL_TITLE = re.compile(r"special issue|call for papers|özel sayı|makale çağrısı", re.I)
_DATE = rf"({sources._DAY}|{sources._MONTH}|\d{{4}}-\d{{2}}-\d{{2}})"
_MANUSCRIPT_DATE = re.compile(
    rf"\b(?:(?:full )?(?:manuscript|paper) (?:submission )?deadline|"
    rf"full (?:manuscript|paper) submissions?(?: for peer review)?|deadline for (?:full )?(?:paper|manuscript) submissions?)"
    rf"\s*(?:is|:)?\s*{_DATE}", re.I,
)
_SUBMISSION_DATE = re.compile(rf"^(?:extended\s+)?submission deadline\s*:?\s*{_DATE}", re.I)
_ABSTRACT_DATE = re.compile(rf"\b(?:abstract|(?:abstract )?proposal) (?:submission )?(?:deadline|due)\s*:?\s*{_DATE}", re.I)


def _checked():
    return datetime.now(timezone.utc)


def _call_url(publisher, base, href):
    try:
        target = urlsplit(urljoin(base, href))
        if target.hostname not in _SOURCE_HOSTS[publisher]:
            return None
        path = target.path.rstrip("/")
        canonical = path + "/" if publisher == "taylor" else path
        host = "callforpapers.taylorandfrancis.com" if publisher == "taylor" else target.netloc
        url = urlunsplit(("https", host, quote(canonical, safe="/%-._~()"), "", ""))
        if sources.public_url(url) and re.fullmatch(PUBLISHERS[publisher][2], path):
            return url
    except ValueError:
        return None
    return None


def _headline(notice, heading):
    return next((text for tag, text in notice.blocks if tag == heading and text), "")


def _published_call(publisher, url, listing, data):
    if len(data.get("title", "").strip()) < 2:
        return None
    now = _checked()
    deadline = data.get("deadline") or ""
    explicit = data.get("status") or "unverified"
    status = explicit
    if deadline and deadline < now.date().isoformat():
        status = "closed"
    elif (explicit == "unverified" and data.get("confirmed_open") and deadline
          and (not data.get("abstract_deadline") or data["abstract_deadline"] >= now.date().isoformat())):
        status = "open"
    return {**data, "id": sha256(url.encode()).hexdigest()[:32], "publisher": publisher,
            "source_url": url, "listing_url": listing, "status": status, "deadline": deadline,
            "kind": "special_issue", "checked_at": now.isoformat()}


def _try_read(url, params=None):
    try:
        return sources._read(url, params) if params else sources._read(url)
    except (requests.RequestException, ValueError):
        return None


def _details(publisher, url, listing, label=""):
    notice = _try_read(url)
    if not notice:
        return None
    # The legacy verifier reads the same page. Pass the parsed notice here so the
    # catalog makes only one request per call.
    data = sources.parse_notice(url, notice)
    if publisher == "taylor":
        data["venue"] = _headline(notice, "h1") or data["venue"]
        data["title"] = _headline(notice, "h2") or label or data["title"]
    elif publisher == "dergipark":
        headings = [text for tag, text in notice.blocks if tag in ("h1", "h2", "h3")]
        data["venue"] = _headline(notice, "h1")
        data["title"] = next((text for text in headings if _CALL_TITLE.search(text)), label)[:280]
    else:
        data["title"] = data["title"] or label
    content = " ".join(notice.chunks)
    full = _MANUSCRIPT_DATE.search(content)
    abstract = _ABSTRACT_DATE.search(content)
    if full:
        data.update(deadline=sources._parse_date(full.group(1)), evidence=full.group(0))
        if data["status"] == "closed" and not any(
            word in content.casefold() for word in ("closed for submissions", "submissions are closed", "no longer accepting")
        ):
            data["status"] = "unverified"
    elif abstract and not data.get("deadline"):
        data["evidence"] = abstract.group(0)
    data["abstract_deadline"] = sources._parse_date(abstract.group(1)) if abstract else ""
    if publisher == "taylor" and data.get("deadline"):
        data["confirmed_open"] = any("submit an article" in text.casefold() for _, text in notice.links)
    if publisher == "dergipark" and data.get("deadline"):
        invited = re.search(r"\b(?:invites?|welcomes?|accepting) (?:[\w-]+ ){0,5}(?:papers|manuscripts|submissions)\b",
                            content, re.I)
        data["confirmed_open"] = bool(invited and not re.search(r"\btentative\b", content, re.I))
    if data.get("deadline") and not full and re.search(r"(?:abstract|proposal) submission deadline", content, re.I):
        if not any(_SUBMISSION_DATE.match(text) for _, text in notice.blocks):
            data["deadline"] = ""
    return _published_call(publisher, url, listing, data)


def _sage_calls(notice, listing):
    rows = []
    journal = ""
    events = notice.events
    for index, (href, label) in enumerate(events):
        if not href or not label:
            continue
        path = urlsplit(urljoin(listing, href)).path
        if re.fullmatch(r"/(?:home|journals)/[a-z0-9]+", path, re.I):
            journal = label
            continue
        url = _call_url("sage", listing, href)
        if not url or not journal or re.search(r"general call|author guidelines", label, re.I):
            continue
        notes = []
        for following_href, text in events[index + 1:index + 8]:
            if following_href and (_call_url("sage", listing, following_href)
                                   or re.fullmatch(r"/(?:home|journals)/[a-z0-9]+", urlsplit(following_href).path, re.I)):
                break
            notes.append(text)
        full = next((match for text in notes if (match := _MANUSCRIPT_DATE.search(text) or _SUBMISSION_DATE.match(text))), None)
        abstract = _ABSTRACT_DATE.search(" ".join(notes))
        if not full and not abstract and not re.search(r"special issue|call for papers", label, re.I):
            continue
        rows.append(_published_call("sage", url, listing, {
            "title": label[:280], "venue": journal[:280], "scope": " ".join(notes)[:1000],
            "deadline": sources._parse_date(full.group(1)) if full else "",
            "abstract_deadline": sources._parse_date(abstract.group(1)) if abstract else "",
            "evidence": (full or abstract).group(0) if (full or abstract) else "",
            "confirmed_open": True,
        }))
    return [row for row in rows if row]


def _tokens(text):
    return re.findall(r"[^\W_]+", text.casefold())


def _matches(row, query, journal):
    text = " ".join(str(row.get(key) or "") for key in ("title", "venue", "scope"))
    issn = "".join(ch for ch in str(row.get("issn") or "").casefold() if ch.isalnum())
    asked = "".join(ch for ch in journal.casefold() if ch.isalnum())
    journal_match = not journal or (bool(issn) and issn == asked) or all(
        term in str(row.get("venue") or "").casefold() for term in _tokens(journal)
    )
    return journal_match and all(term in text.casefold() for term in _tokens(query))


def dergipark_homepage(journal):
    """Resolve a missing public homepage only when its heading confirms the venue."""
    name = _tokens(journal)
    slug = name[0] if name else ""
    if len(slug) < 5 or slug in {"international", "journal", "turkish", "review", "research", "science"}:
        return "", None
    possible = f"https://dergipark.org.tr/en/pub/{slug}"
    notice = _try_read(possible)
    if notice and _tokens(_headline(notice, "h1")) == name:
        return possible, notice
    return "", None


def _dergipark_search(query, journal, openalex, listing):
    if not openalex or not (query or journal):
        return [], "manual"
    if journal:
        candidates = openalex.suggest_journals(journal, 8)
    else:
        data = openalex._make_request(f"{openalex.BASE_URL}/works", {
            "search": query, "filter": "primary_location.source.type:journal",
            "select": "primary_location", "per_page": 40, "mailto": openalex.email,
        })
        if not data or not isinstance(data.get("results"), list):
            return [], "unavailable"
        ids = {}
        for work in data["results"]:
            source = (work.get("primary_location") or {}).get("source") or {}
            source_id = str(source.get("id") or "").rsplit("/", 1)[-1]
            if re.fullmatch(r"S\d+", source_id):
                ids.setdefault(source_id, None)
        candidates = [openalex.resolve_journal(source_id) or {} for source_id in list(ids)[:8]]
    calls = {}
    for candidate in candidates:
        homepage = candidate.get("homepage_url") or ""
        discovered_home = None
        if not homepage and journal and _tokens(candidate.get("display_name", "")) == _tokens(journal):
            homepage, discovered_home = dergipark_homepage(journal)
        home = urlsplit(homepage)
        match = _DERGI_HOME.fullmatch(home.path.rstrip("/"))
        if home.hostname != "dergipark.org.tr" or not match:
            continue
        root = f"https://dergipark.org.tr{home.path.rstrip('/')}"
        announcement = _try_read(root + "/announcements") or discovered_home or _try_read(root)
        if not announcement:
            continue
        for href, label in announcement.links:
            url = _call_url("dergipark", root, href)
            if url and label and _CALL_TITLE.search(label):
                calls.setdefault(url, label)
    rows = []
    for url, title in list(calls.items())[:8]:
        if row := _details("dergipark", url, listing, title):
            rows.append(row)
    return rows, "partial" if len(rows) < min(8, len(calls)) else "checked"


def _source_search(publisher, query, journal, openalex=None):
    name, listing, _ = PUBLISHERS[publisher]
    coverage = {"publisher": publisher, "label": name, "url": listing}
    if publisher == "dergipark":
        rows, status = _dergipark_search(query, journal, openalex, listing)
        return rows, {**coverage, "status": status}
    params = {"content-type": "call for papers", "new-search": "true", "query": query or journal} if publisher == "springer" else None
    notice = _try_read(listing, params)
    if not notice:
        return [], {**coverage, "status": "unavailable"}
    if publisher == "sage":
        rows = _sage_calls(notice, listing)
        return rows, {**coverage, "status": "checked" if rows else "manual"}
    urls = {}
    for href, label in notice.links:
        url = _call_url(publisher, listing, href)
        if url and label:
            urls.setdefault(url, label)
    if not urls:
        return [], {**coverage, "status": "manual"}
    # Keep verification bounded. Prefer clearly relevant labels, then inspect
    # additional notices whose journal or scope may appear only on the call page.
    ranked = sorted(urls, key=lambda url: -sum(term in urls[url].casefold() for term in _tokens(f"{query} {journal}")))
    with ThreadPoolExecutor(max_workers=3) as pool:
        checked = list(pool.map(lambda url: _details(publisher, url, listing, urls[url]), ranked[:8]))
    return [row for row in checked if row], {**coverage, "status": "partial" if None in checked else "checked"}


def search(store, query, journal, deadline_from, deadline_to, open_only, publishers, refresh, openalex=None):
    coverage = []
    current = set()
    # Cache publisher queries for a short period so repeated filter changes
    # do not repeatedly visit the official listings.
    saved = None if refresh else store.publishing.call_search_recent(query, journal, publishers)
    if not saved:
        with ThreadPoolExecutor(max_workers=min(len(publishers), 4)) as pool:
            fetched = list(pool.map(lambda publisher: _source_search(publisher, query, journal, openalex), publishers))
        for rows, status in fetched:
            store.publishing.cache_calls(rows)
            current.update(row["id"] for row in rows)
            coverage.append(status)
        store.publishing.record_call_search(query, journal, publishers, coverage, current)
    else:
        coverage = saved["coverage"]
        current = set(saved["current"])
    today = _checked().date().isoformat()
    rows = []
    for row in store.publishing.calls(publishers):
        if not _matches(row, query, journal):
            continue
        deadline = row["deadline"]
        display = "closed" if deadline and deadline < today else row["status"]
        if open_only and display != "open":
            continue
        if (deadline_from and (not deadline or deadline < deadline_from)) or (
            deadline_to and (not deadline or deadline > deadline_to)
        ):
            continue
        rows.append({**row, "status": display, "cached": row["id"] not in current})
    return {"items": sorted(rows, key=lambda row: (row["status"] != "open", not row["deadline"], row["deadline"], row["title"]))[:80],
            "sources": coverage}


def verify_url(store, url):
    for publisher, (_, listing, _) in PUBLISHERS.items():
        normalized = _call_url(publisher, listing, url)
        if normalized:
            if publisher == "sage":
                notice = _try_read(listing)
                row = next((item for item in (_sage_calls(notice, listing) if notice else [])
                            if item["source_url"] == normalized), None)
                if not row and sources.official_page(normalized):
                    row = _details(publisher, normalized, listing)
            else:
                row = _details(publisher, normalized, listing)
            if row:
                store.publishing.cache_calls([row])
                return store.publishing.get_call(row["id"])
    return None


def recheck(store, call_id):
    current = store.publishing.get_call(call_id)
    if not current:
        return
    store.publishing.note_attempt(call_id)
    publisher, url, listing = current["publisher"], current["source_url"], current["listing_url"]
    # Re-read Sage's official directory entry, including links to publisher PDFs.
    if publisher == "sage":
        notice = _try_read(listing)
        updated = next((row for row in (_sage_calls(notice, listing) if notice else []) if row["id"] == call_id), None)
    else:
        updated = _details(publisher, url, listing, current["title"])
    if updated:
        store.publishing.cache_calls([updated])


async def scheduler(store):
    while True:
        await asyncio.sleep(300)
        for call_id in store.publishing.due_calls():
            try:
                await run_in_threadpool(recheck, store, call_id)
            except Exception:
                logger.exception("A saved special-issue call could not be rechecked")
