"""
Report query endpoints
"""
import logging
import json
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
            conditions.append("company_name ILIKE %s")
            params.append(f"%{company_code}%")
        
        if start_date:
            conditions.append("disclosure_date >= %s")
            params.append(start_date)
        
        if end_date:
            conditions.append("disclosure_date <= %s")
            params.append(end_date)
        
        if report_type:
            conditions.append("disclosure_type = %s")
            params.append(report_type)
        
        where_clause = " AND ".join(conditions) if conditions else "1=1"
        
        # Get total count
        count_query = f"SELECT COUNT(*) FROM kap_disclosures WHERE {where_clause}"
        conn = db_manager.get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute("SET search_path TO turkish_financial,public;")
            cursor.execute(count_query, params)
            total = cursor.fetchone()[0]
            
            # Get reports
            query = f"""
                SELECT id, company_name, disclosure_type, disclosure_date,
                       content, data, scraped_at
                FROM kap_disclosures
                WHERE {where_clause}
                ORDER BY disclosure_date DESC, scraped_at DESC
                LIMIT %s OFFSET %s
            """
            params.extend([limit, offset])
            cursor.execute(query, params)
            
            reports = []
            for row in cursor.fetchall():
                reports.append(ReportResponse(
                    id=row[0],
                    company_code="",
                    company_name=row[1],
                    report_type=row[2],
                    report_date=row[3],
                    title=None,
                    summary=(row[4][:200] + "...") if row[4] and len(row[4]) > 200 else row[4],
                    data=row[5] if row[5] else None,
                    scraped_at=row[6]
                ))
            
            return ReportsListResponse(
                total=total,
                limit=limit,
                offset=offset,
                reports=reports
            )
        finally:
            db_manager.return_connection(conn)
            
    except DatabaseManager.PoolExhaustedError as e:
        logger.error(f"Database connection pool exhausted when querying reports: {e}")
        raise HTTPException(status_code=503, detail="Database temporarily unavailable, please try again later")
    except Exception as e:
        logger.error(f"Failed to query reports: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/kap/pdf-urls")
async def get_pdf_urls(
    company_name: Optional[str] = Query(None, description="Filter by company name"),
    start_date: Optional[date] = Query(None, description="Start date filter"),
    end_date: Optional[date] = Query(None, description="End date filter"),
    limit: int = Query(100, ge=1, le=1000, description="Number of results"),
    offset: int = Query(0, ge=0, description="Pagination offset"),
    db_manager: DatabaseManager = Depends(get_db_manager)
):
    """
    Get PDF URLs for KAP disclosures
    
    Returns PDF download links for financial disclosures.
    Supports filtering by company name and date range.
    
    Example response:
    ```json
    {
        "total": 10,
        "results": [
            {
                "report_id": 1,
                "disclosure_id": "12345",
                "company_name": "ABC Corp",
                "disclosure_type": "Financial Results",
                "disclosure_date": "2026-01-28",
                "pdf_url": "https://kap.org.tr/tr/BildirimPdf/12345",
                "has_pdf": true
            }
        ]
    }
    ```
    """
    try:
        conn = db_manager.get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute("SET search_path TO turkish_financial,public;")
            
            # Build WHERE conditions
            conditions = []
            params = []
            
            if company_name:
                conditions.append("company_name ILIKE %s")
                params.append(f"%{company_name}%")
            
            if start_date:
                conditions.append("disclosure_date >= %s")
                params.append(start_date)
            
            if end_date:
                conditions.append("disclosure_date <= %s")
                params.append(end_date)
            
            where_clause = " AND ".join(conditions) if conditions else "1=1"
            
            # Get PDF information
            query = f"""
                SELECT 
                    id,
                    disclosure_id,
                    company_name,
                    disclosure_type,
                    disclosure_date,
                    pdf_url,
                    CASE 
                        WHEN pdf_url IS NOT NULL AND pdf_url != '' THEN true 
                        ELSE false 
                    END as has_pdf
                FROM kap_disclosures
                WHERE {where_clause}
                ORDER BY disclosure_date DESC, scraped_at DESC
                LIMIT %s OFFSET %s
            """
            params.extend([limit, offset])
            
            cursor.execute(query, params)
            rows = cursor.fetchall()
            
            results = []
            for row in rows:
                results.append({
                    "report_id": row[0],
                    "disclosure_id": row[1],
                    "company_name": row[2],
                    "disclosure_type": row[3],
                    "disclosure_date": row[4].isoformat() if row[4] else None,
                    "pdf_url": row[5],
                    "has_pdf": row[6]
                })
            
            return {
                "total": len(results),
                "results": results
            }
        finally:
            db_manager.return_connection(conn)
    except Exception as e:
        logger.error(f"Failed to get PDF URLs: {e}", exc_info=True)
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
            cursor.execute("SET search_path TO turkish_financial,public;")
            cursor.execute("""
                SELECT id, company_name, disclosure_type, disclosure_date,
                       content, data, scraped_at
                FROM kap_disclosures
                WHERE id = %s
            """, (report_id,))
            
            row = cursor.fetchone()
            if not row:
                raise HTTPException(status_code=404, detail="Report not found")
            
            return ReportResponse(
                id=row[0],
                company_code="",
                company_name=row[1],
                report_type=row[2],
                report_date=row[3],
                title=None,
                summary=(row[4][:200] + "...") if row[4] and len(row[4]) > 200 else row[4],
                data=row[5] if row[5] else None,
                scraped_at=row[6]
            )
        finally:
            db_manager.return_connection(conn)
            
    except HTTPException:
        raise
    except DatabaseManager.PoolExhaustedError as e:
        logger.error(f"Database connection pool exhausted when getting report: {e}")
        raise HTTPException(status_code=503, detail="Database temporarily unavailable, please try again later")
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
            cursor.execute("SET search_path TO turkish_financial,public;")
            
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
            
    except DatabaseManager.PoolExhaustedError as e:
        logger.error(f"Database connection pool exhausted when getting companies: {e}")
        raise HTTPException(status_code=503, detail="Database temporarily unavailable, please try again later")
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
        conn = db_manager.get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute("SET search_path TO turkish_financial,public;")
            cursor.execute("""
                SELECT 
                    s.overall_sentiment,
                    s.sentiment_score,
                    s.key_sentiments,
                    s.analysis_notes,
                    s.created_at
                FROM kap_disclosure_sentiment s
                WHERE s.disclosure_id = %s
            """, (report_id,))

            sentiment = cursor.fetchone()
            if not sentiment:
                raise HTTPException(status_code=404, detail="Sentiment analysis not found for this report")

            return {
                "report_id": report_id,
                "overall_sentiment": sentiment[0],
                "sentiment_score": sentiment[1],
                "key_sentiments": sentiment[2],
                "analysis_notes": sentiment[3],
                "analyzed_at": sentiment[4].isoformat() if sentiment[4] else None
            }
        finally:
            db_manager.return_connection(conn)
    except HTTPException:
        raise
    except DatabaseManager.PoolExhaustedError as e:
        logger.error(f"Database connection pool exhausted when getting sentiment: {e}")
        raise HTTPException(status_code=503, detail="Database temporarily unavailable, please try again later")
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
        # Validate sentiment filter
        sentiment_filter = None
        if sentiment:
            valid = {"positive", "neutral", "negative"}
            if sentiment.lower() not in valid:
                raise HTTPException(status_code=400, detail=f"Invalid sentiment: {sentiment}")
            sentiment_filter = sentiment.lower()

        conn = db_manager.get_connection()
        try:
            cursor = conn.cursor()

            conditions = ["1=1"]
            params = []

            if company_code:
                conditions.append("d.company_name ILIKE %s")
                params.append(f"%{company_code}%")

            if sentiment_filter:
                conditions.append("s.overall_sentiment = %s")
                params.append(sentiment_filter)

            if start_date:
                conditions.append("d.disclosure_date >= %s")
                params.append(start_date)

            if end_date:
                conditions.append("d.disclosure_date <= %s")
                params.append(end_date)

            where_clause = " AND ".join(conditions)

            query = f"""
                SELECT 
                    d.id,
                    d.company_name,
                    d.disclosure_date,
                    d.disclosure_type,
                    d.pdf_url,
                    s.overall_sentiment,
                    s.sentiment_score,
                    s.key_sentiments,
                    s.analysis_notes,
                    s.created_at
                FROM kap_disclosures d
                JOIN kap_disclosure_sentiment s ON d.id = s.disclosure_id
                WHERE {where_clause}
                ORDER BY s.created_at DESC
                LIMIT %s
            """
            params.append(limit)

            cursor.execute(query, params)
            rows = cursor.fetchall()

            response_results = []
            for row in rows:
                response_results.append({
                    "report_id": row[0],
                    "company_code": "",
                    "company_name": row[1],
                    "report_date": row[2].isoformat() if row[2] else None,
                    "disclosure_type": row[3],
                    "pdf_url": row[4],
                    "has_pdf": bool(row[4] and row[4] != ''),
                    "overall_sentiment": row[5],
                    "sentiment_score": row[6],
                    "key_sentiments": json.loads(row[7]) if row[7] and row[7].startswith('[') else (row[7].split(', ') if row[7] else []),
                    "analysis_notes": row[8],
                    "analyzed_at": row[9].isoformat() if row[9] else None
                })

            return {
                "total": len(response_results),
                "results": response_results
            }
        finally:
            db_manager.return_connection(conn)
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to query sentiment: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))

