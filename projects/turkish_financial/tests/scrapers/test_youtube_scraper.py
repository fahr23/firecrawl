"""
Unit tests for YouTubeScraper.

Monkeypatches yt-dlp and youtube-transcript-api so no network calls are made.
Verifies: days_back filtering, transcript joining, captions-disabled skip,
channel→video-id mapping, and scrape_all orchestration.
"""
import asyncio
from datetime import date, datetime, timedelta, timezone
from typing import Any, Dict, List, Optional
from unittest.mock import MagicMock, patch

import pytest


def test_default_youtube_configuration_has_multiple_channel_sources():
    from config import Config

    config = Config()
    assert len(config.youtube.channels) >= 4
    assert len(set(config.youtube.channels)) == len(config.youtube.channels)


def test_extra_youtube_channels_are_appended_without_duplicates(monkeypatch):
    from config import Config

    monkeypatch.setenv("YOUTUBE_CHANNELS", "https://www.youtube.com/@primary/videos")
    monkeypatch.setenv(
        "YOUTUBE_EXTRA_CHANNELS",
        "https://www.youtube.com/@secondary/videos,https://www.youtube.com/@primary/videos",
    )

    assert Config().youtube.channels == [
        "https://www.youtube.com/@primary/videos",
        "https://www.youtube.com/@secondary/videos",
    ]

from domain.entities.youtube_video import YouTubeVideo


def run(coro):
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


def _make_entry(video_id: str, upload_date: str, title: str = "Test Video",
                duration: int = 300) -> Dict[str, Any]:
    return {
        "id": video_id,
        "title": title,
        "upload_date": upload_date,
        "duration": duration,
        "url": video_id,
    }


def _mock_yt_dlp_info(entries: List[Dict]) -> Dict:
    return {"entries": entries}


class FakeYtDlp:
    """Simulates yt_dlp.YoutubeDL context manager."""

    def __init__(self, info: Dict):
        self._info = info

    def __enter__(self):
        return self

    def __exit__(self, *args):
        pass

    def extract_info(self, url, download=False):
        return self._info


class FakeTranscript:
    def __init__(self, segments):
        self._segments = segments
        self.language_code = "tr"

    def fetch(self):
        return self._segments


class FakeTranscriptList:
    def __init__(self, segments: Optional[List[Dict]] = None, disabled: bool = False):
        self._segments = segments or []
        self._disabled = disabled

    def find_transcript(self, langs):
        if self._disabled:
            raise Exception("NoTranscriptFound")
        return FakeTranscript(self._segments)

    def find_generated_transcript(self, langs):
        if self._disabled:
            raise Exception("NoTranscriptFound")
        return FakeTranscript(self._segments)

    def __iter__(self):
        if self._disabled:
            return iter([])
        return iter([FakeTranscript(self._segments)])


class TestYouTubeScraperListChannelVideos:

    def _make_scraper(self):
        # Patch BaseScraper.__init__ to avoid Firecrawl requirements
        with patch("scrapers.base_scraper.BaseScraper.__init__", return_value=None):
            from scrapers.youtube_scraper import YouTubeScraper
            scraper = YouTubeScraper.__new__(YouTubeScraper)
            scraper.config = MagicMock()
            scraper.firecrawl = MagicMock()
            scraper.db_manager = None
            return scraper

    def test_returns_videos_within_window(self):
        """Videos outside the days_back window are excluded."""
        scraper = self._make_scraper()
        # Use dates that are clearly inside (1 day ago) and clearly outside (60 days ago)
        # of any reasonable days_back window, so we don't need to freeze time.
        from datetime import date as date_cls

        today = datetime.now(tz=timezone.utc)
        yesterday_str = (today - timedelta(days=1)).strftime("%Y%m%d")
        old_str = (today - timedelta(days=60)).strftime("%Y%m%d")

        entries = [
            _make_entry("vid1", yesterday_str, "Video recente"),
            _make_entry("vid2", old_str, "Video vecchio"),
        ]
        fake_info = _mock_yt_dlp_info(entries)

        with patch("yt_dlp.YoutubeDL", return_value=FakeYtDlp(fake_info)):
            result = scraper.list_channel_videos(
                "https://www.youtube.com/@test/videos",
                days_back=7,
                limit=50,
            )

        assert len(result) == 1
        assert result[0]["video_id"] == "vid1"

    def test_appends_videos_suffix(self):
        """URL without /videos suffix gets it appended."""
        scraper = self._make_scraper()
        captured_urls = []

        class CapturingYtDlp(FakeYtDlp):
            def extract_info(self, url, download=False):
                captured_urls.append(url)
                return _mock_yt_dlp_info([])

        with patch("yt_dlp.YoutubeDL", return_value=CapturingYtDlp({})):
            scraper.list_channel_videos("https://www.youtube.com/@test", days_back=7)

        assert captured_urls[0].endswith("/videos")

    def test_empty_channel_returns_empty_list(self):
        scraper = self._make_scraper()
        with patch("yt_dlp.YoutubeDL", return_value=FakeYtDlp({"entries": []})):
            result = scraper.list_channel_videos("https://www.youtube.com/@test/videos")
        assert result == []


class TestYouTubeScraperFetchTranscript:

    def _make_scraper(self):
        with patch("scrapers.base_scraper.BaseScraper.__init__", return_value=None):
            from scrapers.youtube_scraper import YouTubeScraper
            scraper = YouTubeScraper.__new__(YouTubeScraper)
            scraper.config = MagicMock()
            scraper.firecrawl = MagicMock()
            scraper.db_manager = None
            return scraper

    def _patch_transcript_api(self, fake_list):
        """Patch the module-level YouTubeTranscriptApi so instantiation returns a mock."""
        mock_instance = MagicMock()
        mock_instance.list.return_value = fake_list
        return patch(
            "scrapers.youtube_scraper.YouTubeTranscriptApi",
            return_value=mock_instance,
        )

    def test_joins_segments_into_text(self):
        scraper = self._make_scraper()
        segments = [
            {"text": "Akbank bu çeyrekte"},
            {"text": "güçlü büyüme kaydetti"},
        ]
        fake_list = FakeTranscriptList(segments=segments)

        with self._patch_transcript_api(fake_list):
            text, lang = scraper.fetch_transcript("vid1")

        assert text == "Akbank bu çeyrekte güçlü büyüme kaydetti"

    def test_returns_none_when_captions_disabled(self):
        scraper = self._make_scraper()
        mock_instance = MagicMock()
        mock_instance.list.side_effect = Exception("TranscriptsDisabled: vid1")

        with patch("scrapers.youtube_scraper.YouTubeTranscriptApi", return_value=mock_instance):
            text, lang = scraper.fetch_transcript("vid1")

        assert text is None
        assert lang is None

    def test_skips_empty_segment_text(self):
        scraper = self._make_scraper()
        segments = [{"text": "Türk Hava Yolları"}, {"text": "  "}, {"text": "yükselişte"}]
        fake_list = FakeTranscriptList(segments=segments)

        with self._patch_transcript_api(fake_list):
            text, _ = scraper.fetch_transcript("vid1")

        assert "  " not in text
        assert "Türk Hava Yolları" in text
        assert "yükselişte" in text


class TestYouTubeScraperScrapeAll:

    def _make_scraper(self, videos_returned=None):
        with patch("scrapers.base_scraper.BaseScraper.__init__", return_value=None):
            from scrapers.youtube_scraper import YouTubeScraper
            scraper = YouTubeScraper.__new__(YouTubeScraper)
            scraper.config = MagicMock()
            scraper.firecrawl = MagicMock()
            scraper.db_manager = None
        scraper._videos = videos_returned or []
        return scraper

    def test_skips_videos_without_transcript(self):
        with patch("scrapers.base_scraper.BaseScraper.__init__", return_value=None):
            from scrapers.youtube_scraper import YouTubeScraper
            scraper = YouTubeScraper.__new__(YouTubeScraper)
            scraper.config = MagicMock()
            scraper.firecrawl = MagicMock()
            scraper.db_manager = None

        metas = [
            {"video_id": "v1", "title": "Vid 1", "url": "u1",
             "published_at": None, "duration": None},
        ]
        with patch.object(scraper, "list_channel_videos", return_value=metas):
            with patch.object(scraper, "fetch_transcript", return_value=(None, None)):
                result = run(scraper.scrape_all(["https://channel"], days_back=7))

        assert result["total"] == 0
        assert result["videos"] == []

    def test_returns_by_channel_counts(self):
        with patch("scrapers.base_scraper.BaseScraper.__init__", return_value=None):
            from scrapers.youtube_scraper import YouTubeScraper
            scraper = YouTubeScraper.__new__(YouTubeScraper)
            scraper.config = MagicMock()
            scraper.firecrawl = MagicMock()
            scraper.db_manager = None

        metas = [
            {"video_id": "v1", "title": "Vid 1", "url": "u1",
             "published_at": datetime(2026, 6, 10, tzinfo=timezone.utc), "duration": 100},
            {"video_id": "v2", "title": "Vid 2", "url": "u2",
             "published_at": datetime(2026, 6, 11, tzinfo=timezone.utc), "duration": 200},
        ]
        with patch.object(scraper, "list_channel_videos", return_value=metas):
            with patch.object(scraper, "fetch_transcript",
                              side_effect=[("metin bir", "tr"), ("metin iki", "tr")]):
                result = run(scraper.scrape_all(["https://channel"], days_back=7))

        assert result["total"] == 2
        assert result["by_channel"]["https://channel"] == 2

    def test_uses_cached_local_transcript_without_fetching_captions(self):
        with patch("scrapers.base_scraper.BaseScraper.__init__", return_value=None):
            from scrapers.youtube_scraper import YouTubeScraper
            scraper = YouTubeScraper.__new__(YouTubeScraper)
            scraper.config = MagicMock()
            scraper.firecrawl = MagicMock()
            scraper.db_manager = None

        cached = YouTubeVideo(
            channel="https://www.youtube.com/@local-finance",
            video_id="cached1",
            title="Cached",
            url="https://www.youtube.com/watch?v=cached1",
            transcript="Akbank için yerel Whisper metni.",
        )
        scraper._cached_videos_by_id = {"cached1": cached}
        metas = [{"video_id": "cached1", "title": "Remote", "url": "remote", "published_at": None, "duration": None}]
        with patch.object(scraper, "list_channel_videos", return_value=metas), patch.object(
            scraper, "fetch_transcript", side_effect=AssertionError("network captions must not run")
        ):
            result = run(scraper.scrape_all(["https://channel"], days_back=7))

        assert result["videos"] == [cached]
        assert result["cached"] == 1
