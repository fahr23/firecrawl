"""
Point and batch reads for kinds that so far only served history
(provider-wait-list §7 C6): corporate_actions, events, dividends,
earnings_calendar, classification (instrument kinds), macro and index
(series kinds), plus footnotes / fund_holdings, which have no verified source
yet (FA-14 / FA-15 spikes) and answer an honest `unavailable`, not a 404.

A point read is the newest history item at or before `as_of`, so the point
envelope reuses exactly the fields the history endpoint already serves.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import date, datetime, timezone
from typing import Any, Callable, Dict, List, Optional

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field

from api.dependencies import get_db_manager
from api.routers import external_analysis as ea
from database.db_manager import DatabaseManager
from domain.entities.external_analysis import CONTRACT_VERSION, Market

logger = logging.getLogger(__name__)

router = APIRouter(tags=["external-analysis"])

_ENVELOPE_1_1_FIELDS = ("published_at", "available_at", "period_end", "fetched_at", "revision_id", "field_status")
_MAX_PAGES = 10  # bounds the as_of scan for repos without a date filter


@dataclass(frozen=True)
class _Kind:
    repo: Callable[[DatabaseManager], Any]
    provider: str
    source: str
    date_filter: bool  # whether repo.get_history accepts date_from/date_to


_INSTRUMENT_KINDS: Dict[str, _Kind] = {
    "corporate_actions": _Kind(ea._corporate_action_repo, "turkish-financial-api", "isyatirim-web+kap", True),
    "events": _Kind(ea._event_repo, "kap-scraper", "kap", True),
    "dividends": _Kind(ea._dividend_repo, "kap-scraper", "kap", False),
    "earnings_calendar": _Kind(ea._earnings_calendar_repo, "kap-scraper", "kap", False),
    "classification": _Kind(ea._classification_repo, "turkish-financial-api", "kap", False),
}

_UNSOURCED_KINDS: Dict[str, str] = {
    "footnotes": "No verified source for footnote disclosures yet (FA-14 spike).",
    "fund_holdings": "No verified source for fund holdings yet (FA-15 spike).",
}


def _parse_ts(value: Any) -> Optional[datetime]:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    if isinstance(value, date):
        return datetime(value.year, value.month, value.day, tzinfo=timezone.utc)
    text = str(value).strip().replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        try:
            parsed = datetime.fromisoformat(text[:10])
        except ValueError:
            return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def _freshness(as_of: Any) -> int:
    ts = _parse_ts(as_of)
    if ts is None:
        return 0
    return max(0, int((datetime.now(timezone.utc) - ts).total_seconds()))


def _unavailable(kind: str, instrument: str, market: str, provider: str, source: str,
                 version: str, detail: Optional[str] = None) -> Dict[str, Any]:
    env: Dict[str, Any] = {
        "contract_version": version, "instrument": instrument, "market": market, "kind": kind,
        "as_of": None, "provider": provider, "source": source,
        "freshness_seconds": 0, "status": "unavailable", "payload": None,
    }
    if detail:
        env["detail"] = detail
    return env


def _envelope(kind: str, instrument: str, market: str, provider: str, source: str,
              version: str, item: Dict[str, Any]) -> Dict[str, Any]:
    env: Dict[str, Any] = {
        "contract_version": version, "instrument": instrument, "market": market, "kind": kind,
        "as_of": item.get("as_of"), "provider": provider, "source": source,
        "freshness_seconds": _freshness(item.get("as_of")),
        "status": item.get("status") or "ok", "payload": item.get("payload"),
    }
    if version != "1.0":
        env.update({k: item[k] for k in _ENVELOPE_1_1_FIELDS if k in item})
    return env


def _latest_at_or_before(fetch_page: Callable[[Optional[str]], Dict[str, Any]],
                         as_of: Optional[str]) -> Optional[Dict[str, Any]]:
    """Newest item with as_of <= the requested cutoff (pages are newest first)."""
    cutoff = _parse_ts(as_of)
    cursor: Optional[str] = None
    for _ in range(_MAX_PAGES):
        page = fetch_page(cursor)
        for item in page.get("items") or []:
            ts = _parse_ts(item.get("as_of"))
            if cutoff is None or (ts is not None and ts <= cutoff):
                return item
        cursor = page.get("next_cursor")
        if not cursor:
            return None
    return None


def _instrument_point(kind: str, instrument: str, market: str, as_of: Optional[str],
                      version: str, db: DatabaseManager) -> Dict[str, Any]:
    spec = _INSTRUMENT_KINDS[kind]
    repo = spec.repo(db)
    if spec.date_filter:
        fetch = lambda cur: repo.get_history(instrument, market, None, as_of, 100, cur, contract_version=version)
    else:
        fetch = lambda cur: repo.get_history(instrument, market, 100, cur, contract_version=version)
    item = _latest_at_or_before(fetch, as_of)
    if item is None:
        return _unavailable(kind, instrument, market, spec.provider, spec.source, version)
    return _envelope(kind, instrument, market, spec.provider, spec.source, version, item)


def _macro_point(series: str, as_of: Optional[str], version: str, db: DatabaseManager) -> Dict[str, Any]:
    repo = ea._macro_repo(db)
    item = _latest_at_or_before(
        lambda cur: repo.get_history(series, None, as_of, 100, cur, contract_version=version), as_of,
    )
    code = series.strip().upper()
    if item is None:
        return _unavailable("macro", code, "tr", "tcmb-evds", "evds", version)
    return _envelope("macro", code, "tr", "tcmb-evds", "evds", version, item)


def _index_point(code: str, version: str) -> Dict[str, Any]:
    index_code = code.strip().upper()
    detail = (
        "No verified İş Yatırım (or other) data source for index-level history yet."
        if index_code in ea._SUPPORTED_INDEX_CODES
        else f"Unsupported index code '{index_code}'."
    )
    return _unavailable("index", index_code, "bist", "turkish-financial-api", "unknown", version, detail)


class InstrumentBatch(BaseModel):
    market: Market
    instruments: List[str] = Field(..., min_length=1, max_length=100)
    as_of: Optional[str] = None
    contract_version: str = CONTRACT_VERSION


class SeriesBatch(BaseModel):
    market: str = "tr"
    instruments: List[str] = Field(..., min_length=1, max_length=100)
    as_of: Optional[str] = None
    contract_version: str = CONTRACT_VERSION


def _guarded(build: Callable[[], Dict[str, Any]], what: str):
    try:
        return build()
    except DatabaseManager.PoolExhaustedError:
        return ea._db_error("database temporarily unavailable")
    except Exception as e:  # noqa: BLE001
        logger.error(f"{what} failed: {e}", exc_info=True)
        return ea._db_error(str(e))


# ── batch routes first: static "/batch" must win over "/{instrument}" ─────────
def _register_instrument_kind(kind: str) -> None:
    @router.post(f"/{kind}/batch", name=f"{kind}_batch")
    async def batch(request: InstrumentBatch, db: DatabaseManager = Depends(get_db_manager)):
        version = ea._resolve_contract_version(request.contract_version)
        return _guarded(lambda: {
            "contract_version": version,
            "items": [_instrument_point(kind, i, request.market.value, request.as_of, version, db)
                      for i in request.instruments],
        }, f"{kind} batch")

    @router.get(f"/{kind}/{{instrument}}", name=f"{kind}_point")
    async def point(instrument: str, market: Market = Query(...), as_of: Optional[str] = Query(None),
                    contract_version: str = Query(CONTRACT_VERSION),
                    db: DatabaseManager = Depends(get_db_manager)):
        version = ea._resolve_contract_version(contract_version)
        return _guarded(lambda: _instrument_point(kind, instrument, market.value, as_of, version, db),
                        f"{kind} point")


for _kind in _INSTRUMENT_KINDS:
    _register_instrument_kind(_kind)


@router.post("/macro/batch")
async def macro_batch(request: SeriesBatch, db: DatabaseManager = Depends(get_db_manager)):
    version = ea._resolve_contract_version(request.contract_version)
    return _guarded(lambda: {
        "contract_version": version,
        "items": [_macro_point(s, request.as_of, version, db) for s in request.instruments],
    }, "macro batch")


@router.get("/macro/{series}")
async def macro_point(series: str, market: str = Query("tr"), as_of: Optional[str] = Query(None),
                      contract_version: str = Query(CONTRACT_VERSION),
                      db: DatabaseManager = Depends(get_db_manager)):
    version = ea._resolve_contract_version(contract_version)
    return _guarded(lambda: _macro_point(series, as_of, version, db), "macro point")


@router.post("/index/batch")
async def index_batch(request: SeriesBatch):
    version = ea._resolve_contract_version(request.contract_version)
    return {"contract_version": version, "items": [_index_point(c, version) for c in request.instruments]}


@router.get("/index/{code}")
async def index_point(code: str, market: str = Query("bist"), as_of: Optional[str] = Query(None),
                      contract_version: str = Query(CONTRACT_VERSION)):
    return _index_point(code, ea._resolve_contract_version(contract_version))


def _register_unsourced_kind(kind: str, detail: str) -> None:
    @router.post(f"/{kind}/batch", name=f"{kind}_batch")
    async def batch(request: InstrumentBatch):
        version = ea._resolve_contract_version(request.contract_version)
        return {"contract_version": version, "items": [
            _unavailable(kind, i, request.market.value, "turkish-financial-api", "unknown", version, detail)
            for i in request.instruments
        ]}

    @router.get(f"/{kind}/{{instrument}}/history", name=f"{kind}_history")
    async def history(instrument: str, market: Market = Query(...),
                      contract_version: str = Query(CONTRACT_VERSION)):
        return {
            "contract_version": ea._resolve_contract_version(contract_version),
            "instrument": instrument, "market": market.value, "kind": kind,
            "items": [], "next_cursor": None, "status": "unavailable", "detail": detail,
        }

    @router.get(f"/{kind}/{{instrument}}", name=f"{kind}_point")
    async def point(instrument: str, market: Market = Query(...),
                    contract_version: str = Query(CONTRACT_VERSION)):
        return _unavailable(kind, instrument, market.value, "turkish-financial-api", "unknown",
                            ea._resolve_contract_version(contract_version), detail)


for _kind, _detail in _UNSOURCED_KINDS.items():
    _register_unsourced_kind(_kind, _detail)
