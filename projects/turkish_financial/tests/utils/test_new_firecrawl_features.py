"""
Tests for new Firecrawl features in BaseScraper and KAPScraper.
All Firecrawl SDK calls are mocked so tests run without a real API key.
"""
import pytest
from unittest.mock import MagicMock, AsyncMock, patch
from typing import Dict, Any


# ---------------------------------------------------------------------------
# Minimal concrete subclass so we can instantiate BaseScraper
# ---------------------------------------------------------------------------

def _make_scraper(mock_firecrawl=None):
    """Create a BaseScraper subclass instance with a mocked FirecrawlApp."""
    with patch("scrapers.base_scraper.FirecrawlApp") as MockFC:
        if mock_firecrawl is not None:
            MockFC.return_value = mock_firecrawl
        from scrapers.base_scraper import BaseScraper

        class ConcreteScraper(BaseScraper):
            async def scrape(self, **kwargs) -> Dict[str, Any]:
                return {}

        scraper = ConcreteScraper()
        if mock_firecrawl is not None:
            scraper.firecrawl = mock_firecrawl
        return scraper


# ---------------------------------------------------------------------------
# map_url() tests
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_map_url_success():
    """map_url returns links list on success."""
    fc = MagicMock()
    mock_result = MagicMock()
    mock_result.links = ["https://example.com/a", "https://example.com/b"]
    fc.map.return_value = mock_result

    scraper = _make_scraper(fc)
    result = await scraper.map_url("https://example.com", limit=100)

    assert result["success"] is True
    assert result["total"] == 2
    assert len(result["links"]) == 2
    fc.map.assert_called_once()


@pytest.mark.asyncio
async def test_map_url_with_search():
    """map_url passes search param to firecrawl.map_url."""
    fc = MagicMock()
    mock_result = MagicMock()
    mock_result.links = ["https://example.com/found"]
    fc.map.return_value = mock_result

    scraper = _make_scraper(fc)
    result = await scraper.map_url("https://example.com", search="annual report")

    assert result["success"] is True
    call_kwargs = fc.map.call_args
    assert call_kwargs[1].get("search") == "annual report"


@pytest.mark.asyncio
async def test_map_url_failure_returns_empty_links():
    """map_url returns empty links on exception."""
    fc = MagicMock()
    fc.map.side_effect = Exception("network error")

    scraper = _make_scraper(fc)
    result = await scraper.map_url("https://example.com")

    assert result["success"] is False
    assert result["links"] == []
    assert "network error" in result["error"]


# ---------------------------------------------------------------------------
# batch_scrape_urls() tests
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_batch_scrape_urls_success():
    """batch_scrape_urls returns data list on success."""
    fc = MagicMock()
    page1 = MagicMock()
    page1.markdown = "# Page 1"
    page2 = MagicMock()
    page2.markdown = "# Page 2"

    result_obj = MagicMock()
    result_obj.data = [page1, page2]
    fc.batch_scrape.return_value = result_obj

    scraper = _make_scraper(fc)
    result = await scraper.batch_scrape_urls(
        ["https://a.com", "https://b.com"]
    )

    assert result["success"] is True
    assert result["total"] == 2
    assert len(result["data"]) == 2


@pytest.mark.asyncio
async def test_batch_scrape_urls_falls_back_to_sync():
    """batch_scrape_urls falls back to synchronous method when async unavailable."""
    fc = MagicMock()
    fc.batch_scrape = None

    job = MagicMock()
    status = MagicMock()
    page = MagicMock()
    page.markdown = "# Sync page"
    status.data = [page]
    job.wait_for_completion.return_value = status
    fc.async_batch_scrape_urls.return_value = job

    scraper = _make_scraper(fc)
    result = await scraper.batch_scrape_urls(["https://a.com"])

    assert result["success"] is True
    assert result["total"] == 1


@pytest.mark.asyncio
async def test_batch_scrape_urls_failure():
    """batch_scrape_urls returns success=False on exception."""
    fc = MagicMock()
    fc.batch_scrape.side_effect = Exception("server error")

    scraper = _make_scraper(fc)
    result = await scraper.batch_scrape_urls(["https://a.com"])

    assert result["success"] is False
    assert result["data"] == []


# ---------------------------------------------------------------------------
# search_web() tests
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_search_web_success():
    """search_web returns results on success."""
    fc = MagicMock()
    item1 = MagicMock()
    item1.url = "https://news.com/article1"
    mock_result = MagicMock()
    mock_result.web = [item1]
    fc.search.return_value = mock_result

    scraper = _make_scraper(fc)
    result = await scraper.search_web("AKBNK KAP bildirimi")

    assert result["success"] is True
    assert result["total"] == 1
    assert len(result["results"]) == 1


@pytest.mark.asyncio
async def test_search_web_passes_language_country():
    """search_web passes lang and country to firecrawl.search."""
    fc = MagicMock()
    mock_result = MagicMock()
    mock_result.web = []
    fc.search.return_value = mock_result

    scraper = _make_scraper(fc)
    await scraper.search_web("test", lang="tr", country="TR", tbs="qdr:w")

    call_kwargs = fc.search.call_args
    assert call_kwargs[1].get("location") == "TR"
    assert call_kwargs[1].get("tbs") == "qdr:w"


@pytest.mark.asyncio
async def test_search_web_failure():
    """search_web returns empty results on exception."""
    fc = MagicMock()
    fc.search.side_effect = Exception("quota exceeded")

    scraper = _make_scraper(fc)
    result = await scraper.search_web("THYAO")

    assert result["success"] is False
    assert result["results"] == []


# ---------------------------------------------------------------------------
# scrape_with_actions() tests
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_scrape_with_actions_success():
    """scrape_with_actions returns content on success."""
    fc = MagicMock()
    page = MagicMock()
    page.markdown = "# KAP Content"
    page.html = "<h1>KAP Content</h1>"
    page.metadata = {"title": "KAP"}
    fc.scrape.return_value = page

    scraper = _make_scraper(fc)
    actions = [
        {"type": "wait", "milliseconds": 2000},
        {"type": "scroll", "direction": "down"},
        {"type": "scrape"},
    ]
    result = await scraper.scrape_with_actions("https://kap.org.tr", actions)

    assert result["success"] is True
    assert "markdown" in result["data"]
    # Verify proxy and location were passed
    call_params = fc.scrape.call_args[1]
    assert call_params.get("proxy") == "stealth"
    assert "actions" in call_params


@pytest.mark.asyncio
async def test_scrape_with_actions_with_location():
    """scrape_with_actions passes location to firecrawl."""
    fc = MagicMock()
    page = MagicMock()
    page.markdown = "content"
    page.html = "<p>content</p>"
    page.metadata = {}
    fc.scrape.return_value = page

    scraper = _make_scraper(fc)
    await scraper.scrape_with_actions(
        "https://example.com",
        actions=[{"type": "scrape"}],
        location={"country": "TR", "languages": ["tr-TR"]},
    )

    call_params = fc.scrape.call_args[1]
    assert call_params.get("location") == {"country": "TR", "languages": ["tr-TR"]}


@pytest.mark.asyncio
async def test_scrape_with_actions_failure():
    """scrape_with_actions returns success=False on exception."""
    fc = MagicMock()
    fc.scrape.side_effect = Exception("blocked")

    scraper = _make_scraper(fc)
    result = await scraper.scrape_with_actions(
        "https://example.com", [{"type": "scrape"}]
    )
    assert result["success"] is False
    assert "blocked" in result["error"]


# ---------------------------------------------------------------------------
# scrape_url() upgrade tests (proxy, location, only_main_content)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_scrape_url_passes_proxy():
    """Upgraded scrape_url sends proxy param to Firecrawl."""
    fc = MagicMock()
    page = MagicMock()
    page.markdown = "content"
    page.html = "<p>content</p>"
    page.metadata = {}
    fc.scrape.return_value = page

    scraper = _make_scraper(fc)
    await scraper.scrape_url("https://example.com", proxy="stealth")

    call_params = fc.scrape.call_args[1]
    assert call_params.get("proxy") == "stealth"


@pytest.mark.asyncio
async def test_scrape_url_passes_location():
    """Upgraded scrape_url sends location param when provided."""
    fc = MagicMock()
    page = MagicMock()
    page.markdown = "content"
    page.html = ""
    page.metadata = {}
    fc.scrape.return_value = page

    scraper = _make_scraper(fc)
    await scraper.scrape_url(
        "https://example.com",
        location={"country": "TR"},
    )

    call_params = fc.scrape.call_args[1]
    assert call_params.get("location") == {"country": "TR"}


@pytest.mark.asyncio
async def test_scrape_url_only_main_content_default_true():
    """scrape_url defaults onlyMainContent to True."""
    fc = MagicMock()
    page = MagicMock()
    page.markdown = "content"
    page.html = ""
    page.metadata = {}
    fc.scrape.return_value = page

    scraper = _make_scraper(fc)
    await scraper.scrape_url("https://example.com")

    call_params = fc.scrape.call_args[1]
    assert call_params.get("only_main_content") is True


@pytest.mark.asyncio
async def test_scrape_url_passes_cache_age_controls():
    """Cache freshness controls use the v2 SDK's snake_case keyword names."""
    fc = MagicMock()
    page = MagicMock()
    page.markdown = "content"
    page.metadata = {}
    fc.scrape.return_value = page

    scraper = _make_scraper(fc)
    await scraper.scrape_url(
        "https://example.com/static-company-list",
        max_age=86_400_000,
        min_age=3_600_000,
        store_in_cache=True,
    )

    call_params = fc.scrape.call_args[1]
    assert call_params["max_age"] == 86_400_000
    assert call_params["min_age"] == 3_600_000
    assert call_params["store_in_cache"] is True


def test_v2_cache_kwargs_accept_camel_and_snake_case():
    scraper = _make_scraper(MagicMock())

    assert scraper._build_v2_scrape_kwargs(
        {"maxAge": 10, "minAge": 5, "storeInCache": False}
    ) == {"max_age": 10, "min_age": 5, "store_in_cache": False}
    assert scraper._build_v2_scrape_kwargs(
        {"max_age": 10, "min_age": 5, "store_in_cache": False}
    ) == {"max_age": 10, "min_age": 5, "store_in_cache": False}


def test_bypass_proxy_payload_serializes_cache_fields_as_v2_camel_case():
    scraper = _make_scraper(MagicMock())

    payload = scraper._build_raw_scrape_payload(
        "https://www.kap.org.tr/tr/Bildirimler",
        {
            "bypass_proxy": True,
            "max_age": 60_000,
            "min_age": 5_000,
            "store_in_cache": False,
            "only_main_content": False,
        },
    )

    assert payload == {
        "url": "https://www.kap.org.tr/tr/Bildirimler",
        "maxAge": 60_000,
        "minAge": 5_000,
        "storeInCache": False,
        "onlyMainContent": False,
        "bypassProxy": True,
    }


def test_normalize_document_preserves_pdf_page_metadata_from_sdk_model():
    class Metadata:
        def model_dump(self, exclude_none=True):
            return {"num_pages": 8, "total_pages": 10, "title": "KAP filing"}

    page = MagicMock()
    page.markdown = "filing"
    page.metadata = Metadata()
    page.raw_html = None
    page.actions = None

    scraper = _make_scraper(MagicMock())
    data = scraper._normalize_document(page)

    assert data["metadata"]["numPages"] == 8
    assert data["metadata"]["totalPages"] == 10
    assert data["metadata"]["title"] == "KAP filing"


@pytest.mark.parametrize(
    ("metadata", "expected_total", "status", "complete", "reason"),
    [
        (
            {"numPages": 10, "totalPages": 10},
            None,
            "complete",
            True,
            "parsed_page_count_matches_total",
        ),
        (
            {"num_pages": 7, "total_pages": 10},
            None,
            "partial",
            False,
            "parsed_fewer_pages_than_expected",
        ),
        (
            {},
            None,
            "unknown",
            None,
            "page_metadata_unavailable",
        ),
        (
            {"numPages": 11, "totalPages": 10},
            None,
            "unknown",
            None,
            "parsed_page_count_exceeds_expected",
        ),
        (
            {"numPages": 12},
            12,
            "complete",
            True,
            "parsed_page_count_matches_total",
        ),
    ],
)
def test_assess_pdf_completeness(
    metadata, expected_total, status, complete, reason
):
    scraper = _make_scraper(MagicMock())

    assessment = scraper.assess_pdf_completeness(
        {"metadata": metadata},
        expected_total_pages=expected_total,
    )

    assert assessment["status"] == status
    assert assessment["complete"] is complete
    assert assessment["reason"] == reason


# ---------------------------------------------------------------------------
# KAPScraper new methods (mocked)
# ---------------------------------------------------------------------------

def _make_kap_scraper(mock_firecrawl=None):
    with patch("scrapers.base_scraper.FirecrawlApp") as MockFC:
        if mock_firecrawl is not None:
            MockFC.return_value = mock_firecrawl
        from scrapers.kap_scraper import KAPScraper
        scraper = KAPScraper()
        if mock_firecrawl is not None:
            scraper.firecrawl = mock_firecrawl
        return scraper


@pytest.mark.asyncio
async def test_map_kap_disclosures_filters_urls():
    """map_kap_disclosures filters to disclosure links."""
    fc = MagicMock()
    mock_result = MagicMock()
    mock_result.links = [
        "https://www.kap.org.tr/tr/BildirimPdf/1234567",
        "https://www.kap.org.tr/tr/Bildirim/123",
        "https://www.kap.org.tr/about",
        "https://www.kap.org.tr/privacy",
    ]
    fc.map.return_value = mock_result

    scraper = _make_kap_scraper(fc)
    result = await scraper.map_kap_disclosures()

    assert result["success"] is True
    assert result["disclosure_count"] == 2
    assert all("/BildirimPdf/" in lnk or "/Bildirim" in lnk
               for lnk in result["disclosure_links"])


@pytest.mark.asyncio
async def test_search_kap_news_uses_tr_params():
    """search_kap_news passes Turkish language and country params."""
    fc = MagicMock()
    mock_result = MagicMock()
    mock_result.web = []
    fc.search.return_value = mock_result

    scraper = _make_kap_scraper(fc)
    result = await scraper.search_kap_news("AKBNK", days_back=7)

    assert result["success"] is True
    call_params = fc.search.call_args[1]
    assert call_params.get("location") == "TR"
    assert call_params.get("tbs") == "qdr:w"  # 7 days maps to weekly


@pytest.mark.asyncio
async def test_scrape_kap_page_with_actions_uses_stealth():
    """scrape_kap_page_with_actions uses stealth proxy and TR location."""
    fc = MagicMock()
    page = MagicMock()
    page.markdown = "KAP content"
    page.html = "<html>KAP</html>"
    page.metadata = {}
    fc.scrape.return_value = page

    scraper = _make_kap_scraper(fc)
    result = await scraper.scrape_kap_page_with_actions(
        "https://www.kap.org.tr/tr/Bildirimdispl"
    )

    assert result["success"] is True
    call_params = fc.scrape.call_args[1]
    assert call_params.get("proxy") == "stealth"
    assert call_params.get("location", {}).get("country") == "TR"


@pytest.mark.asyncio
async def test_batch_scrape_company_pages_maps_codes():
    """batch_scrape_company_pages keys results by company code."""
    fc = MagicMock()
    p1 = MagicMock()
    p1.markdown = "AKBNK content"
    p2 = MagicMock()
    p2.markdown = "THYAO content"

    result_obj = MagicMock()
    result_obj.data = [p1, p2]
    fc.batch_scrape.return_value = result_obj

    scraper = _make_kap_scraper(fc)
    result = await scraper.batch_scrape_company_pages(["AKBNK", "THYAO"])

    assert result["total"] == 2
    assert "AKBNK" in result["results"]
    assert "THYAO" in result["results"]
