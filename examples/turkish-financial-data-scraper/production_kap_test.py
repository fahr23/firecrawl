#!/usr/bin/env python3
"""
Production KAP Scraper Test

Tests the Official KAP scraper using the Firecrawl base scraper pattern.
This follows the same pattern as the Bloomberg HT scraper but targets KAP.org.tr directly.
"""
import asyncio
import sys
import os
import logging
from datetime import datetime

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Simple scraper implementation following base pattern
class ProductionKAPScraper:
    """Production KAP scraper following the base scraper pattern"""
    
    def __init__(self):
        """Initialize scraper with Firecrawl"""
        from firecrawl import FirecrawlApp
        
        self.firecrawl = FirecrawlApp(
            api_key="",  # Empty for self-hosted
            api_url="http://api:3002"  # Self-hosted Firecrawl instance
        )
        
        self.base_url = "https://kap.org.tr"
        self.disclosures_url = f"{self.base_url}/en/"
        
        logger.info("Initialized ProductionKAPScraper with Firecrawl")
    
    async def scrape_url(self, url: str) -> dict:
        """Scrape URL using Firecrawl (same as base scraper)"""
        try:
            logger.info(f"Scraping URL: {url}")
            
            result = self.firecrawl.scrape(
                url,
                formats=["markdown", "html"],
                wait_for=3000,
                timeout=30000
            )
            
            # Handle Document object format
            data = {
                "html": getattr(result, 'html', ''),
                "markdown": getattr(result, 'markdown', ''),
                "metadata": getattr(result, 'metadata', {})
            }
            
            logger.info(f"Successfully scraped {url}: {len(data['html'])} chars HTML, {len(data['markdown'])} chars markdown")
            
            return {
                "success": True,
                "url": url,
                "data": data
            }
            
        except Exception as e:
            logger.error(f"Error scraping {url}: {e}")
            return {
                "success": False,
                "url": url,
                "error": str(e)
            }
    
    def parse_disclosures(self, html: str, markdown: str) -> list:
        """Parse disclosures from scraped content"""
        items = []
        
        # Check if KAP shows no disclosures
        if "Notification not found" in html or "Notification not found" in markdown:
            logger.info("KAP website shows 'Notification not found' - no recent disclosures available")
            return []
        
        # Simple parsing - look for company names in content
        import re
        from bs4 import BeautifulSoup
        
        try:
            # Parse HTML for structured data
            soup = BeautifulSoup(html, 'html.parser')
            
            # Look for table rows that might contain disclosure data
            rows = soup.find_all('tr')
            logger.info(f"Found {len(rows)} table rows to analyze")
            
            for i, row in enumerate(rows):
                cells = row.find_all(['td', 'th'])
                if len(cells) >= 2:  # Need at least 2 cells for meaningful data
                    
                    cell_texts = [cell.get_text(strip=True) for cell in cells]
                    row_text = ' | '.join(cell_texts)
                    
                    # Look for Turkish company patterns
                    if self._contains_company_pattern(row_text):
                        company = self._extract_company_name(row_text)
                        if company:
                            item = {
                                'id': f'kap_prod_{datetime.now().strftime("%Y%m%d_%H%M%S")}_{len(items)}',
                                'company_name': company,
                                'title': row_text[:100],
                                'content': row_text,
                                'scraped_at': datetime.now().isoformat(),
                                'source_url': self.disclosures_url,
                                'data': {
                                    'cells': cell_texts,
                                    'row_index': i
                                }
                            }
                            items.append(item)
                            logger.debug(f"Found disclosure: {company}")
            
            # Fallback: Look in markdown for company names
            if not items:
                lines = markdown.split('\\n')
                for i, line in enumerate(lines):
                    if self._contains_company_pattern(line):
                        company = self._extract_company_name(line)
                        if company:
                            item = {
                                'id': f'kap_md_{datetime.now().strftime("%Y%m%d_%H%M%S")}_{len(items)}',
                                'company_name': company,
                                'title': line[:100],
                                'content': line,
                                'scraped_at': datetime.now().isoformat(),
                                'source_url': self.disclosures_url,
                                'data': {
                                    'source': 'markdown',
                                    'line_index': i
                                }
                            }
                            items.append(item)
                            logger.debug(f"Found company mention: {company}")
            
        except Exception as e:
            logger.error(f"Error parsing content: {e}")
        
        logger.info(f"Parsed {len(items)} disclosure items")
        return items
    
    def _contains_company_pattern(self, text: str) -> bool:
        """Check if text contains Turkish company patterns"""
        if not text or len(text) < 5:
            return False
        
        patterns = [
            r'[A-ZÇĞİÖŞÜ][A-ZÇĞİÖŞÜa-zçğıöşü\s]+A\.Ş\.',
            r'[A-ZÇĞİÖŞÜ][A-ZÇĞİÖŞÜa-zçğıöşü\s]+A\.S\.',
            r'[A-ZÇĞİÖŞÜ][A-ZÇĞİÖŞÜa-zçğıöşü\s]+BANKASI',
            r'[A-ZÇĞİÖŞÜ][A-ZÇĞİÖŞÜa-zçğıöşü\s]+HOLDİNG',
            r'[A-ZÇĞİÖŞÜ][A-ZÇĞİÖŞÜa-zçğıöşü\s]+LTD'
        ]
        
        import re
        for pattern in patterns:
            if re.search(pattern, text):
                return True
        
        return False
    
    def _extract_company_name(self, text: str) -> str:
        """Extract company name from text"""
        import re
        
        patterns = [
            r'([A-ZÇĞİÖŞÜ][A-ZÇĞİÖŞÜa-zçğıöşü\s]+(?:A\.Ş\.|A\.S\.))',
            r'([A-ZÇĞİÖŞÜ][A-ZÇĞİÖŞÜa-zçğıöşü\s]+BANKASI)',
            r'([A-ZÇĞİÖŞÜ][A-ZÇĞİÖŞÜa-zçğıöşü\s]+HOLDİNG)',
            r'([A-ZÇĞİÖŞÜ][A-ZÇĞİÖŞÜa-zçğıöşü\s]+LTD)'
        ]
        
        for pattern in patterns:
            match = re.search(pattern, text)
            if match:
                return match.group(1).strip()
        
        # Fallback: first meaningful word
        words = text.split()
        if words and len(words[0]) > 3:
            return words[0]
        
        return ""
    
    async def scrape(self) -> dict:
        """Main scrape method"""
        try:
            logger.info("Starting KAP disclosure scraping...")
            
            # Step 1: Scrape main page
            result = await self.scrape_url(self.disclosures_url)
            
            if not result.get("success"):
                return {
                    "success": False,
                    "error": f"Failed to scrape main page: {result.get('error')}",
                    "scraped_items": 0
                }
            
            # Step 2: Parse content
            data = result["data"]
            html = data.get("html", "")
            markdown = data.get("markdown", "")
            
            items = self.parse_disclosures(html, markdown)
            
            # Step 3: Return results
            return {
                "success": True,
                "scraped_items": len(items),
                "items": items,
                "source_url": self.disclosures_url,
                "content_stats": {
                    "html_chars": len(html),
                    "markdown_chars": len(markdown),
                    "has_notification_not_found": "Notification not found" in html
                }
            }
            
        except Exception as e:
            logger.error(f"Scraping failed: {e}")
            return {
                "success": False,
                "error": str(e),
                "scraped_items": 0
            }
    
    def save_to_database(self, items: list):
        """Save items to database (same pattern as Bloomberg HT scraper)"""
        try:
            import psycopg2
            
            # Database connection (matches existing setup)
            conn = psycopg2.connect(
                host='nuq-postgres',
                port=5432,
                database='postgres',
                user='postgres', 
                password='postgres'
            )
            cursor = conn.cursor()
            
            saved_count = 0
            for item in items:
                try:
                    # Insert into kap_disclosures table (created earlier)
                    cursor.execute("""
                        INSERT INTO turkish_financial.kap_disclosures 
                        (id, company_name, company_code, title, disclosure_type, summary, content, 
                         published_date, detail_url, source_url, data, scraped_at)
                        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                        ON CONFLICT (id) DO NOTHING
                    """, (
                        item['id'],
                        item['company_name'][:255],
                        item['company_name'].split()[0][:10] if item['company_name'] else '',
                        item['title'][:500],
                        'General',
                        item['content'][:1000],
                        item['content'],
                        datetime.now(),  # published_date
                        '',  # detail_url
                        item['source_url'],
                        item['data'],  # JSON data
                        datetime.now()  # scraped_at
                    ))
                    saved_count += 1
                    
                except Exception as e:
                    logger.error(f"Error saving item {item['id']}: {e}")
                    continue
            
            conn.commit()
            cursor.close()
            conn.close()
            
            logger.info(f"Saved {saved_count} items to database")
            return saved_count
            
        except Exception as e:
            logger.error(f"Database save failed: {e}")
            return 0


async def main():
    """Main test function"""
    print("🚀 Production KAP Scraper Test")
    print("=" * 50)
    
    try:
        # Initialize scraper
        scraper = ProductionKAPScraper()
        
        # Run scraping
        print("📥 Scraping KAP disclosures...")
        result = await scraper.scrape()
        
        if result.get("success"):
            items = result.get("items", [])
            stats = result.get("content_stats", {})
            
            print(f"✅ Scraping successful!")
            print(f"   📊 Items found: {len(items)}")
            print(f"   📄 HTML content: {stats.get('html_chars', 0):,} chars")
            print(f"   📝 Markdown content: {stats.get('markdown_chars', 0):,} chars")
            print(f"   ℹ️  'Notification not found': {stats.get('has_notification_not_found', False)}")
            
            if items:
                print(f"\\n📋 Sample items:")
                for i, item in enumerate(items[:3], 1):
                    print(f"   {i}. {item['company_name']} - {item['title'][:50]}")
                
                # Save to database
                print(f"\\n💾 Saving to database...")
                saved = scraper.save_to_database(items)
                print(f"   ✅ Saved {saved} items to database")
                
            else:
                print("\\n📝 No disclosure items found.")
                print("   This is normal when KAP shows 'Notification not found'")
                print("   This may happen during off-hours or when no recent disclosures exist")
        
        else:
            error = result.get("error", "Unknown error")
            print(f"❌ Scraping failed: {error}")
    
    except Exception as e:
        print(f"❌ Test failed: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    asyncio.run(main())