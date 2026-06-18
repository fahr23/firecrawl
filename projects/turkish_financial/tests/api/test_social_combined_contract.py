"""
Tests for the social + combined sentiment endpoints — Data Contract v1.0.

Covers point + history through FastAPI with a mocked database, verifying that each view
reads the right aggregate column (social_score vs combined_score) and emits a valid
envelope.
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
    PoolExhaustedError = DatabaseManager.PoolExhaustedError

    def __init__(self, point_rows=None, history_rows=None):
        self.point_rows = point_rows or []
        self.history_rows = history_rows or []

    def query(self, sql, params=None):
        if "LIMIT 1" in sql:
            return self.point_rows
        return self.history_rows


def _row(news=0.5, social=-0.25, combined=0.2, period=None):
    return {
        "ticker": "THYAO",
        "period_date": period or date(2026, 6, 14),
        "news_score": news,
        "news_count": 6,
        "social_score": social,
        "social_count": 9,
        "combined_score": combined,
        "computed_at": datetime.now(timezone.utc) - timedelta(seconds=300),
    }


def make_client(db: FakeDB) -> TestClient:
    app = FastAPI()
    app.include_router(news_sentiment.router, prefix="/api/external/v1")
    app.dependency_overrides[get_db_manager] = lambda: db
    return TestClient(app)


class TestSocialView:
    def test_reads_social_score(self):
        client = make_client(FakeDB(point_rows=[_row(social=-0.25)]))
        r = client.get("/api/external/v1/social-sentiment/THYAO?market=bist")
        assert r.status_code == 200
        body = r.json()
        ProviderEnvelope(**body)
        assert body["provider"] == "social-media-scraper"
        payload = SentimentPayload(**body["payload"])
        assert payload.score == -0.25
        assert payload.overall_sentiment.value == "negative"
        assert payload.sample_size == 9  # social_count only

    def test_history_provider(self):
        rows = [_row(period=date(2026, 6, 14 - i)) for i in range(2)]
        client = make_client(FakeDB(history_rows=rows))
        body = client.get(
            "/api/external/v1/social-sentiment/THYAO/history?market=bist"
        ).json()
        assert body["provider"] == "social-media-scraper"
        assert len(body["items"]) == 2


class TestCombinedView:
    def test_reads_combined_score(self):
        client = make_client(FakeDB(point_rows=[_row(combined=0.2)]))
        body = client.get("/api/external/v1/combined-sentiment/THYAO?market=bist").json()
        ProviderEnvelope(**body)
        assert body["provider"] == "news+social"
        payload = SentimentPayload(**body["payload"])
        assert payload.score == 0.2
        assert payload.overall_sentiment.value == "positive"
        assert payload.sample_size == 15  # news_count + social_count

    def test_unsupported_market_unavailable(self):
        client = make_client(FakeDB(point_rows=[_row()]))
        body = client.get("/api/external/v1/combined-sentiment/AAPL?market=usa").json()
        assert body["status"] == "unavailable"
        assert body["payload"] is None
