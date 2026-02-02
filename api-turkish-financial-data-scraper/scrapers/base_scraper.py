"""
Base scraper class using Firecrawl
"""
import asyncio
import logging
from typing import Dict, Any, Optional, List, Callable
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
            
            # Handle new Document object format
            data = {}
            if hasattr(result, 'html'):
                data['html'] = result.html
            if hasattr(result, 'markdown'):
                data['markdown'] = result.markdown
            if hasattr(result, 'metadata'):
                data['metadata'] = result.metadata
            
            # Fallback for dict format (backward compatibility)
            if not data and isinstance(result, dict):
                data = result
            
            logger.info(f"Successfully scraped: {url}")
            return {
                "success": True,
                "url": url,
                "data": data,
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
    
    async def scrape_paginated_parallel(
        self,
        base_url: str,
        pagination_schema: Dict[str, Any],
        extraction_schema: Dict[str, Any],
        max_pages: Optional[int] = None,
        concurrency: int = 5
    ) -> List[Dict[str, Any]]:
        """
        Scrape paginated content in parallel
        
        Args:
            base_url: Starting URL
            pagination_schema: Schema to extract pagination links
            extraction_schema: Schema to extract data from each page
            max_pages: Maximum number of pages to scrape
            concurrency: Number of concurrent requests
            
        Returns:
            List of extracted items from all pages
        """
        try:
            # Step 1: Extract pagination links
            logger.info(f"Extracting pagination links from {base_url}")
            pagination_result = await self.extract_with_schema(
                base_url,
                schema=pagination_schema,
                prompt="Extract all pagination links from this page"
            )
            
            if not pagination_result or not pagination_result.get("success"):
                logger.warning("Failed to extract pagination links, scraping base URL only")
                # Fallback to single page
                result = await self.extract_with_schema(
                    base_url,
                    schema=extraction_schema
                )
                return result.get("data", {}).get("items", []) if result.get("success") else []
            
            # Get page links
            page_links = pagination_result.get("data", {}).get("page_links", [])
            if not page_links:
                logger.warning("No pagination links found")
                page_links = [base_url]
            
            # Limit pages if specified
            if max_pages:
                page_links = page_links[:max_pages]
            
            logger.info(f"Found {len(page_links)} pages to scrape")
            
            # Step 2: Scrape all pages in parallel with concurrency limit
            semaphore = asyncio.Semaphore(concurrency)
            
            async def scrape_page(link: str) -> List[Dict[str, Any]]:
                async with semaphore:
                    try:
                        result = await self.extract_with_schema(
                            link,
                            schema=extraction_schema
                        )
                        if result.get("success"):
                            return result.get("data", {}).get("items", [])
                        return []
                    except Exception as e:
                        logger.error(f"Error scraping page {link}: {e}")
                        return []
            
            # Create tasks for all pages
            tasks = [scrape_page(link) for link in page_links]
            
            # Execute in parallel
            results = await asyncio.gather(*tasks, return_exceptions=True)
            
            # Flatten results and filter exceptions
            all_items = []
            for result in results:
                if isinstance(result, Exception):
                    logger.error(f"Task raised exception: {result}")
                elif isinstance(result, list):
                    all_items.extend(result)
            
            logger.info(f"Scraped {len(all_items)} items from {len(page_links)} pages")
            return all_items
            
        except Exception as e:
            logger.error(f"Error in parallel pagination scraping: {e}", exc_info=True)
            return []
    
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
