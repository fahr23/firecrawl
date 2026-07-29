"""
Unit tests for NewsPortalScraper.

Pure-unit: no network, no DB, no real Firecrawl. We build the scraper via __new__
(so BaseScraper.__init__ — which constructs a FirecrawlApp — is skipped) and stub the
async fetch helpers. feedparser is injected as a sys.modules stub so the RSS path can be
exercised without the real package installed.
"""
import asyncio
import sys
import types
from datetime import datetime, timedelta
from unittest.mock import AsyncMock

import pytest

from scrapers.news_portal_scraper import NewsPortalScraper
from domain.entities.news_article import SOURCE_BLOOMBERG_HT, SOURCE_BIGPARA, SOURCE_INVESTING_TR, SOURCE_EKONOMIM


def run(coro):
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


def _make_scraper() -> NewsPortalScraper:
    scraper = NewsPortalScraper.__new__(NewsPortalScraper)
    scraper.db_manager = None
    scraper.firecrawl = None
    return scraper


def test_economim_uses_the_standard_firecrawl_html_adapter():
    config = NewsPortalScraper.SOURCES[SOURCE_EKONOMIM]
    assert config["method"] == "html"
    assert config["listing_url"] == "https://www.ekonomim.com/ekonomi"


# ── ticker tagging ────────────────────────────────────────────────────────────
class TestDetectTicker:
    def test_explicit_ticker_token(self):
        s = _make_scraper()
        assert s._detect_ticker("THYAO bugün yükseldi") == "THYAO"

    def test_company_name_match(self):
        s = _make_scraper()
        assert s._detect_ticker("Türk Hava Yolları rekor kar açıkladı") == "THYAO"

    def test_macro_headline_has_no_ticker(self):
        s = _make_scraper()
        assert s._detect_ticker("Merkez Bankası faiz kararını açıkladı") is None

    def test_empty_text(self):
        s = _make_scraper()
        assert s._detect_ticker("") is None


# ── date helpers ────────────────────────────────────────────────────────────────
class TestDateHelpers:
    def test_parse_iso_date(self):
        s = _make_scraper()
        dt = s._parse_date("2026-06-10T09:30:00")
        assert dt.year == 2026 and dt.month == 6 and dt.day == 10

    def test_parse_rss_date(self):
        s = _make_scraper()
        dt = s._parse_date("Wed, 10 Jun 2026 09:30:00 +0300")
        assert dt is not None and dt.year == 2026

    def test_parse_garbage_returns_none(self):
        s = _make_scraper()
        assert s._parse_date("not a date") is None

    def test_window_keeps_undated(self):
        s = _make_scraper()
        assert s._within_window(None, 7) is True

    def test_window_drops_old(self):
        s = _make_scraper()
        old = datetime.utcnow() - timedelta(days=30)
        assert s._within_window(old, 7) is False

    def test_window_keeps_recent(self):
        s = _make_scraper()
        recent = datetime.utcnow() - timedelta(days=1)
        assert s._within_window(recent, 7) is True


# ── RSS path ────────────────────────────────────────────────────────────────────
def _install_feedparser_stub(entries):
    mod = types.ModuleType("feedparser")
    parsed = types.SimpleNamespace(entries=entries)
    mod.parse = lambda url: parsed
    sys.modules["feedparser"] = mod


class TestFetchRss:
    def test_maps_entries_to_articles(self):
        _install_feedparser_stub([
            {
                "title": "Türk Hava Yolları rekor yolcu sayısına ulaştı",
                "summary": "<p>THY trafiği arttı</p>",
                "link": "https://www.bloomberght.com/x",
                "published": "2026-06-10T09:30:00",
            },
            {
                "title": "Merkez Bankası faiz kararı",
                "summary": "Politika faizi sabit",
                "link": "https://www.bloomberght.com/y",
                "published": "2026-06-11T09:30:00",
            },
        ])
        s = _make_scraper()
        articles = run(s.fetch_rss("http://feed", SOURCE_BLOOMBERG_HT, None, days_back=3650))
        assert len(articles) == 2
        thy = next(a for a in articles if "Hava" in a.headline)
        assert thy.ticker == "THYAO"
        assert thy.source == SOURCE_BLOOMBERG_HT
        # HTML stripped from summary
        assert "<p>" not in thy.body

    def test_skips_entries_without_title(self):
        _install_feedparser_stub([{"summary": "no title", "link": "x"}])
        s = _make_scraper()
        articles = run(s.fetch_rss("http://feed", SOURCE_BLOOMBERG_HT, None))
        assert articles == []

    def test_ticker_filter_drops_unrelated(self):
        _install_feedparser_stub([
            {"title": "THYAO haberi", "summary": "", "link": "a", "published": "2026-06-10"},
            {"title": "AKBNK haberi", "summary": "", "link": "b", "published": "2026-06-10"},
        ])
        s = _make_scraper()
        articles = run(s.fetch_rss("http://feed", SOURCE_BLOOMBERG_HT, ["THYAO"], days_back=3650))
        assert len(articles) == 1
        assert articles[0].ticker == "THYAO"


# ── HTML path (Firecrawl extract_with_schema) ────────────────────────────────────
class TestFetchHtml:
    def test_extracts_articles_from_schema(self):
        s = _make_scraper()
        s.extract_with_schema = AsyncMock(return_value={
            "success": True,
            "data": {"articles": [
                {"headline": "Aselsan yeni sözleşme imzaladı",
                 "body": "ASELS savunma ihalesi", "url": "/haber/1",
                 "published_at": "2026-06-12"},
            ]},
        })
        articles = run(s.fetch_html("https://www.foreks.com/haberler", "foreks", None, days_back=3650))
        assert len(articles) == 1
        assert articles[0].ticker == "ASELS"
        # relative URL resolved against origin
        assert articles[0].url == "https://www.foreks.com/haber/1"

    def test_falls_back_to_scrape_when_extract_empty(self):
        s = _make_scraper()
        s.extract_with_schema = AsyncMock(return_value={"success": True, "data": {"articles": []}})
        s.scrape_url = AsyncMock(return_value={
            "success": True,
            "data": {"html": '<a href="/h/9">Sabancı Holding çeyrek bilançosunu açıkladı bugün</a>'},
        })
        articles = run(s.fetch_html("https://bigpara.hurriyet.com.tr/x", SOURCE_BIGPARA, None, days_back=3650))
        assert len(articles) == 1
        assert articles[0].ticker == "SAHOL"


# ── Investing.com TR dynamic comments ────────────────────────────────────────────
class TestInvestingComments:
    def test_parses_comments_from_rendered_html(self):
        s = _make_scraper()
        html = (
            '<div class="commentBody">THYAO çok güçlü görünüyor, alım fırsatı</div>'
            '<div class="comment-text">Kar satışı gelebilir dikkat</div>'
        )
        s.scrape_with_actions = AsyncMock(return_value={"success": True, "data": {"html": html}})
        articles = run(s.fetch_investing_comments("THYAO"))
        assert len(articles) == 2
        assert all(a.source == SOURCE_INVESTING_TR for a in articles)
        assert all(a.ticker == "THYAO" for a in articles)

    def test_unknown_ticker_returns_empty(self):
        s = _make_scraper()
        articles = run(s.fetch_investing_comments("ZZZZ"))
        assert articles == []

    def test_failed_scrape_returns_empty(self):
        s = _make_scraper()
        s.scrape_with_actions = AsyncMock(return_value={"success": False})
        articles = run(s.fetch_investing_comments("THYAO"))
        assert articles == []


# ── orchestration ─────────────────────────────────────────────────────────────
class TestScrapeAll:
    def test_includes_verified_additional_turkish_economy_rss_sources(self):
        s = _make_scraper()
        assert s.SOURCES["aa_ekonomi"]["feed_url"] == "https://www.aa.com.tr/tr/teyithatti/rss/news?cat=ekonomi"
        assert s.SOURCES["trt_ekonomi"]["feed_url"] == "https://www.trthaber.com/ekonomi_articles.rss"

    def test_aggregates_across_sources(self):
        s = _make_scraper()
        from domain.entities.news_article import NewsArticle

        async def fake_rss(feed_url, source, tickers, days_back):
            return [NewsArticle(source=source, headline="THYAO haber", url="a", ticker="THYAO")]

        async def fake_html(listing_url, source, tickers, days_back):
            return [NewsArticle(source=source, headline="AKBNK haber", url="b", ticker="AKBNK")]

        async def fake_inv(ticker, max_comments=30):
            return []

        s.fetch_rss = fake_rss
        s.fetch_html = fake_html
        s.fetch_investing_comments = fake_inv

        result = run(s.scrape_all(include_investing_comments=True))
        assert result["success"] is True
        assert result["total"] >= 2
        assert "by_source" in result

    def test_source_failure_isolated(self):
        s = _make_scraper()

        async def boom(*a, **k):
            raise RuntimeError("source down")

        async def fake_inv(ticker, max_comments=30):
            return []

        s.fetch_rss = boom
        s.fetch_html = boom
        s.fetch_investing_comments = fake_inv

        result = run(s.scrape_all(include_investing_comments=False))
        # No exception bubbles up; run still succeeds with zero articles
        assert result["success"] is True
        assert result["total"] == 0
