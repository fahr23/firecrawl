"""
Instrument identity mapping — Data Contract v1.0 §0.

Our platform addresses everything by `instrument` + `market` (e.g. THYAO/bist). The
KAP data we store keys by Turkish `company_name`, with no stock code on the disclosure
rows. This module resolves an `instrument` + `market` to the `company_name` patterns
used to query our database.

Resolution order (best → fallback):
  1. exact `stock_code` column on `kap_disclosures` (populated by newer scrapes)
  2. the `bist_companies` table (code → name), when available
  3. the static map below — the explicit fallback the contract allows us to own

This provider only carries **BIST** KAP disclosures; `usa` / `coin` markets resolve to
nothing and the endpoints return an honest `unavailable` envelope.
"""
from __future__ import annotations

import logging
import csv
import os
import re
from pathlib import Path
from typing import List, Optional

logger = logging.getLogger(__name__)


# Hand-maintained aliases supplement the complete catalogue loaded below.  Turkish
# company names in KAP vary (legal suffixes, accents), so common names retain their
# shorter and ASCII spellings for robust disclosure and transcript matching.
_BIST_NAME_ALIASES: dict[str, List[str]] = {
    "THYAO": ["türk hava yolları", "turk hava yollari"],
    "AKBNK": ["akbank"],
    "GARAN": ["garanti"],
    "ISCTR": ["iş bankası", "is bankasi", "türkiye iş bankası"],
    "YKBNK": ["yapı ve kredi", "yapi ve kredi", "yapı kredi"],
    "HALKB": ["halk bankası", "halkbank"],
    "VAKBN": ["vakıflar bankası", "vakifbank", "vakıfbank"],
    "EREGL": ["ereğli demir", "eregli demir", "erdemir"],
    "KCHOL": ["koç holding", "koc holding"],
    "SAHOL": ["sabancı holding", "sabanci holding", "hacı ömer sabancı"],
    "BIMAS": ["bim birleşik", "bim birlesik", "bim mağaza"],
    "ASELS": ["aselsan"],
    "TUPRS": ["tüpraş", "tupras"],
    "SISE": ["türkiye şişe", "turkiye sise", "şişecam", "sisecam"],
    "PETKM": ["petkim"],
    "TCELL": ["turkcell"],
    "TTKOM": ["türk telekom", "turk telekom"],
    "FROTO": ["ford otosan"],
    "TOASO": ["tofaş", "tofas"],
    "ARCLK": ["arçelik", "arcelik"],
    "PGSUS": ["pegasus"],
    "KOZAL": ["koza altın", "koza altin"],
    "KOZAA": ["koza anadolu"],
    "ENKAI": ["enka inşaat", "enka insaat"],
    "TKFEN": ["tekfen"],
    "SASA": ["sasa polyester"],
    "HEKTS": ["hektaş", "hektas"],
    "GUBRF": ["gübre fabrikaları", "gubre fabrikalari"],
    "VESTL": ["vestel"],
    "DOHOL": ["doğan holding", "dogan holding"],
}

_BIST_DISPLAY_FALLBACK: dict[str, str] = {
    "THYAO": "Türk Hava Yolları", "AKBNK": "Akbank", "GARAN": "Garanti BBVA",
    "ISCTR": "Türkiye İş Bankası", "YKBNK": "Yapı ve Kredi Bankası",
    "HALKB": "Halkbank", "VAKBN": "VakıfBank", "EREGL": "Ereğli Demir ve Çelik",
    "KCHOL": "Koç Holding", "SAHOL": "Sabancı Holding", "BIMAS": "BİM",
    "ASELS": "Aselsan", "TUPRS": "Tüpraş", "SISE": "Şişecam", "PETKM": "Petkim",
    "TCELL": "Turkcell", "TTKOM": "Türk Telekom", "FROTO": "Ford Otosan",
    "TOASO": "Tofaş", "ARCLK": "Arçelik", "PGSUS": "Pegasus", "KOZAL": "Koza Altın",
    "KOZAA": "Koza Anadolu", "ENKAI": "Enka İnşaat", "TKFEN": "Tekfen",
    "SASA": "Sasa Polyester", "HEKTS": "Hektaş", "GUBRF": "Gübre Fabrikaları",
    "VESTL": "Vestel", "DOHOL": "Doğan Holding",
}


def _catalog_paths() -> List[Path]:
    """Return catalogue locations for Compose, local development, and tests."""
    configured = os.getenv("BIST_CATALOG_PATH", "").strip()
    paths = [Path(configured)] if configured else []
    # Compose mounts the shared, versioned catalogue here.  The repository-relative
    # path keeps direct local execution working without an environment variable.
    paths.extend([
        Path("/data/bist_tum.csv"),
        Path(__file__).resolve().parents[3] / "bist_companies" / "BIST TÜM.csv",
    ])
    return paths


def _load_static_bist_catalog() -> dict[str, str]:
    """Load every current symbol from the versioned BIST CSV snapshot.

    The CSV's first field can contain more than one Yahoo-style symbol (for example
    ``A1CAP, ACP.IS``).  Only symbols ending in ``.IS`` are BIST instruments.
    """
    for path in _catalog_paths():
        try:
            with path.open("r", encoding="utf-8", newline="") as source:
                catalogue: dict[str, str] = {}
                for row in csv.DictReader(source):
                    name = (row.get("Name") or "").strip()
                    for code in re.findall(r"\b([A-Z0-9]{3,10})(?=\.IS\b)", row.get("Code.IS") or ""):
                        if name:
                            catalogue[code] = name
                if catalogue:
                    logger.info("Loaded %d BIST instruments from %s", len(catalogue), path)
                    return catalogue
        except OSError:
            continue
        except (csv.Error, UnicodeError) as exc:
            logger.warning("BIST catalogue %s could not be read: %s", path, exc)

    logger.warning("BIST catalogue file unavailable; using the minimal built-in fallback")
    return dict(_BIST_DISPLAY_FALLBACK)


# Complete versioned fallback catalogue.  The database is authoritative once seeded;
# this map makes first startup and text detection cover every symbol in the snapshot.
STATIC_BIST_CATALOG: dict[str, str] = _load_static_bist_catalog()
# Preserve shorter UI labels only for symbols in the active BIST TÜM snapshot.
# Do not accidentally re-add a delisted or non-equity instrument from an old alias.
for _code, _name in _BIST_DISPLAY_FALLBACK.items():
    if _code in STATIC_BIST_CATALOG:
        STATIC_BIST_CATALOG[_code] = _name

# STATIC_BIST_MAP intentionally covers every catalogue ticker.  Names from the
# catalogue provide a safe default phrase, while aliases add KAP/transcript variants.
STATIC_BIST_MAP: dict[str, List[str]] = {
    code: [name, *_BIST_NAME_ALIASES.get(code, [])]
    for code, name in STATIC_BIST_CATALOG.items()
}

_BIST = "bist"


# Ticker → KAP `mkkMemberOid`. The financialTable API addresses companies by this
# MKK member OID, not by ticker, so we must resolve it before calling
# `listCompanyExcelMembers/{oid}/{year}/{term}`. This static seed is the fallback;
# the authoritative source is the `mkk_member_oid` column on `bist_companies`
# (populated by KAPScraper.refresh_member_oids). Extend freely — additive only.
STATIC_MEMBER_OID_MAP: dict[str, str] = {
    "ASELS": "4028e4a1413b7ef401413bc2251e0047",
}


def detect_instruments(text: str) -> List[str]:
    """
    Detect all BIST tickers mentioned in `text`.

    Two-pass scan:
      1. Uppercase \bTICKER\b regex match (handles captions that preserve the code).
      2. Company-name substring match (lowercased), using STATIC_BIST_MAP patterns.
         Primary for YouTube auto-captions which are mostly lowercase.

    Returns de-duplicated list in detection order.
    """
    import re

    found: list[str] = []
    seen: set[str] = set()

    def _add(ticker: str) -> None:
        if ticker not in seen:
            seen.add(ticker)
            found.append(ticker)

    # Pass 1: explicit uppercase ticker tokens in the original text
    for ticker in STATIC_BIST_MAP:
        if re.search(rf"\b{re.escape(ticker)}\b", text):
            _add(ticker)

    # Pass 2: company-name substrings (case-insensitive)
    lower = text.lower()
    for ticker, patterns in STATIC_BIST_MAP.items():
        for pattern in patterns:
            if pattern.lower() in lower:
                _add(ticker)
                break

    return found


def _normalize_instrument(instrument: str) -> str:
    return (instrument or "").strip().upper()


def resolve_member_oid(instrument: str, market: str = _BIST, db_manager=None) -> Optional[str]:
    """
    Resolve an instrument to its KAP `mkkMemberOid`.

    Order: `bist_companies.mkk_member_oid` (authoritative when populated) → static
    seed map. Returns None for unsupported markets or unknown tickers (caller then
    skips the company / emits an honest `unavailable`).
    """
    if not supports_market(market):
        return None
    code = _normalize_instrument(instrument)
    if not code:
        return None

    if db_manager is not None:
        try:
            rows = db_manager.query(
                "SELECT mkk_member_oid FROM bist_companies "
                "WHERE UPPER(code) = %s AND mkk_member_oid IS NOT NULL",
                (code,),
            )
            for row in rows:
                oid = (row.get("mkk_member_oid") or "").strip()
                if oid:
                    return oid
        except Exception as e:  # pragma: no cover - DB optional
            logger.debug(f"mkk_member_oid lookup failed for {code}: {e}")

    return STATIC_MEMBER_OID_MAP.get(code)


def supports_market(market: str) -> bool:
    """This provider only carries BIST KAP disclosures."""
    return (market or "").strip().lower() == _BIST


def static_name_patterns(instrument: str, market: str) -> Optional[List[str]]:
    """Return static company_name ILIKE patterns for the instrument, or None."""
    if not supports_market(market):
        return None
    return STATIC_BIST_MAP.get(_normalize_instrument(instrument))


def resolve_name_patterns(
    instrument: str,
    market: str,
    db_manager=None,
) -> List[str]:
    """
    Resolve an instrument to a list of company_name ILIKE patterns.

    Tries the `bist_companies` table first (authoritative when populated), then falls
    back to the static map, then to the bare instrument itself (so a company_name that
    literally contains the ticker still matches). Returns an empty list for unsupported
    markets or genuinely unknown instruments.
    """
    if not supports_market(market):
        return []

    code = _normalize_instrument(instrument)
    patterns: List[str] = []

    # 1. bist_companies table (code → name), if the DB is reachable.
    if db_manager is not None:
        try:
            rows = db_manager.query(
                "SELECT name FROM bist_companies WHERE UPPER(code) = %s",
                (code,),
            )
            for row in rows:
                name = (row.get("name") or "").strip()
                if name:
                    patterns.append(name)
        except Exception as e:  # pragma: no cover - defensive, DB optional
            logger.debug(f"bist_companies lookup failed for {code}: {e}")

    # 2. static fallback map.
    static = STATIC_BIST_MAP.get(code)
    if static:
        patterns.extend(static)

    # 3. last resort: match the ticker itself inside company_name.
    if not patterns and code:
        patterns.append(code)

    # de-duplicate while preserving order
    seen: set[str] = set()
    deduped: List[str] = []
    for p in patterns:
        key = p.lower()
        if key not in seen:
            seen.add(key)
            deduped.append(p)
    return deduped
