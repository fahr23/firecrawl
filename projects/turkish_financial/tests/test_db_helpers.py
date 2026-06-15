"""
Unit tests for the new DatabaseManager helper methods:
  - upsert_disclosure()
  - upsert_bist_company()
  - upsert_news()

All tests are pure-unit: the DB is mocked so no Postgres connection is needed.
We verify that the helpers build correct SQL and call conn.commit().
db_manager.py is loaded directly from file (importlib) to avoid __init__.py
pulling in real psycopg2.
"""
import importlib.util
import os
import sys
import types
from unittest.mock import MagicMock, patch

import pytest

# ---------------------------------------------------------------------------
# Stub psycopg2 and config before loading db_manager
# ---------------------------------------------------------------------------

def _stub_psycopg2():
    """Inject a minimal psycopg2 stub with all symbols db_manager needs."""

    class _Json:
        def __init__(self, val):
            self.val = val

    class _RealDictCursor:
        pass

    p2 = types.ModuleType("psycopg2")
    p2.errors = types.ModuleType("psycopg2.errors")
    p2.errors.UniqueViolation = Exception
    p2.errors.DuplicateSchema = Exception
    p2.pool = types.ModuleType("psycopg2.pool")
    p2.pool.SimpleConnectionPool = MagicMock()
    p2.pool.PoolError = Exception
    p2.sql = types.ModuleType("psycopg2.sql")
    p2.sql.SQL = MagicMock(return_value=MagicMock())
    p2.sql.Identifier = MagicMock(return_value=MagicMock())
    p2.sql.Placeholder = MagicMock(return_value=MagicMock())
    p2.extras = types.ModuleType("psycopg2.extras")
    p2.extras.RealDictCursor = _RealDictCursor
    p2.extras.Json = _Json

    for name in ["psycopg2", "psycopg2.errors", "psycopg2.pool",
                 "psycopg2.sql", "psycopg2.extras"]:
        sys.modules.setdefault(name, getattr(p2, name.split(".")[-1], p2))
    sys.modules["psycopg2"] = p2
    sys.modules["psycopg2.extras"] = p2.extras
    sys.modules["psycopg2.sql"] = p2.sql
    sys.modules["psycopg2.pool"] = p2.pool
    sys.modules["psycopg2.errors"] = p2.errors
    return _Json


_Json = _stub_psycopg2()

# Stub config
_cfg = MagicMock()
_cfg.database.db_schema = "fin"
_cfg.database.pool_size = 2
_cfg.database.get_connection_params.return_value = {}
sys.modules.setdefault("config", types.ModuleType("config"))
sys.modules["config"].config = _cfg  # type: ignore

# Load db_manager directly
_DM_PATH = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "database", "db_manager.py")
)

_spec = importlib.util.spec_from_file_location("db_manager_under_test", _DM_PATH)
_dm_mod = importlib.util.module_from_spec(_spec)
with patch("psycopg2.pool.SimpleConnectionPool"):
    _spec.loader.exec_module(_dm_mod)

DatabaseManager = _dm_mod.DatabaseManager
# Reference Json from the loaded module so patching works on the right binding.
_dm_Json = _dm_mod.Json
_dm_sql = _dm_mod.sql


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

class FakeConn:
    """Connection stub that records cursor calls."""

    def __init__(self):
        self._cursor = FakeCursor()
        self.committed = False
        self.rolled_back = False

    def cursor(self, **kwargs):
        return self._cursor

    def commit(self):
        self.committed = True

    def rollback(self):
        self.rolled_back = True


class FakeCursor:
    def __init__(self, return_row=None):
        self.executed = []
        self._row = return_row

    def execute(self, q, params=None):
        self.executed.append((str(q), params))

    def fetchone(self):
        return self._row

    def fetchall(self):
        return []

    def close(self):
        pass


def _make_db(return_row=None) -> tuple:
    """Return (db_manager, FakeConn) with pool/sql mocked."""
    db = DatabaseManager.__new__(DatabaseManager)
    db.schema = "fin"
    db.pool = MagicMock()
    conn = FakeConn()
    conn._cursor = FakeCursor(return_row=return_row)
    db.get_connection = lambda: conn
    db.return_connection = lambda c: None
    return db, conn


# ---------------------------------------------------------------------------
# upsert_bist_company
# ---------------------------------------------------------------------------

class TestUpsertBistCompany:
    def test_returns_true_and_commits(self):
        db, conn = _make_db()
        with patch.object(_dm_mod, "sql", _dm_sql):
            result = db.upsert_bist_company("THYAO", name="THY", mkk_member_oid="aaa-111")
        assert result is True
        assert conn.committed is True

    def test_only_code_still_commits(self):
        db, conn = _make_db()
        with patch.object(_dm_mod, "sql", _dm_sql):
            result = db.upsert_bist_company("ZZZZ")
        assert result is True

    def test_db_exception_returns_false(self):
        db, conn = _make_db()
        conn.cursor = lambda **kw: (_ for _ in ()).throw(RuntimeError("boom"))
        result = db.upsert_bist_company("THYAO", mkk_member_oid="x")
        assert result is False
        assert conn.rolled_back is True


# ---------------------------------------------------------------------------
# upsert_disclosure
# ---------------------------------------------------------------------------

class TestUpsertDisclosure:
    def test_missing_disclosure_id_returns_false(self):
        db, conn = _make_db()
        result = db.upsert_disclosure({"stock_code": "THYAO"})
        assert result is False

    def test_valid_disclosure_commits(self):
        db, conn = _make_db()
        with patch.object(_dm_mod, "sql", _dm_sql):
            result = db.upsert_disclosure({
                "disclosure_id": "1234567",
                "stock_code": "THYAO",
                "subject": "ÖKD",
                "is_late": False,
            })
        assert result is True
        assert conn.committed is True

    def test_dict_data_wrapped_in_json(self):
        """A dict `data` field must be wrapped in Json()."""
        db, conn = _make_db()
        seen_json = []

        class CapturingJson:
            def __init__(self, val):
                seen_json.append(val)

        with patch.object(_dm_mod, "Json", CapturingJson):
            with patch.object(_dm_mod, "sql", _dm_sql):
                db.upsert_disclosure({
                    "disclosure_id": "999",
                    "data": {"key": "val"},
                })

        assert any(isinstance(v, dict) for v in seen_json)

    def test_exception_rolls_back(self):
        db, conn = _make_db()
        conn.cursor = lambda **kw: (_ for _ in ()).throw(RuntimeError("boom"))
        result = db.upsert_disclosure({"disclosure_id": "1"})
        assert result is False
        assert conn.rolled_back is True


# ---------------------------------------------------------------------------
# upsert_news
# ---------------------------------------------------------------------------

class TestUpsertNews:
    def test_missing_news_id_returns_none(self):
        db, conn = _make_db()
        result = db.upsert_news({"title": "No ID"})
        assert result is None

    def test_missing_title_returns_none(self):
        db, conn = _make_db()
        result = db.upsert_news({"news_id": "x"})
        assert result is None

    def test_valid_news_returns_row_id(self):
        db, conn = _make_db(return_row=(42,))
        with patch.object(_dm_mod, "sql", _dm_sql):
            result = db.upsert_news({
                "news_id": "n001",
                "title": "SPK Bülten",
                "news_category": "SPK",
            })
        assert result == 42
        assert conn.committed is True

    def test_dict_data_wrapped_in_json(self):
        db, conn = _make_db(return_row=(1,))
        seen_json = []

        class CapturingJson:
            def __init__(self, val):
                seen_json.append(val)

        with patch.object(_dm_mod, "Json", CapturingJson):
            with patch.object(_dm_mod, "sql", _dm_sql):
                db.upsert_news({
                    "news_id": "n002",
                    "title": "Test",
                    "data": {"raw": True},
                })

        assert any(isinstance(v, dict) for v in seen_json)

    def test_exception_rolls_back_and_returns_none(self):
        db, conn = _make_db()
        conn.cursor = lambda **kw: (_ for _ in ()).throw(RuntimeError("boom"))
        result = db.upsert_news({"news_id": "x", "title": "T"})
        assert result is None
        assert conn.rolled_back is True
