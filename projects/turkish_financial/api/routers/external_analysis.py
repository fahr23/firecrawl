"""
External Analysis Provider — Data Contract v1.0 HTTP surface (§4).

This service is the **sentiment** provider (`provider = "kap-scraper"`). It exposes the
contract endpoints the `strategy_management` consumer pulls from:

    GET  {base}/health
    POST {base}/sentiment/batch
    GET  {base}/sentiment/overview?market=&from=&to=
    GET  {base}/sentiment/{instrument}/history?market=&from=&to=&limit=&cursor=
    GET  {base}/sentiment/{instrument}?market=&as_of=

Mounted at `/api/external/v1` (see api/main.py). On any DB failure we degrade to an
honest error/unavailable envelope — we never fabricate data (§5).
"""
import logging
import os
import asyncio
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import requests
from fastapi import APIRouter, Depends, Query
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from api.dependencies import get_db_manager
from api.off_loop import run_off_loop
from database.db_manager import DatabaseManager
from domain.entities.external_analysis import (
    CONTRACT_VERSION,
    CONTRACT_VERSION_1_0,
    SUPPORTED_CONTRACT_VERSIONS,
    Market,
)
from infrastructure.repositories.external_analysis_repository import (
    PROVIDER_ID,
    ExternalAnalysisRepository,
)
from infrastructure.repositories.fundamental_repository import FundamentalRepository
from infrastructure.repositories.market_repository import MarketRepository
from infrastructure.repositories.ownership_repository import OwnershipRepository
from infrastructure.repositories.event_repository import EventRepository
from infrastructure.repositories.corporate_action_repository import CorporateActionRepository
from infrastructure.repositories.macro_repository import MacroRepository
from infrastructure.repositories.classification_repository import ClassificationRepository
from infrastructure.repositories.earnings_calendar_repository import EarningsCalendarRepository
from infrastructure.repositories.dividend_repository import DividendRepository
from infrastructure.repositories.news_repository import NewsRepository
from infrastructure.contracts.instrument_identity_map import STATIC_BIST_CATALOG
from scrapers.isyatirim_market_data import build_market_history_payload, fetch_market_history
from scrapers.isyatirim_fundamentals import fetch_fundamentals

logger = logging.getLogger(__name__)

router = APIRouter(tags=["external-analysis"])

_fundamental_collection_task = None
_fundamental_collection_state = {"status": "idle", "total": 0, "completed": 0, "fetched": 0, "cached": 0, "failed": 0, "started_at": None, "finished_at": None}

# P1 fix: a cache miss must never await a live scrape inside the request — a
# slow KAP scrape (observed 45s+) blocks the single event loop, so concurrent
# requests (including /health) hang until it finishes and the readiness probe
# fails. Instead we fire the fetch as a detached background task (same
# fire-and-forget idiom as `_fundamental_collection_task` above) and respond
# immediately with the current (possibly still-unavailable) stored state. A
# small in-flight set stops concurrent requests for the same instrument from
# each starting their own redundant scrape.
_on_demand_fetch_in_flight: set[tuple[str, str, str]] = set()


def _spawn_on_demand_fetch(key: tuple[str, str, str], make_coro) -> None:
    """`make_coro` is a zero-arg callable returning the fetch coroutine — not
    the coroutine itself — so a deduped call never constructs one it will
    immediately discard unawaited."""
    if key in _on_demand_fetch_in_flight:
        return
    _on_demand_fetch_in_flight.add(key)

    async def _run():
        try:
            await make_coro()
        except Exception:  # noqa: BLE001 - best-effort, errors already logged by coro
            pass
        finally:
            _on_demand_fetch_in_flight.discard(key)

    asyncio.create_task(_run())


class SentimentBatchRequest(BaseModel):
    """§4 batch body."""

    market: Market
    instruments: List[str] = Field(..., min_length=1)
    as_of: Optional[str] = None


class FundamentalBatchRequest(BaseModel):
    """§4 batch body (fundamental kind)."""

    market: Market
    instruments: List[str] = Field(..., min_length=1)
    as_of: Optional[str] = None
    contract_version: str = CONTRACT_VERSION


class FundamentalsCollectionRequest(BaseModel):
    force: bool = False


def _repo(db_manager: DatabaseManager) -> ExternalAnalysisRepository:
    return ExternalAnalysisRepository(db_manager)


def _fund_repo(db_manager: DatabaseManager) -> FundamentalRepository:
    return FundamentalRepository(db_manager)


def _news_repo(db_manager: DatabaseManager) -> NewsRepository:
    return NewsRepository(db_manager)


def _resolve_contract_version(requested: str) -> str:
    """FA-01 §3: unrecognised versions degrade to the compatible default (1.0)."""
    return requested if requested in SUPPORTED_CONTRACT_VERSIONS else CONTRACT_VERSION


def _db_error(detail: str) -> JSONResponse:
    """Standard §6.7 unavailable body with HTTP 503."""
    return JSONResponse(
        status_code=503,
        content={
            "contract_version": CONTRACT_VERSION,
            "status": "unavailable",
            "error_code": "UPSTREAM_DB_ERROR",
            "detail": detail,
        },
    )


def _firecrawl_capabilities() -> dict:
    """Probe the configured local Firecrawl service without exposing its URL.

    A deliberately unsupported tiny upload is used only to distinguish a missing
    `/v2/parse` route from a working parser endpoint.  No financial document or
    client data is sent during this health-style capability check.
    """
    base_url = os.getenv("FIRECRAWL_BASE_URL", "http://api:3002").rstrip("/")
    try:
        root = requests.get(base_url, timeout=3)
        api_reachable = root.status_code < 500
    except requests.RequestException:
        return {
            "status": "unavailable",
            "operations": [],
            "document_parse": False,
        }

    document_parse = False
    try:
        parse_probe = requests.post(
            f"{base_url}/v2/parse",
            files={"file": ("probe.txt", b"capability probe")},
            timeout=3,
        )
        # The local parser rejects .txt with UNSUPPORTED_FILE_TYPE.  That response
        # proves the route is deployed without processing a real client document.
        document_parse = parse_probe.status_code in {400, 401, 403, 422}
    except requests.RequestException:
        document_parse = False

    operations = ["scrape", "crawl", "map", "batch", "search", "actions"]
    if document_parse:
        operations.append("parse")
    return {
        "status": "ok" if api_reachable else "unavailable",
        "operations": operations if api_reachable else [],
        "document_parse": document_parse,
    }


# P3 fix: `/health` must answer in well under a second even under load. The
# upstream Firecrawl probe is two live HTTP round-trips (up to ~6s worst case),
# so it is never run inline in the request — a background loop refreshes this
# cache on an interval and `/health` only ever reads it.
_firecrawl_capabilities_cache: dict = {"status": "unavailable", "operations": [], "document_parse": False}
_firecrawl_capabilities_refresh_task = None


async def _refresh_firecrawl_capabilities_loop(interval_seconds: int = 30) -> None:
    global _firecrawl_capabilities_cache
    while True:
        try:
            _firecrawl_capabilities_cache = await asyncio.to_thread(_firecrawl_capabilities)
        except Exception as exc:  # noqa: BLE001 - background loop must never die
            logger.warning("firecrawl capabilities refresh failed: %s", exc)
        await asyncio.sleep(interval_seconds)


def start_firecrawl_capabilities_refresh() -> None:
    """Called once from the app's startup event (api/main.py)."""
    global _firecrawl_capabilities_refresh_task
    if _firecrawl_capabilities_refresh_task is None or _firecrawl_capabilities_refresh_task.done():
        _firecrawl_capabilities_refresh_task = asyncio.create_task(_refresh_firecrawl_capabilities_loop())


_NON_BIST_MARKET_TABLE: Dict[str, tuple[str, str]] = {
    "usa": ("yahoo_market_history", "ticker"),
    "coin": ("coingecko_market_history", "coin_id"),
}


async def _non_bist_instruments_catalog(market: Market, db_manager: DatabaseManager) -> dict:
    """usa/coin catalog: whatever instruments already have stored market
    history, since there is no BIST-TÜM-style full-universe source for
    either market. Never a fabricated listing (§3.4)."""
    table, column = _NON_BIST_MARKET_TABLE[market.value]
    try:
        rows = db_manager.query(
            f"SELECT DISTINCT {column} AS ticker FROM {table} ORDER BY {column}", ()
        )
    except Exception as e:
        logger.error(f"instruments_catalog ({market.value}) failed: {e}", exc_info=True)
        return JSONResponse(status_code=503, content={
            "contract_version": CONTRACT_VERSION,
            "status": "unavailable",
            "error_code": "UPSTREAM_DB_ERROR",
            "detail": str(e),
        })
    items = [
        {
            "ticker": r["ticker"].upper() if market.value == "usa" else r["ticker"],
            "company_name": None,
            "sector": None,
            "market": market.value,
            "available_data": ["market"],
            "catalog_source": "database",
        }
        for r in rows
    ]
    return {
        "contract_version": CONTRACT_VERSION,
        "market": market.value,
        "total": len(items),
        "items": items,
    }


# ── instruments catalog — discovery endpoint for clients ─────────────────────
@router.get("/instruments")
async def instruments_catalog(
    market: Market = Query(Market.BIST),
    db_manager: DatabaseManager = Depends(get_db_manager),
):
    """
    Return all instruments that have at least one data type available.

    Each item includes: ticker, company_name, sector, available_data (list of
    which kinds have data: sentiment, fundamental, news_sentiment, combined_sentiment).

    Clients call this first to build a selection list, then call the per-instrument
    endpoints using the returned tickers.

    BIST is backed by the seeded bist_companies/BIST TÜM catalogue. usa/coin have
    no equivalent full-universe source this provider owns, so their catalog is
    honestly limited to whatever instruments already have stored market data —
    never a fabricated "every US stock" / "every coin" listing.
    """
    if market != Market.BIST:
        return await _non_bist_instruments_catalog(market, db_manager)

    try:
        rows = db_manager.query(
            """
            WITH
            has_sentiment AS (
                SELECT DISTINCT stock_code AS ticker FROM kap_disclosure_sentiment s
                JOIN kap_disclosures d ON d.id = s.disclosure_id
            ),
            has_fundamental AS (
                SELECT DISTINCT stock_code AS ticker FROM kap_fundamentals
            ),
            has_news_sentiment AS (
                SELECT DISTINCT ticker FROM aggregated_ticker_sentiment
                WHERE combined_score IS NOT NULL OR news_score IS NOT NULL
            ),
            has_market AS (
                SELECT DISTINCT ticker FROM isyatirim_market_history
            ),
            has_ownership AS (
                SELECT DISTINCT ticker FROM isyatirim_ownership_history
            ),
            has_classification AS (
                SELECT DISTINCT stock_code AS ticker FROM stock_classification_history
            ),
            has_events AS (
                SELECT DISTINCT stock_code AS ticker FROM kap_events WHERE stock_code IS NOT NULL
            ),
            has_corporate_actions AS (
                SELECT DISTINCT ticker FROM corporate_actions
            ),
            all_tickers AS (
                -- The startup seed keeps this active BIST TÜM catalogue complete.
                -- Stored historical data is joined below for availability flags, not
                -- unioned here, which avoids duplicate selector rows per ticker.
                SELECT code AS ticker, name AS company_name, sector
                FROM bist_companies
                WHERE is_active = TRUE
            )
            SELECT
                t.ticker,
                t.company_name,
                t.sector,
                (hs.ticker IS NOT NULL)   AS has_sentiment,
                (hf.ticker IS NOT NULL)   AS has_fundamental,
                (hn.ticker IS NOT NULL)   AS has_news_sentiment,
                (hm.ticker IS NOT NULL)   AS has_market,
                (ho.ticker IS NOT NULL)   AS has_ownership,
                (hc.ticker IS NOT NULL)   AS has_classification,
                (he.ticker IS NOT NULL)   AS has_events,
                (hca.ticker IS NOT NULL)  AS has_corporate_actions
            FROM all_tickers t
            LEFT JOIN has_sentiment        hs  ON hs.ticker = t.ticker
            LEFT JOIN has_fundamental      hf  ON hf.ticker = t.ticker
            LEFT JOIN has_news_sentiment   hn  ON hn.ticker = t.ticker
            LEFT JOIN has_market           hm  ON hm.ticker = t.ticker
            LEFT JOIN has_ownership        ho  ON ho.ticker = t.ticker
            LEFT JOIN has_classification   hc  ON hc.ticker = t.ticker
            LEFT JOIN has_events           he  ON he.ticker = t.ticker
            LEFT JOIN has_corporate_actions hca ON hca.ticker = t.ticker
            ORDER BY t.ticker
            """,
            (),
        )
    except Exception as e:
        logger.error(f"instruments_catalog failed: {e}", exc_info=True)
        return JSONResponse(status_code=503, content={
            "contract_version": CONTRACT_VERSION,
            "status": "unavailable",
            "error_code": "UPSTREAM_DB_ERROR",
            "detail": str(e),
        })

    items = []
    seen = set()
    for r in rows:
        ticker = r["ticker"].upper()
        seen.add(ticker)
        available = []
        if r.get("has_sentiment"):
            available.append("sentiment")
        if r.get("has_fundamental"):
            available.append("fundamental")
        if r.get("has_news_sentiment"):
            available.extend(["news_sentiment", "combined_sentiment"])
        if r.get("has_market"):
            available.append("market")
        if r.get("has_ownership"):
            available.append("ownership")
        if r.get("has_classification"):
            available.append("classification")
        if r.get("has_events"):
            available.append("events")
        if r.get("has_corporate_actions"):
            available.append("corporate_actions")
        items.append({
            "ticker": ticker,
            "company_name": r.get("company_name") or STATIC_BIST_CATALOG.get(ticker),
            "sector": r.get("sector"),
            "market": market.value,
            "available_data": available,
            "catalog_source": "database",
        })

    # A data-poor database should not force users to remember tickers.  These are
    # explicitly labelled starter records; they do not imply a stored sentiment or
    # fundamental record exists.
    for ticker, company_name in STATIC_BIST_CATALOG.items():
        if ticker not in seen:
            items.append({
                "ticker": ticker, "company_name": company_name, "sector": None,
                "market": market.value, "available_data": [],
                "catalog_source": "built_in_catalog",
            })
    items.sort(key=lambda item: item["ticker"])

    return {
        "contract_version": CONTRACT_VERSION,
        "market": market.value,
        "total": len(items),
        "items": items,
    }


# ── health (§6.8) — declared first, no path params ───────────────────────────
@router.get("/health")
async def health(db_manager: DatabaseManager = Depends(get_db_manager)):
    """FA-17: reports DB *and* upstream (local Firecrawl) reachability.

    `status` keeps its existing DB-only meaning for readiness-probe
    compatibility (Firecrawl is scaled to zero outside the collector window by
    design — see deploy/turkish-financial — so treating it as a readiness
    dependency would make the probe flap). `checks` carries both results so a
    caller that wants the fuller picture can read it without affecting
    `status`.
    """
    db_ok = False
    try:
        conn = db_manager.get_connection()
        try:
            cur = conn.cursor()
            cur.execute("SELECT 1")
            cur.fetchone()
            db_ok = True
        finally:
            db_manager.return_connection(conn)
    except Exception as e:  # noqa: BLE001 - health must never raise
        logger.warning(f"External-analysis health DB check failed: {e}")

    upstream_ok = _firecrawl_capabilities_cache.get("status") == "ok"

    return {
        "status": "ok" if db_ok else "degraded",
        "contract_version": CONTRACT_VERSION,
        "provider": PROVIDER_ID,
        "checks": {
            "database": "ok" if db_ok else "unavailable",
            "upstream_firecrawl": "ok" if upstream_ok else "unavailable",
        },
    }


# FA-16 §3.6 — one coverage query per kind: instruments served, earliest/latest
# as_of, median observations per instrument, failure counts (last collection run).
# `last_run_failures` reads the in-process collection-state dicts the fundamental/
# ownership collectors already maintain; it is best-effort and process-local (no
# durable job history exists yet), so it is omitted entirely when the collector
# has never run in this process rather than reported as a fabricated zero.
_COVERAGE_QUERIES: Dict[str, str] = {
    "fundamental": """
        SELECT stock_code AS instrument, MIN(effective_at) AS earliest, MAX(effective_at) AS latest,
               COUNT(*) AS observations
        FROM kap_fundamentals GROUP BY stock_code
    """,
    "market": """
        SELECT ticker AS instrument, MIN(market_date) AS earliest, MAX(market_date) AS latest,
               COUNT(*) AS observations
        FROM isyatirim_market_history GROUP BY ticker
        UNION ALL
        SELECT ticker AS instrument, MIN(market_date) AS earliest, MAX(market_date) AS latest,
               COUNT(*) AS observations
        FROM yahoo_market_history GROUP BY ticker
        UNION ALL
        SELECT coin_id AS instrument, MIN(market_date) AS earliest, MAX(market_date) AS latest,
               COUNT(*) AS observations
        FROM coingecko_market_history GROUP BY coin_id
    """,
    "ownership": """
        SELECT ticker AS instrument, MIN(snapshot_date) AS earliest, MAX(snapshot_date) AS latest,
               COUNT(*) AS observations
        FROM isyatirim_ownership_history GROUP BY ticker
    """,
    "sentiment": """
        SELECT d.stock_code AS instrument, MIN(d.disclosure_date) AS earliest, MAX(d.disclosure_date) AS latest,
               COUNT(*) AS observations
        FROM kap_disclosure_sentiment s JOIN kap_disclosures d ON d.id = s.disclosure_id
        WHERE d.stock_code IS NOT NULL
        GROUP BY d.stock_code
    """,
    "events": """
        SELECT stock_code AS instrument, MIN(published_at) AS earliest, MAX(published_at) AS latest,
               COUNT(*) AS observations
        FROM kap_events WHERE stock_code IS NOT NULL GROUP BY stock_code
    """,
    "corporate_actions": """
        SELECT ticker AS instrument, MIN(ex_date) AS earliest, MAX(ex_date) AS latest,
               COUNT(*) AS observations
        FROM corporate_actions GROUP BY ticker
    """,
    "classification": """
        SELECT stock_code AS instrument, MIN(valid_from) AS earliest, MAX(valid_from) AS latest,
               COUNT(*) AS observations
        FROM stock_classification_history GROUP BY stock_code
    """,
}

# kind -> in-process collection-state dict, when one exists (best-effort failure count).
def _collection_states() -> Dict[str, dict]:
    # Each kind maps to the run that writes the table its coverage query reads.
    return {
        "fundamental": _kap_fundamental_collection_state,
        "market": _market_collection_state,
        "corporate_actions": _market_collection_state,
        "ownership": _ownership_collection_state,
    }


def _median(values: List[Any]) -> Optional[float]:
    nums = sorted(v for v in values if v is not None)
    if not nums:
        return None
    mid = len(nums) // 2
    if len(nums) % 2:
        return float(nums[mid])
    return (nums[mid - 1] + nums[mid]) / 2.0


def _kind_coverage(db_manager: DatabaseManager, kind: str, query: str) -> Dict[str, Any]:
    try:
        rows = db_manager.query(query, ())
    except Exception as exc:  # noqa: BLE001 - coverage must never break /capabilities
        logger.warning("coverage query failed for kind=%s: %s", kind, exc)
        return {"instruments_served": 0, "earliest_as_of": None, "latest_as_of": None, "median_observations_per_instrument": None}

    earliest = min((r.get("earliest") for r in rows if r.get("earliest") is not None), default=None)
    latest = max((r.get("latest") for r in rows if r.get("latest") is not None), default=None)
    coverage: Dict[str, Any] = {
        "instruments_served": len(rows),
        "earliest_as_of": _to_iso_utc_coverage(earliest),
        "latest_as_of": _to_iso_utc_coverage(latest),
        "median_observations_per_instrument": _median([r.get("observations") for r in rows]),
    }
    state = _collection_states().get(kind)
    if state is not None and state.get("started_at") is not None:
        coverage["last_collection_run"] = {
            "started_at": state.get("started_at"),
            "finished_at": state.get("finished_at"),
            "status": state.get("status"),
            "failure_count": state.get("failed", 0),
        }
    return coverage


def _to_iso_utc_coverage(value: Any) -> Optional[str]:
    """Local alias so this module doesn't need to import the fundamental repo's
    private `_to_iso_utc` just for the coverage block."""
    from infrastructure.repositories.external_analysis_repository import _to_iso_utc
    return _to_iso_utc(value)


@router.get("/capabilities")
async def capabilities(db_manager: DatabaseManager = Depends(get_db_manager)):
    """Return runtime-confirmed Firecrawl capabilities plus per-kind coverage (FA-16 §3.6)."""
    coverage = {
        kind: _kind_coverage(db_manager, kind, query)
        for kind, query in _COVERAGE_QUERIES.items()
    }
    return {
        "contract_version": CONTRACT_VERSION,
        "provider": PROVIDER_ID,
        "firecrawl": _firecrawl_capabilities_cache,
        "coverage": coverage,
    }


async def _collect_all_isyatirim_fundamentals(db_manager: DatabaseManager, force: bool) -> None:
    global _fundamental_collection_state
    try:
        rows = db_manager.query("SELECT code FROM bist_companies WHERE is_active = TRUE ORDER BY code", ())
        tickers = [row["code"].strip().upper() for row in rows if row.get("code")]
    except Exception:
        tickers = []
    tickers = tickers or sorted(STATIC_BIST_CATALOG)
    _fundamental_collection_state.update({"status": "running", "total": len(tickers), "completed": 0, "fetched": 0, "cached": 0, "failed": 0, "started_at": datetime.now(timezone.utc).isoformat(), "finished_at": None})
    ttl = max(300, int(os.getenv("ISYATIRIM_FUNDAMENTALS_CACHE_TTL_SECONDS", "21600")))
    delay = max(0.1, float(os.getenv("ISYATIRIM_FUNDAMENTALS_COLLECTION_DELAY_SECONDS", "0.5")))
    for ticker in tickers:
        try:
            cached = db_manager.get_isyatirim_fundamentals(ticker, ttl)
            if cached["fresh"] and cached["payload"].get("one_year_statement_history") and not force:
                _fundamental_collection_state["cached"] += 1
            else:
                payload = await asyncio.to_thread(fetch_fundamentals, ticker)
                db_manager.upsert_isyatirim_fundamentals(ticker, payload)
                _fundamental_collection_state["fetched"] += 1
        except Exception as exc:  # noqa: BLE001 - one unavailable company must not stop the collection
            logger.warning("İş Yatırım bulk fundamentals failed for %s: %s", ticker, exc)
            _fundamental_collection_state["failed"] += 1
        _fundamental_collection_state["completed"] += 1
        await asyncio.sleep(delay)
    _fundamental_collection_state.update({"status": "completed", "finished_at": datetime.now(timezone.utc).isoformat()})


@router.post("/isyatirim/fundamentals/collect")
async def collect_isyatirim_fundamentals(
    request: FundamentalsCollectionRequest,
    db_manager: DatabaseManager = Depends(get_db_manager),
):
    """Start a paced local collection of all active BIST fundamental snapshots."""
    global _fundamental_collection_task
    if _fundamental_collection_task is not None and not _fundamental_collection_task.done():
        return JSONResponse(status_code=409, content={"status": "running", **_fundamental_collection_state})
    _fundamental_collection_task = asyncio.create_task(_collect_all_isyatirim_fundamentals(db_manager, request.force))
    return {**_fundamental_collection_state, "status": "started"}


@router.get("/isyatirim/fundamentals/collection-status")
async def isyatirim_fundamentals_collection_status():
    return {"contract_version": CONTRACT_VERSION, **_fundamental_collection_state}


@router.get("/isyatirim/fundamentals")
async def search_isyatirim_fundamentals(
    query_text: str = Query("", alias="query", max_length=20),
    limit: int = Query(50, ge=1, le=200),
    db_manager: DatabaseManager = Depends(get_db_manager),
):
    """Query locally stored current snapshots without contacting İş Yatırım."""
    try:
        rows = db_manager.list_isyatirim_fundamentals(query_text, limit)
    except Exception:
        logger.exception("İş Yatırım fundamental search failed")
        return _db_error("database temporarily unavailable")
    items = []
    for row in rows:
        data = row.get("data") if isinstance(row.get("data"), dict) else {}
        values = data.get("current_valuation", {})
        items.append({"ticker": row.get("ticker"), "report_period": row.get("report_period"), "age_seconds": row.get("age_seconds"), "price_to_earnings": values.get("price_to_earnings"), "price_to_book": values.get("price_to_book"), "net_income_million_try": data.get("statement_snapshot", {}).get("net_income_million_try")})
    return {"contract_version": CONTRACT_VERSION, "status": "ok", "total": len(items), "items": items}


@router.get("/isyatirim/{instrument}/market-history")
async def isyatirim_market_history(
    instrument: str,
    market: Market = Query(Market.BIST),
    days: int = Query(30, ge=1, le=365),
    db_manager: DatabaseManager = Depends(get_db_manager),
):
    """Serve normalized public İş Yatırım daily market data for one BIST ticker."""
    ticker = instrument.strip().upper()
    if market != Market.BIST:
        return JSONResponse(status_code=400, content={
            "contract_version": CONTRACT_VERSION,
            "instrument": ticker,
            "market": market.value,
            "kind": "market_history",
            "status": "unavailable",
            "detail": "İş Yatırım market history currently supports market=bist only.",
        })
    cache_ttl_seconds = max(60, int(os.getenv("ISYATIRIM_MARKET_CACHE_TTL_SECONDS", "900")))
    try:
        cached = db_manager.get_isyatirim_market_history(ticker, days, cache_ttl_seconds)
    except Exception:  # noqa: BLE001 - a cache outage must not prevent an on-demand fetch
        logger.exception("İş Yatırım database cache lookup failed for %s", ticker)
        cached = {"fresh": False, "series": [], "age_seconds": None}
    cache_status = "database_cache"
    if cached["fresh"] and len(cached["series"]) >= days:
        payload = build_market_history_payload(cached["series"], days)
        freshness_seconds = cached["age_seconds"]
    else:
        try:
            payload = await asyncio.to_thread(fetch_market_history, ticker, days)
        except (ValueError, LookupError) as exc:
            return JSONResponse(status_code=404, content={
                "contract_version": CONTRACT_VERSION, "instrument": ticker,
                "market": market.value, "kind": "market_history", "status": "unavailable",
                "detail": str(exc),
            })
        except Exception as exc:  # noqa: BLE001 - upstream availability is variable
            logger.warning("İş Yatırım market history failed for %s: %s", ticker, exc)
            return JSONResponse(status_code=502, content={
                "contract_version": CONTRACT_VERSION, "instrument": ticker,
                "market": market.value, "kind": "market_history", "status": "unavailable",
                "detail": "İş Yatırım market data is temporarily unavailable.",
            })
        try:
            db_manager.upsert_isyatirim_market_history(ticker, payload["series"])
        except Exception:  # noqa: BLE001 - the visible fetched result remains valid
            logger.exception("İş Yatırım database cache write failed for %s", ticker)
        freshness_seconds = 0
        cache_status = "fetched"
    payload["cache"] = {"status": cache_status, "ttl_seconds": cache_ttl_seconds}
    return {
        "contract_version": CONTRACT_VERSION,
        "instrument": ticker,
        "market": market.value,
        "kind": "market_history",
        "as_of": payload["latest"]["trading_date"],
        "provider": "isyatirim-public-data",
        "source": "isyatirim-web",
        "freshness_seconds": freshness_seconds,
        "status": "ok",
        "payload": payload,
    }


@router.get("/isyatirim/{instrument}/fundamentals")
async def isyatirim_fundamentals(
    instrument: str,
    market: Market = Query(Market.BIST),
    db_manager: DatabaseManager = Depends(get_db_manager),
):
    """Serve cache-first public İş Yatırım company-card fundamentals for BIST."""
    ticker = instrument.strip().upper()
    if market != Market.BIST:
        return JSONResponse(status_code=400, content={
            "contract_version": CONTRACT_VERSION, "instrument": ticker,
            "market": market.value, "kind": "fundamentals", "status": "unavailable",
            "detail": "İş Yatırım fundamentals currently support market=bist only.",
        })
    cache_ttl_seconds = max(300, int(os.getenv("ISYATIRIM_FUNDAMENTALS_CACHE_TTL_SECONDS", "21600")))
    try:
        cached = db_manager.get_isyatirim_fundamentals(ticker, cache_ttl_seconds)
    except Exception:  # noqa: BLE001 - cache failure must not hide source availability
        logger.exception("İş Yatırım fundamental cache lookup failed for %s", ticker)
        cached = {"fresh": False, "payload": None, "age_seconds": None}
    cache_status = "database_cache"
    if cached["fresh"] and cached["payload"].get("one_year_statement_history"):
        payload = cached["payload"]
        freshness_seconds = cached["age_seconds"]
    else:
        try:
            payload = await asyncio.to_thread(fetch_fundamentals, ticker)
        except (ValueError, LookupError) as exc:
            return JSONResponse(status_code=404, content={
                "contract_version": CONTRACT_VERSION, "instrument": ticker,
                "market": market.value, "kind": "fundamentals", "status": "unavailable",
                "detail": str(exc),
            })
        except Exception as exc:  # noqa: BLE001 - upstream availability is variable
            logger.warning("İş Yatırım fundamentals failed for %s: %s", ticker, exc)
            return JSONResponse(status_code=502, content={
                "contract_version": CONTRACT_VERSION, "instrument": ticker,
                "market": market.value, "kind": "fundamentals", "status": "unavailable",
                "detail": "İş Yatırım fundamentals are temporarily unavailable.",
            })
        try:
            db_manager.upsert_isyatirim_fundamentals(ticker, payload)
        except Exception:  # noqa: BLE001 - fetched source result remains useful
            logger.exception("İş Yatırım fundamental cache write failed for %s", ticker)
        freshness_seconds = 0
        cache_status = "fetched"
    payload["cache"] = {"status": cache_status, "ttl_seconds": cache_ttl_seconds}
    return {
        "contract_version": CONTRACT_VERSION,
        "instrument": ticker,
        "market": market.value,
        "kind": "fundamentals",
        "as_of": (payload.get("reported_periods") or [None])[0],
        "provider": "isyatirim-public-data",
        "source": "isyatirim-web",
        "freshness_seconds": freshness_seconds,
        "status": "ok",
        "payload": payload,
    }


# ── batch (§6.2) ──────────────────────────────────────────────────────────────
@router.post("/sentiment/batch")
async def sentiment_batch(
    request: SentimentBatchRequest,
    db_manager: DatabaseManager = Depends(get_db_manager),
):
    repo = _repo(db_manager)
    items = []
    try:
        for instrument in request.instruments:
            items.append(
                repo.get_point(instrument, request.market.value, request.as_of)
            )
    except DatabaseManager.PoolExhaustedError:
        return _db_error("database temporarily unavailable")
    except Exception as e:  # noqa: BLE001
        logger.error(f"Batch sentiment failed: {e}", exc_info=True)
        return _db_error(str(e))

    # Sentiment has no contract-1.1 support (ExternalAnalysisRepository always
    # emits the 1.0 shape) — label this wrapper 1.0 too, not the server-wide
    # default, so it never disagrees with the envelopes nested inside it.
    return {"contract_version": CONTRACT_VERSION_1_0, "items": items}


# ── overview (§6.4) — static path before {instrument} ────────────────────────
@router.get("/sentiment/overview")
async def sentiment_overview(
    market: Market = Query(...),
    date_from: Optional[str] = Query(None, alias="from"),
    date_to: Optional[str] = Query(None, alias="to"),
    db_manager: DatabaseManager = Depends(get_db_manager),
):
    repo = _repo(db_manager)
    try:
        data = repo.get_overview(market.value, date_from, date_to)
    except DatabaseManager.PoolExhaustedError:
        return _db_error("database temporarily unavailable")
    except Exception as e:  # noqa: BLE001
        logger.error(f"Sentiment overview failed: {e}", exc_info=True)
        return _db_error(str(e))

    return {"contract_version": CONTRACT_VERSION, **data}


# ── history (§6.3) ────────────────────────────────────────────────────────────
@router.get("/sentiment/{instrument}/history")
async def sentiment_history(
    instrument: str,
    market: Market = Query(...),
    date_from: Optional[str] = Query(None, alias="from"),
    date_to: Optional[str] = Query(None, alias="to"),
    limit: int = Query(100, ge=1, le=1000),
    cursor: Optional[str] = Query(None),
    db_manager: DatabaseManager = Depends(get_db_manager),
):
    repo = _repo(db_manager)
    try:
        data = repo.get_history(
            instrument, market.value, date_from, date_to, limit, cursor
        )
    except DatabaseManager.PoolExhaustedError:
        return _db_error("database temporarily unavailable")
    except Exception as e:  # noqa: BLE001
        logger.error(f"Sentiment history failed: {e}", exc_info=True)
        return _db_error(str(e))

    return {
        "contract_version": CONTRACT_VERSION_1_0,
        "instrument": data["instrument"],
        "market": data["market"],
        "kind": "sentiment",
        "items": data["items"],
        "next_cursor": data["next_cursor"],
    }


# ── point (§6.1) — most general route, declared last ──────────────────────────
@router.get("/sentiment/{instrument}")
async def sentiment_point(
    instrument: str,
    market: Market = Query(...),
    as_of: Optional[str] = Query(None),
    db_manager: DatabaseManager = Depends(get_db_manager),
):
    repo = _repo(db_manager)
    try:
        return repo.get_point(instrument, market.value, as_of)
    except DatabaseManager.PoolExhaustedError:
        return _db_error("database temporarily unavailable")
    except Exception as e:  # noqa: BLE001
        logger.error(f"Sentiment point failed: {e}", exc_info=True)
        return _db_error(str(e))


# ════════════════════════════════════════════════════════════════════════════
# Fundamental kind (§3) — sourced from KAP "Finansal Tablolar"
# ════════════════════════════════════════════════════════════════════════════

async def _fetch_fundamental_in_background(
    instrument: str, db_manager: DatabaseManager
) -> None:
    """Actually run the live KAP scrape. Never awaited by a request handler —
    see `_spawn_on_demand_fundamental_fetch`."""
    from scrapers.kap_scraper import KAPScraper
    from infrastructure.contracts.instrument_identity_map import resolve_member_oid

    logger.info(
        "fundamental data for %s not in DB — triggering on-demand KAP fetch",
        instrument,
    )
    try:
        scraper = KAPScraper(db_manager=db_manager)

        # If OID is unknown, discover it before scraping. P2: KAP's
        # `member/filter` POST (`refresh_member_oids`) is a confirmed dead
        # endpoint (live 404, not transient/anti-bot) — trying it first wastes
        # a multi-proxy JS-injection cascade (45s+) on every miss before ever
        # reaching the GET fallback, which is why fundamental coverage stayed
        # at 0. Go straight to the GET-based resolution, which is verified
        # live and working.
        if resolve_member_oid(instrument, db_manager=db_manager) is None:
            logger.info(
                "mkkMemberOid for %s unknown — resolving via GET (member/filter POST is dead)",
                instrument,
            )
            try:
                await scraper.refresh_member_oids_via_get(instruments=[instrument])
            except Exception as exc:
                logger.warning("refresh_member_oids_via_get failed: %s", exc)

        await scraper.scrape_financial_statements(instruments=[instrument])
    except Exception as exc:
        logger.warning(
            "on-demand KAP fetch for %s failed: %s", instrument, exc
        )


def _spawn_on_demand_fundamental_fetch(instrument: str, db_manager: DatabaseManager) -> None:
    """P1 fix: fire the KAP scrape in the background; never await it in a
    request handler. The caller returns the current (unavailable) envelope
    immediately — a later request will see the data once the scrape lands."""
    if _firecrawl_capabilities_cache.get("status") != "ok":
        # KAP scraping needs Firecrawl, which sleeps outside the collector window;
        # the nightly /fundamental/collect run picks never-collected tickers first.
        logger.info("fundamental %s not stored; Firecrawl asleep, left to the collection window", instrument)
        return
    _spawn_on_demand_fetch(
        ("fundamental", "bist", instrument),
        # KAP scraping does some blocking I/O; keep it off the request loop.
        lambda: run_off_loop(lambda: _fetch_fundamental_in_background(instrument, db_manager)),
    )


class DisclosureCollectRequest(BaseModel):
    days_back: int = Field(2, ge=1, le=31)


@router.post("/kap/disclosures/collect")
async def collect_kap_disclosures(
    request: DisclosureCollectRequest = DisclosureCollectRequest(),
    db_manager: DatabaseManager = Depends(get_db_manager),
):
    """Store KAP disclosures (KAP's own index and ticker) and classify FA-07 events.

    Uses KAP's disclosure search API over plain HTTP — no Firecrawl needed — so it
    feeds events, dividends and earnings_calendar outside the collector window too.
    """
    from scrapers.kap_scraper import KAPScraper

    scraper = KAPScraper(db_manager=db_manager)
    try:
        result = await run_off_loop(lambda: scraper.scrape_and_save_disclosures(days_back=request.days_back))
    except DatabaseManager.PoolExhaustedError:
        return _db_error("database temporarily unavailable")
    except Exception as e:  # noqa: BLE001
        logger.error(f"KAP disclosure collection failed: {e}", exc_info=True)
        return _db_error(str(e))
    body = {k: result.get(k) for k in ("success", "total", "saved", "error") if k in result}
    status = 200 if result.get("success") else 502
    return JSONResponse(status_code=status, content={"contract_version": CONTRACT_VERSION, **body})


class FundamentalCollectRequest(BaseModel):
    # KAP is slow (Firecrawl page renders, rate-based anti-bot), so each daily
    # run handles a bounded batch; coverage accrues across runs.
    max_instruments: int = Field(20, ge=1, le=600)
    tickers: Optional[List[str]] = None


_kap_fundamental_collection_task = None
_kap_fundamental_collection_state = {"status": "idle", "total": 0, "completed": 0, "fetched": 0, "failed": 0, "started_at": None, "finished_at": None}


def _fundamental_collection_queue(db_manager: DatabaseManager, limit: int) -> List[str]:
    """Never-collected tickers first, then the stalest."""
    try:
        rows = db_manager.query(
            """
            SELECT b.code
            FROM bist_companies b
            LEFT JOIN (
                SELECT stock_code, MAX(effective_at) AS last_at
                FROM kap_fundamentals GROUP BY stock_code
            ) f ON f.stock_code = b.code
            WHERE b.is_active = TRUE
            ORDER BY f.last_at ASC NULLS FIRST, b.code
            LIMIT %s
            """,
            (limit,),
        )
        tickers = [r["code"].strip().upper() for r in rows if r.get("code")]
    except Exception:  # noqa: BLE001 - fall back to the built-in catalogue
        tickers = []
    return tickers or sorted(STATIC_BIST_CATALOG)[:limit]


async def _collect_kap_fundamentals(db_manager: DatabaseManager, tickers: List[str]) -> None:
    from scrapers.kap_scraper import KAPScraper
    from infrastructure.contracts.instrument_identity_map import resolve_member_oid

    _kap_fundamental_collection_state.update({"status": "running", "total": len(tickers), "completed": 0, "fetched": 0, "failed": 0, "started_at": datetime.now(timezone.utc).isoformat(), "finished_at": None})
    scraper = KAPScraper(db_manager=db_manager)
    for idx, ticker in enumerate(tickers):
        if idx:
            await asyncio.sleep(scraper.KAP_PAGE_DELAY_S)  # KAP anti-bot is rate-based
        try:
            if resolve_member_oid(ticker, db_manager=db_manager) is None:
                # member/filter POST is dead (live 404); GET resolution only.
                await scraper.refresh_member_oids_via_get(instruments=[ticker])
            result = await scraper.scrape_financial_statements(instruments=[ticker])
            if result.get("processed"):
                _kap_fundamental_collection_state["fetched"] += 1
            else:
                _kap_fundamental_collection_state["failed"] += 1
        except Exception as exc:  # noqa: BLE001 - one ticker must not stop the run
            logger.warning("KAP fundamental collection failed for %s: %s", ticker, exc)
            _kap_fundamental_collection_state["failed"] += 1
        _kap_fundamental_collection_state["completed"] += 1
    _kap_fundamental_collection_state.update({"status": "completed", "finished_at": datetime.now(timezone.utc).isoformat()})


@router.post("/fundamental/collect")
async def collect_kap_fundamentals(
    request: FundamentalCollectRequest = FundamentalCollectRequest(),
    db_manager: DatabaseManager = Depends(get_db_manager),
):
    """Start a paced KAP financial-statement collection run (needs Firecrawl up)."""
    global _kap_fundamental_collection_task
    if _kap_fundamental_collection_task is not None and not _kap_fundamental_collection_task.done():
        return JSONResponse(status_code=409, content={"status": "running", **_kap_fundamental_collection_state})
    tickers = (
        [t.strip().upper() for t in request.tickers if t.strip()][: request.max_instruments]
        if request.tickers
        else _fundamental_collection_queue(db_manager, request.max_instruments)
    )
    _kap_fundamental_collection_state.update({"status": "running", "total": len(tickers), "started_at": datetime.now(timezone.utc).isoformat(), "finished_at": None})
    _kap_fundamental_collection_task = asyncio.create_task(
        run_off_loop(lambda: _collect_kap_fundamentals(db_manager, tickers))
    )
    return {**_kap_fundamental_collection_state, "status": "started", "tickers": tickers}


@router.get("/fundamental/collection-status")
async def kap_fundamental_collection_status():
    return {"contract_version": CONTRACT_VERSION, **_kap_fundamental_collection_state}


# ── batch (§6.2) ──────────────────────────────────────────────────────────────
@router.post("/fundamental/batch")
async def fundamental_batch(
    request: FundamentalBatchRequest,
    db_manager: DatabaseManager = Depends(get_db_manager),
):
    contract_version = _resolve_contract_version(request.contract_version)
    repo = _fund_repo(db_manager)
    items = []
    try:
        for instrument in request.instruments:
            point = repo.get_point(
                instrument, request.market.value, request.as_of,
                contract_version=contract_version,
            )
            if point.get("status") == "unavailable" and request.as_of is None:
                _spawn_on_demand_fundamental_fetch(instrument, db_manager)
            items.append(point)
    except DatabaseManager.PoolExhaustedError:
        return _db_error("database temporarily unavailable")
    except Exception as e:  # noqa: BLE001
        logger.error(f"Batch fundamental failed: {e}", exc_info=True)
        return _db_error(str(e))

    return {"contract_version": contract_version, "items": items}


# ── history (§6.3) — static suffix before {instrument} point ──────────────────
@router.get("/fundamental/{instrument}/history")
async def fundamental_history(
    instrument: str,
    market: Market = Query(...),
    date_from: Optional[str] = Query(None, alias="from"),
    date_to: Optional[str] = Query(None, alias="to"),
    limit: int = Query(100, ge=1, le=1000),
    cursor: Optional[str] = Query(None),
    contract_version: str = Query(CONTRACT_VERSION),
    db_manager: DatabaseManager = Depends(get_db_manager),
):
    resolved_version = _resolve_contract_version(contract_version)
    repo = _fund_repo(db_manager)
    try:
        data = repo.get_history(
            instrument, market.value, date_from, date_to, limit, cursor,
            contract_version=resolved_version,
        )
    except DatabaseManager.PoolExhaustedError:
        return _db_error("database temporarily unavailable")
    except Exception as e:  # noqa: BLE001
        logger.error(f"Fundamental history failed: {e}", exc_info=True)
        return _db_error(str(e))

    return {
        "contract_version": resolved_version,
        "instrument": data["instrument"],
        "market": data["market"],
        "kind": "fundamental",
        "items": data["items"],
        "next_cursor": data["next_cursor"],
    }


# ── point (§6.1) — most general route, declared last ──────────────────────────
@router.get("/fundamental/{instrument}")
async def fundamental_point(
    instrument: str,
    market: Market = Query(...),
    as_of: Optional[str] = Query(None),
    contract_version: str = Query(CONTRACT_VERSION),
    db_manager: DatabaseManager = Depends(get_db_manager),
):
    resolved_version = _resolve_contract_version(contract_version)
    repo = _fund_repo(db_manager)
    try:
        result = repo.get_point(instrument, market.value, as_of, contract_version=resolved_version)
        if result.get("status") == "unavailable" and as_of is None:
            _spawn_on_demand_fundamental_fetch(instrument, db_manager)
        return result
    except DatabaseManager.PoolExhaustedError:
        return _db_error("database temporarily unavailable")
    except Exception as e:  # noqa: BLE001
        logger.error(f"Fundamental point failed: {e}", exc_info=True)
        return _db_error(str(e))


# ════════════════════════════════════════════════════════════════════════════
# Market kind (FA-05) — daily İş Yatırım OHLC/volume/market-cap history
# ════════════════════════════════════════════════════════════════════════════

class MarketBatchRequest(BaseModel):
    """§4 batch body (market kind)."""

    market: Market
    instruments: List[str] = Field(..., min_length=1)
    as_of: Optional[str] = None
    contract_version: str = CONTRACT_VERSION


def _market_repo(db_manager: DatabaseManager) -> MarketRepository:
    return MarketRepository(db_manager)


def _active_bist_tickers(db_manager: DatabaseManager) -> List[str]:
    try:
        rows = db_manager.query("SELECT code FROM bist_companies WHERE is_active = TRUE ORDER BY code", ())
        tickers = [row["code"].strip().upper() for row in rows if row.get("code")]
    except Exception:  # noqa: BLE001 - fall back to the built-in catalogue
        tickers = []
    return tickers or sorted(STATIC_BIST_CATALOG)


class MarketCollectRequest(BaseModel):
    # A daily run only needs the last few sessions; overlap keeps it idempotent
    # across missed days. Use a large value (≤730) once to backfill.
    days: int = Field(7, ge=1, le=730)


_market_collection_task = None
_market_collection_state = {"status": "idle", "total": 0, "completed": 0, "fetched": 0, "failed": 0, "corporate_actions_detected": 0, "started_at": None, "finished_at": None}


async def _collect_all_bist_market_history(db_manager: DatabaseManager, days: int) -> None:
    """C5: pre-collect daily market history for the whole BIST universe so a
    point read never has to trigger a fetch, then re-run FA-06 corporate-action
    detection for each ticker over its updated history (DB-only, idempotent)."""
    tickers = _active_bist_tickers(db_manager)
    _market_collection_state.update({"status": "running", "total": len(tickers), "completed": 0, "fetched": 0, "failed": 0, "corporate_actions_detected": 0, "started_at": datetime.now(timezone.utc).isoformat(), "finished_at": None})
    delay = max(0.1, float(os.getenv("ISYATIRIM_MARKET_COLLECTION_DELAY_SECONDS", "0.5")))
    actions = _corporate_action_repo(db_manager)
    for ticker in tickers:
        try:
            payload = await asyncio.to_thread(fetch_market_history, ticker, days)
            db_manager.upsert_isyatirim_market_history(ticker, payload["series"])
            _market_collection_state["fetched"] += 1
            result = await asyncio.to_thread(actions.detect_and_persist, ticker)
            _market_collection_state["corporate_actions_detected"] += int(result.get("detected") or 0)
        except Exception as exc:  # noqa: BLE001 - one unavailable ticker must not stop the run
            logger.warning("Market history collection failed for %s: %s", ticker, exc)
            _market_collection_state["failed"] += 1
        _market_collection_state["completed"] += 1
        await asyncio.sleep(delay)
    _market_collection_state.update({"status": "completed", "finished_at": datetime.now(timezone.utc).isoformat()})


@router.post("/market/collect")
async def collect_market_history(
    request: MarketCollectRequest = MarketCollectRequest(),
    db_manager: DatabaseManager = Depends(get_db_manager),
):
    """Start a paced BIST market-history (+ corporate-action detection) run."""
    global _market_collection_task
    if _market_collection_task is not None and not _market_collection_task.done():
        return JSONResponse(status_code=409, content={"status": "running", **_market_collection_state})
    # Mark running before returning so a status poll right after the POST never sees the previous run's "completed".
    _market_collection_state.update({"status": "running", "started_at": datetime.now(timezone.utc).isoformat(), "finished_at": None})
    _market_collection_task = asyncio.create_task(_collect_all_bist_market_history(db_manager, request.days))
    return {**_market_collection_state, "status": "started"}


@router.get("/market/collection-status")
async def market_collection_status():
    return {"contract_version": CONTRACT_VERSION, **_market_collection_state}


async def _fetch_market_in_background(instrument: str, db_manager: DatabaseManager, market: str) -> None:
    """Actually run the live fetch. Never awaited by a request handler — see
    `_spawn_on_demand_market_fetch`."""
    market_key = (market or "").strip().lower()
    try:
        if market_key == "bist":
            from scrapers.isyatirim_market_data import fetch_market_history as fetch_bist
            payload = await asyncio.to_thread(fetch_bist, instrument, 30)
            db_manager.upsert_isyatirim_market_history(instrument, payload["series"])
        elif market_key == "usa":
            from scrapers.yahoo_market_data import fetch_market_history as fetch_usa
            payload = await asyncio.to_thread(fetch_usa, instrument, 30)
            db_manager.upsert_yahoo_market_history(instrument, payload["series"])
        elif market_key == "coin":
            from scrapers.coingecko_market_data import fetch_market_history as fetch_coin
            payload = await asyncio.to_thread(fetch_coin, instrument, 30)
            db_manager.upsert_coingecko_market_history(instrument, payload["series"])
    except Exception as exc:  # noqa: BLE001 - best-effort, honest unavailable on failure
        logger.warning("on-demand market fetch for %s/%s failed: %s", market, instrument, exc)


def _spawn_on_demand_market_fetch(instrument: str, db_manager: DatabaseManager, market: str) -> None:
    """P1/C5 fix: fire the market data fetch in the background; never await it
    in a request handler. The caller returns the current (unavailable)
    envelope immediately — a later request will see the data once it lands."""
    _spawn_on_demand_fetch(
        ("market", market, instrument),
        lambda: _fetch_market_in_background(instrument, db_manager, market),
    )


@router.post("/market/batch")
async def market_batch(
    request: MarketBatchRequest,
    db_manager: DatabaseManager = Depends(get_db_manager),
):
    contract_version = _resolve_contract_version(request.contract_version)
    repo = _market_repo(db_manager)
    try:
        items = []
        for instrument in request.instruments:
            point = repo.get_point(
                instrument, request.market.value, request.as_of,
                contract_version=contract_version,
            )
            if point.get("status") == "unavailable" and request.as_of is None:
                _spawn_on_demand_market_fetch(instrument, db_manager, request.market.value)
            items.append(point)
    except DatabaseManager.PoolExhaustedError:
        return _db_error("database temporarily unavailable")
    except Exception as e:  # noqa: BLE001
        logger.error(f"Batch market failed: {e}", exc_info=True)
        return _db_error(str(e))

    return {"contract_version": contract_version, "items": items}


@router.get("/market/{instrument}/history")
async def market_history(
    instrument: str,
    market: Market = Query(...),
    date_from: Optional[str] = Query(None, alias="from"),
    date_to: Optional[str] = Query(None, alias="to"),
    limit: int = Query(100, ge=1, le=1000),
    cursor: Optional[str] = Query(None),
    contract_version: str = Query(CONTRACT_VERSION),
    db_manager: DatabaseManager = Depends(get_db_manager),
):
    resolved_version = _resolve_contract_version(contract_version)
    repo = _market_repo(db_manager)
    try:
        data = repo.get_history(
            instrument, market.value, date_from, date_to, limit, cursor,
            contract_version=resolved_version,
        )
    except DatabaseManager.PoolExhaustedError:
        return _db_error("database temporarily unavailable")
    except Exception as e:  # noqa: BLE001
        logger.error(f"Market history failed: {e}", exc_info=True)
        return _db_error(str(e))

    return {
        "contract_version": resolved_version,
        "instrument": data["instrument"],
        "market": data["market"],
        "kind": "market",
        "items": data["items"],
        "next_cursor": data["next_cursor"],
    }


@router.get("/market/{instrument}")
async def market_point(
    instrument: str,
    market: Market = Query(...),
    as_of: Optional[str] = Query(None),
    contract_version: str = Query(CONTRACT_VERSION),
    db_manager: DatabaseManager = Depends(get_db_manager),
):
    resolved_version = _resolve_contract_version(contract_version)
    repo = _market_repo(db_manager)
    try:
        result = repo.get_point(instrument, market.value, as_of, contract_version=resolved_version)
        if result.get("status") == "unavailable" and as_of is None:
            _spawn_on_demand_market_fetch(instrument, db_manager, market.value)
        return result
    except DatabaseManager.PoolExhaustedError:
        return _db_error("database temporarily unavailable")
    except Exception as e:  # noqa: BLE001
        logger.error(f"Market point failed: {e}", exc_info=True)
        return _db_error(str(e))


# ════════════════════════════════════════════════════════════════════════════
# Index kind (FA-05) — market-wide index series (XU100, XU030, XBANK, XUSIN)
#
# No confirmed public data source yet: İş Yatırım's per-ticker HisseTekil endpoint
# returns ok:true with an empty series for every index-code variant tried
# (XU100, XU100.E, BIST100, "XU 100") — it does not serve index-level OHLC series.
# Until a verified source is wired in, every index request is an honest
# `unavailable` rather than a guess (§3.4). Tracked as a FA-05 follow-up.
# ════════════════════════════════════════════════════════════════════════════

_SUPPORTED_INDEX_CODES = {"XU100", "XU030", "XBANK", "XUSIN"}


@router.get("/index/{code}/history")
async def index_history(
    code: str,
    # Series scope ("bist"), not the instrument-market enum.
    market: str = Query("bist"),
    contract_version: str = Query(CONTRACT_VERSION),
):
    resolved_version = _resolve_contract_version(contract_version)
    index_code = code.strip().upper()
    detail = (
        "No verified İş Yatırım (or other) data source for index-level history yet."
        if index_code in _SUPPORTED_INDEX_CODES
        else f"Unsupported index code '{index_code}'."
    )
    return {
        "contract_version": resolved_version,
        "instrument": index_code,
        "market": market,
        "kind": "index",
        "items": [],
        "next_cursor": None,
        "status": "unavailable",
        "detail": detail,
    }


# ════════════════════════════════════════════════════════════════════════════
# Ownership kind (FA-09) — daily foreign-ownership / free-float snapshots
# ════════════════════════════════════════════════════════════════════════════

_ownership_collection_task = None
_ownership_collection_state = {"status": "idle", "total": 0, "completed": 0, "fetched": 0, "failed": 0, "started_at": None, "finished_at": None}


def _ownership_repo(db_manager: DatabaseManager) -> OwnershipRepository:
    return OwnershipRepository(db_manager)


async def _collect_all_ownership_snapshots(db_manager: DatabaseManager) -> None:
    """Paced daily snapshot of every active BIST ticker's ownership %.

    The public company card exposes only the CURRENT percentage, so this is how
    FA-09's history accrues — one row per ticker for today, every day this runs.
    """
    global _ownership_collection_state
    from datetime import date as _date

    tickers = _active_bist_tickers(db_manager)
    _ownership_collection_state.update({"status": "running", "total": len(tickers), "completed": 0, "fetched": 0, "failed": 0, "started_at": datetime.now(timezone.utc).isoformat(), "finished_at": None})
    delay = max(0.1, float(os.getenv("ISYATIRIM_OWNERSHIP_COLLECTION_DELAY_SECONDS", "0.5")))
    today = _date.today()
    for ticker in tickers:
        try:
            payload = await asyncio.to_thread(fetch_fundamentals, ticker)
            current = payload.get("current_valuation", {})
            db_manager.upsert_isyatirim_ownership_snapshot(
                ticker, today,
                current.get("foreign_ownership_percent"),
                current.get("free_float_percent"),
            )
            _ownership_collection_state["fetched"] += 1
        except Exception as exc:  # noqa: BLE001 - one unavailable company must not stop the collection
            logger.warning("Ownership snapshot failed for %s: %s", ticker, exc)
            _ownership_collection_state["failed"] += 1
        _ownership_collection_state["completed"] += 1
        await asyncio.sleep(delay)
    _ownership_collection_state.update({"status": "completed", "finished_at": datetime.now(timezone.utc).isoformat()})


@router.post("/ownership/collect")
async def collect_ownership_snapshots(db_manager: DatabaseManager = Depends(get_db_manager)):
    """Start a paced daily ownership-snapshot collection run (FA-09)."""
    global _ownership_collection_task
    if _ownership_collection_task is not None and not _ownership_collection_task.done():
        return JSONResponse(status_code=409, content={"status": "running", **_ownership_collection_state})
    _ownership_collection_task = asyncio.create_task(_collect_all_ownership_snapshots(db_manager))
    return {**_ownership_collection_state, "status": "started"}


@router.get("/ownership/collection-status")
async def ownership_collection_status():
    return {"contract_version": CONTRACT_VERSION, **_ownership_collection_state}


@router.post("/ownership/batch")
async def ownership_batch(
    request: MarketBatchRequest,
    db_manager: DatabaseManager = Depends(get_db_manager),
):
    contract_version = _resolve_contract_version(request.contract_version)
    repo = _ownership_repo(db_manager)
    try:
        items = [
            repo.get_point(
                instrument, request.market.value, request.as_of,
                contract_version=contract_version,
            )
            for instrument in request.instruments
        ]
    except DatabaseManager.PoolExhaustedError:
        return _db_error("database temporarily unavailable")
    except Exception as e:  # noqa: BLE001
        logger.error(f"Batch ownership failed: {e}", exc_info=True)
        return _db_error(str(e))

    return {"contract_version": contract_version, "items": items}


@router.get("/ownership/{instrument}/history")
async def ownership_history(
    instrument: str,
    market: Market = Query(...),
    date_from: Optional[str] = Query(None, alias="from"),
    date_to: Optional[str] = Query(None, alias="to"),
    limit: int = Query(100, ge=1, le=1000),
    cursor: Optional[str] = Query(None),
    contract_version: str = Query(CONTRACT_VERSION),
    db_manager: DatabaseManager = Depends(get_db_manager),
):
    resolved_version = _resolve_contract_version(contract_version)
    repo = _ownership_repo(db_manager)
    try:
        data = repo.get_history(
            instrument, market.value, date_from, date_to, limit, cursor,
            contract_version=resolved_version,
        )
    except DatabaseManager.PoolExhaustedError:
        return _db_error("database temporarily unavailable")
    except Exception as e:  # noqa: BLE001
        logger.error(f"Ownership history failed: {e}", exc_info=True)
        return _db_error(str(e))

    return {
        "contract_version": resolved_version,
        "instrument": data["instrument"],
        "market": data["market"],
        "kind": "ownership",
        "items": data["items"],
        "next_cursor": data["next_cursor"],
    }


@router.get("/ownership/{instrument}")
async def ownership_point(
    instrument: str,
    market: Market = Query(...),
    as_of: Optional[str] = Query(None),
    contract_version: str = Query(CONTRACT_VERSION),
    db_manager: DatabaseManager = Depends(get_db_manager),
):
    resolved_version = _resolve_contract_version(contract_version)
    repo = _ownership_repo(db_manager)
    try:
        return repo.get_point(instrument, market.value, as_of, contract_version=resolved_version)
    except DatabaseManager.PoolExhaustedError:
        return _db_error("database temporarily unavailable")
    except Exception as e:  # noqa: BLE001
        logger.error(f"Ownership point failed: {e}", exc_info=True)
        return _db_error(str(e))


# ════════════════════════════════════════════════════════════════════════════
# Events kind (FA-07) — normalized KAP disclosure event taxonomy
# ════════════════════════════════════════════════════════════════════════════

def _event_repo(db_manager: DatabaseManager) -> EventRepository:
    return EventRepository(db_manager)


@router.get("/events/{instrument}/history")
async def events_history(
    instrument: str,
    market: Market = Query(...),
    date_from: Optional[str] = Query(None, alias="from"),
    date_to: Optional[str] = Query(None, alias="to"),
    limit: int = Query(100, ge=1, le=1000),
    cursor: Optional[str] = Query(None),
    contract_version: str = Query(CONTRACT_VERSION),
    db_manager: DatabaseManager = Depends(get_db_manager),
):
    resolved_version = _resolve_contract_version(contract_version)
    repo = _event_repo(db_manager)
    try:
        data = repo.get_history(
            instrument, market.value, date_from, date_to, limit, cursor,
            contract_version=resolved_version,
        )
    except DatabaseManager.PoolExhaustedError:
        return _db_error("database temporarily unavailable")
    except Exception as e:  # noqa: BLE001
        logger.error(f"Events history failed: {e}", exc_info=True)
        return _db_error(str(e))

    return {
        "contract_version": resolved_version,
        "instrument": data["instrument"],
        "market": data["market"],
        "kind": "events",
        "items": data["items"],
        "next_cursor": data["next_cursor"],
    }


# ════════════════════════════════════════════════════════════════════════════
# Corporate actions kind (FA-06, CRITICAL) — back-adjustment price factors
# ════════════════════════════════════════════════════════════════════════════

def _corporate_action_repo(db_manager: DatabaseManager) -> CorporateActionRepository:
    return CorporateActionRepository(db_manager)


@router.post("/corporate_actions/{instrument}/detect")
async def detect_corporate_actions(
    instrument: str,
    market: Market = Query(Market.BIST),
    db_manager: DatabaseManager = Depends(get_db_manager),
):
    """Run FA-06 detection for one ticker over its stored market history.

    Idempotent — safe to re-run after new market history/events accrue."""
    if market != Market.BIST:
        return JSONResponse(status_code=400, content={
            "contract_version": CONTRACT_VERSION, "instrument": instrument.upper(),
            "market": market.value, "kind": "corporate_actions", "status": "unavailable",
            "detail": "Corporate-action detection currently supports market=bist only.",
        })
    repo = _corporate_action_repo(db_manager)
    try:
        result = await asyncio.to_thread(repo.detect_and_persist, instrument)
    except DatabaseManager.PoolExhaustedError:
        return _db_error("database temporarily unavailable")
    except Exception as e:  # noqa: BLE001
        logger.error(f"Corporate action detection failed for {instrument}: {e}", exc_info=True)
        return _db_error(str(e))
    return {"contract_version": CONTRACT_VERSION, **result}


@router.get("/corporate_actions/{instrument}/history")
async def corporate_actions_history(
    instrument: str,
    market: Market = Query(...),
    date_from: Optional[str] = Query(None, alias="from"),
    date_to: Optional[str] = Query(None, alias="to"),
    limit: int = Query(100, ge=1, le=1000),
    cursor: Optional[str] = Query(None),
    contract_version: str = Query(CONTRACT_VERSION),
    db_manager: DatabaseManager = Depends(get_db_manager),
):
    resolved_version = _resolve_contract_version(contract_version)
    repo = _corporate_action_repo(db_manager)
    try:
        data = repo.get_history(
            instrument, market.value, date_from, date_to, limit, cursor,
            contract_version=resolved_version,
        )
    except DatabaseManager.PoolExhaustedError:
        return _db_error("database temporarily unavailable")
    except Exception as e:  # noqa: BLE001
        logger.error(f"Corporate actions history failed: {e}", exc_info=True)
        return _db_error(str(e))

    return {
        "contract_version": resolved_version,
        "instrument": data["instrument"],
        "market": data["market"],
        "kind": "corporate_actions",
        "items": data["items"],
        "next_cursor": data["next_cursor"],
    }


# ════════════════════════════════════════════════════════════════════════════
# Macro kind (FA-11) — EVDS core series by F23 alias
#
# Every alias is honestly `unavailable` today: no EVDS series code has been
# verified against the live catalog yet (domain.services.macro_series_registry),
# and release_date (required on every row, per §3.4) is not sourced from EVDS's
# basic series endpoint at all. See macro_repository.py's module docstring.
# ════════════════════════════════════════════════════════════════════════════

def _macro_repo(db_manager: DatabaseManager) -> MacroRepository:
    return MacroRepository(db_manager)


@router.get("/macro/series")
async def macro_series_catalog(db_manager: DatabaseManager = Depends(get_db_manager)):
    """List every F23 macro alias this provider recognizes, with its
    verification state — never a live upstream call, just the registry."""
    repo = _macro_repo(db_manager)
    return {
        "contract_version": CONTRACT_VERSION,
        "provider": "tcmb-evds",
        "items": repo.list_series(),
    }


@router.get("/macro/{series}/history")
async def macro_history(
    series: str,
    # Series scope: F23 sends market=tr for macro; the enum would reject it with 422.
    market: str = Query("tr"),
    date_from: Optional[str] = Query(None, alias="from"),
    date_to: Optional[str] = Query(None, alias="to"),
    limit: int = Query(100, ge=1, le=1000),
    cursor: Optional[str] = Query(None),
    contract_version: str = Query(CONTRACT_VERSION),
    db_manager: DatabaseManager = Depends(get_db_manager),
):
    resolved_version = _resolve_contract_version(contract_version)
    repo = _macro_repo(db_manager)
    try:
        data = repo.get_history(
            series, date_from, date_to, limit, cursor,
            contract_version=resolved_version,
        )
    except DatabaseManager.PoolExhaustedError:
        return _db_error("database temporarily unavailable")
    except Exception as e:  # noqa: BLE001
        logger.error(f"Macro history failed: {e}", exc_info=True)
        return _db_error(str(e))

    return {
        "contract_version": resolved_version,
        "instrument": data["series"],
        "market": "tr",
        "kind": "macro",
        "items": data["items"],
        "next_cursor": data["next_cursor"],
    }


# ════════════════════════════════════════════════════════════════════════════
# Classification kind (FA-10) — dated sector/industry + index membership
#
# No scraper populates stock_classification_history / index_membership_history
# yet (bist_companies.sector and bist_index_members have no writer either), so
# every instrument reads as honestly `unclassified` and every index has an
# empty member list today — the read/write contract shape is real and ready
# once a classification source is wired in.
# ════════════════════════════════════════════════════════════════════════════

def _classification_repo(db_manager: DatabaseManager) -> ClassificationRepository:
    return ClassificationRepository(db_manager)


@router.get("/classification/{instrument}/history")
async def classification_history(
    instrument: str,
    market: Market = Query(...),
    limit: int = Query(100, ge=1, le=1000),
    cursor: Optional[str] = Query(None),
    contract_version: str = Query(CONTRACT_VERSION),
    db_manager: DatabaseManager = Depends(get_db_manager),
):
    resolved_version = _resolve_contract_version(contract_version)
    repo = _classification_repo(db_manager)
    try:
        data = repo.get_history(instrument, market.value, limit, cursor, contract_version=resolved_version)
    except DatabaseManager.PoolExhaustedError:
        return _db_error("database temporarily unavailable")
    except Exception as e:  # noqa: BLE001
        logger.error(f"Classification history failed: {e}", exc_info=True)
        return _db_error(str(e))

    return {
        "contract_version": resolved_version,
        "instrument": data["instrument"],
        "market": data["market"],
        "kind": "classification",
        "items": data["items"],
        "next_cursor": data["next_cursor"],
    }


@router.get("/index/{code}/members")
async def index_members(
    code: str,
    as_of: Optional[str] = Query(None),
    db_manager: DatabaseManager = Depends(get_db_manager),
):
    repo = _classification_repo(db_manager)
    try:
        data = await asyncio.to_thread(repo.get_index_members, code, as_of)
    except DatabaseManager.PoolExhaustedError:
        return _db_error("database temporarily unavailable")
    except Exception as e:  # noqa: BLE001
        logger.error(f"Index members failed: {e}", exc_info=True)
        return _db_error(str(e))
    return {"contract_version": CONTRACT_VERSION, **data}


# ════════════════════════════════════════════════════════════════════════════
# Earnings calendar kind (FA-08) — derived from FA-02's kap_fundamentals rows
# ════════════════════════════════════════════════════════════════════════════

def _earnings_calendar_repo(db_manager: DatabaseManager) -> EarningsCalendarRepository:
    return EarningsCalendarRepository(db_manager)


@router.get("/earnings_calendar/{instrument}/history")
async def earnings_calendar_history(
    instrument: str,
    market: Market = Query(...),
    limit: int = Query(100, ge=1, le=1000),
    cursor: Optional[str] = Query(None),
    contract_version: str = Query(CONTRACT_VERSION),
    db_manager: DatabaseManager = Depends(get_db_manager),
):
    resolved_version = _resolve_contract_version(contract_version)
    repo = _earnings_calendar_repo(db_manager)
    try:
        data = repo.get_history(instrument, market.value, limit, cursor, contract_version=resolved_version)
    except DatabaseManager.PoolExhaustedError:
        return _db_error("database temporarily unavailable")
    except Exception as e:  # noqa: BLE001
        logger.error(f"Earnings calendar history failed: {e}", exc_info=True)
        return _db_error(str(e))

    return {
        "contract_version": resolved_version,
        "instrument": data["instrument"],
        "market": data["market"],
        "kind": "earnings_calendar",
        "items": data["items"],
        "next_cursor": data["next_cursor"],
    }


# ════════════════════════════════════════════════════════════════════════════
# Dividends kind (FA-08) — ex_date from FA-07's cash_dividend events;
# payment_date / cash_per_share not parsed yet (needs disclosure-body tables,
# same gap as FA-06's rights-issue/dividend price factors)
# ════════════════════════════════════════════════════════════════════════════

def _dividend_repo(db_manager: DatabaseManager) -> DividendRepository:
    return DividendRepository(db_manager)


@router.get("/dividends/{instrument}/history")
async def dividends_history(
    instrument: str,
    market: Market = Query(...),
    limit: int = Query(100, ge=1, le=1000),
    cursor: Optional[str] = Query(None),
    contract_version: str = Query(CONTRACT_VERSION),
    db_manager: DatabaseManager = Depends(get_db_manager),
):
    resolved_version = _resolve_contract_version(contract_version)
    repo = _dividend_repo(db_manager)
    try:
        data = repo.get_history(instrument, market.value, limit, cursor, contract_version=resolved_version)
    except DatabaseManager.PoolExhaustedError:
        return _db_error("database temporarily unavailable")
    except Exception as e:  # noqa: BLE001
        logger.error(f"Dividends history failed: {e}", exc_info=True)
        return _db_error(str(e))

    return {
        "contract_version": resolved_version,
        "instrument": data["instrument"],
        "market": data["market"],
        "kind": "dividends",
        "items": data["items"],
        "next_cursor": data["next_cursor"],
    }


# ════════════════════════════════════════════════════════════════════════════
# News kind — KAP/SPK/MKK platform-level announcements (not instrument-keyed)
# ════════════════════════════════════════════════════════════════════════════
# ── list (newest-first, cursor-paginated) — declared before {news_id} ─────────
@router.get("/news")
async def news_list(
    category: Optional[str] = Query(None, description="SPK | MKK | BIST | KAP …"),
    date_from: Optional[str] = Query(None, alias="from"),
    date_to: Optional[str] = Query(None, alias="to"),
    limit: int = Query(50, ge=1, le=1000),
    cursor: Optional[str] = Query(None),
    db_manager: DatabaseManager = Depends(get_db_manager),
):
    repo = _news_repo(db_manager)
    try:
        data = repo.get_list(category, date_from, date_to, limit, cursor)
    except DatabaseManager.PoolExhaustedError:
        return _db_error("database temporarily unavailable")
    except Exception as e:  # noqa: BLE001
        logger.error(f"News list failed: {e}", exc_info=True)
        return _db_error(str(e))

    return {
        "contract_version": CONTRACT_VERSION,
        "kind": "news",
        "items": data["items"],
        "next_cursor": data["next_cursor"],
    }


# ── point (single item by KAP news_id) ────────────────────────────────────────
@router.get("/news/{news_id}")
async def news_point(
    news_id: str,
    db_manager: DatabaseManager = Depends(get_db_manager),
):
    repo = _news_repo(db_manager)
    try:
        return repo.get_point(news_id)
    except DatabaseManager.PoolExhaustedError:
        return _db_error("database temporarily unavailable")
    except Exception as e:  # noqa: BLE001
        logger.error(f"News point failed: {e}", exc_info=True)
        return _db_error(str(e))
