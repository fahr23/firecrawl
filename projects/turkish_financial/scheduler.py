"""
Scheduler for automated scraping tasks
"""
import asyncio
import logging
import time
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
    
    async def _timed_job(self, name: str, coro):
        """Run a coroutine, logging wall-clock duration and any Firecrawl API timing."""
        logger.info(f"[{name}] starting")
        t0 = time.perf_counter()
        try:
            result = await coro
            duration_s = round(time.perf_counter() - t0, 2)
            # Surface Firecrawl batch timing if present (upstream #3771)
            timing = result.get("timing") if isinstance(result, dict) else None
            if timing:
                logger.info(
                    f"[{name}] done | wall={duration_s}s"
                    f" api_duration={timing.get('api_duration_s')}s"
                    f" created_at={timing.get('created_at')}"
                    f" completed_at={timing.get('completed_at')}"
                )
            else:
                logger.info(f"[{name}] done | wall={duration_s}s")
            return result
        except Exception as e:
            duration_s = round(time.perf_counter() - t0, 2)
            logger.error(f"[{name}] failed after {duration_s}s: {e}", exc_info=True)
            raise

    async def job_scrape_kap_daily(self):
        """Daily KAP reports scraping job"""
        await self._timed_job("kap_daily", self.kap_scraper.scrape(days_back=1))

    async def job_scrape_bist_companies_weekly(self):
        """Weekly BIST companies scraping job"""
        await self._timed_job("bist_weekly", self.bist_scraper.scrape())

    async def job_scrape_tradingview_daily(self):
        """Daily TradingView sectors/industries scraping job"""
        await self._timed_job("tradingview_daily", self.tv_scraper.scrape(data_type="both"))

    async def job_scrape_commodities_4h(self):
        """Every 4 hours commodity prices scraping job"""
        from datetime import datetime, timedelta
        end_date = datetime.now().strftime("%Y%m%d")
        start_date = (datetime.now() - timedelta(days=7)).strftime("%Y%m%d")
        await self._timed_job(
            "commodities_4h",
            self.bist_scraper.scrape_commodity_prices(start_date, end_date)
        )
    
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
