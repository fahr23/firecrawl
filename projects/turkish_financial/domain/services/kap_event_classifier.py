"""
KAP event classifier — FA-07 §4 "events" kind.

Maps a raw `kap_disclosures` row (title/content + subject_code/disclosure_type)
onto the FA-07 normalized `event_type` taxonomy:

    bonus_issue | rights_issue | cash_dividend | share_buyback | insider_trade |
    major_holder_change | financial_report | special_situation | other

No KAP endpoint publishes this taxonomy directly, so classification is primarily
keyword matching over the Turkish disclosure title/content — the same proven
approach `scrapers.kap_financial_parser` uses for statement labels — with
`subject_code` (KAP's own disclosure-class code, e.g. "FR", "ÖZKD") as a
secondary, lower-priority signal. An unmatched disclosure classifies as
`other`, never a guess at a more specific type (§3.4 honest absence).

Pure function, no I/O: cheap to unit-test, and callers own persistence.
"""
from __future__ import annotations

import re
import unicodedata
from typing import Any, Dict, Optional

MAPPING_VERSION = "1"

_EVENT_TYPES = (
    "bonus_issue",
    "rights_issue",
    "cash_dividend",
    "share_buyback",
    "insider_trade",
    "major_holder_change",
    "financial_report",
    "special_situation",
    "other",
)


def _fold(text: Optional[str]) -> str:
    text = (text or "").strip().lower()
    text = text.replace("ı", "i").replace("İ", "i").replace("ş", "s").replace(
        "ğ", "g"
    ).replace("ü", "u").replace("ö", "o").replace("ç", "c")
    text = unicodedata.normalize("NFKD", text)
    text = "".join(c for c in text if not unicodedata.combining(c))
    return re.sub(r"\s+", " ", text).strip()


# Ordered (event_type, [keyword patterns]) — first match wins. More specific
# patterns are listed before broader ones (e.g. "bedelsiz" bonus issue before
# the generic "sermaye artirimi" capital-increase phrase that both share).
_TITLE_PATTERNS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("bonus_issue", ("bedelsiz sermaye artirimi", "bedelsiz pay", "bedelsiz artirim")),
    ("rights_issue", ("bedelli sermaye artirimi", "bedelli pay", "rusanli sermaye artirimi", "rusanli pay")),
    ("cash_dividend", ("kar payi odemesi", "temettu odemesi", "nakit kar payi", "kar dagitimi")),
    ("share_buyback", ("pay geri alim", "geri alinan pay", "geri alim programi")),
    ("insider_trade", ("icerden ogrenenler", "yonetici islemleri", "pay alim satim bildirimi")),
    ("major_holder_change", ("ortaklik yapisi degisikligi", "sermaye payi degisikligi", "pay sahipligi degisikligi", "oy hakki degisikligi")),
    ("financial_report", ("finansal rapor", "finansal tablolar", "ara donem faaliyet raporu")),
)

# subject_code is KAP's own disclosure-class code (not a stable public taxonomy
# for our purposes), used only as a fallback when title text does not match —
# "FR" reliably means financial report, "ÖZKD" is a catch-all special-situation
# class that still needs the title check above to find a more specific type.
_SUBJECT_CODE_FALLBACK: dict[str, str] = {
    "FR": "financial_report",
}


def classify(disclosure: Dict[str, Any]) -> Dict[str, Any]:
    """
    Classify one `kap_disclosures` row into an FA-07 event.

    Args:
        disclosure: a mapping with (at least) `title`/`content`, `subject`,
            `subject_code`, `disclosure_type`, `disclosure_id`/`disclosure_index`,
            `disclosure_date`, `timestamp`.

    Returns: ``{event_type, mapping_version, source_disclosure_index, title,
    published_at, available_at}``. `event_type` is always one of the FA-07
    taxonomy values; unmatched disclosures classify as "other", not a guess.
    """
    title = disclosure.get("title") or disclosure.get("content") or disclosure.get("kapTitle") or ""
    subject = disclosure.get("subject") or ""
    folded = _fold(f"{title} {subject}")

    event_type = "other"
    for candidate, patterns in _TITLE_PATTERNS:
        if any(pattern in folded for pattern in patterns):
            event_type = candidate
            break
    else:
        subject_code = str(disclosure.get("subject_code") or "").strip().upper()
        if subject_code in _SUBJECT_CODE_FALLBACK:
            event_type = _SUBJECT_CODE_FALLBACK[subject_code]
        elif subject_code == "ÖZKD":
            event_type = "special_situation"

    published_at = disclosure.get("disclosure_date") or disclosure.get("published_at")
    source_index = disclosure.get("disclosure_id") or disclosure.get("disclosure_index")

    return {
        "event_type": event_type,
        "mapping_version": MAPPING_VERSION,
        "source_disclosure_index": str(source_index) if source_index is not None else None,
        "title": title or None,
        "published_at": published_at,
        # available_at left for the caller (needs session-calendar logic); not
        # derivable from the disclosure row alone.
        "available_at": None,
    }
