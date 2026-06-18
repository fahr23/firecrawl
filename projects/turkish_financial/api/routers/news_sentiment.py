"""
News-portal sentiment — Data Contract v1.0 HTTP surface.

Exposes institutional/macro sentiment derived from Turkish financial news portals
(Bloomberg HT, Foreks, Mynet Finans, Bigpara, Investing.com TR), aggregated daily per
BIST ticker. Same envelope shape (§1/§2) as the KAP sentiment endpoints, but
`provider = "news-portal-scraper"`.

    GET  {base}/news-sentiment/{instrument}?market=&as_of=
    GET  {base}/news-sentiment/{instrument}/history?market=&from=&to=&limit=&cursor=
    POST {base}/news-sentiment/collect   (trigger a scrape+analyse+aggregate run)

Mounted at `/api/external/v1` (see api/main.py). On DB failure we degrade to an honest
error/unavailable envelope (§5).
"""
import logging
import os
from typing import List, Optional

from fastapi import APIRouter, Depends, Query
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from api.dependencies import get_db_manager
from database.db_manager import DatabaseManager
from domain.entities.external_analysis import CONTRACT_VERSION, Market
from infrastructure.repositories.news_article_repository import (
    AggregateSentimentRepository,
    NewsArticleRepository,
    SocialSentimentRepository,
    CombinedSentimentRepository,
)

logger = logging.getLogger(__name__)

router = APIRouter(tags=["news-sentiment"])


class NewsCollectRequest(BaseModel):
    """Body for the news collect trigger."""

    tickers: Optional[List[str]] = None
    days_back: int = Field(default=7, ge=1, le=90)
    sources: Optional[List[str]] = None
    include_investing_comments: bool = True


class SocialCollectRequest(BaseModel):
    """Body for the social (X/FinTwit) collect trigger."""

    tickers: List[str] = Field(..., min_length=1)
    days_back: int = Field(default=7, ge=1, le=90)
    limit_per_ticker: int = Field(default=30, ge=1, le=200)


def _repo(db_manager: DatabaseManager) -> NewsArticleRepository:
    return NewsArticleRepository(db_manager)


def _db_error(detail: str) -> JSONResponse:
    return JSONResponse(
        status_code=503,
        content={
            "contract_version": CONTRACT_VERSION,
            "status": "unavailable",
            "error_code": "UPSTREAM_DB_ERROR",
            "detail": detail,
        },
    )


def _build_sentiment_analyzer():
    """
    Build a SentimentAnalyzerService from whatever LLM provider is configured.

    Order: Gemini (GEMINI_API_KEY/GOOGLE_API_KEY) → OpenAI (OPENAI_API_KEY) → local
    LM Studio/Ollama. Heavy imports are deferred to here so reading endpoints stay light.
    """
    from infrastructure.services.sentiment_analyzer_impl import SentimentAnalyzerService
    from utils.llm_analyzer import GeminiProvider, OpenAIProvider, LocalLLMProvider

    gemini_key = os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")
    if gemini_key:
        provider = GeminiProvider(api_key=gemini_key)
    elif os.getenv("OPENAI_API_KEY"):
        provider = OpenAIProvider(api_key=os.getenv("OPENAI_API_KEY"))
    else:
        provider = LocalLLMProvider(
            base_url=os.getenv("LOCAL_LLM_BASE_URL", "http://localhost:1234/v1")
        )
    return SentimentAnalyzerService(provider)


# ── collect trigger — declared before {instrument} ───────────────────────────
@router.post("/news-sentiment/collect")
async def news_sentiment_collect(
    request: NewsCollectRequest,
    db_manager: DatabaseManager = Depends(get_db_manager),
):
    """Run the news-portal sentiment pipeline (scrape → analyse → persist → aggregate)."""
    from scrapers.news_portal_scraper import NewsPortalScraper
    from application.use_cases.collect_news_sentiment_use_case import (
        CollectNewsSentimentUseCase,
    )

    try:
        scraper = NewsPortalScraper(db_manager=db_manager)
        analyzer = _build_sentiment_analyzer()
        use_case = CollectNewsSentimentUseCase(scraper, analyzer, db_manager)
        result = await use_case.execute(
            tickers=request.tickers,
            days_back=request.days_back,
            sources=request.sources,
            include_investing_comments=request.include_investing_comments,
        )
        return {"contract_version": CONTRACT_VERSION, **result}
    except DatabaseManager.PoolExhaustedError:
        return _db_error("database temporarily unavailable")
    except Exception as e:  # noqa: BLE001
        logger.error(f"News sentiment collect failed: {e}", exc_info=True)
        return JSONResponse(
            status_code=500,
            content={"contract_version": CONTRACT_VERSION, "status": "error", "detail": str(e)},
        )


# ── history — static suffix before {instrument} point ────────────────────────
@router.get("/news-sentiment/{instrument}/history")
async def news_sentiment_history(
    instrument: str,
    market: Market = Query(...),
    date_from: Optional[str] = Query(None, alias="from"),
    date_to: Optional[str] = Query(None, alias="to"),
    limit: int = Query(100, ge=1, le=1000),
    cursor: Optional[str] = Query(None),
    db_manager: DatabaseManager = Depends(get_db_manager),
):
    return _serve_history(
        _repo(db_manager), instrument, market, date_from, date_to, limit, cursor,
    )


# ── point — most general route, declared last ─────────────────────────────────
@router.get("/news-sentiment/{instrument}")
async def news_sentiment_point(
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
        logger.error(f"News sentiment point failed: {e}", exc_info=True)
        return _db_error(str(e))


# ════════════════════════════════════════════════════════════════════════════
# Generic point/history serving (shared by social + combined views)
# ════════════════════════════════════════════════════════════════════════════
def _serve_point(repo: AggregateSentimentRepository, instrument, market, as_of):
    try:
        return repo.get_point(instrument, market.value, as_of)
    except DatabaseManager.PoolExhaustedError:
        return _db_error("database temporarily unavailable")
    except Exception as e:  # noqa: BLE001
        logger.error(f"Sentiment point failed: {e}", exc_info=True)
        return _db_error(str(e))


def _serve_history(repo: AggregateSentimentRepository, instrument, market,
                   date_from, date_to, limit, cursor):
    try:
        data = repo.get_history(instrument, market.value, date_from, date_to, limit, cursor)
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
        "provider": repo._PROVIDER,
        "items": data["items"],
        "next_cursor": data["next_cursor"],
    }


# ════════════════════════════════════════════════════════════════════════════
# Social (X / FinTwit) — Phase 2
# ════════════════════════════════════════════════════════════════════════════
@router.post("/social-sentiment/collect")
async def social_sentiment_collect(
    request: SocialCollectRequest,
    db_manager: DatabaseManager = Depends(get_db_manager),
):
    """Run the X/FinTwit sentiment pipeline (scrape → analyse → persist → blend)."""
    from scrapers.social_media_scraper import SocialMediaScraper
    from application.use_cases.collect_social_sentiment_use_case import (
        CollectSocialSentimentUseCase,
    )

    try:
        scraper = SocialMediaScraper(db_manager=db_manager)
        analyzer = _build_sentiment_analyzer()
        use_case = CollectSocialSentimentUseCase(scraper, analyzer, db_manager)
        result = await use_case.execute(
            tickers=request.tickers,
            days_back=request.days_back,
            limit_per_ticker=request.limit_per_ticker,
        )
        return {"contract_version": CONTRACT_VERSION, **result}
    except DatabaseManager.PoolExhaustedError:
        return _db_error("database temporarily unavailable")
    except Exception as e:  # noqa: BLE001
        logger.error(f"Social sentiment collect failed: {e}", exc_info=True)
        return JSONResponse(
            status_code=500,
            content={"contract_version": CONTRACT_VERSION, "status": "error", "detail": str(e)},
        )


@router.get("/social-sentiment/{instrument}/history")
async def social_sentiment_history(
    instrument: str,
    market: Market = Query(...),
    date_from: Optional[str] = Query(None, alias="from"),
    date_to: Optional[str] = Query(None, alias="to"),
    limit: int = Query(100, ge=1, le=1000),
    cursor: Optional[str] = Query(None),
    db_manager: DatabaseManager = Depends(get_db_manager),
):
    return _serve_history(
        SocialSentimentRepository(db_manager), instrument, market,
        date_from, date_to, limit, cursor,
    )


@router.get("/social-sentiment/{instrument}")
async def social_sentiment_point(
    instrument: str,
    market: Market = Query(...),
    as_of: Optional[str] = Query(None),
    db_manager: DatabaseManager = Depends(get_db_manager),
):
    return _serve_point(SocialSentimentRepository(db_manager), instrument, market, as_of)


# ════════════════════════════════════════════════════════════════════════════
# Combined (0.6·news + 0.4·social)
# ════════════════════════════════════════════════════════════════════════════
@router.get("/combined-sentiment/{instrument}/history")
async def combined_sentiment_history(
    instrument: str,
    market: Market = Query(...),
    date_from: Optional[str] = Query(None, alias="from"),
    date_to: Optional[str] = Query(None, alias="to"),
    limit: int = Query(100, ge=1, le=1000),
    cursor: Optional[str] = Query(None),
    db_manager: DatabaseManager = Depends(get_db_manager),
):
    return _serve_history(
        CombinedSentimentRepository(db_manager), instrument, market,
        date_from, date_to, limit, cursor,
    )


@router.get("/combined-sentiment/{instrument}")
async def combined_sentiment_point(
    instrument: str,
    market: Market = Query(...),
    as_of: Optional[str] = Query(None),
    db_manager: DatabaseManager = Depends(get_db_manager),
):
    return _serve_point(CombinedSentimentRepository(db_manager), instrument, market, as_of)
