"""Read public submission notices from a small set of official publishers."""

from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, timedelta, timezone
from html.parser import HTMLParser
import re
from urllib.parse import urlencode, urljoin, urlsplit

import requests


SPRINGER_SEARCH = "https://link.springer.com/search"
OFFICIAL_PORTALS = (
    {"name": "Springer Nature collections", "url": SPRINGER_SEARCH + "?content-type=call+for+papers&new-search=true"},
    {"name": "Sage calls for papers", "url": "https://journals.sagepub.com/open-call-for-papers"},
    {"name": "DergiPark journal directory", "url": "https://dergipark.org.tr/en/pub/explore/journals"},
)
_SOURCE_PATHS = {
    "link.springer.com": r"/(?:collections/[a-z0-9]+(?:/how-to-submit)?|journal/\d+(?:/(?:submission-guidelines|aims-and-scope|calls-for-papers))?)",
    "www.nature.com": r"/collections/[a-z0-9]+(?:/how-to-submit)?",
    "think.taylorandfrancis.com": r"/special_issues/[a-z0-9-]+",
    "callforpapers.taylorandfrancis.com": r"/special_issues/[a-z0-9-]+",
    "www.sciencedirect.com": r"/journal/[a-z0-9-]+(?:/publish/guide-for-authors|/about/aims-and-scope|/(?:about/)?call-for-papers(?:/(?:\d+/)?[a-z0-9-]+)?)?",
    "journals.sagepub.com": r"/page/[a-z0-9]+/[a-z0-9/-]+",
    "journals.plos.org": r"/[a-z0-9]+(?:/s/(?:submission-guidelines|journal-information|what-we-publish))?",
    "dergipark.org.tr": r"/(?:en|tr)/(?:pub/)?(?!explore(?:/|$))[a-z0-9-]+(?:/announcements(?:/\d+)?|/writing-rules|/aim-and-scope)?",
}
_BLOCK_TAGS = {"h1", "h2", "h3", "p", "dt", "dd", "time"}
_STATUS = re.compile(
    r"\b(open for submissions|closed for submissions|(?:not |no longer )?accepting (?:full )?(?:manuscript )?submissions|"
    r"submissions (?:are|have) closed|upcoming submissions|makale (?:gönderimine|kabulüne) (?:açık|kapalı))\b", re.I,
)
_HISTORY = re.compile(r"\b(?:submission history|makale gönderim geçmişi|makale gönderimi geçmişi)\b", re.I)
_MONTHS = r"January|February|March|April|May|June|July|August|September|October|November|December"
_DAY = rf"\d{{1,2}}(?:st|nd|rd|th)? (?:{_MONTHS}) \d{{4}}"
_MONTH = rf"(?:{_MONTHS}) \d{{1,2}}(?:st|nd|rd|th)?,? \d{{4}}"
_DEADLINE = re.compile(
    rf"\b(?:submission deadline|deadline for (?:full )?(?:manuscript|paper) submissions?)\s*(?:is|:)?\s*({_DAY}|{_MONTH}|\d{{4}}-\d{{2}}-\d{{2}})",
    re.I,
)


def public_url(url: str) -> bool:
    if re.search(r"[\x00-\x20\\]", url):
        return False
    try:
        parsed = urlsplit(url)
        return (parsed.scheme == "https" and bool(parsed.hostname) and not parsed.username
                and not parsed.password and parsed.port in (None, 443))
    except ValueError:
        return False


def official_page(url: str) -> bool:
    if not public_url(url):
        return False
    parsed = urlsplit(url)
    pattern = _SOURCE_PATHS.get(parsed.hostname or "")
    return bool(pattern and not parsed.query and not parsed.fragment
                and re.fullmatch(pattern, parsed.path.rstrip("/")))


class _Notice(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.chunks = []
        self.blocks = []
        self.links = []
        self.meta = {}
        self.events = []
        self._block = None
        self._anchor = None
        self._ignored = 0

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag in {"script", "style", "noscript"}:
            self._ignored += 1
        elif not self._ignored:
            if tag in _BLOCK_TAGS:
                self._block = (tag, [])
            if tag == "a" and attrs.get("href"):
                self._anchor = (attrs["href"], [])
            if tag == "meta" and attrs.get("content"):
                name = (attrs.get("property") or attrs.get("name") or "").lower()
                self.meta.setdefault(name, attrs["content"])

    def handle_endtag(self, tag):
        if tag in {"script", "style", "noscript"}:
            self._ignored = max(0, self._ignored - 1)
        if self._block and tag == self._block[0]:
            self.blocks.append((tag, " ".join(" ".join(self._block[1]).split())))
            self._block = None
        if tag == "a" and self._anchor:
            url, chunks = self._anchor
            self.links.append((url, " ".join(" ".join(chunks).split())))
            self.events.append((url, self.links[-1][1]))
            self._anchor = None

    def handle_data(self, data):
        text = data.strip()
        if self._ignored or not text:
            return
        self.chunks.append(text)
        if self._block:
            self._block[1].append(text)
        if self._anchor:
            self._anchor[1].append(text)
        else:
            self.events.append(("", text))


def _read(url, params=None):
    with requests.get(url, params=params, timeout=(4, 10), stream=True, allow_redirects=False,
                      headers={"User-Agent": "AcademicSearch/1.5"},
                      ) as response:
        if response.status_code != 200 or "html" not in response.headers.get("Content-Type", "").lower():
            return None
        raw = bytearray()
        for chunk in response.iter_content(chunk_size=16384):
            raw.extend(chunk)
            if len(raw) > 2_000_000:
                return None
        notice = _Notice()
        notice.feed(raw.decode(response.encoding or "utf-8", errors="replace"))
        return notice


def _parse_date(value):
    for form in ("%d %B %Y", "%B %d %Y", "%Y-%m-%d"):
        normalized = re.sub(r"(\d)(?:st|nd|rd|th)\b", r"\1", value, flags=re.I).replace(",", "")
        try:
            return datetime.strptime(normalized, form).date().isoformat()
        except ValueError:
            continue
    return ""


def _labeled_links(notice, source_url):
    result = {}
    for href, text in notice.links:
        link = urljoin(source_url, href)
        if not public_url(link):
            continue
        label = text.casefold()
        if label in {"submission guidelines", "submission instructions", "author guidelines", "guide for authors",
                     "instructions for authors", "writing rules", "yazım kuralları"}:
            result.setdefault("guidelines_url", link)
        if label in {"submit a manuscript", "submit your manuscript", "submit to this journal", "submit manuscript", "online submission system",
                     "submit article", "submit an article", "makale gönder"}:
            result.setdefault("submission_url", link)
        if label in {"aim and scope", "aims and scope", "aim & scope", "aims & scope", "amaç ve kapsam", "what we publish"}:
            result.setdefault("scope_url", link)
        if label in {"price policy", "fees and funding", "article processing charges"}:
            result.setdefault("fees_url", link)
    return result


def verify_notice(url):
    now = datetime.now(timezone.utc).isoformat()
    base = {"source_url": url, "status": "unverified", "checked_at": now,
            "verification": "publisher_page", "evidence": ""}
    if not official_page(url):
        return {**base, "verification": "manual_required", "error": "Use manual verification for this publisher page."}
    try:
        notice = _read(url)
    except (requests.RequestException, ValueError):
        notice = None
    if not notice:
        return {**base, "error": "The publisher page could not be read. Open the official page to verify it."}
    return parse_notice(url, notice, base)


def parse_notice(url, notice, base=None, *, follow_calls=True, journal_policy=False):
    base = base or {"source_url": url, "status": "unverified", "checked_at": datetime.now(timezone.utc).isoformat(),
                    "verification": "publisher_page", "evidence": ""}
    content = " ".join(" ".join(notice.chunks).split())
    current_notice = _HISTORY.split(content, maxsplit=1)[0]
    status_match = _STATUS.search(current_notice)
    deadline_match = _DEADLINE.search(current_notice)
    if journal_policy:
        # A call mentioned in the guidelines does not establish the journal's regular submission status.
        status_match = next((match for _, text in notice.blocks if text in current_notice
                             and (match := _STATUS.fullmatch(text.rstrip(".!")))), None)
        deadline_match = None
    status = "unverified"
    if status_match:
        words = status_match.group(0).lower()
        if "closed" in words or "kapalı" in words or words.startswith(("not ", "no longer ")):
            status = "closed"
        else:
            status = "upcoming" if "upcoming" in words else "open"
    deadline = _parse_date(deadline_match.group(1)) if deadline_match else ""
    if status == "open" and deadline and deadline < (datetime.now(timezone.utc) - timedelta(hours=14)).date().isoformat():
        status = "closed"
    names = [text for tag, text in notice.blocks if tag == "h1" and text]
    journal = next((text for href, text in notice.links if text and re.fullmatch(
        r"/journal/\d+", urlsplit(urljoin(url, href)).path
    )), "")
    scope = next((text for tag, text in notice.blocks if tag == "p" and len(text) > 160), "")
    if not scope:
        scope = notice.meta.get("description", "")
    issn = re.search(r"\b\d{4}-\d{3}[\dX]\b", content, re.I)
    types = re.search(r"\b(?:accepted article types|manuscript types)\s*:\s*([^.;]{4,160})", content, re.I)
    fees = re.search(r"\b(?:no (?:submission (?:or publication )?|publication )fees|(?:article processing charge|publication fee)\s*[: ]\s*(?:EUR|USD|GBP|TRY|€|\$|£)\s*[\d,.]+)\b", content, re.I)
    calls = []
    for href, label in notice.links if follow_calls else ():
        call_url = urljoin(url, href)
        if (not urlsplit(url).hostname == "dergipark.org.tr" or "/announcements/" in url
                or "/announcements/" not in call_url or not official_page(call_url)
                or not re.search(r"call for papers|special issue|özel sayı", label, re.I)):
            continue
        checked = verify_notice(call_url)
        calls.append({**checked, "title": checked.get("title") or label, "kind": "special_issue",
                      "venue": names[0] if names else journal})
        if len(calls) >= 2:
            break
    return {
        **base, "calls": calls, **_labeled_links(notice, url), "status": status, "deadline": deadline,
        "title": (names[0] if names else notice.meta.get("og:title", ""))[:280],
        "venue": journal[:280],
        "scope": scope[:350], "issn": issn.group(0).upper() if issn else "",
        "article_types": types.group(1).strip() if types else "", "fees": fees.group(0) if fees else "",
        "evidence": " · ".join(match.group(0) for match in (status_match, deadline_match) if match)[:350],
    }


def _public_homepage(value):
    if not isinstance(value, str):
        return ""
    url = value.strip()
    if url.startswith("http://"):
        url = "https://" + url[7:]
    return url if public_url(url) else ""


def _related_journal(searcher, source):
    source_id, count, label = source
    journal = searcher.resolve_journal(source_id) or {}
    homepage = _public_homepage(journal.get("homepage_url"))
    row = {
        "title": journal.get("display_name") or label, "venue": journal.get("display_name") or label,
        "kind": "regular", "source_url": homepage, "metadata_url": f"https://openalex.org/{source_id}",
        "issn": journal.get("issn_l") or "", "sample_count": count,
        "status": "unverified", "checked_at": "", "verification": "unverified",
    }
    if not official_page(homepage):
        return [row]
    checked = verify_notice(homepage)
    row.update({key: checked[key] for key in (
        "status", "checked_at", "verification", "deadline", "submission_url", "guidelines_url",
        "fees_url", "fees", "article_types", "scope", "evidence",
    ) if checked.get(key)})
    return [row, *checked.get("calls", [])]


def find_calls(query, searcher):
    portals = [
        {**OFFICIAL_PORTALS[0], "url": f"{SPRINGER_SEARCH}?{urlencode({'content-type': 'call for papers', 'new-search': 'true', 'query': query})}"},
        *OFFICIAL_PORTALS[1:],
    ]
    searcher.clear_last_failure()
    data = searcher._make_request(f"{searcher.BASE_URL}/works", {
        "search": query, "filter": "is_retracted:false,type:article|review",
        "select": "primary_location", "per_page": 50, "mailto": searcher.email,
    })
    if not data or not isinstance(data.get("results"), list):
        failure = searcher.last_failure or {"message": "OpenAlex returned an invalid response."}
        return {"items": [], "sources": portals, "error": failure["message"]}
    counts = Counter()
    names = {}
    for work in data["results"]:
        source = (work.get("primary_location") or {}).get("source") or {}
        source_id = str(source.get("id") or "").rsplit("/", 1)[-1]
        if re.fullmatch(r"S\d+", source_id) and source.get("type") == "journal":
            counts[source_id] += 1
            names[source_id] = source.get("display_name") or source_id
    rows = []
    with ThreadPoolExecutor(max_workers=3) as pool:
        for group in pool.map(lambda item: _related_journal(searcher, item),
                              [(key, count, names[key]) for key, count in counts.most_common(6)]):
            rows.extend(group)
    return {"items": sorted(rows, key=lambda row: row["status"] != "open"), "sources": portals,
            "sample_size": len(data["results"])}
