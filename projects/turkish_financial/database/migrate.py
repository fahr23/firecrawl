"""
Versioned schema migrations.

    python -m database.migrate            apply pending migrations
    python -m database.migrate --status   list applied / pending

Migrations are `database/migrations/NNN_name.sql`, applied in version order,
each in its own transaction and recorded in `schema_migrations` with a sha256
checksum. An applied file whose content later changes is refused (drift), so
history can't be rewritten silently. A Postgres advisory lock makes concurrent
runners (several pods starting at once) safe.

The pre-existing tables are still created by DatabaseManager (the baseline);
`apply()` builds that baseline first, so a fresh database ends in the same
state as an upgraded one.
"""
from __future__ import annotations

import argparse
import hashlib
import logging
import os
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional

logger = logging.getLogger(__name__)

MIGRATIONS_DIR = Path(__file__).parent / "migrations"
_FILE_RE = re.compile(r"^(\d{3,})_([a-z0-9_]+)\.sql$")
_LOCK_ID = 74_210_001  # arbitrary, stable


@dataclass(frozen=True)
class Migration:
    version: int
    name: str
    sql: str

    @property
    def checksum(self) -> str:
        return hashlib.sha256(self.sql.encode("utf-8")).hexdigest()


def discover(directory: Path = MIGRATIONS_DIR) -> List[Migration]:
    found = []
    for path in sorted(directory.glob("*.sql")):
        m = _FILE_RE.match(path.name)
        if not m:
            raise ValueError(f"bad migration file name: {path.name} (want NNN_name.sql)")
        found.append(Migration(int(m.group(1)), m.group(2), path.read_text(encoding="utf-8")))
    versions = [m.version for m in found]
    if len(versions) != len(set(versions)):
        raise ValueError(f"duplicate migration versions in {directory}")
    return sorted(found, key=lambda m: m.version)


def _connect():
    import psycopg2

    from config import config

    return psycopg2.connect(**config.database.get_connection_params())


def _schema() -> str:
    from config import config

    return config.database.db_schema


def _ensure_table(cur, schema: str) -> None:
    cur.execute(f'CREATE SCHEMA IF NOT EXISTS "{schema}"')
    cur.execute(f'''
        CREATE TABLE IF NOT EXISTS "{schema}".schema_migrations (
            version    INTEGER PRIMARY KEY,
            name       TEXT NOT NULL,
            checksum   TEXT NOT NULL,
            applied_at TIMESTAMPTZ NOT NULL DEFAULT now()
        )''')


def _applied(cur, schema: str) -> dict:
    cur.execute(f'SELECT version, name, checksum FROM "{schema}".schema_migrations ORDER BY version')
    return {row[0]: (row[1], row[2]) for row in cur.fetchall()}


def apply(conn=None, migrations: Optional[List[Migration]] = None, schema: Optional[str] = None,
          build_baseline: bool = True) -> List[str]:
    """Apply pending migrations; returns the names applied (empty when up to date)."""
    if build_baseline:
        from database.db_manager import DatabaseManager

        DatabaseManager()  # creates/updates the baseline tables
    schema = schema or _schema()
    migrations = sorted(discover() if migrations is None else migrations, key=lambda m: m.version)
    own = conn is None
    conn = conn or _connect()
    done: List[str] = []
    try:
        conn.autocommit = True
        with conn.cursor() as cur:
            cur.execute("SELECT pg_advisory_lock(%s)", (_LOCK_ID,))
        try:
            conn.autocommit = False
            with conn.cursor() as cur:
                _ensure_table(cur, schema)
                applied = _applied(cur, schema)
            conn.commit()

            for mig in migrations:
                if mig.version in applied:
                    name, checksum = applied[mig.version]
                    if checksum != mig.checksum:
                        raise RuntimeError(
                            f"migration {mig.version:03d}_{mig.name} changed after it was applied "
                            f"(recorded {checksum[:12]}, file {mig.checksum[:12]}); add a new migration instead"
                        )
                    continue
                with conn.cursor() as cur:
                    cur.execute(f'SET LOCAL search_path TO "{schema}", public')
                    cur.execute(mig.sql)
                    cur.execute(
                        f'INSERT INTO "{schema}".schema_migrations (version, name, checksum) VALUES (%s, %s, %s)',
                        (mig.version, mig.name, mig.checksum),
                    )
                conn.commit()
                done.append(f"{mig.version:03d}_{mig.name}")
                logger.info("applied migration %03d_%s", mig.version, mig.name)
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.autocommit = True
            with conn.cursor() as cur:
                cur.execute("SELECT pg_advisory_unlock(%s)", (_LOCK_ID,))
    finally:
        if own:
            conn.close()
    return done


def status(conn=None, schema: Optional[str] = None) -> List[str]:
    schema = schema or _schema()
    own = conn is None
    conn = conn or _connect()
    try:
        with conn.cursor() as cur:
            _ensure_table(cur, schema)
            applied = _applied(cur, schema)
        conn.commit()
    finally:
        if own:
            conn.close()
    return [
        f"{m.version:03d}_{m.name}: {'applied' if m.version in applied else 'PENDING'}"
        for m in discover()
    ]


def main(argv: Optional[List[str]] = None) -> int:
    logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"), format="%(asctime)s %(levelname)s %(message)s")
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--status", action="store_true", help="list applied/pending migrations")
    args = parser.parse_args(argv)
    if args.status:
        print("\n".join(status()) or "no migrations")
        return 0
    applied = apply()
    print("applied: " + (", ".join(applied) if applied else "nothing (up to date)"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
