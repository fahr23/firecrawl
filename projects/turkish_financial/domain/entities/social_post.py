"""
Social media post entity — X/FinTwit items used for retail sentiment.

A `SocialPost` is one tweet/post scraped from X (Twitter) by searching the Turkish
FinTwit cashtag/hashtag forms (e.g. ``#THYAO``, ``$SASA``, ``#EREGL``). Each post is
tied to the ticker it was searched under, analysed individually, then aggregated into
the per-ticker daily rollup alongside news (see CollectSocialSentimentUseCase).

Mirrors the shape and conventions of [[news-article]] so the two sources persist and
aggregate through the same machinery.
"""
from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, Optional


PLATFORM_TWITTER = "twitter"


@dataclass
class SocialPost:
    """One social-media post (tweet) referencing a BIST ticker."""

    platform: str
    ticker: str
    text: str
    url: str = ""
    author: Optional[str] = None
    posted_at: Optional[datetime] = None
    likes: int = 0
    retweets: int = 0
    scraped_at: datetime = field(default_factory=datetime.utcnow)
    post_id: str = ""

    def __post_init__(self) -> None:
        if not self.text or not self.text.strip():
            raise ValueError("SocialPost.text is required")
        self.text = self.text.strip()
        self.ticker = self.ticker.strip().upper()
        if not self.post_id:
            self.post_id = self._build_id()

    def _build_id(self) -> str:
        """Stable id from platform + url, falling back to ticker + text hash."""
        basis = f"{self.platform}|{self.url or (self.ticker + '|' + self.text)}"
        return hashlib.sha1(basis.encode("utf-8")).hexdigest()[:32]

    def text_for_analysis(self) -> str:
        """The text handed to the sentiment analyzer."""
        return self.text

    def to_db_row(self) -> Dict[str, Any]:
        """Shape this post for DatabaseManager.upsert_social_post()."""
        return {
            "post_id": self.post_id,
            "platform": self.platform,
            "ticker": self.ticker,
            "text": self.text,
            "author": self.author,
            "posted_at": self.posted_at,
            "likes": self.likes,
            "retweets": self.retweets,
        }
