import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from unittest.mock import Mock

from api.routers.news_sentiment import router as news_sentiment_router
from database.db_manager import DatabaseManager
from api.dependencies import get_db_manager

app = FastAPI()
app.include_router(news_sentiment_router, prefix="/api/external/v1")

@pytest.fixture
def mock_db():
    db = Mock(spec=DatabaseManager)
    # Ensure dependencies injection uses the mock
    app.dependency_overrides[get_db_manager] = lambda: db
    yield db
    app.dependency_overrides.clear()

def test_combined_sentiment_evidence(mock_db):
    client = TestClient(app)
    # Mocking rows returned by the UNION ALL query
    mock_db.query.return_value = [
        {"evidence_type": "news", "evidence_id": "1", "source": "bloomberght", "title": "News 1", "url": "http://x", "occurred_at": None},
        {"evidence_type": "kap", "evidence_id": "10", "source": "KAP", "title": "Disclosure", "url": "http://k", "occurred_at": None},
    ]
    
    resp = client.get("/api/external/v1/combined-sentiment/THYAO/evidence?market=bist&window_days=7")
    assert resp.status_code == 200
    data = resp.json()
    assert data["instrument"] == "THYAO"
    assert len(data["items"]) == 2
    assert data["items"][0]["evidence_type"] == "news"
    assert data["items"][1]["evidence_type"] == "kap"
    assert data["items"][1]["evidence_id"] == "10"

def test_evidence_detail_news(mock_db):
    client = TestClient(app)
    # Mock row returned by news query
    mock_db.query.return_value = [
        {"body": "This is news body", "key_drivers": "positive earnings"}
    ]
    
    resp = client.get("/api/external/v1/evidence/news/1")
    assert resp.status_code == 200
    data = resp.json()
    assert data["source_type"] == "news"
    assert data["id"] == 1
    assert data["text"] == "This is news body"
    assert data["summary"] == "positive earnings"

def test_evidence_detail_invalid_source(mock_db):
    client = TestClient(app)
    resp = client.get("/api/external/v1/evidence/invalid_source/1")
    assert resp.status_code == 400
    assert resp.json()["detail"] == "Invalid source_type"

def test_evidence_detail_not_found(mock_db):
    client = TestClient(app)
    mock_db.query.return_value = []
    resp = client.get("/api/external/v1/evidence/kap/999")
    assert resp.status_code == 200
    data = resp.json()
    assert data["text"] is None
    assert data["summary"] is None
