"""
Sentiment Repository Interface
Defines contract for sentiment data access
"""
from abc import ABC, abstractmethod
from typing import List, Optional, Tuple
from datetime import date

from domain.entities.kap_report import KAPReport
from domain.value_objects.sentiment import SentimentAnalysis, SentimentType


class ISentimentRepository(ABC):
    """
    Repository interface for sentiment analysis
    
    Defines data access contract without implementation details.
    """
    
    @abstractmethod
    async def find_by_report_id(self, report_id: int) -> Optional[SentimentAnalysis]:
        """
        Find sentiment analysis by report ID
        
        Args:
            report_id: KAP report ID
            
        Returns:
            SentimentAnalysis value object or None
        """
        pass
    
    @abstractmethod
    async def save(
        self,
        report_id: int,
        sentiment: SentimentAnalysis
    ) -> None:
        """
        Save sentiment analysis for a report
        
        Args:
            report_id: KAP report ID
            sentiment: SentimentAnalysis value object
        """
        pass
    
    @abstractmethod
    async def find_by_filters(
        self,
        company_code: Optional[str] = None,
        sentiment_type: Optional[SentimentType] = None,
        start_date: Optional[date] = None,
        end_date: Optional[date] = None,
        limit: int = 100
    ) -> List[Tuple[KAPReport, SentimentAnalysis]]:
        """
        Find sentiment analyses with filters
        
        Args:
            company_code: Filter by company code
            sentiment_type: Filter by sentiment type
            start_date: Start date filter
            end_date: End date filter
            limit: Maximum results
            
        Returns:
            List of tuples (KAPReport, SentimentAnalysis)
        """
        pass
