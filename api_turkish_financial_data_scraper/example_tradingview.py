"""
Simple example: Scrape TradingView sectors and industries
"""
import asyncio
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

from scrapers.tradingview_scraper import TradingViewScraper
from database.db_manager import DatabaseManager
from utils.logger import setup_logging


async def main():
    """Example: Scrape TradingView data"""
    
    # Setup logging
    setup_logging(level="INFO")
    
    # Initialize database
    db_manager = DatabaseManager()
    
    # Create TradingView scraper
    scraper = TradingViewScraper(db_manager=db_manager)
    
    print("\n" + "="*60)
    print("TradingView Scraper - Example")
    print("="*60)
    
    # Example 1: Scrape sectors
    print("\n1. Scraping Turkish stock sectors...")
    sectors_result = await scraper.scrape_sectors()
    
    if sectors_result.get("success"):
        sectors = sectors_result.get("sectors", [])
        print(f"   Found {len(sectors)} sectors")
        
        # Print first 5 sectors
        for sector in sectors[:5]:
            sector_name = sector.get("sector_name", "Unknown")
            stocks_count = len(sector.get("stocks", []))
            print(f"   - {sector_name}: {stocks_count} stocks")
    else:
        print(f"   Error: {sectors_result.get('error')}")
    
    # Example 2: Scrape industries
    print("\n2. Scraping Turkish stock industries...")
    industries_result = await scraper.scrape_industries()
    
    if industries_result.get("success"):
        industries = industries_result.get("industries", [])
        print(f"   Found {len(industries)} industries")
        
        # Print first 5 industries
        for industry in industries[:5]:
            industry_name = industry.get("industry_name", "Unknown")
            stocks_count = len(industry.get("stocks", []))
            print(f"   - {industry_name}: {stocks_count} stocks")
    else:
        print(f"   Error: {industries_result.get('error')}")
    
    # Example 3: Scrape both
    print("\n3. Scraping both sectors and industries...")
    both_result = await scraper.scrape(data_type="both")
    
    if both_result.get("success"):
        data = both_result.get("data", {})
        sectors = data.get("sectors", {})
        industries = data.get("industries", {})
        
        print(f"   Sectors: {sectors.get('total_sectors', 0)}")
        print(f"   Industries: {industries.get('total_industries', 0)}")
    else:
        print(f"   Error: {both_result.get('error')}")
    
    # Example 4: Scrape cryptocurrency symbols
    print("\n4. Scraping cryptocurrency symbols...")
    crypto_result = await scraper.scrape_crypto_symbols()
    
    if crypto_result.get("success"):
        cryptos = crypto_result.get("cryptocurrencies", [])
        print(f"   Found {len(cryptos)} cryptocurrencies")
        
        # Print first 10 crypto symbols
        for crypto in cryptos[:10]:
            symbol = crypto.get("symbol", "N/A")
            name = crypto.get("name", "N/A")
            print(f"   - {symbol}: {name}")
    else:
        print(f"   Error: {crypto_result.get('error')}")
    
    print("\n" + "="*60)
    print("Scraping completed!")
    print("="*60 + "\n")
    
    # Cleanup
    db_manager.close_all()


if __name__ == "__main__":
    asyncio.run(main())
