"""
KAP Report Entity - Domain model for financial disclosure reports
"""
from dataclasses import dataclass
from datetime import date, datetime
from typing import Optional, Dict, Any


@dataclass
class KAPReport:
    """
    Domain entity representing a KAP (Public Disclosure Platform) report
    
    This is a domain entity with business logic, not a data transfer object.
    """
    id: Optional[int]
    company_code: str
    company_name: Optional[str]
    report_type: Optional[str]
    report_date: Optional[date]
    title: Optional[str]
    summary: Optional[str]
    data: Optional[Dict[str, Any]]
    scraped_at: datetime
    
    def __post_init__(self):
        """Validate entity invariants"""
        if not self.company_code:
            raise ValueError("Company code is required")
        if self.company_code and len(self.company_code) > 10:
            raise ValueError("Company code must be 10 characters or less")
    
    def get_content(self) -> str:
        """
        Get combined text content for analysis
        
        Returns:
            Combined text content from title, summary, and data
        """
        parts = []
        if self.title:
            parts.append(f"Başlık: {self.title}")
        if self.summary:
            parts.append(f"Özet: {self.summary}")
        if self.data:
            import json
            parts.append(f"Veri: {json.dumps(self.data, ensure_ascii=False)}")
        return "\n".join(parts)
    
    def is_recent(self, days: int = 7) -> bool:
        """
        Check if report is within specified days
        
        Args:
            days: Number of days to check
            
        Returns:
            True if report is within the date range
        """
        if not self.report_date:
            return False
        from datetime import timedelta
        cutoff = date.today() - timedelta(days=days)
        return self.report_date >= cutoff
    
    def has_financial_data(self) -> bool:
        """
        Check if report contains financial data
        
        Returns:
            True if report has financial indicators
        """
        if not self.data:
            return False
        financial_keywords = ['revenue', 'gelir', 'profit', 'kar', 'ebitda', 'net']
        data_str = str(self.data).lower()
        return any(keyword in data_str for keyword in financial_keywords)
