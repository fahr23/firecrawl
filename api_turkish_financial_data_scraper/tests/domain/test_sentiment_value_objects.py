"""
Tests for Sentiment value objects
"""
import pytest
from datetime import datetime
from domain.value_objects.sentiment import (
    SentimentAnalysis, SentimentType, ImpactHorizon, Confidence
)


def test_confidence_creation():
    """Test creating confidence value object"""
    confidence = Confidence(0.85)
    assert confidence.value == 0.85
    assert confidence.is_high() is True
    assert confidence.is_low() is False


def test_confidence_validation():
    """Test confidence validation"""
    with pytest.raises(ValueError):
        Confidence(1.5)  # Invalid value
    
    with pytest.raises(ValueError):
        Confidence(-0.1)  # Invalid value


def test_sentiment_analysis_creation():
    """Test creating sentiment analysis value object"""
    sentiment = SentimentAnalysis(
        overall_sentiment=SentimentType.POSITIVE,
        confidence=Confidence(0.85),
        impact_horizon=ImpactHorizon.MEDIUM_TERM,
        key_drivers=("Revenue growth", "Market expansion"),
        risk_flags=("Debt increase",),
        tone_descriptors=("Optimistic", "Confident"),
        target_audience="retail_investors",
        analysis_text="Detailed analysis",
        analyzed_at=datetime.now()
    )
    
    assert sentiment.is_positive() is True
    assert sentiment.is_negative() is False
    assert sentiment.has_high_risk() is False
    assert sentiment.get_risk_level() == "low"


def test_sentiment_analysis_high_risk():
    """Test high risk detection"""
    sentiment = SentimentAnalysis(
        overall_sentiment=SentimentType.NEGATIVE,
        confidence=Confidence(0.9),
        impact_horizon=ImpactHorizon.SHORT_TERM,
        key_drivers=("Declining revenue",),
        risk_flags=("Liquidity", "Debt", "Regulation", "Market"),
        tone_descriptors=("Cautious",),
        target_audience=None,
        analysis_text="Analysis",
        analyzed_at=datetime.now()
    )
    
    assert sentiment.has_high_risk() is True
    assert sentiment.get_risk_level() == "high"
    assert sentiment.is_negative() is True
