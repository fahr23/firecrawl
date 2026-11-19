"""Small, local evidence ledger for search-focused research projects.

This deliberately stores search runs rather than becoming a citation manager: every
saved record remains tied to the query, filters, responding sources and retrieval
time that produced it.
"""

from __future__ import annotations

import json
import sqlite3
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from .daily_store import DailyReadingStore
from .journal_favorites_store import JournalFavoritesStore
from .literature_store import LiteratureStore
from .publishing_store import PublishingStore
from .workflow_store import WorkflowStore


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


_NULLABLE_FIELDS = {"research_question", "default_year_min", "default_year_max"}


class DuplicateProjectName(ValueError):
    pass


class WorkspaceConflict(ValueError):
    pass


class ProjectStore:
    """SQLite persistence for essay/research-project search evidence."""

    def __init__(self, path: str) -> None:
        if path != ":memory:":
            Path(path).parent.mkdir(parents=True, exist_ok=True)
        self._connection = sqlite3.connect(path, check_same_thread=False)
        self._connection.row_factory = sqlite3.Row
        self._lock = threading.RLock()
        self._connection.execute("PRAGMA foreign_keys = ON")
        if path != ":memory:":
            self._connection.execute("PRAGMA journal_mode = WAL")
        with self._connection:
            self._connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS research_projects (
                  id TEXT PRIMARY KEY,
                  name TEXT NOT NULL,
                  research_question TEXT,
                  default_category TEXT NOT NULL DEFAULT 'all',
                  default_providers TEXT NOT NULL DEFAULT 'openalex',
                  default_year_min INTEGER,
                  default_year_max INTEGER,
                  created_at TEXT NOT NULL,
                  updated_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS search_runs (
                  id TEXT PRIMARY KEY,
                  project_id TEXT NOT NULL REFERENCES research_projects(id),
                  query TEXT NOT NULL,
                  category TEXT NOT NULL,
                  providers_json TEXT NOT NULL,
                  year_min INTEGER,
                  year_max INTEGER,
                  limit_value INTEGER NOT NULL,
                  retrieved_at TEXT NOT NULL,
                  search_time REAL,
                  total_provider_matches INTEGER,
                  returned_count INTEGER NOT NULL,
                  sources_responded_json TEXT NOT NULL,
                  provider_coverage_json TEXT NOT NULL,
                  manifest_json TEXT NOT NULL DEFAULT '{}',
                  results_json TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS search_runs_project_retrieved_idx
                  ON search_runs(project_id, retrieved_at DESC);
                CREATE TABLE IF NOT EXISTS journal_search_runs (
                  id TEXT PRIMARY KEY,
                  project_id TEXT NOT NULL REFERENCES research_projects(id),
                  journal_json TEXT NOT NULL,
                  topics_json TEXT NOT NULL,
                  query TEXT NOT NULL,
                  year_min INTEGER,
                  year_max INTEGER,
                  limit_value INTEGER NOT NULL,
                  retrieved_at TEXT NOT NULL,
                  total_provider_matches INTEGER NOT NULL,
                  provider_outcomes_json TEXT NOT NULL,
                  profile_json TEXT NOT NULL,
                  papers_json TEXT NOT NULL,
                  manifest_json TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS journal_runs_project_retrieved_idx
                  ON journal_search_runs(project_id, retrieved_at DESC);
                CREATE TABLE IF NOT EXISTS journal_fit_runs (
                  id TEXT PRIMARY KEY,
                  project_id TEXT NOT NULL REFERENCES research_projects(id),
                  journal_search_id TEXT NOT NULL REFERENCES journal_search_runs(id),
                  manuscript_json TEXT NOT NULL,
                  report_json TEXT NOT NULL,
                  created_at TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS journal_fits_project_created_idx
                  ON journal_fit_runs(project_id, created_at DESC);
                CREATE TABLE IF NOT EXISTS workspace_revisions (
                  project_id TEXT NOT NULL REFERENCES research_projects(id),
                  section TEXT NOT NULL,
                  id TEXT NOT NULL,
                  revision INTEGER NOT NULL,
                  data_json TEXT NOT NULL,
                  updated_at TEXT NOT NULL,
                  PRIMARY KEY (project_id, section, id, revision)
                );
                """
            )
            columns = {
                row[1] for row in self._connection.execute("PRAGMA table_info(search_runs)")
            }
            if "manifest_json" not in columns:
                self._connection.execute(
                    "ALTER TABLE search_runs ADD COLUMN manifest_json TEXT NOT NULL DEFAULT '{}'"
                )
        self.literature = LiteratureStore(self._connection, self._lock)
        self.literature.import_project_history()
        self.workflow = WorkflowStore(self)
        self.daily = DailyReadingStore(self._connection, self._lock)
        self.publishing = PublishingStore(self._connection, self._lock)
        self.journal_favorites = JournalFavoritesStore(self._connection, self._lock)

    @staticmethod
    def _project(row: sqlite3.Row) -> Dict[str, Any]:
        return dict(row)

    def list_projects(self) -> List[Dict[str, Any]]:
        with self._lock:
            rows = self._connection.execute(
                "SELECT * FROM research_projects ORDER BY updated_at DESC, name COLLATE NOCASE"
            ).fetchall()
        return [self._project(row) for row in rows]

    def get_project(self, project_id: str) -> Optional[Dict[str, Any]]:
        with self._lock:
            row = self._connection.execute(
                "SELECT * FROM research_projects WHERE id = ?", (project_id,)
            ).fetchone()
        return self._project(row) if row else None

    def _ensure_unique_name(self, name: str, exclude_id: Optional[str] = None) -> None:
        wanted = name.strip().casefold()
        rows = self._connection.execute("SELECT id, name FROM research_projects").fetchall()
        if any(row["id"] != exclude_id and row["name"].strip().casefold() == wanted for row in rows):
            raise DuplicateProjectName(name.strip())

    def create_project(self, data: Dict[str, Any]) -> Dict[str, Any]:
        project_id, now = str(uuid.uuid4()), _now()
        values = {
            "name": data["name"].strip(),
            "research_question": (data.get("research_question") or "").strip() or None,
            "default_category": data.get("default_category") or "all",
            "default_providers": data.get("default_providers") or "openalex",
            "default_year_min": data.get("default_year_min"),
            "default_year_max": data.get("default_year_max"),
        }
        with self._lock, self._connection:
            self._ensure_unique_name(values["name"])
            self._connection.execute(
                """INSERT INTO research_projects
                   (id, name, research_question, default_category, default_providers,
                    default_year_min, default_year_max, created_at, updated_at)
                   VALUES (:id, :name, :research_question, :default_category, :default_providers,
                           :default_year_min, :default_year_max, :created_at, :updated_at)""",
                {"id": project_id, "created_at": now, "updated_at": now, **values},
            )
        return self.get_project(project_id)  # type: ignore[return-value]

    def update_project(self, project_id: str, changes: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        existing = self.get_project(project_id)
        if not existing:
            return None
        allowed = {
            key: value for key, value in changes.items()
            if value is not None or key in _NULLABLE_FIELDS
        }
        if "name" in allowed:
            allowed["name"] = str(allowed["name"]).strip()
        if allowed.get("research_question") is not None:
            allowed["research_question"] = str(allowed["research_question"]).strip() or None
        if not allowed:
            return existing
        allowed["updated_at"] = _now()
        columns = ", ".join(f"{key} = :{key}" for key in allowed)
        with self._lock, self._connection:
            if "name" in allowed:
                self._ensure_unique_name(allowed["name"], exclude_id=project_id)
            self._connection.execute(
                f"UPDATE research_projects SET {columns} WHERE id = :id",
                {"id": project_id, **allowed},
            )
        return self.get_project(project_id)

    def record_search(self, project_id: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        run_id = str(uuid.uuid4())
        with self._lock, self._connection:
            self._connection.execute(
                """INSERT INTO search_runs
                   (id, project_id, query, category, providers_json, year_min, year_max,
                    limit_value, retrieved_at, search_time, total_provider_matches,
                    returned_count, sources_responded_json, provider_coverage_json, manifest_json, results_json)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    run_id, project_id, payload["query"], payload["category"],
                    json.dumps(payload["providers_requested"]), payload.get("year_min"),
                    payload.get("year_max"), payload["limit"], payload["retrieved_at"],
                    payload.get("search_time"), payload.get("total_provider_matches"),
                    payload["returned"], json.dumps(payload["sources_responded"]),
                    json.dumps(payload["provider_coverage"]),
                    json.dumps(payload["manifest"], ensure_ascii=False),
                    json.dumps(payload["results"], ensure_ascii=False),
                ),
            )
        return {"id": run_id, "project_id": project_id}

    def list_searches(self, project_id: str, limit: int = 20) -> List[Dict[str, Any]]:
        with self._lock:
            rows = self._connection.execute(
                """SELECT id, project_id, query, category, providers_json, year_min, year_max,
                          limit_value, retrieved_at, returned_count, sources_responded_json, manifest_json
                   FROM search_runs WHERE project_id = ? ORDER BY retrieved_at DESC LIMIT ?""",
                (project_id, limit),
            ).fetchall()
        return [
            {**dict(row), "providers": json.loads(row["providers_json"]),
             "sources_responded": json.loads(row["sources_responded_json"]),
             "manifest": json.loads(row["manifest_json"])}
            for row in rows
        ]

    @staticmethod
    def _search_run(row: sqlite3.Row) -> Dict[str, Any]:
        item = dict(row)
        for field, column in (
            ("providers_requested", "providers_json"),
            ("sources_responded", "sources_responded_json"),
            ("provider_coverage", "provider_coverage_json"),
            ("manifest", "manifest_json"),
            ("results", "results_json"),
        ):
            item[field] = json.loads(item.pop(column))
        return item

    def get_search(self, project_id: str, run_id: str) -> Optional[Dict[str, Any]]:
        with self._lock:
            row = self._connection.execute(
                "SELECT * FROM search_runs WHERE project_id = ? AND id = ?",
                (project_id, run_id),
            ).fetchone()
        return self._search_run(row) if row else None

    def evidence(self, project_id: str) -> Optional[Dict[str, Any]]:
        project = self.get_project(project_id)
        if not project:
            return None
        with self._lock:
            rows = self._connection.execute(
                "SELECT * FROM search_runs WHERE project_id = ? ORDER BY retrieved_at DESC",
                (project_id,),
            ).fetchall()
        with self._lock:
            journal_rows = self._connection.execute(
                "SELECT * FROM journal_search_runs WHERE project_id = ? ORDER BY retrieved_at DESC",
                (project_id,),
            ).fetchall()
        return {
            "project": project,
            "search_runs": [self._search_run(row) for row in rows],
            "journal_search_runs": [self._journal_run(row) for row in journal_rows],
            "journal_fit_runs": self.list_journal_fits(project_id, 1000),
        }

    @staticmethod
    def _journal_run(row: sqlite3.Row) -> Dict[str, Any]:
        item = dict(row)
        item["journal"] = json.loads(item.pop("journal_json"))
        item["topics"] = json.loads(item.pop("topics_json"))
        item["provider_outcomes"] = json.loads(item.pop("provider_outcomes_json"))
        item["profile"] = json.loads(item.pop("profile_json"))
        item["papers"] = json.loads(item.pop("papers_json"))
        item["manifest"] = json.loads(item.pop("manifest_json"))
        item["limit"] = item.pop("limit_value")
        return item

    def find_journal_search(
        self,
        project_id: str,
        journal_id: str,
        topics: List[str],
        year_min: Optional[int],
        year_max: Optional[int],
        limit: int,
    ) -> Optional[Dict[str, Any]]:
        """Return the newest exact saved snapshot for a repeatable request."""
        topics_json = json.dumps(topics, ensure_ascii=False, separators=(",", ":"))
        with self._lock:
            rows = self._connection.execute(
                """SELECT * FROM journal_search_runs
                   WHERE project_id = ? AND topics_json = ? AND year_min IS ?
                     AND year_max IS ? AND limit_value = ?
                   ORDER BY retrieved_at DESC""",
                (project_id, topics_json, year_min, year_max, limit),
            ).fetchall()
        for row in rows:
            parsed = self._journal_run(row)
            if any(outcome.get("status") in {"failed", "rate_limited", "unavailable"}
                   for outcome in parsed["provider_outcomes"]):
                continue
            if parsed["journal"].get("id") == journal_id:
                return parsed
        return None

    def record_journal_search(self, project_id: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        run_id = str(uuid.uuid4())
        with self._lock, self._connection:
            self._connection.execute(
                """INSERT INTO journal_search_runs
                   (id, project_id, journal_json, topics_json, query, year_min, year_max,
                    limit_value, retrieved_at, total_provider_matches,
                    provider_outcomes_json, profile_json, papers_json, manifest_json)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    run_id, project_id,
                    json.dumps(payload["journal"], ensure_ascii=False),
                    json.dumps(payload["topics"], ensure_ascii=False, separators=(",", ":")),
                    payload["query"], payload.get("year_min"), payload.get("year_max"),
                    payload["limit"], payload["retrieved_at"],
                    payload.get("total_provider_matches", 0),
                    json.dumps(payload.get("provider_outcomes", []), ensure_ascii=False),
                    json.dumps(payload["profile"], ensure_ascii=False),
                    json.dumps(payload["papers"], ensure_ascii=False),
                    json.dumps(payload["manifest"], ensure_ascii=False),
                ),
            )
        return self.get_journal_search(run_id)  # type: ignore[return-value]

    def get_journal_search(self, run_id: str) -> Optional[Dict[str, Any]]:
        with self._lock:
            row = self._connection.execute(
                "SELECT * FROM journal_search_runs WHERE id = ?", (run_id,)
            ).fetchone()
        return self._journal_run(row) if row else None

    def list_journal_searches(self, project_id: str, limit: int = 20) -> List[Dict[str, Any]]:
        with self._lock:
            rows = self._connection.execute(
                """SELECT * FROM journal_search_runs WHERE project_id = ?
                   ORDER BY retrieved_at DESC LIMIT ?""",
                (project_id, limit),
            ).fetchall()
        summaries = []
        for row in rows:
            item = self._journal_run(row)
            item["paper_count"] = len(item.pop("papers"))
            summaries.append(item)
        return summaries

    def record_journal_fit(
        self,
        project_id: str,
        journal_search_id: str,
        manuscript: Dict[str, Any],
        report: Dict[str, Any],
    ) -> Dict[str, Any]:
        fit_id, created_at = str(uuid.uuid4()), _now()
        with self._lock, self._connection:
            self._connection.execute(
                """INSERT INTO journal_fit_runs
                   (id, project_id, journal_search_id, manuscript_json, report_json, created_at)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (
                    fit_id, project_id, journal_search_id,
                    json.dumps(manuscript, ensure_ascii=False),
                    json.dumps(report, ensure_ascii=False), created_at,
                ),
            )
        return {"id": fit_id, "project_id": project_id,
                "journal_search_id": journal_search_id, "created_at": created_at, **report}

    def list_journal_fits(
        self, project_id: str, limit: int = 20, journal_search_id: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        where = "project_id = ?"
        parameters: List[Any] = [project_id]
        if journal_search_id is not None:
            where += " AND journal_search_id = ?"
            parameters.append(journal_search_id)
        with self._lock:
            rows = self._connection.execute(
                f"SELECT * FROM journal_fit_runs WHERE {where} ORDER BY created_at DESC LIMIT ?",
                [*parameters, limit],
            ).fetchall()
        fits = []
        for row in rows:
            item = dict(row)
            item["manuscript"] = json.loads(item.pop("manuscript_json"))
            item.update(json.loads(item.pop("report_json")))
            fits.append(item)
        return fits

    @staticmethod
    def _workspace_record(row: sqlite3.Row) -> Dict[str, Any]:
        item = dict(row)
        item["data"] = json.loads(item.pop("data_json"))
        return item

    def workspace_history(self, project_id: str, section: str, item_id: str, limit: int = 30) -> List[Dict[str, Any]]:
        with self._lock:
            rows = self._connection.execute(
                """SELECT * FROM workspace_revisions WHERE project_id = ? AND section = ? AND id = ?
                   ORDER BY revision DESC LIMIT ?""", (project_id, section, item_id, limit),
            ).fetchall()
        return [self._workspace_record(row) for row in rows]

    def workspace_items(self, project_id: str, section: str, limit: int = 100) -> List[Dict[str, Any]]:
        with self._lock:
            rows = self._connection.execute(
                """SELECT * FROM workspace_revisions WHERE project_id = ? AND section = ?
                   AND (id, revision) IN (
                     SELECT id, MAX(revision) FROM workspace_revisions
                     WHERE project_id = ? AND section = ? GROUP BY id
                   ) ORDER BY updated_at DESC, id LIMIT ?""", (project_id, section, project_id, section, limit),
            ).fetchall()
        return [self._workspace_record(row) for row in rows]

    def all_workspace_items(self, section: str) -> List[Dict[str, Any]]:
        with self._lock:
            rows = self._connection.execute(
                """SELECT w.*, p.name AS project_name FROM workspace_revisions w
                   JOIN research_projects p ON p.id = w.project_id
                   JOIN (SELECT project_id, id, MAX(revision) AS revision FROM workspace_revisions
                         WHERE section = ? GROUP BY project_id, id) latest
                     ON latest.project_id = w.project_id AND latest.id = w.id AND latest.revision = w.revision
                   WHERE w.section = ? ORDER BY w.updated_at DESC, w.id""", (section, section),
            ).fetchall()
        return [self._workspace_record(row) for row in rows]

    def put_workspace_item(
        self, project_id: str, section: str, data: Dict[str, Any],
        item_id: Optional[str] = None, expected_revision: int = 0,
        expected_autosave_version: Optional[int] = None,
    ) -> Dict[str, Any]:
        item_id = item_id or str(uuid.uuid4())
        now = _now()
        with self._lock, self._connection:
            self._connection.execute("BEGIN IMMEDIATE")
            revision = self._connection.execute(
                "SELECT COALESCE(MAX(revision), 0) FROM workspace_revisions WHERE project_id = ? AND section = ? AND id = ?",
                (project_id, section, item_id),
            ).fetchone()[0]
            if revision != expected_revision:
                raise WorkspaceConflict("This item changed. Reload the latest version before saving.")
            if section == "manuscripts" and expected_autosave_version is not None:
                buffer = self.publishing.autosave(project_id, item_id)
                if (buffer or {}).get("version", 0) != expected_autosave_version:
                    raise WorkspaceConflict("An autosave changed in another tab. Reload the draft before saving a version.")
            self._connection.execute(
                "INSERT INTO workspace_revisions VALUES (?, ?, ?, ?, ?, ?)",
                (project_id, section, item_id, revision + 1, json.dumps(data, ensure_ascii=False), now),
            )
            if section == "manuscripts":
                self._connection.execute(
                    "DELETE FROM manuscript_autosaves WHERE project_id = ? AND draft_id = ?", (project_id, item_id),
                )
        return {"project_id": project_id, "section": section, "id": item_id,
                "revision": revision + 1, "updated_at": now, "data": data}
