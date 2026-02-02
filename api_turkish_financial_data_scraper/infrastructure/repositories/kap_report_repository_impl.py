"""
KAP Report Repository Implementation
Concrete implementation of IKAPReportRepository
"""
import logging
from typing import List, Optional
from datetime import date
from psycopg2.extras import RealDictCursor

from domain.entities.kap_report import KAPReport
from domain.repositories.kap_report_repository import IKAPReportRepository
from database.db_manager import DatabaseManager

logger = logging.getLogger(__name__)


class KAPReportRepository(IKAPReportRepository):
    """
    PostgreSQL implementation of KAP Report Repository
    
    Handles all database operations for KAP reports
    """
    
    def __init__(self, db_manager: DatabaseManager):
        """
        Initialize repository
        
        Args:
            db_manager: Database manager instance
        """
        self._db_manager = db_manager
    
    async def find_by_id(self, report_id: int) -> Optional[KAPReport]:
        """Find report by ID"""
        conn = self._db_manager.get_connection()
        try:
            cursor = conn.cursor(cursor_factory=RealDictCursor)
            cursor.execute('''
                SELECT id, company_code, company_name, report_type, report_date,
                       title, summary, data, scraped_at
                FROM kap_reports
                WHERE id = %s
            ''', (report_id,))
            
            row = cursor.fetchone()
            if row:
                return self._row_to_entity(dict(row))
            return None
            
        except Exception as e:
            logger.error(f"Error finding report by ID: {e}")
            return None
        finally:
            self._db_manager.return_connection(conn)
    
    async def find_by_company_code(
        self,
        company_code: str,
        start_date: Optional[date] = None,
        end_date: Optional[date] = None,
        limit: int = 100
    ) -> List[KAPReport]:
        """Find reports by company code"""
        conn = self._db_manager.get_connection()
        try:
            cursor = conn.cursor(cursor_factory=RealDictCursor)
            
            query = '''
                SELECT id, company_code, company_name, report_type, report_date,
                       title, summary, data, scraped_at
                FROM kap_reports
                WHERE company_code = %s
            '''
            params = [company_code]
            
            if start_date:
                query += ' AND report_date >= %s'
                params.append(start_date)
            
            if end_date:
                query += ' AND report_date <= %s'
                params.append(end_date)
            
            query += ' ORDER BY report_date DESC LIMIT %s'
            params.append(limit)
            
            cursor.execute(query, params)
            rows = cursor.fetchall()
            
            return [self._row_to_entity(dict(row)) for row in rows]
            
        except Exception as e:
            logger.error(f"Error finding reports by company code: {e}")
            return []
        finally:
            self._db_manager.return_connection(conn)
    
    async def find_recent(self, days: int = 7, limit: int = 100) -> List[KAPReport]:
        """Find recent reports"""
        from datetime import timedelta
        start_date = date.today() - timedelta(days=days)
        
        conn = self._db_manager.get_connection()
        try:
            cursor = conn.cursor(cursor_factory=RealDictCursor)
            cursor.execute('''
                SELECT id, company_code, company_name, report_type, report_date,
                       title, summary, data, scraped_at
                FROM kap_reports
                WHERE report_date >= %s
                ORDER BY report_date DESC
                LIMIT %s
            ''', (start_date, limit))
            
            rows = cursor.fetchall()
            return [self._row_to_entity(dict(row)) for row in rows]
            
        except Exception as e:
            logger.error(f"Error finding recent reports: {e}")
            return []
        finally:
            self._db_manager.return_connection(conn)
    
    async def save(self, report: KAPReport) -> KAPReport:
        """Save or update report"""
        # Implementation would use db_manager.insert_data or update
        # This is a simplified version
        try:
            data = {
                "company_code": report.company_code,
                "company_name": report.company_name,
                "report_type": report.report_type,
                "report_date": report.report_date.isoformat() if report.report_date else None,
                "title": report.title,
                "summary": report.summary,
                "data": report.data
            }
            
            if report.id:
                # Update existing
                self._db_manager.execute(
                    '''
                    UPDATE kap_reports
                    SET company_name = %s, report_type = %s, report_date = %s,
                        title = %s, summary = %s, data = %s
                    WHERE id = %s
                    ''',
                    (data["company_name"], data["report_type"], data["report_date"],
                     data["title"], data["summary"], data["data"], report.id)
                )
            else:
                # Insert new
                self._db_manager.insert_data("kap_reports", data)
                # In real implementation, would fetch back to get ID
            
            return report
            
        except Exception as e:
            logger.error(f"Error saving report: {e}")
            raise
    
    async def save_many(self, reports: List[KAPReport]) -> int:
        """Save multiple reports"""
        saved = 0
        for report in reports:
            try:
                await self.save(report)
                saved += 1
            except Exception as e:
                logger.error(f"Error saving report: {e}")
        return saved
    
    def _row_to_entity(self, row: dict) -> KAPReport:
        """Convert database row to domain entity"""
        return KAPReport(
            id=row.get("id"),
            company_code=row.get("company_code", ""),
            company_name=row.get("company_name"),
            report_type=row.get("report_type"),
            report_date=row.get("report_date"),
            title=row.get("title"),
            summary=row.get("summary"),
            data=row.get("data"),
            scraped_at=row.get("scraped_at")
        )
