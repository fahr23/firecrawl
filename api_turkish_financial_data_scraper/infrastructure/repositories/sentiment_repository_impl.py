"""
Sentiment Repository Implementation
Concrete implementation of ISentimentRepository
"""
import logging
from typing import List, Optional, Tuple
from datetime import date
from psycopg2.extras import RealDictCursor, Json

from domain.value_objects.sentiment import SentimentAnalysis, SentimentType
from domain.entities.kap_report import KAPReport
from domain.repositories.sentiment_repository import ISentimentRepository
from database.db_manager import DatabaseManager

logger = logging.getLogger(__name__)


class SentimentRepository(ISentimentRepository):
    """
    PostgreSQL implementation of Sentiment Repository
    """
    
    def __init__(self, db_manager: DatabaseManager):
        """
        Initialize repository
        
        Args:
            db_manager: Database manager instance
        """
        self._db_manager = db_manager
    
    async def find_by_report_id(self, report_id: int) -> Optional[SentimentAnalysis]:
        """Find sentiment by report ID"""
        conn = self._db_manager.get_connection()
        try:
            cursor = conn.cursor(cursor_factory=RealDictCursor)
            cursor.execute('''
                SELECT overall_sentiment, confidence, impact_horizon,
                       key_drivers, risk_flags, tone_descriptors,
                       target_audience, analysis_text, analyzed_at
                FROM kap_report_sentiment
                WHERE report_id = %s
            ''', (report_id,))
            
            row = cursor.fetchone()
            if row:
                return self._row_to_value_object(dict(row))
            return None
            
        except Exception as e:
            logger.error(f"Error finding sentiment by report ID: {e}")
            return None
        finally:
            self._db_manager.return_connection(conn)
    
    async def save(self, report_id: int, sentiment: SentimentAnalysis) -> None:
        """Save sentiment analysis"""
        conn = self._db_manager.get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute('''
                INSERT INTO kap_report_sentiment (
                    report_id, overall_sentiment, confidence, impact_horizon,
                    key_drivers, risk_flags, tone_descriptors, target_audience,
                    analysis_text
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (report_id) 
                DO UPDATE SET
                    overall_sentiment = EXCLUDED.overall_sentiment,
                    confidence = EXCLUDED.confidence,
                    impact_horizon = EXCLUDED.impact_horizon,
                    key_drivers = EXCLUDED.key_drivers,
                    risk_flags = EXCLUDED.risk_flags,
                    tone_descriptors = EXCLUDED.tone_descriptors,
                    target_audience = EXCLUDED.target_audience,
                    analysis_text = EXCLUDED.analysis_text,
                    analyzed_at = CURRENT_TIMESTAMP
            ''', (
                report_id,
                sentiment.overall_sentiment.value,
                sentiment.confidence.value,
                sentiment.impact_horizon.value,
                Json(list(sentiment.key_drivers)),
                Json(list(sentiment.risk_flags)),
                Json(list(sentiment.tone_descriptors)),
                sentiment.target_audience,
                sentiment.analysis_text
            ))
            
            conn.commit()
            logger.info(f"Saved sentiment for report {report_id}")
            
        except Exception as e:
            logger.error(f"Error saving sentiment: {e}")
            conn.rollback()
            raise
        finally:
            self._db_manager.return_connection(conn)
    
    async def find_by_filters(
        self,
        company_code: Optional[str] = None,
        sentiment_type: Optional[SentimentType] = None,
        start_date: Optional[date] = None,
        end_date: Optional[date] = None,
        limit: int = 100
    ) -> List[Tuple[KAPReport, SentimentAnalysis]]:
        """Find sentiment analyses with filters"""
        conn = self._db_manager.get_connection()
        try:
            cursor = conn.cursor(cursor_factory=RealDictCursor)
            
            query = '''
                SELECT s.*, r.id as report_id, r.company_code, r.company_name,
                       r.report_date, r.title
                FROM kap_report_sentiment s
                JOIN kap_reports r ON s.report_id = r.id
                WHERE 1=1
            '''
            params = []
            
            if company_code:
                query += ' AND r.company_code = %s'
                params.append(company_code)
            
            if sentiment_type:
                query += ' AND s.overall_sentiment = %s'
                params.append(sentiment_type.value)
            
            if start_date:
                query += ' AND r.report_date >= %s'
                params.append(start_date)
            
            if end_date:
                query += ' AND r.report_date <= %s'
                params.append(end_date)
            
            query += ' ORDER BY s.analyzed_at DESC LIMIT %s'
            params.append(limit)
            
            cursor.execute(query, params)
            rows = cursor.fetchall()
            
            results = []
            for row in rows:
                row_dict = dict(row)
                # Create report entity
                report = KAPReport(
                    id=row_dict.get("report_id"),
                    company_code=row_dict.get("company_code", ""),
                    company_name=row_dict.get("company_name"),
                    report_type=None,
                    report_date=row_dict.get("report_date"),
                    title=row_dict.get("title"),
                    summary=None,
                    data=None,
                    scraped_at=row_dict.get("analyzed_at")
                )
                # Create sentiment value object
                sentiment = self._row_to_value_object(row_dict)
                if sentiment:
                    results.append((report, sentiment))
            
            return results
            
        except Exception as e:
            logger.error(f"Error finding sentiment by filters: {e}")
            return []
        finally:
            self._db_manager.return_connection(conn)
    
    def _row_to_value_object(self, row: dict) -> Optional[SentimentAnalysis]:
        """Convert database row to SentimentAnalysis value object"""
        try:
            from domain.value_objects.sentiment import (
                SentimentType, ImpactHorizon, Confidence
            )
            
            return SentimentAnalysis(
                overall_sentiment=SentimentType(row.get("overall_sentiment", "neutral")),
                confidence=Confidence(float(row.get("confidence", 0.5))),
                impact_horizon=ImpactHorizon(row.get("impact_horizon", "medium_term")),
                key_drivers=tuple(row.get("key_drivers", [])),
                risk_flags=tuple(row.get("risk_flags", [])),
                tone_descriptors=tuple(row.get("tone_descriptors", [])),
                target_audience=row.get("target_audience"),
                analysis_text=row.get("analysis_text", ""),
                analyzed_at=row.get("analyzed_at")
            )
        except Exception as e:
            logger.error(f"Error creating SentimentAnalysis from row: {e}")
            return None
