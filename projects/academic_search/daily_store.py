"""Local schedules and immutable paper selections for the daily reading queue."""

from datetime import date, datetime, time, timedelta, timezone
import json
import uuid
from zoneinfo import ZoneInfo

from .literature_store import now_utc


SCHEMA = """
CREATE TABLE IF NOT EXISTS daily_reading_schedules (
    project_id TEXT PRIMARY KEY REFERENCES research_projects(id),
    settings_json TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS daily_reading_editions (
    project_id TEXT NOT NULL REFERENCES daily_reading_schedules(project_id),
    day TEXT NOT NULL,
    settings_json TEXT NOT NULL,
    created_at TEXT NOT NULL,
    checked_at TEXT,
    attempts INTEGER NOT NULL DEFAULT 0,
    claim_token TEXT,
    claimed_at TEXT,
    retry_at TEXT,
    paper_coverage_json TEXT,
    trend_json TEXT,
    PRIMARY KEY (project_id, day)
);
CREATE TABLE IF NOT EXISTS daily_reading_papers (
    work_id INTEGER PRIMARY KEY REFERENCES literature_works(id),
    project_id TEXT NOT NULL,
    day TEXT NOT NULL,
    position INTEGER NOT NULL CHECK(position > 0),
    paper_json TEXT NOT NULL,
    source TEXT NOT NULL CHECK(source IN ('live', 'library')),
    FOREIGN KEY(project_id, day) REFERENCES daily_reading_editions(project_id, day),
    UNIQUE(project_id, day, position)
);
"""

FAILED = {"failed", "rate_limited", "unavailable"}
EDITION_START_LEASE = timedelta(hours=1)


def clock():
    return datetime.now(timezone.utc)


def local_schedule(settings, now):
    zone = ZoneInfo(settings["timezone"])
    today = now.astimezone(zone).date()
    day = max(today, date.fromisoformat(settings["start_on"]))
    return today, scheduled_time(settings, day, zone)


def scheduled_time(settings, day, zone=None):
    zone = zone or ZoneInfo(settings["timezone"])
    return datetime.combine(day, time.fromisoformat(settings["local_time"]), zone).astimezone(timezone.utc)


class DailyReadingStore:
    def __init__(self, connection, lock):
        self.db = connection
        self.lock = lock
        with lock:
            self.db.executescript(SCHEMA)

    def save_settings(self, project_id, settings):
        with self.lock, self.db:
            self.db.execute(
                """INSERT INTO daily_reading_schedules VALUES (?, ?, ?) ON CONFLICT(project_id)
                   DO UPDATE SET settings_json = excluded.settings_json, updated_at = excluded.updated_at""",
                (project_id, json.dumps(settings, ensure_ascii=False), now_utc()),
            )

    def _settings(self, project_id):
        row = self.db.execute(
            "SELECT settings_json FROM daily_reading_schedules WHERE project_id = ?", (project_id,),
        ).fetchone()
        return json.loads(row["settings_json"]) if row else None

    def _edition(self, project_id, day):
        row = self.db.execute(
            "SELECT * FROM daily_reading_editions WHERE project_id = ? AND day = ?", (project_id, day),
        ).fetchone()
        if not row:
            return None
        entry = dict(row)
        entry["settings"] = json.loads(entry.pop("settings_json"))
        entry["coverage"] = json.loads(entry.pop("paper_coverage_json") or "null")
        entry["trend"] = json.loads(entry.pop("trend_json") or "null")
        entry["papers"] = [dict(paper) for paper in self.db.execute(
            """SELECT d.paper_json, d.source, p.read_at FROM daily_reading_papers d
               LEFT JOIN paper_reading p ON p.work_id = d.work_id WHERE d.project_id = ? AND d.day = ?
               ORDER BY d.position""", (project_id, day),
        )]
        for paper in entry["papers"]:
            paper["paper"] = json.loads(paper.pop("paper_json"))
        return entry

    @staticmethod
    def _work_left(edition, *, manual=False):
        if not edition:
            return True, True
        coverage = edition["coverage"]
        papers_failed = coverage is None or any(provider["status"] in FAILED for provider in coverage)
        space = len(edition["papers"]) < edition["settings"]["papers_per_day"]
        papers = coverage is None or ((manual or papers_failed) and space)
        trend = edition["trend"] is None or bool(edition["trend"].get("errors"))
        return papers, trend

    @staticmethod
    def _claimed(edition, now):
        return bool(edition and edition["claim_token"] and
                    datetime.fromisoformat(edition["claimed_at"]) + EDITION_START_LEASE > now)

    def _next(self, settings, project_id, now):
        today, due = local_schedule(settings, now)
        if not settings["enabled"]:
            return today, None
        if settings["start_on"] > today.isoformat():
            return today, due
        edition = self._edition(project_id, today.isoformat())
        if not edition or not edition["checked_at"]:
            return today, max(now, due)
        if edition["retry_at"]:
            retry = datetime.fromisoformat(edition["retry_at"])
            return today, max(now, retry, due)
        return today, scheduled_time(settings, today + timedelta(days=1))

    def due(self, now=None, limit=2):
        now = now or clock()
        with self.lock:
            rows = self.db.execute("SELECT project_id, settings_json FROM daily_reading_schedules").fetchall()
            queue = []
            for row in rows:
                project_id = row["project_id"]
                settings = json.loads(row["settings_json"])
                today, due = self._next(settings, project_id, now)
                if due and due <= now and not self._claimed(self._edition(project_id, today.isoformat()), now):
                    queue.append((scheduled_time(settings, today), project_id))
            return [project_id for _, project_id in sorted(queue)[:limit]]

    def claim(self, project_id, now, *, manual=False):
        with self.lock, self.db:
            self.db.execute("BEGIN IMMEDIATE")
            settings = self._settings(project_id)
            if not settings:
                return None
            today, due = local_schedule(settings, now)
            day = today.isoformat()
            if settings["start_on"] > day or (not manual and (not settings["enabled"] or now < due)):
                return None
            edition = self._edition(project_id, day)
            if self._claimed(edition, now):
                return None
            papers, trend = self._work_left(edition, manual=manual)
            if not (papers or trend):
                return None
            if edition and edition["checked_at"] and not manual:
                retry = edition["retry_at"]
                if retry is None or now < datetime.fromisoformat(retry):
                    return None
            token = str(uuid.uuid4())
            self.db.execute(
                """INSERT INTO daily_reading_editions
                   (project_id, day, settings_json, created_at, claim_token, claimed_at) VALUES (?, ?, ?, ?, ?, ?)
                   ON CONFLICT(project_id, day) DO UPDATE
                   SET claim_token = excluded.claim_token, claimed_at = excluded.claimed_at""",
                (project_id, day, json.dumps(settings, ensure_ascii=False), now.isoformat(), token, now.isoformat()),
            )
            return {"day": day, "token": token, "settings": (edition or {}).get("settings", settings),
                    "need_papers": papers, "need_trend": trend}

    def release(self, project_id, day, token):
        with self.lock, self.db:
            self.db.execute(
                """UPDATE daily_reading_editions SET claim_token = NULL, claimed_at = NULL
                   WHERE project_id = ? AND day = ? AND claim_token = ?""", (project_id, day, token),
            )

    def finish(self, project_id, run, live, saved, coverage, trend, now):
        day, token = run["day"], run["token"]
        with self.lock, self.db:
            self.db.execute("BEGIN IMMEDIATE")
            edition = self._edition(project_id, day)
            if not edition or edition["claim_token"] != token:
                return
            position = len(edition["papers"]) + 1
            for source, candidates in (("live", live), ("library", saved)):
                for paper in candidates:
                    if position > edition["settings"]["papers_per_day"]:
                        break
                    work_id = paper.get("library_id")
                    if not work_id:
                        continue
                    cursor = self.db.execute(
                        """INSERT OR IGNORE INTO daily_reading_papers
                           SELECT ?, ?, ?, ?, ?, ? WHERE NOT EXISTS (
                               SELECT 1 FROM paper_reading WHERE work_id = ? AND read_at IS NOT NULL
                           ) AND NOT EXISTS (SELECT 1 FROM paper_open_events WHERE work_id = ?)""",
                        (work_id, project_id, day, position, json.dumps(paper, ensure_ascii=False), source, work_id, work_id),
                    )
                    position += cursor.rowcount
            attempts = edition["attempts"] + 1
            coverage = edition["coverage"] if coverage is None else coverage
            trend = edition["trend"] if trend is None else trend
            paper_failed = any(item["status"] in FAILED for item in coverage or [])
            needs_retry = (paper_failed and position <= edition["settings"]["papers_per_day"]) or bool(trend and trend["errors"])
            retry = now + timedelta(hours=2)
            same_day = retry.astimezone(ZoneInfo(edition["settings"]["timezone"])).date().isoformat() == day
            retry_at = retry.isoformat() if needs_retry and attempts < 3 and same_day else None
            self.db.execute(
                """UPDATE daily_reading_editions SET checked_at = ?, attempts = ?, claim_token = NULL,
                   claimed_at = NULL, retry_at = ?, paper_coverage_json = ?, trend_json = ?
                   WHERE project_id = ? AND day = ?""",
                (now.isoformat(), attempts, retry_at, json.dumps(coverage), json.dumps(trend), project_id, day),
            )

    def _public_edition(self, edition, now):
        if not edition:
            return None
        coverage = edition["coverage"] or []
        incomplete = any(source["status"] in FAILED for source in coverage) or bool(
            edition["trend"] and edition["trend"]["errors"]
        )
        return {key: edition[key] for key in ("day", "papers", "checked_at", "coverage", "trend", "settings")} | {
            "checking": self._claimed(edition, now),
            "status": "pending" if not edition["checked_at"] else "partial" if incomplete else "ready",
            "can_retry": any(self._work_left(edition, manual=True)),
        }

    def view(self, project_id, day=None):
        now = clock()
        with self.lock:
            settings = self._settings(project_id)
            if not settings:
                return {"settings": None, "today": None, "next_run_at": None, "edition": None, "history": []}
            today, next_at = self._next(settings, project_id, now)
            today_string = today.isoformat()
            edition = self._public_edition(self._edition(project_id, day or today_string), now)
            previous = self.db.execute(
                """SELECT d.day, count(p.work_id) AS total, count(r.read_at) AS read
                   FROM daily_reading_editions d LEFT JOIN daily_reading_papers p
                   ON p.project_id = d.project_id AND p.day = d.day
                   LEFT JOIN paper_reading r ON r.work_id = p.work_id
                   WHERE d.project_id = ? AND d.checked_at IS NOT NULL GROUP BY d.day ORDER BY d.day DESC LIMIT 120""",
                (project_id,),
            ).fetchall()
            return {"settings": settings, "today": today_string, "next_run_at": next_at.isoformat() if next_at else None,
                    "edition": edition, "history": [dict(row) for row in previous]}

    def overview(self):
        with self.lock:
            rows = self.db.execute(
                """SELECT d.project_id, p.name FROM daily_reading_schedules d
                   JOIN research_projects p ON p.id = d.project_id ORDER BY p.name COLLATE NOCASE""",
            ).fetchall()
            results = []
            for row in rows:
                entry = self.view(row["project_id"])
                today = next((day for day in entry["history"] if day["day"] == entry["today"]), {})
                edition = entry["edition"] or {}
                trends = edition.get("trend") or {}
                results.append({**dict(row), "settings": entry["settings"], "next_run_at": entry["next_run_at"],
                                "today": entry["today"], "total": today.get("total", 0), "read": today.get("read", 0),
                                "status": edition.get("status", "pending"),
                                "trends": trends.get("topics", []) if not trends.get("errors") else []})
            return results
