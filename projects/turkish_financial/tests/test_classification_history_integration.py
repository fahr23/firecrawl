"""
Integration tests for FA-10's classification/membership history semantics
(DatabaseManager.record_stock_classification / record_index_membership).

These exercise real SQL (ON CONFLICT, UPDATE-then-INSERT for the "close prior,
open new" pattern) against a live Postgres connection, so they are marked
`integration` and need the database dependency (unlike the rest of the
turkish-financial-test lane, which runs with --no-deps).

Run via: docker compose run --rm turkish-financial-test python -m pytest -q \
    tests/test_classification_history_integration.py
"""
from datetime import date

import pytest

from database.db_manager import DatabaseManager

pytestmark = pytest.mark.integration


@pytest.fixture
def db():
    return DatabaseManager()


def _cleanup(db, stock_code, index_code):
    conn = db.get_connection()
    try:
        cur = conn.cursor()
        cur.execute("DELETE FROM stock_classification_history WHERE stock_code = %s", (stock_code,))
        cur.execute("DELETE FROM index_membership_history WHERE stock_code = %s AND index_code = %s", (stock_code, index_code))
        conn.commit()
    finally:
        db.return_connection(conn)


class TestRecordStockClassification:
    def test_first_classification_opens_a_row(self, db):
        _cleanup(db, "TESTCO", "TESTIDX")
        try:
            db.record_stock_classification("TESTCO", "Transportation", "Airlines", date(2026, 1, 1))
            rows = db.query("SELECT sector, valid_from, valid_to FROM stock_classification_history WHERE stock_code = %s", ("TESTCO",))
            assert len(rows) == 1
            assert rows[0]["sector"] == "Transportation"
            assert rows[0]["valid_to"] is None
        finally:
            _cleanup(db, "TESTCO", "TESTIDX")

    def test_repeating_the_same_classification_is_a_no_op(self, db):
        _cleanup(db, "TESTCO", "TESTIDX")
        try:
            db.record_stock_classification("TESTCO", "Transportation", "Airlines", date(2026, 1, 1))
            db.record_stock_classification("TESTCO", "Transportation", "Airlines", date(2026, 2, 1))
            rows = db.query("SELECT valid_from FROM stock_classification_history WHERE stock_code = %s", ("TESTCO",))
            assert len(rows) == 1  # still just the one row from Jan 1
        finally:
            _cleanup(db, "TESTCO", "TESTIDX")

    def test_reclassification_closes_prior_and_opens_new(self, db):
        _cleanup(db, "TESTCO", "TESTIDX")
        try:
            db.record_stock_classification("TESTCO", "Transportation", "Airlines", date(2026, 1, 1))
            db.record_stock_classification("TESTCO", "Industrials", "Airlines", date(2026, 3, 1))
            rows = db.query(
                "SELECT sector, valid_from, valid_to FROM stock_classification_history WHERE stock_code = %s ORDER BY valid_from",
                ("TESTCO",),
            )
            assert len(rows) == 2
            assert rows[0]["sector"] == "Transportation"
            assert rows[0]["valid_to"] == date(2026, 3, 1)
            assert rows[1]["sector"] == "Industrials"
            assert rows[1]["valid_to"] is None
        finally:
            _cleanup(db, "TESTCO", "TESTIDX")


class TestRecordIndexMembership:
    def test_join_opens_a_row(self, db):
        _cleanup(db, "TESTCO", "TESTIDX")
        try:
            db.record_index_membership("TESTIDX", "TESTCO", date(2026, 1, 1), True)
            rows = db.query("SELECT valid_from, valid_to FROM index_membership_history WHERE stock_code = %s AND index_code = %s", ("TESTCO", "TESTIDX"))
            assert len(rows) == 1
            assert rows[0]["valid_to"] is None
        finally:
            _cleanup(db, "TESTCO", "TESTIDX")

    def test_leave_closes_the_open_row(self, db):
        _cleanup(db, "TESTCO", "TESTIDX")
        try:
            db.record_index_membership("TESTIDX", "TESTCO", date(2026, 1, 1), True)
            db.record_index_membership("TESTIDX", "TESTCO", date(2026, 6, 1), False)
            rows = db.query("SELECT valid_from, valid_to FROM index_membership_history WHERE stock_code = %s AND index_code = %s", ("TESTCO", "TESTIDX"))
            assert len(rows) == 1
            assert rows[0]["valid_to"] == date(2026, 6, 1)
        finally:
            _cleanup(db, "TESTCO", "TESTIDX")

    def test_joining_twice_does_not_duplicate(self, db):
        _cleanup(db, "TESTCO", "TESTIDX")
        try:
            db.record_index_membership("TESTIDX", "TESTCO", date(2026, 1, 1), True)
            db.record_index_membership("TESTIDX", "TESTCO", date(2026, 2, 1), True)
            rows = db.query("SELECT valid_from FROM index_membership_history WHERE stock_code = %s AND index_code = %s", ("TESTCO", "TESTIDX"))
            assert len(rows) == 1
        finally:
            _cleanup(db, "TESTCO", "TESTIDX")
