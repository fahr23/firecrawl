"""
Unit tests for CollectYouTubeSentimentUseCase.

Pure-unit: scraper, sentiment analyzer, and DB are all stubbed. Verifies:
  - Multi-ticker detection per video feeds individual sentiment runs
  - Per-ticker daily aggregate = mean(score × confidence)
  - Three-way blend math (news + social + youtube)
  - One bad video / one bad ticker does not abort the run
  - Videos with no detected tickers are skipped gracefully
"""
import asyncio
from collections import defaultdict
from datetime import date, datetime
from typing import Any, Dict, List, Optional

import pytest

from application.use_cases.collect_youtube_sentiment_use_case import (
    CollectYouTubeSentimentUseCase,
)
from application.use_cases.collect_social_sentiment_use_case import blend_sources
from domain.entities.youtube_video import YouTubeVideo
from domain.value_objects.sentiment import (
    Confidence,
    ImpactHorizon,
    SentimentAnalysis,
    SentimentType,
)


# ── helpers ────────────────────────────────────────────────────────────────────

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


def _video(video_id: str, transcript: str, published: Optional[date] = None) -> YouTubeVideo:
    return YouTubeVideo(
        channel="https://www.youtube.com/@test/videos",
        video_id=video_id,
        title=f"Video {video_id}",
        url=f"https://www.youtube.com/watch?v={video_id}",
        transcript=transcript,
        published_at=datetime.combine(published or date(2026, 6, 10), datetime.min.time()),
    )


# ── fakes ──────────────────────────────────────────────────────────────────────

class FakeScraper:
    def __init__(self, videos: List[YouTubeVideo]):
        self._videos = videos
        self.calls = 0

    async def scrape_all(self, channel_urls, days_back=7, limit_per_channel=50):
        self.calls += 1
        return {
            "success": True,
            "total": len(self._videos),
            "by_channel": {"https://www.youtube.com/@test/videos": len(self._videos)},
            "videos": self._videos,
        }


class FakeAnalyzer:
    def __init__(self, mapping: Dict[str, SentimentAnalysis]):
        # mapping: text-substring -> SentimentAnalysis
        self._mapping = mapping
        self.calls = 0
        self.fail_on: set = set()

    async def analyze(self, content, custom_prompt=None):
        self.calls += 1
        if content in self.fail_on:
            raise RuntimeError("simulated failure")
        for key, sent in self._mapping.items():
            if key in content:
                return sent
        return _sentiment(SentimentType.NEUTRAL, 0.5)


class FakeDB:
    def __init__(self, existing: Optional[Dict] = None, stored_transcripts: Optional[List[Dict]] = None):
        self._existing = existing or {}
        self._stored_transcripts = stored_transcripts or []
        self.videos: List[Dict] = []
        self.sentiments: List[Dict] = []
        self.aggregates: List[Dict] = []
        self._video_id_counter = 1

    def upsert_youtube_video(self, data: Dict[str, Any]) -> int:
        self.videos.append(data)
        pk = self._video_id_counter
        self._video_id_counter += 1
        return pk

    def list_ready_youtube_transcripts(self, days_back: int):
        return self._stored_transcripts

    def upsert_youtube_video_sentiment(self, video_db_id: int, ticker: str,
                                        data: Dict[str, Any]) -> bool:
        self.sentiments.append({"video_db_id": video_db_id, "ticker": ticker, **data})
        return True

    def get_aggregated_ticker_sentiment(self, ticker: str, period_date) -> Optional[Dict]:
        return self._existing.get((ticker, period_date))

    def upsert_aggregated_ticker_sentiment(self, data: Dict[str, Any]) -> bool:
        self.aggregates.append(data)
        return True


# ── tests ──────────────────────────────────────────────────────────────────────

class TestCollectYouTubeSentimentUseCase:

    def test_single_video_single_ticker(self):
        """One video mentioning one ticker produces one sentiment + one aggregate row."""
        videos = [_video("aaa", "Akbank bu çeyrekte güçlü büyüme kaydetti.")]
        analyzer = FakeAnalyzer({"Akbank": _sentiment(SentimentType.POSITIVE, 0.8)})
        db = FakeDB()

        uc = CollectYouTubeSentimentUseCase(FakeScraper(videos), analyzer, db)
        result = run(uc.execute(channel_urls=[], days_back=7))

        assert result["scraped"] == 1
        assert result["analyzed"] >= 1
        assert result["saved"] >= 1
        assert result["aggregated_tickers"] >= 1
        assert len(db.aggregates) >= 1

    def test_multi_ticker_per_video(self):
        """
        Transcript mentioning AKBNK + GARAN → two sentiment calls, two sentiment rows,
        two aggregate entries (one per ticker).
        """
        transcript = (
            "Akbank son çeyrekte rekor kar açıkladı. "
            "Garanti Bankası ise temettü dağıtımını artırdı."
        )
        videos = [_video("bbb", transcript)]
        analyzer = FakeAnalyzer({
            "Akbank": _sentiment(SentimentType.POSITIVE, 0.9),
            "Garanti": _sentiment(SentimentType.POSITIVE, 0.7),
        })
        db = FakeDB()

        uc = CollectYouTubeSentimentUseCase(FakeScraper(videos), analyzer, db)
        result = run(uc.execute(channel_urls=[], days_back=7))

        tickers_aggregated = {row["ticker"] for row in db.aggregates}
        assert "AKBNK" in tickers_aggregated
        assert "GARAN" in tickers_aggregated
        assert result["aggregated_tickers"] == 2

    def test_aggregate_is_mean_of_score_times_confidence(self):
        """Two positive videos for same ticker/day: aggregate = mean(score×conf)."""
        videos = [
            _video("c1", "Akbank güçlü büyüme kaydetti.", date(2026, 6, 10)),
            _video("c2", "Akbank rekor kar açıkladı.", date(2026, 6, 10)),
        ]
        analyzer = FakeAnalyzer({
            "güçlü": _sentiment(SentimentType.POSITIVE, 0.8),
            "rekor":  _sentiment(SentimentType.POSITIVE, 0.6),
        })
        db = FakeDB()

        uc = CollectYouTubeSentimentUseCase(FakeScraper(videos), analyzer, db)
        run(uc.execute(channel_urls=[], days_back=7))

        # both are positive → score = confidence (from SentimentType.POSITIVE.to_score)
        # mean(0.8*0.8, 0.6*0.6) = mean(0.64, 0.36) = 0.5
        akbnk_rows = [r for r in db.aggregates if r["ticker"] == "AKBNK"]
        assert len(akbnk_rows) == 1
        assert akbnk_rows[0]["youtube_score"] == pytest.approx(0.5, abs=1e-3)

    def test_three_way_blend_includes_existing_news_and_social(self):
        """
        When news_score and social_score already exist, combined_score
        is a three-way blend (not just youtube alone).
        """
        videos = [_video("d1", "Akbank iyi performans.")]
        analyzer = FakeAnalyzer({"Akbank": _sentiment(SentimentType.POSITIVE, 1.0)})
        existing = {
            ("AKBNK", date(2026, 6, 10)): {"news_score": 0.5, "social_score": 0.3}
        }
        db = FakeDB(existing=existing)

        uc = CollectYouTubeSentimentUseCase(FakeScraper(videos), analyzer, db)
        run(uc.execute(channel_urls=[], days_back=7))

        agg = db.aggregates[0]
        # youtube_score = 1.0 (positive × confidence 1.0)
        expected = blend_sources({"news": 0.5, "social": 0.3, "youtube": 1.0})
        assert agg["combined_score"] == pytest.approx(expected, abs=1e-4)

    def test_video_with_no_tickers_is_skipped(self):
        """Video whose transcript has no BIST mentions produces no aggregates."""
        videos = [_video("e1", "Bugün hava çok güzel ve güneşli.")]
        analyzer = FakeAnalyzer({})
        db = FakeDB()

        uc = CollectYouTubeSentimentUseCase(FakeScraper(videos), analyzer, db)
        result = run(uc.execute(channel_urls=[], days_back=7))

        assert result["analyzed"] == 0
        assert result["aggregated_tickers"] == 0

    def test_stored_whisper_transcript_is_scored_without_youtube_network_fetch(self):
        stored = [{
            "video_id": "local1",
            "channel": "https://www.youtube.com/@local-finance",
            "title": "Akbank değerlendirmesi",
            "url": "https://www.youtube.com/watch?v=local1",
            "transcript": "Akbank güçlü büyüme ve karlılık açıkladı.",
            "published_at": datetime(2026, 6, 10),
            "duration": 300,
            "lang": "tr",
            "transcript_method": "whisper",
        }]
        db = FakeDB(stored_transcripts=stored)
        scraper = FakeScraper([])
        analyzer = FakeAnalyzer({"Akbank": _sentiment(SentimentType.POSITIVE, 0.8)})

        result = run(CollectYouTubeSentimentUseCase(scraper, analyzer, db).execute(
            channel_urls=[], days_back=7, stored_only=True,
        ))

        assert scraper.calls == 0
        assert result["cached_transcripts"] == 1
        assert result["analyzed"] == 1
        assert {row["ticker"] for row in db.aggregates} == {"AKBNK"}

    def test_bad_ticker_analysis_does_not_abort_run(self):
        """Analyzer failure on one ticker should not prevent other tickers from being processed."""
        transcript = "Akbank ve Garanti bugün güçlü performans sergiledi."
        videos = [_video("f1", transcript)]

        analyzer = FakeAnalyzer({
            "Akbank": _sentiment(SentimentType.POSITIVE, 0.8),
            "Garanti": _sentiment(SentimentType.POSITIVE, 0.7),
        })
        # make AKBNK's text window trigger a failure
        analyzer.fail_on.add("Akbank")

        db = FakeDB()
        uc = CollectYouTubeSentimentUseCase(FakeScraper(videos), analyzer, db)
        result = run(uc.execute(channel_urls=[], days_back=7))

        # GARAN should still be processed
        tickers = {r["ticker"] for r in db.aggregates}
        assert "GARAN" in tickers
        assert result["success"] is True


class TestBlendSources:
    def test_news_only(self):
        assert blend_sources({"news": 0.6}) == pytest.approx(0.6, abs=1e-4)

    def test_social_only(self):
        assert blend_sources({"social": 0.4}) == pytest.approx(0.4, abs=1e-4)

    def test_youtube_only(self):
        assert blend_sources({"youtube": 0.8}) == pytest.approx(0.8, abs=1e-4)

    def test_news_social_preserves_60_40(self):
        """news+social with no youtube must match the old 0.6/0.4 weights exactly."""
        result = blend_sources({"news": 1.0, "social": 0.0})
        expected = 0.6 * 1.0 + 0.4 * 0.0  # = 0.6
        assert result == pytest.approx(expected, abs=1e-6)

    def test_all_none_returns_none(self):
        assert blend_sources({"news": None, "social": None, "youtube": None}) is None

    def test_three_sources(self):
        result = blend_sources({"news": 1.0, "social": 1.0, "youtube": 1.0})
        assert result == pytest.approx(1.0, abs=1e-4)
