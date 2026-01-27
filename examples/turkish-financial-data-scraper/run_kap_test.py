#!/usr/bin/env python3
"""
KAP Scraper Database Test

Run the KAP scraper and save results to database, then display the results.
"""

import asyncio
import sys
import os
import logging
from datetime import datetime
import psycopg2
import json

# Add current directory to path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from config import config

# Set up logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


class DatabaseManager:
    """Simple database manager for KAP data"""
    
    def __init__(self):
        self.config = config
    
    def save_disclosure(self, disclosure_data):
        """Save disclosure to database"""
        try:
            conn = psycopg2.connect(**self.config.database.get_connection_params())
            cursor = conn.cursor()
            
            insert_sql = f"""
                INSERT INTO {self.config.database.schema}.kap_disclosures 
                (disclosure_id, company_name, disclosure_type, disclosure_date, 
                 timestamp, language_info, has_attachment, detail_url, content, data)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (disclosure_id, company_name, disclosure_type) 
                DO UPDATE SET 
                    content = EXCLUDED.content,
                    data = EXCLUDED.data,
                    scraped_at = CURRENT_TIMESTAMP
                RETURNING id
            """
            
            cursor.execute(insert_sql, (
                disclosure_data.get('disclosure_id'),
                disclosure_data.get('company_name'),
                disclosure_data.get('disclosure_type'),
                disclosure_data.get('disclosure_date'),
                disclosure_data.get('timestamp'),
                disclosure_data.get('language_info'),
                disclosure_data.get('has_attachment'),
                disclosure_data.get('detail_url'),
                disclosure_data.get('content'),
                json.dumps(disclosure_data.get('data', {}))
            ))
            
            result = cursor.fetchone()
            disclosure_db_id = result[0] if result else None
            
            conn.commit()
            cursor.close()
            conn.close()
            
            return disclosure_db_id
            
        except Exception as e:
            logger.error(f"Error saving disclosure: {e}")
            return None
    
    def get_recent_disclosures(self, limit=10):
        """Get recent disclosures from database"""
        try:
            conn = psycopg2.connect(**self.config.database.get_connection_params())
            cursor = conn.cursor()
            
            cursor.execute(f"""
                SELECT id, disclosure_id, company_name, disclosure_type, 
                       disclosure_date, timestamp, language_info, 
                       has_attachment, LENGTH(content) as content_length,
                       scraped_at
                FROM {self.config.database.schema}.kap_disclosures 
                ORDER BY scraped_at DESC 
                LIMIT %s
            """, (limit,))
            
            results = cursor.fetchall()
            cursor.close()
            conn.close()
            
            return results
            
        except Exception as e:
            logger.error(f"Error fetching disclosures: {e}")
            return []
    
    def get_disclosure_stats(self):
        """Get disclosure statistics"""
        try:
            conn = psycopg2.connect(**self.config.database.get_connection_params())
            cursor = conn.cursor()
            
            # Total disclosures
            cursor.execute(f"SELECT COUNT(*) FROM {self.config.database.schema}.kap_disclosures")
            total_disclosures = cursor.fetchone()[0]
            
            # Disclosures by type
            cursor.execute(f"""
                SELECT disclosure_type, COUNT(*) 
                FROM {self.config.database.schema}.kap_disclosures 
                GROUP BY disclosure_type 
                ORDER BY COUNT(*) DESC 
                LIMIT 5
            """)
            by_type = cursor.fetchall()
            
            # Disclosures by company
            cursor.execute(f"""
                SELECT company_name, COUNT(*) 
                FROM {self.config.database.schema}.kap_disclosures 
                GROUP BY company_name 
                ORDER BY COUNT(*) DESC 
                LIMIT 5
            """)
            by_company = cursor.fetchall()
            
            # Recent activity
            cursor.execute(f"""
                SELECT DATE(scraped_at) as date, COUNT(*) 
                FROM {self.config.database.schema}.kap_disclosures 
                GROUP BY DATE(scraped_at) 
                ORDER BY date DESC 
                LIMIT 7
            """)
            by_date = cursor.fetchall()
            
            cursor.close()
            conn.close()
            
            return {
                'total': total_disclosures,
                'by_type': by_type,
                'by_company': by_company,
                'by_date': by_date
            }
            
        except Exception as e:
            logger.error(f"Error getting stats: {e}")
            return None


class SimplifiedKAPScraper:
    """Simplified KAP scraper for testing"""
    
    BASE_URL = "https://kap.org.tr"
    MAIN_PAGE_URL = f"{BASE_URL}/en"
    
    def __init__(self, db_manager=None):
        self.db_manager = db_manager
        
    async def scrape_with_firecrawl(self, max_items=5):
        """Scrape using Firecrawl"""
        try:
            from firecrawl import FirecrawlApp
            
            # Initialize Firecrawl
            if config.firecrawl.base_url:
                app = FirecrawlApp(api_url=config.firecrawl.base_url)
            else:
                app = FirecrawlApp(api_key=config.firecrawl.api_key)
            
            print(f"🔗 Scraping KAP main page: {self.MAIN_PAGE_URL}")
            
            # Scrape the main page
            result = app.scrape(
                self.MAIN_PAGE_URL,
                params={
                    'formats': ['markdown', 'html'],
                    'waitFor': 5000
                }
            )
            
            if not result.get('success'):
                print(f"❌ Firecrawl failed: {result.get('error', 'Unknown error')}")
                return []
            
            # Get content
            content = result.get('data', {})
            markdown = content.get('markdown', '')
            
            if not markdown:
                print("❌ No content received from Firecrawl")
                return []
            
            print(f"✅ Retrieved {len(markdown)} characters of content")
            
            # Parse the content for disclosure items
            disclosures = self.parse_kap_content(markdown)
            
            # Limit results for testing
            if len(disclosures) > max_items:
                disclosures = disclosures[:max_items]
            
            return disclosures
            
        except Exception as e:
            logger.error(f"Error with Firecrawl scraping: {e}")
            print(f"❌ Firecrawl error: {e}")
            return []
    
    def parse_kap_content(self, content):
        """Parse KAP content to extract disclosure items"""
        import re
        from datetime import datetime, date
        
        disclosures = []
        
        try:
            # Look for disclosure patterns in the text
            # Pattern: checkbox NUMBER Today/Yesterday TIME COMPANY_NAME Disclosure_Type
            pattern = r'checkbox\s+(\d+)\s+(Today|Yesterday|\d{2}\.\d{2}\.\d{4})\s+(\d{2}:\d{2})\s+(.+?)(?=checkbox|$)'
            matches = re.finditer(pattern, content, re.MULTILINE | re.DOTALL)
            
            for match in matches:
                disclosure_id = match.group(1)
                date_part = match.group(2)
                time_str = match.group(3)
                content_text = match.group(4).strip()
                
                # Parse the content text to extract company and disclosure type
                lines = content_text.split('\n')
                main_line = lines[0] if lines else content_text
                
                # Clean the main line
                main_line = main_line.strip()
                
                # Try to split company name and disclosure type
                company_name = ""
                disclosure_type = ""
                language_info = ""
                
                # Look for language info (English, Attachment, etc.)
                for line in lines:
                    if line.strip() in ['English', 'Attachment', 'Turkish']:
                        language_info = line.strip()
                        break
                
                # Split main line into company and disclosure type
                if main_line:
                    # Common patterns for company name endings
                    company_endings = ['A.Ş.', 'T.A.Ş.', 'BANKASI', 'BANK']
                    
                    words = main_line.split()
                    company_words = []
                    disclosure_words = []
                    found_break = False
                    
                    for i, word in enumerate(words):
                        if not found_break:
                            company_words.append(word)
                            # Check if this word ends the company name
                            if any(ending in word for ending in company_endings):
                                found_break = True
                            # Also check if next words look like disclosure types
                            elif i < len(words) - 1:
                                next_word = words[i + 1].lower()
                                if next_word in ['material', 'notification', 'financial', 'fund', 'corporate']:
                                    found_break = True
                        else:
                            disclosure_words.append(word)
                    
                    company_name = ' '.join(company_words).strip()
                    disclosure_type = ' '.join(disclosure_words).strip()
                
                # Parse date
                disclosure_date = None
                try:
                    if date_part == "Today":
                        disclosure_date = date.today()
                    elif date_part == "Yesterday":
                        from datetime import timedelta
                        disclosure_date = date.today() - timedelta(days=1)
                    else:
                        disclosure_date = datetime.strptime(date_part, "%d.%m.%Y").date()
                except:
                    disclosure_date = date.today()
                
                if company_name and disclosure_type:
                    disclosures.append({
                        'disclosure_id': disclosure_id,
                        'company_name': company_name,
                        'disclosure_type': disclosure_type,
                        'disclosure_date': disclosure_date.isoformat(),
                        'timestamp': f"{date_part} {time_str}",
                        'language_info': language_info,
                        'has_attachment': 'attachment' in language_info.lower(),
                        'detail_url': '',
                        'content': content_text[:1000],  # First 1000 chars
                        'data': {
                            'source': 'kap_org',
                            'scraped_with': 'firecrawl',
                            'raw_content_length': len(content_text)
                        }
                    })
            
            print(f"📋 Parsed {len(disclosures)} disclosure items")
            
        except Exception as e:
            logger.error(f"Error parsing content: {e}")
            print(f"❌ Parse error: {e}")
        
        return disclosures
    
    async def run_test_scrape(self, max_items=5):
        """Run a test scrape and save to database"""
        print("🚀 Starting KAP scraper test with database integration")
        print("=" * 60)
        
        # Scrape disclosures
        disclosures = await self.scrape_with_firecrawl(max_items)
        
        if not disclosures:
            print("❌ No disclosures found")
            return
        
        # Save to database
        if self.db_manager:
            saved_count = 0
            for disclosure in disclosures:
                db_id = self.db_manager.save_disclosure(disclosure)
                if db_id:
                    saved_count += 1
                    print(f"💾 Saved disclosure {db_id}: {disclosure['company_name'][:30]}...")
            
            print(f"\n✅ Saved {saved_count}/{len(disclosures)} disclosures to database")
        
        return disclosures


async def main():
    """Main function"""
    print("🎯 KAP Scraper Database Integration Test")
    print("=" * 50)
    
    # Initialize database manager
    db_manager = DatabaseManager()
    
    # Check existing data
    print("\n📊 Current Database Status")
    print("-" * 30)
    stats = db_manager.get_disclosure_stats()
    if stats:
        print(f"Total disclosures: {stats['total']}")
        
        if stats['by_type']:
            print("\nTop disclosure types:")
            for dtype, count in stats['by_type']:
                print(f"   - {dtype}: {count}")
        
        if stats['by_company']:
            print("\nTop companies:")
            for company, count in stats['by_company']:
                print(f"   - {company[:40]}: {count}")
    
    # Initialize scraper
    scraper = SimplifiedKAPScraper(db_manager)
    
    # Run scraping test
    print("\n🔄 Running Scraping Test")
    print("-" * 30)
    
    try:
        disclosures = await scraper.run_test_scrape(max_items=3)
        
        if disclosures:
            print(f"\n📋 Sample Results:")
            for i, disclosure in enumerate(disclosures[:2], 1):
                print(f"\n   {i}. {disclosure['company_name']}")
                print(f"      Type: {disclosure['disclosure_type']}")
                print(f"      Date: {disclosure['disclosure_date']}")
                print(f"      Language: {disclosure['language_info']}")
    
    except Exception as e:
        logger.error(f"Scraping error: {e}")
        print(f"❌ Scraping failed: {e}")
    
    # Show recent results from database
    print("\n🗃️ Recent Database Results")
    print("-" * 30)
    recent = db_manager.get_recent_disclosures(5)
    
    if recent:
        print(f"Latest {len(recent)} disclosures:")
        for row in recent:
            print(f"   [{row[0]}] {row[2][:40]} - {row[3][:40]} ({row[9]})")
    else:
        print("No disclosures found in database")
    
    print("\n🎉 Test completed!")


if __name__ == "__main__":
    asyncio.run(main())