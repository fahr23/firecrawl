"""KAP fundamental collection records every attempt (with the failure reason), and
the queue treats a failed attempt as "tried" so it doesn't lead every run."""
import asyncio

from api.routers import external_analysis as ea


class FakeDB:
    def __init__(self):
        self.executed = []
        self.queries = []

    def execute(self, sql, params=None):
        self.executed.append((" ".join(sql.split()), params))
        return True

    def query(self, sql, params=None):
        self.queries.append(" ".join(sql.split()))
        return [{"code": "AAA "}]


class FakeScraper:
    KAP_PAGE_DELAY_S = 0

    def __init__(self, db_manager=None):
        pass

    async def refresh_member_oids_via_get(self, instruments):
        return None

    async def scrape_financial_statements(self, instruments):
        if instruments == ["GOOD"]:
            return {"processed": [{"stock_code": "GOOD"}], "failed": []}
        return {"processed": [], "failed": [{"stock_code": instruments[0], "reason": "unit_unknown"},
                                            {"stock_code": instruments[0], "reason": "no_parsable_facts"}]}


def _run(monkeypatch, tickers):
    import scrapers.kap_scraper as ks
    import infrastructure.contracts.instrument_identity_map as idm

    monkeypatch.setattr(ks, "KAPScraper", FakeScraper)
    monkeypatch.setattr(idm, "resolve_member_oid", lambda ticker, db_manager=None: "oid")
    db = FakeDB()
    asyncio.new_event_loop().run_until_complete(ea._collect_kap_fundamentals(db, tickers))
    return db


def test_each_attempt_is_recorded_with_its_outcome(monkeypatch, caplog):
    db = _run(monkeypatch, ["GOOD", "BAD"])
    attempts = [p for sql, p in db.executed if "kap_fundamental_attempts" in sql]
    assert attempts == [("GOOD", "fetched"), ("BAD", "no_parsable_facts,unit_unknown")]
    assert "KAP fundamental collection got nothing for BAD: no_parsable_facts,unit_unknown" in caplog.text
    state = ea._kap_fundamental_collection_state
    assert (state["fetched"], state["failed"], state["status"]) == (1, 1, "completed")


def test_queue_orders_by_latest_of_collected_and_attempted():
    db = FakeDB()
    assert ea._fundamental_collection_queue(db, 5) == ["AAA"]
    sql = db.queries[0]
    assert "LEFT JOIN kap_fundamental_attempts a" in sql
    assert "ORDER BY GREATEST(f.last_at, a.last_attempt_at) ASC NULLS FIRST" in sql
