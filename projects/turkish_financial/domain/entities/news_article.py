"""
News article entity — financial news/portal items used for sentiment.

A `NewsArticle` is one item scraped from a Turkish financial news portal
(Bloomberg HT, Foreks, Mynet Finans, Bigpara, Investing.com TR). Unlike KAP
disclosures, an article is not always tied to a single instrument — macro/sector
headlines carry ``ticker = None``. Articles are analysed individually and then
aggregated per ticker per day (see CollectNewsSentimentUseCase).

This is a plain, hashable identity holder; sentiment lives in the
`SentimentAnalysis` value object and is persisted alongside via the repository.
"""
from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, Optional


# Canonical source identifiers. Kept here so the scraper, DB and API agree on spelling.
SOURCE_BLOOMBERG_HT = "bloomberght"
SOURCE_FOREKS = "foreks"
SOURCE_MYNET_FINANS = "mynetfinans"
SOURCE_BIGPARA = "bigpara"
SOURCE_INVESTING_TR = "investing_tr"
SOURCE_HABERTURK = "haberturk"
SOURCE_NTV = "ntv"
SOURCE_EKONOMIM = "ekonomim"
SOURCE_DUNYA = "dunya"
SOURCE_FINANSGUNDEM = "finansgundem"
SOURCE_PARAAJANSI = "paraajansi"
SOURCE_AA_EKONOMI = "aa_ekonomi"
SOURCE_TRT_EKONOMI = "trt_ekonomi"
SOURCE_BORSAGUNDEM = "borsagundem"
SOURCE_CNBCE = "cnbce"
SOURCE_DOVIZCOM = "dovizcom"

VALID_SOURCES = frozenset(
    {
        SOURCE_BLOOMBERG_HT,
        SOURCE_FOREKS,
        SOURCE_MYNET_FINANS,
        SOURCE_BIGPARA,
        SOURCE_INVESTING_TR,
        SOURCE_HABERTURK,
        SOURCE_NTV,
        SOURCE_EKONOMIM,
        SOURCE_DUNYA,
        SOURCE_FINANSGUNDEM,
        SOURCE_PARAAJANSI,
        SOURCE_AA_EKONOMI,
        SOURCE_TRT_EKONOMI,
        SOURCE_BORSAGUNDEM,
        SOURCE_CNBCE,
        SOURCE_DOVIZCOM,
    }
)


@dataclass
class NewsArticle:
    """One financial-news item from a Turkish portal."""

    source: str
    headline: str
    url: str
    body: str = ""
    ticker: Optional[str] = None
    published_at: Optional[datetime] = None
    scraped_at: datetime = field(default_factory=datetime.utcnow)
    article_id: str = ""

    def __post_init__(self) -> None:
        if not self.headline or not self.headline.strip():
            raise ValueError("NewsArticle.headline is required")
        self.headline = self.headline.strip()
        if self.ticker:
            self.ticker = self.ticker.strip().upper()
        if not self.article_id:
            self.article_id = self._build_id()

    def _build_id(self) -> str:
        """Stable id from source + url (falls back to headline when url is blank)."""
        basis = f"{self.source}|{self.url or self.headline}"
        return hashlib.sha1(basis.encode("utf-8")).hexdigest()[:32]

    def text_for_analysis(self) -> str:
        """Headline + body, the text handed to the sentiment analyzer."""
        body = (self.body or "").strip()
        return f"{self.headline}\n\n{body}".strip() if body else self.headline

    def to_db_row(self) -> Dict[str, Any]:
        """Shape this article for DatabaseManager.upsert_news_article()."""
        return {
            "article_id": self.article_id,
            "source": self.source,
            "ticker": self.ticker,
            "headline": self.headline,
            "body": self.body or None,
            "url": self.url or None,
            "published_at": self.published_at,
        }
