"""
Base scraper class using Firecrawl
"""
import asyncio
import logging
from typing import Dict, Any, Optional, List
from abc import ABC, abstractmethod
from firecrawl import FirecrawlApp
from config import config

logger = logging.getLogger(__name__)


class BaseScraper(ABC):
    """Base scraper class with Firecrawl integration"""
    
    def __init__(self, db_manager=None):
        """
        Initialize base scraper
        
        Args:
            db_manager: Database manager instance
        """
        self.db_manager = db_manager
        
        # Initialize Firecrawl with optional base_url for self-hosted
        firecrawl_kwargs = {"api_key": config.firecrawl.api_key}
        if config.firecrawl.base_url:
            firecrawl_kwargs["api_url"] = config.firecrawl.base_url
        
        self.firecrawl = FirecrawlApp(**firecrawl_kwargs)
        self.config = config
        
        logger.info(f"Initialized {self.__class__.__name__}")
    
    async def scrape_url(
        self,
        url: str,
        wait_for: Optional[int] = None,
        formats: Optional[List[str]] = None,
        timeout: Optional[int] = None,
        **kwargs
    ) -> Dict[str, Any]:
        """
        Scrape a single URL using Firecrawl
        
        Args:
            url: URL to scrape
            wait_for: Time to wait for JS rendering (ms)
            formats: Output formats (markdown, html, etc.)
            timeout: Request timeout (ms)
            **kwargs: Additional Firecrawl parameters
            
        Returns:
            Scraped data
        """
        wait_for = wait_for or config.firecrawl.wait_for
        formats = formats or config.firecrawl.formats
        timeout = timeout or config.firecrawl.timeout
        
        try:
            logger.info(f"Scraping URL: {url}")
            
            result = self.firecrawl.scrape(
                url,
                formats=formats,
                wait_for=wait_for,
                timeout=timeout,
                **kwargs
            )
            
            logger.info(f"Successfully scraped: {url}")
            return {
                "success": True,
                "url": url,
                "data": result,
                "scraper": self.__class__.__name__
            }
            
        except Exception as e:
            logger.error(f"Error scraping {url}: {e}")
            return {
                "success": False,
                "url": url,
                "error": str(e),
                "scraper": self.__class__.__name__
            }
    
    async def crawl_website(
        self,
        start_url: str,
        limit: int = 100,
        include_patterns: Optional[List[str]] = None,
        exclude_patterns: Optional[List[str]] = None,
        **kwargs
    ) -> Dict[str, Any]:
        """
        Crawl a website starting from a URL
        
        Args:
            start_url: Starting URL
            limit: Maximum number of pages to crawl
            include_patterns: URL patterns to include
            exclude_patterns: URL patterns to exclude
            **kwargs: Additional Firecrawl parameters
            
        Returns:
            Crawled data
        """
        try:
            logger.info(f"Crawling website: {start_url} (limit: {limit})")
            
            # Build scrape options
            from firecrawl.v2.types import ScrapeOptions
            scrape_options = ScrapeOptions(
                formats=config.firecrawl.formats,
                wait_for=config.firecrawl.wait_for,
            )
            
            result = self.firecrawl.crawl(
                start_url,
                limit=limit,
                include_paths=include_patterns,
                exclude_paths=exclude_patterns,
                scrape_options=scrape_options,
                poll_interval=5,
                **kwargs
            )
            
            logger.info(f"Successfully crawled: {start_url}")
            return {
                "success": True,
                "url": start_url,
                "data": result,
                "scraper": self.__class__.__name__
            }
            
        except Exception as e:
            logger.error(f"Error crawling {start_url}: {e}")
            return {
                "success": False,
                "url": start_url,
                "error": str(e),
                "scraper": self.__class__.__name__
            }
    
    async def extract_with_schema(
        self,
        url: str,
        schema: Dict[str, Any],
        prompt: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Extract structured data from URL using LLM
        
        Args:
            url: URL to extract from
            schema: JSON schema for extraction
            prompt: Optional extraction prompt
            
        Returns:
            Extracted structured data
        """
        try:
            logger.info(f"Extracting data from: {url}")
            
            # Ensure we don't wait forever; respect configured timeout
            # firecrawl-py extract supports poll_interval (seconds) and timeout (seconds)
            poll_interval = 3
            try:
                timeout_s = max(10, int(self.config.firecrawl.timeout / 1000))
            except Exception:
                timeout_s = 60

            result = self.firecrawl.extract(
                urls=[url],
                schema=schema,
                prompt=prompt,
                poll_interval=poll_interval,
                timeout=timeout_s,
            )
            
            logger.info(f"Successfully extracted data from: {url}")
            return {
                "success": True,
                "url": url,
                "data": result.data if hasattr(result, 'data') else result,
                "scraper": self.__class__.__name__
            }
            
        except Exception as e:
            logger.error(f"Error extracting from {url}: {e}")
            return {
                "success": False,
                "url": url,
                "error": str(e),
                "scraper": self.__class__.__name__
            }
    
    async def retry_with_backoff(
        self,
        func,
        *args,
        max_retries: Optional[int] = None,
        **kwargs
    ):
        """
        Retry a function with exponential backoff
        
        Args:
            func: Function to retry
            max_retries: Maximum number of retries
            *args, **kwargs: Function arguments
            
        Returns:
            Function result
        """
        max_retries = max_retries or config.firecrawl.max_retries
        
        for attempt in range(max_retries):
            try:
                result = await func(*args, **kwargs)
                if result.get("success"):
                    return result
                    
                if attempt < max_retries - 1:
                    wait_time = config.firecrawl.retry_backoff ** attempt
                    logger.warning(
                        f"Attempt {attempt + 1} failed, "
                        f"retrying in {wait_time}s..."
                    )
                    await asyncio.sleep(wait_time)
                    
            except Exception as e:
                if attempt < max_retries - 1:
                    wait_time = config.firecrawl.retry_backoff ** attempt
                    logger.warning(
                        f"Attempt {attempt + 1} raised exception: {e}, "
                        f"retrying in {wait_time}s..."
                    )
                    await asyncio.sleep(wait_time)
                else:
                    raise
        
        return {"success": False, "error": "Max retries exceeded"}
    
    @abstractmethod
    async def scrape(self, **kwargs) -> Dict[str, Any]:
        """
        Main scraping method to be implemented by subclasses
        
        Args:
            **kwargs: Scraper-specific parameters
            
        Returns:
            Scraped data
        """
        pass
    
    def save_to_db(self, data: Dict[str, Any], table_name: str):
        """
        Save scraped data to database
        
        Args:
            data: Data to save
            table_name: Target table name
        """
        if not self.db_manager:
            logger.warning("No database manager configured")
            return
        
        try:
            self.db_manager.insert_data(table_name, data)
            logger.info(f"Saved data to {table_name}")
        except Exception as e:
            logger.error(f"Error saving to database: {e}")
