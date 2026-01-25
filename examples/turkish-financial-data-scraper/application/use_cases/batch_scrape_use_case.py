"""
Batch Scrape Use Case
Single responsibility: Execute batch scraping operations
"""
import logging
from typing import List, Dict, Any

from domain.repositories.kap_report_repository import IKAPReportRepository
from utils.batch_job_manager import BatchJobManager, JobStatus

logger = logging.getLogger(__name__)


class BatchScrapeUseCase:
    """
    Use case for batch scraping operations
    
    Single Responsibility: Coordinate batch scraping workflow
    """
    
    def __init__(
        self,
        report_repository: IKAPReportRepository,
        job_manager: BatchJobManager,
        scraper_factory: callable  # Factory function to create scrapers
    ):
        """
        Initialize use case
        
        Args:
            report_repository: Repository for saving reports
            job_manager: Job manager for tracking batch jobs
            scraper_factory: Factory function to create scraper instances
        """
        self._report_repository = report_repository
        self._job_manager = job_manager
        self._scraper_factory = scraper_factory
    
    async def execute(
        self,
        urls: List[str],
        formats: List[str],
        job_id: str
    ) -> None:
        """
        Execute batch scraping
        
        Args:
            urls: List of URLs to scrape
            formats: Output formats
            job_id: Job ID for tracking
        """
        self._job_manager.update_job_status(
            job_id,
            JobStatus.RUNNING,
            total=len(urls)
        )
        
        results = []
        scraper = self._scraper_factory()
        
        for i, url in enumerate(urls):
            try:
                # Scrape URL
                result = await scraper.scrape_url(url, formats=formats)
                results.append(result)
                
                # Update progress
                self._job_manager.update_job_status(
                    job_id,
                    JobStatus.RUNNING,
                    progress=i + 1
                )
                
                # Save to repository if successful
                if result.get("success") and result.get("data"):
                    # Convert to domain entity and save
                    # This would need proper mapping from scraper result to KAPReport
                    pass
                
            except Exception as e:
                logger.error(f"Error scraping {url}: {e}")
                results.append({"url": url, "success": False, "error": str(e)})
        
        # Mark job as completed
        self._job_manager.update_job_status(
            job_id,
            JobStatus.COMPLETED,
            result={
                "total": len(results),
                "successful": sum(1 for r in results if r.get("success"))
            }
        )
