"""
Main entry point for Turkish Financial Data Scraper
"""
import asyncio
import argparse
import logging
import sys
from datetime import datetime, timedelta

from config import config
from database.db_manager import DatabaseManager
from scrapers.kap_scraper import KAPScraper
from scrapers.bloomberg_ht_kap_scraper import BloombergHTKAPScraper
from scrapers.bist_scraper import BISTScraper
from scrapers.tradingview_scraper import TradingViewScraper
from utils.logger import setup_logging


async def scrape_kap(db_manager: DatabaseManager, args):
    """Scrape KAP reports from Bloomberg HT"""
    logger = logging.getLogger(__name__)
    logger.info("Starting KAP scraper (Bloomberg HT)")
    
    # Use Bloomberg HT scraper (more reliable than KAP API)
    from scrapers.bloomberg_ht_kap_scraper import BloombergHTKAPScraper
    import os
    
    scraper = BloombergHTKAPScraper(db_manager=db_manager)
    
    # Configure LLM for sentiment analysis if API key is available
    gemini_key = os.getenv("GEMINI_API_KEY")
    if gemini_key:
        try:
            scraper.configure_llm(
                provider_type="gemini",
                api_key=gemini_key
            )
            logger.info("✅ LLM configured for sentiment analysis (Gemini)")
            print("✅ LLM configured - sentiment analysis will be performed")
        except Exception as e:
            logger.warning(f"Failed to configure LLM: {e}")
            print(f"⚠️  LLM configuration failed: {e}")
    else:
        logger.info("LLM not configured - sentiment analysis will be skipped")
        print("⚠️  GEMINI_API_KEY not set - sentiment analysis will be skipped")
    
    # Scrape with sentiment analysis if LLM is configured
    analyze_sentiment = scraper.llm_analyzer is not None
    if analyze_sentiment:
        print("🤖 Sentiment analysis: ENABLED")
    else:
        print("🤖 Sentiment analysis: DISABLED (no LLM configured)")
    
    result = await scraper.scrape(
        days_back=args.days,
        analyze_sentiment=analyze_sentiment
    )
    
    logger.info(f"KAP scraping completed: {result.get('total_companies')} companies")
    if analyze_sentiment:
        logger.info(f"Sentiment analyses: {result.get('sentiment_analyses', 0)}")
    return result


async def scrape_bist(db_manager: DatabaseManager, args):
    """Scrape BIST companies"""
    logger = logging.getLogger(__name__)
    logger.info("Starting BIST scraper")
    
    scraper = BISTScraper(db_manager=db_manager)
    
    if args.data_type == "companies":
        result = await scraper.scrape()
    elif args.data_type == "indices":
        result = await scraper.scrape_indices()
    elif args.data_type == "commodities":
        end_date = datetime.now().strftime("%Y%m%d")
        start_date = (datetime.now() - timedelta(days=7)).strftime("%Y%m%d")
        result = await scraper.scrape_commodity_prices(start_date, end_date)
    else:
        result = await scraper.scrape()
    
    logger.info(f"BIST scraping completed")
    return result


async def scrape_tradingview(db_manager: DatabaseManager, args):
    """Scrape TradingView data"""
    logger = logging.getLogger(__name__)
    logger.info("Starting TradingView scraper")
    
    scraper = TradingViewScraper(db_manager=db_manager)
    result = await scraper.scrape(data_type=args.data_type or "both")
    
    logger.info(f"TradingView scraping completed")
    return result


async def scrape_all(db_manager: DatabaseManager, args):
    """Scrape all sources"""
    logger = logging.getLogger(__name__)
    logger.info("Starting all scrapers")
    
    results = {}
    
    # KAP Reports
    try:
        kap_result = await scrape_kap(db_manager, args)
        results["kap"] = kap_result
    except Exception as e:
        logger.error(f"KAP scraper failed: {e}")
        results["kap"] = {"success": False, "error": str(e)}
    
    # BIST Companies
    try:
        bist_result = await scrape_bist(db_manager, args)
        results["bist"] = bist_result
    except Exception as e:
        logger.error(f"BIST scraper failed: {e}")
        results["bist"] = {"success": False, "error": str(e)}
    
    # TradingView
    try:
        tv_result = await scrape_tradingview(db_manager, args)
        results["tradingview"] = tv_result
    except Exception as e:
        logger.error(f"TradingView scraper failed: {e}")
        results["tradingview"] = {"success": False, "error": str(e)}
    
    logger.info("All scrapers completed")
    return results


async def main():
    """Main entry point"""
    parser = argparse.ArgumentParser(
        description="Turkish Financial Data Scraper using Firecrawl"
    )
    
    parser.add_argument(
        "--scraper",
        choices=["kap", "bist", "tradingview", "all"],
        default="all",
        help="Which scraper to run"
    )
    
    parser.add_argument(
        "--days",
        type=int,
        default=7,
        help="Number of days to look back for KAP reports"
    )
    
    parser.add_argument(
        "--data-type",
        type=str,
        help="Data type to scrape (varies by scraper)"
    )
    
    parser.add_argument(
        "--log-level",
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
        default="INFO",
        help="Logging level"
    )
    
    args = parser.parse_args()
    
    # Setup logging
    setup_logging(level=args.log_level)
    logger = logging.getLogger(__name__)
    
    # Validate config
    try:
        config.validate()
    except ValueError as e:
        logger.error(f"Configuration error: {e}")
        sys.exit(1)
    
    # Initialize database
    try:
        db_manager = DatabaseManager()
        logger.info("Database initialized")
    except Exception as e:
        logger.error(f"Failed to initialize database: {e}")
        sys.exit(1)
    
    # Run selected scraper
    try:
        if args.scraper == "kap":
            result = await scrape_kap(db_manager, args)
        elif args.scraper == "bist":
            result = await scrape_bist(db_manager, args)
        elif args.scraper == "tradingview":
            result = await scrape_tradingview(db_manager, args)
        else:
            result = await scrape_all(db_manager, args)
        
        # Print results
        logger.info("=" * 60)
        logger.info("SCRAPING RESULTS")
        logger.info("=" * 60)
        
        if isinstance(result, dict):
            for key, value in result.items():
                if isinstance(value, dict) and value.get("success"):
                    logger.info(f"{key.upper()}: Success")
                else:
                    logger.info(f"{key.upper()}: {value}")
        
        logger.info("=" * 60)
        
    except Exception as e:
        logger.error(f"Scraping failed: {e}", exc_info=True)
        sys.exit(1)
    
    finally:
        # Cleanup
        db_manager.close_all()
        logger.info("Cleanup completed")


if __name__ == "__main__":
    asyncio.run(main())
