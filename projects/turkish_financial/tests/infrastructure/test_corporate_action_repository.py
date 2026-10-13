"""
Tests for CorporateActionRepository.detect_and_persist (FA-06).

Drives the full detection pipeline (share-count change → KAP-event match →
price_factor) against a fake db_manager, without any real DB or network.
"""
from datetime import date

from infrastructure.repositories.corporate_action_repository import CorporateActionRepository


class FakeDB:
    """Records every upsert_corporate_action call; serves canned query results."""

    def __init__(self, market_rows, event_rows):
        self.market_rows = market_rows
        self.event_rows = event_rows
        self.upserted = []

    def query(self, sql, params=None):
        if "isyatirim_market_history" in sql:
            return self.market_rows
        if "kap_events" in sql:
            return self.event_rows
        return []

    def upsert_corporate_action(self, action):
        self.upserted.append(action)
        return True


def _market_row(trading_date_ddmmyyyy, shares_outstanding, close_try=100.0):
    return {"data": {
        "trading_date": trading_date_ddmmyyyy,
        "shares_outstanding": shares_outstanding,
        "close_try": close_try,
    }}


class TestDetectAndPersist:
    def test_bonus_issue_is_matched_and_priced_exactly(self):
        market_rows = [
            _market_row("01-05-2026", 1_000_000),
            _market_row("08-05-2026", 1_200_000),  # +20% — bonus-issue sized
        ]
        event_rows = [
            {"event_type": "bonus_issue", "published_at": date(2026, 5, 7), "source_disclosure_index": "111"},
        ]
        db = FakeDB(market_rows, event_rows)
        repo = CorporateActionRepository(db)

        summary = repo.detect_and_persist("THYAO")

        assert summary == {"ticker": "THYAO", "detected": 1, "matched": 1, "priced": 1}
        assert len(db.upserted) == 1
        action = db.upserted[0]
        assert action["ticker"] == "THYAO"
        assert action["ex_date"] == date(2026, 5, 8)
        assert action["event_type"] == "bonus_issue"
        assert action["match_status"] == "matched"
        assert round(action["price_factor"], 4) == round(1 / 1.2, 4)
        assert action["source_disclosure_index"] == "111"

    def test_rights_issue_matched_but_unpriced_pending_term_extraction(self):
        market_rows = [
            _market_row("01-05-2026", 1_000_000),
            _market_row("08-05-2026", 1_250_000),  # +25% — rights-issue sized
        ]
        event_rows = [
            {"event_type": "rights_issue", "published_at": date(2026, 5, 6), "source_disclosure_index": "222"},
        ]
        db = FakeDB(market_rows, event_rows)
        repo = CorporateActionRepository(db)

        summary = repo.detect_and_persist("AKBNK")

        assert summary["matched"] == 1
        assert summary["priced"] == 0  # needs subscription_price — not parsed yet
        action = db.upserted[0]
        assert action["event_type"] == "rights_issue"
        assert action["match_status"] == "matched"
        assert action["price_factor"] is None
        assert action["ratio"] is not None  # the implied ratio IS known and stored

    def test_unmatched_change_persists_with_unmatched_status_no_factor(self):
        market_rows = [
            _market_row("01-05-2026", 1_000_000),
            _market_row("08-05-2026", 1_200_000),
        ]
        db = FakeDB(market_rows, event_rows=[])  # no KAP event anywhere nearby
        repo = CorporateActionRepository(db)

        summary = repo.detect_and_persist("THYAO")

        assert summary["matched"] == 0
        action = db.upserted[0]
        assert action["match_status"] == "unmatched"
        assert action["price_factor"] is None

    def test_no_share_count_change_persists_nothing(self):
        market_rows = [_market_row("01-05-2026", 1_000_000), _market_row("02-05-2026", 1_000_000)]
        db = FakeDB(market_rows, event_rows=[])
        repo = CorporateActionRepository(db)

        summary = repo.detect_and_persist("THYAO")

        assert summary == {"ticker": "THYAO", "detected": 0, "matched": 0, "priced": 0}
        assert db.upserted == []

    def test_idempotent_rerun_upserts_same_action_again(self):
        market_rows = [
            _market_row("01-05-2026", 1_000_000),
            _market_row("08-05-2026", 1_200_000),
        ]
        event_rows = [
            {"event_type": "bonus_issue", "published_at": date(2026, 5, 7), "source_disclosure_index": "111"},
        ]
        db = FakeDB(market_rows, event_rows)
        repo = CorporateActionRepository(db)

        repo.detect_and_persist("THYAO")
        repo.detect_and_persist("THYAO")

        # Both runs call upsert with the same (ticker, ex_date, event_type) key;
        # the DB layer's ON CONFLICT handles de-duplication, so we just assert
        # both calls produced identical action payloads (safe to re-run).
        assert len(db.upserted) == 2
        assert db.upserted[0] == db.upserted[1]
