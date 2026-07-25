"""
YouTube channel scraper — finance channel transcript extraction.

Discovers recent videos from a YouTube channel and fetches their transcript text.
Uses yt-dlp for metadata (video list + exact upload dates) and youtube-transcript-api
for caption text. Both tools require no API key.

I/O-only: sentiment analysis and persistence are handled by
CollectYouTubeSentimentUseCase. This scraper only returns YouTubeVideo objects.

Whisper/audio STT for caption-less videos is a future fallback not implemented here.
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from scrapers.base_scraper import BaseScraper
from domain.entities.youtube_video import YouTubeVideo, PLATFORM_YOUTUBE

try:
    from youtube_transcript_api import YouTubeTranscriptApi
except ImportError:  # pragma: no cover — optional dep; error is logged at call site
    YouTubeTranscriptApi = None  # type: ignore[assignment,misc]

logger = logging.getLogger(__name__)

_YOUTUBE_BASE = "https://www.youtube.com"


class YouTubeScraper(BaseScraper):
    """Scrape YouTube finance channels into YouTubeVideo objects."""

    # ── video discovery ───────────────────────────────────────────────────────

    def list_channel_videos(
        self,
        channel_url: str,
        days_back: int = 7,
        limit: int = 50,
    ) -> List[Dict[str, Any]]:
        """
        Return metadata dicts for the most recent `limit` videos from `channel_url`
        published within the last `days_back` days.

        Uses yt-dlp in flat-playlist mode (no download) so only metadata is fetched.
        Raises ImportError if yt-dlp is not installed.
        """
        import yt_dlp  # imported here so the rest of the project doesn't require it

        cutoff = datetime.now(tz=timezone.utc) - timedelta(days=days_back)

        ydl_opts = {
            "quiet": True,
            "no_warnings": True,
            "extract_flat": "in_playlist",
            "playlistend": limit,
            "ignoreerrors": True,
        }

        # Normalise: ensure /videos suffix so we land on the uploads tab
        url = channel_url.rstrip("/")
        if not url.endswith("/videos"):
            url = url + "/videos"

        videos: List[Dict[str, Any]] = []
        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(url, download=False)
                if not info:
                    logger.warning(f"yt-dlp returned nothing for {url}")
                    return videos
                entries = info.get("entries") or []
                for entry in entries:
                    if not entry:
                        continue
                    upload_str = entry.get("upload_date") or ""  # "YYYYMMDD"
                    upload_dt: Optional[datetime] = None
                    if upload_str and len(upload_str) == 8:
                        try:
                            upload_dt = datetime(
                                int(upload_str[:4]),
                                int(upload_str[4:6]),
                                int(upload_str[6:8]),
                                tzinfo=timezone.utc,
                            )
                        except ValueError:
                            pass
                    if upload_dt and upload_dt < cutoff:
                        continue
                    vid_id = entry.get("id") or entry.get("url") or ""
                    if not vid_id:
                        continue
                    videos.append(
                        {
                            "video_id": vid_id,
                            "title": entry.get("title") or "",
                            "url": f"{_YOUTUBE_BASE}/watch?v={vid_id}",
                            "published_at": upload_dt,
                            "duration": entry.get("duration"),
                            "channel": channel_url,
                        }
                    )
        except Exception as e:
            logger.error(f"yt-dlp error for {url}: {e}", exc_info=True)

        logger.info(f"YouTube channel {channel_url}: {len(videos)} videos in window")
        return videos

    # ── transcript fetch ──────────────────────────────────────────────────────

    def fetch_transcript(
        self,
        video_id: str,
        languages: Optional[List[str]] = None,
    ) -> tuple[Optional[str], Optional[str]]:
        """
        Fetch and join the transcript for `video_id`.

        Returns (text, lang) where `text` is the joined caption string and `lang` is
        the language code. Returns (None, None) when captions are disabled or unavailable
        (logged, not fatal).
        """
        if YouTubeTranscriptApi is None:
            logger.error("youtube-transcript-api is not installed; cannot fetch transcripts")
            return None, None

        preferred = languages or ["tr", "en"]

        try:
            ytt = YouTubeTranscriptApi()
            transcript_list = ytt.list(video_id)

            # Try preferred languages; fall back to any available transcript
            transcript = None
            used_lang = None
            for lang in preferred:
                try:
                    transcript = transcript_list.find_transcript([lang])
                    used_lang = lang
                    break
                except Exception:
                    try:
                        transcript = transcript_list.find_generated_transcript([lang])
                        used_lang = lang
                        break
                    except Exception:
                        continue

            if transcript is None:
                try:
                    available = list(transcript_list)
                    if available:
                        transcript = available[0]
                        used_lang = transcript.language_code
                except Exception:
                    pass

            if transcript is None:
                logger.info(f"No transcript for video {video_id}")
                return None, None

            segments = transcript.fetch()
            # segments is a FetchedTranscript iterable; each item has .text attribute or is dict
            parts = []
            for seg in segments:
                text_val = seg.get("text") if isinstance(seg, dict) else getattr(seg, "text", "")
                if text_val and text_val.strip():
                    parts.append(text_val.strip())
            text = " ".join(parts)
            return text or None, used_lang

        except Exception as e:
            logger.info(f"Transcript unavailable for {video_id}: {e}")
            return None, None

    # ── orchestration ─────────────────────────────────────────────────────────

    async def scrape_all(
        self,
        channel_urls: List[str],
        days_back: int = 7,
        limit_per_channel: int = 50,
    ) -> Dict[str, Any]:
        """
        Collect YouTubeVideo objects from all `channel_urls`.

        Skips videos with no transcript (they carry no text to score). Returns
        {success, total, by_channel, videos}.
        """
        all_videos: List[YouTubeVideo] = []
        by_channel: Dict[str, int] = {}

        for channel_url in channel_urls or []:
            channel_videos: List[YouTubeVideo] = []
            try:
                metas = self.list_channel_videos(channel_url, days_back, limit_per_channel)
                for meta in metas:
                    vid_id = meta["video_id"]
                    try:
                        transcript_text, lang = self.fetch_transcript(vid_id)
                        if not transcript_text:
                            logger.debug(f"Skipping {vid_id}: no transcript")
                            continue
                        channel_videos.append(
                            YouTubeVideo(
                                channel=channel_url,
                                video_id=vid_id,
                                title=meta["title"],
                                url=meta["url"],
                                transcript=transcript_text,
                                published_at=meta.get("published_at"),
                                duration=meta.get("duration"),
                                lang=lang,
                            )
                        )
                    except Exception as e:
                        logger.error(f"Error processing video {vid_id}: {e}", exc_info=True)
            except Exception as e:
                logger.error(f"Channel scrape failed for {channel_url}: {e}", exc_info=True)

            by_channel[channel_url] = len(channel_videos)
            all_videos.extend(channel_videos)

        return {
            "success": True,
            "total": len(all_videos),
            "by_channel": by_channel,
            "videos": all_videos,
        }

    # BaseScraper abstract method
    async def scrape(self, **kwargs) -> Dict[str, Any]:
        """Alias for scrape_all() to satisfy BaseScraper contract."""
        return await self.scrape_all(**kwargs)
