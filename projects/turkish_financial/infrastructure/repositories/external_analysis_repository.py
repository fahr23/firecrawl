"""
External Analysis Provider repository — Data Contract v1.0 fetching layer.

Reads our own KAP sentiment tables (`kap_disclosures` JOIN `kap_disclosure_sentiment`)
and normalises rows into the contract's common envelope. The router stays thin; all
DB access and shaping happens here.

Only the sentiment `kind` is backed by real data. Score is derived from
`overall_sentiment × confidence` (§2 fallback), which is consistent regardless of
whether the legacy `sentiment_score` column stored a signed score or a confidence.
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

from domain.entities.external_analysis import (
    OverallSentiment,
    RiskLevel,
    derive_score,
)
from infrastructure.contracts.instrument_identity_map import resolve_name_patterns

logger = logging.getLogger(__name__)

PROVIDER_ID = "kap-scraper"
_VALID_SENTIMENTS = {s.value for s in OverallSentiment}
_VALID_RISK_LEVELS = {r.value for r in RiskLevel}


def _to_iso_utc(value: Any) -> Optional[str]:
    """Render a DB timestamp/date as ISO-8601 UTC (naive values treated as UTC)."""
    if value is None:
        return None
    if isinstance(value, datetime):
        dt = value if value.tzinfo else value.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    # date or string
    try:
        return datetime.fromisoformat(str(value)).replace(tzinfo=timezone.utc).strftime(
            "%Y-%m-%dT%H:%M:%SZ"
        )
    except ValueError:
        return str(value)


def _freshness_seconds(value: Any) -> int:
    """Age in seconds of the effective timestamp, clamped to >= 0."""
    if value is None:
        return 0
    try:
        if isinstance(value, datetime):
            dt = value if value.tzinfo else value.replace(tzinfo=timezone.utc)
        else:
            dt = datetime.fromisoformat(str(value)).replace(tzinfo=timezone.utc)
    except (ValueError, TypeError):
        return 0
    delta = (datetime.now(timezone.utc) - dt.astimezone(timezone.utc)).total_seconds()
    return max(0, int(delta))


def _parse_array(value: Any) -> List[str]:
    """
    Coerce a stored field into a string array (§2: always send arrays).

    Handles native lists (TEXT[]), JSON array strings, and comma-delimited strings.
    """
    if value is None:
        return []
    if isinstance(value, list):
        return [str(v).strip() for v in value if str(v).strip()]
    text = str(value).strip()
    if not text:
        return []
    if text.startswith("["):
        try:
            parsed = json.loads(text)
            if isinstance(parsed, list):
                return [str(v).strip() for v in parsed if str(v).strip()]
        except json.JSONDecodeError:
            pass
    return [part.strip() for part in text.split(",") if part.strip()]


class ExternalAnalysisRepository:
    """Fetches and normalises KAP sentiment into Data Contract v1.0 envelopes."""

    def __init__(self, db_manager):
        self._db = db_manager

    # ── instrument → company_name filter ────────────────────────────────────
    def _company_filter(
        self, instrument: str, market: str
    ) -> Tuple[Optional[str], List[Any]]:
        """
        Build a SQL WHERE fragment matching the instrument's companies.

        Returns (sql_fragment, params), or (None, []) when the instrument cannot be
        resolved (caller emits an `unavailable` envelope).
        """
        patterns = resolve_name_patterns(instrument, market, db_manager=self._db)
        if not patterns:
            return None, []

        clauses = ["d.stock_code = %s"]
        params: List[Any] = [instrument.strip().upper()]
        for pat in patterns:
            clauses.append("d.company_name ILIKE %s")
            params.append(f"%{pat}%")
        return "(" + " OR ".join(clauses) + ")", params

    # ── point query (§6.1) ───────────────────────────────────────────────────
    def get_point(
        self, instrument: str, market: str, as_of: Optional[str] = None
    ) -> Dict[str, Any]:
        """Latest sentiment at/<= as_of for the instrument. Returns an envelope dict."""
        company_filter, params = self._company_filter(instrument, market)
        if company_filter is None:
            return self._unavailable(instrument, market)

        where = [company_filter]
        if as_of:
            where.append("COALESCE(s.created_at, s.analyzed_at, d.disclosure_date) <= %s")
            params.append(as_of)

        query = f"""
            SELECT s.overall_sentiment, s.sentiment_score, s.confidence,
                   s.impact_horizon, s.key_drivers, s.risk_flags, s.key_sentiments,
                   s.risk_level, s.tone_descriptors, s.sample_size, s.analyzer,
                   COALESCE(s.created_at, s.analyzed_at, d.disclosure_date) AS effective_at
            FROM kap_disclosures d
            JOIN kap_disclosure_sentiment s ON s.disclosure_id = d.id
            WHERE {' AND '.join(where)}
            ORDER BY effective_at DESC NULLS LAST
            LIMIT 1
        """
        rows = self._db.query(query, tuple(params))
        if not rows:
            return self._unavailable(instrument, market)

        return self._envelope(instrument, market, rows[0])

    # ── history (§6.3) ────────────────────────────────────────────────────────
    def get_history(
        self,
        instrument: str,
        market: str,
        date_from: Optional[str] = None,
        date_to: Optional[str] = None,
        limit: int = 100,
        cursor: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Time series of sentiment points with cursor pagination."""
        company_filter, params = self._company_filter(instrument, market)
        if company_filter is None:
            return {
                "instrument": instrument,
                "market": market,
                "items": [],
                "next_cursor": None,
            }

        where = [company_filter]
        if date_from:
            where.append("COALESCE(s.created_at, s.analyzed_at, d.disclosure_date) >= %s")
            params.append(date_from)
        if date_to:
            where.append("COALESCE(s.created_at, s.analyzed_at, d.disclosure_date) <= %s")
            params.append(date_to)
        if cursor:
            # cursor is the effective_at of the last item seen (descending order)
            where.append("COALESCE(s.created_at, s.analyzed_at, d.disclosure_date) < %s")
            params.append(cursor)

        fetch = max(1, min(limit, 1000))
        query = f"""
            SELECT s.overall_sentiment, s.sentiment_score, s.confidence,
                   s.impact_horizon, s.key_drivers, s.risk_flags, s.key_sentiments,
                   s.risk_level, s.tone_descriptors, s.sample_size, s.analyzer,
                   COALESCE(s.created_at, s.analyzed_at, d.disclosure_date) AS effective_at
            FROM kap_disclosures d
            JOIN kap_disclosure_sentiment s ON s.disclosure_id = d.id
            WHERE {' AND '.join(where)}
            ORDER BY effective_at DESC NULLS LAST
            LIMIT %s
        """
        params.append(fetch + 1)  # fetch one extra to compute next_cursor
        rows = self._db.query(query, tuple(params))

        next_cursor = None
        if len(rows) > fetch:
            rows = rows[:fetch]
            last_effective = rows[-1].get("effective_at")
            next_cursor = _to_iso_utc(last_effective)

        items = [
            {
                "as_of": _to_iso_utc(r.get("effective_at")),
                "payload": self._payload(r),
            }
            for r in rows
        ]
        return {
            "instrument": instrument,
            "market": market,
            "items": items,
            "next_cursor": next_cursor,
        }

    # ── overview (§6.4) ───────────────────────────────────────────────────────
    def get_overview(
        self, market: str, date_from: Optional[str] = None, date_to: Optional[str] = None
    ) -> Dict[str, Any]:
        """Distribution + daily trend across all instruments in the window."""
        where = ["1=1"]
        params: List[Any] = []
        if date_from:
            where.append("DATE(COALESCE(s.created_at, s.analyzed_at)) >= %s")
            params.append(date_from)
        if date_to:
            where.append("DATE(COALESCE(s.created_at, s.analyzed_at)) <= %s")
            params.append(date_to)
        where_clause = " AND ".join(where)

        summary_rows = self._db.query(
            f"""
            SELECT COUNT(*) AS total_analyses,
                   COUNT(DISTINCT d.company_name) AS unique_instruments,
                   AVG(s.confidence) AS average_confidence,
                   COUNT(*) FILTER (WHERE s.overall_sentiment = 'positive') AS positive,
                   COUNT(*) FILTER (WHERE s.overall_sentiment = 'neutral')  AS neutral,
                   COUNT(*) FILTER (WHERE s.overall_sentiment = 'negative') AS negative
            FROM kap_disclosure_sentiment s
            JOIN kap_disclosures d ON s.disclosure_id = d.id
            WHERE {where_clause}
            """,
            tuple(params),
        )
        s = summary_rows[0] if summary_rows else {}
        total = int(s.get("total_analyses") or 0)
        pos = int(s.get("positive") or 0)
        neu = int(s.get("neutral") or 0)
        neg = int(s.get("negative") or 0)

        def _frac(n: int) -> float:
            return round(n / total, 4) if total else 0.0

        trend_rows = self._db.query(
            f"""
            SELECT DATE(COALESCE(s.created_at, s.analyzed_at)) AS day,
                   AVG(
                       CASE s.overall_sentiment
                           WHEN 'positive' THEN  s.confidence
                           WHEN 'negative' THEN -s.confidence
                           ELSE 0 END
                   ) AS avg_score,
                   COUNT(*) AS count,
                   COUNT(DISTINCT d.company_name) AS unique_instruments
            FROM kap_disclosure_sentiment s
            JOIN kap_disclosures d ON s.disclosure_id = d.id
            WHERE {where_clause}
            GROUP BY day
            ORDER BY day
            """,
            tuple(params),
        )
        daily_trend = [
            {
                "date": str(r.get("day")) if r.get("day") else None,
                "avg_score": round(float(r.get("avg_score") or 0), 4),
                "count": int(r.get("count") or 0),
                "unique_instruments": int(r.get("unique_instruments") or 0),
            }
            for r in trend_rows
        ]

        return {
            "market": market,
            "period": {"from": date_from, "to": date_to},
            "summary": {
                "total_analyses": total,
                "unique_instruments": int(s.get("unique_instruments") or 0),
                "average_confidence": round(float(s.get("average_confidence") or 0), 4),
                "distribution": {
                    "positive": _frac(pos),
                    "neutral": _frac(neu),
                    "negative": _frac(neg),
                },
            },
            "daily_trend": daily_trend,
        }

    # ── shaping helpers ───────────────────────────────────────────────────────
    def _payload(self, row: Dict[str, Any]) -> Dict[str, Any]:
        """Normalise a joined row into a SentimentPayload dict (§2)."""
        sentiment = (row.get("overall_sentiment") or "neutral").lower()
        if sentiment not in _VALID_SENTIMENTS:
            sentiment = "neutral"

        # Legacy rows sometimes stored confidence in sentiment_score; prefer the
        # explicit confidence column and fall back through sensible defaults.
        confidence = row.get("confidence")
        if confidence is None:
            confidence = row.get("sentiment_score")
        confidence = float(confidence) if confidence is not None else 0.5
        confidence = max(0.0, min(1.0, confidence))

        payload: Dict[str, Any] = {
            "overall_sentiment": sentiment,
            "score": derive_score(sentiment, confidence),
            "confidence": round(confidence, 4),
            "key_drivers": _parse_array(row.get("key_drivers"))
            or _parse_array(row.get("key_sentiments")),
            "risk_flags": _parse_array(row.get("risk_flags")),
            "tone_descriptors": _parse_array(row.get("tone_descriptors")),
        }

        impact = row.get("impact_horizon")
        if impact:
            payload["impact_horizon"] = impact

        risk_level = (row.get("risk_level") or "").lower()
        if risk_level in _VALID_RISK_LEVELS:
            payload["risk_level"] = risk_level

        if row.get("sample_size") is not None:
            payload["sample_size"] = int(row["sample_size"])
        if row.get("analyzer"):
            payload["analyzer"] = row["analyzer"]
        return payload

    def _envelope(
        self, instrument: str, market: str, row: Dict[str, Any]
    ) -> Dict[str, Any]:
        effective = row.get("effective_at")
        return {
            "contract_version": "1.0",
            "instrument": instrument,
            "market": market,
            "kind": "sentiment",
            "as_of": _to_iso_utc(effective),
            "provider": PROVIDER_ID,
            "source": "external-db",
            "freshness_seconds": _freshness_seconds(effective),
            "status": "ok",
            "payload": self._payload(row),
        }

    def _unavailable(self, instrument: str, market: str) -> Dict[str, Any]:
        """No data / unresolved instrument → honest empty envelope (§5)."""
        return {
            "contract_version": "1.0",
            "instrument": instrument,
            "market": market,
            "kind": "sentiment",
            "as_of": None,
            "provider": PROVIDER_ID,
            "source": "external-db",
            "freshness_seconds": 0,
            "status": "unavailable",
            "payload": None,
        }
