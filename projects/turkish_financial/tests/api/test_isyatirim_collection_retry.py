"""İş Yatırım collections: timed-out tickers get one retry after a pause, other
failures don't; the ownership run reuses a fresh fundamentals copy instead of
downloading the same company card again."""
import asyncio

import requests

from api.routers import external_analysis as ea


def _run(coro):
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


class FakeDB:
    def __init__(self, fresh=()):
        self.fresh = set(fresh)
        self.ownership = []
        self.saved = []

    def query(self, sql, params=None):
        return [{"code": c} for c in ("AAA", "BBB", "CCC")]

    def get_isyatirim_fundamentals(self, ticker, ttl):
        if ticker in self.fresh:
            payload = {"current_valuation": {"foreign_ownership_percent": 10.0, "free_float_percent": 20.0},
                       "one_year_statement_history": [1]}
            return {"fresh": True, "payload": payload, "age_seconds": 5}
        return {"fresh": False, "payload": None, "age_seconds": None}

    def upsert_isyatirim_fundamentals(self, ticker, payload):
        self.saved.append(ticker)
        return True

    def upsert_isyatirim_ownership_snapshot(self, ticker, day, foreign, free_float):
        self.ownership.append((ticker, foreign, free_float))
        return True


def _no_pause(monkeypatch):
    monkeypatch.setenv("ISYATIRIM_RETRY_PAUSE_SECONDS", "0")
    monkeypatch.setenv("ISYATIRIM_OWNERSHIP_COLLECTION_DELAY_SECONDS", "0.1")
    monkeypatch.setenv("ISYATIRIM_FUNDAMENTALS_COLLECTION_DELAY_SECONDS", "0.1")


def test_timeouts_are_retried_once_and_only_lasting_failures_count(monkeypatch):
    _no_pause(monkeypatch)
    calls = []

    def fetch(ticker):
        calls.append(ticker)
        if ticker == "AAA" and calls.count("AAA") == 1:
            raise requests.Timeout("read timed out")  # transient: recovers on retry
        if ticker == "BBB":
            raise requests.Timeout("read timed out")  # still down after retry
        if ticker == "CCC":
            raise ValueError("no financial table")  # permanent: not retried
        return {"current_valuation": {"foreign_ownership_percent": 1.0, "free_float_percent": 2.0}}

    monkeypatch.setattr(ea, "fetch_fundamentals", fetch)
    _run(ea._collect_all_isyatirim_fundamentals(FakeDB(), force=False))
    state = ea._fundamental_collection_state
    assert calls == ["AAA", "BBB", "CCC", "AAA", "BBB"]
    assert (state["fetched"], state["failed"], state["completed"], state["status"]) == (1, 2, 3, "completed")


def test_ownership_reuses_fresh_fundamentals_instead_of_refetching(monkeypatch):
    _no_pause(monkeypatch)
    fetched = []

    def fetch(ticker):
        fetched.append(ticker)
        return {"current_valuation": {"foreign_ownership_percent": 3.0, "free_float_percent": 4.0}}

    monkeypatch.setattr(ea, "fetch_fundamentals", fetch)
    db = FakeDB(fresh={"AAA", "BBB"})
    _run(ea._collect_all_ownership_snapshots(db))
    assert fetched == ["CCC"]  # only the one without a fresh copy
    assert db.saved == ["CCC"]  # and that download is kept for the fundamentals run
    assert db.ownership == [("AAA", 10.0, 20.0), ("BBB", 10.0, 20.0), ("CCC", 3.0, 4.0)]
    assert ea._ownership_collection_state["fetched"] == 3
