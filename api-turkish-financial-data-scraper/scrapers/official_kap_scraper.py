"""
Official KAP.org.tr Scraper using Firecrawl Base

Scrapes KAP (Kamuyu Aydınlatma Platformu) disclosures directly from the official source.
This is the primary source for all disclosure data.

Source: https://kap.org.tr/en/

Strategy:
1. Scrape main disclosure pages using Firecrawl
2. Parse HTML to extract disclosure items 
3. Follow detail links for full content
4. Perform LLM sentiment analysis on extracted content
5. Save both disclosure data and sentiment analysis to database
"""
import asyncio
import logging
import re
from typing import Dict, Any, List, Optional
from datetime import datetime, timedelta
from bs4 import BeautifulSoup
from scrapers.base_scraper import BaseScraper
from utils.llm_analyzer import LLMAnalyzer, LocalLLMProvider, OpenAIProvider, GeminiProvider

logger = logging.getLogger(__name__)


class OfficialKAPScraper(BaseScraper):
    """Official KAP.org.tr scraper using Firecrawl base"""
    
    BASE_URL = "https://kap.org.tr"
    DISCLOSURES_URL = f"{BASE_URL}/en/Bildirim/"
    
    def __init__(self, *args, **kwargs):
        """Initialize Official KAP scraper"""
        super().__init__(*args, **kwargs)
        self.llm_analyzer = None  # Lazy initialization
        logger.info("Initialized OfficialKAPScraper")
    
    def configure_llm(
        self,
        provider_type: str = "local",
        **provider_config
    ):
        """
        Configure LLM provider for sentiment analysis
        
        Args:
            provider_type: 'local', 'openai', or 'gemini'
            **provider_config: Provider-specific configuration
        """
        if provider_type == "local":
            provider = LocalLLMProvider(**provider_config)
        elif provider_type == "openai":
            provider = OpenAIProvider(**provider_config)
        elif provider_type == "gemini":
            provider = GeminiProvider(**provider_config)
        else:
            raise ValueError(f"Unknown provider type: {provider_type}. Supported: local, openai, gemini")
        
        self.llm_analyzer = LLMAnalyzer(provider)
        logger.info(f"Configured {provider_type} LLM provider for sentiment analysis")

    async def scrape(self, **kwargs) -> Dict[str, Any]:
        """
        Main scrape method following base scraper pattern
        
        Args:
            **kwargs: Scraper parameters
            
        Returns:
            Scraped data results
        """
        try:
            logger.info("Starting Official KAP scraping...")
            
            # Step 1: Scrape main page using Firecrawl
            main_page_result = await self.scrape_url(self.DISCLOSURES_URL)
            
            if not main_page_result.get("success"):
                logger.error(f"Failed to scrape main page: {main_page_result.get('error')}")
                return {
                    "success": False,
                    "error": "Failed to scrape main page",
                    "scraped_items": 0,
                    "saved_items": 0
                }
            
            # Step 2: Parse HTML content to extract disclosure items
            data = main_page_result.get("data", {})
            html_content = data.get("html", "")
            markdown_content = data.get("markdown", "")
            
            logger.info(f"Retrieved content: {len(html_content)} chars HTML, {len(markdown_content)} chars markdown")
            
            # Step 3: Extract disclosure items from HTML
            disclosure_items = self._parse_disclosure_items_from_html(html_content)
            logger.info(f"Extracted {len(disclosure_items)} disclosure items")
            
            if not disclosure_items:
                # Try parsing from markdown as fallback
                disclosure_items = self._parse_disclosure_items_from_markdown(markdown_content)
                logger.info(f"Fallback markdown parsing found {len(disclosure_items)} items")
            
            # Step 4: Process each disclosure item
            saved_count = 0
            for item in disclosure_items:
                try:
                    # Save to database if db_manager is available
                    if self.db_manager and item.get('company_name'):
                        self._save_disclosure_to_db(item)
                        saved_count += 1
                        
                        # Optional: Perform sentiment analysis
                        if self.llm_analyzer and item.get('content'):
                            sentiment = await self._analyze_sentiment(item)
                            if sentiment:
                                self._save_sentiment_to_db(item.get('id'), sentiment)
                        
                except Exception as e:
                    logger.error(f"Error processing disclosure item: {e}")
                    continue
            
            logger.info(f"Successfully scraped {len(disclosure_items)} items, saved {saved_count} to database")
            
            return {
                "success": True,
                "scraped_items": len(disclosure_items),
                "saved_items": saved_count,
                "items": disclosure_items[:5],  # Return sample for testing
                "source_url": self.DISCLOSURES_URL,
                "scraper": self.__class__.__name__
            }
            
        except Exception as e:
            logger.error(f"Error in KAP scraping: {e}", exc_info=True)
            return {
                "success": False,
                "error": str(e),
                "scraped_items": 0,
                "saved_items": 0
            }

    def _parse_disclosure_items_from_html(self, html_content: str) -> List[Dict[str, Any]]:
        """
        Parse disclosure items from HTML content
        
        Args:
            html_content: Raw HTML from KAP website
            
        Returns:
            List of disclosure items
        """
        if not html_content:
            logger.warning("No HTML content to parse")
            return []
        
        try:
            soup = BeautifulSoup(html_content, 'html.parser')
            items = []
            
            # Debug: Check page structure
            logger.info("Analyzing HTML structure...")
            
            # Look for common table structures
            tables = soup.find_all('table')
            logger.info(f"Found {len(tables)} tables")
            
            # Look for disclosure-like patterns
            rows = soup.find_all('tr')
            logger.info(f"Found {len(rows)} table rows")
            
            # Strategy 1: Look for table rows with disclosure data
            for i, row in enumerate(rows):
                cells = row.find_all(['td', 'th'])
                if len(cells) >= 3:  # Minimum columns for disclosure data
                    
                    # Extract text from cells
                    cell_texts = [cell.get_text(strip=True) for cell in cells]
                    
                    # Skip header rows
                    if i == 0 or any(header in ' '.join(cell_texts).lower() for header in [
                        'company', 'date', 'type', 'başlık', 'şirket', 'tarih'
                    ]):
                        continue
                    
                    # Look for company patterns (Turkish companies end with A.Ş., A.S., etc.)
                    company_text = ""
                    for text in cell_texts:
                        if self._is_company_name(text):
                            company_text = text
                            break
                    
                    if company_text:
                        # Extract other data
                        date_text = self._extract_date_from_cells(cell_texts)
                        title_text = self._extract_title_from_cells(cell_texts)
                        
                        # Look for detail link
                        detail_link = ""
                        for cell in cells:
                            link = cell.find('a', href=True)
                            if link:
                                href = link['href']
                                if href.startswith('/'):
                                    detail_link = f"{self.BASE_URL}{href}"
                                elif href.startswith('http'):
                                    detail_link = href
                                break
                        
                        item = {
                            'id': f"kap_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{len(items)}",
                            'company_name': company_text,
                            'title': title_text or "KAP Disclosure",
                            'disclosure_type': self._extract_disclosure_type(cell_texts),
                            'published_date': self._parse_date(date_text) if date_text else datetime.now(),
                            'content': self._build_content_from_cells(cell_texts),
                            'detail_url': detail_link,
                            'source_url': self.DISCLOSURES_URL,
                            'data': {
                                'cells': cell_texts,
                                'scraper': self.__class__.__name__,
                                'scraped_at': datetime.now().isoformat()
                            }
                        }
                        
                        items.append(item)
                        logger.debug(f"Extracted item: {company_text} - {title_text}")
            
            # Strategy 2: Look for divs with disclosure-like content if no table data
            if not items:
                logger.info("No table data found, trying div-based extraction...")
                divs = soup.find_all('div')
                
                for div in divs:
                    text = div.get_text(strip=True)
                    if len(text) > 50 and self._contains_company_indicators(text):
                        item = {
                            'id': f"kap_div_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{len(items)}",
                            'company_name': self._extract_company_from_text(text),
                            'title': text[:100],
                            'disclosure_type': 'General',
                            'published_date': datetime.now(),
                            'content': text,
                            'detail_url': '',
                            'source_url': self.DISCLOSURES_URL,
                            'data': {
                                'source_type': 'div',
                                'scraper': self.__class__.__name__,
                                'scraped_at': datetime.now().isoformat()
                            }
                        }
                        items.append(item)
            
            logger.info(f"Parsed {len(items)} disclosure items from HTML")
            return items
            
        except Exception as e:
            logger.error(f"Error parsing HTML: {e}")
            return []

    def _parse_disclosure_items_from_markdown(self, markdown_content: str) -> List[Dict[str, Any]]:
        """
        Parse disclosure items from markdown content as fallback
        
        Args:
            markdown_content: Markdown content from Firecrawl
            
        Returns:
            List of disclosure items
        """
        if not markdown_content:
            return []
        
        try:
            items = []
            lines = markdown_content.split('\n')
            
            # Look for table-like structures in markdown
            current_item = {}
            in_table = False
            
            for line in lines:
                line = line.strip()
                
                # Check for table rows (markdown format)
                if '|' in line and len(line.split('|')) >= 3:
                    in_table = True
                    cells = [cell.strip() for cell in line.split('|') if cell.strip()]
                    
                    # Look for company data
                    for cell in cells:
                        if self._is_company_name(cell):
                            current_item = {
                                'id': f"kap_md_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{len(items)}",
                                'company_name': cell,
                                'title': self._extract_title_from_cells(cells),
                                'disclosure_type': 'General',
                                'published_date': datetime.now(),
                                'content': ' | '.join(cells),
                                'detail_url': '',
                                'source_url': self.DISCLOSURES_URL,
                                'data': {
                                    'source_type': 'markdown_table',
                                    'scraper': self.__class__.__name__,
                                    'scraped_at': datetime.now().isoformat()
                                }
                            }
                            items.append(current_item)
                            break
                
                # Look for company mentions in regular text
                elif self._contains_company_indicators(line):
                    company = self._extract_company_from_text(line)
                    if company:
                        item = {
                            'id': f"kap_md_text_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{len(items)}",
                            'company_name': company,
                            'title': line[:100],
                            'disclosure_type': 'General',
                            'published_date': datetime.now(),
                            'content': line,
                            'detail_url': '',
                            'source_url': self.DISCLOSURES_URL,
                            'data': {
                                'source_type': 'markdown_text',
                                'scraper': self.__class__.__name__,
                                'scraped_at': datetime.now().isoformat()
                            }
                        }
                        items.append(item)
            
            logger.info(f"Parsed {len(items)} items from markdown")
            return items
            
        except Exception as e:
            logger.error(f"Error parsing markdown: {e}")
            return []

    def _is_company_name(self, text: str) -> bool:
        """Check if text looks like a Turkish company name"""
        if not text or len(text) < 3:
            return False
        
        text = text.upper()
        
        # Turkish company suffixes
        company_suffixes = [
            'A.Ş.', 'A.S.', 'T.A.Ş.', 'T.A.S.', 'LTD.', 'LTD', 'ŞTİ.', 'STI.',
            'BANKASI', 'BANK', 'SİGORTA', 'GAYRİMENKUL', 'HOLDİNG', 'YATIRIM'
        ]
        
        return any(suffix in text for suffix in company_suffixes)

    def _contains_company_indicators(self, text: str) -> bool:
        """Check if text contains company-related indicators"""
        indicators = [
            'A.Ş.', 'A.S.', 'BANKASI', 'HOLDİNG', 'LTD', 'ŞTİ', 'SİGORTA',
            'açıklama', 'bildirim', 'disclosure', 'announcement'
        ]
        
        text_upper = text.upper()
        return any(indicator.upper() in text_upper for indicator in indicators)

    def _extract_company_from_text(self, text: str) -> str:
        """Extract company name from text"""
        # Look for patterns ending with company suffixes
        patterns = [
            r'([A-ZÇĞİÖŞÜ][A-ZÇĞİÖŞÜa-zçğıöşü\s]+(?:A\.Ş\.|A\.S\.|\sBankası))',
            r'([A-ZÇĞİÖŞÜ][A-ZÇĞİÖŞÜa-zçğıöşü\s]+(?:HOLDİNG|LTD|ŞTİ))',
        ]
        
        for pattern in patterns:
            match = re.search(pattern, text)
            if match:
                return match.group(1).strip()
        
        return text.split()[0] if text.split() else ""

    def _extract_date_from_cells(self, cells: List[str]) -> str:
        """Extract date from table cells"""
        for cell in cells:
            # Look for date patterns
            date_patterns = [
                r'\d{1,2}[./]\d{1,2}[./]\d{4}',
                r'\d{4}-\d{2}-\d{2}',
                r'\d{1,2}\s+\w+\s+\d{4}'
            ]
            
            for pattern in date_patterns:
                match = re.search(pattern, cell)
                if match:
                    return match.group(0)
        
        return ""

    def _extract_title_from_cells(self, cells: List[str]) -> str:
        """Extract title from table cells"""
        for cell in cells:
            if len(cell) > 20 and not self._is_company_name(cell):
                # Skip cells that look like dates or codes
                if not re.match(r'^[\d\s/.-]+$', cell) and len(cell.split()) > 2:
                    return cell[:200]  # Limit title length
        
        return ""

    def _extract_disclosure_type(self, cells: List[str]) -> str:
        """Extract disclosure type from cells"""
        type_keywords = {
            'özel durum': 'Special Situation',
            'genel': 'General',
            'finansal': 'Financial',
            'financial': 'Financial',
            'special': 'Special Situation',
            'general': 'General'
        }
        
        for cell in cells:
            cell_lower = cell.lower()
            for keyword, disclosure_type in type_keywords.items():
                if keyword in cell_lower:
                    return disclosure_type
        
        return 'General'

    def _build_content_from_cells(self, cells: List[str]) -> str:
        """Build content from table cells"""
        return ' | '.join(cells)

    def _parse_date(self, date_text: str) -> datetime:
        """Parse date text to datetime object"""
        try:
            # Try different date formats
            formats = [
                '%d.%m.%Y',
                '%d/%m/%Y',
                '%Y-%m-%d',
                '%d %m %Y'
            ]
            
            for fmt in formats:
                try:
                    return datetime.strptime(date_text, fmt)
                except ValueError:
                    continue
                    
        except:
            pass
        
        return datetime.now()

    def _save_disclosure_to_db(self, item: Dict[str, Any]):
        """Save disclosure to database"""
        try:
            # Prepare data for kap_disclosures table
            db_data = {
                'id': item['id'],
                'company_name': item['company_name'][:255],
                'company_code': self._extract_company_code(item['company_name']),
                'title': item['title'][:500],
                'disclosure_type': item['disclosure_type'],
                'summary': item['content'][:1000],
                'content': item['content'],
                'published_date': item['published_date'],
                'detail_url': item.get('detail_url', ''),
                'source_url': item['source_url'],
                'data': item['data'],
                'scraped_at': datetime.now()
            }
            
            # Use base scraper's save method
            self.save_to_db(db_data, 'kap_disclosures')
            logger.debug(f"Saved disclosure: {item['company_name']}")
            
        except Exception as e:
            logger.error(f"Error saving disclosure to DB: {e}")

    def _extract_company_code(self, company_name: str) -> str:
        """Extract company stock code from name (simple extraction)"""
        # This is a simple extraction - in practice, you'd need a mapping table
        name_parts = company_name.split()
        if name_parts:
            return name_parts[0][:10].upper()
        return ""

    async def _analyze_sentiment(self, item: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Analyze sentiment of disclosure content"""
        if not self.llm_analyzer or not item.get('content'):
            return None
        
        try:
            analysis = await self.llm_analyzer.analyze_sentiment_async(
                text=item['content'],
                language="turkish"
            )
            return analysis
        except Exception as e:
            logger.error(f"Error in sentiment analysis: {e}")
            return None

    def _save_sentiment_to_db(self, disclosure_id: str, sentiment: Dict[str, Any]):
        """Save sentiment analysis to database"""
        try:
            db_data = {
                'disclosure_id': disclosure_id,
                'overall_sentiment': sentiment.get('sentiment', 'neutral'),
                'confidence': sentiment.get('confidence', 0.0),
                'positive_score': sentiment.get('scores', {}).get('positive', 0.0),
                'negative_score': sentiment.get('scores', {}).get('negative', 0.0),
                'neutral_score': sentiment.get('scores', {}).get('neutral', 0.0),
                'key_topics': sentiment.get('topics', []),
                'analysis_text': sentiment.get('analysis', ''),
                'analyzed_at': datetime.now()
            }
            
            self.save_to_db(db_data, 'kap_disclosure_sentiment')
            logger.debug(f"Saved sentiment analysis for {disclosure_id}")
            
        except Exception as e:
            logger.error(f"Error saving sentiment to DB: {e}")


# For backwards compatibility and testing
class KAPOrgScraper(OfficialKAPScraper):
    """Alias for OfficialKAPScraper"""
    pass