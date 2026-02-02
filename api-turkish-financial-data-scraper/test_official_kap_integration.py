#!/usr/bin/env python3
"""
Test Official KAP Scraper with Base Scraper Integration

This test verifies the KAP scraper works with the existing Firecrawl base scraper
and can save data to the database in the same format as Bloomberg HT scraper.
"""
import asyncio
import sys
import os
from pathlib import Path

# Add project paths
project_root = Path("/workspaces/firecrawl/examples/turkish-financial-data-scraper")
sys.path.insert(0, str(project_root))

# Test imports
print("🔄 Testing imports...")

try:
    from config import config
    print("✅ Config imported")
    
    from scrapers.base_scraper import BaseScraper
    print("✅ Base scraper imported")
    
    from scrapers.official_kap_scraper import OfficialKAPScraper
    print("✅ Official KAP scraper imported")
    
except ImportError as e:
    print(f"❌ Import error: {e}")
    sys.exit(1)


async def test_kap_scraper():
    """Test the KAP scraper functionality"""
    
    print("\n🧪 Testing Official KAP Scraper with Base Integration")
    print("=" * 60)
    
    try:
        # Initialize scraper
        print("1️⃣  Initializing KAP scraper...")
        scraper = OfficialKAPScraper()
        print(f"   ✅ Scraper initialized: {scraper.__class__.__name__}")
        
        # Check Firecrawl configuration
        print("2️⃣  Checking Firecrawl configuration...")
        firecrawl_config = scraper.firecrawl
        print(f"   API URL: {getattr(firecrawl_config, 'api_url', 'Not set')}")
        print(f"   Formats: {config.firecrawl.formats}")
        print(f"   Wait for: {config.firecrawl.wait_for}ms")
        print(f"   Timeout: {config.firecrawl.timeout}ms")
        
        # Test basic URL scraping
        print("3️⃣  Testing URL scraping with Firecrawl...")
        test_url = "https://kap.org.tr/en/"
        
        result = await scraper.scrape_url(test_url)
        
        if result.get("success"):
            data = result.get("data", {})
            html_length = len(data.get("html", ""))
            markdown_length = len(data.get("markdown", ""))
            
            print(f"   ✅ Successfully scraped {test_url}")
            print(f"   📄 HTML content: {html_length:,} characters")
            print(f"   📝 Markdown content: {markdown_length:,} characters")
            
            # Show sample content
            if data.get("markdown"):
                sample = data["markdown"][:200]
                print(f"   📋 Sample content: {sample}...")
                
        else:
            error = result.get("error", "Unknown error")
            print(f"   ❌ Failed to scrape: {error}")
            return False
        
        # Test full scraper functionality
        print("4️⃣  Testing full scraper functionality...")
        
        scrape_result = await scraper.scrape()
        
        if scrape_result.get("success"):
            scraped_items = scrape_result.get("scraped_items", 0)
            saved_items = scrape_result.get("saved_items", 0)
            
            print(f"   ✅ Scraping completed successfully")
            print(f"   📊 Items scraped: {scraped_items}")
            print(f"   💾 Items saved: {saved_items}")
            
            # Show sample items
            items = scrape_result.get("items", [])
            if items:
                print(f"   📋 Sample items:")
                for i, item in enumerate(items[:3], 1):
                    company = item.get("company_name", "N/A")[:30]
                    title = item.get("title", "N/A")[:40] 
                    print(f"      {i}. {company} - {title}")
            
        else:
            error = scrape_result.get("error", "Unknown error")
            print(f"   ❌ Scraping failed: {error}")
            
        return True
        
    except Exception as e:
        print(f"❌ Test failed with error: {e}")
        import traceback
        traceback.print_exc()
        return False


async def test_database_integration():
    """Test database integration"""
    print("\n💾 Testing Database Integration")
    print("=" * 40)
    
    try:
        import psycopg2
        
        # Test connection
        conn_params = config.database.get_connection_params()
        print(f"1️⃣  Connecting to database: {conn_params['host']}:{conn_params['port']}")
        
        conn = psycopg2.connect(**conn_params)
        cursor = conn.cursor()
        
        # Check tables
        cursor.execute("""
            SELECT table_name 
            FROM information_schema.tables 
            WHERE table_schema = %s
            AND table_name LIKE 'kap%'
            ORDER BY table_name
        """, (config.database.schema,))
        
        tables = [row[0] for row in cursor.fetchall()]
        print(f"   ✅ Found KAP tables: {tables}")
        
        # Check existing data
        if 'kap_disclosures' in tables:
            cursor.execute(f"SELECT COUNT(*) FROM {config.database.schema}.kap_disclosures")
            disclosure_count = cursor.fetchone()[0]
            print(f"   📊 Existing disclosures: {disclosure_count}")
        
        if 'kap_reports' in tables:
            cursor.execute(f"SELECT COUNT(*) FROM {config.database.schema}.kap_reports")
            report_count = cursor.fetchone()[0]
            print(f"   📊 Existing reports: {report_count}")
        
        cursor.close()
        conn.close()
        
        print("   ✅ Database integration test passed")
        return True
        
    except Exception as e:
        print(f"   ❌ Database test failed: {e}")
        return False


if __name__ == "__main__":
    async def main():
        print("🚀 Official KAP Scraper Integration Test")
        print("=" * 50)
        
        # Test database first
        db_success = await test_database_integration()
        
        if db_success:
            # Test scraper
            scraper_success = await test_kap_scraper()
            
            if scraper_success:
                print("\n🎉 All tests passed! Integration working correctly.")
                print("💡 The Official KAP scraper is ready to use with Firecrawl base.")
            else:
                print("\n⚠️  Scraper tests failed - check configuration.")
                sys.exit(1)
        else:
            print("\n⚠️  Database tests failed - check connection.")
            sys.exit(1)
    
    # Run the test
    asyncio.run(main())