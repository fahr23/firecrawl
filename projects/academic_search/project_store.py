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


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class ProjectStore:
    """SQLite persistence for essay/research-project search evidence."""

    def __init__(self, path: str) -> None:
        if path != ":memory:":
            Path(path).parent.mkdir(parents=True, exist_ok=True)
        self._connection = sqlite3.connect(path, check_same_thread=False)
        self._connection.row_factory = sqlite3.Row
        self._lock = threading.RLock()
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
                """
            )
            columns = {
                row[1] for row in self._connection.execute("PRAGMA table_info(search_runs)")
            }
            if "manifest_json" not in columns:
                self._connection.execute(
                    "ALTER TABLE search_runs ADD COLUMN manifest_json TEXT NOT NULL DEFAULT '{}'"
                )

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
        allowed = {key: value for key, value in changes.items() if value is not None}
        if "name" in allowed:
            allowed["name"] = str(allowed["name"]).strip()
        if "research_question" in allowed:
            allowed["research_question"] = str(allowed["research_question"]).strip() or None
        if not allowed:
            return existing
        allowed["updated_at"] = _now()
        columns = ", ".join(f"{key} = :{key}" for key in allowed)
        with self._lock, self._connection:
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

    def evidence(self, project_id: str) -> Optional[Dict[str, Any]]:
        project = self.get_project(project_id)
        if not project:
            return None
        with self._lock:
            rows = self._connection.execute(
                "SELECT * FROM search_runs WHERE project_id = ? ORDER BY retrieved_at DESC",
                (project_id,),
            ).fetchall()
        runs = []
        for row in rows:
            item = dict(row)
            item["providers_requested"] = json.loads(item.pop("providers_json"))
            item["sources_responded"] = json.loads(item.pop("sources_responded_json"))
            item["provider_coverage"] = json.loads(item.pop("provider_coverage_json"))
            item["manifest"] = json.loads(item.pop("manifest_json"))
            item["results"] = json.loads(item.pop("results_json"))
            runs.append(item)
        return {"project": project, "search_runs": runs}
