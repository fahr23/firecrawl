"""Combined-sentiment batch: one stored point per instrument, no collection."""
from fastapi import FastAPI
from fastapi.testclient import TestClient

from api.dependencies import get_db_manager
from api.routers import news_sentiment
from database.db_manager import DatabaseManager


class FakeDB:
    PoolExhaustedError = DatabaseManager.PoolExhaustedError


def _client(monkeypatch, get_point):
    monkeypatch.setattr(news_sentiment.CombinedSentimentRepository, "get_point", get_point)
    app = FastAPI()
    app.include_router(news_sentiment.router, prefix="/api/external/v1")
    app.dependency_overrides[get_db_manager] = lambda: FakeDB()
    return TestClient(app)


def test_batch_returns_one_envelope_per_instrument_in_order(monkeypatch):
    seen = []

    def get_point(self, instrument, market, as_of=None):
        seen.append((instrument, market, as_of))
        return {"instrument": instrument, "status": "ok" if instrument != "NODATA" else "unavailable"}

    body = _client(monkeypatch, get_point).post(
        "/api/external/v1/combined-sentiment/batch",
        json={"market": "bist", "instruments": ["AKBNK", "NODATA", "TSKB"]},
    ).json()
    assert [item["instrument"] for item in body["items"]] == ["AKBNK", "NODATA", "TSKB"]
    assert body["items"][1]["status"] == "unavailable"
    assert seen == [("AKBNK", "bist", None), ("NODATA", "bist", None), ("TSKB", "bist", None)]


def test_batch_rejects_empty_and_oversized_requests(monkeypatch):
    client = _client(monkeypatch, lambda self, i, m, a=None: {})
    assert client.post("/api/external/v1/combined-sentiment/batch",
                       json={"market": "bist", "instruments": []}).status_code == 422
    assert client.post("/api/external/v1/combined-sentiment/batch",
                       json={"market": "bist", "instruments": [f"T{i}" for i in range(201)]}).status_code == 422


def test_batch_reports_a_database_error_instead_of_raising(monkeypatch):
    def failing(self, instrument, market, as_of=None):
        raise DatabaseManager.PoolExhaustedError("pool exhausted")

    response = _client(monkeypatch, failing).post(
        "/api/external/v1/combined-sentiment/batch", json={"market": "bist", "instruments": ["AKBNK"]})
    assert response.status_code == 503
