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
from typing import List, Optional

logger = logging.getLogger(__name__)


# Static instrument → company_name ILIKE patterns. Turkish company names in KAP vary
# (legal suffixes, accents), so each ticker maps to one or more substrings we ILIKE on.
# Owned by us per §0; extend freely — additive changes keep contract_version 1.0.
STATIC_BIST_MAP: dict[str, List[str]] = {
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

_BIST = "bist"


# Ticker → KAP `mkkMemberOid`. The financialTable API addresses companies by this
# MKK member OID, not by ticker, so we must resolve it before calling
# `listCompanyExcelMembers/{oid}/{year}/{term}`. This static seed is the fallback;
# the authoritative source is the `mkk_member_oid` column on `bist_companies`
# (populated by KAPScraper.refresh_member_oids). Extend freely — additive only.
STATIC_MEMBER_OID_MAP: dict[str, str] = {
    "ASELS": "4028e4a1413b7ef401413bc2251e0047",
}


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
