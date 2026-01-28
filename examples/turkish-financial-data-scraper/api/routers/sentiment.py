"""
Sentiment Analysis API endpoints for Turkish Financial Data
Supports both Keyword-Based and HuggingFace BERT analyzers
"""
import logging
import json
from fastapi import APIRouter, Depends, HTTPException, Query
from typing import Optional, List, Dict, Any
from datetime import date, datetime
import asyncio

from api.models import (
    SentimentAnalysisRequest, SentimentAnalysisResponse, 
    AutoSentimentRequest, ScrapeResponse
)
from api.dependencies import get_db_manager
from database.db_manager import DatabaseManager
from production_kap_final import ProductionKAPScraper
from utils.llm_analyzer import HuggingFaceLocalProvider, LLMAnalyzer

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/sentiment", tags=["sentiment"])


@router.get("/")
async def get_sentiment_overview(
    db_manager: DatabaseManager = Depends(get_db_manager)
):
    """
    Get overview of sentiment analysis data
    
    Returns statistics and summary of available sentiment analysis
    """
    try:
        conn = db_manager.get_connection()
        cursor = conn.cursor()
        
        # Set search path
        cursor.execute("SET search_path TO turkish_financial,public;")
        
        # Get sentiment statistics
        cursor.execute("""
            SELECT 
                COUNT(*) as total_analyses,
                COUNT(DISTINCT disclosure_id) as unique_disclosures,
                AVG(sentiment_score) as avg_sentiment_score,
                COUNT(CASE WHEN overall_sentiment = 'positive' THEN 1 END) as positive_count,
                COUNT(CASE WHEN overall_sentiment = 'neutral' THEN 1 END) as neutral_count,
                COUNT(CASE WHEN overall_sentiment = 'negative' THEN 1 END) as negative_count,
                MAX(created_at) as latest_analysis
            FROM kap_disclosure_sentiment
        """)
        
        stats = cursor.fetchone()
        
        # Get recent sentiment trends
        cursor.execute("""
            SELECT 
                DATE(created_at) as analysis_date,
                overall_sentiment,
                COUNT(*) as count
            FROM kap_disclosure_sentiment
            WHERE created_at >= CURRENT_DATE - INTERVAL '30 days'
            GROUP BY DATE(created_at), overall_sentiment
            ORDER BY analysis_date DESC, overall_sentiment
            LIMIT 90
        """)
        
        trends = cursor.fetchall()
        
        # Get top companies by analysis volume
        cursor.execute("""
            SELECT 
                d.company_name,
                COUNT(*) as analysis_count,
                AVG(s.sentiment_score) as avg_sentiment_score,
                MAX(s.created_at) as latest_analysis
            FROM kap_disclosure_sentiment s
            JOIN kap_disclosures d ON s.disclosure_id = d.id
            GROUP BY d.company_name
            ORDER BY analysis_count DESC
            LIMIT 10
        """)
        
        top_companies = cursor.fetchall()
        
        cursor.close()
        db_manager.return_connection(conn)
        
        return {
            "success": True,
            "data": {
                "overview": {
                    "total_analyses": stats[0],
                    "unique_disclosures": stats[1],
                    "average_sentiment_score": round(stats[2] or 0, 3),
                    "sentiment_distribution": {
                        "positive": stats[3],
                        "neutral": stats[4], 
                        "negative": stats[5]
                    },
                    "latest_analysis": stats[6]
                },
                "trends": [
                    {
                        "date": trend[0],
                        "sentiment": trend[1],
                        "count": trend[2]
                    } for trend in trends
                ],
                "top_companies": [
                    {
                        "company_name": company[0],
                        "analysis_count": company[1],
                        "avg_sentiment_score": round(company[2], 3),
                        "latest_analysis": company[3]
                    } for company in top_companies
                ]
            },
            "timestamp": datetime.now().isoformat()
        }
        
    except DatabaseManager.PoolExhaustedError as e:
        logger.error(f"Database connection pool exhausted when getting sentiment overview: {e}")
        raise HTTPException(status_code=503, detail="Database temporarily unavailable, please try again later")
    except Exception as e:
        logger.error(f"Error getting sentiment overview: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/disclosures/{disclosure_id}")
async def get_disclosure_sentiment(
    disclosure_id: int,
    db_manager: DatabaseManager = Depends(get_db_manager)
):
    """
    Get sentiment analysis for a specific disclosure
    
    - **disclosure_id**: Database ID of the disclosure
    """
    try:
        conn = db_manager.get_connection()
        cursor = conn.cursor()
        
        # Set search path
        cursor.execute("SET search_path TO turkish_financial,public;")
        
        cursor.execute("""
            SELECT 
                d.disclosure_id,
                d.company_name,
                d.disclosure_type,
                d.disclosure_date,
                d.content,
                s.overall_sentiment,
                s.sentiment_score,
                s.key_sentiments,
                s.analysis_notes,
                s.created_at
            FROM kap_disclosures d
            LEFT JOIN kap_disclosure_sentiment s ON d.id = s.disclosure_id
            WHERE d.id = %s
        """, (disclosure_id,))
        
        result = cursor.fetchone()
        cursor.close()
        db_manager.return_connection(conn)
        
        if not result:
            raise HTTPException(status_code=404, detail="Disclosure not found")
        
        return {
            "success": True,
            "data": {
                "disclosure": {
                    "id": disclosure_id,
                    "disclosure_id": result[0],
                    "company_name": result[1],
                    "disclosure_type": result[2],
                    "disclosure_date": result[3],
                    "content": result[4][:500] + "..." if len(result[4]) > 500 else result[4]
                },
                "sentiment": {
                    "overall_sentiment": result[5],
                    "sentiment_score": result[6],
                    "key_sentiments": result[7],
                    "analysis_notes": result[8],
                    "analyzed_at": result[9]
                } if result[5] else None
            },
            "timestamp": datetime.now().isoformat()
        }
        
    except HTTPException:
        raise
    except DatabaseManager.PoolExhaustedError as e:
        logger.error(f"Database connection pool exhausted when getting disclosure sentiment: {e}")
        raise HTTPException(status_code=503, detail="Database temporarily unavailable, please try again later")
    except DatabaseManager.PoolExhaustedError as e:
        logger.error(f"Database connection pool exhausted when getting disclosure sentiment: {e}")
        raise HTTPException(status_code=503, detail="Database temporarily unavailable, please try again later")
    except Exception as e:
        logger.error(f"Error getting disclosure sentiment: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/company/{company_name}")
async def get_company_sentiment_history(
    company_name: str,
    limit: int = Query(50, ge=1, le=200, description="Number of results"),
    days_back: int = Query(30, ge=1, le=365, description="Days to look back"),
    db_manager: DatabaseManager = Depends(get_db_manager)
):
    """
    Get sentiment analysis history for a specific company
    
    - **company_name**: Name of the company
    - **limit**: Maximum number of results
    - **days_back**: Number of days to look back
    """
    try:
        conn = db_manager.get_connection()
        cursor = conn.cursor()
        
        # Set search path
        cursor.execute("SET search_path TO turkish_financial,public;")
        
        cursor.execute("""
            SELECT 
                d.disclosure_id,
                d.disclosure_type,
                d.disclosure_date,
                s.overall_sentiment,
                s.sentiment_score,
                s.key_sentiments,
                s.analysis_notes,
                s.created_at
            FROM kap_disclosures d
            JOIN kap_disclosure_sentiment s ON d.id = s.disclosure_id
            WHERE d.company_name = %s 
                AND s.created_at >= CURRENT_DATE - INTERVAL '%s days'
            ORDER BY s.created_at DESC
            LIMIT %s
        """, (company_name, days_back, limit))
        
        results = cursor.fetchall()
        
        # Get company sentiment summary
        cursor.execute("""
            SELECT 
                COUNT(*) as total_analyses,
                AVG(sentiment_score) as avg_sentiment_score,
                COUNT(CASE WHEN overall_sentiment = 'positive' THEN 1 END) as positive_count,
                COUNT(CASE WHEN overall_sentiment = 'neutral' THEN 1 END) as neutral_count,
                COUNT(CASE WHEN overall_sentiment = 'negative' THEN 1 END) as negative_count
            FROM kap_disclosures d
            JOIN kap_disclosure_sentiment s ON d.id = s.disclosure_id
            WHERE d.company_name = %s 
                AND s.created_at >= CURRENT_DATE - INTERVAL '%s days'
        """, (company_name, days_back))
        
        summary = cursor.fetchone()
        
        cursor.close()
        db_manager.return_connection(conn)
        
        return {
            "success": True,
            "data": {
                "company_name": company_name,
                "period": f"Last {days_back} days",
                "summary": {
                    "total_analyses": summary[0],
                    "average_sentiment_score": round(summary[1] or 0, 3),
                    "sentiment_distribution": {
                        "positive": summary[2],
                        "neutral": summary[3],
                        "negative": summary[4]
                    }
                },
                "sentiment_history": [
                    {
                        "disclosure_id": result[0],
                        "disclosure_type": result[1],
                        "disclosure_date": result[2],
                        "sentiment": {
                            "overall_sentiment": result[3],
                            "sentiment_score": result[4],
                            "key_sentiments": result[5],
                            "analysis_notes": result[6],
                            "analyzed_at": result[7]
                        }
                    } for result in results
                ]
            },
            "timestamp": datetime.now().isoformat()
        }
        
    except DatabaseManager.PoolExhaustedError as e:
        logger.error(f"Database connection pool exhausted when getting company sentiment history: {e}")
        raise HTTPException(status_code=503, detail="Database temporarily unavailable, please try again later")
    except Exception as e:
        logger.error(f"Error getting company sentiment history: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/analyze", response_model=SentimentAnalysisResponse)
async def analyze_sentiment_bulk(
    request: SentimentAnalysisRequest,
    db_manager: DatabaseManager = Depends(get_db_manager)
):
    """
    Perform sentiment analysis on specific disclosures
    
    - **report_ids**: List of disclosure database IDs to analyze
    - **analyzer_type**: 'keyword' (fast, default) or 'huggingface' (accurate)
    - **custom_prompt**: Optional custom prompt for analysis
    """
    try:
        # Determine LLM provider based on analyzer_type
        use_llm = request.analyzer_type == "huggingface"
        llm_provider = "huggingface" if use_llm else None
        
        # Initialize production scraper with selected analyzer
        scraper = ProductionKAPScraper(use_test_data=False, use_llm=use_llm, llm_provider=llm_provider)
        
        conn = db_manager.get_connection()
        cursor = conn.cursor()
        
        # Set search path
        cursor.execute("SET search_path TO turkish_financial,public;")
        
        successful = 0
        failed = 0
        results = []
        
        for report_id in request.report_ids:
            try:
                # Get disclosure data
                cursor.execute("""
                    SELECT id, disclosure_id, company_name, disclosure_type, content
                    FROM kap_disclosures WHERE id = %s
                """, (report_id,))
                
                disclosure = cursor.fetchone()
                if not disclosure:
                    failed += 1
                    results.append({
                        "report_id": report_id,
                        "success": False,
                        "error": "Disclosure not found"
                    })
                    continue
                
                # Perform sentiment analysis
                sentiment_data = scraper.analyze_sentiment(
                    content=disclosure[4],
                    company_name=disclosure[2],
                    disclosure_type=disclosure[3]
                )
                
                # Check if analysis already exists
                cursor.execute("SELECT id FROM kap_disclosure_sentiment WHERE disclosure_id = %s", (disclosure[0],))
                existing = cursor.fetchone()
                
                if existing:
                    # Update existing record
                    cursor.execute("""
                        UPDATE kap_disclosure_sentiment SET
                            overall_sentiment = %s,
                            sentiment_score = %s,
                            key_sentiments = %s,
                            analysis_notes = %s,
                            created_at = %s
                        WHERE disclosure_id = %s
                    """, (
                        sentiment_data['overall_sentiment'],
                        sentiment_data.get('confidence', sentiment_data.get('sentiment_score', 0.5)),
                        json.dumps(sentiment_data.get('key_sentiments', [])),
                        sentiment_data.get('analysis_notes', sentiment_data.get('analysis_text', '')),
                        datetime.now(),
                        disclosure[0]
                    ))
                else:
                    # Insert new record
                    cursor.execute("""
                        INSERT INTO kap_disclosure_sentiment 
                        (disclosure_id, overall_sentiment, sentiment_score, key_sentiments, analysis_notes, created_at)
                        VALUES (%s, %s, %s, %s, %s, %s)
                    """, (
                        disclosure[0],
                        sentiment_data['overall_sentiment'],
                        sentiment_data.get('confidence', sentiment_data.get('sentiment_score', 0.5)),
                        json.dumps(sentiment_data.get('key_sentiments', [])),
                        sentiment_data.get('analysis_notes', sentiment_data.get('analysis_text', '')),
                        datetime.now()
                    ))
                
                successful += 1
                results.append({
                    "report_id": report_id,
                    "success": True,
                    "sentiment": sentiment_data,
                    "analyzer": request.analyzer_type
                })
                
            except Exception as e:
                failed += 1
                results.append({
                    "report_id": report_id,
                    "success": False,
                    "error": str(e)
                })
                logger.error(f"Error analyzing sentiment for report {report_id}: {e}")
        
        conn.commit()
        cursor.close()
        db_manager.return_connection(conn)
        
        return SentimentAnalysisResponse(
            total_analyzed=len(request.report_ids),
            successful=successful,
            failed=failed,
            results=results
        )
        
    except DatabaseManager.PoolExhaustedError as e:
        logger.error(f"Database connection pool exhausted during bulk sentiment analysis: {e}")
        raise HTTPException(status_code=503, detail="Database temporarily unavailable, please try again later")
    except Exception as e:
        logger.error(f"Error in bulk sentiment analysis: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/analyze/auto", response_model=ScrapeResponse)
async def analyze_recent_sentiment(
    request: AutoSentimentRequest,
    db_manager: DatabaseManager = Depends(get_db_manager)
):
    """
    Automatically analyze sentiment for recent disclosures
    
    - **days_back**: Days to look back for new disclosures
    - **analyzer_type**: 'keyword' (fast, default) or 'huggingface' (accurate)
    - **company_codes**: Optional list of specific companies
    - **force_reanalyze**: Re-analyze existing sentiment data
    """
    try:
        # Determine LLM provider based on analyzer_type
        use_llm = request.analyzer_type == "huggingface"
        llm_provider = "huggingface" if use_llm else None
        
        # Initialize production scraper with selected analyzer
        scraper = ProductionKAPScraper(use_test_data=False, use_llm=use_llm, llm_provider=llm_provider)
        
        conn = db_manager.get_connection()
        cursor = conn.cursor()
        
        # Set search path
        cursor.execute("SET search_path TO turkish_financial,public;")
        
        # Build query to find disclosures needing sentiment analysis
        where_conditions = ["d.scraped_at >= CURRENT_DATE - INTERVAL %s"]
        params = [f"{request.days_back} days"]
        
        if request.company_codes:
            placeholders = ','.join(['%s'] * len(request.company_codes))
            where_conditions.append(f"d.company_name IN ({placeholders})")
            params.extend(request.company_codes)
        
        if not request.force_reanalyze:
            where_conditions.append("s.id IS NULL")
        
        query = f"""
            SELECT d.id, d.disclosure_id, d.company_name, d.disclosure_type, d.content
            FROM kap_disclosures d
            LEFT JOIN kap_disclosure_sentiment s ON d.id = s.disclosure_id
            WHERE {' AND '.join(where_conditions)}
            ORDER BY d.scraped_at DESC
            LIMIT 100
        """
        
        cursor.execute(query, params)
        disclosures = cursor.fetchall()
        
        # Analyze sentiment for each disclosure
        analyzed_count = 0
        for disclosure in disclosures:
            try:
                # Skip test data
                if 'Test verisi' in disclosure[4]:
                    continue
                
                # Check if analysis already exists
                cursor.execute("SELECT id FROM kap_disclosure_sentiment WHERE disclosure_id = %s", (disclosure[0],))
                existing = cursor.fetchone()
                
                if existing and not request.force_reanalyze:
                    continue  # Skip if already analyzed and not forcing reanalysis
                
                sentiment_data = scraper.analyze_sentiment(
                    content=disclosure[4],
                    company_name=disclosure[2], 
                    disclosure_type=disclosure[3]
                )
                
                if existing:
                    # Update existing record
                    cursor.execute("""
                        UPDATE kap_disclosure_sentiment SET
                            overall_sentiment = %s,
                            sentiment_score = %s,
                            key_sentiments = %s,
                            analysis_notes = %s,
                            created_at = %s
                        WHERE disclosure_id = %s
                    """, (
                        sentiment_data['overall_sentiment'],
                        sentiment_data.get('confidence', sentiment_data.get('sentiment_score', 0.5)),
                        json.dumps(sentiment_data.get('key_sentiments', [])),
                        sentiment_data.get('analysis_notes', sentiment_data.get('analysis_text', '')),
                        datetime.now(),
                        disclosure[0]
                    ))
                else:
                    # Insert new record
                    cursor.execute("""
                        INSERT INTO kap_disclosure_sentiment 
                        (disclosure_id, overall_sentiment, sentiment_score, key_sentiments, analysis_notes, created_at)
                        VALUES (%s, %s, %s, %s, %s, %s)
                    """, (
                        disclosure[0],
                        sentiment_data['overall_sentiment'],
                        sentiment_data.get('confidence', sentiment_data.get('sentiment_score', 0.5)),
                        json.dumps(sentiment_data.get('key_sentiments', [])),
                        sentiment_data.get('analysis_notes', sentiment_data.get('analysis_text', '')),
                        datetime.now()
                    ))
                
                analyzed_count += 1
                
            except Exception as e:
                logger.error(f"Error analyzing disclosure {disclosure[0]}: {e}")
                continue
        
        conn.commit()
        cursor.close()
        db_manager.return_connection(conn)
        
        return ScrapeResponse(
            success=True,
            message=f"Analyzed sentiment for {analyzed_count} disclosures using {request.analyzer_type} analyzer",
            data={
                "analyzed_count": analyzed_count,
                "total_found": len(disclosures),
                "period": f"Last {request.days_back} days",
                "analyzer_type": request.analyzer_type
            }
        )
        
    except DatabaseManager.PoolExhaustedError as e:
        logger.error(f"Database connection pool exhausted during automatic sentiment analysis: {e}")
        raise HTTPException(status_code=503, detail="Database temporarily unavailable, please try again later")
    except Exception as e:
        logger.error(f"Error in automatic sentiment analysis: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/trends")
async def get_sentiment_trends(
    days_back: int = Query(30, ge=1, le=365, description="Days to look back"),
    company_name: Optional[str] = Query(None, description="Filter by company"),
    db_manager: DatabaseManager = Depends(get_db_manager)
):
    """
    Get sentiment trends over time
    
    - **days_back**: Number of days to analyze
    - **company_name**: Optional company filter
    """
    try:
        conn = db_manager.get_connection()
        cursor = conn.cursor()
        
        # Set search path
        cursor.execute("SET search_path TO turkish_financial,public;")
        
        # Base query for trends
        base_query = """
            SELECT 
                DATE(s.created_at) as trend_date,
                s.overall_sentiment,
                COUNT(*) as count,
                AVG(s.sentiment_score) as avg_sentiment_score,
                COUNT(DISTINCT d.company_name) as unique_companies
            FROM kap_disclosure_sentiment s
            JOIN kap_disclosures d ON s.disclosure_id = d.id
            WHERE s.created_at >= CURRENT_DATE - INTERVAL %s
        """
        
        params = [f"{days_back} days"]
        
        if company_name:
            base_query += " AND d.company_name = %s"
            params.append(company_name)
        
        base_query += """
            GROUP BY DATE(s.created_at), s.overall_sentiment
            ORDER BY trend_date DESC, s.overall_sentiment
        """
        
        cursor.execute(base_query, params)
        trends = cursor.fetchall()
        
        # Get summary statistics
        summary_query = """
            SELECT 
                COUNT(*) as total_analyses,
                COUNT(DISTINCT d.company_name) as total_companies,
                AVG(s.sentiment_score) as overall_sentiment_score,
                COUNT(CASE WHEN s.overall_sentiment = 'positive' THEN 1 END) as positive_total,
                COUNT(CASE WHEN s.overall_sentiment = 'neutral' THEN 1 END) as neutral_total,
                COUNT(CASE WHEN s.overall_sentiment = 'negative' THEN 1 END) as negative_total
            FROM kap_disclosure_sentiment s
            JOIN kap_disclosures d ON s.disclosure_id = d.id
            WHERE s.created_at >= CURRENT_DATE - INTERVAL %s
        """
        
        summary_params = [f"{days_back} days"]
        if company_name:
            summary_query += " AND d.company_name = %s"
            summary_params.append(company_name)
        
        cursor.execute(summary_query, summary_params)
        summary = cursor.fetchone()
        
        cursor.close()
        conn.close()
        
        return {
            "success": True,
            "data": {
                "period": f"Last {days_back} days",
                "company_filter": company_name,
                "summary": {
                    "total_analyses": summary[0],
                    "total_companies": summary[1],
                    "overall_sentiment_score": round(summary[2] or 0, 3),
                    "sentiment_totals": {
                        "positive": summary[3],
                        "neutral": summary[4],
                        "negative": summary[5]
                    }
                },
                "daily_trends": [
                    {
                        "date": trend[0],
                        "sentiment": trend[1],
                        "count": trend[2],
                        "avg_confidence": round(trend[3], 3),
                        "unique_companies": trend[4]
                    } for trend in trends
                ]
            },
            "timestamp": datetime.now().isoformat()
        }
        
    except DatabaseManager.PoolExhaustedError as e:
        logger.error(f"Database connection pool exhausted when getting sentiment trends: {e}")
        raise HTTPException(status_code=503, detail="Database temporarily unavailable, please try again later")
    except Exception as e:
        logger.error(f"Error getting sentiment trends: {e}")
        raise HTTPException(status_code=500, detail=str(e))