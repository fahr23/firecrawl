"""Tests for the guarded dashboard action that refreshes source scores."""
from unittest.mock import AsyncMock, patch

from fastapi import FastAPI
from fastapi.testclient import TestClient

from api.dependencies import get_db_manager
from api.routers import news_sentiment


def _client() -> TestClient:
    app = FastAPI()
    app.include_router(news_sentiment.router, prefix="/api/external/v1")
    class StaleCacheDB:
        def get_source_refresh_cache(self, ticker, max_age_seconds):
            return {
                source: {"fresh": False, "age_seconds": None}
                for source in ("news", "social", "youtube")
            }

    app.dependency_overrides[get_db_manager] = StaleCacheDB
    return TestClient(app)


def test_refresh_collects_each_source_sequentially_and_returns_partial_results():
    calls = []

    async def news(request, db_manager):
        calls.append(("news", request.tickers, request.days_back))
        return {"contract_version": "1.0"}

    async def social(request, db_manager):
        calls.append(("social", request.tickers, request.days_back))
        return {"contract_version": "1.0"}

    async def youtube(request, db_manager):
        calls.append(("youtube", request.days_back, request.stored_only))
        raise RuntimeError("source unavailable")

    with patch.object(news_sentiment, "news_sentiment_collect", new=AsyncMock(side_effect=news)), patch.object(
        news_sentiment, "social_sentiment_collect", new=AsyncMock(side_effect=social)
    ), patch("api.routers.youtube_sentiment.youtube_sentiment_collect", new=AsyncMock(side_effect=youtube)):
        response = _client().post(
            "/api/external/v1/scores/refresh",
            json={"ticker": "thyao", "days_back": 3},
        )

    assert response.status_code == 200
    assert response.json()["status"] == "partial"
    assert response.json()["ticker"] == "THYAO"
    assert response.json()["sources"] == [
        {"source": "news", "status": "ok"},
        {"source": "social", "status": "ok"},
        {"source": "youtube", "status": "error", "detail": "collection failed"},
    ]
    assert calls == [
        ("news", ["THYAO"], 3),
        ("social", ["THYAO"], 3),
        ("youtube", 3, True),
    ]


def test_refresh_uses_fresh_database_sources_without_collecting():
    class FreshCacheDB:
        def get_source_refresh_cache(self, ticker, max_age_seconds):
            return {
                source: {"fresh": True, "age_seconds": 42}
                for source in ("news", "social", "youtube")
            }

    app = FastAPI()
    app.include_router(news_sentiment.router, prefix="/api/external/v1")
    app.dependency_overrides[get_db_manager] = FreshCacheDB

    response = TestClient(app).post(
        "/api/external/v1/scores/refresh", json={"ticker": "THYAO", "days_back": 1}
    )

    assert response.status_code == 200
    assert response.json()["status"] == "ok"
    assert all(item["status"] == "cached" for item in response.json()["sources"])
