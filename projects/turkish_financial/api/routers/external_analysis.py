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
from typing import List, Optional

import requests
from fastapi import APIRouter, Depends, Query
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from api.dependencies import get_db_manager
from database.db_manager import DatabaseManager
from domain.entities.external_analysis import (
    CONTRACT_VERSION,
    Market,
)
from infrastructure.repositories.external_analysis_repository import (
    PROVIDER_ID,
    ExternalAnalysisRepository,
)
from infrastructure.repositories.fundamental_repository import FundamentalRepository
from infrastructure.repositories.news_repository import NewsRepository
from infrastructure.contracts.instrument_identity_map import STATIC_BIST_CATALOG
from scrapers.isyatirim_market_data import build_market_history_payload, fetch_market_history
from scrapers.isyatirim_fundamentals import fetch_fundamentals

logger = logging.getLogger(__name__)

router = APIRouter(tags=["external-analysis"])

_fundamental_collection_task = None
_fundamental_collection_state = {"status": "idle", "total": 0, "completed": 0, "fetched": 0, "cached": 0, "failed": 0, "started_at": None, "finished_at": None}


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


class FundamentalsCollectionRequest(BaseModel):
    force: bool = False


def _repo(db_manager: DatabaseManager) -> ExternalAnalysisRepository:
    return ExternalAnalysisRepository(db_manager)


def _fund_repo(db_manager: DatabaseManager) -> FundamentalRepository:
    return FundamentalRepository(db_manager)


def _news_repo(db_manager: DatabaseManager) -> NewsRepository:
    return NewsRepository(db_manager)


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
    """
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
                (hn.ticker IS NOT NULL)   AS has_news_sentiment
            FROM all_tickers t
            LEFT JOIN has_sentiment   hs ON hs.ticker = t.ticker
            LEFT JOIN has_fundamental hf ON hf.ticker = t.ticker
            LEFT JOIN has_news_sentiment hn ON hn.ticker = t.ticker
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

    return {
        "status": "ok" if db_ok else "degraded",
        "contract_version": CONTRACT_VERSION,
        "provider": PROVIDER_ID,
    }


@router.get("/capabilities")
async def capabilities():
    """Return only runtime-confirmed Firecrawl capabilities for external clients."""
    return {
        "contract_version": CONTRACT_VERSION,
        "provider": PROVIDER_ID,
        "firecrawl": _firecrawl_capabilities(),
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

    return {"contract_version": CONTRACT_VERSION, "items": items}


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
        "contract_version": CONTRACT_VERSION,
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

async def _on_demand_fundamental_fetch(
    instrument: str,
    db_manager: DatabaseManager,
    repo,
    market: str,
    as_of: Optional[str] = None,
) -> dict:
    """Trigger a live KAP scrape for *instrument* and re-query the repo.

    Called when the DB has no row for the ticker.  Best-effort: if the scrape
    fails we still return the unavailable envelope rather than raising.

    If the instrument's mkkMemberOid is not yet known, calls refresh_member_oids
    first to populate it from KAP's member API, then retries the scrape.
    """
    from scrapers.kap_scraper import KAPScraper
    from infrastructure.contracts.instrument_identity_map import resolve_member_oid

    logger.info(
        "fundamental data for %s not in DB — triggering on-demand KAP fetch",
        instrument,
    )
    try:
        scraper = KAPScraper(db_manager=db_manager)

        # If OID is unknown, try to discover all OIDs before scraping.
        if resolve_member_oid(instrument, db_manager=db_manager) is None:
            logger.info(
                "mkkMemberOid for %s unknown — running refresh_member_oids first",
                instrument,
            )
            try:
                await scraper.refresh_member_oids()
            except Exception as exc:
                logger.warning("refresh_member_oids failed: %s", exc)
            # If POST-based refresh failed, try the GET-based fallback.
            if resolve_member_oid(instrument, db_manager=db_manager) is None:
                try:
                    await scraper.refresh_member_oids_via_get(instruments=[instrument])
                except Exception as exc:
                    logger.warning("refresh_member_oids_via_get failed: %s", exc)

        await scraper.scrape_financial_statements(instruments=[instrument])
    except Exception as exc:
        logger.warning(
            "on-demand KAP fetch for %s failed: %s", instrument, exc
        )
    return repo.get_point(instrument, market, as_of)


# ── batch (§6.2) ──────────────────────────────────────────────────────────────
@router.post("/fundamental/batch")
async def fundamental_batch(
    request: FundamentalBatchRequest,
    db_manager: DatabaseManager = Depends(get_db_manager),
):
    repo = _fund_repo(db_manager)
    items = []
    try:
        for instrument in request.instruments:
            point = repo.get_point(instrument, request.market.value, request.as_of)
            if point.get("status") == "unavailable" and request.as_of is None:
                point = await _on_demand_fundamental_fetch(
                    instrument, db_manager, repo, request.market.value
                )
            items.append(point)
    except DatabaseManager.PoolExhaustedError:
        return _db_error("database temporarily unavailable")
    except Exception as e:  # noqa: BLE001
        logger.error(f"Batch fundamental failed: {e}", exc_info=True)
        return _db_error(str(e))

    return {"contract_version": CONTRACT_VERSION, "items": items}


# ── history (§6.3) — static suffix before {instrument} point ──────────────────
@router.get("/fundamental/{instrument}/history")
async def fundamental_history(
    instrument: str,
    market: Market = Query(...),
    date_from: Optional[str] = Query(None, alias="from"),
    date_to: Optional[str] = Query(None, alias="to"),
    limit: int = Query(100, ge=1, le=1000),
    cursor: Optional[str] = Query(None),
    db_manager: DatabaseManager = Depends(get_db_manager),
):
    repo = _fund_repo(db_manager)
    try:
        data = repo.get_history(
            instrument, market.value, date_from, date_to, limit, cursor
        )
    except DatabaseManager.PoolExhaustedError:
        return _db_error("database temporarily unavailable")
    except Exception as e:  # noqa: BLE001
        logger.error(f"Fundamental history failed: {e}", exc_info=True)
        return _db_error(str(e))

    return {
        "contract_version": CONTRACT_VERSION,
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
    db_manager: DatabaseManager = Depends(get_db_manager),
):
    repo = _fund_repo(db_manager)
    try:
        result = repo.get_point(instrument, market.value, as_of)
        if result.get("status") == "unavailable" and as_of is None:
            result = await _on_demand_fundamental_fetch(instrument, db_manager, repo, market.value)
        return result
    except DatabaseManager.PoolExhaustedError:
        return _db_error("database temporarily unavailable")
    except Exception as e:  # noqa: BLE001
        logger.error(f"Fundamental point failed: {e}", exc_info=True)
        return _db_error(str(e))


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
