#!/usr/bin/env python3
"""Local-only button runner for the native macOS YouTube transcription command.

This server intentionally does not import Whisper or yt-dlp. It runs on
127.0.0.1 only and starts one collector subprocess when the dashboard asks for
it, leaving the model unloaded at every other time.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import threading
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

SCRIPTS_DIR = Path(__file__).resolve().parent
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

from youtube_sources import load_local_sources, normalize_channel_source, save_local_sources

PROJECT_DIR = Path(__file__).resolve().parents[1]
WORKSPACE_DIR = PROJECT_DIR.parents[1] if len(PROJECT_DIR.parents) > 1 else PROJECT_DIR
RUNNER_HOST = "127.0.0.1"
RUNNER_PORT = 8765
ALLOWED_ORIGINS = {
    "http://127.0.0.1:8000",
    "http://localhost:8000",
}
ALLOWED_BROWSERS = {"", "brave", "chrome", "chromium", "edge", "firefox", "safari", "vivaldi"}
WHISPER_BIN = PROJECT_DIR / ".local/whisper.cpp/build/bin/whisper-cli"
WHISPER_MODEL = PROJECT_DIR / ".local/whisper.cpp/models/ggml-small.bin"
COLLECTOR = PROJECT_DIR / "scripts/youtube_to_text.py"
LOG_PATH = PROJECT_DIR / ".local/youtube-runner.log"
LOCAL_SOURCES_PATH = PROJECT_DIR / ".local/youtube-sources.json"


def last_collection_summary() -> dict[str, Any] | None:
    """Read the collector's final compact result without exposing its full log."""
    try:
        lines = LOG_PATH.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return None
    for line in reversed(lines):
        try:
            result = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(result, dict) and {"stored", "cached", "deferred", "failed"} <= result.keys():
            summary: dict[str, Any] = {
                key: int(result[key]) for key in ("stored", "cached", "deferred", "failed")
            }
            analysis = result.get("analysis")
            if isinstance(analysis, dict):
                summary["analysis"] = {
                    key: int(analysis[key])
                    for key in ("cached_transcripts", "analyzed", "saved", "aggregated_tickers")
                    if key in analysis
                }
            return summary
    return None


def project_sources() -> list[str]:
    """Read configured sources through the container, keeping the host cache local."""
    local_sources = load_local_sources(LOCAL_SOURCES_PATH)
    if local_sources is not None:
        return local_sources
    result = subprocess.run(
        ["docker", "compose", "exec", "-T", "turkish-financial-api", "python", "-m",
         "scripts.youtube_transcript_store", "--channels"],
        cwd=WORKSPACE_DIR,
        text=True,
        capture_output=True,
        check=False,
    )
    if result.returncode:
        raise RuntimeError("The finance service is unavailable; source settings cannot be read.")
    try:
        channels = json.loads(result.stdout).get("channels", [])
        return [normalize_channel_source(channel) for channel in channels]
    except (AttributeError, json.JSONDecodeError, ValueError) as exc:
        raise RuntimeError("The configured YouTube source list is invalid.") from exc


def source_payload() -> dict[str, Any]:
    return {
        "sources": project_sources(),
        "using_local_override": LOCAL_SOURCES_PATH.exists(),
    }


class RunnerState:
    """Owns exactly one collector subprocess."""

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._process: subprocess.Popen | None = None
        self._last_exit_code: int | None = None
        self._stop_requested = False
        self._last_was_stopped = False

    def status(self) -> dict[str, Any]:
        with self._lock:
            running = self._process is not None and self._process.poll() is None
            if self._process is not None and not running:
                self._last_exit_code = self._process.returncode
                self._process = None
                self._last_was_stopped = self._stop_requested
                self._stop_requested = False
            return {
                "running": running,
                "stopping": running and self._stop_requested,
                "last_was_stopped": self._last_was_stopped,
                "last_exit_code": self._last_exit_code,
                "last_result": None if running else last_collection_summary(),
                "log_path": str(LOG_PATH),
            }

    def start(self, browser: str) -> tuple[bool, dict[str, Any]]:
        browser = browser.strip().lower()
        if browser not in ALLOWED_BROWSERS:
            return False, {"detail": "Unsupported browser cookie source."}
        with self._lock:
            if self._process is not None and self._process.poll() is None:
                return False, {"detail": "A local transcription run is already active."}
            if not WHISPER_BIN.is_file() or not WHISPER_MODEL.is_file():
                return False, {"detail": "Whisper small is not installed. Run the local Whisper installer once."}

            LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
            command = [
                str(COLLECTOR),
                "--whisper-bin", str(WHISPER_BIN),
                "--whisper-model", str(WHISPER_MODEL),
            ]
            if browser:
                command.extend(["--cookies-from-browser", browser])
            environment = os.environ.copy()
            environment["PATH"] = ":".join([
                environment.get("PATH", ""),
                "/opt/homebrew/bin",
                "/usr/local/bin",
                "/usr/bin",
                "/bin",
            ])
            with LOG_PATH.open("a", encoding="utf-8") as log_file:
                log_file.write("\n=== Local YouTube transcription started ===\n")
                self._process = subprocess.Popen(
                    command,
                    cwd=WORKSPACE_DIR,
                    env=environment,
                    stdout=log_file,
                    stderr=subprocess.STDOUT,
                    start_new_session=True,
                )
            self._last_exit_code = None
            self._last_was_stopped = False
            self._stop_requested = False
            return True, self.status()

    def stop(self) -> tuple[bool, dict[str, Any]]:
        with self._lock:
            if self._process is None or self._process.poll() is not None:
                return False, {"detail": "No local transcription is running."}
            self._stop_requested = True
            try:
                os.killpg(self._process.pid, 15)  # SIGTERM ends yt-dlp/Whisper and its children.
            except ProcessLookupError:
                return False, {"detail": "The local transcription has already finished."}
            return True, self.status()


STATE = RunnerState()


class Handler(BaseHTTPRequestHandler):
    server_version = "TurkishFinancialYouTubeRunner/1.0"

    def log_message(self, _format: str, *_args: object) -> None:
        """Do not copy browser requests or cookie-source selections to stdout."""

    def _origin_allowed(self) -> bool:
        origin = self.headers.get("Origin")
        return origin is None or origin in ALLOWED_ORIGINS

    def _send(self, status: HTTPStatus, payload: dict[str, Any]) -> None:
        body = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        origin = self.headers.get("Origin")
        if origin in ALLOWED_ORIGINS:
            self.send_header("Access-Control-Allow-Origin", origin)
            self.send_header("Vary", "Origin")
        self.end_headers()
        self.wfile.write(body)

    def do_OPTIONS(self) -> None:  # noqa: N802
        if not self._origin_allowed():
            self._send(HTTPStatus.FORBIDDEN, {"detail": "Local dashboard origin required."})
            return
        self.send_response(HTTPStatus.NO_CONTENT)
        self.send_header("Access-Control-Allow-Methods", "GET, POST, DELETE, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        origin = self.headers.get("Origin")
        if origin in ALLOWED_ORIGINS:
            self.send_header("Access-Control-Allow-Origin", origin)
            self.send_header("Vary", "Origin")
        self.end_headers()

    def do_GET(self) -> None:  # noqa: N802
        if not self._origin_allowed():
            self._send(HTTPStatus.FORBIDDEN, {"detail": "Local dashboard origin required."})
        elif self.path == "/status":
            self._send(HTTPStatus.OK, STATE.status())
        elif self.path == "/sources":
            try:
                self._send(HTTPStatus.OK, source_payload())
            except (RuntimeError, ValueError) as exc:
                self._send(HTTPStatus.SERVICE_UNAVAILABLE, {"detail": str(exc)})
        else:
            self._send(HTTPStatus.NOT_FOUND, {"detail": "Not found"})

    def _body(self) -> dict[str, Any]:
        length = int(self.headers.get("Content-Length", "0"))
        if length > 4096:
            raise ValueError("request is too large")
        data = json.loads(self.rfile.read(length) or b"{}")
        if not isinstance(data, dict):
            raise ValueError("expected an object")
        return data

    def do_POST(self) -> None:  # noqa: N802
        if not self._origin_allowed():
            self._send(HTTPStatus.FORBIDDEN, {"detail": "Local dashboard origin required."})
            return
        try:
            data = self._body()
        except (ValueError, json.JSONDecodeError):
            self._send(HTTPStatus.BAD_REQUEST, {"detail": "Invalid local runner request."})
            return
        if self.path == "/run":
            started, payload = STATE.start(str(data.get("cookies_from_browser") or ""))
            self._send(HTTPStatus.ACCEPTED if started else HTTPStatus.CONFLICT, payload)
        elif self.path == "/stop":
            stopped, payload = STATE.stop()
            self._send(HTTPStatus.ACCEPTED if stopped else HTTPStatus.CONFLICT, payload)
        elif self.path == "/sources":
            try:
                existing = project_sources()
                source = normalize_channel_source(data.get("channel"))
                if source not in existing:
                    existing.append(source)
                self._send(HTTPStatus.OK, {"sources": save_local_sources(LOCAL_SOURCES_PATH, existing), "using_local_override": True})
            except (RuntimeError, ValueError) as exc:
                self._send(HTTPStatus.BAD_REQUEST, {"detail": str(exc)})
        elif self.path == "/sources/reset":
            try:
                LOCAL_SOURCES_PATH.unlink(missing_ok=True)
                self._send(HTTPStatus.OK, source_payload())
            except (RuntimeError, ValueError, OSError) as exc:
                self._send(HTTPStatus.BAD_REQUEST, {"detail": str(exc)})
        else:
            self._send(HTTPStatus.NOT_FOUND, {"detail": "Not found"})

    def do_DELETE(self) -> None:  # noqa: N802
        if not self._origin_allowed():
            self._send(HTTPStatus.FORBIDDEN, {"detail": "Local dashboard origin required."})
            return
        if urlparse(self.path).path != "/sources":
            self._send(HTTPStatus.NOT_FOUND, {"detail": "Not found"})
            return
        try:
            data = self._body()
            source = normalize_channel_source(data.get("channel"))
            sources = [item for item in project_sources() if item != source]
            self._send(HTTPStatus.OK, {"sources": save_local_sources(LOCAL_SOURCES_PATH, sources), "using_local_override": True})
        except (RuntimeError, ValueError) as exc:
            self._send(HTTPStatus.BAD_REQUEST, {"detail": str(exc)})


def main() -> int:
    server = ThreadingHTTPServer((RUNNER_HOST, RUNNER_PORT), Handler)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        return 0
    finally:
        server.server_close()


if __name__ == "__main__":
    raise SystemExit(main())
