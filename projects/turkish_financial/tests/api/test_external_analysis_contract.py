"""
Tests for the External Analysis Provider — Data Contract v1.0.

Covers the provider side end-to-end through FastAPI with a mocked database:
  - envelope shape + Pydantic validation (§1)
  - score derivation positive/neutral/negative (§2)
  - array coercion for key_drivers / risk_flags (§2)
  - instrument↔company identity resolution (§0)
  - point / batch / history / overview / health endpoints (§4, §6)
  - honest unavailable + DB-error degradation (§5)

The `external_analysis` router is mounted on a minimal app so the heavy legacy
`sentiment` router (openai / huggingface imports) is not pulled in.
"""
from datetime import datetime, timezone, timedelta
from pathlib import Path
from unittest.mock import Mock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from api.dependencies import get_db_manager
from api.routers import external_analysis
from database.db_manager import DatabaseManager
from domain.entities.external_analysis import (
    ProviderEnvelope,
    SentimentPayload,
    derive_score,
)
from infrastructure.contracts.instrument_identity_map import (
    resolve_name_patterns,
    supports_market,
)
from infrastructure.repositories.external_analysis_repository import _parse_array


# ── fake database ─────────────────────────────────────────────────────────────
class FakeCursor:
    def execute(self, *a, **k):
        return None

    def fetchone(self):
        return (1,)

    def close(self):
        return None


class FakeConn:
    def cursor(self, *a, **k):
        return FakeCursor()


class FakeDB:
    """Minimal db_manager stand-in. Routes queries by SQL substring."""

    PoolExhaustedError = DatabaseManager.PoolExhaustedError

    def __init__(self, point_rows=None, history_rows=None, summary=None, trend=None,
                 raise_on_query=False):
        self.point_rows = point_rows or []
        self.history_rows = history_rows or []
        self.summary = summary
        self.trend = trend or []
        self.raise_on_query = raise_on_query

    def query(self, sql, params=None):
        if self.raise_on_query:
            raise RuntimeError("boom")
        if "FROM bist_companies" in sql:
            return []  # force static-map resolution
        if "total_analyses" in sql:
            return [self.summary] if self.summary is not None else []
        if "GROUP BY day" in sql:
            return self.trend
        if "ORDER BY effective_at" in sql and "LIMIT 1" in sql:
            return self.point_rows
        if "ORDER BY effective_at" in sql:
            return self.history_rows
        return []

    def get_connection(self):
        return FakeConn()

    def return_connection(self, conn):
        return None


def _row(sentiment="positive", confidence=0.78, **over):
    row = {
        "overall_sentiment": sentiment,
        "sentiment_score": confidence,
        "confidence": confidence,
        "impact_horizon": "medium_term",
        "key_drivers": '["traffic_growth", "fuel_cost_decline"]',
        "risk_flags": "fx_exposure",
        "key_sentiments": None,
        "risk_level": "medium",
        "tone_descriptors": "optimistic, forward_looking",
        "sample_size": 12,
        "analyzer": "llm:gemini-1.5",
        "effective_at": datetime.now(timezone.utc) - timedelta(seconds=1840),
    }
    row.update(over)
    return row


def make_client(db: FakeDB) -> TestClient:
    app = FastAPI()
    app.include_router(external_analysis.router, prefix="/api/external/v1")
    app.dependency_overrides[get_db_manager] = lambda: db
    return TestClient(app)


def test_finance_dashboard_assets_describe_the_external_contract_without_advice():
    web_dir = Path(__file__).resolve().parents[2] / "web"
    page = (web_dir / "index.html").read_text()
    script = (web_dir / "app.js").read_text()

    assert "not investment advice" in page
    assert "/api/external/v1/capabilities" in script
    assert "/api/external/v1/${selectedKind}" in script
    assert "/api/external/v1/instruments?market=bist" in script
    assert "/api/external/v1/scores/refresh" in script
    assert "combined-sentiment" in page
    assert "youtube-sentiment" in page


def test_instruments_catalog_includes_named_starter_instruments_when_database_is_sparse():
    client = make_client(FakeDB())
    response = client.get("/api/external/v1/instruments?market=bist")
    assert response.status_code == 200
    items = response.json()["items"]
    thy = next(item for item in items if item["ticker"] == "THYAO")
    assert thy["company_name"] == "Türk Hava Yolları"
    assert thy["catalog_source"] == "built_in_catalog"


def test_instruments_catalog_keeps_data_tickers_when_company_refresh_is_missing():
    class DataOnlyDB(FakeDB):
        def query(self, sql, params=None):
            if "has_fundamental" in sql and "all_tickers" in sql:
                return [{
                    "ticker": "ASELS", "company_name": None, "sector": None,
                    "has_sentiment": False, "has_fundamental": True,
                    "has_news_sentiment": True,
                }]
            return super().query(sql, params)

    items = make_client(DataOnlyDB()).get("/api/external/v1/instruments?market=bist").json()["items"]
    asels = next(item for item in items if item["ticker"] == "ASELS")
    assert asels["company_name"] == "Aselsan"
    assert asels["available_data"] == ["fundamental", "news_sentiment", "combined_sentiment"]


def test_capabilities_only_advertises_the_confirmed_local_parse_route():
    client = make_client(FakeDB())
    root = Mock(status_code=200)
    parse_probe = Mock(status_code=400)

    with patch("api.routers.external_analysis.requests.get", return_value=root), patch(
        "api.routers.external_analysis.requests.post", return_value=parse_probe
    ):
        response = client.get("/api/external/v1/capabilities")

    assert response.status_code == 200
    body = response.json()
    assert body["contract_version"] == "1.0"
    assert body["firecrawl"]["status"] == "ok"
    assert body["firecrawl"]["document_parse"] is True
    assert "parse" in body["firecrawl"]["operations"]


def test_capabilities_degrades_honestly_when_firecrawl_is_unreachable():
    client = make_client(FakeDB())

    with patch(
        "api.routers.external_analysis.requests.get",
        side_effect=external_analysis.requests.RequestException("offline"),
    ):
        body = client.get("/api/external/v1/capabilities").json()

    assert body["firecrawl"]["status"] == "unavailable"
    assert body["firecrawl"]["operations"] == []


# ════════════════════════════════════════════════════════════════════════════
# Pure helpers
# ════════════════════════════════════════════════════════════════════════════
class TestScoreDerivation:
    def test_positive_is_plus_confidence(self):
        assert derive_score("positive", 0.62) == 0.62

    def test_negative_is_minus_confidence(self):
        assert derive_score("negative", 0.62) == -0.62

    def test_neutral_is_zero(self):
        assert derive_score("neutral", 0.9) == 0.0

    def test_confidence_clamped(self):
        assert derive_score("positive", 5.0) == 1.0
        assert derive_score("positive", -2.0) == 0.0

    def test_bad_confidence_safe(self):
        assert derive_score("positive", None) == 0.0


class TestArrayParsing:
    def test_json_array_string(self):
        assert _parse_array('["a", "b"]') == ["a", "b"]

    def test_comma_string(self):
        assert _parse_array("a, b ,c") == ["a", "b", "c"]

    def test_native_list(self):
        assert _parse_array(["x", "y"]) == ["x", "y"]

    def test_none_and_empty(self):
        assert _parse_array(None) == []
        assert _parse_array("") == []


class TestIdentityResolution:
    def test_known_bist_ticker(self):
        pats = resolve_name_patterns("THYAO", "bist")
        assert any("hava yolları" in p.lower() or "hava yollari" in p.lower() for p in pats)

    def test_case_insensitive(self):
        assert resolve_name_patterns("thyao", "bist")

    def test_unsupported_market_returns_empty(self):
        assert resolve_name_patterns("AAPL", "usa") == []
        assert not supports_market("usa")
        assert supports_market("bist")

    def test_unknown_ticker_falls_back_to_self(self):
        assert resolve_name_patterns("ZZZZ", "bist") == ["ZZZZ"]


# ════════════════════════════════════════════════════════════════════════════
# Point endpoint (§6.1)
# ════════════════════════════════════════════════════════════════════════════
class TestPoint:
    def test_ok_envelope_shape(self):
        client = make_client(FakeDB(point_rows=[_row()]))
        r = client.get("/api/external/v1/sentiment/THYAO?market=bist")
        assert r.status_code == 200
        body = r.json()

        # validates against the contract model
        env = ProviderEnvelope(**body)
        assert env.contract_version == "1.0"
        assert env.instrument == "THYAO"
        assert env.market.value == "bist"
        assert env.kind.value == "sentiment"
        assert env.provider == "kap-scraper"
        assert env.source == "external-db"
        assert env.status.value == "ok"
        assert env.as_of is not None
        assert env.freshness_seconds >= 1800

        payload = SentimentPayload(**body["payload"])
        assert payload.overall_sentiment.value == "positive"
        assert payload.score == 0.78
        assert payload.confidence == 0.78
        assert payload.key_drivers == ["traffic_growth", "fuel_cost_decline"]
        assert payload.risk_flags == ["fx_exposure"]
        assert payload.tone_descriptors == ["optimistic", "forward_looking"]
        assert payload.sample_size == 12
        assert payload.analyzer == "llm:gemini-1.5"

    def test_negative_score_sign(self):
        client = make_client(FakeDB(point_rows=[_row(sentiment="negative", confidence=0.5)]))
        body = client.get("/api/external/v1/sentiment/AKBNK?market=bist").json()
        assert body["payload"]["score"] == -0.5

    def test_no_data_is_unavailable(self):
        client = make_client(FakeDB(point_rows=[]))
        body = client.get("/api/external/v1/sentiment/THYAO?market=bist").json()
        assert body["status"] == "unavailable"
        assert body["payload"] is None
        assert body["as_of"] is None

    def test_unsupported_market_is_unavailable(self):
        client = make_client(FakeDB(point_rows=[_row()]))
        body = client.get("/api/external/v1/sentiment/AAPL?market=usa").json()
        assert body["status"] == "unavailable"
        assert body["payload"] is None

    def test_db_error_returns_503(self):
        client = make_client(FakeDB(raise_on_query=True))
        r = client.get("/api/external/v1/sentiment/THYAO?market=bist")
        assert r.status_code == 503
        body = r.json()
        assert body["status"] == "unavailable"
        assert body["error_code"] == "UPSTREAM_DB_ERROR"


# ════════════════════════════════════════════════════════════════════════════
# Batch endpoint (§6.2)
# ════════════════════════════════════════════════════════════════════════════
class TestBatch:
    def test_partial_items(self):
        # THYAO resolves and has a row; ZZZZ resolves to self but no rows -> unavailable
        client = make_client(FakeDB(point_rows=[_row()]))
        r = client.post(
            "/api/external/v1/sentiment/batch",
            json={"market": "bist", "instruments": ["THYAO", "ZZZZ"]},
        )
        assert r.status_code == 200
        body = r.json()
        assert body["contract_version"] == "1.0"
        assert len(body["items"]) == 2
        # Both share the same fake point rows, so both are 'ok' here; assert envelope echo
        assert body["items"][0]["instrument"] == "THYAO"
        assert body["items"][1]["instrument"] == "ZZZZ"

    def test_empty_instruments_rejected(self):
        client = make_client(FakeDB())
        r = client.post(
            "/api/external/v1/sentiment/batch",
            json={"market": "bist", "instruments": []},
        )
        assert r.status_code == 422


# ════════════════════════════════════════════════════════════════════════════
# History endpoint (§6.3)
# ════════════════════════════════════════════════════════════════════════════
class TestHistory:
    def test_items_and_no_cursor(self):
        rows = [_row(effective_at=datetime.now(timezone.utc) - timedelta(days=i))
                for i in range(3)]
        client = make_client(FakeDB(history_rows=rows))
        body = client.get(
            "/api/external/v1/sentiment/THYAO/history?market=bist&limit=10"
        ).json()
        assert body["kind"] == "sentiment"
        assert len(body["items"]) == 3
        assert body["next_cursor"] is None
        assert "as_of" in body["items"][0]
        assert "score" in body["items"][0]["payload"]

    def test_pagination_sets_cursor(self):
        # limit=2 but repo fetches limit+1=3 rows -> trims to 2 and sets next_cursor
        rows = [_row(effective_at=datetime.now(timezone.utc) - timedelta(days=i))
                for i in range(3)]
        client = make_client(FakeDB(history_rows=rows))
        body = client.get(
            "/api/external/v1/sentiment/THYAO/history?market=bist&limit=2"
        ).json()
        assert len(body["items"]) == 2
        assert body["next_cursor"] is not None

    def test_unsupported_market_empty(self):
        client = make_client(FakeDB(history_rows=[_row()]))
        body = client.get(
            "/api/external/v1/sentiment/AAPL/history?market=usa"
        ).json()
        assert body["items"] == []
        assert body["next_cursor"] is None


# ════════════════════════════════════════════════════════════════════════════
# Overview endpoint (§6.4)
# ════════════════════════════════════════════════════════════════════════════
class TestOverview:
    def test_distribution_and_trend(self):
        summary = {
            "total_analyses": 100,
            "unique_instruments": 30,
            "average_confidence": 0.69,
            "positive": 46,
            "neutral": 33,
            "negative": 21,
        }
        trend = [
            {"day": "2026-06-13", "avg_score": 0.24, "count": 138, "unique_instruments": 118},
            {"day": "2026-06-14", "avg_score": 0.27, "count": 96, "unique_instruments": 88},
        ]
        client = make_client(FakeDB(summary=summary, trend=trend))
        body = client.get(
            "/api/external/v1/sentiment/overview?market=bist&from=2026-05-15&to=2026-06-14"
        ).json()
        assert body["contract_version"] == "1.0"
        assert body["market"] == "bist"
        assert body["summary"]["total_analyses"] == 100
        dist = body["summary"]["distribution"]
        assert dist["positive"] == 0.46
        assert dist["neutral"] == 0.33
        assert dist["negative"] == 0.21
        assert len(body["daily_trend"]) == 2
        assert body["daily_trend"][0]["date"] == "2026-06-13"

    def test_empty_overview(self):
        client = make_client(FakeDB(summary={"total_analyses": 0}, trend=[]))
        body = client.get("/api/external/v1/sentiment/overview?market=bist").json()
        assert body["summary"]["total_analyses"] == 0
        assert body["summary"]["distribution"]["positive"] == 0.0


# ════════════════════════════════════════════════════════════════════════════
# Health endpoint (§6.8)
# ════════════════════════════════════════════════════════════════════════════
class TestHealth:
    def test_ok(self):
        client = make_client(FakeDB())
        body = client.get("/api/external/v1/health").json()
        assert body["status"] == "ok"
        assert body["contract_version"] == "1.0"
        assert body["provider"] == "kap-scraper"
