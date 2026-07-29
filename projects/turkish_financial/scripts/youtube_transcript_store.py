#!/usr/bin/env python3
"""Small container-side cache/store bridge for native YouTube transcription.

This runs *inside* ``turkish-financial-api`` through ``docker compose exec``.
The macOS collector keeps browser cookies, audio, and the Whisper process on the
host; this bridge only receives final text through stdin and writes it to the
existing PostgreSQL database.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import sys
from datetime import datetime
from typing import Any

from config import config
from database.db_manager import DatabaseManager


def _timestamp(value: Any) -> datetime | None:
    if not value:
        return None
    if isinstance(value, datetime):
        return value
    return datetime.fromisoformat(str(value).replace("Z", "+00:00"))


def _read_payload() -> dict[str, Any]:
    payload = json.load(sys.stdin)
    if not isinstance(payload, dict):
        raise ValueError("expected a JSON object")
    if not str(payload.get("video_id") or "").strip():
        raise ValueError("video_id is required")
    return payload


def _store(db: DatabaseManager, payload: dict[str, Any]) -> dict[str, Any]:
    transcript = str(payload.get("transcript") or "").strip()
    status = "ready" if transcript else "retry_later"
    method = str(payload.get("transcript_method") or "unavailable").strip()
    if status == "ready" and method not in {"caption", "whisper"}:
        raise ValueError("successful transcripts must use caption or whisper")

    row = {
        "video_id": str(payload["video_id"]).strip(),
        "channel": str(payload.get("channel") or "").strip(),
        "title": str(payload.get("title") or "").strip(),
        "url": str(payload.get("url") or "").strip(),
        "transcript": transcript or None,
        "transcript_method": method,
        "transcript_status": status,
        "transcript_attempted_at": datetime.utcnow(),
        "published_at": _timestamp(payload.get("published_at")),
        "duration": payload.get("duration"),
        "lang": str(payload.get("lang") or "tr").strip() or "tr",
    }
    database_id = db.upsert_youtube_video(row)
    if database_id is None:
        raise RuntimeError("database upsert failed")
    return {
        "video_id": row["video_id"],
        "database_id": database_id,
        "status": status,
        "method": method,
    }


async def _analyze_stored(db: DatabaseManager, days_back: int) -> dict[str, Any]:
    """Score cached host transcripts without issuing any YouTube request."""
    from api.routers.news_sentiment import _build_sentiment_analyzer
    from application.use_cases.collect_youtube_sentiment_use_case import CollectYouTubeSentimentUseCase

    class StoredOnlyScraper:
        async def scrape_all(self, **_kwargs):
            return {"success": True, "total": 0, "by_channel": {}, "videos": []}

    use_case = CollectYouTubeSentimentUseCase(StoredOnlyScraper(), _build_sentiment_analyzer(), db)
    return await use_case.execute([], days_back=days_back, stored_only=True)


def main() -> int:
    parser = argparse.ArgumentParser(description="Store native YouTube transcript results")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--cache", metavar="VIDEO_ID", help="return cache state for one video")
    group.add_argument("--ingest", action="store_true", help="read one transcript result as JSON from stdin")
    group.add_argument("--channels", action="store_true", help="return configured YouTube channels")
    group.add_argument("--analyze-stored", action="store_true", help="score saved local transcripts without YouTube network access")
    parser.add_argument("--days-back", type=int, default=7, choices=range(1, 91))
    args = parser.parse_args()

    if args.channels:
        print(json.dumps({"channels": config.youtube.channels}))
        return 0

    db = DatabaseManager()
    if args.cache:
        print(json.dumps(db.get_youtube_transcript_cache(args.cache)))
        return 0

    if args.analyze_stored:
        print(json.dumps(asyncio.run(_analyze_stored(db, args.days_back))))
        return 0

    print(json.dumps(_store(db, _read_payload())))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
