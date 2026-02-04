#!/usr/bin/env python3
"""
Production KAP Scraper - Fixed Version

Final production-ready KAP scraper with all fixes applied.
Integrates with Firecrawl base scraper infrastructure.
"""

import asyncio
import sys
import os
import logging
import json
import random
import re
from datetime import datetime, timedelta
from pathlib import Path
from dotenv import load_dotenv
from typing import Optional

# Try to import Firecrawl API
try:
    from firecrawl import FirecrawlApp
    FIRECRAWL_AVAILABLE = True
except ImportError:
    FIRECRAWL_AVAILABLE = False
    logger_temp = logging.getLogger(__name__)
    logger_temp.warning("Firecrawl SDK not available, using direct Playwright service")

# Try to import LLM analyzer for advanced sentiment analysis
try:
    from utils.llm_analyzer import (
        LLMAnalyzer,
        GeminiProvider,
        LocalLLMProvider,
        OpenAIProvider,
        HuggingFaceLocalProvider
    )
    LLM_AVAILABLE = True
except ImportError:
    LLM_AVAILABLE = False

# Configure logging for production
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Load environment variables from .env if present
load_dotenv()


class ProductionKAPScraper:
    """Production-ready KAP scraper with Firecrawl API"""
    
    
    def __init__(self, use_test_data=False, use_llm=False, llm_provider: Optional[str] = None):
        """Initialize production scraper"""
        # Initialize Firecrawl API client for advanced scraping with actions
        self.firecrawl_api_key = os.getenv("FIRECRAWL_API_KEY", "test-api-key")
        self.firecrawl_api_url = os.getenv("FIRECRAWL_API_URL", "http://localhost:3002")
        
        # Always set playwright_url as fallback
        self.playwright_url = os.getenv("PLAYWRIGHT_SERVICE_URL", "http://localhost:3000/scrape")
        
        if FIRECRAWL_AVAILABLE:
            self.firecrawl = FirecrawlApp(api_key=self.firecrawl_api_key, api_url=self.firecrawl_api_url)
            logger.info(f"Firecrawl API initialized: {self.firecrawl_api_url}")
        else:
            self.firecrawl = None
            logger.warning("Using Playwright service as fallback")
        
        self.base_url = "https://kap.org.tr"
        self.disclosures_url = f"{self.base_url}/tr/"  # Turkish homepage
        self.use_test_data = use_test_data
        
        # Initialize LLM analyzer if available
        self.llm_analyzer = None
        self._llm_provider_override = llm_provider
        self._llm_fallback_warned = False  # Track if we've warned about using fallback
        if LLM_AVAILABLE and use_llm:
            try:
                provider = self._build_llm_provider()
                self.llm_analyzer = LLMAnalyzer(provider)
                logger.info(
                    "Initialized LLM analyzer for sentiment analysis using %s",
                    provider.__class__.__name__
                )
            except Exception as e:
                logger.warning(
                    "Failed to initialize LLM analyzer from environment: %s. Sentiment analysis will be skipped.",
                    e
                )
        else:
            logger.info("LLM analyzer not enabled, using keyword-based sentiment analysis")
        
        # Initialize sentiment cache for cost optimization
        self.sentiment_cache = {}
        
        logger.info("Production KAP Scraper initialized")

    def configure_llm(self, provider_type: str = "local", **provider_config):
        """Configure LLM provider for sentiment analysis"""
        if not LLM_AVAILABLE:
            raise RuntimeError("LLM analyzer not available in this environment")

        if provider_type == "local":
            provider = LocalLLMProvider(**provider_config)
        elif provider_type == "openai":
            provider = OpenAIProvider(**provider_config)
        elif provider_type == "gemini":
            provider = GeminiProvider(**provider_config)
        elif provider_type == "huggingface":
            provider = HuggingFaceLocalProvider(**provider_config)
        else:
            raise ValueError(
                f"Unknown provider type: {provider_type}. Supported: local, openai, gemini, huggingface"
            )

        self.llm_analyzer = LLMAnalyzer(provider)
        logger.info(f"Configured {provider_type} LLM provider")

    def _build_llm_provider(self):
        """Build LLM provider from environment configuration."""
        provider_type = self._llm_provider_override or os.getenv("SENTIMENT_PROVIDER")
        if not provider_type:
            if os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY"):
                provider_type = "gemini"
            elif os.getenv("OPENAI_API_KEY"):
                provider_type = "openai"
            elif os.getenv("LOCAL_LLM_BASE_URL"):
                provider_type = "local_llm"
            else:
                provider_type = "huggingface"
        provider_type = provider_type.lower()

        if provider_type == "gemini":
            api_key = os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")
            if not api_key:
                raise ValueError("GEMINI_API_KEY or GOOGLE_API_KEY is not set")
            model = os.getenv("GEMINI_MODEL", "gemini-1.5-flash")
            temperature = float(os.getenv("GEMINI_TEMPERATURE", "0.3"))
            chunk_size = int(os.getenv("GEMINI_CHUNK_SIZE", "2000"))
            return GeminiProvider(
                api_key=api_key,
                model=model,
                temperature=temperature,
                chunk_size=chunk_size
            )

        if provider_type == "openai":
            api_key = os.getenv("OPENAI_API_KEY")
            if not api_key:
                raise ValueError("OPENAI_API_KEY is not set")
            model = os.getenv("OPENAI_MODEL", "gpt-4")
            temperature = float(os.getenv("OPENAI_TEMPERATURE", "0.7"))
            return OpenAIProvider(api_key=api_key, model=model, temperature=temperature)

        if provider_type == "local_llm":
            base_url = os.getenv("LOCAL_LLM_BASE_URL", "http://localhost:1234/v1")
            api_key = os.getenv("LOCAL_LLM_API_KEY", "lm-studio")
            model = os.getenv("LOCAL_LLM_MODEL", "QuantFactory/Llama-3-8B-Instruct-Finance-RAG-GGUF")
            temperature = float(os.getenv("LOCAL_LLM_TEMPERATURE", "0.7"))
            max_tokens = int(os.getenv("LOCAL_LLM_MAX_TOKENS", "4096"))
            chunk_size = int(os.getenv("LOCAL_LLM_CHUNK_SIZE", "4000"))
            return LocalLLMProvider(
                base_url=base_url,
                api_key=api_key,
                model=model,
                temperature=temperature,
                max_tokens=max_tokens,
                chunk_size=chunk_size
            )

        model_name = os.getenv("HF_SENTIMENT_MODEL", "savasy/bert-base-turkish-sentiment-cased")
        return HuggingFaceLocalProvider(model_name=model_name)
    
    async def scrape_url(self, url: str) -> dict:
        """Scrape URL using Firecrawl API for details, Playwright with button clicking for homepage"""
        import aiohttp
        
        try:
            logger.info(f"Scraping: {url}")
            
            # For KAP homepage, use Playwright service with button clicking
            if url == self.disclosures_url:
                logger.info("Using Playwright service for KAP homepage (with button clicking for pagination)")
                return await self._click_and_scrape_homepage(url)
            
            # For detail pages and other URLs, use Firecrawl API when available
            elif self.firecrawl:
                logger.info("Using Firecrawl API for detail page scraping")
                try:
                    result = self.firecrawl.scrape(
                        url,
                        formats=["html"],
                        wait_for=3000
                    )
                    
                    # Result is a Document object, access attributes directly
                    if result and result.html:
                        html_content = result.html
                        logger.info(f"Scraped {url}: {len(html_content):,} chars HTML")
                        
                        return {
                            "success": True,
                            "url": url,
                            "data": {
                                "html": html_content,
                                "markdown": result.markdown or "",
                                "metadata": {"statusCode": 200, "error": None, "source": "firecrawl_api"}
                            }
                        }
                    else:
                        logger.warning(f"Firecrawl API failed for {url}")
                        return await self._fallback_scrape_url(url)
                
                except Exception as e:
                    logger.error(f"Firecrawl API error for {url}: {e}")
                    return await self._fallback_scrape_url(url)
            
            # Fallback to direct Playwright service if Firecrawl not available
            else:
                return await self._fallback_scrape_url(url)
            
        except Exception as e:
            logger.error(f"Scraping failed {url}: {e}")
            return {"success": False, "url": url, "error": str(e)}
    
    async def _click_and_scrape_homepage(self, url: str) -> dict:
        """Click 'Daha Fazla Göster' button repeatedly and scrape all items"""
        import aiohttp
        import time
        
        try:
            logger.info(f"Starting interactive scraping of {url} with button clicking")
            
            payload = {
                "url": url,
                "wait_after_load": 5000,
                "timeout": 180000,  # 3 minutes for interactive scraping
            }
            
            async with aiohttp.ClientSession() as session:
                # First load the page
                async with session.post(self.playwright_url, json=payload) as response:
                    if response.status != 200:
                        raise Exception(f"Initial page load failed: {response.status}")
                    
                    result = await response.json()
                    html_content = result.get('content', '')
                    logger.info(f"Initial page loaded: {len(html_content):,} chars")
                
                # Now repeatedly click the "Daha Fazla Göster" button
                click_payload = {
                    "url": url,
                    "wait_after_load": 3000,  # Shorter wait between clicks
                    "timeout": 180000,
                    "action": "click",
                    "selector": "button:has-text('Daha Fazla Göster')"  # Click "Show More" button
                }
                
                max_clicks = 20  # Increased from 10 to 20 to ensure we load all items
                clicks = 0
                previous_size = 0
                stable_count = 0  # Count how many times size hasn't changed
                max_stable_count = 3  # If size hasn't changed 3 times in a row, we're done
                
                while clicks < max_clicks:
                    try:
                        # Try to click the button
                        async with session.post(self.playwright_url, json=click_payload) as response:
                            if response.status != 200:
                                logger.info(f"Button click {clicks + 1}: No more button or click failed (status {response.status})")
                                break
                            
                            result = await response.json()
                            html_content = result.get('content', '')
                            current_size = len(html_content)
                            
                            # Check if content size changed
                            if current_size == previous_size:
                                stable_count += 1
                                logger.info(f"Click {clicks + 1}: Size unchanged (stable_count={stable_count}/{max_stable_count})")
                                
                                if stable_count >= max_stable_count:
                                    logger.info(f"Content size stable after {stable_count} stable clicks, stopping")
                                    break
                            else:
                                stable_count = 0  # Reset counter if size changed
                            
                            clicks += 1
                            previous_size = current_size
                            size_delta = current_size - previous_size if clicks > 1 else 0
                            logger.info(f"Click {clicks}: page size: {current_size:,} chars (delta: {size_delta:+,})")
                            
                            # Very short delay between clicks
                            await asyncio.sleep(0.2)
                    
                    except Exception as e:
                        logger.warning(f"Error during button click {clicks + 1}: {e}")
                        break
                
                logger.info(f"Finished clicking button: {clicks} total clicks, Final HTML size: {len(html_content):,} chars")
                
                return {
                    "success": True,
                    "url": url,
                    "data": {
                        "html": html_content,
                        "markdown": "",
                        "metadata": {
                            "statusCode": 200,
                            "error": None,
                            "source": "playwright_button_clicking",
                            "button_clicks": clicks,
                            "final_html_size": len(html_content)
                        }
                    }
                }
        
        except Exception as e:
            logger.error(f"Button clicking scrape failed for {url}: {e}")
            # Fallback to simple scrape without clicking
            return await self._fallback_scrape_url(url)
    
    async def get_pdf_attachments_from_detail(self, detail_url: str) -> list:
        """Extract PDF attachment URLs from disclosure detail page"""
        import aiohttp
        from bs4 import BeautifulSoup
        
        if not detail_url:
            return []
        
        try:
            # Scrape the detail page
            result = await self.scrape_url(detail_url)
            if not result.get('success'):
                return []
            
            content = result.get('data', {}).get('html', '')
            soup = BeautifulSoup(content, 'html.parser')
            
            # Find all download links for PDF files
            pdf_attachments = []
            download_links = soup.find_all('a', href=lambda x: x and '/api/file/download/' in x)
            
            for link in download_links:
                href = link.get('href', '')
                text = link.get_text(strip=True)
                
                if href and ('pdf' in text.lower() or href):
                    full_url = f"https://kap.org.tr{href}" if href.startswith('/') else href
                    pdf_attachments.append({
                        'url': full_url,
                        'filename': text
                    })
            
            logger.info(f"Found {len(pdf_attachments)} PDF attachments on {detail_url}")
            return pdf_attachments
            
        except Exception as e:
            logger.error(f"Error extracting PDF attachments from {detail_url}: {e}")
            return []
    
    async def scrape_pdf(self, pdf_url: str) -> dict:
        """Scrape PDF content using pdfplumber for direct PDF parsing"""
        import io
        import aiohttp
        import pdfplumber
        
        if not pdf_url:
            return {"success": False, "error": "No PDF URL provided"}
        
        try:
            logger.info(f"Fetching PDF: {pdf_url}")
            
            # Download PDF file directly
            async with aiohttp.ClientSession() as session:
                async with session.get(pdf_url, timeout=aiohttp.ClientTimeout(total=60)) as response:
                    if response.status != 200:
                        logger.warning(f"PDF fetch failed {pdf_url}: {response.status}")
                        return {"success": False, "error": f"Status {response.status}"}
                    
                    # Read PDF content
                    pdf_content = await response.read()
                    
                    # Parse PDF using pdfplumber
                    pdf_file = io.BytesIO(pdf_content)
                    
                    try:
                        with pdfplumber.open(pdf_file) as pdf:
                            # Extract text from all pages
                            text_parts = []
                            for page in pdf.pages:
                                page_text = page.extract_text()
                                if page_text:
                                    text_parts.append(page_text)
                            
                            full_text = '\n\n'.join(text_parts)
                            
                            if len(full_text) > 100:  # If we got substantial content
                                logger.info(f"Extracted PDF text: {len(full_text):,} chars from {len(pdf.pages)} pages")
                                return {"success": True, "text": full_text, "length": len(full_text), "pages": len(pdf.pages)}
                            else:
                                logger.warning(f"PDF extraction returned minimal content: {len(full_text)} chars")
                                return {"success": False, "error": "Minimal content extracted", "text": full_text}
                    
                    except Exception as pdf_error:
                        logger.error(f"PDF parsing error {pdf_url}: {pdf_error}")
                        return {"success": False, "error": f"PDF parse error: {str(pdf_error)}"}
            
        except Exception as e:
            logger.error(f"PDF scraping failed {pdf_url}: {e}")
            return {"success": False, "error": str(e)}

    
    def parse_kap_disclosures(self, html: str, markdown: str) -> list:
        """Parse KAP disclosures with Turkish content support"""
        items = []
        
        try:
            from bs4 import BeautifulSoup
            import re
            
            soup = BeautifulSoup(html, 'html.parser')
            
            # Advanced parsing for Turkish company disclosures from HTML table
            tables = soup.find_all('table')
            logger.info(f"Analyzing {len(tables)} tables for disclosure data")
            
            for table_idx, table in enumerate(tables):
                rows = table.find_all('tr')
                logger.debug(f"Table {table_idx} has {len(rows)} rows")
                
                for row_idx, row in enumerate(rows):
                    cells = row.find_all(['td', 'th'])
                    
                    if len(cells) >= 3:  # Need at least: checkbox, number/date, company, disclosure, etc.
                        cell_texts = [cell.get_text(strip=True) for cell in cells]
                        row_text = ' | '.join(cell_texts)
                        
                        logger.debug(f"Row {row_idx}: {len(cells)} cells - {row_text[:100]}")
                        
                        # Turkish company pattern detection
                        if self.contains_turkish_company(row_text):
                            company = self.extract_company_name(row_text)
                            
                            if company:
                                # Extract date/time information
                                timestamp_info = self.extract_timestamp_from_row(row_text, cell_texts)
                                
                                # Extract detail URL - check for links in the row
                                detail_url = self.extract_detail_url(cells)
                                if not detail_url:
                                    # Try to find disclosure ID from text and construct URL
                                    detail_url = self.construct_detail_url(row_text, cell_texts)
                                
                                timestamp_str = datetime.now().strftime("%Y%m%d_%H%M%S")
                                item = {
                                    'disclosure_id': f'live_kap_{timestamp_str}_{len(items)}',
                                    'company_name': company,
                                    'disclosure_type': self.extract_disclosure_type(row_text),
                                    'disclosure_date': timestamp_info.get('date', datetime.now().date()),
                                    'timestamp': timestamp_info.get('time', datetime.now().strftime("%H:%M")),
                                    'language_info': self.extract_language_info(row_text, cells),
                                    'has_attachment': self.check_attachments(cells),
                                    'detail_url': detail_url,
                                    'content': row_text,
                                    'data': {
                                        'cells': cell_texts,
                                        'cell_count': len(cells),
                                        'table_index': table_idx,
                                        'row_index': row_idx,
                                        'source': 'kap.org.tr',
                                        'scraped_at': datetime.now().isoformat()
                                    }
                                }
                                
                                items.append(item)
                                logger.info(f"Found disclosure: {company} - {item['disclosure_type']} - URL: {detail_url[:60]}")
            
            # Strategy 2: Div-based parsing (for modern/responsive layouts)
            if not items:
                logger.info("No table items found, attempting div-based parsing")
                # Look for div rows that might contain disclosure info
                div_rows = soup.find_all('div', class_=re.compile(r'(row|list-item|notification|bildirim-satir|disclosure-row|disclosure|item)', re.I))
                
                for i, row in enumerate(div_rows):
                    row_text = row.get_text(" ", strip=True)
                    
                    if len(row_text) > 20 and self.contains_turkish_company(row_text):
                        company = self.extract_company_name(row_text)
                        if company:
                            timestamp_str = datetime.now().strftime("%Y%m%d_%H%M%S")
                            detail_url = self.extract_detail_url(row.find_all('a'))
                            
                            item = {
                                'disclosure_id': f'live_kap_div_{timestamp_str}_{len(items)}',
                                'company_name': company,
                                'disclosure_type': self.extract_disclosure_type(row_text),
                                'disclosure_date': datetime.now().date(),
                                'timestamp': datetime.now().strftime("%H:%M"),
                                'language_info': self.extract_language_info(row_text, []),
                                'has_attachment': self.check_attachments(row.find_all('a')),
                                'detail_url': detail_url,
                                'content': row_text,
                                'data': {
                                    'source': 'kap.org.tr',
                                    'parsing_method': 'div_row',
                                    'scraped_at': datetime.now().isoformat()
                                }
                            }
                            items.append(item)
                            logger.info(f"Found div-based disclosure: {company}")

        except Exception as e:
            logger.error(f"Parsing error: {e}", exc_info=True)
        
        return items
    
    def contains_turkish_company(self, text: str) -> bool:
        """Detect Turkish company names"""
        if not text or len(text) < 5:
            return False
        
        # Turkish company suffixes and patterns
        turkish_patterns = [
            r'[A-ZÇĞİÖŞÜ][A-ZÇĞİÖŞÜa-zçğıöşü\s\.\-]{2,}A\.Ş\.?',
            r'[A-ZÇĞİÖŞÜ][A-ZÇĞİÖŞÜa-zçğıöşü\s\.\-]{2,}BANKASI',
            r'[A-ZÇĞİÖŞÜ][A-ZÇĞİÖŞÜa-zçğıöşü\s\.\-]{2,}HOLDİNG',
            r'[A-ZÇĞİÖŞÜ][A-ZÇĞİÖŞÜa-zçğıöşü\s\.\-]{2,}T\.A\.Ş\.?'
        ]
        
        import re
        for pattern in turkish_patterns:
            if re.search(pattern, text):
                return True
        
        return False
    
    def extract_company_name(self, text: str) -> str:
        """Extract Turkish company name"""
        import re
        
        # Remove common prefixes like "1-", "2-", "3-" etc. from summary tables
        text = re.sub(r'^\d+-', '', text)
        
        patterns = [
            r'([A-ZÇĞİÖŞÜ][A-ZÇĞİÖŞÜa-zçğıöşü\s\.\-]{2,}(?:A\.Ş\.?|A\.S\.?))',
            r'([A-ZÇĞİÖŞÜ][A-ZÇĞİÖŞÜa-zçğıöşü\s\.\-]{2,}BANKASI)',
            r'([A-ZÇĞİÖŞÜ][A-ZÇĞİÖŞÜa-zçğıöşü\s\.\-]{2,}HOLDİNG)',
            r'([A-ZÇĞİÖŞÜ][A-ZÇĞİÖŞÜa-zçğıöşü\s\.\-]{2,}T\.A\.Ş\.?)'
        ]
        
        for pattern in patterns:
            match = re.search(pattern, text)
            if match:
                return match.group(1).strip()
        
        return ""
    
    def extract_disclosure_type(self, text: str) -> str:
        """Extract disclosure type from Turkish content"""
        text_lower = text.lower()
        
        type_mapping = {
            'özel durum': 'Özel Durum Açıklaması',
            'finansal': 'Finansal Rapor',
            'mali': 'Finansal Rapor',
            'genel kurul': 'Genel Kurul',
            'sermaye': 'Sermaye İşlemleri',
            'duyuru': 'Duyuru',
            'kar payı': 'Kar Payı Dağıtımı',
            'pay geri': 'Pay Geri Alımı',
            'temettü': 'Temettü',
            'sorumluluk beyanı': 'Sorumluluk Beyanı',
            'faaliyet raporu': 'Faaliyet Raporu',
            'ihraç': 'İhraç İşlemleri',
            'transfer': 'Transfer İşlemleri'
        }
        
        for keyword, disc_type in type_mapping.items():
            if keyword in text_lower:
                return disc_type
        
        return 'Diğer'
    
    def extract_timestamp_from_row(self, row_text: str, cell_texts: list) -> dict:
        """Extract timestamp information from table row"""
        result = {
            'date': datetime.now().date(),
            'time': datetime.now().strftime("%H:%M")
        }
        
        try:
            import re
            # Look for time patterns like "22:26", "14:30" etc in the cells
            for cell_text in cell_texts:
                # Match Turkish date/time patterns like "Dün 22:26", "Bugün 14:30", "15 gün önce"
                time_match = re.search(r'(\d{1,2}):(\d{2})', cell_text)
                if time_match:
                    result['time'] = f"{time_match.group(1)}:{time_match.group(2)}"
                    break
            
            # Check for date markers
            if 'Dün' in row_text or 'dün' in row_text:
                result['date'] = (datetime.now() - timedelta(days=1)).date()
            elif 'Bugün' in row_text or 'bugün' in row_text:
                result['date'] = datetime.now().date()
            
        except Exception as e:
            logger.debug(f"Error extracting timestamp: {e}")
        
        return result
    
    def extract_language_info(self, row_text: str, cells=None) -> str:
        """Extract language information from disclosure row"""
        # Check for language indicators in the content
        if 'İngilizce' in row_text or 'English' in row_text:
            return 'Turkish, English'
        elif 'Ekli Dosya' in row_text:
            return 'Turkish'
        else:
            return 'Turkish'
    
    def check_attachments(self, cells) -> bool:
        """Check for attachment indicators"""
        if not cells:
            return False
            
        cell_list = cells if isinstance(cells, list) else [cells]
        
        for cell in cell_list:
            # Check if it's a BeautifulSoup element
            if hasattr(cell, 'find_all'):
                text = cell.get_text(strip=True) if hasattr(cell, 'get_text') else str(cell)
                if any(indicator in text for indicator in ['Ekli', 'Dosya', 'Attachment', 'PDF', 'excel']):
                    return True
                
                links = cell.find_all('a') if hasattr(cell, 'find_all') else []
                for link in links:
                    href = link.get('href', '') or ''
                    if any(indicator in href.lower() for indicator in ['attach', 'file', 'pdf', 'doc', 'excel']):
                        return True
            else:
                # Plain string
                if any(indicator in str(cell) for indicator in ['Ekli', 'Dosya', 'Attachment', 'PDF']):
                    return True
        
        return False
    
    def extract_detail_url(self, cells) -> str:
        """Extract detail URL from cells"""
        if not cells:
            return ""
            
        cell_list = cells if isinstance(cells, list) else [cells]
        
        for cell in cell_list:
            # Check if it's a BeautifulSoup element
            if hasattr(cell, 'find_all'):
                links = cell.find_all('a', href=True)
                for link in links:
                    href = link.get('href', '')
                    if href.startswith('/'):
                        return f"{self.base_url}{href}"
                    elif href.startswith('http'):
                        return href
        
        return ""

    def construct_detail_url(self, row_text: str, cell_texts: list) -> str:
        """Construct detail URL from row information"""
        try:
            import re
            
            # Try to extract disclosure ID from the row text
            # Look for numeric patterns that might be disclosure IDs
            disclosure_id_match = re.search(r'\b(\d{4,8})\b', row_text)
            
            if disclosure_id_match:
                disclosure_id = disclosure_id_match.group(1)
                # KAP disclosure URL format: https://kap.org.tr/tr/Bildirim/{disclosure_id}
                return f"{self.base_url}/tr/Bildirim/{disclosure_id}"
            
            # Alternative: Try to find ID in cells
            for i, cell_text in enumerate(cell_texts):
                if cell_text.isdigit() and 1000 <= int(cell_text) <= 999999:
                    return f"{self.base_url}/tr/Bildirim/{cell_text}"
            
        except Exception as e:
            logger.debug(f"Could not construct detail URL: {e}")
        
        return ""

    
    def generate_realistic_test_data(self) -> list:
        """Generate realistic test data for demonstration"""
        import random
        
        companies = [
            "ANADOLU HAYAT EMEKLİLİK A.Ş.",
            "GARANTİ BANKASI A.Ş.",
            "TÜRK HAVA YOLLARI A.Ş.",
            "BİM BİRLEŞİK MAĞAZALAR A.Ş.",
            "KOÇ HOLDİNG A.Ş.",
            "SABANCI HOLDİNG A.Ş.",
            "AKBANK T.A.Ş.",
            "PETROL OFİSİ A.Ş."
        ]
        
        disclosure_types = [
            "Özel Durum Açıklaması",
            "Finansal Rapor",
            "Genel Kurul",
            "Sermaye Artırımı",
            "Duyuru"
        ]
        
        content_templates = [
            "{company} yönetim kurulu kararı alınmıştır.",
            "{company} dönemlik finansal sonuçları açıklanmıştır.",
            "{company} olağan genel kurul toplantısı yapılacaktır.",
            "{company} sermaye artırımı gerçekleştirilecektir.",
            "{company} önemli bilgilendirme duyurusu."
        ]
        
        items = []
        timestamp_str = datetime.now().strftime("%Y%m%d_%H%M%S")
        
        for i, company in enumerate(companies[:5]):
            disc_type = random.choice(disclosure_types)
            content_template = random.choice(content_templates)
            
            item = {
                'disclosure_id': f'demo_kap_{timestamp_str}_{i}',
                'company_name': company,
                'disclosure_type': disc_type,
                'disclosure_date': (datetime.now() - timedelta(hours=random.randint(1, 48))).date(),
                'timestamp': f"{random.randint(9, 17):02d}:{random.randint(0, 59):02d}",
                'language_info': 'Turkish',
                'has_attachment': random.choice([True, False]),
                'detail_url': f'https://kap.org.tr/tr/Bildirim/{random.randint(100000, 999999)}',
                'content': content_template.format(company=company),
                'data': {
                    'source': 'demo_data',
                    'generated_at': datetime.now().isoformat(),
                    'note': 'Demonstration data showing KAP scraper functionality',
                    'company_category': self.categorize_company(company)
                }
            }
            
            items.append(item)
        
        logger.info(f'Generated {len(items)} realistic test disclosures')
        return items
    
    def categorize_company(self, company_name: str) -> str:
        """Categorize company by name"""
        name_lower = company_name.lower()
        
        if 'bank' in name_lower or 'finansal' in name_lower:
            return 'Finansal Hizmetler'
        elif 'holding' in name_lower:
            return 'Holding'
        elif 'hava yolları' in name_lower or 'taşımacılık' in name_lower:
            return 'Ulaştırma'
        elif 'mağaza' in name_lower or 'perakende' in name_lower:
            return 'Perakende'
        else:
            return 'Diğer'
    
    def get_content_hash(self, content: str, company_name: str, disclosure_type: str) -> str:
        """Generate hash for content caching to avoid duplicate LLM calls"""
        import hashlib
        cache_key = f"{company_name}:{disclosure_type}:{content[:200]}"
        return hashlib.md5(cache_key.encode()).hexdigest()
    
    def analyze_sentiment(self, content: str, company_name: str, disclosure_type: str, use_llm: Optional[bool] = None) -> dict:
        """Perform sentiment analysis using the configured provider."""
        
        # Check cache first
        cache_key = self.get_content_hash(content, company_name, disclosure_type)
        if cache_key in self.sentiment_cache:
            logger.debug(f"Using cached sentiment for {company_name}")
            return self.sentiment_cache[cache_key]

        if not self.llm_analyzer:
            if not self._llm_fallback_warned:
                logger.debug("Using fallback keyword-based sentiment analysis")
                self._llm_fallback_warned = True
            # Use fallback sentiment analysis
            return self._fallback_sentiment_analysis(content, company_name, disclosure_type)

        try:
            # The provider is now configured via dependencies to be HuggingFace, Gemini, etc.
            # We pass company_name and disclosure_type to the provider context if it's HuggingFace
            if isinstance(self.llm_analyzer.provider, HuggingFaceLocalProvider):
                self.llm_analyzer.provider.company_name = company_name
                self.llm_analyzer.provider.disclosure_type = disclosure_type

            result = self.llm_analyzer.analyze_sentiment(content=content)
            
            if result:
                sentiment_result = result.dict()
                sentiment_result['provider'] = self.llm_analyzer.provider.__class__.__name__
                sentiment_result['risk_level'] = 'high' if len(result.risk_flags) >= 2 else ('medium' if len(result.risk_flags) == 1 else 'low')
                
                # Cache the result
                self.sentiment_cache[cache_key] = sentiment_result
                return sentiment_result
            else:
                logger.warning(f"Sentiment analysis returned no result for {company_name}")
                return {}

        except Exception as e:
            logger.error(f"Error during sentiment analysis for {company_name}: {e}", exc_info=True)
            return {}

    def _fallback_sentiment_analysis(self, content: str, company_name: str, disclosure_type: str) -> dict:
        """Fallback sentiment analysis using keyword matching when LLM unavailable"""
        
        if not content:
            return {
                'overall_sentiment': 'neutral',
                'confidence': 0.5,
                'provider': 'fallback_keyword',
                'impact_horizon': 'unknown',
                'key_drivers': ['insufficient_content'],
                'risk_flags': [],
                'tone_descriptors': [],
                'target_audience': 'company_officials',
                'analysis_text': 'Insufficient content for analysis'
            }
        
        content_lower = content.lower()
        
        # Turkish sentiment keywords
        positive_keywords = [
            'artış', 'yüksek', 'iyi', 'başarı', 'başarılı', 'kazanç', 'kar', 'büyüme', 
            'gelişme', 'iyileşme', 'güçlü', 'pozitif', 'olumlu', 'kazanı', 'verimlil',
            'artan', 'arttı', 'yükseldi', 'iyileşti', 'başardı'
        ]
        
        negative_keywords = [
            'azalış', 'düşük', 'kötü', 'kayıp', 'zarara', 'kaybetme', 'risk', 'tehdit',
            'zayıf', 'negatif', 'olumsuz', 'olumsuzluk', 'düşüş', 'geriş', 'zayıf',
            'azalda', 'düştü', 'geriledi', 'kötüleşti', 'sorun', 'sorunlar', 'krizp'
        ]
        
        # Count sentiment indicators
        positive_count = sum(1 for word in positive_keywords if word in content_lower)
        negative_count = sum(1 for word in negative_keywords if word in content_lower)
        
        # Determine sentiment
        if positive_count > negative_count * 1.5:
            sentiment = 'positive'
            confidence = 0.6
        elif negative_count > positive_count * 1.5:
            sentiment = 'negative'
            confidence = 0.6
        else:
            sentiment = 'neutral'
            confidence = 0.5
        
        # Identify risk flags
        risk_flags = []
        risk_keywords = ['risk', 'zararı', 'kayıp', 'sorun', 'tehdit', 'olumsuz']
        for keyword in risk_keywords:
            if keyword in content_lower:
                risk_flags.append(keyword)
                break
        
        return {
            'overall_sentiment': sentiment,
            'confidence': confidence,
            'provider': 'fallback_keyword',
            'impact_horizon': 'unknown',
            'key_drivers': [disclosure_type] if disclosure_type else ['financial_disclosure'],
            'risk_flags': risk_flags,
            'tone_descriptors': ['financial_disclosure', 'official_statement'],
            'target_audience': 'company_officials',
            'analysis_text': f'Fallback keyword analysis: {positive_count} positive, {negative_count} negative indicators'
        }

    def generate_pdf_url(self, detail_url: str) -> str:
        """Generate PDF URL from detail URL
        
        Converts: https://kap.org.tr/tr/Bildirim/1537677
        To:       https://kap.org.tr/tr/api/BildirimPdf/1537677
        """
        if not detail_url:
            return ""
        
        import re
        # Extract ID from detail URL
        match = re.search(r'/Bildirim/(\d+)', detail_url)
        if match:
            disclosure_id = match.group(1)
            return f"https://kap.org.tr/tr/api/BildirimPdf/{disclosure_id}"
        
        return ""

    async def save_to_database(self, items: list) -> int:
        """Save items to PostgreSQL database"""
        try:
            import psycopg2
            
            # Use environment variables for database connection
            conn = psycopg2.connect(
                host=os.getenv('DB_HOST', 'localhost'),
                port=int(os.getenv('DB_PORT', '5432')),
                database=os.getenv('DB_NAME', 'backtofuture'),
                user=os.getenv('DB_USER', 'backtofuture'),
                password=os.getenv('DB_PASSWORD', 'back2future')
            )
            cursor = conn.cursor()
            
            # Set search path to use turkish_financial schema
            cursor.execute("SET search_path TO turkish_financial,public;")
            
            saved_count = 0
            
            for item in items:
                # Skip test data
                # This check ensures that if test data is somehow generated, it's not saved to the database
                if 'Test verisi' in item.get('content', ''):
                    logger.debug(f"Skipping test data: {item['disclosure_id']}")
                    continue
                    
                try:
                    # Generate PDF URL from detail URL
                    pdf_url = self.generate_pdf_url(item.get('detail_url', ''))
                    pdf_text = item.get('pdf_text', '')
                    
                    cursor.execute("""
                        INSERT INTO kap_disclosures 
                        (disclosure_id, company_name, disclosure_type, disclosure_date, 
                         timestamp, language_info, has_attachment, detail_url, pdf_url, pdf_text, content, data, scraped_at)
                        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                        ON CONFLICT (disclosure_id) DO UPDATE SET
                            content = EXCLUDED.content,
                            data = EXCLUDED.data,
                            pdf_url = EXCLUDED.pdf_url,
                            pdf_text = EXCLUDED.pdf_text,
                            scraped_at = EXCLUDED.scraped_at
                    """, (
                        item['disclosure_id'],
                        item['company_name'],
                        item['disclosure_type'],
                        item['disclosure_date'],
                        item['timestamp'],
                        item['language_info'],
                        item['has_attachment'],
                        item['detail_url'],
                        pdf_url,
                        pdf_text,
                        item['content'],
                        json.dumps(item['data']),
                        datetime.now()
                    ))
                    saved_count += 1
                    
                except Exception as e:
                    logger.error(f"Error saving {item['disclosure_id']}: {e}")
                    continue
            
            conn.commit()
            cursor.close()
            conn.close()
            
            logger.info(f"Saved {saved_count} items to database")
            return saved_count
            
        except Exception as e:
            logger.error(f"Database save failed: {e}")
            return 0
    
    async def save_sentiment_analysis(self, items: list) -> int:
        """Save sentiment analysis to database"""
        try:
            import psycopg2
            
            # Use environment variables for database connection
            conn = psycopg2.connect(
                host=os.getenv('DB_HOST', 'localhost'),
                port=int(os.getenv('DB_PORT', '5432')),
                database=os.getenv('DB_NAME', 'backtofuture'),
                user=os.getenv('DB_USER', 'backtofuture'),
                password=os.getenv('DB_PASSWORD', 'back2future')
            )
            cursor = conn.cursor()
            
            # Set search path to use turkish_financial schema
            cursor.execute("SET search_path TO turkish_financial,public;")
            
            saved_count = 0
            pdf_analyzed_count = 0
            html_analyzed_count = 0
            total_pdf_content_chars = 0
            total_html_content_chars = 0
            
            for item in items:
                # Skip test data
                # This check ensures that if test data is somehow generated, sentiment analysis is not performed on it
                if 'Test verisi' in item.get('content', ''):
                    logger.debug(f"Skipping sentiment analysis for test data: {item['disclosure_id']}")
                    continue
                    
                try:
                    # Get the database ID of the disclosure
                    cursor.execute("""
                        SELECT id FROM kap_disclosures 
                        WHERE disclosure_id = %s
                    """, (item['disclosure_id'],))
                    
                    result = cursor.fetchone()
                    if not result:
                        logger.warning(f"No disclosure found for {item['disclosure_id']}")
                        continue
                    
                    disclosure_db_id = result[0]
                    
                    # Prepare content for sentiment analysis
                    # Priority: PDF text (if available) + HTML content
                    pdf_text = item.get('pdf_text', '')
                    html_content = item.get('content', '')
                    
                    # Build analysis content with PDF text preferred
                    if pdf_text and len(pdf_text) > 100:
                        # Use PDF text for more detailed analysis
                        analysis_content = f"Company: {item['company_name']}\nDisclosure Type: {item['disclosure_type']}\n\nDocument Content:\n{pdf_text[:10000]}"
                        logger.info(f"Analyzing PDF content for {item['company_name']}: {len(pdf_text):,} chars")
                    else:
                        # Fall back to HTML content if PDF text not available
                        analysis_content = html_content
                        if pdf_text:
                            logger.debug(f"PDF text too short ({len(pdf_text)} chars) for {item['company_name']}, using HTML content")
                    
                    # Perform sentiment analysis on PDF or HTML content
                    sentiment_data = self.analyze_sentiment(
                        analysis_content, 
                        item['company_name'], 
                        item['disclosure_type']
                    )
                    
                    # Skip if sentiment analysis failed (no LLM analyzer available)
                    if not sentiment_data or not sentiment_data.get('overall_sentiment'):
                        logger.warning(f"Sentiment analysis failed for {item['company_name']} - No sentiment result")
                        continue
                    
                    # Add metadata about which content was analyzed
                    if pdf_text and len(pdf_text) > 100:
                        sentiment_data['analyzed_from'] = 'pdf_document'
                        sentiment_data['analysis_content_length'] = len(pdf_text)
                    else:
                        sentiment_data['analyzed_from'] = 'html_disclosure'
                        sentiment_data['analysis_content_length'] = len(html_content)
                    
                    # Check if sentiment already exists
                    cursor.execute("""
                        SELECT id FROM kap_disclosure_sentiment 
                        WHERE disclosure_id = %s
                    """, (disclosure_db_id,))
                    
                    sentiment_exists = cursor.fetchone()
                    
                    # Prepare sentiment data for database (map to actual schema)
                    overall_sentiment = sentiment_data.get('overall_sentiment', 'neutral')
                    sentiment_score = sentiment_data.get('confidence', 0.5)
                    
                    # Combine key sentiments
                    key_sentiments_list = []
                    if sentiment_data.get('key_drivers'):
                        key_sentiments_list.extend(sentiment_data['key_drivers'])
                    if sentiment_data.get('tone_descriptors'):
                        key_sentiments_list.extend(sentiment_data['tone_descriptors'])
                    if sentiment_data.get('risk_flags'):
                        key_sentiments_list.extend(sentiment_data['risk_flags'])
                    
                    key_sentiments = json.dumps(key_sentiments_list) if key_sentiments_list else json.dumps([])
                    
                    # Prepare analysis notes
                    analysis_notes = sentiment_data.get('analysis_text', '')
                    
                    if sentiment_exists:
                        # Update existing sentiment
                        cursor.execute("""
                            UPDATE kap_disclosure_sentiment 
                            SET overall_sentiment = %s, 
                                sentiment_score = %s, 
                                key_sentiments = %s, 
                                analysis_notes = %s
                            WHERE disclosure_id = %s
                        """, (
                            overall_sentiment,
                            sentiment_score,
                            key_sentiments,
                            analysis_notes,
                            disclosure_db_id
                        ))
                    else:
                        # Insert new sentiment analysis
                        cursor.execute("""
                            INSERT INTO kap_disclosure_sentiment 
                            (disclosure_id, overall_sentiment, sentiment_score, 
                             key_sentiments, analysis_notes)
                            VALUES (%s, %s, %s, %s, %s)
                        """, (
                            disclosure_db_id,
                            overall_sentiment,
                            sentiment_score,
                            key_sentiments,
                            analysis_notes
                        ))
                    
                    saved_count += 1
                    
                    # Track sentiment analysis source
                    source = sentiment_data.get('analyzed_from', 'unknown')
                    content_len = sentiment_data.get('analysis_content_length', 0)
                    
                    if source == 'pdf_document':
                        pdf_analyzed_count += 1
                        total_pdf_content_chars += content_len
                    elif source == 'html_disclosure':
                        html_analyzed_count += 1
                        total_html_content_chars += content_len
                    
                    # Log sentiment analysis result with content source
                    sentiment = sentiment_data.get('overall_sentiment', 'neutral')
                    logger.info(
                        f"Sentiment analysis saved: {item['company_name']} - "
                        f"Sentiment: {sentiment} - Source: {source} ({content_len:,} chars)"
                    )
                    
                except Exception as e:
                    logger.error(f"Error saving sentiment for {item['disclosure_id']}: {e}")
                    continue
            
            conn.commit()
            cursor.close()
            conn.close()
            
            # Log detailed sentiment analysis summary
            logger.info("=" * 70)
            logger.info("SENTIMENT ANALYSIS SUMMARY")
            logger.info("=" * 70)
            logger.info(f"Total sentiment analyses saved: {saved_count}")
            logger.info(f"  ✓ Analyzed from PDF documents: {pdf_analyzed_count} ({total_pdf_content_chars:,} chars)")
            logger.info(f"  ✓ Analyzed from HTML disclosures: {html_analyzed_count} ({total_html_content_chars:,} chars)")
            logger.info(f"Total content analyzed: {total_pdf_content_chars + total_html_content_chars:,} characters")
            if total_pdf_content_chars > 0:
                pdf_ratio = (pdf_analyzed_count / saved_count * 100) if saved_count > 0 else 0
                logger.info(f"PDF-based sentiment analysis: {pdf_ratio:.1f}% of items")
            logger.info("=" * 70)
            
            return saved_count
            
        except Exception as e:
            logger.error(f"Sentiment analysis save failed: {e}")
            return 0
    
    async def run_production_scrape(self) -> dict:
        """Run production scraping workflow"""
        try:
            logger.info("Starting production KAP scraping workflow")
            
            # Step 1: Scrape KAP website
            result = await self.scrape_url(self.disclosures_url)
            
            if not result.get("success"):
                logger.error(f"Failed to scrape KAP: {result.get('error')}")
                return {
                    "success": False,
                    "error": "Failed to scrape KAP website",
                    "items_scraped": 0,
                    "items_saved": 0
                }
            
            # Step 2: Parse content
            data = result["data"]
            html = data.get("html", "")
            markdown = data.get("markdown", "")
            
            logger.info(f"Retrieved content: {len(html):,} HTML chars, {len(markdown):,} markdown chars")
            
            # Step 3: Extract disclosures
            items = self.parse_kap_disclosures(html, markdown)
            
            # Step 4: Handle no-data scenario
            if not items:
                if self.use_test_data:
                    logger.info("No live disclosures found, generating demo data")
                    items = self.generate_realistic_test_data()
                else:
                    logger.info("No disclosures available at this time")
                    return {
                        "success": True,
                        "message": "No current disclosures available",
                        "items_scraped": 0,
                        "items_saved": 0,
                        "content_stats": {
                            "html_chars": len(html),
                            "markdown_chars": len(markdown)
                        }
                    }
            
            # Step 4.5: Fetch PDF attachments and content for items with detail URLs
            logger.info("Fetching PDF content for disclosures...")
            pdf_fetch_count = 0
            total_pdf_chars = 0
            
            for item in items:
                detail_url = item.get('detail_url', '')
                if detail_url:
                    # Get PDF attachments from detail page
                    attachments = await self.get_pdf_attachments_from_detail(detail_url)
                    
                    if attachments:
                        # Extract text from all PDF attachments
                        pdf_texts = []
                        for attachment in attachments:
                            pdf_result = await self.scrape_pdf(attachment['url'])
                            if pdf_result.get('success'):
                                text = pdf_result.get('text', '')
                                if text:
                                    pdf_texts.append(f"=== {attachment['filename']} ===\n{text}")
                                    pdf_fetch_count += 1
                        
                        # Combine all PDF texts
                        combined_text = '\n\n'.join(pdf_texts)
                        item['pdf_text'] = combined_text
                        total_pdf_chars += len(combined_text)
                        
                        if combined_text:
                            logger.info(f"PDF extracted for {item['company_name']}: {len(combined_text):,} chars from {len(attachments)} files")
                    else:
                        item['pdf_text'] = ''
                        logger.debug(f"No PDF attachments found for {item['company_name']}")
                else:
                    item['pdf_text'] = ''
            
            logger.info(f"Successfully fetched {pdf_fetch_count} PDF files, total {total_pdf_chars:,} chars extracted")
            
            # Step 5: Save to database
            saved_count = await self.save_to_database(items)
            
            # Step 6: Perform and save sentiment analysis
            sentiment_count = 0
            if items and saved_count > 0:
                logger.info("Running sentiment analysis on scraped items...")
                sentiment_count = await self.save_sentiment_analysis(items)
            
            logger.info(f"Production scrape completed: {len(items)} items scraped, {saved_count} saved, {sentiment_count} sentiment analyses")
            
            return {
                "success": True,
                "items_scraped": len(items),
                "items_saved": saved_count,
                "sentiment_analyses": sentiment_count,
                "items_sample": items[:3],  # Sample for verification
                "content_stats": {
                    "html_chars": len(html),
                    "markdown_chars": len(markdown)
                },
                "scraping_timestamp": datetime.now().isoformat()
            }
            
        except Exception as e:
            logger.error(f"Production scrape failed: {e}")
            return {
                "success": False,
                "error": str(e),
                "items_scraped": 0,
                "items_saved": 0
            }


async def main():
    """Main production workflow"""
    print("🚀 Production KAP Scraper - Live Deployment")
    print("=" * 55)
    
    try:
        # Instantiate scraper to use live data and enable LLM for sentiment analysis
        scraper = ProductionKAPScraper(use_test_data=False, use_llm=True)
        
        print("📥 Running production KAP scraping...")
        result = await scraper.run_production_scrape()
        
        if result.get("success"):
            print("✅ Production scraping completed successfully!")
            print(f"   📊 Items scraped: {result['items_scraped']}")
            print(f"   💾 Items saved: {result['items_saved']}")
            print(f"   🧠 Sentiment analyses: {result.get('sentiment_analyses', 0)}")
            
            stats = result.get("content_stats", {})
            print(f"   📄 Content processed: {stats.get('html_chars', 0):,} HTML chars")
            
            # Show sample items
            items = result.get("items_sample", [])
            if items:
                print("\n📋 Sample items:")
                for i, item in enumerate(items, 1):
                    company = item.get('company_name', 'N/A')[:30]
                    disc_type = item.get('disclosure_type', 'N/A')
                    print(f"   {i}. {company} - {disc_type}")
            
            timestamp = result['scraping_timestamp']
            print(f"\n🕒 Scraping timestamp: {timestamp}")
            print("\n🎉 KAP scraper is ready for production deployment!")
            
        else:
            error = result.get("error", "Unknown error")
            print(f"❌ Production scraping failed: {error}")
        
    except Exception as e:
        print(f"❌ Production workflow failed: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    asyncio.run(main())