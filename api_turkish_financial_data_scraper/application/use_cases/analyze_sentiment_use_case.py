"""
Analyze Sentiment Use Case
Single responsibility: Analyze sentiment for KAP reports
"""
from typing import List, Dict, Any
import logging

from domain.entities.kap_report import KAPReport
from domain.repositories.kap_report_repository import IKAPReportRepository
from domain.repositories.sentiment_repository import ISentimentRepository
from domain.services.sentiment_analyzer_service import ISentimentAnalyzer
from domain.value_objects.sentiment import SentimentAnalysis

logger = logging.getLogger(__name__)


class AnalyzeSentimentUseCase:
    """
    Use case for analyzing sentiment of KAP reports
    
    Single Responsibility: Coordinate sentiment analysis workflow
    """
    
    def __init__(
        self,
        report_repository: IKAPReportRepository,
        sentiment_repository: ISentimentRepository,
        sentiment_analyzer: ISentimentAnalyzer
    ):
        """
        Initialize use case with dependencies
        
        Args:
            report_repository: Repository for KAP reports
            sentiment_repository: Repository for sentiment data
            sentiment_analyzer: Service for sentiment analysis
        """
        self._report_repository = report_repository
        self._sentiment_repository = sentiment_repository
        self._sentiment_analyzer = sentiment_analyzer
    
    async def execute(
        self,
        report_ids: List[int],
        custom_prompt: str = None
    ) -> Dict[str, Any]:
        """
        Execute sentiment analysis for reports
        
        Args:
            report_ids: List of report IDs to analyze
            custom_prompt: Optional custom analysis prompt
            
        Returns:
            Dictionary with analysis results
        """
        results = []
        successful = 0
        failed = 0
        
        for report_id in report_ids:
            try:
                # Get report from repository
                report = await self._report_repository.find_by_id(report_id)
                if not report:
                    logger.warning(f"Report {report_id} not found")
                    failed += 1
                    continue
                
                # Get content for analysis
                content = report.get_content()
                if not content:
                    logger.warning(f"Report {report_id} has no content")
                    failed += 1
                    continue
                
                # Analyze sentiment
                sentiment = await self._sentiment_analyzer.analyze(
                    content,
                    custom_prompt
                )
                
                if not sentiment:
                    logger.warning(f"Failed to analyze sentiment for report {report_id}")
                    failed += 1
                    continue
                
                # Save sentiment to repository
                await self._sentiment_repository.save(report_id, sentiment)
                
                results.append({
                    "report_id": report_id,
                    "sentiment": self._sentiment_to_dict(sentiment)
                })
                successful += 1
                
            except Exception as e:
                logger.error(f"Error analyzing report {report_id}: {e}", exc_info=True)
                failed += 1
        
        return {
            "total_analyzed": len(report_ids),
            "successful": successful,
            "failed": failed,
            "results": results
        }
    
    def _sentiment_to_dict(self, sentiment: SentimentAnalysis) -> Dict[str, Any]:
        """Convert SentimentAnalysis value object to dictionary"""
        return {
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
