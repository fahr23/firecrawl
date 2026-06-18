"""
Tests for the news-portal sentiment endpoints — Data Contract v1.0.

Covers point + history through FastAPI with a mocked database:
  - envelope shape + Pydantic validation (§1)
  - score → overall_sentiment/confidence derivation (§2)
  - honest `unavailable` on no-data and unsupported market (§5)

The `news_sentiment` router is mounted on a minimal app so the heavy collect-trigger
imports (scraper / LLM) are never pulled in by the read paths.
"""
from datetime import date, datetime, timezone, timedelta

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from api.dependencies import get_db_manager
from api.routers import news_sentiment
from database.db_manager import DatabaseManager
from domain.entities.external_analysis import ProviderEnvelope, SentimentPayload


class FakeDB:
    """Minimal db_manager stand-in. Routes queries by SQL substring."""

    PoolExhaustedError = DatabaseManager.PoolExhaustedError

    def __init__(self, point_rows=None, history_rows=None, raise_on_query=False):
        self.point_rows = point_rows or []
        self.history_rows = history_rows or []
        self.raise_on_query = raise_on_query

    def query(self, sql, params=None):
        if self.raise_on_query:
            raise RuntimeError("boom")
        if "LIMIT 1" in sql:
            return self.point_rows
        return self.history_rows


def _row(score=0.42, period=None, news_count=5):
    return {
        "ticker": "THYAO",
        "period_date": period or date(2026, 6, 14),
        "news_score": score,
        "news_count": news_count,
        "social_score": None,
        "social_count": 0,
        "combined_score": score,
        "computed_at": datetime.now(timezone.utc) - timedelta(seconds=600),
    }


def make_client(db: FakeDB) -> TestClient:
    app = FastAPI()
    app.include_router(news_sentiment.router, prefix="/api/external/v1")
    app.dependency_overrides[get_db_manager] = lambda: db
    return TestClient(app)


class TestPoint:
    def test_ok_envelope_shape(self):
        client = make_client(FakeDB(point_rows=[_row(score=0.42)]))
        r = client.get("/api/external/v1/news-sentiment/THYAO?market=bist")
        assert r.status_code == 200
        body = r.json()

        env = ProviderEnvelope(**body)
        assert env.contract_version == "1.0"
        assert env.instrument == "THYAO"
        assert env.market.value == "bist"
        assert env.kind.value == "sentiment"
        assert env.provider == "news-portal-scraper"
        assert env.status.value == "ok"

        payload = SentimentPayload(**body["payload"])
        assert payload.overall_sentiment.value == "positive"
        assert payload.score == 0.42
        assert payload.confidence == 0.42
        assert payload.sample_size == 5

    def test_negative_score_maps_to_negative(self):
        client = make_client(FakeDB(point_rows=[_row(score=-0.3)]))
        body = client.get("/api/external/v1/news-sentiment/THYAO?market=bist").json()
        assert body["payload"]["overall_sentiment"] == "negative"
        assert body["payload"]["score"] == -0.3

    def test_near_zero_is_neutral(self):
        client = make_client(FakeDB(point_rows=[_row(score=0.01)]))
        body = client.get("/api/external/v1/news-sentiment/THYAO?market=bist").json()
        assert body["payload"]["overall_sentiment"] == "neutral"

    def test_no_data_is_unavailable(self):
        client = make_client(FakeDB(point_rows=[]))
        body = client.get("/api/external/v1/news-sentiment/THYAO?market=bist").json()
        assert body["status"] == "unavailable"
        assert body["payload"] is None
        assert body["as_of"] is None

    def test_unsupported_market_is_unavailable(self):
        client = make_client(FakeDB(point_rows=[_row()]))
        body = client.get("/api/external/v1/news-sentiment/AAPL?market=usa").json()
        assert body["status"] == "unavailable"
        assert body["payload"] is None

    def test_db_error_returns_503(self):
        client = make_client(FakeDB(raise_on_query=True))
        r = client.get("/api/external/v1/news-sentiment/THYAO?market=bist")
        assert r.status_code == 503
        assert r.json()["error_code"] == "UPSTREAM_DB_ERROR"


class TestHistory:
    def test_items_and_no_cursor(self):
        rows = [_row(period=date(2026, 6, 14 - i)) for i in range(3)]
        client = make_client(FakeDB(history_rows=rows))
        body = client.get(
            "/api/external/v1/news-sentiment/THYAO/history?market=bist&limit=10"
        ).json()
        assert body["kind"] == "sentiment"
        assert body["provider"] == "news-portal-scraper"
        assert len(body["items"]) == 3
        assert body["next_cursor"] is None
        assert "score" in body["items"][0]["payload"]

    def test_pagination_sets_cursor(self):
        rows = [_row(period=date(2026, 6, 14 - i)) for i in range(3)]
        client = make_client(FakeDB(history_rows=rows))
        body = client.get(
            "/api/external/v1/news-sentiment/THYAO/history?market=bist&limit=2"
        ).json()
        assert len(body["items"]) == 2
        assert body["next_cursor"] is not None

    def test_unsupported_market_empty(self):
        client = make_client(FakeDB(history_rows=[_row()]))
        body = client.get(
            "/api/external/v1/news-sentiment/AAPL/history?market=usa"
        ).json()
        assert body["items"] == []
        assert body["next_cursor"] is None
