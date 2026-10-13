"""
TCMB EVDS scraper — fails closed when no API key is configured (FA-00).

No simulated/mocked macro values are ever returned or written; a missing key
or an upstream failure both produce an honest `unavailable` result with zero
rows fetched/saved.
"""
from unittest.mock import Mock, patch

import pytest

from scrapers.tcmb_scraper import TCMBScraper


class _FakeDBManager:
    def __init__(self):
        self.inserted = []
        self._conn = Mock()
        self._cursor = Mock()
        self._conn.cursor.return_value = self._cursor

    def get_connection(self):
        return self._conn

    def return_connection(self, conn):
        pass


@pytest.mark.asyncio
async def test_no_api_key_is_unavailable_and_writes_nothing():
    db = _FakeDBManager()
    scraper = TCMBScraper(db, api_key=None)

    result = await scraper.scrape("TP.DK.USD.A", "2026-01-01", "2026-01-31")

    assert result["success"] is False
    assert result["status"] == "unavailable"
    assert result["records_fetched"] == 0
    assert result["records_saved"] == 0
    db._cursor.execute.assert_not_called()


@pytest.mark.asyncio
async def test_upstream_failure_is_unavailable_and_writes_nothing():
    db = _FakeDBManager()
    scraper = TCMBScraper(db, api_key="real-key")

    with patch("scrapers.tcmb_scraper.requests.get", side_effect=RuntimeError("network down")):
        result = await scraper.scrape("TP.DK.USD.A", "2026-01-01", "2026-01-31")

    assert result["success"] is False
    assert result["status"] == "unavailable"
    assert result["records_saved"] == 0
    db._cursor.execute.assert_not_called()


@pytest.mark.asyncio
async def test_with_api_key_fetches_and_saves_real_data():
    db = _FakeDBManager()
    scraper = TCMBScraper(db, api_key="real-key")

    upstream_response = Mock()
    upstream_response.raise_for_status = Mock()
    upstream_response.json.return_value = {
        "items": [
            {"Tarih": "01-01-2026", "TP.DK.USD.A": "35.12"},
            {"Tarih": "31-01-2026", "TP.DK.USD.A": "35.80"},
        ]
    }

    with patch("scrapers.tcmb_scraper.requests.get", return_value=upstream_response):
        result = await scraper.scrape("TP.DK.USD.A", "2026-01-01", "2026-01-31")

    assert result["success"] is True
    assert result["status"] == "ok"
    assert result["records_fetched"] == 2
    assert result["records_saved"] == 2
    # +1 for the "SET search_path" statement issued before the inserts.
    assert db._cursor.execute.call_count == 3
