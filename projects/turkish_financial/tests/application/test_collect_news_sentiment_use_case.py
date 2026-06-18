"""
Unit tests for CollectNewsSentimentUseCase.

Pure-unit: the scraper, sentiment analyzer and DB are all stubbed. We verify the
orchestration: every article is analysed and persisted, and the per-ticker daily
aggregate is the mean of (score × confidence).
"""
import asyncio
from datetime import datetime

import pytest

from application.use_cases.collect_news_sentiment_use_case import (
    CollectNewsSentimentUseCase,
)
from domain.entities.news_article import NewsArticle
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
    def __init__(self, articles):
        self._articles = articles

    async def scrape_all(self, tickers=None, days_back=7, sources=None,
                         include_investing_comments=True):
        return {"success": True, "total": len(self._articles),
                "by_source": {"bloomberght": len(self._articles)},
                "articles": self._articles}


class FakeAnalyzer:
    def __init__(self, mapping):
        # mapping: headline substring -> SentimentAnalysis
        self._mapping = mapping
        self.calls = 0

    async def analyze(self, content, custom_prompt=None):
        self.calls += 1
        for key, sent in self._mapping.items():
            if key in content:
                return sent
        return None


class FakeDB:
    def __init__(self):
        self.articles = []
        self.sentiments = []
        self.aggregates = []
        self._id = 0

    def upsert_news_article(self, data):
        self._id += 1
        self.articles.append(data)
        return self._id

    def upsert_news_article_sentiment(self, article_pk, data):
        self.sentiments.append((article_pk, data))
        return True

    def upsert_aggregated_ticker_sentiment(self, data):
        self.aggregates.append(data)
        return True

    def get_aggregated_ticker_sentiment(self, ticker, period_date):
        return None  # no pre-existing social side in these tests


class TestExecute:
    def test_analyzes_and_persists_each_article(self):
        articles = [
            NewsArticle(source="bloomberght", headline="THYAO güçlü", url="a",
                        ticker="THYAO", published_at=datetime(2026, 6, 10)),
            NewsArticle(source="bloomberght", headline="AKBNK zayıf", url="b",
                        ticker="AKBNK", published_at=datetime(2026, 6, 10)),
        ]
        analyzer = FakeAnalyzer({
            "THYAO": _sentiment(SentimentType.POSITIVE, 0.8),
            "AKBNK": _sentiment(SentimentType.NEGATIVE, 0.6),
        })
        db = FakeDB()
        uc = CollectNewsSentimentUseCase(FakeScraper(articles), analyzer, db)

        result = run(uc.execute(days_back=7))

        assert result["analyzed"] == 2
        assert result["saved"] == 2
        assert len(db.articles) == 2
        assert len(db.sentiments) == 2

    def test_aggregate_is_mean_of_score_times_confidence(self):
        # Two positive THYAO articles same day: scores 0.8 and 0.6 confidence
        # contribution = (+0.8*0.8 + 0.6*0.6)/2 = (0.64+0.36)/2 = 0.5
        articles = [
            NewsArticle(source="bloomberght", headline="THYAO haber bir", url="a",
                        ticker="THYAO", published_at=datetime(2026, 6, 10)),
            NewsArticle(source="bloomberght", headline="THYAO haber iki", url="b",
                        ticker="THYAO", published_at=datetime(2026, 6, 10)),
        ]
        analyzer = FakeAnalyzer({
            "bir": _sentiment(SentimentType.POSITIVE, 0.8),
            "iki": _sentiment(SentimentType.POSITIVE, 0.6),
        })
        db = FakeDB()
        uc = CollectNewsSentimentUseCase(FakeScraper(articles), analyzer, db)

        run(uc.execute())

        assert len(db.aggregates) == 1
        agg = db.aggregates[0]
        assert agg["ticker"] == "THYAO"
        assert agg["news_count"] == 2
        assert agg["news_score"] == pytest.approx(0.5, abs=1e-4)
        assert agg["combined_score"] == agg["news_score"]

    def test_untagged_articles_not_aggregated(self):
        articles = [
            NewsArticle(source="bloomberght", headline="Makro haber", url="a",
                        ticker=None, published_at=datetime(2026, 6, 10)),
        ]
        analyzer = FakeAnalyzer({"Makro": _sentiment(SentimentType.NEUTRAL, 0.5)})
        db = FakeDB()
        uc = CollectNewsSentimentUseCase(FakeScraper(articles), analyzer, db)

        result = run(uc.execute())
        assert result["analyzed"] == 1
        assert result["saved"] == 1
        assert db.aggregates == []  # no ticker → no aggregate

    def test_analysis_failure_is_skipped(self):
        articles = [
            NewsArticle(source="bloomberght", headline="THYAO haber", url="a",
                        ticker="THYAO", published_at=datetime(2026, 6, 10)),
        ]
        analyzer = FakeAnalyzer({})  # returns None for everything
        db = FakeDB()
        uc = CollectNewsSentimentUseCase(FakeScraper(articles), analyzer, db)

        result = run(uc.execute())
        assert result["analyzed"] == 0
        assert result["saved"] == 0
        assert db.aggregates == []
