#!/usr/bin/env python3
"""Native macOS YouTube-to-text collector for the local finance project.

It deliberately has one job at a time and no service process:
public YouTube channel -> cached caption -> local whisper.cpp -> PostgreSQL.
Run this on the Mac host, not inside Docker.
"""
from __future__ import annotations

import argparse
import html
import json
import re
import shutil
import subprocess
import sys
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

SCRIPTS_DIR = Path(__file__).resolve().parent
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

from youtube_sources import load_local_sources

PROJECT_DIR = Path(__file__).resolve().parents[1]
# On macOS this is ``<repo>/projects/turkish_financial``; tests import the
# script from the container mount at ``/app``. Keep imports portable while the
# actual collector still runs on the host and uses the repository root for
# ``docker compose`` commands.
WORKSPACE_DIR = PROJECT_DIR.parents[1] if len(PROJECT_DIR.parents) > 1 else PROJECT_DIR
VIDEO_ID_RE = re.compile(r"^[A-Za-z0-9_-]{6,20}$")
TIMESTAMP_RE = re.compile(r"^\d{2}:\d{2}:\d{2}[.,]\d{3}\s+-->")
TAG_RE = re.compile(r"<[^>]+>")
VTT_CUE_RE = re.compile(r"<\d{2}:\d{2}:\d{2}[.,]\d{3}>")
LOCAL_SOURCES_PATH = PROJECT_DIR / ".local/youtube-sources.json"


def run(command: list[str], *, input_text: str | None = None) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        command,
        cwd=WORKSPACE_DIR,
        input=input_text,
        text=True,
        capture_output=True,
        check=False,
    )


def bridge(args: list[str], *, input_text: str | None = None) -> dict[str, Any]:
    result = run(
        ["docker", "compose", "exec", "-T", "turkish-financial-api", "python",
         "-m", "scripts.youtube_transcript_store", *args],
        input_text=input_text,
    )
    if result.returncode:
        raise RuntimeError(result.stderr.strip() or "finance database bridge failed")
    try:
        return json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        raise RuntimeError("finance database bridge returned invalid JSON") from exc


def parse_vtt(content: str) -> str:
    """Turn a VTT subtitle file into deduplicated readable text."""
    lines: list[str] = []
    previous = ""
    for raw in content.splitlines():
        line = raw.strip()
        if not line or line == "WEBVTT" or line.startswith(("NOTE", "Kind:", "Language:")):
            continue
        if TIMESTAMP_RE.match(line) or line.isdigit():
            continue
        line = html.unescape(VTT_CUE_RE.sub("", TAG_RE.sub("", line))).strip()
        if line and line != previous:
            lines.append(line)
            previous = line
    return " ".join(lines)


def date_from_entry(entry: dict[str, Any]) -> datetime | None:
    raw = str(entry.get("upload_date") or "")
    if len(raw) != 8 or not raw.isdigit():
        return None
    try:
        return datetime.strptime(raw, "%Y%m%d").replace(tzinfo=timezone.utc)
    except ValueError:
        return None


def list_channel_videos(channel: str, limit: int, days_back: int, cookie_args: list[str]) -> list[dict[str, Any]]:
    result = run([
        "yt-dlp", "--flat-playlist", "--dump-single-json", "--playlist-end", str(limit),
        *cookie_args, channel.rstrip("/") + "/videos",
    ])
    if result.returncode:
        print(f"[channel failed] {channel}: {result.stderr.strip()}", file=sys.stderr)
        return []
    try:
        entries = json.loads(result.stdout).get("entries") or []
    except (json.JSONDecodeError, AttributeError):
        return []
    cutoff = datetime.now(timezone.utc) - timedelta(days=days_back)
    videos: list[dict[str, Any]] = []
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        video_id = str(entry.get("id") or "")
        if not VIDEO_ID_RE.match(video_id):
            continue
        published_at = date_from_entry(entry)
        if published_at and published_at < cutoff:
            continue
        videos.append({
            "video_id": video_id,
            "channel": channel,
            "title": str(entry.get("title") or ""),
            "url": f"https://www.youtube.com/watch?v={video_id}",
            "published_at": published_at.isoformat() if published_at else None,
            "duration": entry.get("duration"),
        })
    return videos


def download_caption(video: dict[str, Any], directory: Path, cookie_args: list[str]) -> str | None:
    output = str(directory / "%(id)s.%(ext)s")
    result = run([
        "yt-dlp", "--skip-download", "--write-subs", "--write-auto-subs",
        "--sub-langs", "tr", "--sub-format", "vtt", *cookie_args,
        "-o", output, video["url"],
    ])
    subtitle_files = list(directory.glob(f"{video['video_id']}*.vtt"))
    for subtitle in subtitle_files:
        text = parse_vtt(subtitle.read_text(encoding="utf-8", errors="replace"))
        if len(text) >= 40:
            return text
    if result.returncode:
        print(f"[captions unavailable] {video['video_id']}", file=sys.stderr)
    return None


def whisper_text_output_path(output_prefix: Path) -> Path:
    """Return the exact text filename emitted by whisper-cli for ``-of``."""
    return Path(f"{output_prefix}.txt")


def transcribe_audio(
    video: dict[str, Any], directory: Path, cookie_args: list[str], whisper_bin: str, whisper_model: str,
) -> str | None:
    audio_template = str(directory / "%(id)s.%(ext)s")
    audio_result = run([
        "yt-dlp", "--no-playlist", "-f", "bestaudio/best", "-x", "--audio-format", "wav",
        "--postprocessor-args", "ffmpeg:-ar 16000 -ac 1", *cookie_args,
        "-o", audio_template, video["url"],
    ])
    audio_files = list(directory.glob(f"{video['video_id']}*.wav"))
    if audio_result.returncode or not audio_files:
        return None
    output_prefix = directory / f"{video['video_id']}.transcript"
    whisper_result = run([
        whisper_bin, "-m", whisper_model, "-f", str(audio_files[0]), "-l", "tr", "-t", "4",
        "-otxt", "-of", str(output_prefix),
    ])
    # ``whisper-cli -of <prefix> -otxt`` appends ``.txt`` to the exact
    # prefix.  Keep the deliberate ``.transcript`` part so its output cannot
    # be mistaken for the downloaded audio or subtitle files.
    output_file = whisper_text_output_path(output_prefix)
    if whisper_result.returncode or not output_file.exists():
        print(f"[whisper failed] {video['video_id']}: {whisper_result.stderr.strip()}", file=sys.stderr)
        return None
    text = output_file.read_text(encoding="utf-8", errors="replace").strip()
    return text if len(text) >= 40 else None


def requirements_ok(whisper_bin: str, whisper_model: str) -> bool:
    missing = [name for name in ("docker", "yt-dlp", "ffmpeg") if not shutil.which(name)]
    if not Path(whisper_bin).is_file():
        missing.append(f"whisper-cli ({whisper_bin})")
    if not Path(whisper_model).is_file():
        missing.append(f"small model ({whisper_model})")
    if missing:
        print("Missing: " + ", ".join(missing), file=sys.stderr)
        return False
    return True


def main() -> int:
    parser = argparse.ArgumentParser(description="Transcribe only new YouTube finance videos on this Mac")
    parser.add_argument("--channel", action="append", default=[], help="channel URL; repeat to override configured channels")
    parser.add_argument("--days-back", type=int, default=7, choices=range(1, 91))
    parser.add_argument("--limit-per-channel", type=int, default=20, choices=range(1, 101))
    parser.add_argument("--cookies-from-browser", metavar="BROWSER", help="optional yt-dlp browser cookie source, e.g. chrome")
    parser.add_argument("--whisper-bin", default=str(PROJECT_DIR / ".local/whisper.cpp/build/bin/whisper-cli"))
    parser.add_argument("--whisper-model", default=str(PROJECT_DIR / ".local/whisper.cpp/models/ggml-small.bin"))
    args = parser.parse_args()

    if not requirements_ok(args.whisper_bin, args.whisper_model):
        return 2
    cookie_args = ["--cookies-from-browser", args.cookies_from_browser] if args.cookies_from_browser else []
    local_sources = load_local_sources(LOCAL_SOURCES_PATH)
    channels = args.channel or local_sources or bridge(["--channels"]).get("channels", [])
    if not channels:
        print("No YouTube channels are configured.", file=sys.stderr)
        return 2

    processed = cached = deferred = failed = 0
    for channel in channels:
        for video in list_channel_videos(channel, args.limit_per_channel, args.days_back, cookie_args):
            cache = bridge(["--cache", video["video_id"]])
            if cache.get("ready"):
                cached += 1
                continue
            if cache.get("retry_later"):
                deferred += 1
                continue

            with tempfile.TemporaryDirectory(prefix="turkish-finance-youtube-") as temp:
                directory = Path(temp)
                text = download_caption(video, directory, cookie_args)
                method = "caption"
                if not text:
                    text = transcribe_audio(video, directory, cookie_args, args.whisper_bin, args.whisper_model)
                    method = "whisper"
                payload = {**video, "transcript": text or "", "transcript_method": method if text else "unavailable", "lang": "tr"}
                bridge(["--ingest"], input_text=json.dumps(payload))
                if text:
                    processed += 1
                    print(f"[stored:{method}] {video['video_id']} {video['title']}")
                else:
                    failed += 1
                    print(f"[retry in 24h] {video['video_id']} {video['title']}", file=sys.stderr)

    try:
        analysis = bridge(["--analyze-stored", "--days-back", str(args.days_back)])
    except RuntimeError as exc:
        # Transcription succeeded even if scoring is temporarily unavailable;
        # leave the durable text cache intact so this operation can be retried.
        analysis = {"error": "stored transcript scoring unavailable"}
        print(f"[analysis unavailable] {exc}", file=sys.stderr)

    print(json.dumps({
        "stored": processed,
        "cached": cached,
        "deferred": deferred,
        "failed": failed,
        "analysis": {
            key: analysis[key]
            for key in ("cached_transcripts", "analyzed", "saved", "aggregated_tickers")
            if key in analysis
        },
    }))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
