"""
Sentiment Analyzer Domain Service
Business logic for sentiment analysis
"""
from abc import ABC, abstractmethod
from typing import Optional

from domain.value_objects.sentiment import SentimentAnalysis


class ISentimentAnalyzer(ABC):
    """
    Interface for sentiment analysis service
    
    This is a domain service interface - implementation is in application/infrastructure layer
    """
    
    @abstractmethod
    async def analyze(
        self,
        content: str,
        custom_prompt: Optional[str] = None
    ) -> Optional[SentimentAnalysis]:
        """
        Analyze sentiment from content
        
        Args:
            content: Text content to analyze
            custom_prompt: Optional custom analysis prompt
            
        Returns:
            SentimentAnalysis value object or None if analysis fails
        """
        pass
