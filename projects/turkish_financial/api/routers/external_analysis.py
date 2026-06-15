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
from typing import List, Optional

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

logger = logging.getLogger(__name__)

router = APIRouter(tags=["external-analysis"])


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
            items.append(
                repo.get_point(instrument, request.market.value, request.as_of)
            )
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
        return repo.get_point(instrument, market.value, as_of)
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
