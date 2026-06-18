"""
Social media scraper — X (Twitter) FinTwit for retail sentiment.

Searches X for the Turkish FinTwit cashtag/hashtag forms of a ticker (``#THYAO``,
``$SASA``, ``#EREGL``) and returns `SocialPost` objects. Because the official Twitter
API is prohibitively expensive, fetching is **Firecrawl-first**: the JS-heavy X search
page is rendered with `scrape_with_actions` (Playwright: wait → scroll → scrape) under a
stealth proxy, mirroring the Investing.com TR pattern in `news_portal_scraper.py`.

`ntscraper` (public Nitter instances) is kept as a *secondary* fallback only — most
Nitter instances are unreliable in 2026, so it is tried only when the rendered search
yields nothing and the package is installed.

I/O-only: sentiment analysis and persistence are orchestrated by
CollectSocialSentimentUseCase.
"""
from __future__ import annotations

import logging
import re
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

from bs4 import BeautifulSoup

from scrapers.base_scraper import BaseScraper
from domain.entities.social_post import SocialPost, PLATFORM_TWITTER

logger = logging.getLogger(__name__)


class SocialMediaScraper(BaseScraper):
    """Scrape X/FinTwit for ticker mentions into SocialPost objects."""

    # X 'live' search; %23 = '#', %24 = '$'. We render both the hashtag and cashtag
    # variants because Turkish FinTwit uses them interchangeably.
    SEARCH_URL = "https://x.com/search?q={query}&src=typed_query&f=live"
    QUERY_FORMS = ("%23{t}", "%24{t}")  # #TICKER, $TICKER

    LOCATION_TR = {"country": "TR", "languages": ["tr-TR", "tr"]}

    @staticmethod
    def _within_window(posted: Optional[datetime], days_back: int) -> bool:
        if posted is None:
            return True
        return posted >= datetime.utcnow() - timedelta(days=days_back)

    # ── Firecrawl Playwright (primary) ────────────────────────────────────────
    async def fetch_tweets(
        self,
        ticker: str,
        days_back: int = 7,
        limit: int = 30,
    ) -> List[SocialPost]:
        """Render X live-search for #TICKER and $TICKER and harvest posts."""
        ticker = ticker.strip().upper()
        posts: Dict[str, SocialPost] = {}

        for form in self.QUERY_FORMS:
            url = self.SEARCH_URL.format(query=form.format(t=ticker))
            actions = [
                {"type": "wait", "milliseconds": 4000},
                {"type": "scroll", "direction": "down"},
                {"type": "wait", "milliseconds": 2000},
                {"type": "scroll", "direction": "down"},
                {"type": "wait", "milliseconds": 2000},
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
                continue
            html = (result.get("data") or {}).get("html") or ""
            for post in self._parse_tweets(html, ticker, limit):
                posts.setdefault(post.post_id, post)
            if len(posts) >= limit:
                break

        found = [p for p in posts.values() if self._within_window(p.posted_at, days_back)]

        # Secondary fallback: ntscraper (Nitter), only if rendering produced nothing.
        if not found:
            found = self._fetch_via_ntscraper(ticker, limit)
            found = [p for p in found if self._within_window(p.posted_at, days_back)]

        logger.info(f"X/FinTwit {ticker}: {len(found)} posts")
        return found[:limit]

    def _parse_tweets(self, html: str, ticker: str, limit: int) -> List[SocialPost]:
        """Best-effort parse of rendered X search HTML into SocialPost objects."""
        if not html:
            return []
        soup = BeautifulSoup(html, "html.parser")
        posts: List[SocialPost] = []
        seen_text: set = set()

        # X renders each tweet in an <article>; tweet text lives in
        # [data-testid="tweetText"]. Fall back to article text when testid is absent.
        articles = soup.find_all("article") or []
        for art in articles:
            node = art.find(attrs={"data-testid": "tweetText"}) or art
            text = node.get_text(" ", strip=True)
            if not text or len(text) < 5 or text in seen_text:
                continue
            seen_text.add(text)

            href = ""
            link = art.find("a", href=re.compile(r"/status/\d+"))
            if link and link.get("href"):
                href = "https://x.com" + link["href"]

            author = None
            author_link = art.find("a", href=re.compile(r"^/[^/]+$"))
            if author_link and author_link.get("href"):
                author = author_link["href"].lstrip("/")

            try:
                posts.append(
                    SocialPost(
                        platform=PLATFORM_TWITTER,
                        ticker=ticker,
                        text=text,
                        url=href,
                        author=author,
                    )
                )
            except ValueError:
                continue
            if len(posts) >= limit:
                break
        return posts

    # ── ntscraper (secondary fallback) ────────────────────────────────────────
    def _fetch_via_ntscraper(self, ticker: str, limit: int) -> List[SocialPost]:
        """Fallback to ntscraper/Nitter when Firecrawl rendering yields nothing."""
        try:
            from ntscraper import Nitter
        except Exception:
            logger.info("ntscraper not installed; skipping Nitter fallback")
            return []

        posts: List[SocialPost] = []
        try:
            scraper = Nitter(log_level=1, skip_instance_check=False)
            data = scraper.get_tweets(f"#{ticker}", mode="hashtag", number=limit)
            tweets = (data or {}).get("tweets", []) if isinstance(data, dict) else []
            for tw in tweets:
                text = (tw.get("text") or "").strip()
                if not text:
                    continue
                stats = tw.get("stats") or {}
                try:
                    posts.append(
                        SocialPost(
                            platform=PLATFORM_TWITTER,
                            ticker=ticker,
                            text=text,
                            url=tw.get("link") or "",
                            author=(tw.get("user") or {}).get("username"),
                            likes=int(stats.get("likes") or 0),
                            retweets=int(stats.get("retweets") or 0),
                        )
                    )
                except ValueError:
                    continue
        except Exception as e:  # noqa: BLE001 - Nitter instances are flaky by design
            logger.warning(f"ntscraper fallback failed for {ticker}: {e}")
        return posts

    # ── orchestration ─────────────────────────────────────────────────────────
    async def scrape_all(
        self,
        tickers: List[str],
        days_back: int = 7,
        limit_per_ticker: int = 30,
    ) -> Dict[str, Any]:
        """Collect posts for each ticker. Returns {success, total, by_ticker, posts}."""
        all_posts: List[SocialPost] = []
        by_ticker: Dict[str, int] = {}
        for ticker in tickers or []:
            try:
                found = await self.fetch_tweets(ticker, days_back, limit_per_ticker)
            except Exception as e:
                logger.error(f"X scrape failed for {ticker}: {e}", exc_info=True)
                found = []
            by_ticker[ticker.strip().upper()] = len(found)
            all_posts.extend(found)

        return {
            "success": True,
            "total": len(all_posts),
            "by_ticker": by_ticker,
            "posts": all_posts,
        }

    # BaseScraper abstract method.
    async def scrape(self, **kwargs) -> Dict[str, Any]:
        """Alias for scrape_all() to satisfy the BaseScraper contract."""
        return await self.scrape_all(**kwargs)
