import logging
from typing import Optional, List, Dict, Any

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from api.dependencies import get_db_manager
from database.db_manager import DatabaseManager

logger = logging.getLogger(__name__)

router = APIRouter(tags=["analytics"])

class CorrelationResponse(BaseModel):
    success: bool
    symbol: str
    data: List[Dict[str, Any]]

@router.get("/analytics/correlation/{symbol}", response_model=CorrelationResponse)
async def get_correlation(
    symbol: str,
    days: int = Query(30, description="Number of days to fetch"),
    indicator: Optional[str] = Query(None, description="TCMB indicator code"),
    db_manager: DatabaseManager = Depends(get_db_manager)
):
    """Fetch correlated time-series data for a symbol (prices, sentiment, macro)."""
    try:
        # Fetch sentiment
        sentiment_rows = db_manager.query(
            "SELECT period_date, combined_score, news_score, social_score, youtube_score FROM aggregated_ticker_sentiment WHERE ticker = %s ORDER BY period_date DESC LIMIT %s",
            (symbol.upper(), days)
        )
        
        # Fetch prices
        price_rows = db_manager.query(
            "SELECT market_date, data FROM isyatirim_market_history WHERE ticker = %s ORDER BY market_date DESC LIMIT %s",
            (symbol.upper(), days)
        )
        
        # Fetch TCMB if indicator is provided
        tcmb_rows = []
        if indicator:
            tcmb_rows = db_manager.query(
                "SELECT date, value FROM tcmb_macro_data WHERE indicator_code = %s ORDER BY date DESC LIMIT %s",
                (indicator, days)
            )
            
        # Group by date
        data_by_date = {}
        
        for r in sentiment_rows:
            if not r["period_date"]:
                continue
            d_str = r["period_date"].strftime("%Y-%m-%d")
            data_by_date.setdefault(d_str, {})["sentiment"] = {
                "combined_score": r["combined_score"],
                "news_score": r["news_score"],
                "social_score": r["social_score"],
                "youtube_score": r["youtube_score"]
            }
            
        for r in price_rows:
            if not r["market_date"]:
                continue
            d_str = r["market_date"].strftime("%Y-%m-%d")
            data_by_date.setdefault(d_str, {})["price"] = r["data"]
            
        for r in tcmb_rows:
            if not r["date"]:
                continue
            d_str = r["date"].strftime("%Y-%m-%d")
            data_by_date.setdefault(d_str, {})["tcmb"] = r["value"]
            
        # Convert to list
        results = []
        for date_str in sorted(data_by_date.keys(), reverse=True):
            entry = {"date": date_str}
            entry.update(data_by_date[date_str])
            results.append(entry)
            
        return CorrelationResponse(success=True, symbol=symbol.upper(), data=results)
        
    except Exception as e:
        logger.error(f"Failed to fetch correlation for {symbol}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Internal server error")
