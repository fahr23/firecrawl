"""Personal journal follows and their cached publication and submission evidence."""

from datetime import datetime, timedelta, timezone
import json
import re
from uuid import uuid4


_SCHEMA = """
CREATE TABLE IF NOT EXISTS journal_favorites (
    id TEXT PRIMARY KEY,
    openalex_id TEXT UNIQUE,
    journal_json TEXT NOT NULL,
    followed_at TEXT NOT NULL,
    active INTEGER NOT NULL DEFAULT 1 CHECK(active IN (0, 1)),
    last_attempt_at TEXT,
    refresh_token TEXT,
    paper_status_json TEXT,
    papers_checked_at TEXT,
    publisher_status_json TEXT,
    publisher_checked_at TEXT,
    publisher_json TEXT
);
CREATE TABLE IF NOT EXISTS journal_favorite_aliases (
    favorite_id TEXT NOT NULL REFERENCES journal_favorites(id),
    identifier TEXT NOT NULL,
    PRIMARY KEY(favorite_id, identifier)
);
CREATE INDEX IF NOT EXISTS journal_favorite_identifiers ON journal_favorite_aliases(identifier);
CREATE TABLE IF NOT EXISTS journal_favorite_papers (
    favorite_id TEXT NOT NULL REFERENCES journal_favorites(id),
    work_id INTEGER NOT NULL REFERENCES literature_works(id),
    publication_sort TEXT NOT NULL,
    discovered_at TEXT NOT NULL,
    seen_at TEXT,
    paper_json TEXT NOT NULL,
    PRIMARY KEY(favorite_id, work_id)
);
CREATE INDEX IF NOT EXISTS journal_favorite_feed_order
    ON journal_favorite_papers(favorite_id, publication_sort DESC, discovered_at DESC);
"""

_UNSEEN = """jp.seen_at IS NULL
    AND NOT EXISTS (SELECT 1 FROM paper_open_events e WHERE e.work_id = jp.work_id)
    AND NOT EXISTS (SELECT 1 FROM paper_reading r WHERE r.work_id = jp.work_id AND r.read_at IS NOT NULL)"""
_SUMMARIES = f"""SELECT f.*, (
    SELECT count(*) FROM journal_favorite_papers jp WHERE jp.favorite_id = f.id AND {_UNSEEN}
) AS unread FROM journal_favorites f"""


def clock():
    return datetime.now(timezone.utc)


def normalize_issn(value):
    compact = str(value or "").strip().upper().replace("-", "")
    return compact if re.fullmatch(r"\d{7}[0-9X]", compact) else ""


def normalize_source_id(value):
    identifier = str(value or "").rstrip("/").rsplit("/", 1)[-1].upper()
    return identifier if re.fullmatch(r"S\d+", identifier) else ""


def journal_issns(journal):
    return {value for issn in [journal.get("issn_l"), *(journal.get("issns") or [])]
            if (value := normalize_issn(issn))}


def catalog_alias(provider, journal_id):
    value = str(journal_id).strip()
    if provider == "openalex":
        value = normalize_source_id(value) or value
    return f"catalog:{provider}:{value}"


def journal_openalex(journal):
    if journal.get("search_supported") is False:
        return ""
    return normalize_source_id((journal.get("identifiers") or {}).get("openalex") or journal.get("id"))


def _summary(row, now):
    if not row:
        return None
    item = dict(row)
    claimed = item.pop("refresh_token")
    item["refreshing"] = bool(claimed and item["last_attempt_at"] and
                              datetime.fromisoformat(item["last_attempt_at"]) + timedelta(minutes=15) > now)
    item["active"] = bool(item["active"])
    for stored, key in (("journal_json", "journal"), ("paper_status_json", "paper_status"),
                        ("publisher_status_json", "publisher_status"), ("publisher_json", "submission")):
        item[key] = json.loads(item.pop(stored) or "null")
    return item


class JournalFavoritesStore:
    def __init__(self, connection, lock):
        self.db = connection
        self.lock = lock
        with lock:
            self.db.executescript(_SCHEMA)

    def all(self):
        with self.lock:
            rows = self.db.execute(_SUMMARIES + " WHERE f.active = 1 ORDER BY f.followed_at DESC, f.id").fetchall()
        now = clock()
        return [_summary(row, now) for row in rows]

    def get(self, favorite_id, *, include_inactive=False):
        with self.lock:
            row = self.db.execute(
                _SUMMARIES + " WHERE f.id = ? AND (f.active = 1 OR ?)", (favorite_id, include_inactive),
            ).fetchone()
        return _summary(row, clock())

    def _by_catalog(self, alias):
        return self.db.execute(
            """SELECT f.id FROM journal_favorites f JOIN journal_favorite_aliases a ON a.favorite_id = f.id
               WHERE a.identifier = ? ORDER BY f.active DESC, f.followed_at DESC LIMIT 1""", (alias,),
        ).fetchone()

    def restore_by_catalog(self, provider, journal_id):
        with self.lock, self.db:
            row = self._by_catalog(catalog_alias(provider, journal_id))
            if not row:
                return None
            self.db.execute("UPDATE journal_favorites SET active = 1 WHERE id = ?", (row["id"],))
            return self.get(row["id"])

    def follow(self, journal, provider, journal_id):
        published_id = journal_openalex(journal) or None
        ids = sorted(f"issn:{value}" for value in journal_issns(journal))
        alias = catalog_alias(provider, journal_id)
        with self.lock, self.db:
            self.db.execute("BEGIN IMMEDIATE")
            row = self.db.execute("SELECT id FROM journal_favorites WHERE openalex_id = ?", (published_id,)).fetchone()
            if not row:
                row = self._by_catalog(alias)
            if not row and ids:
                choices = ",".join("?" for _ in ids)
                row = self.db.execute(
                    f"""SELECT f.id FROM journal_favorites f JOIN journal_favorite_aliases a ON a.favorite_id = f.id
                        WHERE a.identifier IN ({choices}) AND (f.openalex_id IS NULL OR ? IS NULL OR f.openalex_id = ?)
                        ORDER BY (f.openalex_id IS NOT NULL) DESC, f.active DESC, f.followed_at LIMIT 1""",
                    (*ids, published_id, published_id),
                ).fetchone()
            favorite_id = row["id"] if row else str(uuid4())
            if row:
                self.db.execute(
                    """UPDATE journal_favorites SET active = 1,
                       journal_json = CASE WHEN openalex_id IS NOT NULL AND ? IS NULL THEN journal_json ELSE ? END,
                       openalex_id = COALESCE(openalex_id, ?) WHERE id = ?""",
                    (published_id, json.dumps(journal, ensure_ascii=False), published_id, favorite_id),
                )
            else:
                self.db.execute(
                    "INSERT INTO journal_favorites(id, openalex_id, journal_json, followed_at) VALUES (?, ?, ?, ?)",
                    (favorite_id, published_id, json.dumps(journal, ensure_ascii=False), clock().isoformat()),
                )
            if published_id:
                ids.append(catalog_alias("openalex", published_id))
            self.db.executemany(
                "INSERT OR IGNORE INTO journal_favorite_aliases VALUES (?, ?)",
                [(favorite_id, identifier) for identifier in [alias, *ids]],
            )
            return self.get(favorite_id)

    def unfollow(self, favorite_id):
        with self.lock, self.db:
            return bool(self.db.execute(
                "UPDATE journal_favorites SET active = 0, refresh_token = NULL WHERE id = ? AND active = 1",
                (favorite_id,),
            ).rowcount)

    def due(self, limit=2):
        now = clock()
        with self.lock:
            return [row["id"] for row in self.db.execute(
                """SELECT id FROM journal_favorites
                   WHERE active = 1 AND (last_attempt_at IS NULL OR last_attempt_at <= ?)
                   ORDER BY COALESCE(last_attempt_at, ''), followed_at LIMIT ?""",
                ((now - timedelta(days=1)).isoformat(), limit),
            )]

    def claim(self, favorite_id):
        now, token = clock(), str(uuid4())
        with self.lock, self.db:
            saved = self.db.execute(
                """UPDATE journal_favorites SET last_attempt_at = ?, refresh_token = ?
                   WHERE id = ? AND active = 1 AND (refresh_token IS NULL OR last_attempt_at <= ?)""",
                (now.isoformat(), token, favorite_id, (now - timedelta(minutes=15)).isoformat()),
            )
            return token if saved.rowcount else None

    def finish(self, favorite_id, token, papers, paper_status, publisher, publisher_status):
        checked = clock().isoformat()
        with self.lock, self.db:
            self.db.execute("BEGIN IMMEDIATE")
            saved = self.db.execute(
                """UPDATE journal_favorites SET refresh_token = NULL, paper_status_json = ?, publisher_status_json = ?,
                   papers_checked_at = COALESCE(?, papers_checked_at),
                   publisher_json = COALESCE(?, publisher_json),
                   publisher_checked_at = COALESCE(?, publisher_checked_at)
                   WHERE id = ? AND active = 1 AND refresh_token = ?""",
                (json.dumps(paper_status), json.dumps(publisher_status), checked if papers is not None else None,
                 json.dumps(publisher, ensure_ascii=False) if publisher is not None else None,
                 checked if publisher is not None else None, favorite_id, token),
            )
            if not saved.rowcount:
                return 0
            added = 0
            for paper in papers or []:
                stamp = paper.get("publication_date") or str(paper.get("year") or "")
                added += self.db.execute(
                    """INSERT OR IGNORE INTO journal_favorite_papers
                       (favorite_id, work_id, publication_sort, discovered_at, paper_json) VALUES (?, ?, ?, ?, ?)""",
                    (favorite_id, paper["library_id"], stamp, checked, json.dumps(paper, ensure_ascii=False)),
                ).rowcount
                self.db.execute(
                    """UPDATE journal_favorite_papers SET publication_sort = ?, paper_json = ?
                       WHERE favorite_id = ? AND work_id = ?""",
                    (stamp, json.dumps(paper, ensure_ascii=False), favorite_id, paper["library_id"]),
                )
            return added

    def release(self, favorite_id, token):
        with self.lock, self.db:
            self.db.execute(
                "UPDATE journal_favorites SET refresh_token = NULL WHERE id = ? AND refresh_token = ?", (favorite_id, token),
            )

    def papers(self, favorite_id, limit, offset, unread_only):
        seen_filter = f" AND {_UNSEEN}" if unread_only else ""
        with self.lock:
            rows = self.db.execute(
                f"""SELECT jp.paper_json, jp.discovered_at, ({_UNSEEN}) AS unread FROM journal_favorite_papers jp
                    WHERE jp.favorite_id = ? {seen_filter}
                    ORDER BY jp.publication_sort DESC, jp.discovered_at DESC, jp.work_id DESC LIMIT ? OFFSET ?""",
                (favorite_id, limit + 1, offset),
            ).fetchall()
        return [{**json.loads(row["paper_json"]), "followed_unread": bool(row["unread"]),
                 "followed_discovered_at": row["discovered_at"]} for row in rows[:limit]], len(rows) > limit

    def mark_seen(self, favorite_id, work_id=None):
        with self.lock, self.db:
            return self.db.execute(
                """UPDATE journal_favorite_papers SET seen_at = ?
                   WHERE favorite_id = ? AND seen_at IS NULL AND (? IS NULL OR work_id = ?)""",
                (clock().isoformat(), favorite_id, work_id, work_id),
            ).rowcount
