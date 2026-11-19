"""Durable draft recovery and saved publisher call monitoring."""

from datetime import datetime, timedelta, timezone
import json

from .literature_store import now_utc


SCHEMA = """
CREATE TABLE IF NOT EXISTS manuscript_autosaves (
    project_id TEXT NOT NULL REFERENCES research_projects(id),
    draft_id TEXT NOT NULL,
    base_revision INTEGER NOT NULL,
    version INTEGER NOT NULL,
    data_json TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    PRIMARY KEY(project_id, draft_id)
);
CREATE TABLE IF NOT EXISTS special_issue_calls (
    id TEXT PRIMARY KEY,
    publisher TEXT NOT NULL,
    checked_at TEXT NOT NULL,
    data_json TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS special_issue_queries (
    signature TEXT PRIMARY KEY,
    checked_at TEXT NOT NULL,
    data_json TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS special_issue_targets (
    project_id TEXT NOT NULL REFERENCES research_projects(id),
    item_id TEXT NOT NULL,
    call_id TEXT NOT NULL REFERENCES special_issue_calls(id),
    PRIMARY KEY(project_id, item_id)
);
CREATE INDEX IF NOT EXISTS special_issue_watched ON special_issue_targets(call_id);
CREATE TABLE IF NOT EXISTS special_issue_attempts (
    call_id TEXT PRIMARY KEY REFERENCES special_issue_calls(id),
    attempted_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS special_issue_alerts (
    id INTEGER PRIMARY KEY,
    call_id TEXT NOT NULL REFERENCES special_issue_calls(id),
    changed_at TEXT NOT NULL,
    changes_json TEXT NOT NULL,
    dismissed_at TEXT
);
"""


def _json(value):
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


def _ago(**kwargs):
    return (datetime.now(timezone.utc) - timedelta(**kwargs)).isoformat()


class PublishingStore:
    def __init__(self, connection, lock):
        self.db, self.lock = connection, lock
        with lock:
            self.db.executescript(SCHEMA)

    def autosave(self, project_id, draft_id):
        with self.lock:
            row = self.db.execute(
                "SELECT * FROM manuscript_autosaves WHERE project_id = ? AND draft_id = ?", (project_id, draft_id),
            ).fetchone()
            if not row:
                return None
            record = dict(row)
            record["data"] = json.loads(record.pop("data_json"))
            return record

    def save_draft(self, project_id, draft_id, revision, version, data):
        with self.lock, self.db:
            self.db.execute("BEGIN IMMEDIATE")
            base = self.db.execute(
                """SELECT MAX(revision) FROM workspace_revisions
                   WHERE section = 'manuscripts' AND project_id = ? AND id = ?""", (project_id, draft_id),
            ).fetchone()[0]
            current = self.autosave(project_id, draft_id)
            if revision != base or version != (current or {}).get("version", 0):
                return None
            self.db.execute(
                """INSERT INTO manuscript_autosaves VALUES (?, ?, ?, ?, ?, ?)
                   ON CONFLICT(project_id, draft_id) DO UPDATE SET version = excluded.version,
                     data_json = excluded.data_json, updated_at = excluded.updated_at""",
                (project_id, draft_id, revision, version + 1, _json(data), now_utc()),
            )
            return self.autosave(project_id, draft_id)

    def record_call_search(self, query, journal, publishers, coverage, current):
        signature = _json([query.casefold(), journal.casefold(), sorted(publishers)])
        with self.lock, self.db:
            self.db.execute(
                """INSERT INTO special_issue_queries VALUES (?, ?, ?) ON CONFLICT(signature)
                   DO UPDATE SET checked_at = excluded.checked_at, data_json = excluded.data_json""",
                (signature, now_utc(), _json({"coverage": coverage, "current": sorted(current)})),
            )

    def call_search_recent(self, query, journal, publishers):
        signature = _json([query.casefold(), journal.casefold(), sorted(publishers)])
        with self.lock:
            row = self.db.execute(
                "SELECT data_json FROM special_issue_queries WHERE signature = ? AND checked_at >= ?",
                (signature, _ago(minutes=30)),
            ).fetchone()
            return json.loads(row[0]) if row else None

    def calls(self, publishers):
        with self.lock:
            placeholders = ",".join("?" for _ in publishers)
            rows = self.db.execute(
                f"SELECT data_json FROM special_issue_calls WHERE publisher IN ({placeholders})", publishers,
            ).fetchall()
            return [json.loads(row[0]) for row in rows]

    def get_call(self, call_id):
        with self.lock:
            row = self.db.execute("SELECT data_json FROM special_issue_calls WHERE id = ?", (call_id,)).fetchone()
            return json.loads(row[0]) if row else None

    def cache_calls(self, rows):
        if not rows:
            return
        with self.lock, self.db:
            self.db.execute("BEGIN IMMEDIATE")
            for item in rows:
                old = self.get_call(item["id"])
                if old and old["checked_at"] > item["checked_at"]:
                    continue
                if old and old["status"] != "unverified" and item["status"] == "unverified":
                    continue
                self.db.execute(
                    """INSERT INTO special_issue_calls VALUES (?, ?, ?, ?) ON CONFLICT(id)
                       DO UPDATE SET checked_at = excluded.checked_at, data_json = excluded.data_json""",
                    (item["id"], item["publisher"], item["checked_at"], _json(item)),
                )
                watched = self.db.execute(
                    "SELECT 1 FROM special_issue_targets WHERE call_id = ? LIMIT 1", (item["id"],),
                ).fetchone()
                changes = {field: {"before": old.get(field) or "", "after": item.get(field) or ""}
                           for field in ("deadline", "abstract_deadline", "status")
                           if old and old.get(field) != item.get(field)}
                if changes and watched:
                    self.db.execute(
                        "INSERT INTO special_issue_alerts(call_id, changed_at, changes_json) VALUES (?, ?, ?)",
                        (item["id"], item["checked_at"], _json(changes)),
                    )

    def watch(self, project_id, item_id, call_id):
        with self.lock, self.db:
            self.db.execute("INSERT OR IGNORE INTO special_issue_targets VALUES (?, ?, ?)", (project_id, item_id, call_id))

    def watched_call(self, project_id, item_id):
        with self.lock:
            row = self.db.execute(
                """SELECT c.data_json FROM special_issue_targets t JOIN special_issue_calls c ON c.id = t.call_id
                   WHERE t.project_id = ? AND t.item_id = ?""", (project_id, item_id),
            ).fetchone()
            return json.loads(row[0]) if row else None

    def due_calls(self):
        with self.lock:
            return [row[0] for row in self.db.execute(
                """SELECT c.id FROM special_issue_calls c LEFT JOIN special_issue_attempts a ON a.call_id = c.id
                   WHERE c.checked_at < ? AND (a.attempted_at IS NULL OR a.attempted_at < ?)
                     AND EXISTS (SELECT 1 FROM special_issue_targets t WHERE t.call_id = c.id)
                   ORDER BY COALESCE(a.attempted_at, c.checked_at), c.id LIMIT 4""", (_ago(hours=24), _ago(hours=6)),
            )]

    def note_attempt(self, call_id):
        with self.lock, self.db:
            self.db.execute(
                """INSERT INTO special_issue_attempts VALUES (?, ?) ON CONFLICT(call_id)
                   DO UPDATE SET attempted_at = excluded.attempted_at""", (call_id, now_utc()),
            )

    def alerts(self, project_id=None):
        project_clause = "AND t.project_id = ?" if project_id else ""
        with self.lock:
            rows = self.db.execute(
                f"""SELECT a.id, a.changed_at, a.changes_json, c.data_json,
                           t.project_id, t.item_id, p.name AS project_name
                    FROM special_issue_alerts a JOIN special_issue_calls c ON c.id = a.call_id
                    JOIN special_issue_targets t ON t.call_id = c.id
                    JOIN research_projects p ON p.id = t.project_id
                    WHERE a.dismissed_at IS NULL {project_clause} ORDER BY a.changed_at DESC LIMIT 50""",
                (project_id,) if project_id else (),
            ).fetchall()
            return [{**{key: row[key] for key in ("id", "changed_at", "project_id", "item_id", "project_name")},
                     "changes": json.loads(row["changes_json"]), "call": json.loads(row["data_json"])} for row in rows]

    def dismiss(self, alert_id):
        with self.lock, self.db:
            return self.db.execute(
                "UPDATE special_issue_alerts SET dismissed_at = COALESCE(dismissed_at, ?) WHERE id = ?", (now_utc(), alert_id),
            ).rowcount
