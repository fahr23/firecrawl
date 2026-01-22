"""
Scheduler for automated scraping tasks
"""
import asyncio
import logging
from datetime import datetime
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger

from config import config
from database.db_manager import DatabaseManager
from scrapers.kap_scraper import KAPScraper
from scrapers.bist_scraper import BISTScraper
from scrapers.tradingview_scraper import TradingViewScraper
from utils.logger import setup_logging

logger = logging.getLogger(__name__)


class ScraperScheduler:
    """Scheduler for running scrapers at specified intervals"""
    
    def __init__(self, db_manager: DatabaseManager):
        """
        Initialize scheduler
        
        Args:
            db_manager: Database manager instance
        """
        self.db_manager = db_manager
        self.scheduler = AsyncIOScheduler()
        self.kap_scraper = KAPScraper(db_manager=db_manager)
        self.bist_scraper = BISTScraper(db_manager=db_manager)
        self.tv_scraper = TradingViewScraper(db_manager=db_manager)
    
    async def job_scrape_kap_daily(self):
        """Daily KAP reports scraping job"""
        logger.info("Starting scheduled KAP scraping")
        try:
            result = await self.kap_scraper.scrape(days_back=1)
            logger.info(f"KAP daily scraping completed: {result}")
        except Exception as e:
            logger.error(f"KAP daily scraping failed: {e}", exc_info=True)
    
    async def job_scrape_bist_companies_weekly(self):
        """Weekly BIST companies scraping job"""
        logger.info("Starting scheduled BIST companies scraping")
        try:
            result = await self.bist_scraper.scrape()
            logger.info(f"BIST companies scraping completed: {result}")
        except Exception as e:
            logger.error(f"BIST scraping failed: {e}", exc_info=True)
    
    async def job_scrape_tradingview_daily(self):
        """Daily TradingView sectors/industries scraping job"""
        logger.info("Starting scheduled TradingView scraping")
        try:
            result = await self.tv_scraper.scrape(data_type="both")
            logger.info(f"TradingView scraping completed: {result}")
        except Exception as e:
            logger.error(f"TradingView scraping failed: {e}", exc_info=True)
    
    async def job_scrape_commodities_4h(self):
        """Every 4 hours commodity prices scraping job"""
        logger.info("Starting scheduled commodity prices scraping")
        try:
            from datetime import datetime, timedelta
            end_date = datetime.now().strftime("%Y%m%d")
            start_date = (
                datetime.now() - timedelta(days=7)
            ).strftime("%Y%m%d")
            
            result = await self.bist_scraper.scrape_commodity_prices(
                start_date,
                end_date
            )
            logger.info(f"Commodity prices scraping completed: {result}")
        except Exception as e:
            logger.error(f"Commodity scraping failed: {e}", exc_info=True)
    
    def setup_jobs(self):
        """Setup all scheduled jobs"""
        # KAP reports - Daily at 08:00
        self.scheduler.add_job(
            self.job_scrape_kap_daily,
            trigger=CronTrigger(hour=8, minute=0),
            id="kap_daily_08am",
            name="KAP Daily Reports (08:00)",
            replace_existing=True
        )
        logger.info("Scheduled: KAP daily reports at 08:00")
        
        # BIST companies - Weekly on Monday at 09:00
        self.scheduler.add_job(
            self.job_scrape_bist_companies_weekly,
            trigger=CronTrigger(day_of_week='mon', hour=9, minute=0),
            id="bist_companies_weekly",
            name="BIST Companies Weekly (Monday 09:00)",
            replace_existing=True
        )
        logger.info("Scheduled: BIST companies weekly on Monday at 09:00")
        
        # TradingView - Daily at 09:30
        self.scheduler.add_job(
            self.job_scrape_tradingview_daily,
            trigger=CronTrigger(hour=9, minute=30),
            id="tradingview_daily_09_30",
            name="TradingView Daily (09:30)",
            replace_existing=True
        )
        logger.info("Scheduled: TradingView daily at 09:30")
        
        # Commodity prices - Every 4 hours
        self.scheduler.add_job(
            self.job_scrape_commodities_4h,
            trigger=IntervalTrigger(hours=4),
            id="commodities_4h",
            name="Commodity Prices Every 4 Hours",
            replace_existing=True
        )
        logger.info("Scheduled: Commodity prices every 4 hours")
    
    def start(self):
        """Start the scheduler"""
        self.setup_jobs()
        self.scheduler.start()
        logger.info("Scheduler started")
        
        # Print job schedule
        jobs = self.scheduler.get_jobs()
        logger.info(f"Total scheduled jobs: {len(jobs)}")
        for job in jobs:
            logger.info(f"  - {job.name}: {job.trigger}")
    
    def stop(self):
        """Stop the scheduler"""
        self.scheduler.shutdown()
        logger.info("Scheduler stopped")


async def main():
    """Main scheduler entry point"""
    # Setup logging
    setup_logging(level="INFO")
    logger.info("Turkish Financial Data Scraper - Scheduler")
    
    # Validate config
    try:
        config.validate()
    except ValueError as e:
        logger.error(f"Configuration error: {e}")
        return
    
    # Initialize database
    try:
        db_manager = DatabaseManager()
        logger.info("Database initialized")
    except Exception as e:
        logger.error(f"Failed to initialize database: {e}")
        return
    
    # Create and start scheduler
    scheduler = ScraperScheduler(db_manager)
    scheduler.start()
    
    try:
        # Keep running
        while True:
            await asyncio.sleep(60)
    except KeyboardInterrupt:
        logger.info("Received shutdown signal")
    finally:
        scheduler.stop()
        db_manager.close_all()
        logger.info("Shutdown complete")


if __name__ == "__main__":
    asyncio.run(main())
