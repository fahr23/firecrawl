"""
The daily KAP disclosure step (production_kap_final) stores disclosures under KAP's
own index and ticker, and classifies FA-07 events.

Before: synthetic ids (live_kap_<time>_<n>) re-inserted every run, company cells
ran several companies together, stock_code was never set and no events were made.
"""
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

from production_kap_final import ProductionKAPScraper

_PUBLISHED = datetime(2026, 10, 13, 11, 48, 14, tzinfo=timezone.utc)
_BASIC = {
    "disclosure_index": "1680281", "stock_code": "BRKO", "related_stocks": None,
    "company_name": "BİRKO A.Ş.", "title": "Genel Kurul İşlemlerine İlişkin Bildirim",
    "disclosure_class": "ODA", "disclosure_type": "CA", "disclosure_category": "STT",
    "published_at": _PUBLISHED, "is_late": False, "attachment_count": 6, "mkk_member_oid": "oid",
}


def _row():
    return {"disclosure_id": "live_kap_20261015_181636_49", "company_name": "BİRKO …-UMPAŞ HOLDİNG A.Ş.",
            "disclosure_type": "Genel Kurul", "disclosure_date": "2026-10-15", "data": {"cells": []}}


def test_list_row_takes_kaps_identity():
    item = _row()
    ProductionKAPScraper._apply_disclosure_basic(item, _BASIC)
    assert item["disclosure_id"] == "1680281"
    assert item["kap_identity"] is True
    assert item["stock_code"] == "BRKO"
    assert item["company_name"] == "BİRKO A.Ş."
    assert item["subject_code"] == "ODA"
    assert item["disclosure_date"] == _PUBLISHED.date()
    assert item["data"]["disclosure_basic"]["published_at"] == _PUBLISHED.isoformat()
    assert item["data"]["cells"] == []


def test_row_without_identity_is_left_unmarked():
    item = _row()
    ProductionKAPScraper._apply_disclosure_basic(item, {})
    assert "kap_identity" not in item
    assert item["disclosure_id"].startswith("live_kap_")


def test_events_are_classified_with_ticker_and_available_at():
    item = _row()
    ProductionKAPScraper._apply_disclosure_basic(item, _BASIC)
    db = MagicMock()
    db.upsert_kap_event.return_value = True
    with patch("database.db_manager.DatabaseManager", return_value=db):
        saved = ProductionKAPScraper._save_events([item, _row()])  # second row has no identity
    assert saved == 1
    event = db.upsert_kap_event.call_args[0][0]
    assert event["stock_code"] == "BRKO"
    assert event["source_disclosure_index"] == "1680281"
    assert event["published_at"] == _PUBLISHED
    assert event["available_at"] == _PUBLISHED
