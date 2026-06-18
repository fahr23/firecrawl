"""
Unit tests for SocialMediaScraper.

Pure-unit: no network, no DB, no real Firecrawl. The scraper is built via __new__ and
the async render helper (scrape_with_actions) is stubbed.
"""
import asyncio
from unittest.mock import AsyncMock

import pytest

from scrapers.social_media_scraper import SocialMediaScraper
from domain.entities.social_post import PLATFORM_TWITTER


def run(coro):
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


def _make_scraper() -> SocialMediaScraper:
    s = SocialMediaScraper.__new__(SocialMediaScraper)
    s.db_manager = None
    s.firecrawl = None
    return s


_TWEET_HTML = """
<div>
  <article>
    <a href="/borsaci"></a>
    <div data-testid="tweetText">THYAO bilanço sonrası çok güçlü, hedef yükseltildi</div>
    <a href="/borsaci/status/123">link</a>
  </article>
  <article>
    <a href="/yatirimci"></a>
    <div data-testid="tweetText">THYAO kar satışı gelebilir, dikkatli olun</div>
    <a href="/yatirimci/status/456">link</a>
  </article>
</div>
"""


class TestParseTweets:
    def test_extracts_posts_from_articles(self):
        s = _make_scraper()
        posts = s._parse_tweets(_TWEET_HTML, "THYAO", limit=30)
        assert len(posts) == 2
        assert all(p.platform == PLATFORM_TWITTER for p in posts)
        assert all(p.ticker == "THYAO" for p in posts)
        assert posts[0].url == "https://x.com/borsaci/status/123"
        assert posts[0].author == "borsaci"

    def test_dedupes_identical_text(self):
        s = _make_scraper()
        html = (
            '<article><div data-testid="tweetText">aynı tweet metni burada</div></article>'
            '<article><div data-testid="tweetText">aynı tweet metni burada</div></article>'
        )
        posts = s._parse_tweets(html, "AKBNK", limit=30)
        assert len(posts) == 1

    def test_empty_html(self):
        s = _make_scraper()
        assert s._parse_tweets("", "THYAO", 30) == []

    def test_respects_limit(self):
        s = _make_scraper()
        posts = s._parse_tweets(_TWEET_HTML, "THYAO", limit=1)
        assert len(posts) == 1


class TestFetchTweets:
    def test_renders_and_parses(self):
        s = _make_scraper()
        s.scrape_with_actions = AsyncMock(return_value={
            "success": True, "data": {"html": _TWEET_HTML}
        })
        # ntscraper fallback should NOT be needed
        s._fetch_via_ntscraper = lambda ticker, limit: pytest.fail("fallback used")
        posts = run(s.fetch_tweets("THYAO", days_back=3650, limit=30))
        assert len(posts) == 2

    def test_falls_back_to_ntscraper_when_empty(self):
        s = _make_scraper()
        s.scrape_with_actions = AsyncMock(return_value={"success": True, "data": {"html": ""}})
        called = {"n": 0}

        def fake_fallback(ticker, limit):
            called["n"] += 1
            return []

        s._fetch_via_ntscraper = fake_fallback
        run(s.fetch_tweets("THYAO", days_back=7, limit=30))
        assert called["n"] == 1

    def test_failed_render_then_empty_fallback(self):
        s = _make_scraper()
        s.scrape_with_actions = AsyncMock(return_value={"success": False})
        s._fetch_via_ntscraper = lambda ticker, limit: []
        posts = run(s.fetch_tweets("THYAO"))
        assert posts == []


class TestScrapeAll:
    def test_aggregates_per_ticker(self):
        s = _make_scraper()

        async def fake_fetch(ticker, days_back, limit):
            from domain.entities.social_post import SocialPost
            return [SocialPost(platform=PLATFORM_TWITTER, ticker=ticker, text=f"{ticker} tweet")]

        s.fetch_tweets = fake_fetch
        result = run(s.scrape_all(["THYAO", "AKBNK"]))
        assert result["success"] is True
        assert result["total"] == 2
        assert result["by_ticker"] == {"THYAO": 1, "AKBNK": 1}

    def test_ticker_failure_isolated(self):
        s = _make_scraper()

        async def boom(ticker, days_back, limit):
            raise RuntimeError("X down")

        s.fetch_tweets = boom
        result = run(s.scrape_all(["THYAO"]))
        assert result["success"] is True
        assert result["total"] == 0
