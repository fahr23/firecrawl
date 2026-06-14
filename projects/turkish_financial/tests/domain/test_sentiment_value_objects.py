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


def test_sentiment_to_score_positive():
    """Positive sentiment produces a positive score equal to confidence."""
    sentiment = SentimentAnalysis(
        overall_sentiment=SentimentType.POSITIVE,
        confidence=Confidence(0.8),
        impact_horizon=ImpactHorizon.MEDIUM_TERM,
        key_drivers=(),
        risk_flags=(),
        tone_descriptors=(),
        target_audience=None,
        analysis_text="Positive outlook",
        analyzed_at=__import__("datetime").datetime.now()
    )
    assert sentiment.to_score() == pytest.approx(0.8)


def test_sentiment_to_score_negative():
    """Negative sentiment produces a negative score."""
    sentiment = SentimentAnalysis(
        overall_sentiment=SentimentType.NEGATIVE,
        confidence=Confidence(0.6),
        impact_horizon=ImpactHorizon.SHORT_TERM,
        key_drivers=(),
        risk_flags=(),
        tone_descriptors=(),
        target_audience=None,
        analysis_text="Negative outlook",
        analyzed_at=__import__("datetime").datetime.now()
    )
    assert sentiment.to_score() == pytest.approx(-0.6)


def test_sentiment_to_score_neutral():
    """Neutral sentiment produces score of 0."""
    sentiment = SentimentAnalysis(
        overall_sentiment=SentimentType.NEUTRAL,
        confidence=Confidence(0.9),
        impact_horizon=ImpactHorizon.LONG_TERM,
        key_drivers=(),
        risk_flags=(),
        tone_descriptors=(),
        target_audience=None,
        analysis_text="Neutral outlook",
        analyzed_at=__import__("datetime").datetime.now()
    )
    assert sentiment.to_score() == 0.0


def test_sentiment_to_dict_keys():
    """to_dict contains all required keys."""
    from datetime import datetime
    sentiment = SentimentAnalysis(
        overall_sentiment=SentimentType.POSITIVE,
        confidence=Confidence(0.75),
        impact_horizon=ImpactHorizon.MEDIUM_TERM,
        key_drivers=("Growth",),
        risk_flags=("Debt",),
        tone_descriptors=("Optimistic",),
        target_audience="retail_investors",
        analysis_text="Good report",
        analyzed_at=datetime.now()
    )
    d = sentiment.to_dict()
    for key in ("overall_sentiment", "confidence", "sentiment_score",
                "impact_horizon", "risk_level", "key_drivers",
                "risk_flags", "tone_descriptors", "target_audience",
                "analysis_text", "analyzed_at"):
        assert key in d, f"Missing key: {key}"

    assert d["overall_sentiment"] == "positive"
    assert d["sentiment_score"] == pytest.approx(0.75)
    assert d["risk_level"] == "low"
    assert d["key_drivers"] == ["Growth"]


def test_sentiment_to_dict_analyzed_at_is_iso_string():
    """analyzed_at in to_dict should be an ISO-formatted string."""
    from datetime import datetime
    now = datetime(2025, 6, 15, 10, 30, 0)
    sentiment = SentimentAnalysis(
        overall_sentiment=SentimentType.NEUTRAL,
        confidence=Confidence(0.5),
        impact_horizon=ImpactHorizon.LONG_TERM,
        key_drivers=(),
        risk_flags=(),
        tone_descriptors=(),
        target_audience=None,
        analysis_text="Neutral",
        analyzed_at=now
    )
    d = sentiment.to_dict()
    assert d["analyzed_at"] == now.isoformat()


def test_confidence_boundary_values():
    """Boundary values 0.0 and 1.0 are valid."""
    c_min = Confidence(0.0)
    c_max = Confidence(1.0)
    assert c_min.value == 0.0
    assert c_max.value == 1.0
    assert c_min.is_low() is True
    assert c_max.is_high() is True
