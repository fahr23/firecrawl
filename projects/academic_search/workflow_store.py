"""Durable research watches, paper activity, and shared portfolio evidence."""

from datetime import datetime, timedelta
import json
import uuid
from urllib.parse import unquote

from .literature_store import _doi, _url, now_utc


SCHEMA = """
CREATE TABLE IF NOT EXISTS research_watches (
    id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL REFERENCES research_projects(id),
    signature TEXT NOT NULL,
    label TEXT NOT NULL,
    filters_json TEXT NOT NULL,
    interval_hours INTEGER NOT NULL,
    created_at TEXT NOT NULL,
    due_at TEXT NOT NULL,
    refresh_token TEXT,
    last_attempt_at TEXT,
    last_success_at TEXT,
    coverage_json TEXT NOT NULL DEFAULT '[]',
    UNIQUE(project_id, signature)
);
CREATE INDEX IF NOT EXISTS research_watches_due ON research_watches(interval_hours, due_at);
CREATE TABLE IF NOT EXISTS research_watch_hits (
    watch_id TEXT NOT NULL REFERENCES research_watches(id) ON DELETE CASCADE,
    work_id INTEGER NOT NULL REFERENCES literature_works(id),
    discovered_at TEXT NOT NULL,
    freshness TEXT NOT NULL CHECK (freshness IN ('baseline', 'recent', 'discovered', 'known')),
    seen_at TEXT,
    PRIMARY KEY(watch_id, work_id)
);
CREATE INDEX IF NOT EXISTS research_watch_inbox ON research_watch_hits(watch_id, seen_at, discovered_at);
CREATE TABLE IF NOT EXISTS paper_reading (
    work_id INTEGER PRIMARY KEY REFERENCES literature_works(id),
    read_at TEXT,
    updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS paper_open_events (
    id TEXT PRIMARY KEY,
    work_id INTEGER NOT NULL REFERENCES literature_works(id),
    url TEXT NOT NULL,
    opened_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS paper_open_events_work ON paper_open_events(work_id, opened_at DESC);
CREATE TABLE IF NOT EXISTS portfolio_activities (
    id TEXT PRIMARY KEY,
    revision INTEGER NOT NULL,
    data_json TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    source_project_id TEXT REFERENCES research_projects(id),
    source_item_id TEXT,
    UNIQUE(source_project_id, source_item_id)
);
CREATE TABLE IF NOT EXISTS portfolio_activity_versions (
    activity_id TEXT NOT NULL REFERENCES portfolio_activities(id),
    revision INTEGER NOT NULL,
    data_json TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    PRIMARY KEY(activity_id, revision)
);
"""


def _after(stamp, hours):
    return (datetime.fromisoformat(stamp) + timedelta(hours=hours)).isoformat()


def _watch(row):
    item = dict(row)
    item["filters"] = json.loads(item.pop("filters_json"))
    item["coverage"] = json.loads(item.pop("coverage_json"))
    item["refreshing"] = bool(item.pop("refresh_token"))
    return item


class WorkflowStore:
    def __init__(self, store):
        self.store = store
        self.db = store._connection
        self.lock = store._lock
        with self.lock:
            self.db.executescript(SCHEMA)
        self._import_portfolio()

    def _import_portfolio(self):
        with self.lock, self.db:
            self.db.execute("BEGIN IMMEDIATE")
            rows = self.db.execute(
                """SELECT w.project_id, w.id, w.updated_at, w.data_json FROM workspace_revisions AS w
                   JOIN (SELECT project_id, id, MAX(revision) AS revision FROM workspace_revisions
                         WHERE section = 'dossier-activities' GROUP BY project_id, id) AS recent
                     ON w.project_id = recent.project_id AND w.id = recent.id AND w.revision = recent.revision
                   WHERE w.section = 'dossier-activities'"""
            ).fetchall()
            for row in rows:
                if self.db.execute(
                    "SELECT 1 FROM portfolio_activities WHERE source_project_id = ? AND source_item_id = ?",
                    (row["project_id"], row["id"]),
                ).fetchone():
                    continue
                self.import_activity(row["project_id"], row["id"], json.loads(row["data_json"]), row["updated_at"])

    def import_activity(self, project_id, item_id, data, updated_at):
        activity = {**data, "reading_id": ""}
        if data.get("reading_id"):
            source = self.store.workspace_history(project_id, "reading", data["reading_id"], 1)
            if source:
                activity["paper"] = source[0]["data"]["paper"]
        key = str(uuid.uuid5(uuid.NAMESPACE_OID, f"{project_id}:{item_id}"))
        # The shared copy stays editable even as the source topic keeps its own revisions.
        self.db.execute(
            """INSERT OR IGNORE INTO portfolio_activities VALUES (?, 1, ?, ?, ?, ?)""",
            (key, json.dumps(activity, ensure_ascii=False), updated_at, project_id, item_id),
        )
        self._archive_activity(key)

    def _archive_activity(self, item_id):
        self.db.execute(
            """INSERT OR IGNORE INTO portfolio_activity_versions
               SELECT id, revision, data_json, updated_at FROM portfolio_activities WHERE id = ?""", (item_id,),
        )

    @staticmethod
    def _activity(row):
        item = dict(row)
        item["data"] = json.loads(item.pop("data_json"))
        return item

    def portfolio(self):
        with self.lock:
            rows = self.db.execute("SELECT * FROM portfolio_activities ORDER BY updated_at DESC, id").fetchall()
            return [self._activity(row) for row in rows]

    def portfolio_item(self, item_id):
        with self.lock:
            row = self.db.execute("SELECT * FROM portfolio_activities WHERE id = ?", (item_id,)).fetchone()
            return self._activity(row) if row else None

    def portfolio_history(self, item_id):
        with self.lock:
            rows = self.db.execute(
                """SELECT revision, data_json, updated_at FROM portfolio_activity_versions
                   WHERE activity_id = ? ORDER BY revision DESC""", (item_id,),
            ).fetchall()
            return [self._activity(row) for row in rows]

    def save_activity(self, data, item_id=None, revision=0):
        with self.lock, self.db:
            stamp = now_utc()
            if item_id:
                cursor = self.db.execute(
                    """UPDATE portfolio_activities SET data_json = ?, updated_at = ?, revision = revision + 1
                       WHERE id = ? AND revision = ?""",
                    (json.dumps(data, ensure_ascii=False), stamp, item_id, revision),
                )
                if not cursor.rowcount:
                    return None
            else:
                item_id = str(uuid.uuid4())
                self.db.execute(
                    "INSERT INTO portfolio_activities VALUES (?, 1, ?, ?, NULL, NULL)",
                    (item_id, json.dumps(data, ensure_ascii=False), stamp),
                )
            self._archive_activity(item_id)
            return self.portfolio_item(item_id)

    def save_watch(self, project_id, signature, label, filters, interval_hours, baseline):
        stamp = now_utc()
        watch_id = str(uuid.uuid4())
        with self.lock, self.db:
            self.db.execute("BEGIN IMMEDIATE")
            cursor = self.db.execute(
                """INSERT OR IGNORE INTO research_watches
                   (id, project_id, signature, label, filters_json, interval_hours, created_at, due_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                (watch_id, project_id, signature, label, json.dumps(filters), interval_hours, stamp, stamp),
            )
            if not cursor.rowcount:
                watch_id = self.db.execute(
                    "SELECT id FROM research_watches WHERE project_id = ? AND signature = ?",
                    (project_id, signature),
                ).fetchone()["id"]
            else:
                self.db.executemany(
                    """INSERT OR IGNORE INTO research_watch_hits VALUES (?, ?, ?, 'baseline', ?)""",
                    ((watch_id, paper["library_id"], stamp, stamp) for paper in baseline if paper.get("library_id")),
                )
            return self.watch(project_id, watch_id)

    def watch(self, project_id, watch_id):
        with self.lock:
            row = self.db.execute(
                """SELECT w.*, (SELECT count(*) FROM research_watch_hits h WHERE h.watch_id = w.id
                                 AND h.seen_at IS NULL) AS unread FROM research_watches w
                   WHERE w.project_id = ? AND w.id = ?""", (project_id, watch_id),
            ).fetchone()
            return _watch(row) if row else None

    def configure_watch(self, project_id, watch_id, label, interval_hours):
        with self.lock, self.db:
            stamp = now_utc()
            self.db.execute(
                """UPDATE research_watches SET label = ?, interval_hours = ?, due_at = ?
                   WHERE project_id = ? AND id = ?""", (label, interval_hours, _after(stamp, interval_hours), project_id, watch_id),
            )
            return self.watch(project_id, watch_id)

    def delete_watch(self, project_id, watch_id):
        with self.lock, self.db:
            return bool(self.db.execute(
                "DELETE FROM research_watches WHERE project_id = ? AND id = ?", (project_id, watch_id),
            ).rowcount)

    def watches(self, project_id=None):
        where, params = ("WHERE w.project_id = ?", (project_id,)) if project_id else ("", ())
        with self.lock:
            rows = self.db.execute(
                f"""SELECT w.*, count(h.work_id) AS unread FROM research_watches w
                    LEFT JOIN research_watch_hits h ON h.watch_id = w.id AND h.seen_at IS NULL
                    {where} GROUP BY w.id ORDER BY w.created_at DESC""", params,
            ).fetchall()
            return [_watch(row) for row in rows]

    def unread_counts(self):
        with self.lock:
            rows = self.db.execute(
                """SELECT w.project_id, count(DISTINCT h.work_id) AS unread
                   FROM research_watch_hits h JOIN research_watches w ON w.id = h.watch_id
                   WHERE h.seen_at IS NULL GROUP BY w.project_id""",
            ).fetchall()
            return {row["project_id"]: row["unread"] for row in rows}

    def due(self, limit=2):
        stamp = now_utc()
        with self.lock:
            rows = self.db.execute(
                """SELECT project_id, id FROM research_watches
                   WHERE interval_hours > 0 AND due_at <= ?
                     AND (refresh_token IS NULL OR last_attempt_at < ?) ORDER BY due_at LIMIT ?""",
                (stamp, _after(stamp, -1), limit),
            ).fetchall()
            return [tuple(row) for row in rows]

    def claim_watch(self, project_id, watch_id):
        stamp, token = now_utc(), str(uuid.uuid4())
        with self.lock, self.db:
            cursor = self.db.execute(
                """UPDATE research_watches SET refresh_token = ?, last_attempt_at = ?
                   WHERE project_id = ? AND id = ? AND (refresh_token IS NULL OR last_attempt_at < ?)""",
                (token, stamp, project_id, watch_id, _after(stamp, -1)),
            )
            return token if cursor.rowcount else None

    def finish_watch(self, watch_id, token, results, coverage, complete, new_work_ids=()):
        stamp = now_utc()
        with self.lock, self.db:
            self.db.execute("BEGIN IMMEDIATE")
            row = self.db.execute(
                "SELECT interval_hours FROM research_watches WHERE id = ? AND refresh_token = ?",
                (watch_id, token),
            ).fetchone()
            if not row:
                return 0
            added = 0
            cutoff = (datetime.fromisoformat(stamp).date() - timedelta(days=30)).isoformat()
            for paper in results:
                if not paper.get("library_id") or paper.get("retrieval_kind") == "saved":
                    continue
                work_id = paper["library_id"]
                published = paper.get("publication_date") or ""
                freshness = "recent" if cutoff <= published <= stamp[:10] else (
                    "discovered" if work_id in new_work_ids else "known"
                )
                activity = self.paper_state(work_id)
                seen_at = activity["read_at"] or activity["last_opened_at"]
                cursor = self.db.execute(
                    """INSERT OR IGNORE INTO research_watch_hits VALUES (?, ?, ?, ?, ?)""",
                    (watch_id, work_id, stamp, freshness, seen_at),
                )
                added += cursor.rowcount
            self.db.execute(
                """UPDATE research_watches SET refresh_token = NULL, coverage_json = ?,
                   last_success_at = COALESCE(?, last_success_at), due_at = ? WHERE id = ?""",
                (json.dumps(coverage), stamp if complete else None,
                 _after(stamp, row["interval_hours"] if complete else min(row["interval_hours"], 6)), watch_id),
            )
            return added

    def mark_seen(self, project_id, watch_id, work_id=None):
        with self.lock, self.db:
            if work_id is not None:
                return self.db.execute(
                    """UPDATE research_watch_hits SET seen_at = ? WHERE seen_at IS NULL AND work_id = ?
                       AND watch_id IN (SELECT id FROM research_watches WHERE project_id = ?)""",
                    (now_utc(), work_id, project_id),
                ).rowcount
            return self.db.execute(
                """UPDATE research_watch_hits SET seen_at = ? WHERE seen_at IS NULL AND watch_id = (
                       SELECT id FROM research_watches WHERE id = ? AND project_id = ?
                   )""",
                (now_utc(), watch_id, project_id),
            ).rowcount

    def inbox(self, project_id, limit, unread_only):
        project = "AND w.project_id = ?" if project_id else ""
        unread = "AND h.seen_at IS NULL" if unread_only else ""
        params = (project_id, limit) if project_id else (limit,)
        with self.lock:
            rows = self.db.execute(
                f"""WITH matches AS (
                        SELECT h.*, w.project_id, w.label,
                            row_number() OVER (PARTITION BY w.project_id, h.work_id
                                ORDER BY h.seen_at IS NOT NULL, h.discovered_at DESC, h.watch_id) AS position
                          FROM research_watch_hits h JOIN research_watches w ON w.id = h.watch_id
                         WHERE h.freshness != 'baseline' {project} {unread}
                    )
                    SELECT m.*, p.name AS project_name, o.observed_at, o.record_json FROM matches m
                    JOIN research_projects p ON p.id = m.project_id
                    JOIN literature_observations o ON o.id = (
                       SELECT candidate.id FROM literature_observations candidate WHERE candidate.work_id = m.work_id
                       ORDER BY candidate.has_abstract DESC, candidate.observed_at DESC, candidate.id LIMIT 1
                    )
                    WHERE m.position = 1 ORDER BY m.seen_at IS NOT NULL, m.discovered_at DESC, m.work_id DESC LIMIT ?""", params,
            ).fetchall()
            return [{key: row[key] for key in row.keys() if key not in {"observed_at", "record_json", "work_id", "position"}}
                    | {"paper": self.store.literature._paper(row)} for row in rows]

    def identify_paper(self, url, doi=None):
        normalized = _url(url)
        if not normalized:
            return None
        with self.lock:
            row = self.db.execute(
                """SELECT work_id FROM literature_urls WHERE url = ?""", (normalized,),
            ).fetchone()
            url_doi = _doi(unquote(normalized).replace("://dx.doi.org/", "://doi.org/", 1))
            doi = _doi(doi) or url_doi
            if doi:
                match = self.db.execute("SELECT id FROM literature_works WHERE doi = ?", (doi,)).fetchone()
                if match and (not row or match["id"] != row["work_id"]):
                    known = self.db.execute(
                        "SELECT 1 FROM literature_observations WHERE work_id = ? AND url = ?",
                        (match["id"], url),
                    ).fetchone()
                    if known or url_doi == doi:
                        return match["id"]
            return row["work_id"] if row else None

    def paper_state(self, work_id):
        with self.lock:
            row = self.db.execute(
                """SELECT count(*) AS open_count, max(opened_at) AS last_opened_at,
                          (SELECT read_at FROM paper_reading WHERE work_id = ?) AS read_at,
                          (SELECT updated_at FROM paper_reading WHERE work_id = ?) AS read_updated_at
                   FROM paper_open_events WHERE work_id = ?""", (work_id, work_id, work_id),
            ).fetchone()
            state = dict(row)
            state["updated_at"] = max(filter(None, (state.pop("read_updated_at"), state["last_opened_at"])), default=None)
            return {"library_id": str(work_id), **state}

    def open_paper(self, work_id, url, event_id):
        with self.lock, self.db:
            stamp = now_utc()
            recorded = self.db.execute(
                "INSERT OR IGNORE INTO paper_open_events VALUES (?, ?, ?, ?)",
                (event_id, work_id, _url(url), stamp),
            ).rowcount
            if recorded:
                self.db.execute(
                    """UPDATE research_watch_hits SET seen_at = ? WHERE work_id = ? AND seen_at IS NULL""",
                    (stamp, work_id),
                )
            return self.paper_state(work_id)

    def mark_read(self, work_id, read):
        with self.lock, self.db:
            stamp = now_utc()
            self.db.execute(
                """INSERT INTO paper_reading VALUES (?, ?, ?) ON CONFLICT(work_id)
                   DO UPDATE SET read_at = excluded.read_at, updated_at = excluded.updated_at""",
                (work_id, stamp if read else None, stamp),
            )
            if read:
                self.db.execute(
                    """UPDATE research_watch_hits SET seen_at = COALESCE(seen_at, ?)
                       WHERE work_id = ? AND seen_at IS NULL""", (stamp, work_id),
                )
            return self.paper_state(work_id)

    def reading_history(self, limit, offset, query=""):
        query = query.strip().lower()
        with self.lock:
            rows = self.db.execute(
                """WITH activity AS (
                      SELECT work_id, max(opened_at) AS happened_at FROM paper_open_events GROUP BY work_id
                      UNION ALL SELECT work_id, read_at FROM paper_reading WHERE read_at IS NOT NULL
                   ), recent AS (SELECT work_id, max(happened_at) AS activity_at FROM activity GROUP BY work_id)
                   SELECT w.id, w.title, w.doi FROM recent r JOIN literature_works w ON w.id = r.work_id
                   WHERE ? = '' OR instr(lower(w.title), ?) OR instr(w.doi, ?) OR EXISTS (
                      SELECT 1 FROM paper_open_events e WHERE e.work_id = w.id AND instr(lower(e.url), ?)
                   )
                   ORDER BY r.activity_at DESC, w.id LIMIT ? OFFSET ?""", (query, query, query, query, limit, offset),
            ).fetchall()
            results = []
            for row in rows:
                urls = self.db.execute(
                    """SELECT url, count(*) AS open_count, max(opened_at) AS last_opened_at FROM paper_open_events
                       WHERE work_id = ? GROUP BY url ORDER BY last_opened_at DESC""", (row["id"],),
                ).fetchall()
                results.append({"title": row["title"], "doi": row["doi"], "urls": [dict(url) for url in urls],
                                **self.paper_state(row["id"])})
            return results
