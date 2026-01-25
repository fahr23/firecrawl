"""
Sentiment Analyzer Implementation
Concrete implementation using LLM providers
"""
import logging
import json
import re
from typing import Optional, Tuple
from datetime import datetime

from domain.services.sentiment_analyzer_service import ISentimentAnalyzer
from domain.value_objects.sentiment import (
    SentimentAnalysis, SentimentType, ImpactHorizon, Confidence
)
from utils.llm_analyzer import LLMProvider

logger = logging.getLogger(__name__)


class SentimentAnalyzerService(ISentimentAnalyzer):
    """
    Implementation of sentiment analyzer using LLM providers
    
    Single Responsibility: Convert LLM responses to domain value objects
    """
    
    def __init__(self, llm_provider: LLMProvider):
        """
        Initialize sentiment analyzer
        
        Args:
            llm_provider: LLM provider implementation
        """
        self._llm_provider = llm_provider
    
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
            SentimentAnalysis value object or None
        """
        try:
            prompt = custom_prompt or self._get_default_prompt()
            
            # Get LLM response
            response = self._llm_provider.analyze(content, prompt)
            
            if not response:
                logger.error("Empty response from LLM")
                return None
            
            # Parse JSON from response
            sentiment_data = self._parse_json_response(response)
            if not sentiment_data:
                return None
            
            # Create domain value objects
            return self._create_sentiment_analysis(sentiment_data)
            
        except Exception as e:
            logger.error(f"Error in sentiment analysis: {e}", exc_info=True)
            return None
    
    def _get_default_prompt(self) -> str:
        """Get default Turkish financial sentiment analysis prompt"""
        return """
        Sen bir Türk finansal analiz uzmanısın. KAP (Kamu Aydınlatma Platformu) bildirimlerini analiz edip 
        yapılandırılmış bir duygu analizi yapmalısın.
        
        LÜTFEN SADECE GEÇERLİ JSON DÖNDÜR, BAŞKA HİÇBİR ŞEY EKLEME. JSON'u backtick veya kod bloğu içine alma.
        
        JSON formatı şu şekilde olmalı:
        {
            "overall_sentiment": "positive" veya "neutral" veya "negative",
            "confidence": 0.0 ile 1.0 arasında bir sayı,
            "impact_horizon": "short_term" veya "medium_term" veya "long_term",
            "key_drivers": ["faktör1", "faktör2", ...],
            "risk_flags": ["risk1", "risk2", ...] veya boş liste,
            "tone_descriptors": ["iyimser", "ihtiyatlı", ...],
            "target_audience": "retail_investors" veya "institutional" veya null,
            "analysis_text": "Detaylı analiz metni Türkçe olarak"
        }
        
        SADECE JSON DÖNDÜR, BAŞKA HİÇBİR ŞEY YOK.
        """
    
    def _parse_json_response(self, response: str) -> Optional[dict]:
        """Parse JSON from LLM response"""
        try:
            # Extract JSON from response
            json_match = re.search(r'\{.*\}', response, re.DOTALL)
            if json_match:
                json_str = json_match.group(0)
            else:
                json_str = response.strip()
            
            # Remove markdown code blocks
            json_str = re.sub(r'```json\s*', '', json_str)
            json_str = re.sub(r'```\s*', '', json_str)
            json_str = json_str.strip()
            
            return json.loads(json_str)
            
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse JSON: {e}")
            logger.debug(f"Response was: {response[:500]}")
            return None
    
    def _create_sentiment_analysis(self, data: dict) -> SentimentAnalysis:
        """Create SentimentAnalysis value object from parsed data"""
        try:
            return SentimentAnalysis(
                overall_sentiment=SentimentType(data.get("overall_sentiment", "neutral").lower()),
                confidence=Confidence(float(data.get("confidence", 0.5))),
                impact_horizon=ImpactHorizon(data.get("impact_horizon", "medium_term")),
                key_drivers=tuple(data.get("key_drivers", [])),
                risk_flags=tuple(data.get("risk_flags", [])),
                tone_descriptors=tuple(data.get("tone_descriptors", [])),
                target_audience=data.get("target_audience"),
                analysis_text=data.get("analysis_text", ""),
                analyzed_at=datetime.now()
            )
        except (ValueError, KeyError) as e:
            logger.error(f"Error creating SentimentAnalysis: {e}")
            raise
