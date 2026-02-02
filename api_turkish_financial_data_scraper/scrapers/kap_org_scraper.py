"""
KAP.org.tr Official Portal Scraper

Scrapes disclosure and announcement data directly from the official KAP portal.
This is the primary source for all Turkish capital market disclosures.

Source: https://kap.org.tr/en

Strategy:
1. Scrape main page to get list of disclosure items with details
2. Follow each disclosure link to detail page for full content
3. Extract structured data including company info, disclosure type, and content
4. Perform LLM sentiment analysis on extracted content
5. Save both disclosure data and sentiment analysis to database

The main page shows a table with:
- Company Name
- Disclosure Type
- Date/Time
- Language/Attachment indicators
- Link to detail page
"""

import logging
import re
import asyncio
from typing import Dict, Any, List, Optional
from datetime import datetime, timedelta
from bs4 import BeautifulSoup
from .base_scraper import BaseScraper

# Optional imports for LLM analysis (will handle import errors gracefully)
try:
    from utils.llm_analyzer import LLMAnalyzer, LocalLLMProvider, OpenAIProvider, GeminiProvider
    LLM_AVAILABLE = True
except ImportError:
    logger.debug("LLM analyzer modules not available")
    LLM_AVAILABLE = False

logger = logging.getLogger(__name__)


class KAPOrgScraper(BaseScraper):
    """Scraper for official KAP.org.tr disclosure portal"""
    
    BASE_URL = "https://kap.org.tr"
    MAIN_PAGE_URL = f"{BASE_URL}/en"
    
    def __init__(self, *args, **kwargs):
        """Initialize KAP.org scraper"""
        super().__init__(*args, **kwargs)
        self.llm_analyzer = None  # Lazy initialization
        logger.info("Initialized KAPOrgScraper")
    
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
        if not LLM_AVAILABLE:
            logger.warning("LLM analyzer modules not available - sentiment analysis will be skipped")
            return
            
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
    
    def _parse_main_page_html(self, html_content: str) -> List[Dict[str, Any]]:
        """
        Parse the main KAP page HTML to extract disclosure items
        
        Args:
            html_content: Raw HTML content from main page
            
        Returns:
            List of disclosure items with metadata
        """
        if not html_content:
            return []
        
        soup = BeautifulSoup(html_content, 'html.parser')
        disclosure_items = []
        
        try:
            # Look for the main disclosure table
            # The structure appears to be checkboxes with disclosure info
            
            # Method 1: Look for table rows with disclosure data
            rows = soup.find_all('tr')
            for row in rows:
                cells = row.find_all(['td', 'th'])
                if len(cells) >= 3:  # Expect at least checkbox, company/disclosure, and language/attachment
                    
                    # Look for checkbox column (first column)
                    checkbox_cell = cells[0] if cells else None
                    if checkbox_cell and ('checkbox' in str(checkbox_cell) or 'input' in str(checkbox_cell)):
                        
                        # Extract disclosure info from the row
                        main_cell = cells[1] if len(cells) > 1 else None
                        language_cell = cells[2] if len(cells) > 2 else None
                        
                        if main_cell:
                            main_text = main_cell.get_text(strip=True)
                            
                            # Parse the main text to extract components
                            # Expected format: "COMPANY_NAME Disclosure_Type"
                            # Look for links within the cell
                            links = main_cell.find_all('a', href=True)
                            detail_url = None
                            for link in links:
                                href = link.get('href', '')
                                if href.startswith('/') or 'kap.org.tr' in href:
                                    detail_url = href if href.startswith('http') else f"{self.BASE_URL}{href}"
                                    break
                            
                            # Extract company name and disclosure type
                            company_name = ""
                            disclosure_type = ""
                            
                            # Try to split the main text to get company and disclosure
                            if main_text:
                                # Look for pattern: "COMPANY_NAME Some Disclosure Type"
                                # Company names are usually in all caps or title case
                                parts = main_text.split()
                                if parts:
                                    # Find the break between company name and disclosure type
                                    # Company names often end with specific suffixes
                                    company_suffixes = ['A.Ş.', 'A.S.', 'T.A.Ş.', 'T.A.S.', 'PORTFÖY', 'BANK', 'BANKASI']
                                    
                                    company_parts = []
                                    disclosure_parts = []
                                    found_break = False
                                    
                                    for i, part in enumerate(parts):
                                        if not found_break:
                                            company_parts.append(part)
                                            # Check if this part ends the company name
                                            if any(suffix in part for suffix in company_suffixes):
                                                found_break = True
                                                continue
                                            # Also check if next parts look like disclosure types
                                            if i < len(parts) - 1:
                                                next_part = parts[i + 1]
                                                if next_part.lower() in ['material', 'notification', 'financial', 'corporate', 'fund', 'credit']:
                                                    found_break = True
                                                    continue
                                        else:
                                            disclosure_parts.append(part)
                                    
                                    company_name = ' '.join(company_parts).strip()
                                    disclosure_type = ' '.join(disclosure_parts).strip()
                            
                            # Extract language and attachment info
                            language_info = ""
                            has_attachment = False
                            if language_cell:
                                lang_text = language_cell.get_text(strip=True)
                                language_info = lang_text
                                has_attachment = 'attachment' in lang_text.lower()
                            
                            # Extract timestamp from checkbox cell or other cells
                            timestamp_str = ""
                            date_obj = None
                            time_str = ""
                            
                            # Look for timestamp in the row
                            row_text = row.get_text()
                            # Look for patterns like "Today 14:56", "Yesterday 09:30", etc.
                            time_match = re.search(r'(Today|Yesterday|Last \d+ Days|\d{2}\.\d{2}\.\d{4})\s+(\d{2}:\d{2})', row_text)
                            if time_match:
                                date_part = time_match.group(1)
                                time_str = time_match.group(2)
                                timestamp_str = f"{date_part} {time_str}"
                                
                                # Convert to datetime
                                try:
                                    if date_part == "Today":
                                        date_obj = datetime.now().date()
                                    elif date_part == "Yesterday":
                                        date_obj = (datetime.now() - timedelta(days=1)).date()
                                    elif date_part.startswith("Last"):
                                        # For "Last X Days", use today's date (this is approximate)
                                        date_obj = datetime.now().date()
                                    else:
                                        # Try to parse date format like "26.01.2025"
                                        date_obj = datetime.strptime(date_part, "%d.%m.%Y").date()
                                except Exception as e:
                                    logger.debug(f"Error parsing date '{date_part}': {e}")
                                    date_obj = datetime.now().date()
                            
                            # Extract disclosure ID from checkbox or link
                            disclosure_id = None
                            if checkbox_cell:
                                # Look for ID in checkbox value or data attributes
                                checkbox_input = checkbox_cell.find('input')
                                if checkbox_input:
                                    disclosure_id = checkbox_input.get('value')
                                # Also look for ID in the text (like "checkbox 129")
                                if not disclosure_id:
                                    id_match = re.search(r'checkbox\s+(\d+)', str(checkbox_cell))
                                    if id_match:
                                        disclosure_id = id_match.group(1)
                            
                            # Only add if we have essential info
                            if company_name or disclosure_type:
                                disclosure_items.append({
                                    'id': disclosure_id,
                                    'company_name': company_name,
                                    'disclosure_type': disclosure_type,
                                    'timestamp_str': timestamp_str,
                                    'date': date_obj,
                                    'time': time_str,
                                    'language_info': language_info,
                                    'has_attachment': has_attachment,
                                    'detail_url': detail_url,
                                    'raw_text': main_text
                                })
            
            # Method 2: If table parsing didn't work, try to find disclosure items by pattern
            if not disclosure_items:
                # Look for text patterns in the page
                text_content = soup.get_text()
                
                # Pattern: checkbox NUMBER Today/Yesterday TIME COMPANY_NAME Disclosure_Type
                pattern = r'checkbox\s+(\d+)\s+(Today|Yesterday|\d{2}\.\d{2}\.\d{4})\s+(\d{2}:\d{2})\s+(.+?)(?=checkbox|\n|$)'
                matches = re.finditer(pattern, text_content, re.MULTILINE | re.DOTALL)
                
                for match in matches:
                    disclosure_id = match.group(1)
                    date_part = match.group(2)
                    time_str = match.group(3)
                    content = match.group(4).strip()
                    
                    # Parse content to extract company and disclosure type
                    content_parts = content.split()
                    company_name = ""
                    disclosure_type = ""
                    
                    if content_parts:
                        # Similar logic as above to split company and disclosure
                        company_suffixes = ['A.Ş.', 'A.S.', 'T.A.Ş.', 'T.A.S.', 'PORTFÖY', 'BANK', 'BANKASI']
                        company_parts = []
                        disclosure_parts = []
                        found_break = False
                        
                        for i, part in enumerate(content_parts):
                            if not found_break:
                                company_parts.append(part)
                                if any(suffix in part for suffix in company_suffixes):
                                    found_break = True
                                    continue
                                if i < len(content_parts) - 1:
                                    next_part = content_parts[i + 1]
                                    if next_part.lower() in ['material', 'notification', 'financial', 'corporate', 'fund']:
                                        found_break = True
                                        continue
                            else:
                                disclosure_parts.append(part)
                        
                        company_name = ' '.join(company_parts).strip()
                        disclosure_type = ' '.join(disclosure_parts).strip()
                    
                    # Convert date
                    date_obj = None
                    try:
                        if date_part == "Today":
                            date_obj = datetime.now().date()
                        elif date_part == "Yesterday":
                            date_obj = (datetime.now() - timedelta(days=1)).date()
                        else:
                            date_obj = datetime.strptime(date_part, "%d.%m.%Y").date()
                    except Exception as e:
                        logger.debug(f"Error parsing date '{date_part}': {e}")
                        date_obj = datetime.now().date()
                    
                    disclosure_items.append({
                        'id': disclosure_id,
                        'company_name': company_name,
                        'disclosure_type': disclosure_type,
                        'timestamp_str': f"{date_part} {time_str}",
                        'date': date_obj,
                        'time': time_str,
                        'language_info': "",
                        'has_attachment': False,
                        'detail_url': None,
                        'raw_text': content
                    })
            
        except Exception as e:
            logger.error(f"Error parsing main page HTML: {e}", exc_info=True)
        
        logger.info(f"Parsed {len(disclosure_items)} disclosure items from main page")
        return disclosure_items
    
    async def _scrape_disclosure_detail(self, disclosure_item: Dict[str, Any]) -> Optional[str]:
        """
        Scrape the detail page for a specific disclosure
        
        Args:
            disclosure_item: Disclosure metadata from main page
            
        Returns:
            Full disclosure content text or None
        """
        if not disclosure_item.get('detail_url'):
            logger.debug(f"No detail URL for disclosure {disclosure_item.get('id')}")
            return None
        
        detail_url = disclosure_item['detail_url']
        
        try:
            logger.debug(f"Scraping detail page: {detail_url}")
            
            # Scrape the detail page
            result = await self.scrape_url(
                detail_url,
                wait_for=5000,
                formats=["markdown", "html"]
            )
            
            if not result.get("success"):
                logger.warning(f"Failed to scrape detail page: {detail_url}")
                return None
            
            doc = result.get("data")
            if not doc:
                logger.warning(f"No document data from detail page: {detail_url}")
                return None
            
            # Try to get HTML content first, then markdown
            content = ""
            if hasattr(doc, 'html') and doc.html:
                content = self._extract_content_from_detail_html(doc.html)
            elif hasattr(doc, 'raw_html') and doc.raw_html:
                content = self._extract_content_from_detail_html(doc.raw_html)
            elif hasattr(doc, 'markdown') and doc.markdown:
                content = self._extract_content_from_detail_markdown(doc.markdown)
            
            return content
            
        except Exception as e:
            logger.error(f"Error scraping detail page {detail_url}: {e}", exc_info=True)
            return None
    
    def _extract_content_from_detail_html(self, html_content: str) -> str:
        """
        Extract disclosure content from detail page HTML
        
        Args:
            html_content: Raw HTML from detail page
            
        Returns:
            Clean disclosure content text
        """
        if not html_content:
            return ""
        
        soup = BeautifulSoup(html_content, 'html.parser')
        extracted_parts = []
        
        try:
            # Remove navigation, ads, and other non-content elements
            for elem in soup.find_all(['nav', 'header', 'footer']):
                elem.decompose()
            
            # Remove elements with common navigation/ad classes
            for elem in soup.find_all(class_=re.compile(r'nav|menu|header|footer|ad|sidebar', re.I)):
                elem.decompose()
            
            # Look for main content area
            main_content = soup.find('main') or soup.find('article') or soup.find(class_=re.compile(r'content|main|disclosure', re.I))
            
            if not main_content:
                # Use the body if no specific content area found
                main_content = soup.find('body') or soup
            
            # Extract heading (company name and disclosure type)
            headings = main_content.find_all(['h1', 'h2', 'h3'])
            for heading in headings:
                heading_text = heading.get_text(strip=True)
                if heading_text and len(heading_text) > 5:
                    extracted_parts.append(f"# {heading_text}")
                    break  # Only take the first significant heading
            
            # Extract date/time information
            date_pattern = r'(\d{1,2}[./]\d{1,2}[./]\d{2,4}|\d{1,2}\s+\w+\s+\d{4})'
            time_pattern = r'\d{2}:\d{2}'
            
            # Look for date/time in the page
            text_content = main_content.get_text()
            date_match = re.search(f'{date_pattern}.*?{time_pattern}', text_content)
            if date_match:
                extracted_parts.append(f"**Date:** {date_match.group(0)}")
            
            # Extract all tables (KAP disclosures often contain tabular data)
            tables = main_content.find_all('table')
            for table in tables:
                table_md = self._table_to_markdown(table)
                if table_md and len(table_md) > 50:
                    extracted_parts.append(table_md)
            
            # Extract paragraphs and text content
            for elem in main_content.find_all(['p', 'div', 'section']):
                text = elem.get_text(strip=True)
                
                # Skip empty or very short text
                if not text or len(text) < 20:
                    continue
                
                # Skip navigation-like text
                if any(nav_word in text.lower() for nav_word in [
                    'click here', 'go to', 'navigate', 'menu', 'home page',
                    'copyright', 'all rights', 'terms of use', 'privacy policy'
                ]):
                    continue
                
                # Skip if it's just a link
                if len(text) < 100 and ('http' in text or 'www' in text):
                    continue
                
                extracted_parts.append(text)
            
            # If we have very little content, try to get more from the body
            content_text = '\n\n'.join(extracted_parts)
            if len(content_text) < 200:
                # Try to get all text from the page
                all_text = soup.get_text(separator='\n', strip=True)
                lines = all_text.split('\n')
                
                # Filter out navigation and short lines
                content_lines = []
                for line in lines:
                    if (len(line) > 30 and 
                        not any(nav in line.lower() for nav in ['menu', 'navigation', 'copyright', 'home', 'contact'])):
                        content_lines.append(line)
                
                if content_lines:
                    extracted_parts.extend(content_lines[:20])  # Limit to first 20 substantial lines
            
        except Exception as e:
            logger.error(f"Error extracting content from HTML: {e}", exc_info=True)
            return html_content[:2000]  # Return truncated raw content as fallback
        
        content = '\n\n'.join(extracted_parts).strip()
        return content[:5000]  # Limit content size for processing
    
    def _extract_content_from_detail_markdown(self, markdown_content: str) -> str:
        """
        Extract disclosure content from detail page markdown
        
        Args:
            markdown_content: Markdown content from detail page
            
        Returns:
            Clean disclosure content text
        """
        if not markdown_content:
            return ""
        
        lines = markdown_content.split('\n')
        extracted_lines = []
        skip_patterns = [
            'home', 'menu', 'navigation', 'contact', 'copyright',
            'facebook', 'twitter', 'linkedin', 'instagram'
        ]
        
        for line in lines:
            line_clean = line.strip()
            
            # Skip empty lines at the beginning
            if not line_clean and not extracted_lines:
                continue
            
            # Skip navigation and social media links
            if any(pattern in line_clean.lower() for pattern in skip_patterns):
                continue
            
            # Skip pure markdown links that look like navigation
            if (line_clean.startswith('- [') and '](' in line_clean and 
                len(line_clean) < 100 and 
                any(nav in line_clean.lower() for nav in ['home', 'page', 'site', 'menu'])):
                continue
            
            # Include table content and substantial text
            if line_clean:
                extracted_lines.append(line_clean)
        
        content = '\n'.join(extracted_lines).strip()
        
        # Remove excessive whitespace
        content = re.sub(r'\n{3,}', '\n\n', content)
        
        return content[:5000]  # Limit content size
    
    def _table_to_markdown(self, table) -> str:
        """Convert HTML table to markdown format"""
        try:
            rows = []
            for tr in table.find_all('tr'):
                cells = []
                for td in tr.find_all(['td', 'th']):
                    # Get text and clean it
                    cell_text = td.get_text(separator=' ', strip=True)
                    # Replace newlines with spaces
                    cell_text = ' '.join(cell_text.split())
                    # Limit cell length to prevent huge cells
                    if len(cell_text) > 200:
                        cell_text = cell_text[:200] + '...'
                    cells.append(cell_text)
                
                if cells:
                    rows.append('| ' + ' | '.join(cells) + ' |')
            
            if rows:
                # Add separator after header row (if we have headers)
                if len(rows) > 1:
                    # Count columns from first row
                    num_cols = len(rows[0].split('|')) - 2  # Subtract 2 for leading/trailing empty
                    if num_cols > 0:
                        separator = '|' + '---|' * num_cols
                        rows.insert(1, separator)
                return '\n'.join(rows)
        except Exception as e:
            logger.debug(f"Error converting table to markdown: {e}")
        return ""
    
    async def _analyze_sentiment(self, content: str, disclosure_id: Optional[str] = None) -> Optional[Dict[str, Any]]:
        """
        Analyze sentiment of disclosure content using LLM
        
        Args:
            content: Disclosure content text
            disclosure_id: Optional disclosure ID for database reference
            
        Returns:
            Sentiment analysis result dict or None
        """
        if not LLM_AVAILABLE:
            logger.debug("LLM analyzer modules not available, skipping sentiment analysis")
            return None
            
        if not self.llm_analyzer:
            logger.debug("LLM analyzer not configured, skipping sentiment analysis")
            return None
        
        if not content or len(content.strip()) < 50:
            logger.debug(f"Insufficient content for sentiment analysis ({len(content) if content else 0} chars)")
            return None
        
        try:
            logger.info(f"Analyzing sentiment for disclosure {disclosure_id}: {len(content)} chars")
            
            # Use LLM analyzer's sentiment analysis method
            sentiment_result = self.llm_analyzer.analyze_sentiment(content, report_id=disclosure_id)
            
            if sentiment_result:
                # Handle both enum and string types
                overall_sentiment = sentiment_result.overall_sentiment
                if hasattr(overall_sentiment, 'value'):
                    overall_sentiment = overall_sentiment.value
                
                confidence_val = sentiment_result.confidence
                if hasattr(confidence_val, 'value'):
                    confidence_val = confidence_val.value
                
                impact_horizon_val = sentiment_result.impact_horizon
                if impact_horizon_val and hasattr(impact_horizon_val, 'value'):
                    impact_horizon_val = impact_horizon_val.value
                
                target_audience_val = sentiment_result.target_audience
                if target_audience_val and hasattr(target_audience_val, 'value'):
                    target_audience_val = target_audience_val.value
                
                logger.info(f"✅ Sentiment analysis successful: {overall_sentiment} (confidence: {confidence_val})")
                print(f"   ✅ Sentiment: {overall_sentiment}, Confidence: {confidence_val:.2f}")
                
                # Convert to dict for database storage
                return {
                    "overall_sentiment": str(overall_sentiment),
                    "confidence": float(confidence_val),
                    "impact_horizon": str(impact_horizon_val) if impact_horizon_val else None,
                    "key_drivers": [str(d) for d in sentiment_result.key_drivers] if sentiment_result.key_drivers else [],
                    "risk_flags": [str(r) for r in sentiment_result.risk_flags] if sentiment_result.risk_flags else [],
                    "tone_descriptors": [str(t) for t in sentiment_result.tone_descriptors] if sentiment_result.tone_descriptors else [],
                    "target_audience": str(target_audience_val) if target_audience_val else None,
                    "analysis_text": sentiment_result.analysis_text,
                    "risk_level": sentiment_result.get_risk_level() if hasattr(sentiment_result, 'get_risk_level') else None
                }
            else:
                logger.warning("LLM analyzer returned None for sentiment analysis")
                print(f"   ⚠️  Sentiment analysis returned None")
        except Exception as e:
            logger.error(f"Error analyzing sentiment: {e}", exc_info=True)
            print(f"   ❌ Error: {str(e)[:100]}")
        
        return None
    
    async def scrape(
        self,
        days_back: int = 1,
        company_symbols: Optional[List[str]] = None,
        disclosure_types: Optional[List[str]] = None,
        analyze_sentiment: bool = False,
        max_items: int = 100
    ) -> Dict[str, Any]:
        """
        Scrape disclosure data from KAP.org.tr
        
        Args:
            days_back: Number of days to look back
            company_symbols: Specific company symbols/codes to filter
            disclosure_types: Specific disclosure types to filter
            analyze_sentiment: Whether to perform sentiment analysis
            max_items: Maximum number of items to process
            
        Returns:
            Scraped disclosures data
        """
        logger.info(f"Scraping KAP.org.tr for last {days_back} days")
        print(f"🔗 KAP URL: {self.MAIN_PAGE_URL}")
        print(f"📅 Looking back {days_back} days")
        
        # Calculate date range
        end_date = datetime.now()
        start_date = end_date - timedelta(days=days_back)
        
        all_disclosures = []
        
        try:
            # Scrape the main KAP page
            logger.info(f"Scraping main KAP page: {self.MAIN_PAGE_URL}")
            result = await self.scrape_url(
                self.MAIN_PAGE_URL,
                wait_for=5000,
                formats=["html", "markdown"]
            )
            
            if not result.get("success"):
                logger.error("Failed to scrape KAP main page")
                return {
                    "success": False,
                    "error": "Failed to access KAP main page",
                    "total_companies": 0,
                    "processed_companies": 0,
                    "disclosures": []
                }
            
            # Get HTML content
            doc = result.get("data")
            html_content = None
            if doc:
                if hasattr(doc, 'html') and doc.html:
                    html_content = doc.html
                elif hasattr(doc, 'raw_html') and doc.raw_html:
                    html_content = doc.raw_html
                elif hasattr(doc, 'markdown') and doc.markdown:
                    html_content = doc.markdown
            
            if not html_content:
                logger.error("No HTML content received from KAP main page")
                return {
                    "success": False,
                    "error": "No HTML content received",
                    "total_companies": 0,
                    "processed_companies": 0,
                    "disclosures": []
                }
            
            # Parse HTML to extract disclosure items
            disclosure_items = self._parse_main_page_html(html_content)
            
            if not disclosure_items:
                logger.warning("No disclosure items found on main page")
                print("⚠️  No disclosure items found on main page")
                return {
                    "success": True,
                    "total_companies": 0,
                    "processed_companies": 0,
                    "disclosures": [],
                    "message": "No disclosure items found"
                }
            
            logger.info(f"Found {len(disclosure_items)} disclosure items")
            print(f"📊 Found {len(disclosure_items)} disclosure items")
            
            # Filter items by date range
            filtered_items = []
            for item in disclosure_items:
                item_date = item.get('date')
                if item_date:
                    days_diff = (end_date.date() - item_date).days
                    if days_diff <= days_back and days_diff >= 0:
                        filtered_items.append(item)
            
            logger.info(f"Filtered to {len(filtered_items)} items within date range")
            print(f"📅 Filtered to {len(filtered_items)} items within {days_back} days")
            
            # Apply additional filters
            if company_symbols:
                filtered_items = [
                    item for item in filtered_items 
                    if any(symbol.upper() in item.get('company_name', '').upper() for symbol in company_symbols)
                ]
                print(f"🏢 Filtered to {len(filtered_items)} items matching company symbols")
            
            if disclosure_types:
                filtered_items = [
                    item for item in filtered_items 
                    if any(dtype.lower() in item.get('disclosure_type', '').lower() for dtype in disclosure_types)
                ]
                print(f"📋 Filtered to {len(filtered_items)} items matching disclosure types")
            
            # Limit number of items to process
            if len(filtered_items) > max_items:
                filtered_items = filtered_items[:max_items]
                print(f"⚡ Limited to first {max_items} items for processing")
            
            # Process each disclosure item
            processed_count = 0
            for i, item in enumerate(filtered_items):
                try:
                    logger.info(f"Processing disclosure {i+1}/{len(filtered_items)}: {item.get('company_name')} - {item.get('disclosure_type')}")
                    print(f"⚙️  Processing {i+1}/{len(filtered_items)}: {item.get('company_name', 'N/A')[:30]}...")
                    
                    # Scrape detail page content
                    detail_content = await self._scrape_disclosure_detail(item)
                    
                    # Prepare disclosure data
                    disclosure_data = {
                        "disclosure_id": item.get('id'),
                        "company_name": item.get('company_name', ''),
                        "disclosure_type": item.get('disclosure_type', ''),
                        "disclosure_date": item.get('date').isoformat() if item.get('date') else None,
                        "timestamp": item.get('timestamp_str', ''),
                        "language_info": item.get('language_info', ''),
                        "has_attachment": item.get('has_attachment', False),
                        "detail_url": item.get('detail_url', ''),
                        "content": detail_content or item.get('raw_text', ''),
                        "data": {
                            "source": "kap_org",
                            "time": item.get('time', ''),
                            "raw_text": item.get('raw_text', ''),
                            "detail_scraped": bool(detail_content)
                        },
                        "scraped_at": datetime.now().isoformat()
                    }
                    
                    # Save to database
                    disclosure_db_id = None
                    if self.db_manager:
                        try:
                            self.save_to_db(disclosure_data, "kap_disclosures")
                            all_disclosures.append(disclosure_data)
                            
                            # Get the inserted disclosure ID for sentiment analysis
                            try:
                                # Import database modules here to avoid dependency issues
                                import psycopg2
                                from config import config
                                conn = psycopg2.connect(**config.database.get_connection_params())
                                cursor = conn.cursor()
                                cursor.execute(f"""
                                    SELECT id FROM {config.database.schema}.kap_disclosures
                                    WHERE disclosure_id = %s AND company_name = %s AND disclosure_type = %s
                                    ORDER BY scraped_at DESC LIMIT 1
                                """, (item.get('id'), item.get('company_name'), item.get('disclosure_type')))
                                result = cursor.fetchone()
                                if result:
                                    disclosure_db_id = result[0]
                                cursor.close()
                                conn.close()
                            except Exception as e:
                                logger.debug(f"Error getting disclosure DB ID: {e}")
                        except Exception as e:
                            logger.error(f"Error saving disclosure {item.get('id')}: {e}")
                    
                    # Perform sentiment analysis if requested
                    if analyze_sentiment and detail_content and len(detail_content.strip()) > 100 and self.llm_analyzer:
                        try:
                            content_for_analysis = detail_content[:3000] if len(detail_content) > 3000 else detail_content
                            
                            sentiment_data = await self._analyze_sentiment(
                                content_for_analysis, 
                                disclosure_id=item.get('id')
                            )
                            
                            if sentiment_data and self.db_manager and disclosure_db_id:
                                # Save sentiment analysis to database
                                try:
                                    sentiment_record = {
                                        "disclosure_id": disclosure_db_id,
                                        "overall_sentiment": sentiment_data["overall_sentiment"],
                                        "confidence": sentiment_data["confidence"],
                                        "impact_horizon": sentiment_data.get("impact_horizon"),
                                        "key_drivers": sentiment_data.get("key_drivers", []),
                                        "risk_flags": sentiment_data.get("risk_flags", []),
                                        "tone_descriptors": sentiment_data.get("tone_descriptors", []),
                                        "target_audience": sentiment_data.get("target_audience"),
                                        "analysis_text": sentiment_data.get("analysis_text", ""),
                                        "risk_level": sentiment_data.get("risk_level"),
                                        "analyzed_at": datetime.now().isoformat()
                                    }
                                    self.save_to_db(sentiment_record, "kap_disclosure_sentiment")
                                    logger.info(f"Saved sentiment analysis for disclosure {disclosure_db_id}")
                                except Exception as e:
                                    logger.error(f"Error saving sentiment analysis: {e}")
                        except Exception as e:
                            logger.error(f"Error during sentiment analysis: {e}")
                    
                    processed_count += 1
                    
                    # Add small delay to avoid overwhelming the server
                    await asyncio.sleep(1)
                    
                except Exception as e:
                    logger.error(f"Error processing disclosure item {item}: {e}", exc_info=True)
                    continue
            
        except Exception as e:
            logger.error(f"Error scraping KAP.org.tr: {e}", exc_info=True)
            return {
                "success": False,
                "error": f"Error: {str(e)}",
                "total_companies": 0,
                "processed_companies": 0,
                "disclosures": []
            }
        
        # Get unique companies processed
        processed_companies = len(set(d.get("company_name") for d in all_disclosures if d.get("company_name")))
        
        logger.info(f"Successfully processed {processed_count} disclosures from KAP.org.tr")
        print(f"✅ Successfully processed {processed_count} disclosures")
        
        # Count sentiment analyses performed
        sentiment_count = 0
        if analyze_sentiment and self.db_manager:
            try:
                # Import database modules here to avoid dependency issues  
                import psycopg2
                from config import config
                conn = psycopg2.connect(**config.database.get_connection_params())
                cursor = conn.cursor()
                cursor.execute(f"""
                    SELECT COUNT(*) FROM {config.database.schema}.kap_disclosure_sentiment
                    WHERE analyzed_at >= %s
                """, (start_date.isoformat(),))
                sentiment_count = cursor.fetchone()[0]
                cursor.close()
                conn.close()
            except Exception as e:
                logger.debug(f"Error counting sentiment analyses: {e}")
        
        if analyze_sentiment:
            print(f"📊 Performed {sentiment_count} sentiment analyses")
        
        return {
            "success": True,
            "total_companies": processed_companies,
            "processed_companies": processed_companies,
            "disclosures": all_disclosures,
            "total_disclosures": len(all_disclosures),
            "sentiment_analyses": sentiment_count if analyze_sentiment else 0,
            "date_range": {
                "start": start_date.isoformat(),
                "end": end_date.isoformat()
            },
            "source": "kap_org"
        }