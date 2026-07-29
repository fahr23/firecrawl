"""Local, user-managed YouTube sources for native Mac transcription."""
from __future__ import annotations

import json
from pathlib import Path
from urllib.parse import urlparse


MAX_SOURCES = 25


def normalize_channel_source(value: object) -> str:
    """Accept only public YouTube channel URLs, without query-string tracking."""
    source = str(value or "").strip().rstrip("/")
    parsed = urlparse(source)
    if parsed.scheme != "https" or parsed.netloc.lower() not in {"youtube.com", "www.youtube.com"}:
        raise ValueError("Use a public https://www.youtube.com/@channel or /channel/ URL.")
    path = parsed.path.rstrip("/")
    if path.endswith("/videos"):
        path = path[:-7]
    prefixes = ("/@", "/channel/", "/c/", "/user/")
    if (not path.startswith(prefixes) or path in prefixes or parsed.params or parsed.query or parsed.fragment):
        raise ValueError("Use a YouTube channel URL, not a video, playlist, or search URL.")
    return f"https://www.youtube.com{path}"


def load_local_sources(path: Path) -> list[str] | None:
    """Return the local override; ``None`` means use the project configuration."""
    if not path.exists():
        return None
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError("The local YouTube source list is invalid.") from exc
    if not isinstance(value, list):
        raise ValueError("The local YouTube source list is invalid.")
    return list(dict.fromkeys(normalize_channel_source(item) for item in value))


def save_local_sources(path: Path, sources: list[str]) -> list[str]:
    normalized = list(dict.fromkeys(normalize_channel_source(item) for item in sources))
    if not normalized:
        raise ValueError("Keep at least one YouTube source.")
    if len(normalized) > MAX_SOURCES:
        raise ValueError(f"Add at most {MAX_SOURCES} YouTube sources.")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(normalized, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return normalized
