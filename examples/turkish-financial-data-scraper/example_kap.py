"""
Simple example: Scrape KAP reports using Firecrawl
"""
import asyncio
import os
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

from scrapers.kap_scraper import KAPScraper
from database.db_manager import DatabaseManager
from utils.logger import setup_logging


async def main():
    """Example: Scrape recent KAP reports"""
    
    # Setup logging
    setup_logging(level="INFO")
    
    # Initialize database
    db_manager = DatabaseManager()
    
    # Create KAP scraper
    scraper = KAPScraper(db_manager=db_manager)
    
    print("\n" + "="*60)
    print("KAP Reports Scraper - Example")
    print("="*60)
    
    # Example 1: Scrape all BIST indices and companies
    print("\n1. Scraping BIST indices...")
    indices_result = await scraper.scrape_bist_indices()
    
    if indices_result.get("success"):
        indices = indices_result.get("data", {}).get("indices", [])
        print(f"   Found {len(indices)} indices")
        
        # Print first 3 indices
        for idx in indices[:3]:
            print(f"   - {idx.get('name')}: "
                  f"{len(idx.get('companies', []))} companies")
    else:
        print(f"   Error: {indices_result.get('error')}")
    
    # Example 2: Scrape recent reports (last 7 days)
    print("\n2. Scraping recent KAP reports (last 7 days)...")
    reports_result = await scraper.scrape(days_back=7)
    
    if reports_result.get("success"):
        total_companies = reports_result.get("total_companies", 0)
        processed = reports_result.get("processed_companies", 0)
        print(f"   Total companies: {total_companies}")
        print(f"   Processed: {processed}")
    else:
        print(f"   Error: {reports_result.get('error')}")
    
    # Example 3: Scrape specific company report
    print("\n3. Scraping specific company (THYAO - Turkish Airlines)...")
    company_result = await scraper.scrape_company_report(
        company_code="THYAO"
    )
    
    if company_result.get("success"):
        data = company_result.get("data", {})
        print(f"   Company: {data.get('company', 'N/A')}")
        print(f"   Report Type: {data.get('report_type', 'N/A')}")
        print(f"   Date: {data.get('date', 'N/A')}")
    else:
        print(f"   Error: {company_result.get('error')}")
    
    print("\n" + "="*60)
    print("Scraping completed!")
    print("="*60 + "\n")
    
    # Cleanup
    db_manager.close_all()


if __name__ == "__main__":
    asyncio.run(main())
