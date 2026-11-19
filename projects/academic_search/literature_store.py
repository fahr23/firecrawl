"""Persistent literature library and ranked search cache in the project database."""

from datetime import datetime, timezone
import json
import re
import sqlite3
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple
from urllib.parse import urlsplit, urlunsplit


_SCHEMA = """
CREATE TABLE IF NOT EXISTS literature_works (
    id INTEGER PRIMARY KEY,
    doi TEXT UNIQUE,
    title TEXT NOT NULL,
    authors TEXT NOT NULL DEFAULT '',
    abstract TEXT NOT NULL DEFAULT '',
    journal TEXT NOT NULL DEFAULT '',
    keywords TEXT NOT NULL DEFAULT '',
    publication_year INTEGER,
    category TEXT NOT NULL,
    first_seen_at TEXT NOT NULL,
    last_seen_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS literature_works_year_category
    ON literature_works(publication_year, category);
CREATE TABLE IF NOT EXISTS literature_urls (
    url TEXT PRIMARY KEY,
    work_id INTEGER NOT NULL REFERENCES literature_works(id)
);
CREATE TABLE IF NOT EXISTS literature_observations (
    id INTEGER PRIMARY KEY,
    work_id INTEGER NOT NULL REFERENCES literature_works(id),
    provider TEXT NOT NULL COLLATE NOCASE,
    url TEXT NOT NULL,
    observed_at TEXT NOT NULL,
    has_abstract INTEGER NOT NULL CHECK (has_abstract IN (0, 1)),
    record_json TEXT NOT NULL,
    UNIQUE(work_id, provider, url)
);
CREATE INDEX IF NOT EXISTS literature_observations_provider
    ON literature_observations(provider, work_id);
CREATE TABLE IF NOT EXISTS literature_queries (
    id INTEGER PRIMARY KEY,
    signature TEXT NOT NULL UNIQUE
);
CREATE TABLE IF NOT EXISTS literature_query_pages (
    id INTEGER PRIMARY KEY,
    query_id INTEGER NOT NULL REFERENCES literature_queries(id),
    page INTEGER NOT NULL CHECK (page > 0),
    page_size INTEGER NOT NULL CHECK (page_size > 0),
    fetched_at TEXT NOT NULL,
    metadata_json TEXT NOT NULL,
    UNIQUE(query_id, page, page_size)
);
CREATE TABLE IF NOT EXISTS literature_query_hits (
    page_id INTEGER NOT NULL REFERENCES literature_query_pages(id) ON DELETE CASCADE,
    rank INTEGER NOT NULL CHECK (rank >= 0),
    observation_id INTEGER NOT NULL REFERENCES literature_observations(id),
    PRIMARY KEY(page_id, rank)
);
CREATE TABLE IF NOT EXISTS literature_migrations (
    name TEXT PRIMARY KEY,
    applied_at TEXT NOT NULL
);

CREATE VIRTUAL TABLE IF NOT EXISTS literature_fts USING fts5(
    title, abstract, authors, journal, keywords,
    content='literature_works', content_rowid='id', tokenize='unicode61'
);
CREATE TRIGGER IF NOT EXISTS literature_works_insert AFTER INSERT ON literature_works BEGIN
    INSERT INTO literature_fts(rowid, title, abstract, authors, journal, keywords)
    VALUES (new.id, new.title, new.abstract, new.authors, new.journal, new.keywords);
END;
CREATE TRIGGER IF NOT EXISTS literature_works_update
AFTER UPDATE OF title, abstract, authors, journal, keywords ON literature_works
WHEN old.title != new.title OR old.abstract != new.abstract OR old.authors != new.authors
     OR old.journal != new.journal OR old.keywords != new.keywords
BEGIN
    INSERT INTO literature_fts(literature_fts, rowid, title, abstract, authors, journal, keywords)
    VALUES ('delete', old.id, old.title, old.abstract, old.authors, old.journal, old.keywords);
    INSERT INTO literature_fts(rowid, title, abstract, authors, journal, keywords)
    VALUES (new.id, new.title, new.abstract, new.authors, new.journal, new.keywords);
END;
CREATE TRIGGER IF NOT EXISTS literature_works_delete AFTER DELETE ON literature_works BEGIN
    INSERT INTO literature_fts(literature_fts, rowid, title, abstract, authors, journal, keywords)
    VALUES ('delete', old.id, old.title, old.abstract, old.authors, old.journal, old.keywords);
END;
"""

# Keep the query grammar intentionally small: library search accepts text, a quoted
# phrase, or an exact DOI. Provider-specific operators still go to the remote APIs.
_DOI = re.compile(r"10\.\d{4,9}/\S+", re.IGNORECASE)
_TOKEN = re.compile(r"[^\W_]+", re.UNICODE)
_SAVED_METADATA = (
    "query", "category", "category_provenance", "providers_requested", "sources_responded",
    "provider_outcomes", "retrieved_at", "search_time", "total_provider_matches", "year_min",
    "year_max", "limit", "page", "has_more", "pagination", "provider_coverage", "manifest",
)


def now_utc() -> str:
    return datetime.now(timezone.utc).isoformat()


def _time(value: Any) -> str:
    try:
        stamp = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if stamp.tzinfo is None:
            stamp = stamp.replace(tzinfo=timezone.utc)
        return stamp.astimezone(timezone.utc).isoformat()
    except (AttributeError, TypeError, ValueError, OverflowError):
        return now_utc()


def _text(value: Any) -> str:
    return value.strip() if isinstance(value, str) else ""


def _doi(value: Any) -> Optional[str]:
    candidate = _text(value).lower().removeprefix("https://doi.org/").removeprefix("http://doi.org/").removeprefix("doi:").strip()
    return candidate if _DOI.fullmatch(candidate) else None


def _url(value: Any) -> Optional[str]:
    if not isinstance(value, str) or not value or re.search(r"[\\\x00-\x20]", value):
        return None
    try:
        parsed = urlsplit(value)
        if parsed.scheme not in ("http", "https") or not parsed.hostname or parsed.username or parsed.password:
            return None
        host = parsed.netloc.lower().removesuffix(":443") if parsed.scheme == "https" else parsed.netloc.lower().removesuffix(":80")
        # Keep query strings and paths. Some repositories identify the paper there.
        return urlunsplit((parsed.scheme, host, parsed.path.rstrip("/") or "/", parsed.query, ""))
    except ValueError:
        return None


def _fts_query(text: str) -> Optional[str]:
    clauses = []
    for part in re.findall(r'"[^"]+"|[^\s"]+', text):
        if part in {"AND", "OR", "NOT"}:
            continue
        tokens = _TOKEN.findall(part)
        if tokens:
            clauses.append('"' + " ".join(tokens) + '"' if part.startswith('"')
                           else " AND ".join(f'"{token}"' for token in tokens))
    return " AND ".join(clauses) if clauses else None


class LiteratureStore:
    """The library owns searchable paper metadata. Project receipts remain independent."""

    def __init__(self, connection: sqlite3.Connection, lock) -> None:
        self._connection = connection
        self._lock = lock
        with self._lock:
            self._connection.executescript(_SCHEMA)

    @staticmethod
    def signature(query: str, category: str, providers: Sequence[str], year_min, year_max) -> str:
        # Provider order can affect ranking. Search syntax is kept exactly as sent.
        return json.dumps([query, category, list(providers), year_min, year_max], ensure_ascii=False, separators=(",", ":"))

    def _work_for_paper(self, paper: Dict[str, Any], stamp: str, normalized_url: str) -> Tuple[int, bool]:
        db = self._connection
        doi = _doi(paper.get("doi")) or _doi(normalized_url)
        match = db.execute("SELECT id, doi FROM literature_works WHERE doi = ?", (doi,)).fetchone() if doi else None
        alias = db.execute(
            "SELECT w.id, w.doi FROM literature_urls AS u JOIN literature_works AS w ON w.id = u.work_id WHERE u.url = ?",
            (normalized_url,),
        ).fetchone()
        if not match and alias and (not doi or not alias["doi"] or alias["doi"] == doi):
            match = alias
        try:
            year = int(paper.get("year"))
        except (ValueError, TypeError):
            year = None
        fields = (
            _text(paper.get("title")), _text(paper.get("authors")), _text(paper.get("abstract")),
            _text(paper.get("journal")),
            " ".join(item for item in (paper.get("keywords") or []) if isinstance(item, str)),
            year, _text(paper.get("category")) or "multidisciplinary",
        )
        if match:
            work_id = match["id"]
            db.execute(
                """UPDATE literature_works SET doi = COALESCE(doi, ?),
                     title = CASE WHEN ? >= last_seen_at THEN COALESCE(NULLIF(?, ''), title) ELSE title END,
                     authors = CASE WHEN ? >= last_seen_at OR authors = '' THEN COALESCE(NULLIF(?, ''), authors) ELSE authors END,
                     abstract = CASE WHEN ? >= last_seen_at OR abstract = '' THEN COALESCE(NULLIF(?, ''), abstract) ELSE abstract END,
                     journal = CASE WHEN ? >= last_seen_at OR journal = '' THEN COALESCE(NULLIF(?, ''), journal) ELSE journal END,
                     keywords = CASE WHEN ? >= last_seen_at OR keywords = '' THEN COALESCE(NULLIF(?, ''), keywords) ELSE keywords END,
                     publication_year = CASE WHEN ? >= last_seen_at OR publication_year IS NULL THEN COALESCE(?, publication_year) ELSE publication_year END,
                     category = CASE WHEN ? >= last_seen_at THEN ? ELSE category END,
                     first_seen_at = MIN(first_seen_at, ?), last_seen_at = MAX(last_seen_at, ?)
                   WHERE id = ?""",
                (doi, *(value for field in fields for value in (stamp, field)), stamp, stamp, work_id),
            )
        else:
            work_id = db.execute(
                """INSERT INTO literature_works
                   (doi, title, authors, abstract, journal, keywords, publication_year, category, first_seen_at, last_seen_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""", (doi, *fields, stamp, stamp),
            ).lastrowid
        # A publisher sometimes reuses the same URL for different articles. An explicit
        # conflicting DOI keeps its own work record and cannot steal the existing alias.
        db.execute("INSERT OR IGNORE INTO literature_urls VALUES (?, ?)", (normalized_url, work_id))
        return work_id, match is None

    def _observe(self, paper: Dict[str, Any], stamp: str) -> Optional[Tuple[int, int, bool]]:
        if not isinstance(paper, dict) or not _text(paper.get("title")):
            return None
        normalized = _url(paper.get("url"))
        if not normalized:
            return None
        work_id, created = self._work_for_paper(paper, stamp, normalized)
        db = self._connection
        provider = _text(paper.get("source")) or "Unknown"
        db.execute(
            """INSERT INTO literature_observations(work_id, provider, url, observed_at, has_abstract, record_json)
               VALUES (?, ?, ?, ?, ?, ?) ON CONFLICT(work_id, provider, url) DO UPDATE SET
                 observed_at = excluded.observed_at,
                 has_abstract = excluded.has_abstract,
                 record_json = excluded.record_json
               WHERE excluded.observed_at >= literature_observations.observed_at""",
            (work_id, provider, paper["url"], stamp, int(bool(_text(paper.get("abstract")))), json.dumps(paper, ensure_ascii=False)),
        )
        row = db.execute(
            "SELECT id FROM literature_observations WHERE work_id = ? AND provider = ? AND url = ?",
            (work_id, provider, paper["url"]),
        ).fetchone()
        return work_id, row["id"], created

    def _write_page(self, signature, payload, stamp, observations):
        db = self._connection
        db.execute("INSERT OR IGNORE INTO literature_queries(signature) VALUES (?)", (signature,))
        query_id = db.execute("SELECT id FROM literature_queries WHERE signature = ?", (signature,)).fetchone()[0]
        metadata = json.dumps({field: payload[field] for field in _SAVED_METADATA if field in payload}, ensure_ascii=False)
        page, limit = payload["page"], payload["limit"]
        cursor = db.execute(
            """INSERT INTO literature_query_pages(query_id, page, page_size, fetched_at, metadata_json)
               VALUES (?, ?, ?, ?, ?) ON CONFLICT(query_id, page, page_size) DO UPDATE SET
                 fetched_at = excluded.fetched_at, metadata_json = excluded.metadata_json
               WHERE excluded.fetched_at >= literature_query_pages.fetched_at""",
            (query_id, page, limit, stamp, metadata),
        )
        if not cursor.rowcount:
            return
        page_id = db.execute(
            "SELECT id FROM literature_query_pages WHERE query_id = ? AND page = ? AND page_size = ?",
            (query_id, page, limit),
        ).fetchone()[0]
        db.execute("DELETE FROM literature_query_hits WHERE page_id = ?", (page_id,))
        db.executemany(
            "INSERT INTO literature_query_hits VALUES (?, ?, ?)",
            ((page_id, rank, observation) for rank, observation in enumerate(observations)),
        )

    def save_search(self, signature: str, payload: Dict[str, Any], candidates: Iterable[Dict[str, Any]], complete: bool):
        stamp = _time(payload.get("retrieved_at"))
        new_work_ids = set()
        with self._lock, self._connection:
            self._connection.execute("BEGIN IMMEDIATE")
            observed = self._observe_many(candidates, stamp, new_work_ids)
            observations = []
            for paper in payload["results"]:
                key = self._key(paper)
                if key in observed:
                    work_id, observation_id = observed[key]
                    observations.append(observation_id)
                    paper["library_id"] = str(work_id)
            if complete:
                self._write_page(signature, payload, stamp, observations)
        return new_work_ids

    @staticmethod
    def _key(paper):
        return (_text(paper.get("source")).casefold(), paper.get("url"), _doi(paper.get("doi")))

    def _observe_many(self, papers: Iterable[Dict[str, Any]], stamp: str, new_work_ids=None):
        observed = {}
        for paper in papers:
            ids = self._observe(paper, stamp)
            if ids:
                work_id, observation_id, created = ids
                observed[self._key(paper)] = (work_id, observation_id)
                if created and new_work_ids is not None:
                    new_work_ids.add(str(work_id))
        return observed

    def observe(self, papers: List[Dict[str, Any]], retrieved_at: str) -> None:
        if not papers:
            return
        with self._lock, self._connection:
            self._connection.execute("BEGIN IMMEDIATE")
            self._observe_many(papers, _time(retrieved_at))

    @staticmethod
    def _paper(row):
        return {**json.loads(row["record_json"]), "library_id": str(row["work_id"]), "library_observed_at": row["observed_at"]}

    def cached_page(self, signature: str, page: int, limit: int) -> Optional[Dict[str, Any]]:
        with self._lock:
            cache = self._connection.execute(
                """SELECT p.id, p.fetched_at, p.metadata_json FROM literature_query_pages AS p
                   JOIN literature_queries AS q ON q.id = p.query_id
                   WHERE q.signature = ? AND p.page = ? AND p.page_size = ?""",
                (signature, page, limit),
            ).fetchone()
            if not cache:
                return None
            rows = self._connection.execute(
                """SELECT o.work_id, o.observed_at, o.record_json FROM literature_query_hits AS h
                   JOIN literature_observations AS o ON o.id = h.observation_id
                   WHERE h.page_id = ? ORDER BY h.rank""", (cache["id"],),
            ).fetchall()
        return {**json.loads(cache["metadata_json"]), "cache_fetched_at": cache["fetched_at"],
                "results": [self._paper(row) for row in rows]}

    def search(self, query: str, category: str, providers: Sequence[str], year_min, year_max,
               limit: int, offset: int, *, for_daily: bool = False) -> List[Dict[str, Any]]:
        doi = _doi(query)
        match = _fts_query(query) if not doi else None
        if not doi and not match:
            return []
        conditions, parameters = [], []
        if doi:
            conditions.append("w.doi = ?")
            parameters.append(doi)
        else:
            conditions.append("literature_fts MATCH ?")
            parameters.append(match)
        if category != "all":
            conditions.append("w.category = ?")
            parameters.append(category)
        if year_min is not None:
            conditions.append("w.publication_year >= ?")
            parameters.append(year_min)
        if year_max is not None:
            conditions.append("w.publication_year <= ?")
            parameters.append(year_max)
        if for_daily:
            conditions.extend((
                "NOT EXISTS (SELECT 1 FROM daily_reading_papers d WHERE d.work_id = w.id)",
                "NOT EXISTS (SELECT 1 FROM paper_reading r WHERE r.work_id = w.id AND r.read_at IS NOT NULL)",
                "NOT EXISTS (SELECT 1 FROM paper_open_events e WHERE e.work_id = w.id)",
            ))
        provider_clause = ""
        provider_params = []
        if providers:
            placeholders = ",".join("?" for _ in providers)
            provider_clause = f" AND o.provider IN ({placeholders})"
            provider_params.extend(providers)
        index_join = "" if doi else "JOIN literature_fts ON literature_fts.rowid = w.id"
        order = "w.id" if doi else "bm25(literature_fts, 5, 1, 2, 2, 2), w.last_seen_at DESC, w.id"
        if for_daily:
            order = f"w.publication_year DESC, json_extract(selected.record_json, '$.publication_date') DESC, {order}"
        sql = f"""
            SELECT selected.work_id, selected.observed_at, selected.record_json FROM literature_works AS w
            {index_join} JOIN literature_observations AS selected ON selected.id = (
                SELECT o.id FROM literature_observations AS o WHERE o.work_id = w.id {provider_clause}
                ORDER BY o.has_abstract DESC, o.observed_at DESC, o.id LIMIT 1
            )
            WHERE {" AND ".join(conditions)} ORDER BY {order} LIMIT ? OFFSET ?
        """
        with self._lock:
            rows = self._connection.execute(sql, (*provider_params, *parameters, limit, offset)).fetchall()
        return [self._paper(row) for row in rows]

    def paper(self, work_id: str, url: str) -> Optional[Dict[str, Any]]:
        with self._lock:
            row = self._connection.execute(
                """SELECT work_id, observed_at, record_json FROM literature_observations
                   WHERE work_id = ? AND url = ? ORDER BY observed_at DESC, id LIMIT 1""", (work_id, url),
            ).fetchone()
        return self._paper(row) if row else None

    def status(self) -> Dict[str, Any]:
        with self._lock:
            row = self._connection.execute(
                """SELECT (SELECT count(*) FROM literature_works) AS works,
                          count(*) AS observations, max(observed_at) AS last_saved_at
                   FROM literature_observations"""
            ).fetchone()
        return dict(row)

    def import_project_history(self) -> None:
        """Index historical paper observations once without rewriting project evidence."""
        name = "project-evidence-library-v1"
        db = self._connection
        with self._lock, db:
            db.execute("BEGIN IMMEDIATE")
            if db.execute("SELECT 1 FROM literature_migrations WHERE name = ?", (name,)).fetchone():
                return
            sources = (
                ("SELECT retrieved_at, results_json FROM search_runs ORDER BY retrieved_at", None),
                ("SELECT retrieved_at, papers_json FROM journal_search_runs ORDER BY retrieved_at", None),
                ("SELECT updated_at, data_json FROM workspace_revisions WHERE section IN ('search-page', 'discovery', 'discovery-papers', 'reading') ORDER BY updated_at", "workspace"),
            )
            for statement, kind in sources:
                for stamp, raw in db.execute(statement):
                    data = json.loads(raw)
                    if kind:
                        stamp = data.get("retrieved_at") or stamp
                        data = data.get("papers") or data.get("results") or ([data["paper"]] if data.get("paper") else [])
                    if isinstance(data, list):
                        self._observe_many(data, _time(stamp))
            db.execute("INSERT INTO literature_migrations VALUES (?, ?)", (name, now_utc()))
