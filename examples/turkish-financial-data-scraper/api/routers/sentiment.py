"""
Sentiment Analysis API endpoints for Turkish Financial Data
"""
import logging
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
                AVG(confidence) as avg_confidence,
                COUNT(CASE WHEN overall_sentiment = 'positive' THEN 1 END) as positive_count,
                COUNT(CASE WHEN overall_sentiment = 'neutral' THEN 1 END) as neutral_count,
                COUNT(CASE WHEN overall_sentiment = 'negative' THEN 1 END) as negative_count,
                MAX(analyzed_at) as latest_analysis
            FROM kap_disclosure_sentiment
        """)
        
        stats = cursor.fetchone()
        
        # Get recent sentiment trends
        cursor.execute("""
            SELECT 
                DATE(analyzed_at) as analysis_date,
                overall_sentiment,
                COUNT(*) as count
            FROM kap_disclosure_sentiment
            WHERE analyzed_at >= CURRENT_DATE - INTERVAL '30 days'
            GROUP BY DATE(analyzed_at), overall_sentiment
            ORDER BY analysis_date DESC, overall_sentiment
            LIMIT 90
        """)
        
        trends = cursor.fetchall()
        
        # Get top companies by analysis volume
        cursor.execute("""
            SELECT 
                d.company_name,
                COUNT(*) as analysis_count,
                AVG(s.confidence) as avg_confidence,
                MAX(s.analyzed_at) as latest_analysis
            FROM kap_disclosure_sentiment s
            JOIN kap_disclosures d ON s.disclosure_id = d.id
            GROUP BY d.company_name
            ORDER BY analysis_count DESC
            LIMIT 10
        """)
        
        top_companies = cursor.fetchall()
        
        cursor.close()
        conn.close()
        
        return {
            "success": True,
            "data": {
                "overview": {
                    "total_analyses": stats[0],
                    "unique_disclosures": stats[1],
                    "average_confidence": round(stats[2] or 0, 3),
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
                        "avg_confidence": round(company[2], 3),
                        "latest_analysis": company[3]
                    } for company in top_companies
                ]
            },
            "timestamp": datetime.now().isoformat()
        }
        
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
                s.confidence,
                s.impact_horizon,
                s.key_drivers,
                s.risk_flags,
                s.tone_descriptors,
                s.target_audience,
                s.analysis_text,
                s.risk_level,
                s.analyzed_at
            FROM kap_disclosures d
            LEFT JOIN kap_disclosure_sentiment s ON d.id = s.disclosure_id
            WHERE d.id = %s
        """, (disclosure_id,))
        
        result = cursor.fetchone()
        cursor.close()
        conn.close()
        
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
                    "confidence": result[6],
                    "impact_horizon": result[7],
                    "key_drivers": result[8],
                    "risk_flags": result[9],
                    "tone_descriptors": result[10],
                    "target_audience": result[11],
                    "analysis_text": result[12],
                    "risk_level": result[13],
                    "analyzed_at": result[14]
                } if result[5] else None
            },
            "timestamp": datetime.now().isoformat()
        }
        
    except HTTPException:
        raise
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
                s.confidence,
                s.impact_horizon,
                s.key_drivers,
                s.risk_flags,
                s.risk_level,
                s.analysis_text,
                s.analyzed_at
            FROM kap_disclosures d
            JOIN kap_disclosure_sentiment s ON d.id = s.disclosure_id
            WHERE d.company_name = %s 
                AND s.analyzed_at >= CURRENT_DATE - INTERVAL '%s days'
            ORDER BY s.analyzed_at DESC
            LIMIT %s
        """, (company_name, days_back, limit))
        
        results = cursor.fetchall()
        
        # Get company sentiment summary
        cursor.execute("""
            SELECT 
                COUNT(*) as total_analyses,
                AVG(confidence) as avg_confidence,
                COUNT(CASE WHEN overall_sentiment = 'positive' THEN 1 END) as positive_count,
                COUNT(CASE WHEN overall_sentiment = 'neutral' THEN 1 END) as neutral_count,
                COUNT(CASE WHEN overall_sentiment = 'negative' THEN 1 END) as negative_count
            FROM kap_disclosures d
            JOIN kap_disclosure_sentiment s ON d.id = s.disclosure_id
            WHERE d.company_name = %s 
                AND s.analyzed_at >= CURRENT_DATE - INTERVAL '%s days'
        """, (company_name, days_back))
        
        summary = cursor.fetchone()
        
        cursor.close()
        conn.close()
        
        return {
            "success": True,
            "data": {
                "company_name": company_name,
                "period": f"Last {days_back} days",
                "summary": {
                    "total_analyses": summary[0],
                    "average_confidence": round(summary[1] or 0, 3),
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
                            "confidence": result[4],
                            "impact_horizon": result[5],
                            "key_drivers": result[6],
                            "risk_flags": result[7],
                            "risk_level": result[8],
                            "analysis_text": result[9][:200] + "..." if len(result[9]) > 200 else result[9],
                            "analyzed_at": result[10]
                        }
                    } for result in results
                ]
            },
            "timestamp": datetime.now().isoformat()
        }
        
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
    - **custom_prompt**: Optional custom prompt for analysis
    """
    try:
        # Initialize production scraper
        scraper = ProductionKAPScraper()
        
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
                            confidence = %s,
                            impact_horizon = %s,
                            key_drivers = %s,
                            risk_flags = %s,
                            tone_descriptors = %s,
                            target_audience = %s,
                            analysis_text = %s,
                            risk_level = %s,
                            analyzed_at = %s
                        WHERE disclosure_id = %s
                    """, (
                        sentiment_data['overall_sentiment'],
                        sentiment_data['confidence'],
                        sentiment_data['impact_horizon'],
                        sentiment_data['key_drivers'],
                        sentiment_data['risk_flags'],
                        sentiment_data['tone_descriptors'],
                        sentiment_data['target_audience'],
                        sentiment_data['analysis_text'],
                        sentiment_data['risk_level'],
                        datetime.now(),
                        disclosure[0]
                    ))
                else:
                    # Insert new record
                    cursor.execute("""
                        INSERT INTO kap_disclosure_sentiment 
                        (disclosure_id, overall_sentiment, confidence, impact_horizon, 
                         key_drivers, risk_flags, tone_descriptors, target_audience, 
                         analysis_text, risk_level, analyzed_at)
                        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    """, (
                        disclosure[0],
                        sentiment_data['overall_sentiment'],
                        sentiment_data['confidence'],
                        sentiment_data['impact_horizon'],
                        sentiment_data['key_drivers'],
                        sentiment_data['risk_flags'],
                        sentiment_data['tone_descriptors'],
                        sentiment_data['target_audience'],
                        sentiment_data['analysis_text'],
                        sentiment_data['risk_level'],
                        datetime.now()
                    ))
                
                successful += 1
                results.append({
                    "report_id": report_id,
                    "success": True,
                    "sentiment": sentiment_data
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
        conn.close()
        
        return SentimentAnalysisResponse(
            total_analyzed=len(request.report_ids),
            successful=successful,
            failed=failed,
            results=results
        )
        
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
    - **company_codes**: Optional list of specific companies
    - **force_reanalyze**: Re-analyze existing sentiment data
    """
    try:
        # Initialize production scraper
        scraper = ProductionKAPScraper()
        
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
                            confidence = %s,
                            impact_horizon = %s,
                            key_drivers = %s,
                            risk_flags = %s,
                            tone_descriptors = %s,
                            target_audience = %s,
                            analysis_text = %s,
                            risk_level = %s,
                            analyzed_at = %s
                        WHERE disclosure_id = %s
                    """, (
                        sentiment_data['overall_sentiment'],
                        sentiment_data['confidence'],
                        sentiment_data['impact_horizon'],
                        sentiment_data['key_drivers'],
                        sentiment_data['risk_flags'],
                        sentiment_data['tone_descriptors'],
                        sentiment_data['target_audience'],
                        sentiment_data['analysis_text'],
                        sentiment_data['risk_level'],
                        datetime.now(),
                        disclosure[0]
                    ))
                else:
                    # Insert new record
                    cursor.execute("""
                        INSERT INTO kap_disclosure_sentiment 
                        (disclosure_id, overall_sentiment, confidence, impact_horizon, 
                         key_drivers, risk_flags, tone_descriptors, target_audience, 
                         analysis_text, risk_level, analyzed_at)
                        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    """, (
                        disclosure[0],
                        sentiment_data['overall_sentiment'],
                        sentiment_data['confidence'],
                        sentiment_data['impact_horizon'],
                        sentiment_data['key_drivers'],
                        sentiment_data['risk_flags'],
                        sentiment_data['tone_descriptors'],
                        sentiment_data['target_audience'],
                        sentiment_data['analysis_text'],
                        sentiment_data['risk_level'],
                        datetime.now()
                    ))
                
                analyzed_count += 1
                
            except Exception as e:
                logger.error(f"Error analyzing disclosure {disclosure[0]}: {e}")
                continue
        
        conn.commit()
        cursor.close()
        conn.close()
        
        return ScrapeResponse(
            success=True,
            message=f"Analyzed sentiment for {analyzed_count} disclosures",
            data={
                "analyzed_count": analyzed_count,
                "total_found": len(disclosures),
                "period": f"Last {request.days_back} days"
            }
        )
        
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
                DATE(s.analyzed_at) as trend_date,
                s.overall_sentiment,
                COUNT(*) as count,
                AVG(s.confidence) as avg_confidence,
                COUNT(DISTINCT d.company_name) as unique_companies
            FROM kap_disclosure_sentiment s
            JOIN kap_disclosures d ON s.disclosure_id = d.id
            WHERE s.analyzed_at >= CURRENT_DATE - INTERVAL %s
        """
        
        params = [f"{days_back} days"]
        
        if company_name:
            base_query += " AND d.company_name = %s"
            params.append(company_name)
        
        base_query += """
            GROUP BY DATE(s.analyzed_at), s.overall_sentiment
            ORDER BY trend_date DESC, s.overall_sentiment
        """
        
        cursor.execute(base_query, params)
        trends = cursor.fetchall()
        
        # Get summary statistics
        summary_query = """
            SELECT 
                COUNT(*) as total_analyses,
                COUNT(DISTINCT d.company_name) as total_companies,
                AVG(s.confidence) as overall_confidence,
                COUNT(CASE WHEN s.overall_sentiment = 'positive' THEN 1 END) as positive_total,
                COUNT(CASE WHEN s.overall_sentiment = 'neutral' THEN 1 END) as neutral_total,
                COUNT(CASE WHEN s.overall_sentiment = 'negative' THEN 1 END) as negative_total
            FROM kap_disclosure_sentiment s
            JOIN kap_disclosures d ON s.disclosure_id = d.id
            WHERE s.analyzed_at >= CURRENT_DATE - INTERVAL %s
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
                    "overall_confidence": round(summary[2] or 0, 3),
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
        
    except Exception as e:
        logger.error(f"Error getting sentiment trends: {e}")
        raise HTTPException(status_code=500, detail=str(e))