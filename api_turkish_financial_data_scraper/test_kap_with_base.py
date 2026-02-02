#!/usr/bin/env python3
"""
KAP Scraper Test with Base Scraper Integration

This script tests the KAP scraper using the base scraper's Firecrawl integration
and saves results to the database.
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
    """Database manager for KAP data"""
    
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
            
            cursor.close()
            conn.close()
            
            return {
                'total': total_disclosures,
                'by_type': by_type,
                'by_company': by_company
            }
            
        except Exception as e:
            logger.error(f"Error getting stats: {e}")
            return None


async def test_with_base_scraper():
    """Test KAP scraping using base scraper functionality"""
    
    # Import the actual KAP scraper
    try:
        from scrapers.kap_org_scraper import KAPOrgScraper
        
        print("🚀 Testing KAP Scraper with Base Scraper Integration")
        print("=" * 60)
        
        # Initialize database manager
        db_manager = DatabaseManager()
        
        # Show current database status
        print("\n📊 Current Database Status")
        print("-" * 30)
        stats = db_manager.get_disclosure_stats()
        if stats:
            print(f"Total disclosures: {stats['total']}")
            
            if stats['by_type']:
                print("\nTop disclosure types:")
                for dtype, count in stats['by_type']:
                    print(f"   - {dtype}: {count}")
        
        # Initialize KAP scraper with database manager
        scraper = KAPOrgScraper(db_manager=db_manager)
        
        print(f"\n✅ KAP Scraper initialized")
        print(f"   Target URL: {scraper.MAIN_PAGE_URL}")
        print(f"   Database manager: {'✓' if scraper.db_manager else '✗'}")
        
        # Test basic scraping
        print("\n🔄 Running KAP Scraping Test")
        print("-" * 30)
        
        result = await scraper.scrape(
            days_back=1,
            max_items=3,
            analyze_sentiment=False
        )
        
        if result.get('success'):
            print(f"✅ Scraping successful!")
            print(f"   Total disclosures found: {result.get('total_disclosures', 0)}")
            print(f"   Companies processed: {result.get('processed_companies', 0)}")
            
            # Show sample results
            disclosures = result.get('disclosures', [])
            if disclosures:
                print(f"\n📋 Sample Results ({len(disclosures)} items):")
                for i, disclosure in enumerate(disclosures[:2], 1):
                    print(f"\n   {i}. {disclosure.get('company_name', 'N/A')[:40]}")
                    print(f"      Type: {disclosure.get('disclosure_type', 'N/A')[:50]}")
                    print(f"      Date: {disclosure.get('disclosure_date', 'N/A')}")
                    print(f"      Content length: {len(disclosure.get('content', ''))}")
                    print(f"      Language: {disclosure.get('language_info', 'N/A')}")
            
        else:
            print(f"❌ Scraping failed: {result.get('error', 'Unknown error')}")
            print("   This might be due to:")
            print("   - Network connectivity issues")
            print("   - KAP website structure changes") 
            print("   - Firecrawl API configuration")
            
            # Let's test basic connectivity
            print("\n🧪 Testing Basic Firecrawl Connectivity")
            print("-" * 40)
            
            try:
                test_result = await scraper.scrape_url("https://example.com", wait_for=3000)
                if test_result.get('success'):
                    print("✅ Firecrawl is working - issue might be with KAP site")
                else:
                    print(f"❌ Firecrawl test failed: {test_result.get('error')}")
            except Exception as e:
                print(f"❌ Firecrawl connectivity error: {e}")
        
        # Show updated database status
        print("\n🗃️ Updated Database Status")
        print("-" * 30)
        recent = db_manager.get_recent_disclosures(5)
        
        if recent:
            print(f"Latest {len(recent)} disclosures:")
            for row in recent:
                company_name = row[2][:40] if row[2] else "N/A"
                disclosure_type = row[3][:40] if row[3] else "N/A"
                scraped_at = row[9].strftime('%Y-%m-%d %H:%M') if row[9] else "N/A"
                print(f"   [{row[0]}] {company_name} - {disclosure_type} ({scraped_at})")
        else:
            print("No disclosures found in database")
        
        # Final statistics
        final_stats = db_manager.get_disclosure_stats()
        if final_stats and final_stats['total'] > 0:
            print(f"\n📈 Final Statistics")
            print(f"   Total disclosures: {final_stats['total']}")
            print(f"   Unique disclosure types: {len(final_stats['by_type'])}")
            print(f"   Unique companies: {len(final_stats['by_company'])}")
        
        print("\n🎉 Test completed!")
        
    except ImportError as e:
        print(f"❌ Import error: {e}")
        print("   Could not import KAP scraper. Checking dependencies...")
        
        # Test basic imports
        try:
            from scrapers.base_scraper import BaseScraper
            print("✅ Base scraper import successful")
        except ImportError as e2:
            print(f"❌ Base scraper import failed: {e2}")
        
        try:
            from firecrawl import FirecrawlApp
            print("✅ Firecrawl import successful")
        except ImportError as e3:
            print(f"❌ Firecrawl import failed: {e3}")
    
    except Exception as e:
        logger.error(f"Test error: {e}", exc_info=True)
        print(f"❌ Test failed: {e}")


async def main():
    """Main function"""
    await test_with_base_scraper()


if __name__ == "__main__":
    asyncio.run(main())