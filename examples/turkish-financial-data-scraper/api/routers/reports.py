"""
Report query endpoints
"""
import logging
from fastapi import APIRouter, Depends, HTTPException, Query
from typing import Optional, List
from datetime import date
from psycopg2.extras import RealDictCursor

from api.models import (
    QueryReportsRequest, ReportResponse, ReportsListResponse
)
from api.dependencies import get_db_manager
from database.db_manager import DatabaseManager

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/reports", tags=["reports"])


@router.get("/kap", response_model=ReportsListResponse)
async def get_kap_reports(
    company_code: Optional[str] = Query(None, description="Filter by company code"),
    start_date: Optional[date] = Query(None, description="Start date filter"),
    end_date: Optional[date] = Query(None, description="End date filter"),
    report_type: Optional[str] = Query(None, description="Filter by report type"),
    limit: int = Query(100, ge=1, le=1000, description="Number of results"),
    offset: int = Query(0, ge=0, description="Pagination offset"),
    db_manager: DatabaseManager = Depends(get_db_manager)
):
    """
    Query KAP reports from database
    
    Supports filtering by:
    - Company code
    - Date range
    - Report type
    """
    try:
        # Build WHERE clause
        conditions = []
        params = []
        
        if company_code:
            conditions.append("company_code = %s")
            params.append(company_code)
        
        if start_date:
            conditions.append("report_date >= %s")
            params.append(start_date)
        
        if end_date:
            conditions.append("report_date <= %s")
            params.append(end_date)
        
        if report_type:
            conditions.append("report_type = %s")
            params.append(report_type)
        
        where_clause = " AND ".join(conditions) if conditions else "1=1"
        
        # Get total count
        count_query = f"SELECT COUNT(*) FROM kap_reports WHERE {where_clause}"
        conn = db_manager.get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute(count_query, params)
            total = cursor.fetchone()[0]
            
            # Get reports
            query = f"""
                SELECT id, company_code, company_name, report_type, report_date,
                       title, summary, data, scraped_at
                FROM kap_reports
                WHERE {where_clause}
                ORDER BY report_date DESC, scraped_at DESC
                LIMIT %s OFFSET %s
            """
            params.extend([limit, offset])
            cursor.execute(query, params)
            
            reports = []
            for row in cursor.fetchall():
                reports.append(ReportResponse(
                    id=row[0],
                    company_code=row[1] or "",
                    company_name=row[2],
                    report_type=row[3],
                    report_date=row[4],
                    title=row[5],
                    summary=row[6],
                    data=row[7] if row[7] else None,
                    scraped_at=row[8]
                ))
            
            return ReportsListResponse(
                total=total,
                limit=limit,
                offset=offset,
                reports=reports
            )
        finally:
            db_manager.return_connection(conn)
            
    except Exception as e:
        logger.error(f"Failed to query reports: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/kap/{report_id}", response_model=ReportResponse)
async def get_kap_report(
    report_id: int,
    db_manager: DatabaseManager = Depends(get_db_manager)
):
    """
    Get a specific KAP report by ID
    """
    try:
        conn = db_manager.get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT id, company_code, company_name, report_type, report_date,
                       title, summary, data, scraped_at
                FROM kap_reports
                WHERE id = %s
            """, (report_id,))
            
            row = cursor.fetchone()
            if not row:
                raise HTTPException(status_code=404, detail="Report not found")
            
            return ReportResponse(
                id=row[0],
                company_code=row[1] or "",
                company_name=row[2],
                report_type=row[3],
                report_date=row[4],
                title=row[5],
                summary=row[6],
                data=row[7] if row[7] else None,
                scraped_at=row[8]
            )
        finally:
            db_manager.return_connection(conn)
            
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get report: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/companies", response_model=List[dict])
async def get_companies(
    sector: Optional[str] = Query(None, description="Filter by sector"),
    limit: int = Query(100, ge=1, le=1000),
    db_manager: DatabaseManager = Depends(get_db_manager)
):
    """
    Get list of companies from BIST
    """
    try:
        conn = db_manager.get_connection()
        try:
            cursor = conn.cursor()
            
            if sector:
                query = """
                    SELECT DISTINCT code, name, sector
                    FROM bist_companies
                    WHERE sector = %s
                    ORDER BY name
                    LIMIT %s
                """
                cursor.execute(query, (sector, limit))
            else:
                query = """
                    SELECT DISTINCT code, name, sector
                    FROM bist_companies
                    ORDER BY name
                    LIMIT %s
                """
                cursor.execute(query, (limit,))
            
            companies = []
            for row in cursor.fetchall():
                companies.append({
                    "code": row[0],
                    "name": row[1],
                    "sector": row[2]
                })
            
            return companies
        finally:
            db_manager.return_connection(conn)
            
    except Exception as e:
        logger.error(f"Failed to get companies: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/kap/{report_id}/sentiment")
async def get_report_sentiment(
    report_id: int,
    db_manager: DatabaseManager = Depends(get_db_manager)
):
    """
    Get sentiment analysis for a specific KAP report
    """
    try:
        from infrastructure.repositories.sentiment_repository_impl import SentimentRepository
        
        # Use DDD repository
        sentiment_repo = SentimentRepository(db_manager)
        sentiment = await sentiment_repo.find_by_report_id(report_id)
        
        if not sentiment:
            raise HTTPException(status_code=404, detail="Sentiment analysis not found for this report")
        
        # Convert value object to dict for response
        return {
            "report_id": report_id,
            "overall_sentiment": sentiment.overall_sentiment.value,
            "confidence": sentiment.confidence.value,
            "impact_horizon": sentiment.impact_horizon.value,
            "key_drivers": list(sentiment.key_drivers),
            "risk_flags": list(sentiment.risk_flags),
            "tone_descriptors": list(sentiment.tone_descriptors),
            "target_audience": sentiment.target_audience,
            "analysis_text": sentiment.analysis_text,
            "analyzed_at": sentiment.analyzed_at.isoformat()
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get sentiment: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/kap/sentiment/query")
async def query_sentiment(
    company_code: Optional[str] = None,
    sentiment: Optional[str] = None,
    start_date: Optional[date] = None,
    end_date: Optional[date] = None,
    limit: int = Query(100, ge=1, le=1000),
    db_manager: DatabaseManager = Depends(get_db_manager)
):
    """
    Query sentiment data with filters
    
    - **company_code**: Filter by company code
    - **sentiment**: Filter by sentiment (positive/neutral/negative)
    - **start_date**: Start date filter (YYYY-MM-DD)
    - **end_date**: End date filter (YYYY-MM-DD)
    - **limit**: Maximum results
    """
    try:
        from infrastructure.repositories.sentiment_repository_impl import SentimentRepository
        from domain.value_objects.sentiment import SentimentType
        
        # Use DDD repository
        sentiment_repo = SentimentRepository(db_manager)
        
        # Convert string to enum
        sentiment_type = None
        if sentiment:
            try:
                sentiment_type = SentimentType(sentiment.lower())
            except ValueError:
                raise HTTPException(status_code=400, detail=f"Invalid sentiment: {sentiment}")
        
        results = await sentiment_repo.find_by_filters(
            company_code=company_code,
            sentiment_type=sentiment_type,
            start_date=start_date,
            end_date=end_date,
            limit=limit
        )
        
        # Convert to response format
        response_results = []
        for report, sentiment_vo in results:
            response_results.append({
                "report_id": report.id,
                "company_code": report.company_code,
                "company_name": report.company_name,
                "report_date": report.report_date.isoformat() if report.report_date else None,
                "overall_sentiment": sentiment_vo.overall_sentiment.value,
                "confidence": sentiment_vo.confidence.value,
                "impact_horizon": sentiment_vo.impact_horizon.value,
                "key_drivers": list(sentiment_vo.key_drivers),
                "risk_flags": list(sentiment_vo.risk_flags),
                "analyzed_at": sentiment_vo.analyzed_at.isoformat()
            })
        
        return {
            "total": len(response_results),
            "results": response_results
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to query sentiment: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))
