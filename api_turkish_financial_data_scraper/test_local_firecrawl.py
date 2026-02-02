"""
Test script for local Firecrawl instance
"""
import asyncio
from scrapers.bist_scraper import BISTScraper
from database.db_manager import DatabaseManager
from utils.logger import setup_logging

setup_logging()

async def test_bist_scraper():
    """Test BIST scraper with local Firecrawl"""
    print("=" * 60)
    print("Testing Turkish Financial Scraper with Local Firecrawl")
    print("=" * 60)
    
    # Initialize database
    db = DatabaseManager()
    print("✓ Database initialized")
    
    # Initialize scraper
    scraper = BISTScraper(db_manager=db)
    print("✓ BIST Scraper initialized")
    print(f"  Using Firecrawl at: {scraper.config.firecrawl.base_url or 'Cloud API'}")
    
    # Try a simple scrape of BIST main page
    print("\n" + "=" * 60)
    print("Testing scrape of BIST main page...")
    print("=" * 60)
    
    try:
        result = await scraper.scrape_url(
            "https://www.borsaistanbul.com/",
            wait_for=2000,
            timeout=15000
        )
        
        if result:
            print("✓ Successfully scraped BIST main page")
            markdown = result.get('markdown', '')
            if markdown:
                print(f"\nFirst 300 characters of content:")
                print("-" * 60)
                print(markdown[:300])
                print("-" * 60)
            else:
                print("⚠ No markdown content returned")
        else:
            print("✗ No result returned from scrape")
            
    except Exception as e:
        print(f"✗ Error during scrape: {e}")
        import traceback
        traceback.print_exc()
    
    finally:
        db.close_pool()
        print("\n✓ Database connection closed")

if __name__ == "__main__":
    asyncio.run(test_bist_scraper())
