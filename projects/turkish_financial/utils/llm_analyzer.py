"""
LLM Analysis utilities for financial data
Supports local and cloud LLM providers with Strategy Pattern
"""
import logging
import json
import re
from abc import ABC, abstractmethod
from typing import Dict, Any, List, Optional
from pathlib import Path
from openai import OpenAI
from fpdf import FPDF
from pydantic import BaseModel, Field
from datetime import datetime
import os

# Try to import Google Generative AI (optional dependency)
try:
    import google.generativeai as genai
    GEMINI_AVAILABLE = True
except ImportError:
    GEMINI_AVAILABLE = False
    genai = None

logger = logging.getLogger(__name__)


class LLMProvider(ABC):
    """Abstract base class for LLM providers"""
    
    @abstractmethod
    def analyze(self, content: str, prompt: Optional[str] = None) -> str:
        """
        Analyze content using LLM
        
        Args:
            content: Text content to analyze
            prompt: Optional custom prompt
            
        Returns:
            Analysis result
        """
        pass


class LocalLLMProvider(LLMProvider):
    """Local LLM provider (LM Studio, Ollama, etc.)"""
    
    def __init__(
        self,
        base_url: str = "http://localhost:1234/v1",
        api_key: str = "lm-studio",
        model: str = "QuantFactory/Llama-3-8B-Instruct-Finance-RAG-GGUF",
        temperature: float = 0.7,
        max_tokens: int = 4096,
        chunk_size: int = 4000
    ):
        self.client = OpenAI(base_url=base_url, api_key=api_key)
        self.model = model
        self.temperature = temperature
        self.max_tokens = max_tokens
        self.chunk_size = chunk_size
        
    def analyze(self, content: str, prompt: Optional[str] = None) -> str:
        """
        Analyze content using local LLM
        
        Args:
            content: Text content to analyze
            prompt: Optional custom prompt
            
        Returns:
            Analysis result
        """
        try:
            # Use default Turkish financial analysis prompt if none provided
            if not prompt:
                prompt = (
                    "Kamu Aydınlatma Platformu (KAP) verilerini sana göndereceğim. "
                    "Türkçe olarak cevaplarını hazırla. "
                    "Verilen bildirimlerden yola çıkarak kısa ve orta vadeli yatırım yorumları yap. "
                    "Yatırım fırsatlarını değerlendir ve her yorumun yanında yatırımcılara yönelik "
                    "net tavsiyelerde bulun. Tavsiyelerinin dayandığı nedenleri açıkça belirt. "
                    "Cevaplarını Türkçe olarak hazırla ve finansal fırsatları detaylandır."
                )
            
            # Split content into chunks if needed
            chunks = self._chunk_content(content)
            responses = []
            
            for i, chunk in enumerate(chunks):
                logger.info(f"Analyzing chunk {i + 1}/{len(chunks)}")
                
                messages = [
                    {"role": "system", "content": prompt},
                    {"role": "user", "content": chunk}
                ]
                
                response = self.client.chat.completions.create(
                    model=self.model,
                    messages=messages,
                    temperature=self.temperature
                )
                
                responses.append(response.choices[0].message.content)
            
            return "\n\n".join(responses)
            
        except Exception as e:
            logger.error(f"Error analyzing content with LLM: {e}")
            return ""
    
    def _chunk_content(self, content: str) -> List[str]:
        """
        Split content into chunks to fit model context
        
        Args:
            content: Text to split
            
        Returns:
            List of content chunks
        """
        if len(content) <= self.chunk_size:
            return [content]
        
        chunks = []
        for i in range(0, len(content), self.chunk_size):
            chunks.append(content[i:i + self.chunk_size])
        
        return chunks


class OpenAIProvider(LLMProvider):
    """OpenAI API provider"""
    
    def __init__(
        self,
        api_key: str,
        model: str = "gpt-4",
        temperature: float = 0.7
    ):
        self.client = OpenAI(api_key=api_key)
        self.model = model
        self.temperature = temperature
    
    def analyze(self, content: str, prompt: Optional[str] = None) -> str:
        """Analyze content using OpenAI API"""
        try:
            if not prompt:
                prompt = (
                    "Analyze the following Turkish financial disclosure (KAP) data. "
                    "Provide investment insights and recommendations in Turkish."
                )
            
            messages = [
                {"role": "system", "content": prompt},
                {"role": "user", "content": content}
            ]
            
            response = self.client.chat.completions.create(
                model=self.model,
                messages=messages,
                temperature=self.temperature
            )
            
            return response.choices[0].message.content
            
        except Exception as e:
            logger.error(f"Error with OpenAI API: {e}")
            return ""


class GeminiProvider(LLMProvider):
    """Google Gemini API provider - uses REST API v1 for compatibility"""
    
    def __init__(
        self,
        api_key: str,
        model: str = "gemini-pro",
        temperature: float = 0.7,
        chunk_size: int = 30000  # Gemini has larger context window
    ):
        self.api_key = api_key
        self.model_name = model
        self.temperature = temperature
        self.chunk_size = chunk_size
        self.base_url = "https://generativelanguage.googleapis.com/v1"
        
        # Try SDK first, fallback to REST API
        self.use_rest_api = False
        if GEMINI_AVAILABLE:
            try:
                genai.configure(api_key=api_key)
                # Try to create model - if it fails, we'll use REST API
                test_model = genai.GenerativeModel(model)
                self.model = test_model
                logger.info(f"Using Gemini SDK with model: {model}")
            except Exception as e:
                logger.warning(f"Gemini SDK failed ({e}), will use REST API instead")
                self.use_rest_api = True
        else:
            logger.info("google-generativeai not available, using REST API")
            self.use_rest_api = True
    
    def analyze(self, content: str, prompt: Optional[str] = None) -> str:
        """Analyze content using Google Gemini API (REST API v1 for compatibility)"""
        try:
            import requests
            
            # Use default Turkish financial analysis prompt if none provided
            if not prompt:
                prompt = (
                    "Kamu Aydınlatma Platformu (KAP) verilerini sana göndereceğim. "
                    "Türkçe olarak cevaplarını hazırla. "
                    "Verilen bildirimlerden yola çıkarak kısa ve orta vadeli yatırım yorumları yap. "
                    "Yatırım fırsatlarını değerlendir ve her yorumun yanında yatırımcılara yönelik "
                    "net tavsiyelerde bulun. Tavsiyelerinin dayandığı nedenleri açıkça belirt. "
                    "Cevaplarını Türkçe olarak hazırla ve finansal fırsatları detaylandır."
                )
            
            # Combine prompt and content
            full_prompt = f"{prompt}\n\n{content}"
            
            # Use REST API v1 (more reliable than SDK)
            # Try different model names if the default fails
            model_to_try = self.model_name
            models_to_try = [
                self.model_name,
                "gemini-1.5-flash",
                "gemini-1.5-pro", 
                "gemini-pro",
                "models/gemini-1.5-flash",
                "models/gemini-1.5-pro"
            ]
            
            last_error = None
            for model_to_try in models_to_try:
                url = f"{self.base_url}/models/{model_to_try}:generateContent"
            
            payload = {
                "contents": [{
                    "parts": [{
                        "text": full_prompt
                    }]
                }],
                "generationConfig": {
                    "temperature": self.temperature
                }
            }
            
            headers = {"Content-Type": "application/json"}
            params = {"key": self.api_key}
            
            # Try different model names - COST OPTIMIZED ORDER (cheapest first)
            models_to_try = [
                "models/gemini-1.5-flash",  # COST OPTIMIZED: 75-80% cheaper than 2.5
                "models/gemini-2.0-flash",  # Fallback option 
                "models/gemini-2.5-flash",  # Expensive - only if others fail
                "models/gemini-2.0-flash-lite",  # Lightweight backup
                self.model_name  # User-specified
            ]
            
            last_error = None
            for model_to_try in models_to_try:
                url = f"{self.base_url}/{model_to_try}:generateContent"
                
                logger.info(f"Trying Gemini REST API v1 with model: {model_to_try}")
                
                try:
                    response = requests.post(url, json=payload, headers=headers, params=params, timeout=60)
                    
                    if response.status_code == 200:
                        data = response.json()
                        if 'candidates' in data and data['candidates']:
                            text = data['candidates'][0]['content']['parts'][0]['text']
                            logger.info(f"✅ Successfully got {len(text)} chars from Gemini using model: {model_to_try}")
                            return text
                        else:
                            logger.warning(f"No candidates in Gemini response for {model_to_try}")
                            continue
                    else:
                        error_text = response.text[:300]
                        last_error = f"{response.status_code}: {error_text}"
                        logger.debug(f"Model {model_to_try} failed: {last_error}")
                        continue
                except Exception as e:
                    last_error = str(e)
                    logger.debug(f"Exception with {model_to_try}: {e}")
                    continue
            
            # If all models failed, log the last error
            logger.error(f"All Gemini models failed. Last error: {last_error}")
            return ""
            
            # If all models failed, log the last error
            logger.error(f"All Gemini models failed. Last error: {last_error}")
            return ""
            
        except ImportError:
            logger.error("requests library required for Gemini REST API")
            return ""
        except Exception as e:
            logger.error(f"Error analyzing content with Gemini API: {e}", exc_info=True)
            return ""
    
    def _chunk_content(self, content: str) -> List[str]:
        """
        Split content into chunks to fit model context
        
        Args:
            content: Text to split
            
        Returns:
            List of content chunks
        """
        if len(content) <= self.chunk_size:
            return [content]
        
        chunks = []
        for i in range(0, len(content), self.chunk_size):
            chunks.append(content[i:i + self.chunk_size])
        
        return chunks


class HuggingFaceLocalProvider(LLMProvider):
    """HuggingFace local sentiment analysis provider"""

    def __init__(self, model_name: str = "savasy/bert-base-turkish-sentiment-cased", disclosure_type: str = 'Diğer', company_name: str = ""):
        try:
            from transformers import pipeline
            self.classifier = pipeline(
                "sentiment-analysis",
                model=model_name,
                tokenizer=model_name
            )
        except (ImportError, Exception) as e:
            logger.error(f"Failed to initialize HuggingFace pipeline: {e}")
            self.classifier = None
        self.disclosure_type = disclosure_type
        self.company_name = company_name


    def analyze(self, content: str, prompt: Optional[str] = None) -> str:
        """
        Analyze sentiment using a local HuggingFace model.

        Args:
            content: Text content to analyze.
            prompt: This is not used by this provider but is part of the interface.

        Returns:
            A JSON string with the sentiment analysis result.
        """
        if not self.classifier:
            return ""

        try:
            # This logic is adapted from `_analyze_sentiment_text_only`
            def tr_lower(text: str) -> str:
                return text.replace('I', 'ı').replace('İ', 'i').lower()

            content_processed = tr_lower(content)

            # --- Strategy 1: Transformer Model ---
            model_sentiment = None
            model_confidence = 0.0
            result = self.classifier(content[:2000])[0]
            mapping = {
                'POSITIVE': 'positive',
                'NEGATIVE': 'negative',
                'LABEL_0': 'negative',
                'LABEL_1': 'positive',
                'LABEL_2': 'neutral'
            }
            model_sentiment = mapping.get(result['label'], 'neutral')
            model_confidence = float(result['score'])

            # --- Strategy 2: Enhanced Financial Lexicon (simplified for provider) ---
            keywords = {
                'positive': ['artış', 'büyüme', 'başarı', 'kar', 'gelir', 'yatırım', 'kârlılık', 'temettü', 'iyileşme', 'onay'],
                'negative': ['zarar', 'düşüş', 'azalma', 'kayıp', 'risk', 'kriz', 'borç', 'daralma', 'ceza', 'iptal']
            }
            pos_score = sum(1 for word in keywords['positive'] if word in content_processed)
            neg_score = sum(1 for word in keywords['negative'] if word in content_processed)
            total_lexicon_score = pos_score - neg_score

            # --- Consolidation ---
            if model_sentiment:
                sentiment = model_sentiment
                confidence = model_confidence
                if sentiment == 'positive' and total_lexicon_score < -1:
                    sentiment = 'neutral'
                    confidence *= 0.7
            else:
                if total_lexicon_score > 1:
                    sentiment = 'positive'
                elif total_lexicon_score < -1:
                    sentiment = 'negative'
                else:
                    sentiment = 'neutral'
                confidence = min(0.9, 0.5 + (abs(total_lexicon_score) * 0.1))

            # --- KAP Specific Metadata Extraction ---
            long_term_types = ['Finansal Rapor', 'Faaliyet Raporu', 'Sermaye Artırımı', 'Birleşme ve Bölünme']
            short_term_types = ['Özel Durum Açıklaması (Genel)', 'Borsa Dışı İşlem', 'Devre Kesici']

            if self.disclosure_type in long_term_types:
                impact_horizon = 'long_term'
            elif any(t in self.disclosure_type for t in short_term_types):
                impact_horizon = 'short_term'
            else:
                impact_horizon = 'medium_term'

            risk_flags = [word for word in ['iflas', 'konkordato', 'dava', 'kur farkı'] if word in content_processed]
            key_drivers = [word for word in ['temettü', 'yatırım', 'yeni fabrika', 'beklenti'] if word in content_processed]
            
            if sentiment == 'positive':
                tone_descriptors = ['optimistic', 'confident']
            elif sentiment == 'negative':
                tone_descriptors = ['cautious', 'concerning']
            else:
                tone_descriptors = ['informative', 'neutral']
            
            analysis_text = (
                f"KAP Analizi ({self.company_name}): {self.disclosure_type} bildirimi '{sentiment.upper()}' olarak değerlendirildi "
                f"(Güven: %{confidence * 100:.0f})."
            )

            result_dict = {
                'overall_sentiment': sentiment,
                'confidence': float(confidence),
                'impact_horizon': impact_horizon,
                'key_drivers': key_drivers,
                'risk_flags': risk_flags,
                'tone_descriptors': tone_descriptors,
                'target_audience': 'investors',
                'analysis_text': analysis_text,
            }
            return json.dumps(result_dict)

        except Exception as e:
            logger.error(f"Error during HuggingFace sentiment analysis: {e}")
            return ""


class PDFReportGenerator:
    """Generate PDF reports from analysis results"""
    
    def __init__(self, font_path: Optional[str] = None):
        """
        Initialize PDF generator
        
        Args:
            font_path: Optional path to Unicode font directory
        """
        self.font_path = font_path or self._find_font_path()
    
    def _find_font_path(self) -> str:
        """Find font files in the project"""
        # Get the project root (relative to this file: utils/llm_analyzer.py)
        project_root = Path(__file__).parent.parent.parent
        
        # Try common locations (container paths and local paths)
        locations = [
            "/workspaces/firecrawl/getData_ff/llm",
            "/workspaces/firecrawl/examples/turkish-financial-data-scraper/utils",
            str(Path(__file__).parent),
            # Local development paths
            str(project_root / "getData_ff" / "llm"),
            str(Path(__file__).parent / "fonts"),
        ]
        
        for location in locations:
            font_file = os.path.join(location, "DejaVuSans.ttf")
            if os.path.exists(font_file):
                logger.debug(f"Found Unicode fonts at: {location}")
                return location
        
        logger.debug("Unicode fonts not found, PDF generation may use fallback fonts for Turkish text")
        return ""
    
    def generate_report(
        self,
        analyses: List[Dict[str, str]],
        output_path: str,
        title: str = "KAP Analysis Report"
    ) -> bool:
        """
        Generate PDF report from analyses
        
        Args:
            analyses: List of analysis results with 'title' and 'content'
            output_path: Output PDF file path
            title: Report title
            
        Returns:
            Success status
        """
        try:
            pdf = FPDF()
            
            # Add Unicode font if available
            if self.font_path:
                regular_font = os.path.join(self.font_path, "DejaVuSans.ttf")
                bold_font = os.path.join(self.font_path, "DejaVuSansBold.ttf")
                
                if os.path.exists(regular_font):
                    pdf.add_font('DejaVu', '', regular_font, uni=True)
                if os.path.exists(bold_font):
                    pdf.add_font('DejaVu', 'B', bold_font, uni=True)
            
            pdf.add_page()
            pdf.set_font('DejaVu', 'B', 16)
            pdf.cell(0, 10, title, 0, 1, 'C')
            pdf.ln(10)
            
            for analysis in analyses:
                # Section title
                pdf.set_font('DejaVu', 'B', 12)
                pdf.set_text_color(255, 0, 0)
                pdf.multi_cell(0, 10, analysis.get('title', 'Analysis'))
                pdf.ln(5)
                
                # Section content
                pdf.set_font('DejaVu', '', 11)
                pdf.set_text_color(0, 0, 0)
                pdf.multi_cell(0, 10, analysis.get('content', ''))
                pdf.ln(10)
            
            # Ensure output directory exists
            Path(output_path).parent.mkdir(parents=True, exist_ok=True)
            pdf.output(output_path, 'F')
            
            logger.info(f"Generated PDF report: {output_path}")
            return True
            
        except Exception as e:
            logger.error(f"Error generating PDF report: {e}")
            return False


class SentimentResult(BaseModel):
    """Structured sentiment analysis result"""
    overall_sentiment: str = Field(description="positive, neutral, or negative")
    confidence: float = Field(ge=0.0, le=1.0, description="Confidence score 0-1")
    impact_horizon: str = Field(description="short_term, medium_term, or long_term")
    key_drivers: List[str] = Field(default_factory=list, description="Key positive/negative factors")
    risk_flags: List[str] = Field(default_factory=list, description="Risk indicators")
    tone_descriptors: List[str] = Field(default_factory=list, description="Tone adjectives")
    target_audience: Optional[str] = Field(default=None, description="Target investor type")
    analysis_text: str = Field(description="Detailed analysis in Turkish")


class LLMAnalyzer:
    """Main analyzer class using dependency injection"""
    
    def __init__(
        self,
        provider: LLMProvider,
        report_generator: Optional[PDFReportGenerator] = None
    ):
        """
        Initialize analyzer with LLM provider
        
        Args:
            provider: LLM provider instance
            report_generator: Optional PDF report generator
        """
        self.provider = provider
        self.report_generator = report_generator or PDFReportGenerator()
    
    def analyze_reports(
        self,
        reports: List[Dict[str, Any]],
        prompt: Optional[str] = None
    ) -> List[Dict[str, str]]:
        """
        Analyze multiple reports
        
        Args:
            reports: List of report dictionaries with 'content' key
            prompt: Optional custom prompt
            
        Returns:
            List of analysis results
        """
        results = []
        
        for i, report in enumerate(reports):
            logger.info(f"Analyzing report {i + 1}/{len(reports)}")
            
            content = report.get('content', '')
            if not content:
                logger.warning(f"Empty content in report {i + 1}")
                continue
            
            analysis = self.provider.analyze(content, prompt)
            
            results.append({
                'title': report.get('title', f'Report {i + 1}'),
                'url': report.get('url', ''),
                'content': analysis
            })
        
        return results
    
    def generate_pdf_report(
        self,
        analyses: List[Dict[str, str]],
        output_path: str
    ) -> bool:
        """
        Generate PDF report from analyses
        
        Args:
            analyses: Analysis results
            output_path: Output file path
            
        Returns:
            Success status
        """
        return self.report_generator.generate_report(analyses, output_path)
    
    def analyze_sentiment(
        self,
        content: str,
        report_id: Optional[int] = None,
        custom_prompt: Optional[str] = None
    ) -> Optional[SentimentResult]:
        """
        Analyze sentiment with structured JSON output
        
        Args:
            content: Text content to analyze
            report_id: Optional report ID for tracking
            custom_prompt: Optional custom analysis prompt
            
        Returns:
            SentimentResult object or None if parsing fails
        """
        try:
            # Create sentiment-specific prompt
            if not custom_prompt:
                prompt = """
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
                
                Analiz yaparken:
                - Finansal göstergeleri (gelir, kar, borç) değerlendir
                - Piyasa etkisini tahmin et
                - Yatırımcılar için riskleri belirle
                - Kısa, orta ve uzun vadeli etkileri değerlendir
                
                SADECE JSON DÖNDÜR, BAŞKA HİÇBİR ŞEY YOK.
                """
            else:
                prompt = custom_prompt
            
            # Get LLM response
            logger.debug(f"Calling LLM provider with {len(content)} chars of content")
            response = self.provider.analyze(content, prompt)
            
            if not response:
                logger.error("Empty response from LLM - check API key and network connection")
                logger.debug(f"Provider type: {type(self.provider).__name__}")
                return None
            
            logger.debug(f"LLM response length: {len(response)} chars")
            logger.debug(f"LLM response preview: {response[:200]}...")
            
            # Extract JSON from response (handle cases where LLM adds extra text)
            json_match = re.search(r'\{.*\}', response, re.DOTALL)
            if json_match:
                json_str = json_match.group(0)
            else:
                # Try to parse entire response as JSON
                json_str = response.strip()
            
            # Remove markdown code blocks if present
            json_str = re.sub(r'```json\s*', '', json_str)
            json_str = re.sub(r'```\s*', '', json_str)
            json_str = json_str.strip()
            
            # Parse JSON
            try:
                data = json.loads(json_str)
                
                # Validate and create SentimentResult
                result = SentimentResult(
                    overall_sentiment=data.get("overall_sentiment", "neutral").lower(),
                    confidence=float(data.get("confidence", 0.5)),
                    impact_horizon=data.get("impact_horizon", "medium_term"),
                    key_drivers=data.get("key_drivers", []),
                    risk_flags=data.get("risk_flags", []),
                    tone_descriptors=data.get("tone_descriptors", []),
                    target_audience=data.get("target_audience"),
                    analysis_text=data.get("analysis_text", response)
                )
                
                logger.info(f"Successfully parsed sentiment: {result.overall_sentiment} (confidence: {result.confidence})")
                return result
                
            except json.JSONDecodeError as e:
                logger.error(f"Failed to parse JSON from LLM response: {e}")
                logger.debug(f"Response was: {response[:500]}")
                return None
            except Exception as e:
                logger.error(f"Error creating SentimentResult: {e}")
                return None
                
        except Exception as e:
            logger.error(f"Error in sentiment analysis: {e}", exc_info=True)
            return None
    
    def analyze_sentiment_batch(
        self,
        reports: List[Dict[str, Any]],
        custom_prompt: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """
        Analyze sentiment for multiple reports
        
        Args:
            reports: List of reports with 'content' and optionally 'id' keys
            custom_prompt: Optional custom prompt
            
        Returns:
            List of sentiment results with report metadata
        """
        results = []
        
        for i, report in enumerate(reports):
            logger.info(f"Analyzing sentiment for report {i + 1}/{len(reports)}")
            
            content = report.get('content', '')
            report_id = report.get('id')
            
            if not content:
                logger.warning(f"Empty content in report {i + 1}")
                continue
            
            sentiment = self.analyze_sentiment(content, report_id, custom_prompt)
            
            if sentiment:
                results.append({
                    'report_id': report_id,
                    'report_title': report.get('title', f'Report {i + 1}'),
                    'sentiment': sentiment.dict(),
                    'analyzed_at': datetime.now().isoformat()
                })
            else:
                logger.warning(f"Failed to analyze sentiment for report {i + 1}")
        
        return results
