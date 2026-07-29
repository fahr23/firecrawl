import importlib.util
import json
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch


SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"


def _load(name: str):
    spec = importlib.util.spec_from_file_location(name, SCRIPTS / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module


def test_vtt_parser_removes_timestamps_tags_and_repeated_cues():
    collector = _load("youtube_to_text")
    source = """WEBVTT

00:00:00.000 --> 00:00:01.000
<c>Akbank güçlü</c>

00:00:01.000 --> 00:00:02.000
Akbank güçlü

00:00:02.000 --> 00:00:03.000
büyüme kaydetti
"""
    assert collector.parse_vtt(source) == "Akbank güçlü büyüme kaydetti"


def test_entry_date_parses_youtube_upload_date_in_utc():
    collector = _load("youtube_to_text")
    assert collector.date_from_entry({"upload_date": "20260728"}) == datetime(2026, 7, 28, tzinfo=timezone.utc)
    assert collector.date_from_entry({"upload_date": "invalid"}) is None


def test_whisper_text_output_keeps_the_full_prefix_suffix():
    collector = _load("youtube_to_text")
    prefix = Path("/tmp/video-id.transcript")

    # whisper-cli appends the selected format to ``-of``; Path.with_suffix()
    # would incorrectly turn this into ``video-id.txt``.
    assert collector.whisper_text_output_path(prefix) == Path("/tmp/video-id.transcript.txt")


def test_store_marks_text_as_ready_and_empty_text_for_retry(monkeypatch):
    store = _load("youtube_transcript_store")

    class FakeDB:
        def __init__(self):
            self.rows = []

        def upsert_youtube_video(self, row):
            self.rows.append(row)
            return len(self.rows)

    db = FakeDB()
    ready = store._store(db, {
        "video_id": "abc123def45", "transcript": "Finans metni", "transcript_method": "whisper",
    })
    retry = store._store(db, {"video_id": "def456ghi78", "transcript_method": "unavailable"})

    assert ready["status"] == "ready"
    assert db.rows[0]["transcript_status"] == "ready"
    assert retry["status"] == "retry_later"
    assert db.rows[1]["transcript_status"] == "retry_later"


def test_local_runner_rejects_unknown_browser_cookie_source():
    runner = _load("youtube_runner_server")
    started, payload = runner.RunnerState().start("unknown-browser")

    assert not started
    assert "Unsupported browser" in payload["detail"]


def test_local_runner_reads_only_the_final_collection_summary(tmp_path, monkeypatch):
    runner = _load("youtube_runner_server")
    log_path = tmp_path / "youtube-runner.log"
    log_path.write_text(
        "some private yt-dlp detail\n"
        '{"stored": 2, "cached": 5, "deferred": 1, "failed": 0}\n',
        encoding="utf-8",
    )
    monkeypatch.setattr(runner, "LOG_PATH", log_path)

    assert runner.last_collection_summary() == {"stored": 2, "cached": 5, "deferred": 1, "failed": 0}


def test_local_runner_exposes_stored_transcript_analysis_counts(tmp_path, monkeypatch):
    runner = _load("youtube_runner_server")
    log_path = tmp_path / "youtube-runner.log"
    log_path.write_text(
        '{"stored": 1, "cached": 2, "deferred": 0, "failed": 0, '
        '"analysis": {"cached_transcripts": 3, "analyzed": 2, "saved": 2, "aggregated_tickers": 1}}\n',
        encoding="utf-8",
    )
    monkeypatch.setattr(runner, "LOG_PATH", log_path)

    assert runner.last_collection_summary()["analysis"] == {
        "cached_transcripts": 3, "analyzed": 2, "saved": 2, "aggregated_tickers": 1,
    }


def test_local_source_override_normalizes_a_channel_url(tmp_path):
    sources = _load("youtube_sources")
    source_file = tmp_path / "youtube-sources.json"

    saved = sources.save_local_sources(
        source_file, ["https://www.youtube.com/@kanalfinans/videos"],
    )

    assert saved == ["https://www.youtube.com/@kanalfinans"]
    assert sources.load_local_sources(source_file) == saved


def test_local_source_override_rejects_a_video_url(tmp_path):
    sources = _load("youtube_sources")

    try:
        sources.save_local_sources(tmp_path / "youtube-sources.json", ["https://www.youtube.com/watch?v=abc123def45"])
    except ValueError as exc:
        assert "channel URL" in str(exc)
    else:
        raise AssertionError("video URLs must not be accepted as channel sources")


def test_local_runner_stop_sends_sigterm_to_the_collector_group(monkeypatch):
    runner = _load("youtube_runner_server")

    class Process:
        pid = 4242

        @staticmethod
        def poll():
            return None

    state = runner.RunnerState()
    state._process = Process()
    killpg = []
    monkeypatch.setattr(runner.os, "killpg", lambda pid, signal: killpg.append((pid, signal)))

    stopped, payload = state.stop()

    assert stopped
    assert payload["stopping"] is True
    assert killpg == [(4242, 15)]
