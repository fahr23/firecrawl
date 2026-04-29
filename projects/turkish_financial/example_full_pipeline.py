"""
Comprehensive example: Complete scraping pipeline
Demonstrates all features of the Turkish Financial Data Scraper
"""
import asyncio
from datetime import datetime, timedelta
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

from scrapers import KAPScraper, BISTScraper, TradingViewScraper
from database.db_manager import DatabaseManager
from utils.logger import setup_logging


async def run_full_pipeline():
    """Run complete scraping pipeline"""
    
    print("\n" + "="*70)
    print(" Turkish Financial Data Scraper - Full Pipeline Example ".center(70))
    print("="*70)
    
    # Initialize database
    print("\n[1/5] Initializing database...")
    db_manager = DatabaseManager()
    print("✓ Database initialized")
    
    # ========== BIST Companies ==========
    print("\n[2/5] Scraping BIST Companies...")
    bist_scraper = BISTScraper(db_manager=db_manager)
    
    # Scrape all BIST companies
    companies_result = await bist_scraper.scrape()
    if companies_result.get("success"):
        total = companies_result.get("total_companies", 0)
        print(f"✓ Scraped {total} BIST companies")
    else:
        print(f"✗ Error: {companies_result.get('error')}")
    
    # Scrape BIST indices
    indices_result = await bist_scraper.scrape_indices()
    if indices_result.get("success"):
        total = indices_result.get("total_indices", 0)
        print(f"✓ Scraped {total} BIST indices")
    else:
        print(f"✗ Error: {indices_result.get('error')}")
    
    # ========== Commodity Prices ==========
    print("\n[3/5] Scraping Commodity Prices...")
    
    end_date = datetime.now().strftime("%Y%m%d")
    start_date = (datetime.now() - timedelta(days=30)).strftime("%Y%m%d")
    
    commodity_result = await bist_scraper.scrape_commodity_prices(
        start_date=start_date,
        end_date=end_date,
        price_types=["AG", "AU"]  # Silver and Gold
    )
    
    if commodity_result.get("success"):
        total = commodity_result.get("total_prices", 0)
        types = commodity_result.get("price_types", [])
        print(f"✓ Scraped {total} commodity prices for {', '.join(types)}")
    else:
        print(f"✗ Error: {commodity_result.get('error')}")
    
    # ========== TradingView Data ==========
    print("\n[4/5] Scraping TradingView Classifications...")
    tv_scraper = TradingViewScraper(db_manager=db_manager)
    
    # Scrape sectors
    sectors_result = await tv_scraper.scrape_sectors()
    if sectors_result.get("success"):
        total = sectors_result.get("total_sectors", 0)
        print(f"✓ Scraped {total} sectors")
    else:
        print(f"✗ Error: {sectors_result.get('error')}")
    
    # Scrape industries
    industries_result = await tv_scraper.scrape_industries()
    if industries_result.get("success"):
        total = industries_result.get("total_industries", 0)
        print(f"✓ Scraped {total} industries")
    else:
        print(f"✗ Error: {industries_result.get('error')}")
    
    # ========== KAP Reports ==========
    print("\n[5/5] Scraping KAP Reports...")
    kap_scraper = KAPScraper(db_manager=db_manager)
    
    # Scrape recent reports
    reports_result = await kap_scraper.scrape(days_back=3)
    if reports_result.get("success"):
        total = reports_result.get("processed_companies", 0)
        print(f"✓ Scraped reports from {total} companies")
    else:
        print(f"✗ Error: {reports_result.get('error')}")
    
    # ========== Query Results ==========
    print("\n" + "="*70)
    print(" Database Summary ".center(70))
    print("="*70)
    
    # Query database for summary
    queries = {
        "BIST Companies": "SELECT COUNT(*) as count FROM bist_companies",
        "Index Members": "SELECT COUNT(*) as count FROM bist_index_members",
        "Commodity Prices": "SELECT COUNT(*) as count FROM historical_price_emtia",
        "TradingView Sectors": "SELECT COUNT(*) as count FROM tradingview_sectors_tr",
        "TradingView Industries": "SELECT COUNT(*) as count FROM tradingview_industry_tr",
        "KAP Reports": "SELECT COUNT(*) as count FROM kap_reports",
    }
    
    print()
    for name, query in queries.items():
        result = db_manager.query(query)
        count = result[0]["count"] if result else 0
        print(f"  {name:.<30} {count:>6} records")
    
    # Show latest KAP reports
    print("\n" + "-"*70)
    print(" Latest KAP Reports ".center(70))
    print("-"*70)
    
    latest_reports = db_manager.query("""
        SELECT company_code, company_name, scraped_at
        FROM kap_reports
        ORDER BY scraped_at DESC
        LIMIT 5
    """)
    
    if latest_reports:
        for report in latest_reports:
            code = report.get("company_code", "N/A")
            name = report.get("company_name", "N/A")[:30]
            date = report.get("scraped_at", "N/A")
            print(f"  {code:<10} {name:<32} {date}")
    else:
        print("  No reports found")
    
    # Show sector distribution
    print("\n" + "-"*70)
    print(" Top Sectors by Stock Count ".center(70))
    print("-"*70)
    
    sector_stats = db_manager.query("""
        SELECT sector_name, COUNT(*) as stock_count
        FROM tradingview_sectors_tr
        GROUP BY sector_name
        ORDER BY stock_count DESC
        LIMIT 5
    """)
    
    if sector_stats:
        for sector in sector_stats:
            name = sector.get("sector_name", "N/A")[:40]
            count = sector.get("stock_count", 0)
            print(f"  {name:<42} {count:>4} stocks")
    else:
        print("  No sector data found")
    
    print("\n" + "="*70)
    print(" Pipeline Completed Successfully! ".center(70))
    print("="*70)
    print()
    print("Next steps:")
    print("  • Review data in your database")
    print("  • Set up automated scheduling with scheduler.py")
    print("  • Build analytics and reports on collected data")
    print("  • Customize scrapers for your specific needs")
    print()
    
    # Cleanup
    db_manager.close_all()


async def main():
    """Main entry point"""
    # Setup logging
    setup_logging(level="INFO")
    
    try:
        await run_full_pipeline()
    except KeyboardInterrupt:
        print("\n\nScraping interrupted by user")
    except Exception as e:
        print(f"\n\nError: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    asyncio.run(main())
