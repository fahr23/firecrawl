"""
Bloomberg HT KAP News Scraper

Scrapes KAP (Kamuyu Aydınlatma Platformu) news from Bloomberg HT website.
This is an alternative source when the KAP API is not accessible.

Source: https://www.bloomberght.com/borsa/hisseler/kap-haberleri

Strategy:
1. Scrape main page to get list of KAP news items with links
2. Follow each link to detail page (e.g., /borsa/hisse/anadolu-hayat/kap-haberi/345485)
3. Extract actual KAP report content from detail pages
4. Perform LLM sentiment analysis on extracted content
5. Save both report data and sentiment analysis to database
"""
import logging
import re
from typing import Dict, Any, List, Optional
from datetime import datetime, timedelta
from bs4 import BeautifulSoup
from scrapers.base_scraper import BaseScraper
from utils.llm_analyzer import LLMAnalyzer, LocalLLMProvider, OpenAIProvider, GeminiProvider
from application.dependencies import get_sentiment_analyzer_service
from domain.value_objects.sentiment import SentimentAnalysis

logger = logging.getLogger(__name__)


class BloombergHTKAPScraper(BaseScraper):
    """Scraper for KAP news from Bloomberg HT website"""
    
    BASE_URL = "https://www.bloomberght.com"
    KAP_NEWS_URL = f"{BASE_URL}/borsa/hisseler/kap-haberleri"
    
    def __init__(self, *args, **kwargs):
        """Initialize Bloomberg HT KAP scraper"""
        super().__init__(*args, **kwargs)
        self.llm_analyzer = None  # Lazy initialization
        logger.info("Initialized BloombergHTKAPScraper")
    
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
    
    def _extract_kap_content_from_html(self, html_content: str) -> str:
        """
        Extract KAP content directly from HTML (more reliable than markdown)
        
        Strategy:
        1. Find the main heading with company code (h1 containing '/')
        2. Extract all content from that heading until footer/navigation
        3. Convert tables to markdown format
        4. Clean up navigation links
        """
        if not html_content:
            return ""
        
        soup = BeautifulSoup(html_content, 'html.parser')
        extracted_parts = []
        
        # Find the main KAP heading (h1 with company code like "ANHYT/ANADOLU...")
        main_heading = None
        for h1 in soup.find_all('h1'):
            text = h1.get_text(strip=True)
            if '/' in text and len(text.split('/')) == 2:
                main_heading = h1
                break
        
        if not main_heading:
            # Try h2 as fallback
            for h2 in soup.find_all('h2'):
                text = h2.get_text(strip=True)
                if '/' in text:
                    main_heading = h2
                    break
        
        if main_heading:
            # Start from the main heading
            extracted_parts.append(f"# {main_heading.get_text(strip=True)}")
            
            # Get the next sibling (usually h2 with title)
            next_sibling = main_heading.find_next_sibling(['h2', 'h3'])
            if next_sibling:
                extracted_parts.append(f"## {next_sibling.get_text(strip=True)}")
            
            # Get date/time if present (look in parent or next elements)
            parent = main_heading.parent
            date_text = None
            for elem in [parent, main_heading.find_next(['p', 'div', 'span'])]:
                if elem:
                    text = elem.get_text()
                    date_match = re.search(r'\d{1,2}\s+\w+\s+\d{4}.*?\d{2}:\d{2}', text)
                    if date_match:
                        date_text = date_match.group(0).strip()
                        break
            
            if date_text:
                extracted_parts.append(date_text)
            
            # Find the main content container (main, article, or a large div)
            container = soup.find('main') or soup.find('article')
            if not container:
                # Try to find a content div
                container = main_heading.find_parent(['div', 'section'])
                # Go up to find a larger container
                while container and container.parent:
                    parent = container.parent
                    if parent.name in ['main', 'article', 'body']:
                        container = parent
                        break
                    container = parent
            
            # Extract all tables in the page (KAP reports have tables)
            # Find tables that are after the main heading
            all_tables = soup.find_all('table')
            tables_added = 0
            for table in all_tables:
                # Check if table is after our heading (or if no heading, include all)
                if main_heading:
                    prev_h1 = table.find_previous('h1')
                    if prev_h1 != main_heading:
                        continue
                
                table_md = self._table_to_markdown(table)
                if table_md and len(table_md) > 50:  # Only substantial tables
                    extracted_parts.append(table_md)
                    tables_added += 1
                    if tables_added >= 10:  # Limit to prevent too many tables
                        break
            
            # Extract text content after the heading
            if container:
                # Find all elements after the heading
                for elem in container.find_all(['p', 'div', 'section']):
                    # Skip if it's before our heading
                    if main_heading and elem.find_previous('h1') != main_heading:
                        continue
                    
                    # Stop at footer/navigation markers
                    text_lower = elem.get_text().lower()
                    if any(stop in text_lower for stop in [
                        'ilgili haberler', 'öne çıkan', 'çerez politikası',
                        'aydınlatma metni', 'reklam', 'birkaç kelime', 'kabul et'
                    ]):
                        break
                    
                    # Skip navigation elements
                    if elem.name == 'nav' or (elem.get('class') and any(
                        'nav' in str(c).lower() or 'menu' in str(c).lower() 
                        for c in elem.get('class', [])
                    )):
                        continue
                    
                    # Extract text content
                    text = elem.get_text(strip=True)
                    if text and len(text) > 20:  # Only substantial text
                        # Skip navigation links
                        if not any(nav in text.lower() for nav in [
                            'piyasalar', 'borsa', 'döviz', 'altın', 'haberler',
                            'facebook', 'twitter', 'linkedin', 'whatsapp'
                        ]):
                            extracted_parts.append(text)
        
        # If we didn't find structured content, try to find tables directly
        if len(extracted_parts) < 3:
            tables = soup.find_all('table')
            for table in tables[:5]:  # Limit to first 5 tables
                table_md = self._table_to_markdown(table)
                if table_md:
                    extracted_parts.append(table_md)
        
        content = '\n\n'.join(extracted_parts).strip()
        return content[:5000]  # Limit size
    
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
    
    def _extract_kap_content_from_detail_page(self, markdown_content: str) -> str:
        """
        Extract actual KAP report content from Bloomberg HT detail page markdown
        
        The page contains navigation, ads, etc. We need to extract just the KAP content.
        Strategy: Find the main heading (company code/name), then extract tables and text until navigation resumes.
        """
        if not markdown_content:
            return ""
        
        lines = markdown_content.split('\n')
        extracted_lines = []
        in_kap_section = False
        found_main_title = False
        
        # Look for the main KAP content section
        # Pattern: "# COMPANY_CODE/COMPANY_NAME" followed by "## TITLE" and then content
        for i, line in enumerate(lines):
            line_lower = line.lower()
            
            # Look for the main KAP content section (starts with company code heading)
            # Pattern: "# COMPANY_CODE/COMPANY_NAME"
            if line.startswith('# ') and '/' in line:
                parts = line.split()
                if parts and '/' in parts[0]:  # First word contains /
                    # This is the main title: "# ANHYT/ANADOLU HAYAT..."
                    found_main_title = True
                    in_kap_section = True
                    extracted_lines.append(line)  # Include the title
                    continue
            
            # Skip everything before the main title (navigation, etc.)
            if not found_main_title:
                continue
            
            # Detect the report title (usually ## TITLE)
            if found_main_title and line.startswith('## '):
                extracted_lines.append(line)
                continue
            
            # Detect date line (usually "DD Ocak YYYY Pazar, HH:MM")
            if found_main_title and re.match(r'\d{1,2}\s+\w+\s+\d{4}', line):
                extracted_lines.append(line)
                continue
            
            # Once we're in KAP section, extract content
            if in_kap_section:
                # Stop if we hit navigation or footer
                if any(stop in line_lower for stop in [
                    'ilgili haberler', 'öne çıkan', 'çerez politikası', 
                    'aydınlatma metni', 'reklam', 'birkaç kelime'
                ]):
                    break
                
                # Skip social media sharing links
                if any(skip in line_lower for skip in ['facebook', 'twitter', 'linkedin', 'whatsapp', 'bluesky', 'mail']):
                    continue
                
                # Skip pure navigation links (markdown links to other pages)
                if line.startswith('- [') and '](' in line and any(nav in line_lower for nav in [
                    'piyasalar', 'borsa', 'döviz', 'altın', 'haberler', 'yatırım fonları'
                ]):
                    continue
                
                # Include table rows (KAP reports have lots of tables)
                if '|' in line:
                    extracted_lines.append(line)
                    continue
                
                # Include text content (but skip empty lines at start)
                if line.strip():
                    # Skip if it's just a markdown link without context
                    if line.strip().startswith('[') and '](' in line and len(line.strip()) < 100:
                        continue
                    extracted_lines.append(line)
        
        # If we didn't find structured content, try to extract tables directly
        if len(extracted_lines) < 5:
            # Look for table content (KAP reports often have tables)
            in_table = False
            table_lines = []
            for line in lines:
                # Detect table start (look for table header with multiple columns)
                if '|' in line and '---' not in line and line.count('|') >= 3:
                    in_table = True
                    table_lines.append(line)
                elif in_table:
                    if '|' in line:
                        table_lines.append(line)
                    elif line.strip() and not any(skip in line.lower() for skip in ['piyasalar', 'borsa', 'döviz', 'altın', 'haberler']):
                        # Continue table if next line has content
                        if len(line.strip()) > 10 and not line.strip().startswith('['):
                            table_lines.append(line)
                        else:
                            in_table = False
                    else:
                        in_table = False
            
            if table_lines:
                extracted_lines.extend(table_lines)
        
        # Join and clean up
        content = '\n'.join(extracted_lines).strip()
        
        # Remove excessive whitespace
        content = re.sub(r'\n{3,}', '\n\n', content)
        
        # Remove markdown links that are just navigation (but keep table content)
        # Only remove links that are clearly navigation
        lines_cleaned = []
        for line in content.split('\n'):
            # Skip pure navigation links
            if line.strip().startswith('- [') and any(nav in line.lower() for nav in [
                'piyasalar', 'borsa', 'döviz', 'altın', 'haberler', 'yatırım fonları', 'endeksler'
            ]):
                continue
            # Skip social media links
            if any(social in line.lower() for social in ['facebook', 'twitter', 'linkedin', 'whatsapp']):
                continue
            lines_cleaned.append(line)
        
        content = '\n'.join(lines_cleaned).strip()
        
        # Final cleanup: remove standalone markdown links (but keep table content with |)
        if '|' not in content[:100]:  # If no tables, be more aggressive
            content = re.sub(r'\[([^\]]+)\]\(https?://[^\)]+\)', r'\1', content)  # Convert links to text
        
        return content[:5000]  # Limit content size
    
    async def _analyze_sentiment(self, content: str, report_id: Optional[int] = None) -> Optional[Dict[str, Any]]:
        """
        Analyze sentiment of KAP report content using LLM
        
        Args:
            content: KAP report content text
            report_id: Optional report ID for database reference
            
        Returns:
            Sentiment analysis result dict or None
        """
        if not self.llm_analyzer:
            logger.debug("LLM analyzer not configured, skipping sentiment analysis")
            return None
        
        if not content or len(content.strip()) < 50:
            logger.debug(f"Insufficient content for sentiment analysis ({len(content) if content else 0} chars)")
            return None
        
        try:
            logger.info(f"Calling LLM analyzer with {len(content)} chars of content")
            logger.debug(f"Content preview: {content[:200]}...")
            
            # Use LLM analyzer's sentiment analysis method
            sentiment_result = self.llm_analyzer.analyze_sentiment(content, report_id=report_id)
            
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
                logger.warning("LLM analyzer returned None for sentiment analysis - check LLM response")
                print(f"   ⚠️  Sentiment analysis returned None")
        except Exception as e:
            logger.error(f"Error analyzing sentiment: {e}", exc_info=True)
            print(f"   ❌ Error: {str(e)[:100]}")
        
        return None
    
    async def scrape(
        self,
        days_back: int = 7,
        company_symbols: Optional[List[str]] = None,
        analyze_sentiment: bool = False
    ) -> Dict[str, Any]:
        """
        Scrape KAP reports from Bloomberg HT KAP news page
        
        Args:
            days_back: Number of days to look back
            company_symbols: Specific company symbols to scrape (filters results)
            
        Returns:
            Scraped reports data
        """
        logger.info(f"Scraping KAP reports from Bloomberg HT for last {days_back} days")
        print(f"🔗 Bloomberg HT URL: {self.KAP_NEWS_URL}")
        print(f"📅 Looking back {days_back} days")
        
        # Calculate date range
        end_date = datetime.now()
        start_date = end_date - timedelta(days=days_back)
        
        all_reports = []
        
        try:
            # Scrape the main Bloomberg HT KAP news page
            logger.info(f"Scraping Bloomberg HT KAP page: {self.KAP_NEWS_URL}")
            result = await self.scrape_url(
                self.KAP_NEWS_URL,
                wait_for=5000,
                formats=["markdown", "html"]
            )
            
            if not result.get("success"):
                logger.error("Failed to scrape Bloomberg HT page")
                return {
                    "success": False,
                    "error": "Failed to access Bloomberg HT page",
                    "total_companies": 0,
                    "processed_companies": 0,
                    "reports": []
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
                    # Use markdown as fallback
                    html_content = doc.markdown
            
            if not html_content:
                logger.error("No HTML content received from Bloomberg HT")
                return {
                    "success": False,
                    "error": "No HTML content received",
                    "total_companies": 0,
                    "processed_companies": 0,
                    "reports": []
                }
            
            # Parse HTML to extract KAP news items
            soup = BeautifulSoup(html_content, 'html.parser')
            
            # Find all KAP news items and their detail page links
            # Pattern from page: "COMPANY_CODE/COMPANY_NAME - TITLE DD.MM.YYYY HH:MM"
            # Links point to: /borsa/hisse/{company-slug}/kap-haberi/{id}
            news_items = []
            
            # Method 1: Look for links to detail pages (kap-haberi URLs)
            links = soup.find_all('a', href=True)
            for link in links:
                link_text = link.get_text(strip=True)
                href = link.get('href', '')
                
                # Look for KAP detail page links: /borsa/hisse/.../kap-haberi/...
                if '/kap-haberi/' in href:
                    # Extract company code and info from link text
                    # Pattern: "COMPANY_CODE/COMPANY_NAME - TITLE DD.MM.YYYY HH:MM"
                    if '/' in link_text and ' - ' in link_text:
                        parts = link_text.split('/')
                        if len(parts) >= 2:
                            company_code_part = parts[0].strip()
                            rest = '/'.join(parts[1:])
                            
                            # Extract company name and title (after -)
                            if ' - ' in rest:
                                company_name = rest.split(' - ')[0].strip()
                                title_part = ' - '.join(rest.split(' - ')[1:])
                                
                                # Extract date and time from title
                                # Pattern: "TITLE DD.MM.YYYY HH:MM"
                                date_match = re.search(r'(\d{2}\.\d{2}\.\d{4})\s+(\d{2}:\d{2})', title_part)
                                if date_match:
                                    date_str = date_match.group(1)
                                    time_str = date_match.group(2)
                                    title = title_part[:date_match.start()].strip()
                                    
                                    # Parse date
                                    try:
                                        report_date = datetime.strptime(date_str, "%d.%m.%Y").date()
                                        
                                        # Check if date is within range
                                        days_diff = (end_date.date() - report_date).days
                                        if days_diff <= days_back and days_diff >= 0:
                                            # Filter by company symbols if provided
                                            if company_symbols and company_code_part not in company_symbols:
                                                continue
                                            
                                            # Construct full URL
                                            full_url = href
                                            if href.startswith('/'):
                                                full_url = f"{self.BASE_URL}{href}"
                                            elif not href.startswith('http'):
                                                full_url = f"{self.BASE_URL}/{href.lstrip('/')}"
                                            
                                            news_items.append({
                                                "company_code": company_code_part,
                                                "company_name": company_name,
                                                "title": title,
                                                "date": date_str,
                                                "time": time_str,
                                                "report_date": report_date,
                                                "url": full_url
                                            })
                                    except Exception as e:
                                        logger.debug(f"Error parsing date {date_str}: {e}")
                
                # Also check for pattern in link text (fallback)
                elif '/' in link_text and ' - ' in link_text and not any(item['url'] == href for item in news_items):
                    # Same extraction logic as above but for any link with the pattern
                    parts = link_text.split('/')
                    if len(parts) >= 2:
                        company_code_part = parts[0].strip()
                        rest = '/'.join(parts[1:])
                        
                        if ' - ' in rest:
                            company_name = rest.split(' - ')[0].strip()
                            title_part = ' - '.join(rest.split(' - ')[1:])
                            
                            date_match = re.search(r'(\d{2}\.\d{2}\.\d{4})\s+(\d{2}:\d{2})', title_part)
                            if date_match:
                                date_str = date_match.group(1)
                                time_str = date_match.group(2)
                                title = title_part[:date_match.start()].strip()
                                
                                try:
                                    report_date = datetime.strptime(date_str, "%d.%m.%Y").date()
                                    days_diff = (end_date.date() - report_date).days
                                    
                                    if days_diff <= days_back and days_diff >= 0:
                                        if company_symbols and company_code_part not in company_symbols:
                                            continue
                                        
                                        full_url = href
                                        if href.startswith('/'):
                                            full_url = f"{self.BASE_URL}{href}"
                                        elif not href.startswith('http'):
                                            full_url = f"{self.KAP_NEWS_URL}{href}"
                                        
                                        # Only add if URL looks like a detail page
                                        if '/kap-haberi/' in full_url or '/hisse/' in full_url:
                                            news_items.append({
                                                "company_code": company_code_part,
                                                "company_name": company_name,
                                                "title": title,
                                                "date": date_str,
                                                "time": time_str,
                                                "report_date": report_date,
                                                "url": full_url
                                            })
                                except Exception as e:
                                    logger.debug(f"Error parsing date {date_str}: {e}")
            
            # Method 2: Try to find text patterns directly in the page
            if not news_items:
                # Look for text patterns in the page
                text_content = soup.get_text()
                # Pattern: COMPANY_CODE/COMPANY_NAME - TITLE DD.MM.YYYY HH:MM
                pattern = r'([A-Z]{2,6})/([^/]+?)\s+-\s+(.+?)\s+(\d{2}\.\d{2}\.\d{4})\s+(\d{2}:\d{2})'
                matches = re.finditer(pattern, text_content)
                
                for match in matches:
                    company_code_part = match.group(1)
                    company_name = match.group(2).strip()
                    title = match.group(3).strip()
                    date_str = match.group(4)
                    time_str = match.group(5)
                    
                    try:
                        report_date = datetime.strptime(date_str, "%d.%m.%Y").date()
                        days_diff = (end_date.date() - report_date).days
                        
                        if days_diff <= days_back and days_diff >= 0:
                            if company_symbols and company_code_part not in company_symbols:
                                continue
                            
                            news_items.append({
                                "company_code": company_code_part,
                                "company_name": company_name,
                                "title": title,
                                "date": date_str,
                                "time": time_str,
                                "report_date": report_date,
                                "url": self.KAP_NEWS_URL
                            })
                    except Exception as e:
                        logger.debug(f"Error parsing date from pattern match: {e}")
            
            logger.info(f"Found {len(news_items)} KAP news items from Bloomberg HT")
            print(f"📊 Found {len(news_items)} KAP news items")
            
            # Process each news item
            for item in news_items:
                report_data = {
                    "company_code": item["company_code"],
                    "company_name": item["company_name"],
                    "report_date": item["report_date"].isoformat(),
                    "title": item["title"],
                    "report_type": "",  # Bloomberg HT doesn't provide this directly
                    "summary": "",
                    "data": {
                        "url": item.get("url", self.KAP_NEWS_URL),
                        "format": "html",
                        "extracted": True,
                        "source": "bloomberg_ht",
                        "time": item["time"],
                        "original_date_str": item["date"]
                    },
                    "scraped_at": datetime.now().isoformat()
                }
                
                # Scrape detail page to get actual KAP report content
                kap_content = ""
                if item.get("url") and item["url"] != self.KAP_NEWS_URL:
                    try:
                        logger.debug(f"Scraping detail page: {item['url']}")
                        detail_result = await self.scrape_url(
                            item["url"],
                            wait_for=5000,  # Longer wait for content to load
                            formats=["markdown", "html"]
                        )
                        if detail_result.get("success"):
                            detail_doc = detail_result.get("data")
                            if detail_doc:
                                # Get HTML and markdown content
                                html_content = None
                                markdown_content = None
                                
                                if hasattr(detail_doc, 'html') and detail_doc.html:
                                    html_content = detail_doc.html
                                
                                if hasattr(detail_doc, 'markdown') and detail_doc.markdown:
                                    markdown_content = detail_doc.markdown
                                
                                # Extract KAP content from HTML directly (more reliable)
                                kap_content = ""
                                if html_content:
                                    kap_content = self._extract_kap_content_from_html(html_content)
                                
                                # Fallback to markdown extraction if HTML extraction didn't work
                                if not kap_content or len(kap_content.strip()) < 100:
                                    if markdown_content:
                                        kap_content = self._extract_kap_content_from_detail_page(markdown_content)
                                
                                # If extraction didn't work well, use the full markdown but clean it
                                if not kap_content or len(kap_content.strip()) < 100:
                                    # Fallback: try to extract from markdown directly
                                    # Look for content after the main heading
                                    lines = markdown_content.split('\n')
                                    content_lines = []
                                    found_start = False
                                    
                                    for line in lines:
                                        # Start collecting after main heading
                                        if line.startswith('# ') and '/' in line:
                                            found_start = True
                                            content_lines.append(line)
                                            continue
                                        
                                        if found_start:
                                            # Stop at navigation/footer
                                            if any(stop in line.lower() for stop in ['ilgili haberler', 'çerez', 'reklam']):
                                                break
                                            # Skip navigation links
                                            if line.strip().startswith('- [') and any(nav in line.lower() for nav in ['piyasalar', 'borsa', 'döviz']):
                                                continue
                                            # Include everything else
                                            if line.strip():
                                                content_lines.append(line)
                                    
                                    if content_lines:
                                        kap_content = '\n'.join(content_lines).strip()
                                
                                if kap_content and len(kap_content.strip()) > 50:
                                    # Use extracted content for summary and storage
                                    report_data["summary"] = kap_content[:500]  # First 500 chars as summary
                                    report_data["data"]["detail_content"] = kap_content[:5000]  # Full content up to 5k chars
                                    logger.debug(f"Extracted {len(kap_content)} chars of KAP content for {item['company_code']}")
                                else:
                                    logger.debug(f"Insufficient content extracted for {item['company_code']} ({len(kap_content) if kap_content else 0} chars)")
                                    # Fallback: use title as summary if content extraction failed
                                    if not report_data["summary"]:
                                        report_data["summary"] = item["title"]
                                    # Still store the markdown for later processing
                                    if markdown_content:
                                        report_data["data"]["detail_content"] = markdown_content[:5000]
                    except Exception as e:
                        logger.debug(f"Error scraping detail page {item['url']}: {e}")
                
                # Save report to database first
                report_id = None
                if self.db_manager:
                    try:
                        self.save_to_db(report_data, "kap_reports")
                        all_reports.append(report_data)
                        
                        # Get the inserted report ID for sentiment analysis
                        # Query the database to get the ID we just inserted
                        import psycopg2
                        from config import config
                        conn = psycopg2.connect(**config.database.get_connection_params())
                        cursor = conn.cursor()
                        cursor.execute(f"""
                            SELECT id FROM {config.database.schema}.kap_reports
                            WHERE company_code = %s AND title = %s AND report_date = %s
                            ORDER BY scraped_at DESC LIMIT 1
                        """, (item["company_code"], item["title"], item["report_date"].isoformat()))
                        result = cursor.fetchone()
                        if result:
                            report_id = result[0]
                        cursor.close()
                        conn.close()
                    except Exception as e:
                        logger.error(f"Error saving report for {item['company_code']}: {e}")
                
                # Perform sentiment analysis if requested and we have good content
                if analyze_sentiment and kap_content and len(kap_content.strip()) > 100 and self.llm_analyzer and report_id:
                    try:
                        # Limit content size for LLM (keep first 3000 chars to ensure quality analysis)
                        content_for_analysis = kap_content[:3000] if len(kap_content) > 3000 else kap_content
                        
                        logger.info(f"Analyzing sentiment for report {report_id} ({item['company_code']}): {item['title'][:50]}")
                        logger.debug(f"Content length for analysis: {len(content_for_analysis)} chars")
                        print(f"🤖 Analyzing sentiment for {item['company_code']}: {item['title'][:50]} ({len(content_for_analysis)} chars)")
                        
                        sentiment_data = await self._analyze_sentiment(content_for_analysis, report_id=report_id)
                        
                        if sentiment_data and self.db_manager:
                            # Save sentiment analysis to database
                            try:
                                import psycopg2
                                from config import config
                                from psycopg2.extras import Json
                                
                                conn = psycopg2.connect(**config.database.get_connection_params())
                                cursor = conn.cursor()
                                
                                # Use the actual table schema (no tone_descriptors, target_audience, risk_level, analysis_text)
                                # Store analysis_text in summary field, and put full JSON in raw_analysis
                                import json as json_lib
                                
                                cursor.execute(f"""
                                    INSERT INTO {config.database.schema}.kap_report_sentiment (
                                        report_id, overall_sentiment, confidence, impact_horizon,
                                        key_drivers, risk_flags, summary, raw_analysis, analyzed_at
                                    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, CURRENT_TIMESTAMP)
                                    ON CONFLICT (report_id) DO UPDATE SET
                                        overall_sentiment = EXCLUDED.overall_sentiment,
                                        confidence = EXCLUDED.confidence,
                                        impact_horizon = EXCLUDED.impact_horizon,
                                        key_drivers = EXCLUDED.key_drivers,
                                        risk_flags = EXCLUDED.risk_flags,
                                        summary = EXCLUDED.summary,
                                        raw_analysis = EXCLUDED.raw_analysis,
                                        analyzed_at = CURRENT_TIMESTAMP
                                """, (
                                    report_id,
                                    sentiment_data.get("overall_sentiment"),
                                    sentiment_data.get("confidence"),
                                    sentiment_data.get("impact_horizon"),
                                    Json(sentiment_data.get("key_drivers", [])),
                                    Json(sentiment_data.get("risk_flags", [])),
                                    sentiment_data.get("analysis_text", "")[:1000],  # Store in summary (limit length)
                                    Json(sentiment_data)  # Store full data in raw_analysis JSONB
                                ))
                                conn.commit()
                                cursor.close()
                                conn.close()
                                logger.info(f"✅ Saved sentiment analysis for report {report_id}")
                                print(f"   💾 Saved to database")
                            except Exception as e:
                                logger.error(f"Error saving sentiment analysis: {e}", exc_info=True)
                                print(f"   ❌ Database save error: {str(e)[:100]}")
                    except Exception as e:
                        logger.error(f"Error analyzing sentiment: {e}", exc_info=True)
            
        except Exception as e:
            logger.error(f"Error scraping Bloomberg HT: {e}", exc_info=True)
            return {
                "success": False,
                "error": f"Error: {str(e)}",
                "total_companies": 0,
                "processed_companies": 0,
                "reports": []
            }
        
        # Get unique companies processed
        processed_companies = len(set(r.get("company_code") for r in all_reports if r.get("company_code")))
        
        logger.info(f"Successfully scraped {len(all_reports)} reports from Bloomberg HT")
        print(f"✅ Successfully saved {len(all_reports)} reports to database")
        
        # Count sentiment analyses performed
        sentiment_count = 0
        if analyze_sentiment and self.db_manager:
            try:
                import psycopg2
                from config import config
                conn = psycopg2.connect(**config.database.get_connection_params())
                cursor = conn.cursor()
                cursor.execute(f"""
                    SELECT COUNT(*) FROM {config.database.schema}.kap_report_sentiment
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
            "reports": all_reports,
            "total_reports": len(all_reports),
            "sentiment_analyses": sentiment_count if analyze_sentiment else 0,
            "date_range": {
                "start": start_date.isoformat(),
                "end": end_date.isoformat()
            },
            "source": "bloomberg_ht"
        }
