#!/usr/bin/env python3
"""
Test script for KAP.org.tr scraper

This script demonstrates how to use the KAP scraper to fetch and analyze 
disclosure data from the official Turkish capital markets disclosure portal.
"""

import asyncio
import logging
from datetime import datetime
import sys
import os

# Add the parent directory to the path to import modules
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from scrapers.kap_org_scraper import KAPOrgScraper

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

logger = logging.getLogger(__name__)


async def test_kap_scraper():
    """Test the KAP scraper functionality"""
    print("🚀 Testing KAP.org.tr Scraper")
    print("=" * 50)
    
    # Initialize scraper
    scraper = KAPOrgScraper()
    
    # Configure LLM for sentiment analysis (optional)
    try:
        # Try to configure local LLM first
        scraper.configure_llm(provider_type="local")
        print("✅ Configured local LLM for sentiment analysis")
        analyze_sentiment = True
    except Exception as e:
        print(f"⚠️  Could not configure LLM: {e}")
        print("   Continuing without sentiment analysis...")
        analyze_sentiment = False
    
    try:
        # Test 1: Basic scraping without sentiment analysis
        print("\n📊 Test 1: Basic Disclosure Scraping")
        print("-" * 40)
        
        result = await scraper.scrape(
            days_back=1,  # Look back 1 day
            max_items=5,  # Limit to 5 items for testing
            analyze_sentiment=False
        )
        
        if result.get("success"):
            print(f"✅ Successfully scraped {result.get('total_disclosures', 0)} disclosures")
            print(f"   Companies: {result.get('processed_companies', 0)}")
            
            # Display sample disclosures
            disclosures = result.get('disclosures', [])
            for i, disclosure in enumerate(disclosures[:3]):  # Show first 3
                print(f"\n   📋 Disclosure {i+1}:")
                print(f"      Company: {disclosure.get('company_name', 'N/A')}")
                print(f"      Type: {disclosure.get('disclosure_type', 'N/A')}")
                print(f"      Date: {disclosure.get('disclosure_date', 'N/A')}")
                print(f"      Content length: {len(disclosure.get('content', ''))} chars")
        else:
            print(f"❌ Scraping failed: {result.get('error', 'Unknown error')}")
            return
        
        # Test 2: Scraping with company filter
        print("\n🏢 Test 2: Company-Filtered Scraping")
        print("-" * 40)
        
        # Test with some common Turkish bank names
        test_companies = ["AKBANK", "İŞ BANK", "GARANTI", "VAKIF", "HALK"]
        
        result2 = await scraper.scrape(
            days_back=2,
            company_symbols=test_companies,
            max_items=3,
            analyze_sentiment=False
        )
        
        if result2.get("success"):
            print(f"✅ Found {result2.get('total_disclosures', 0)} disclosures for filtered companies")
            
            disclosures = result2.get('disclosures', [])
            for disclosure in disclosures:
                print(f"   📋 {disclosure.get('company_name', 'N/A')}: {disclosure.get('disclosure_type', 'N/A')}")
        else:
            print(f"⚠️  No matching companies found")
        
        # Test 3: Sentiment analysis (if LLM is configured)
        if analyze_sentiment and result.get('disclosures'):
            print("\n🤖 Test 3: Sentiment Analysis")
            print("-" * 40)
            
            # Take one disclosure for sentiment analysis
            test_disclosure = result['disclosures'][0]
            content = test_disclosure.get('content', '')
            
            if content and len(content) > 100:
                print(f"   Analyzing disclosure: {test_disclosure.get('company_name', 'N/A')}")
                print(f"   Content length: {len(content)} chars")
                
                sentiment_result = await scraper._analyze_sentiment(
                    content[:2000],  # Limit content for testing
                    disclosure_id=test_disclosure.get('disclosure_id')
                )
                
                if sentiment_result:
                    print(f"   ✅ Sentiment: {sentiment_result.get('overall_sentiment', 'N/A')}")
                    print(f"      Confidence: {sentiment_result.get('confidence', 0):.2f}")
                    print(f"      Impact: {sentiment_result.get('impact_horizon', 'N/A')}")
                    print(f"      Risk Level: {sentiment_result.get('risk_level', 'N/A')}")
                else:
                    print("   ⚠️  Sentiment analysis failed")
            else:
                print("   ⚠️  Insufficient content for sentiment analysis")
        
        print("\n🎉 All tests completed!")
        
    except Exception as e:
        logger.error(f"Error during testing: {e}", exc_info=True)
        print(f"❌ Test failed: {e}")


async def main():
    """Main function to run tests"""
    try:
        await test_kap_scraper()
    except KeyboardInterrupt:
        print("\n⏹️  Tests interrupted by user")
    except Exception as e:
        print(f"❌ Unexpected error: {e}")
        logger.error(f"Unexpected error in main: {e}", exc_info=True)


if __name__ == "__main__":
    asyncio.run(main())