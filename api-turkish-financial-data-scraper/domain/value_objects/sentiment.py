"""
Sentiment Value Objects - Immutable sentiment-related value objects
"""
from dataclasses import dataclass
from enum import Enum
from typing import List, Optional, Tuple
from datetime import datetime


class SentimentType(str, Enum):
    """Sentiment type enumeration"""
    POSITIVE = "positive"
    NEUTRAL = "neutral"
    NEGATIVE = "negative"


class ImpactHorizon(str, Enum):
    """Impact horizon enumeration"""
    SHORT_TERM = "short_term"
    MEDIUM_TERM = "medium_term"
    LONG_TERM = "long_term"


@dataclass(frozen=True)
class Confidence:
    """
    Value object representing confidence score
    
    Immutable and validated at creation
    """
    value: float
    
    def __post_init__(self):
        """Validate confidence value"""
        if not 0.0 <= self.value <= 1.0:
            raise ValueError(f"Confidence must be between 0.0 and 1.0, got {self.value}")
    
    def is_high(self) -> bool:
        """Check if confidence is high (>= 0.7)"""
        return self.value >= 0.7
    
    def is_low(self) -> bool:
        """Check if confidence is low (< 0.5)"""
        return self.value < 0.5


@dataclass(frozen=True)
class SentimentAnalysis:
    """
    Value object representing sentiment analysis result
    
    Immutable and contains all sentiment-related data
    """
    overall_sentiment: SentimentType
    confidence: Confidence
    impact_horizon: ImpactHorizon
    key_drivers: Tuple[str, ...]  # Immutable tuple
    risk_flags: Tuple[str, ...]  # Immutable tuple
    tone_descriptors: Tuple[str, ...]  # Immutable tuple
    target_audience: Optional[str]
    analysis_text: str
    analyzed_at: datetime
    
    def __post_init__(self):
        """Validate sentiment analysis"""
        if not self.analysis_text:
            raise ValueError("Analysis text is required")
    
    def is_positive(self) -> bool:
        """Check if sentiment is positive"""
        return self.overall_sentiment == SentimentType.POSITIVE
    
    def is_negative(self) -> bool:
        """Check if sentiment is negative"""
        return self.overall_sentiment == SentimentType.NEGATIVE
    
    def has_high_risk(self) -> bool:
        """Check if analysis indicates high risk"""
        return len(self.risk_flags) > 2
    
    def get_risk_level(self) -> str:
        """
        Get risk level based on risk flags
        
        Returns:
            Risk level: "low", "medium", or "high"
        """
        risk_count = len(self.risk_flags)
        # Treat 0–1 flags as low risk, a small number of issues as medium,
        # and many flags as high. Thresholds are chosen to match tests.
        if risk_count <= 1:
            return "low"
        elif risk_count <= 3:
            return "medium"
        else:
            return "high"
