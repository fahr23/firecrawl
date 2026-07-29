"""
YouTube video entity — finance channel content for ticker sentiment.

A `YouTubeVideo` represents one video scraped from a Turkish finance YouTube channel.
Unlike `SocialPost` (always one ticker per post), a video transcript typically discusses
*multiple* BIST instruments; instrument detection and per-ticker windowing are handled
here so the use-case layer can score each ticker independently.

Mirrors the shape and conventions of [[social-post]] and [[news-article]].
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional


PLATFORM_YOUTUBE = "youtube"


@dataclass
class YouTubeVideo:
    """One video from a Turkish finance YouTube channel."""

    channel: str            # canonical channel URL or handle, e.g. "@bistyatirimcipsikolojisi"
    video_id: str           # YouTube 11-char video id (stable primary key)
    title: str
    url: str                # https://www.youtube.com/watch?v=<video_id>
    transcript: str         # joined caption text; empty string when captions are unavailable
    published_at: Optional[datetime] = None
    duration: Optional[int] = None   # seconds
    lang: Optional[str] = None       # e.g. "tr", "en"
    transcript_method: Optional[str] = None  # caption | whisper
    transcript_status: Optional[str] = None  # ready | retry_later
    transcript_attempted_at: Optional[datetime] = None
    scraped_at: datetime = field(default_factory=datetime.utcnow)

    def __post_init__(self) -> None:
        self.video_id = self.video_id.strip()
        self.title = (self.title or "").strip()
        self.channel = (self.channel or "").strip()
        if not self.url:
            self.url = f"https://www.youtube.com/watch?v={self.video_id}"

    # ── analysis helpers ──────────────────────────────────────────────────────

    def text_for_analysis(self) -> str:
        """Full text fed to the sentiment analyzer when no ticker windowing is done."""
        if self.transcript:
            return f"{self.title}\n\n{self.transcript}"
        return self.title

    def tickers_text_window(self, ticker_patterns: List[str], context_sentences: int = 3) -> str:
        """
        Extract the subset of the transcript that mentions any of `ticker_patterns`.

        Splits the transcript into sentences, finds every sentence that contains at least
        one pattern (case-insensitive), and returns those sentences plus `context_sentences`
        neighbours on each side. Falls back to the full `text_for_analysis()` when no
        sentences match — ensuring the LLM always gets some content to score.
        """
        if not self.transcript or not ticker_patterns:
            return self.text_for_analysis()

        sentences = re.split(r'(?<=[.!?])\s+', self.transcript)
        lower_patterns = [p.lower() for p in ticker_patterns]
        lower_sentences = [s.lower() for s in sentences]

        hit_indices: list[int] = []
        for i, ls in enumerate(lower_sentences):
            if any(p in ls for p in lower_patterns):
                hit_indices.append(i)

        if not hit_indices:
            return self.text_for_analysis()

        # expand hits with context window
        include: set[int] = set()
        for idx in hit_indices:
            for j in range(max(0, idx - context_sentences),
                           min(len(sentences), idx + context_sentences + 1)):
                include.add(j)

        window = " ".join(sentences[i] for i in sorted(include))
        return f"{self.title}\n\n{window}"

    # ── persistence helpers ───────────────────────────────────────────────────

    def to_db_row(self) -> Dict[str, Any]:
        """Shape for DatabaseManager.upsert_youtube_video()."""
        return {
            "video_id": self.video_id,
            "channel": self.channel,
            "title": self.title,
            "url": self.url,
            "transcript": self.transcript or None,
            "published_at": self.published_at,
            "duration": self.duration,
            "lang": self.lang,
            "transcript_method": self.transcript_method,
            "transcript_status": self.transcript_status,
            "transcript_attempted_at": self.transcript_attempted_at,
        }
