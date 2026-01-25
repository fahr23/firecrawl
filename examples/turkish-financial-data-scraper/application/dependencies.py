"""
Dependency Injection Container
Provides configured instances for use cases
"""
from functools import lru_cache
from database.db_manager import DatabaseManager
from infrastructure.repositories.kap_report_repository_impl import KAPReportRepository
from infrastructure.repositories.sentiment_repository_impl import SentimentRepository
from infrastructure.services.sentiment_analyzer_impl import SentimentAnalyzerService
from utils.llm_analyzer import LocalLLMProvider, OpenAIProvider
from application.use_cases.analyze_sentiment_use_case import AnalyzeSentimentUseCase
import os


@lru_cache()
def get_db_manager() -> DatabaseManager:
    """Get database manager singleton"""
    return DatabaseManager()


def get_report_repository(db_manager: DatabaseManager = None) -> KAPReportRepository:
    """Get KAP report repository"""
    if db_manager is None:
        db_manager = get_db_manager()
    return KAPReportRepository(db_manager)


def get_sentiment_repository(db_manager: DatabaseManager = None) -> SentimentRepository:
    """Get sentiment repository"""
    if db_manager is None:
        db_manager = get_db_manager()
    return SentimentRepository(db_manager)


def get_sentiment_analyzer_service():
    """Get sentiment analyzer service"""
    # Check for OpenAI API key
    openai_key = os.getenv("OPENAI_API_KEY")
    if openai_key:
        provider = OpenAIProvider(api_key=openai_key)
    else:
        # Default to local LLM
        base_url = os.getenv("LOCAL_LLM_BASE_URL", "http://localhost:1234/v1")
        provider = LocalLLMProvider(base_url=base_url)
    
    return SentimentAnalyzerService(provider)


def get_analyze_sentiment_use_case(
    db_manager: DatabaseManager = None
) -> AnalyzeSentimentUseCase:
    """
    Get configured AnalyzeSentimentUseCase
    
    Args:
        db_manager: Optional database manager (uses singleton if not provided)
        
    Returns:
        Configured use case instance
    """
    if db_manager is None:
        db_manager = get_db_manager()
    
    report_repo = get_report_repository(db_manager)
    sentiment_repo = get_sentiment_repository(db_manager)
    sentiment_analyzer = get_sentiment_analyzer_service()
    
    return AnalyzeSentimentUseCase(
        report_repository=report_repo,
        sentiment_repository=sentiment_repo,
        sentiment_analyzer=sentiment_analyzer
    )
