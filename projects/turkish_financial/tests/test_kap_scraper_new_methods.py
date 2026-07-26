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
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

import pytest


# ---------------------------------------------------------------------------
# Stubs for everything kap_scraper.py imports at module level
# ---------------------------------------------------------------------------

_MISSING_MODULE = object()


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

    originals = {
        name: sys.modules.get(name, _MISSING_MODULE)
        for name in stubs
    }
    for name, mod in stubs.items():
        sys.modules[name] = mod

    return FakeBaseScraper, _FakePath, originals


_FakeBase, _FakePath, _ORIGINAL_MODULES = _inject_stubs()

_SCRAPER_PATH = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "scrapers", "kap_scraper.py")
)


def _load_scraper_module():
    spec = importlib.util.spec_from_file_location("kap_scraper_under_test", _SCRAPER_PATH)
    mod = importlib.util.module_from_spec(spec)
    with patch("pathlib.Path.mkdir"):
        spec.loader.exec_module(mod)
    return mod


try:
    _kap_mod = _load_scraper_module()
finally:
    for _name, _original in _ORIGINAL_MODULES.items():
        if _original is _MISSING_MODULE:
            sys.modules.pop(_name, None)
        else:
            sys.modules[_name] = _original

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
        "publishDate": (datetime.now(timezone.utc) - timedelta(days=1)).isoformat(),
        "type": "SPK",
    },
    {
        "id": "n002",
        "title": "MKK Duyurusu",
        "content": "Merkezi Kayıt Kuruluşu yeni hizmet başlattı.",
        "publishDate": (datetime.now(timezone.utc) - timedelta(days=2)).isoformat(),
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
            return [{
                "title": "Unnamed News",
                "publishDate": (
                    datetime.now(timezone.utc) - timedelta(days=1)
                ).isoformat(),
                "type": "KAP",
            }]

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


# ---------------------------------------------------------------------------
# _kap_api_via_js tests
# ---------------------------------------------------------------------------

class TestKapApiViaJs:
    """Unit tests for the JS-injection proxy helper."""

    def _make_action_scraper(self, rawHtml_response: str, success: bool = True):
        """Return a scraper whose scrape_with_actions() returns a fixed rawHtml."""
        scraper = _make_scraper()

        async def fake_scrape_with_actions(url, actions, **kwargs):
            if not success:
                return {"success": False}
            return {
                "success": True,
                "data": {"rawHtml": rawHtml_response},
            }

        scraper.scrape_with_actions = fake_scrape_with_actions
        return scraper

    def test_get_returns_json_from_pre_element(self):
        """JS-API GET: JSON in <pre id="__kap_api_result"> is parsed and returned."""
        payload = '[{"disclosureIndex": "123"}]'
        html = f'<html><body><pre id="__kap_api_result" data-status="200">{payload}</pre></body></html>'
        scraper = self._make_action_scraper(html)
        result = run(scraper._kap_api_via_js("/tr/api/memberDisclosureQuery"))
        assert result == [{"disclosureIndex": "123"}]

    def test_post_returns_json_from_pre_element(self):
        """JS-API POST: JSON in <pre id="__kap_api_result"> is parsed and returned."""
        payload = '{"success": true, "data": []}'
        html = f'<pre id="__kap_api_result" data-status="200">{payload}</pre>'
        scraper = self._make_action_scraper(html)
        body = {"fromDate": "2026-01-01", "toDate": "2026-01-07", "memberType": "IGS"}
        result = run(scraper._kap_api_via_js("/tr/api/memberDisclosureQuery", method="POST", body=body))
        assert result == {"success": True, "data": []}

    def test_returns_none_when_scrape_fails(self):
        """_kap_api_via_js returns None when scrape_with_actions fails for all proxies."""
        scraper = self._make_action_scraper("", success=False)
        result = run(scraper._kap_api_via_js("/tr/api/memberDisclosureQuery"))
        assert result is None

    def test_returns_none_when_no_pre_element(self):
        """_kap_api_via_js returns None when the DOM injection anchor is absent."""
        scraper = self._make_action_scraper("<html><body>No result here</body></html>")
        result = run(scraper._kap_api_via_js("/tr/api/memberDisclosureQuery"))
        assert result is None

    def test_pre_element_with_double_quoted_id(self):
        """Regex handles double-quoted id attribute correctly."""
        payload = '[{"x": 1}]'
        html = f'<pre id="__kap_api_result">{payload}</pre>'
        scraper = self._make_action_scraper(html)
        result = run(scraper._kap_api_via_js("/tr/api/test"))
        assert result == [{"x": 1}]

    def test_pre_element_with_single_quoted_id(self):
        """Regex handles single-quoted id attribute correctly."""
        payload = '{"ok": true}'
        html = f"<pre id='__kap_api_result'>{payload}</pre>"
        scraper = self._make_action_scraper(html)
        result = run(scraper._kap_api_via_js("/tr/api/test"))
        assert result == {"ok": True}

    def test_actions_include_execute_javascript(self):
        """The injected actions list must contain an executeJavascript step."""
        captured_actions = []

        async def capture_actions(url, actions, **kwargs):
            captured_actions.extend(actions)
            return {"success": False}  # don't need a result

        scraper = _make_scraper()
        scraper.scrape_with_actions = capture_actions
        run(scraper._kap_api_via_js("/tr/api/test", method="POST", body={"k": "v"}))

        types_seen = {a["type"] for a in captured_actions}
        assert "executeJavascript" in types_seen
        js_action = next(a for a in captured_actions if a["type"] == "executeJavascript")
        assert "fetch" in js_action["script"]
        assert "POST" in js_action["script"]

    def test_post_body_embedded_in_script(self):
        """POST body dict is serialised into the JS script for the fetch() call."""
        captured_actions = []

        async def capture_actions(url, actions, **kwargs):
            captured_actions.extend(actions)
            return {"success": False}

        scraper = _make_scraper()
        scraper.scrape_with_actions = capture_actions
        body = {"fromDate": "2026-01-01", "memberType": "IGS"}
        run(scraper._kap_api_via_js("/tr/api/memberDisclosureQuery", method="POST", body=body))

        js_action = next(a for a in captured_actions if a["type"] == "executeJavascript")
        # The body JSON must be embedded somewhere in the script (double-encoded)
        assert "fromDate" in js_action["script"]


# ---------------------------------------------------------------------------
# _post_kap_api_json fallback chain tests
# ---------------------------------------------------------------------------

class TestPostKapApiJsonFallback:
    """_post_kap_api_json must try JS injection first, then cookie-warm, then bare POST."""

    def test_js_injection_success_returns_result(self):
        """When _kap_api_via_js succeeds the result is returned without trying aiohttp."""
        scraper = _make_scraper()

        async def good_js(*a, **kw):
            return [{"disclosureIndex": "777"}]

        scraper._kap_api_via_js = good_js

        result = run(scraper._post_kap_api_json(
            "https://www.kap.org.tr/tr/api/memberDisclosureQuery", {}
        ))
        assert result == [{"disclosureIndex": "777"}]

    def test_js_injection_failure_falls_through_to_aiohttp(self):
        """When JS injection returns None, _post_kap_api_json does not raise and returns None."""
        scraper = _make_scraper()

        # JS injection always returns nothing.
        async def no_result(*a, **kw):
            return None

        scraper._kap_api_via_js = no_result

        # The aiohttp stubs registered by _inject_stubs use a MagicMock for ClientSession.
        # With MagicMock, context-manager protocol returns MagicMocks (not coroutines), which
        # causes AttributeError inside _post_kap_api_json — but the method must NOT propagate
        # that as an unhandled exception; it must catch it and return None.
        result = run(scraper._post_kap_api_json(
            "https://www.kap.org.tr/tr/api/memberDisclosureQuery", {}
        ))
        # Either None (fallbacks failed) or a real value — never an exception.
        assert result is None or isinstance(result, (list, dict))


# ---------------------------------------------------------------------------
# _fetch_kap_api_json fallback chain tests
# ---------------------------------------------------------------------------

class TestFetchKapApiJsonFallback:
    """_fetch_kap_api_json must try JS injection first, then Firecrawl scrape, then aiohttp."""

    def test_js_injection_success_skips_firecrawl(self):
        """When JS injection returns JSON, Firecrawl scrape is never attempted."""
        scraper = _make_scraper()
        firecrawl_called = []

        async def good_js(*a, **kw):
            return [{"ok": True}]

        async def forbidden_scrape(*a, **kw):
            firecrawl_called.append(True)
            return {"success": False}

        scraper._kap_api_via_js = good_js
        scraper.scrape_url = forbidden_scrape

        result = run(scraper._fetch_kap_api_json(
            "https://www.kap.org.tr/tr/api/financialTable/listCompanyExcelMembers/abc/2025/T"
        ))
        assert result == [{"ok": True}]
        assert firecrawl_called == [], "Firecrawl scrape should not be called when JS succeeds"

    def test_firecrawl_scrape_used_when_js_fails(self):
        """When JS injection returns None, Firecrawl scrape is attempted."""
        scraper = _make_scraper()

        async def no_result(*a, **kw):
            return None

        async def fake_scrape(url, **kw):
            return {"success": True, "data": {"rawHtml": '[{"member": "x"}]'}}

        scraper._kap_api_via_js = no_result
        scraper.scrape_url = fake_scrape

        result = run(scraper._fetch_kap_api_json(
            "https://www.kap.org.tr/tr/api/financialTable/listCompanyExcelMembers/abc/2025/T"
        ))
        assert result == [{"member": "x"}]
