"""
News portal scraper — Turkish financial news/portals for institutional sentiment.

Collects headlines/articles from Bloomberg HT, Foreks, Mynet Finans, Bigpara and
Investing.com TR and tags each with a BIST ticker when the text references a known
company. Fetching is **Firecrawl-first** (self-hosted, open-source): RSS indices are
read with `feedparser` only where the portal truly publishes a feed; everything else
goes through Firecrawl (`scrape_url`, `extract_with_schema`, `scrape_with_actions`).

Investing.com TR comment sections load via JavaScript, so they are rendered with
`scrape_with_actions` (Playwright: wait → scroll → scrape), mirroring the KAP SPA
pattern in `kap_scraper.py`.

The scraper is intentionally I/O-only: it returns `NewsArticle` objects. Sentiment
analysis and persistence are orchestrated by CollectNewsSentimentUseCase.
"""
from __future__ import annotations

import logging
import re
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

from bs4 import BeautifulSoup

from scrapers.base_scraper import BaseScraper
from domain.entities.news_article import (
    NewsArticle,
    SOURCE_BLOOMBERG_HT,
    SOURCE_FOREKS,
    SOURCE_MYNET_FINANS,
    SOURCE_BIGPARA,
    SOURCE_HABERTURK,
    SOURCE_NTV,
    SOURCE_INVESTING_TR,
)
from infrastructure.contracts.instrument_identity_map import STATIC_BIST_MAP

logger = logging.getLogger(__name__)


# Structured-extraction schema for portal article listings. Modelled on
# KAP_REPORT_SCHEMA so Firecrawl bills the cached/deterministic rate (~3 credits).
NEWS_ARTICLE_SCHEMA: Dict[str, Any] = {
    "type": "object",
    "properties": {
        "articles": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "headline": {"type": "string"},
                    "body": {"type": "string"},
                    "url": {"type": "string"},
                    "published_at": {"type": "string"},
                },
                "required": ["headline"],
            },
        }
    },
}
NEWS_ARTICLE_PROMPT = (
    "Extract the financial news article list. For each article return its headline, "
    "a short summary/body, the article URL, and the publish date if shown."
)


class NewsPortalScraper(BaseScraper):
    """Scrape Turkish financial news portals into NewsArticle objects."""

    # Per-source configuration. `method` selects the fetch path:
    #   rss  → feedparser index (+ scrape_url body enrichment when truncated)
    #   html → Firecrawl scrape_url / extract_with_schema over a listing page
    SOURCES: Dict[str, Dict[str, Any]] = {
        SOURCE_BLOOMBERG_HT: {
            "method": "rss",
            "feed_url": "https://www.bloomberght.com/rss",
        },
        SOURCE_MYNET_FINANS: {
            "method": "rss",
            "feed_url": "https://finans.mynet.com/rss/sondakika/",
        },
        SOURCE_BIGPARA: {
            "method": "html",
            "listing_url": "https://bigpara.hurriyet.com.tr/haberler/borsa-haberleri/",
        },
        SOURCE_FOREKS: {
            "method": "html",
            "listing_url": "https://www.foreks.com/haberler",
        },
        SOURCE_HABERTURK: {
            "method": "rss",
            "feed_url": "https://www.haberturk.com/rss/ekonomi.xml",
        },
        SOURCE_NTV: {
            "method": "rss",
            "feed_url": "https://www.ntv.com.tr/ekonomi.rss",
        },
    }

    # Investing.com TR per-stock comment pages (dynamic JS). Keyed by ticker so we
    # only render the pages for instruments we actually care about.
    INVESTING_EQUITY_URLS: Dict[str, str] = {
        "THYAO": "https://tr.investing.com/equities/turk-hava-yollari-commentary",
        "GARAN": "https://tr.investing.com/equities/garanti-bankasi-commentary",
        "AKBNK": "https://tr.investing.com/equities/akbank-commentary",
        "SISE": "https://tr.investing.com/equities/sise-cam-commentary",
        "EREGL": "https://tr.investing.com/equities/eregli-demir-celik-commentary",
        "ASELS": "https://tr.investing.com/equities/aselsan-commentary",
        "SASA": "https://tr.investing.com/equities/sasa-polyester-commentary",
    }

    LOCATION_TR = {"country": "TR", "languages": ["tr-TR", "tr"]}

    # ── ticker tagging ────────────────────────────────────────────────────────
    def _detect_ticker(self, text: str) -> Optional[str]:
        """
        Tag a BIST ticker from article text.

        Matches an explicit ticker token (e.g. "THYAO") first, then falls back to the
        company-name substrings in STATIC_BIST_MAP (e.g. "türk hava yolları" → THYAO).
        Returns the first match or None for macro/sector headlines.
        """
        if not text:
            return None
        upper = text.upper()
        for ticker in STATIC_BIST_MAP:
            # word-boundary match so "SISE" doesn't fire inside "SISECAM" text noise
            if re.search(rf"\b{re.escape(ticker)}\b", upper):
                return ticker

        lowered = text.lower()
        for ticker, patterns in STATIC_BIST_MAP.items():
            for pat in patterns:
                if pat in lowered:
                    return ticker
        return None

    @staticmethod
    def _parse_date(value: Any) -> Optional[datetime]:
        """Best-effort parse of a feed/extracted date into a naive datetime."""
        if not value:
            return None
        if isinstance(value, datetime):
            return value
        text = str(value).strip()
        # feedparser struct_time tuple support
        for fmt in (
            "%a, %d %b %Y %H:%M:%S %z",
            "%a, %d %b %Y %H:%M:%S %Z",
            "%Y-%m-%dT%H:%M:%S%z",
            "%Y-%m-%dT%H:%M:%S",
            "%Y-%m-%d %H:%M:%S",
            "%Y-%m-%d",
        ):
            try:
                dt = datetime.strptime(text, fmt)
                return dt.replace(tzinfo=None)
            except ValueError:
                continue
        try:
            return datetime.fromisoformat(text.replace("Z", "+00:00")).replace(tzinfo=None)
        except ValueError:
            return None

    def _within_window(self, published: Optional[datetime], days_back: int) -> bool:
        """Keep undated items (can't prove they're old) and items inside the window."""
        if published is None:
            return True
        return published >= datetime.utcnow() - timedelta(days=days_back)

    # ── RSS source (feedparser index, Firecrawl body enrichment) ──────────────
    async def fetch_rss(
        self,
        feed_url: str,
        source: str,
        tickers: Optional[List[str]] = None,
        days_back: int = 7,
    ) -> List[NewsArticle]:
        """Read an RSS feed with feedparser and map entries to NewsArticle objects."""
        import feedparser  # local import: optional dep, keeps module import light

        articles: List[NewsArticle] = []
        try:
            parsed = feedparser.parse(feed_url)
        except Exception as e:
            logger.error(f"feedparser failed for {feed_url}: {e}")
            return articles

        for entry in getattr(parsed, "entries", []) or []:
            headline = (entry.get("title") or "").strip()
            if not headline:
                continue
            body = (entry.get("summary") or entry.get("description") or "").strip()
            body = BeautifulSoup(body, "html.parser").get_text(" ", strip=True) if body else ""
            published = self._parse_date(
                entry.get("published") or entry.get("updated")
            )
            if not self._within_window(published, days_back):
                continue

            ticker = self._detect_ticker(f"{headline} {body}")
            if tickers and ticker not in tickers:
                # When the caller restricts to specific tickers, drop unrelated items
                # but keep genuinely macro (untagged) headlines out too.
                continue

            try:
                articles.append(
                    NewsArticle(
                        source=source,
                        headline=headline,
                        url=(entry.get("link") or "").strip(),
                        body=body,
                        ticker=ticker,
                        published_at=published,
                    )
                )
            except ValueError:
                continue

        logger.info(f"RSS {source}: {len(articles)} articles from {feed_url}")
        return articles

    # ── HTML source (Firecrawl extract_with_schema, scrape_url fallback) ──────
    async def fetch_html(
        self,
        listing_url: str,
        source: str,
        tickers: Optional[List[str]] = None,
        days_back: int = 7,
    ) -> List[NewsArticle]:
        """Extract a portal listing via Firecrawl structured extraction."""
        articles: List[NewsArticle] = []
        result = await self.extract_with_schema(
            listing_url, schema=NEWS_ARTICLE_SCHEMA, prompt=NEWS_ARTICLE_PROMPT
        )
        items: List[Dict[str, Any]] = []
        if result.get("success"):
            data = result.get("data") or {}
            if isinstance(data, dict):
                items = data.get("articles") or []

        # Fallback: plain scrape + heading parse when extraction yields nothing.
        if not items:
            items = await self._scrape_listing_fallback(listing_url)

        for item in items:
            headline = (item.get("headline") or "").strip()
            if not headline:
                continue
            body = (item.get("body") or "").strip()
            published = self._parse_date(item.get("published_at"))
            if not self._within_window(published, days_back):
                continue

            ticker = self._detect_ticker(f"{headline} {body}")
            if tickers and ticker not in tickers:
                continue

            url = (item.get("url") or "").strip()
            if url and url.startswith("/"):
                # resolve relative links against the listing origin
                m = re.match(r"^(https?://[^/]+)", listing_url)
                if m:
                    url = m.group(1) + url
            try:
                articles.append(
                    NewsArticle(
                        source=source,
                        headline=headline,
                        url=url,
                        body=body,
                        ticker=ticker,
                        published_at=published,
                    )
                )
            except ValueError:
                continue

        logger.info(f"HTML {source}: {len(articles)} articles from {listing_url}")
        return articles

    async def _scrape_listing_fallback(self, listing_url: str) -> List[Dict[str, Any]]:
        """Plain Firecrawl scrape + BS4 anchor harvest when extraction returns nothing."""
        result = await self.scrape_url(
            listing_url,
            formats=["html", "markdown"],
            proxy="auto",
            location=self.LOCATION_TR,
        )
        if not result.get("success"):
            return []
        html = (result.get("data") or {}).get("html") or ""
        if not html:
            return []

        soup = BeautifulSoup(html, "html.parser")
        seen: set = set()
        items: List[Dict[str, Any]] = []
        for a in soup.find_all("a"):
            text = a.get_text(strip=True)
            href = a.get("href") or ""
            if len(text) < 25 or not href:  # skip nav/chrome links
                continue
            if text in seen:
                continue
            seen.add(text)
            items.append({"headline": text, "url": href, "body": ""})
        return items

    # ── Investing.com TR dynamic comments (Playwright via scrape_with_actions) ─
    async def fetch_investing_comments(
        self,
        ticker: str,
        max_comments: int = 30,
    ) -> List[NewsArticle]:
        """Render an Investing.com TR stock page and harvest its JS-loaded comments."""
        url = self.INVESTING_EQUITY_URLS.get(ticker.strip().upper())
        if not url:
            logger.info(f"No Investing.com TR comment URL configured for {ticker}")
            return []

        actions = [
            {"type": "wait", "milliseconds": 3000},
            {"type": "scroll", "direction": "down"},
            {"type": "wait", "milliseconds": 1500},
            {"type": "scroll", "direction": "down"},
            {"type": "wait", "milliseconds": 1500},
            {"type": "scrape"},
        ]
        result = await self.scrape_with_actions(
            url=url,
            actions=actions,
            formats=["html", "markdown"],
            proxy="stealth",
            location=self.LOCATION_TR,
        )
        if not result.get("success"):
            return []

        html = (result.get("data") or {}).get("html") or ""
        comments = self._parse_investing_comments(html, max_comments)

        articles: List[NewsArticle] = []
        for idx, text in enumerate(comments):
            try:
                articles.append(
                    NewsArticle(
                        source=SOURCE_INVESTING_TR,
                        headline=text[:200],
                        url=f"{url}#comment-{idx}",
                        body=text,
                        ticker=ticker.strip().upper(),
                        published_at=None,
                    )
                )
            except ValueError:
                continue

        logger.info(f"Investing.com TR {ticker}: {len(articles)} comments")
        return articles

    @staticmethod
    def _parse_investing_comments(html: str, max_comments: int) -> List[str]:
        """Extract comment text from a rendered Investing.com TR page."""
        if not html:
            return []
        soup = BeautifulSoup(html, "html.parser")
        texts: List[str] = []
        # Investing renders comments in containers whose class mentions "comment".
        for node in soup.find_all(class_=re.compile("comment", re.I)):
            text = node.get_text(" ", strip=True)
            if text and len(text) >= 10 and text not in texts:
                texts.append(text)
            if len(texts) >= max_comments:
                break
        return texts

    # ── orchestration ─────────────────────────────────────────────────────────
    async def scrape_all(
        self,
        tickers: Optional[List[str]] = None,
        days_back: int = 7,
        sources: Optional[List[str]] = None,
        include_investing_comments: bool = True,
    ) -> Dict[str, Any]:
        """
        Collect articles from all (or selected) sources.

        Args:
            tickers: restrict to these BIST tickers (also drives which Investing.com TR
                     pages are rendered). None → keep everything, tag where possible.
            days_back: drop dated items older than this window.
            sources: subset of SOURCES keys; None → all portal sources.
            include_investing_comments: also render Investing.com TR comment pages.

        Returns:
            {"success", "total", "by_source", "articles": List[NewsArticle]}
        """
        norm_tickers = [t.strip().upper() for t in tickers] if tickers else None
        selected = sources or list(self.SOURCES.keys())
        all_articles: List[NewsArticle] = []
        by_source: Dict[str, int] = {}

        for source in selected:
            cfg = self.SOURCES.get(source)
            if not cfg:
                continue
            try:
                if cfg["method"] == "rss":
                    found = await self.fetch_rss(
                        cfg["feed_url"], source, norm_tickers, days_back
                    )
                else:
                    found = await self.fetch_html(
                        cfg["listing_url"], source, norm_tickers, days_back
                    )
            except Exception as e:
                logger.error(f"Source {source} failed: {e}", exc_info=True)
                found = []
            by_source[source] = len(found)
            all_articles.extend(found)

        if include_investing_comments:
            inv_tickers = norm_tickers or list(self.INVESTING_EQUITY_URLS.keys())
            inv_count = 0
            for ticker in inv_tickers:
                try:
                    found = await self.fetch_investing_comments(ticker)
                except Exception as e:
                    logger.error(f"Investing comments {ticker} failed: {e}")
                    found = []
                inv_count += len(found)
                all_articles.extend(found)
            by_source[SOURCE_INVESTING_TR] = inv_count

        return {
            "success": True,
            "total": len(all_articles),
            "by_source": by_source,
            "articles": all_articles,
        }

    # BaseScraper abstract method.
    async def scrape(self, **kwargs) -> Dict[str, Any]:
        """Alias for scrape_all() to satisfy the BaseScraper contract."""
        return await self.scrape_all(**kwargs)
