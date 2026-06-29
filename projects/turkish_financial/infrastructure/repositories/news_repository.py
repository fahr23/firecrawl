"""
News repository — Data Contract v1.0 platform-news surface.

Reads KAP platform-level announcements (`kap_news`, optionally enriched by
`kap_news_sentiment`) and normalises them into the contract envelope with
`kind = "news"`. These are NOT company disclosures — they are regulatory / system
news (SPK decisions, MKK announcements, BIST notices) that affect whole sectors or
the market, so they are addressed by `news_id` / `category`, not by `instrument`.

Like the other repositories, the router stays thin: all DB access and shaping happen
here, and on no-data we return an honest `unavailable`/empty result (§5).
"""
from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from domain.entities.external_analysis import OverallSentiment, derive_score
from infrastructure.repositories.external_analysis_repository import (
    PROVIDER_ID,
    _to_iso_utc,
    _freshness_seconds,
)

logger = logging.getLogger(__name__)

KIND = "news"
_VALID_SENTIMENTS = {s.value for s in OverallSentiment}

# Columns selected for every read; kept in one place so list/point stay in sync.
_SELECT = (
    "n.news_id, n.news_category, n.title, n.content, n.source_url, n.publish_date, "
    "s.overall_sentiment, s.sentiment_score, s.confidence, s.analyzer"
)
_FROM = (
    "FROM kap_news n "
    "LEFT JOIN kap_news_sentiment s ON s.news_id = n.id"
)

# UNION source: portal news from news_articles (Bloomberg HT, Mynet, etc.)
# Maps news_articles columns → same shape as _SELECT so shaping code is shared.
_PORTAL_SELECT = (
    "a.article_id AS news_id, "
    "a.source AS news_category, "
    "a.headline AS title, "
    "a.body AS content, "
    "a.url AS source_url, "
    "COALESCE(a.published_at, a.scraped_at) AS publish_date, "
    "s.overall_sentiment, s.sentiment_score, s.confidence, s.analyzer"
)
_PORTAL_FROM = (
    "FROM news_articles a "
    "LEFT JOIN news_article_sentiment s ON s.article_id = a.id"
)


class NewsRepository:
    """Fetches/normalises KAP platform news into Data Contract v1.0 envelopes."""

    def __init__(self, db_manager):
        self._db = db_manager

    # ── list (cursor-paginated, newest first) ─────────────────────────────────
    def get_list(
        self,
        category: Optional[str] = None,
        date_from: Optional[str] = None,
        date_to: Optional[str] = None,
        limit: int = 50,
        cursor: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Recent news items from both KAP platform and portal sources (Bloomberg HT etc)."""
        fetch = max(1, min(limit, 1000))

        # Build filter fragments for each branch of the UNION.
        # kap_news branch
        kap_where: List[str] = ["1=1"]
        kap_params: List[Any] = []
        if category:
            kap_where.append("UPPER(n.news_category) = %s")
            kap_params.append(category.strip().upper())
        if date_from:
            kap_where.append("n.publish_date >= %s")
            kap_params.append(date_from)
        if date_to:
            kap_where.append("n.publish_date <= %s")
            kap_params.append(date_to)
        if cursor:
            kap_where.append("n.publish_date < %s")
            kap_params.append(cursor)

        # portal (news_articles) branch — category maps to source
        portal_where: List[str] = ["1=1"]
        portal_params: List[Any] = []
        if category:
            portal_where.append("UPPER(a.source) = %s")
            portal_params.append(category.strip().upper())
        if date_from:
            portal_where.append("COALESCE(a.published_at, a.scraped_at) >= %s")
            portal_params.append(date_from)
        if date_to:
            portal_where.append("COALESCE(a.published_at, a.scraped_at) <= %s")
            portal_params.append(date_to)
        if cursor:
            portal_where.append("COALESCE(a.published_at, a.scraped_at) < %s")
            portal_params.append(cursor)

        union_params = tuple(kap_params + portal_params + [fetch + 1])
        query = f"""
            SELECT {_SELECT} {_FROM}
            WHERE {' AND '.join(kap_where)}
            UNION ALL
            SELECT {_PORTAL_SELECT} {_PORTAL_FROM}
            WHERE {' AND '.join(portal_where)}
            ORDER BY publish_date DESC NULLS LAST
            LIMIT %s
        """
        rows = self._db.query(query, union_params)

        next_cursor = None
        if len(rows) > fetch:
            rows = rows[:fetch]
            next_cursor = _to_iso_utc(rows[-1].get("publish_date"))

        items = [self._item(r) for r in rows]
        return {"items": items, "next_cursor": next_cursor}

    # ── point (single news item by its KAP news_id) ───────────────────────────
    def get_point(self, news_id: str) -> Dict[str, Any]:
        rows = self._db.query(
            f"SELECT {_SELECT} {_FROM} WHERE n.news_id = %s LIMIT 1",
            (news_id,),
        )
        if not rows:
            return self._unavailable(news_id)
        return self._envelope(rows[0])

    # ── shaping helpers ───────────────────────────────────────────────────────
    def _payload(self, row: Dict[str, Any]) -> Dict[str, Any]:
        payload: Dict[str, Any] = {
            "news_id": row.get("news_id"),
            "category": row.get("news_category"),
            "title": row.get("title"),
        }
        if row.get("content"):
            payload["content"] = row["content"]
        if row.get("source_url"):
            payload["source_url"] = row["source_url"]

        sentiment = (row.get("overall_sentiment") or "").lower()
        if sentiment in _VALID_SENTIMENTS:
            confidence = row.get("confidence")
            confidence = float(confidence) if confidence is not None else 0.5
            confidence = max(0.0, min(1.0, confidence))
            payload["sentiment"] = {
                "overall_sentiment": sentiment,
                "score": derive_score(sentiment, confidence),
                "confidence": round(confidence, 4),
            }
            if row.get("analyzer"):
                payload["sentiment"]["analyzer"] = row["analyzer"]
        return payload

    def _item(self, row: Dict[str, Any]) -> Dict[str, Any]:
        return {"as_of": _to_iso_utc(row.get("publish_date")), "payload": self._payload(row)}

    def _envelope(self, row: Dict[str, Any]) -> Dict[str, Any]:
        publish = row.get("publish_date")
        return {
            "contract_version": "1.0",
            "kind": KIND,
            "news_id": row.get("news_id"),
            "as_of": _to_iso_utc(publish),
            "provider": PROVIDER_ID,
            "source": "external-db",
            "freshness_seconds": _freshness_seconds(publish),
            "status": "ok",
            "payload": self._payload(row),
        }

    def _unavailable(self, news_id: str) -> Dict[str, Any]:
        return {
            "contract_version": "1.0",
            "kind": KIND,
            "news_id": news_id,
            "as_of": None,
            "provider": PROVIDER_ID,
            "source": "external-db",
            "freshness_seconds": 0,
            "status": "unavailable",
            "payload": None,
        }
