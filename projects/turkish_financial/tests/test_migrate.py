"""database.migrate: discovery, ordering, applied-once, and drift refusal (no DB)."""
from pathlib import Path

import pytest

from database import migrate
from database.migrate import Migration, apply, discover


class FakeCursor:
    def __init__(self, conn):
        self.conn = conn

    def execute(self, sql, params=None):
        self.conn.executed.append((sql.strip(), params))
        if "INSERT INTO" in sql and "schema_migrations" in sql:
            version, name, checksum = params
            self.conn.applied[version] = (name, checksum)

    def fetchall(self):
        return [(v, n, c) for v, (n, c) in sorted(self.conn.applied.items())]

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


class FakeConn:
    def __init__(self, applied=None):
        self.applied = dict(applied or {})
        self.executed = []
        self.autocommit = False
        self.commits = 0
        self.rollbacks = 0

    def cursor(self):
        return FakeCursor(self)

    def commit(self):
        self.commits += 1

    def rollback(self):
        self.rollbacks += 1

    def ran(self, fragment):
        return any(fragment in sql for sql, _ in self.executed)


def _mig(v, name, sql="SELECT 1;"):
    return Migration(v, name, sql)


def test_repository_migrations_are_well_formed_and_ordered():
    found = discover()
    assert [m.version for m in found] == sorted(m.version for m in found)
    assert found[0].version == 1
    assert {m.name for m in found} >= {"schema_migrations", "timestamptz", "point_in_time_indexes"}


def test_bad_file_name_is_rejected(tmp_path: Path):
    (tmp_path / "2_oops.sql").write_text("SELECT 1;")
    with pytest.raises(ValueError, match="bad migration file name"):
        discover(tmp_path)


def test_duplicate_versions_are_rejected(tmp_path: Path):
    (tmp_path / "001_a.sql").write_text("SELECT 1;")
    (tmp_path / "001_b.sql").write_text("SELECT 2;")
    with pytest.raises(ValueError, match="duplicate"):
        discover(tmp_path)


def test_applies_only_pending_in_order_and_records_them():
    first = _mig(1, "one", "CREATE TABLE a (x int);")
    conn = FakeConn(applied={1: ("one", first.checksum)})
    done = apply(conn, [first, _mig(3, "three", "SELECT 3;"), _mig(2, "two", "SELECT 2;")],
                 schema="s", build_baseline=False)
    assert done == ["002_two", "003_three"]  # version order, whatever order they were passed in
    assert not conn.ran("CREATE TABLE a")
    assert conn.applied[2][0] == "two" and conn.applied[3][0] == "three"
    assert conn.ran("pg_advisory_lock") and conn.ran("pg_advisory_unlock")


def test_up_to_date_applies_nothing():
    m = _mig(1, "one")
    conn = FakeConn(applied={1: ("one", m.checksum)})
    assert apply(conn, [m], schema="s", build_baseline=False) == []


def test_changed_applied_migration_is_refused_and_lock_released():
    conn = FakeConn(applied={1: ("one", "0" * 64)})
    with pytest.raises(RuntimeError, match="changed after it was applied"):
        apply(conn, [_mig(1, "one", "SELECT 'edited';")], schema="s", build_baseline=False)
    assert conn.rollbacks == 1
    assert conn.ran("pg_advisory_unlock")


def test_each_migration_runs_inside_the_target_schema():
    conn = FakeConn()
    apply(conn, [_mig(1, "one")], schema="turkish_financial", build_baseline=False)
    assert conn.ran('SET LOCAL search_path TO "turkish_financial", public')
