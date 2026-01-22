"""
LLM Analysis utilities for financial data
Supports local and cloud LLM providers with Strategy Pattern
"""
import logging
from abc import ABC, abstractmethod
from typing import Dict, Any, List, Optional
from pathlib import Path
from openai import OpenAI
from fpdf import FPDF
import os

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
        # Try common locations
        locations = [
            "/workspaces/firecrawl/getData_ff/llm",
            "/workspaces/firecrawl/examples/turkish-financial-data-scraper/utils",
            str(Path(__file__).parent)
        ]
        
        for location in locations:
            font_file = os.path.join(location, "DejaVuSans.ttf")
            if os.path.exists(font_file):
                return location
        
        logger.warning("Unicode fonts not found, PDF generation may fail for Turkish text")
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
