"""
Keyword-based sentiment provider — no external API calls.

Uses a simple positive/negative keyword list against Turkish financial text
to produce a JSON response compatible with SentimentAnalyzerService.
"""
import json
import re
from typing import Optional

from utils.llm_analyzer import LLMProvider

_POSITIVE = [
    "artış", "yükseliş", "kazanç", "kâr", "büyüme", "rekor", "güçlü",
    "olumlu", "iyimser", "başarı", "gelir", "anlaşma", "ihracat",
    "positive", "growth", "profit", "gain", "record", "strong",
]
_NEGATIVE = [
    "düşüş", "kayıp", "zarar", "risk", "belirsizlik", "kriz", "gerileme",
    "olumsuz", "endişe", "saldırı", "çatışma", "düştü", "azaldı",
    "negative", "loss", "decline", "risk", "crisis", "war", "attack",
]


class KeywordSentimentProvider(LLMProvider):
    """Fast keyword-based sentiment provider; returns JSON string."""

    def analyze(self, content: str, prompt: Optional[str] = None) -> str:
        text = content.lower() if content else ""
        pos = sum(1 for w in _POSITIVE if w in text)
        neg = sum(1 for w in _NEGATIVE if w in text)
        total = pos + neg or 1

        if pos > neg:
            overall = "positive"
            confidence = round(0.5 + 0.4 * pos / total, 2)
        elif neg > pos:
            overall = "negative"
            confidence = round(0.5 + 0.4 * neg / total, 2)
        else:
            overall = "neutral"
            confidence = 0.5

        result = {
            "overall_sentiment": overall,
            "confidence": min(confidence, 0.9),
            "impact_horizon": "short_term",
            "key_drivers": [],
            "risk_flags": [],
            "tone_descriptors": [overall],
            "target_audience": None,
            "analysis_text": f"Keyword analysis: {pos} positive, {neg} negative signals.",
        }
        return json.dumps(result, ensure_ascii=False)
