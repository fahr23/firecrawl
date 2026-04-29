"""
KAP Report Repository Interface
Defines contract for KAP report data access
"""
from abc import ABC, abstractmethod
from typing import List, Optional
from datetime import date

from domain.entities.kap_report import KAPReport


class IKAPReportRepository(ABC):
    """
    Repository interface for KAP reports
    
    Defines data access contract without implementation details.
    Implementation belongs in infrastructure layer.
    """
    
    @abstractmethod
    async def find_by_id(self, report_id: int) -> Optional[KAPReport]:
        """
        Find report by ID
        
        Args:
            report_id: Report ID
            
        Returns:
            KAPReport entity or None if not found
        """
        pass
    
    @abstractmethod
    async def find_by_company_code(
        self,
        company_code: str,
        start_date: Optional[date] = None,
        end_date: Optional[date] = None,
        limit: int = 100
    ) -> List[KAPReport]:
        """
        Find reports by company code
        
        Args:
            company_code: Company code
            start_date: Optional start date filter
            end_date: Optional end date filter
            limit: Maximum results
            
        Returns:
            List of KAPReport entities
        """
        pass
    
    @abstractmethod
    async def find_recent(self, days: int = 7, limit: int = 100) -> List[KAPReport]:
        """
        Find recent reports
        
        Args:
            days: Number of days to look back
            limit: Maximum results
            
        Returns:
            List of KAPReport entities
        """
        pass
    
    @abstractmethod
    async def save(self, report: KAPReport) -> KAPReport:
        """
        Save or update report
        
        Args:
            report: KAPReport entity to save
            
        Returns:
            Saved KAPReport entity (with ID if new)
        """
        pass
    
    @abstractmethod
    async def save_many(self, reports: List[KAPReport]) -> int:
        """
        Save multiple reports
        
        Args:
            reports: List of KAPReport entities
            
        Returns:
            Number of reports saved
        """
        pass
