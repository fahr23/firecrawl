"""
Unit tests for FA-06 share-count change detection and KAP-event matching.

Pure functions over small fixtures — no DB, no network.
"""
from datetime import date

from domain.services.corporate_action_detector import (
    detect_share_count_changes,
    match_detected_change,
)


def _market_row(trading_date, shares_outstanding):
    return {"trading_date": trading_date, "shares_outstanding": shares_outstanding}


class TestDetectShareCountChanges:
    def test_no_change_detected_for_stable_series(self):
        series = [_market_row(date(2026, 1, d), 1_000_000) for d in range(1, 5)]
        assert detect_share_count_changes(series) == []

    def test_bonus_issue_sized_jump_detected(self):
        series = [
            _market_row(date(2026, 1, 1), 1_000_000),
            _market_row(date(2026, 1, 2), 1_000_000),
            _market_row(date(2026, 1, 3), 1_200_000),  # +20%
        ]
        changes = detect_share_count_changes(series)
        assert len(changes) == 1
        assert changes[0]["ex_date"] == date(2026, 1, 3)
        assert round(changes[0]["implied_ratio"], 4) == 0.2

    def test_tiny_rounding_difference_is_not_a_change(self):
        series = [
            _market_row(date(2026, 1, 1), 1_000_000),
            _market_row(date(2026, 1, 2), 1_000_050),  # 0.005% — noise
        ]
        assert detect_share_count_changes(series) == []

    def test_missing_shares_outstanding_rows_are_skipped(self):
        series = [
            _market_row(date(2026, 1, 1), 1_000_000),
            {"trading_date": date(2026, 1, 2), "shares_outstanding": None},
            _market_row(date(2026, 1, 3), 1_200_000),
        ]
        changes = detect_share_count_changes(series)
        assert len(changes) == 1
        # prior remains the last row WITH a value — Jan 1, not the null Jan 2 row.
        assert changes[0]["shares_before"] == 1_000_000


class TestMatchDetectedChange:
    def test_matches_nearby_bonus_issue_event(self):
        change = {"ex_date": date(2026, 5, 10), "implied_ratio": 0.2}
        events = [
            {"event_type": "bonus_issue", "published_at": date(2026, 5, 8), "source_disclosure_index": "111"},
            {"event_type": "financial_report", "published_at": date(2026, 5, 9), "source_disclosure_index": "222"},
        ]
        result = match_detected_change(change, events)
        assert result["match_status"] == "matched"
        assert result["event_type"] == "bonus_issue"
        assert result["source_disclosure_index"] == "111"

    def test_picks_closest_date_when_multiple_candidates(self):
        change = {"ex_date": date(2026, 5, 10)}
        events = [
            {"event_type": "bonus_issue", "published_at": date(2026, 5, 1), "source_disclosure_index": "far"},
            {"event_type": "rights_issue", "published_at": date(2026, 5, 9), "source_disclosure_index": "near"},
        ]
        result = match_detected_change(change, events)
        assert result["source_disclosure_index"] == "near"

    def test_no_candidate_within_window_is_unmatched(self):
        change = {"ex_date": date(2026, 5, 10)}
        events = [
            {"event_type": "bonus_issue", "published_at": date(2026, 1, 1), "source_disclosure_index": "111"},
        ]
        result = match_detected_change(change, events, date_window_days=10)
        assert result["match_status"] == "unmatched"
        assert "event_type" not in result

    def test_non_share_events_are_ignored(self):
        change = {"ex_date": date(2026, 5, 10)}
        events = [
            {"event_type": "financial_report", "published_at": date(2026, 5, 10), "source_disclosure_index": "111"},
        ]
        result = match_detected_change(change, events)
        assert result["match_status"] == "unmatched"

    def test_missing_ex_date_is_unmatched(self):
        result = match_detected_change({"ex_date": None}, [])
        assert result["match_status"] == "unmatched"
