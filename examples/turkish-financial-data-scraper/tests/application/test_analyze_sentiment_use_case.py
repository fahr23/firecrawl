"""
Tests for AnalyzeSentimentUseCase
Following DDD - test use case in isolation with mocks
"""
import pytest
from unittest.mock import AsyncMock, MagicMock
from datetime import datetime

from application.use_cases.analyze_sentiment_use_case import AnalyzeSentimentUseCase
from domain.entities.kap_report import KAPReport
from domain.value_objects.sentiment import (
    SentimentAnalysis, SentimentType, ImpactHorizon, Confidence
)


@pytest.fixture
def mock_report_repository():
    """Mock report repository"""
    repo = AsyncMock()
    return repo


@pytest.fixture
def mock_sentiment_repository():
    """Mock sentiment repository"""
    repo = AsyncMock()
    return repo


@pytest.fixture
def mock_sentiment_analyzer():
    """Mock sentiment analyzer"""
    analyzer = AsyncMock()
    return analyzer


@pytest.fixture
def use_case(mock_report_repository, mock_sentiment_repository, mock_sentiment_analyzer):
    """Create use case with mocked dependencies"""
    return AnalyzeSentimentUseCase(
        report_repository=mock_report_repository,
        sentiment_repository=mock_sentiment_repository,
        sentiment_analyzer=mock_sentiment_analyzer
    )


@pytest.mark.asyncio
async def test_analyze_sentiment_success(use_case, mock_report_repository, 
                                        mock_sentiment_repository, mock_sentiment_analyzer):
    """Test successful sentiment analysis"""
    # Setup mocks
    report = KAPReport(
        id=1,
        company_code="AKBNK",
        company_name="Akbank",
        report_type=None,
        report_date=None,
        title="Test Report",
        summary="Test Summary",
        data=None,
        scraped_at=datetime.now()
    )
    
    sentiment = SentimentAnalysis(
        overall_sentiment=SentimentType.POSITIVE,
        confidence=Confidence(0.85),
        impact_horizon=ImpactHorizon.MEDIUM_TERM,
        key_drivers=("Growth",),
        risk_flags=(),
        tone_descriptors=("Optimistic",),
        target_audience="retail_investors",
        analysis_text="Analysis",
        analyzed_at=datetime.now()
    )
    
    mock_report_repository.find_by_id.return_value = report
    mock_sentiment_analyzer.analyze.return_value = sentiment
    
    # Execute
    result = await use_case.execute([1])
    
    # Verify
    assert result["total_analyzed"] == 1
    assert result["successful"] == 1
    assert result["failed"] == 0
    assert len(result["results"]) == 1
    mock_sentiment_repository.save.assert_called_once_with(1, sentiment)


@pytest.mark.asyncio
async def test_analyze_sentiment_report_not_found(use_case, mock_report_repository):
    """Test when report is not found"""
    mock_report_repository.find_by_id.return_value = None
    
    result = await use_case.execute([999])
    
    assert result["total_analyzed"] == 1
    assert result["successful"] == 0
    assert result["failed"] == 1


@pytest.mark.asyncio
async def test_analyze_sentiment_analysis_fails(use_case, mock_report_repository,
                                                mock_sentiment_analyzer):
    """Test when sentiment analysis fails"""
    report = KAPReport(
        id=1,
        company_code="AKBNK",
        company_name="Akbank",
        report_type=None,
        report_date=None,
        title="Test",
        summary=None,
        data=None,
        scraped_at=datetime.now()
    )
    
    mock_report_repository.find_by_id.return_value = report
    mock_sentiment_analyzer.analyze.return_value = None  # Analysis fails
    
    result = await use_case.execute([1])
    
    assert result["successful"] == 0
    assert result["failed"] == 1
