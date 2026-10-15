"""POST /kap/disclosures/collect runs the API-based KAP disclosure saver."""
from unittest.mock import AsyncMock, patch

from fastapi import FastAPI
from fastapi.testclient import TestClient

from api.dependencies import get_db_manager
from api.routers import external_analysis
from database.db_manager import DatabaseManager


class FakeDB:
    PoolExhaustedError = DatabaseManager.PoolExhaustedError


def _client():
    app = FastAPI()
    app.include_router(external_analysis.router, prefix="/api/external/v1")
    app.dependency_overrides[get_db_manager] = lambda: FakeDB()
    return TestClient(app)


def test_collect_reports_totals():
    run = AsyncMock(return_value={"success": True, "total": 659, "saved": 659, "disclosures": [{"x": 1}]})
    with patch("scrapers.kap_scraper.KAPScraper.scrape_and_save_disclosures", run):
        r = _client().post("/api/external/v1/kap/disclosures/collect", json={"days_back": 2})
    assert r.status_code == 200
    assert r.json() == {"contract_version": "1.1", "success": True, "total": 659, "saved": 659}
    assert run.await_args.kwargs == {"days_back": 2}


def test_upstream_failure_is_502_not_a_fake_success():
    run = AsyncMock(return_value={"success": False, "error": "invalid_response", "total": 0, "saved": 0})
    with patch("scrapers.kap_scraper.KAPScraper.scrape_and_save_disclosures", run):
        r = _client().post("/api/external/v1/kap/disclosures/collect", json={})
    assert r.status_code == 502
    assert r.json()["error"] == "invalid_response"


def test_kap_publish_date_parsing():
    from datetime import datetime, timezone
    from scrapers.kap_scraper import KAPScraper
    assert KAPScraper._parse_kap_publish_date("14.10.2026 22:36:00") == datetime(2026, 10, 14, 19, 36, tzinfo=timezone.utc)
    assert KAPScraper._parse_kap_publish_date("nonsense") is None
