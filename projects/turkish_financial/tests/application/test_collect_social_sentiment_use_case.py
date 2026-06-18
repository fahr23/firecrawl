"""
Unit tests for CollectSocialSentimentUseCase and the news+social blend.
"""
import asyncio
from datetime import datetime

import pytest

from application.use_cases.collect_social_sentiment_use_case import (
    CollectSocialSentimentUseCase, blend_scores,
)
from domain.entities.social_post import SocialPost, PLATFORM_TWITTER
from domain.value_objects.sentiment import (
    SentimentAnalysis, SentimentType, ImpactHorizon, Confidence,
)


def run(coro):
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


def _sentiment(kind: SentimentType, confidence: float) -> SentimentAnalysis:
    return SentimentAnalysis(
        overall_sentiment=kind,
        confidence=Confidence(confidence),
        impact_horizon=ImpactHorizon.SHORT_TERM,
        key_drivers=("k1",),
        risk_flags=(),
        tone_descriptors=("optimistic",),
        target_audience=None,
        analysis_text="analiz",
        analyzed_at=datetime(2026, 6, 10),
    )


class FakeScraper:
    def __init__(self, posts):
        self._posts = posts

    async def scrape_all(self, tickers, days_back=7, limit_per_ticker=30):
        return {"success": True, "total": len(self._posts),
                "by_ticker": {}, "posts": self._posts}


class FakeAnalyzer:
    def __init__(self, mapping):
        self._mapping = mapping

    async def analyze(self, content, custom_prompt=None):
        for key, sent in self._mapping.items():
            if key in content:
                return sent
        return None


class FakeDB:
    def __init__(self, existing=None):
        self.posts = []
        self.sentiments = []
        self.aggregates = []
        self._id = 0
        self._existing = existing or {}

    def upsert_social_post(self, data):
        self._id += 1
        self.posts.append(data)
        return self._id

    def upsert_social_post_sentiment(self, post_pk, data):
        self.sentiments.append((post_pk, data))
        return True

    def upsert_aggregated_ticker_sentiment(self, data):
        self.aggregates.append(data)
        return True

    def get_aggregated_ticker_sentiment(self, ticker, period_date):
        return self._existing.get((ticker, period_date))


class TestBlendScores:
    def test_both_present(self):
        assert blend_scores(1.0, 0.0) == 0.6
        assert blend_scores(0.5, 0.5) == 0.5

    def test_only_news(self):
        assert blend_scores(0.4, None) == 0.4

    def test_only_social(self):
        assert blend_scores(None, -0.3) == -0.3

    def test_neither(self):
        assert blend_scores(None, None) is None


class TestExecute:
    def test_persists_and_aggregates(self):
        posts = [
            SocialPost(platform=PLATFORM_TWITTER, ticker="THYAO", text="THYAO uçuşta",
                       posted_at=datetime(2026, 6, 10)),
            SocialPost(platform=PLATFORM_TWITTER, ticker="THYAO", text="THYAO güçlü kapanış",
                       posted_at=datetime(2026, 6, 10)),
        ]
        analyzer = FakeAnalyzer({"THYAO": _sentiment(SentimentType.POSITIVE, 0.5)})
        db = FakeDB()
        uc = CollectSocialSentimentUseCase(FakeScraper(posts), analyzer, db)

        result = run(uc.execute(["THYAO"]))
        assert result["analyzed"] == 2
        assert result["saved"] == 2
        assert len(db.aggregates) == 1
        agg = db.aggregates[0]
        # both posts positive conf 0.5 → score 0.5*0.5=0.25 each → mean 0.25
        assert agg["social_score"] == pytest.approx(0.25, abs=1e-4)
        assert agg["social_count"] == 2
        # no existing news → combined == social
        assert agg["combined_score"] == pytest.approx(0.25, abs=1e-4)

    def test_combined_blends_with_existing_news(self):
        posts = [
            SocialPost(platform=PLATFORM_TWITTER, ticker="THYAO", text="THYAO yorum",
                       posted_at=datetime(2026, 6, 10)),
        ]
        analyzer = FakeAnalyzer({"THYAO": _sentiment(SentimentType.NEGATIVE, 1.0)})
        # existing news_score = +0.5 for that ticker/day
        existing = {("THYAO", datetime(2026, 6, 10).date()): {"news_score": 0.5}}
        db = FakeDB(existing=existing)
        uc = CollectSocialSentimentUseCase(FakeScraper(posts), analyzer, db)

        run(uc.execute(["THYAO"]))
        agg = db.aggregates[0]
        # social_score = -1.0*1.0 = -1.0 ; combined = 0.6*0.5 + 0.4*(-1.0) = 0.3 - 0.4 = -0.1
        assert agg["social_score"] == pytest.approx(-1.0, abs=1e-4)
        assert agg["combined_score"] == pytest.approx(-0.1, abs=1e-4)

    def test_analysis_failure_skipped(self):
        posts = [SocialPost(platform=PLATFORM_TWITTER, ticker="THYAO", text="x",
                            posted_at=datetime(2026, 6, 10))]
        db = FakeDB()
        uc = CollectSocialSentimentUseCase(FakeScraper(posts), FakeAnalyzer({}), db)
        result = run(uc.execute(["THYAO"]))
        assert result["analyzed"] == 0
        assert db.aggregates == []
