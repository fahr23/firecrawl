"""
Unit tests for the three new KAPScraper methods added in Step 2:
  - refresh_member_oids()
  - scrape_and_save_disclosures()
  - scrape_kap_news()

All tests are pure-unit: no network, no DB. We stub out the scraper's
async helpers (_post_kap_api_json, _fetch_kap_api_json) and the
db_manager to verify the orchestration logic.

KAPScraper is loaded directly from its file (importlib) rather than via
`scrapers.__init__` to avoid chain-importing heavy dependencies.
"""
import asyncio
import importlib.util
import os
import sys
import types
from datetime import datetime
from unittest.mock import MagicMock, patch

import pytest


# ---------------------------------------------------------------------------
# Stubs for everything kap_scraper.py imports at module level
# ---------------------------------------------------------------------------

def _inject_stubs():
    """Put lightweight stubs into sys.modules before loading kap_scraper."""
    stubs = {
        "aiohttp": types.ModuleType("aiohttp"),
        "bs4": types.ModuleType("bs4"),
        "scrapers.base_scraper": types.ModuleType("scrapers.base_scraper"),
        "utils.text_extractor": types.ModuleType("utils.text_extractor"),
        "utils.pdf_downloader": types.ModuleType("utils.pdf_downloader"),
        "utils.llm_analyzer": types.ModuleType("utils.llm_analyzer"),
    }

    class FakeTimeout:
        def __init__(self, **kwargs):
            pass

    stubs["aiohttp"].ClientTimeout = FakeTimeout
    stubs["aiohttp"].ClientSession = MagicMock()
    stubs["bs4"].BeautifulSoup = MagicMock()

    class _FakePath:
        def __init__(self, *a):
            pass
        def mkdir(self, **kw):
            pass
        def __truediv__(self, other):
            return self

    class FakeBaseScraper:
        BASE_URL = "https://www.kap.org.tr"
        def __init__(self, *a, **kw):
            self.db_manager = None

    stubs["scrapers.base_scraper"].BaseScraper = FakeBaseScraper
    stubs["utils.text_extractor"].TextExtractorFactory = MagicMock()
    stubs["utils.pdf_downloader"].PDFDownloader = MagicMock()
    stubs["utils.llm_analyzer"].LLMAnalyzer = MagicMock()
    stubs["utils.llm_analyzer"].LocalLLMProvider = MagicMock()
    stubs["utils.llm_analyzer"].OpenAIProvider = MagicMock()
    stubs["utils.llm_analyzer"].GeminiProvider = MagicMock()

    for name, mod in stubs.items():
        sys.modules.setdefault(name, mod)

    return FakeBaseScraper, _FakePath


_FakeBase, _FakePath = _inject_stubs()

_SCRAPER_PATH = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "scrapers", "kap_scraper.py")
)


def _load_scraper_module():
    spec = importlib.util.spec_from_file_location("kap_scraper_under_test", _SCRAPER_PATH)
    mod = importlib.util.module_from_spec(spec)
    with patch("pathlib.Path.mkdir"):
        spec.loader.exec_module(mod)
    return mod


_kap_mod = _load_scraper_module()
KAPScraper = _kap_mod.KAPScraper


def _make_scraper():
    """Return a KAPScraper instance with no real I/O wired up."""
    with patch("pathlib.Path.mkdir"):
        scraper = KAPScraper.__new__(KAPScraper)
        _FakeBase.__init__(scraper)
        scraper.db_manager = None
        scraper.pdf_downloader = None
        scraper.text_extractor_factory = None
        scraper.llm_analyzer = None
        scraper.pdf_storage_path = _FakePath()
        scraper.text_storage_path = _FakePath()
        scraper.analysis_storage_path = _FakePath()
    return scraper


def run(coro):
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

class FakeDB:
    """Minimal db_manager stub that records upsert calls."""

    def __init__(self):
        self.companies: dict = {}
        self.disclosures: list = []
        self.news: list = []
        self._next_id = 1

    def query(self, sql, params=None):
        return []

    def upsert_bist_company(self, code, name=None, mkk_member_oid=None):
        self.companies[code] = {"name": name, "oid": mkk_member_oid}
        return True

    def upsert_disclosure(self, data):
        self.disclosures.append(dict(data))
        return True

    def upsert_news(self, data):
        self.news.append(dict(data))
        row_id = self._next_id
        self._next_id += 1
        return row_id


# ---------------------------------------------------------------------------
# refresh_member_oids tests
# ---------------------------------------------------------------------------

SAMPLE_MEMBERS = [
    {"mkkMemberOid": "aaa-111", "stockCodes": "THYAO", "shortName": "Türk Hava Yolları"},
    {"mkkMemberOid": "bbb-222", "stockCodes": "AKBNK,AKBNK2", "shortName": "Akbank"},
    {"mkkMemberOid": "4028e4a1413b7ef401413bc2251e0047", "stockCodes": "ASELS", "shortName": "Aselsan"},
    {"mkkMemberOid": "ccc-333", "stockCodes": "", "shortName": "No Stock Code"},
]


class TestRefreshMemberOids:
    def test_oids_saved_to_db(self):
        scraper = _make_scraper()
        db = FakeDB()
        scraper.db_manager = db

        async def fake_post(url, body):
            return SAMPLE_MEMBERS

        scraper._post_kap_api_json = fake_post
        result = run(scraper.refresh_member_oids())

        assert result["success"] is True
        assert result["resolved"] >= 3  # THYAO, AKBNK, ASELS
        assert "THYAO" in db.companies
        assert db.companies["THYAO"]["oid"] == "aaa-111"
        assert "AKBNK" in db.companies
        assert db.companies["AKBNK"]["oid"] == "bbb-222"

    def test_empty_response_returns_failure(self):
        scraper = _make_scraper()
        scraper.db_manager = None

        async def fake_post(url, body):
            return []

        scraper._post_kap_api_json = fake_post
        result = run(scraper.refresh_member_oids())

        assert result["success"] is False

    def test_wrapped_response_handled(self):
        scraper = _make_scraper()
        db = FakeDB()
        scraper.db_manager = db

        async def fake_post(url, body):
            return {"data": SAMPLE_MEMBERS}

        scraper._post_kap_api_json = fake_post
        result = run(scraper.refresh_member_oids())

        assert result["success"] is True
        assert result["resolved"] >= 3

    def test_no_db_updates_static_map(self):
        """refresh_member_oids must update the in-memory static map even without a DB."""
        from infrastructure.contracts.instrument_identity_map import STATIC_MEMBER_OID_MAP

        scraper = _make_scraper()
        scraper.db_manager = None

        ticker = "TSTCO_UNIT"
        async def fake_post(url, body):
            return [{"mkkMemberOid": "new-oid-xyz", "stockCodes": ticker, "shortName": "Test Co"}]

        scraper._post_kap_api_json = fake_post
        result = run(scraper.refresh_member_oids())

        assert result["success"] is True
        assert STATIC_MEMBER_OID_MAP.get(ticker) == "new-oid-xyz"

    def test_api_failure_returns_failure(self):
        scraper = _make_scraper()
        scraper.db_manager = None

        async def fake_post(url, body):
            return None

        scraper._post_kap_api_json = fake_post
        result = run(scraper.refresh_member_oids())

        assert result["success"] is False


# ---------------------------------------------------------------------------
# scrape_and_save_disclosures tests
# ---------------------------------------------------------------------------

SAMPLE_DISCLOSURES = [
    {
        "disclosureIndex": "1234567",
        "stockCodes": "THYAO",
        "publishDate": "2026-06-10T09:30:00",
        "kapTitle": "Yönetim Kurulu Kararı",
        "subject": "Özel Durum Açıklaması",
        "disclosureClass": "ÖZKD",
        "isLate": False,
        "attachmentCount": 1,
    },
    {
        "disclosureIndex": "9876543",
        "stockCodes": "AKBNK",
        "publishDate": "2026-06-11T14:00:00",
        "kapTitle": "Finansal Rapor",
        "subject": "Finansal Tablolar",
        "disclosureClass": "FR",
        "isLate": False,
        "attachmentCount": 0,
    },
]


class TestScrapeAndSaveDisclosures:
    def test_disclosures_saved_to_db(self):
        scraper = _make_scraper()
        db = FakeDB()
        scraper.db_manager = db

        async def fake_post(url, body):
            return SAMPLE_DISCLOSURES

        scraper._post_kap_api_json = fake_post
        result = run(scraper.scrape_and_save_disclosures(days_back=7))

        assert result["success"] is True
        assert result["total"] == 2
        assert result["saved"] == 2
        assert len(db.disclosures) == 2

    def test_disclosure_fields_populated(self):
        scraper = _make_scraper()
        db = FakeDB()
        scraper.db_manager = db

        async def fake_post(url, body):
            return SAMPLE_DISCLOSURES[:1]

        scraper._post_kap_api_json = fake_post
        run(scraper.scrape_and_save_disclosures())

        disc = db.disclosures[0]
        assert disc["disclosure_id"] == "1234567"
        assert disc["stock_code"] == "THYAO"
        assert disc["subject_code"] == "ÖZKD"
        assert disc["is_late"] is False
        assert disc["has_attachment"] is True

    def test_invalid_api_response_returns_failure(self):
        scraper = _make_scraper()
        scraper.db_manager = None

        async def fake_post(url, body):
            return {"error": "not a list"}

        scraper._post_kap_api_json = fake_post
        result = run(scraper.scrape_and_save_disclosures())

        assert result["success"] is False

    def test_missing_disclosure_index_skipped(self):
        scraper = _make_scraper()
        db = FakeDB()
        scraper.db_manager = db

        async def fake_post(url, body):
            return [{"stockCodes": "THYAO", "kapTitle": "No index"}]

        scraper._post_kap_api_json = fake_post
        result = run(scraper.scrape_and_save_disclosures())

        assert result["total"] == 1
        assert result["saved"] == 0
        assert len(db.disclosures) == 0

    def test_instrument_filter_builds_oid_list(self):
        """OID filter list must be included in the POST body."""
        scraper = _make_scraper()
        scraper.db_manager = None
        captured_body: dict = {}

        async def fake_post(url, body):
            captured_body.update(body)
            return []

        scraper._post_kap_api_json = fake_post

        with patch(
            "infrastructure.contracts.instrument_identity_map.resolve_member_oid",
            return_value="aaa-111",
        ):
            run(scraper.scrape_and_save_disclosures(instruments=["THYAO"]))

        assert "aaa-111" in captured_body.get("mkkMemberOidList", [])


# ---------------------------------------------------------------------------
# scrape_kap_news tests
# ---------------------------------------------------------------------------

SAMPLE_NEWS_API = [
    {
        "id": "n001",
        "title": "SPK Bülten 2026-06-10",
        "content": "SPK yönetim kurulu kararları açıklandı.",
        "publishDate": "2026-06-10T10:00:00",
        "type": "SPK",
    },
    {
        "id": "n002",
        "title": "MKK Duyurusu",
        "content": "Merkezi Kayıt Kuruluşu yeni hizmet başlattı.",
        "publishDate": "2026-06-11T08:00:00",
        "type": "MKK",
    },
]


class TestScrapeKapNews:
    def test_news_saved_from_api(self):
        scraper = _make_scraper()
        db = FakeDB()
        scraper.db_manager = db

        async def fake_get_json(url, prefer_firecrawl=True):
            return SAMPLE_NEWS_API

        scraper._fetch_kap_api_json = fake_get_json
        result = run(scraper.scrape_kap_news(days_back=7))

        assert result["success"] is True
        assert result["total"] >= 2
        assert result["saved"] == 2
        assert len(db.news) == 2

    def test_category_filter(self):
        scraper = _make_scraper()
        db = FakeDB()
        scraper.db_manager = db

        async def fake_get_json(url, prefer_firecrawl=True):
            return SAMPLE_NEWS_API

        scraper._fetch_kap_api_json = fake_get_json
        result = run(scraper.scrape_kap_news(categories=["SPK"]))

        assert result["saved"] == 1
        assert db.news[0]["news_category"] == "SPK"

    def test_fallback_to_firecrawl_when_api_empty(self):
        scraper = _make_scraper()
        db = FakeDB()
        scraper.db_manager = db
        call_count = {"firecrawl": 0}

        async def fake_get_json(url, prefer_firecrawl=True):
            return []

        async def fake_scrape_page(url):
            call_count["firecrawl"] += 1
            return {"success": True, "data": {"markdown": ""}}

        scraper._fetch_kap_api_json = fake_get_json
        scraper.scrape_kap_page_with_actions = fake_scrape_page
        run(scraper.scrape_kap_news())

        assert call_count["firecrawl"] >= 1

    def test_news_id_generated_when_missing(self):
        scraper = _make_scraper()
        db = FakeDB()
        scraper.db_manager = db

        async def fake_get_json(url, prefer_firecrawl=True):
            return [{"title": "Unnamed News", "publishDate": "2026-06-10", "type": "KAP"}]

        scraper._fetch_kap_api_json = fake_get_json
        run(scraper.scrape_kap_news())

        assert len(db.news) == 1
        assert db.news[0]["news_id"]  # auto-generated hash ID

    def test_no_db_still_returns_items(self):
        scraper = _make_scraper()
        scraper.db_manager = None

        async def fake_get_json(url, prefer_firecrawl=True):
            return SAMPLE_NEWS_API

        scraper._fetch_kap_api_json = fake_get_json
        result = run(scraper.scrape_kap_news())

        assert result["success"] is True
        assert len(result["items"]) >= 2
        assert result["saved"] == 0  # no DB → nothing persisted

    def test_date_filter_drops_old_items(self):
        """Items older than days_back must not appear in the output."""
        scraper = _make_scraper()
        scraper.db_manager = None

        old_item = {
            "id": "old-001",
            "title": "Very Old News",
            "publishDate": "2020-01-01T00:00:00",
            "type": "KAP",
        }
        recent_item = SAMPLE_NEWS_API[0]

        async def fake_get_json(url, prefer_firecrawl=True):
            return [old_item, recent_item]

        scraper._fetch_kap_api_json = fake_get_json
        result = run(scraper.scrape_kap_news(days_back=30))

        titles = [i["title"] for i in result["items"]]
        assert "Very Old News" not in titles
        assert recent_item["title"] in titles
