"""
Base scraper class using Firecrawl
"""
import asyncio
import logging
import time
from typing import Dict, Any, Optional, List, Callable, Union
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

    def _normalize_document(self, result: Any) -> Dict[str, Any]:
        """Normalize Firecrawl document-like responses across SDK versions."""
        if isinstance(result, dict):
            return dict(result)

        data: Dict[str, Any] = {}
        for attr in ("html", "markdown", "metadata", "links", "summary", "json", "videos"):
            value = getattr(result, attr, None)
            if value is not None:
                data[attr] = value

        raw_html = getattr(result, "rawHtml", None)
        if raw_html is not None:
            data["rawHtml"] = raw_html

        action_results = getattr(result, "actions", None)
        if action_results is not None:
            data["action_results"] = action_results

        return data

    def _normalize_links(self, result: Any) -> List[str]:
        """Normalize map() results into a plain list of URLs."""
        raw_links = result.links if hasattr(result, "links") else (result or [])
        links: List[str] = []
        for item in raw_links:
            if isinstance(item, str):
                links.append(item)
            elif isinstance(item, dict) and item.get("url"):
                links.append(item["url"])
            elif hasattr(item, "url") and getattr(item, "url"):
                links.append(item.url)
        return links

    def _normalize_search_results(self, result: Any) -> List[Any]:
        """Flatten v2 grouped search results while tolerating older SDK responses."""
        data = getattr(result, "data", None)
        if isinstance(data, list):
            return list(data)
        if isinstance(result, dict):
            return list(result.get("data") or result.get("results") or [])

        items: List[Any] = []
        for attr in ("web", "news", "images"):
            group = getattr(result, attr, None)
            if group:
                items.extend(group)
        return items

    def _build_v2_scrape_kwargs(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Translate legacy params dicts into Firecrawl v2 keyword arguments."""
        kwargs: Dict[str, Any] = {}
        mapping = {
            "waitFor": "wait_for",
            "onlyMainContent": "only_main_content",
            "skipTLSVerification": "skip_tls_verification",
            "removeBase64Images": "remove_base64_images",
            "fastMode": "fast_mode",
            "useMock": "use_mock",
            "blockAds": "block_ads",
            "maxAge": "max_age",
            "storeInCache": "store_in_cache",
        }
        for key, value in params.items():
            if value is None:
                continue
            kwargs[mapping.get(key, key)] = value
        return kwargs

    def _call_scrape(self, url: str, params: Dict[str, Any]) -> Any:
        """Call the installed Firecrawl scrape method with v2-first compatibility."""
        scrape = getattr(self.firecrawl, "scrape", None)
        if callable(scrape):
            return scrape(url, **self._build_v2_scrape_kwargs(params))

        scrape_url = getattr(self.firecrawl, "scrape_url", None)
        if callable(scrape_url):
            return scrape_url(url, params=params)

        raise AttributeError("Firecrawl client does not expose scrape() or scrape_url()")
    
    async def scrape_url(
        self,
        url: str,
        wait_for: Optional[int] = None,
        formats: Optional[List[str]] = None,
        timeout: Optional[int] = None,
        proxy: str = "auto",
        only_main_content: bool = True,
        location: Optional[Dict[str, Any]] = None,
        mobile: bool = False,
        include_video: bool = False,
        **kwargs
    ) -> Dict[str, Any]:
        """
        Scrape a single URL using Firecrawl

        Args:
            url: URL to scrape
            wait_for: Time to wait for JS rendering (ms)
            formats: Output formats (markdown, html, etc.)
            timeout: Request timeout (ms)
            proxy: Proxy type – 'basic', 'stealth', 'enhanced', or 'auto'
            only_main_content: Strip nav/footer/ads for cleaner output
            location: Geolocation dict, e.g. {"country": "TR"}
            mobile: Emulate a mobile device
            **kwargs: Additional Firecrawl parameters

        Returns:
            Scraped data
        """
        wait_for = wait_for or config.firecrawl.wait_for
        formats = list(formats or config.firecrawl.formats)
        if include_video and "video" not in formats:
            formats.append("video")
        timeout = timeout or config.firecrawl.timeout

        params: Dict[str, Any] = {
            "formats": formats,
            "waitFor": wait_for,
            "timeout": timeout,
            "onlyMainContent": only_main_content,
            "proxy": proxy,
            "mobile": mobile,
            **kwargs,
        }
        if location:
            params["location"] = location

        try:
            logger.info(f"Scraping URL: {url}")
            result = self._call_scrape(url, params)
            data = self._normalize_document(result)

            logger.info(f"Successfully scraped: {url}")
            return {
                "success": True,
                "url": url,
                "data": data,
                "scraper": self.__class__.__name__,
            }

        except Exception as e:
            logger.error(f"Error scraping {url}: {e}")
            return {
                "success": False,
                "url": url,
                "error": str(e),
                "scraper": self.__class__.__name__,
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

            t0 = time.perf_counter()
            result = self.firecrawl.crawl(
                start_url,
                limit=limit,
                include_paths=include_patterns,
                exclude_paths=exclude_patterns,
                scrape_options=scrape_options,
                poll_interval=5,
                **kwargs
            )
            duration_s = round(time.perf_counter() - t0, 2)

            # Extract API-level timing when the SDK exposes it (upstream #3771)
            created_at = getattr(result, "created_at", None)
            completed_at = getattr(result, "completed_at", None)
            api_duration = getattr(result, "duration", None)

            logger.info(
                f"Successfully crawled: {start_url} | wall={duration_s}s"
                + (f" api_duration={api_duration}s" if api_duration else "")
            )
            return {
                "success": True,
                "url": start_url,
                "data": result,
                "timing": {
                    "wall_duration_s": duration_s,
                    "created_at": str(created_at) if created_at else None,
                    "completed_at": str(completed_at) if completed_at else None,
                    "api_duration_s": api_duration,
                },
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
    
    # ------------------------------------------------------------------
    # NEW: map() – discover all URLs on a website
    # ------------------------------------------------------------------

    async def map_url(
        self,
        url: str,
        search: Optional[str] = None,
        limit: int = 5000,
        sitemap_only: bool = False,
        include_subdomains: bool = False,
    ) -> Dict[str, Any]:
        """
        Use Firecrawl map() to discover all URLs under a domain.

        Args:
            url: Base URL to map
            search: Optional search query to filter discovered links
            limit: Max links to return (up to 30 000)
            sitemap_only: Return only sitemap.xml links
            include_subdomains: Include subdomain links

        Returns:
            Dict with 'links' list and metadata
        """
        try:
            logger.info(f"Mapping URL: {url} (search={search!r}, limit={limit})")
            map_call = getattr(self.firecrawl, "map", None)
            if callable(map_call):
                result = map_call(
                    url,
                    limit=limit,
                    search=search,
                    include_subdomains=include_subdomains,
                    sitemap="only" if sitemap_only else None,
                )
            else:
                params: Dict[str, Any] = {
                    "limit": limit,
                    "sitemapOnly": sitemap_only,
                    "includeSubdomains": include_subdomains,
                }
                if search:
                    params["search"] = search
                result = self.firecrawl.map_url(url, params=params)

            links = self._normalize_links(result)
            logger.info(f"Map found {len(links)} links for {url}")
            return {
                "success": True,
                "url": url,
                "links": links,
                "total": len(links),
                "scraper": self.__class__.__name__,
            }
        except Exception as e:
            logger.error(f"Error mapping {url}: {e}")
            return {
                "success": False,
                "url": url,
                "links": [],
                "error": str(e),
                "scraper": self.__class__.__name__,
            }

    # ------------------------------------------------------------------
    # NEW: batch_scrape() – scrape many URLs in one job
    # ------------------------------------------------------------------

    async def batch_scrape_urls(
        self,
        urls: List[str],
        formats: Optional[List[str]] = None,
        wait_for: Optional[int] = None,
        proxy: str = "auto",
        only_main_content: bool = True,
        poll_interval: int = 5,
        max_concurrency: Optional[int] = None,
    ) -> Dict[str, Any]:
        """
        Use Firecrawl batch_scrape() to scrape multiple URLs in a single job.

        Significantly more efficient than scraping one-by-one for 5+ URLs.
        max_concurrency defaults to config.firecrawl.max_batch_concurrency (NuQ #3758).

        Args:
            urls: List of URLs to scrape
            formats: Output formats (default: markdown)
            wait_for: Wait time for JS rendering (ms)
            proxy: Proxy type – 'basic', 'stealth', 'enhanced', or 'auto'
            only_main_content: Strip nav/footer/ads
            poll_interval: Seconds between status polls
            max_concurrency: Max concurrent scrapes per job (NuQ server enforced)

        Returns:
            Dict with 'data' list and 'timing' block (wall_duration_s, api timing fields)
        """
        formats = formats or config.firecrawl.formats
        wait_for = wait_for or config.firecrawl.wait_for
        # Use config default so NuQ's server-side concurrency cap is respected
        if max_concurrency is None:
            max_concurrency = getattr(config.firecrawl, "max_batch_concurrency", None)

        scrape_options: Dict[str, Any] = {
            "formats": formats,
            "waitFor": wait_for,
            "onlyMainContent": only_main_content,
            "proxy": proxy,
        }

        kwargs: Dict[str, Any] = {
            "poll_interval": poll_interval,
        }
        if max_concurrency is not None:
            kwargs["max_concurrency"] = max_concurrency

        max_retries = getattr(config.firecrawl, "max_retries", 3)
        for attempt in range(max_retries):
            try:
                logger.info(f"Batch scraping {len(urls)} URLs (concurrency={max_concurrency})")
                t0 = time.perf_counter()
                batch_scrape = getattr(self.firecrawl, "batch_scrape", None)
                if callable(batch_scrape):
                    result = batch_scrape(urls, **self._build_v2_scrape_kwargs(scrape_options), **kwargs)
                    pages = result.data if hasattr(result, "data") else []
                else:
                    kwargs["scrape_options"] = scrape_options
                    async_batch_scrape = getattr(self.firecrawl, "async_batch_scrape_urls", None)
                    if callable(async_batch_scrape):
                        result = async_batch_scrape(urls, **kwargs)
                        status = result.wait_for_completion(poll_interval=poll_interval)
                        pages = status.data if hasattr(status, "data") else []
                        result = status
                    else:
                        legacy_batch_scrape = getattr(self.firecrawl, "batch_scrape_urls", None)
                        if not callable(legacy_batch_scrape):
                            raise AttributeError("Firecrawl client does not expose batch_scrape() or batch_scrape_urls()")
                        result = legacy_batch_scrape(urls, **kwargs)
                        pages = result.data if hasattr(result, "data") else []

                duration_s = round(time.perf_counter() - t0, 2)

                # Extract API-level timing fields added in upstream #3771
                created_at = getattr(result, "created_at", None)
                completed_at = getattr(result, "completed_at", None)
                api_duration = getattr(result, "duration", None)

                logger.info(
                    f"Batch scrape completed: {len(pages)} pages | wall={duration_s}s"
                    + (f" api_duration={api_duration}s" if api_duration else "")
                )
                return {
                    "success": True,
                    "total": len(pages),
                    "data": pages,
                    "timing": {
                        "wall_duration_s": duration_s,
                        "created_at": str(created_at) if created_at else None,
                        "completed_at": str(completed_at) if completed_at else None,
                        "api_duration_s": api_duration,
                    },
                    "scraper": self.__class__.__name__,
                }
            except Exception as e:
                # Retry on concurrency/rate-limit errors (HTTP 429) from NuQ queue
                err_str = str(e).lower()
                if attempt < max_retries - 1 and ("429" in err_str or "rate" in err_str or "concurren" in err_str):
                    wait = config.firecrawl.retry_backoff ** attempt
                    logger.warning(f"Batch scrape rate-limited (attempt {attempt+1}), retrying in {wait}s: {e}")
                    await asyncio.sleep(wait)
                    continue
                logger.error(f"Batch scrape failed: {e}")
                return {
                    "success": False,
                    "error": str(e),
                    "data": [],
                    "scraper": self.__class__.__name__,
                }

    # ------------------------------------------------------------------
    # NEW: search() – web search + optional scrape of results
    # ------------------------------------------------------------------

    async def search_web(
        self,
        query: str,
        limit: int = 10,
        lang: str = "tr",
        country: str = "TR",
        tbs: Optional[str] = None,
        scrape_results: bool = False,
        scrape_formats: Optional[List[str]] = None,
        only_main_content: bool = True,
    ) -> Dict[str, Any]:
        """
        Use Firecrawl search() to run a web search and optionally scrape results.

        Args:
            query: Search query string
            limit: Max results (up to 100)
            lang: Language code (default 'tr' for Turkish)
            country: Country code (default 'TR')
            tbs: Time-based filter ('qdr:d' past day, 'qdr:w' past week, etc.)
            scrape_results: Whether to scrape the returned URLs
            scrape_formats: Formats to use when scraping results
            only_main_content: Strip nav/footer when scraping

        Returns:
            Dict with 'results' list and optional scraped content
        """
        params: Dict[str, Any] = {
            "limit": limit,
            "lang": lang,
            "country": country,
        }
        if tbs:
            params["tbs"] = tbs
        if scrape_results:
            params["scrape_options"] = {
                "formats": scrape_formats or ["markdown"],
                "only_main_content": only_main_content,
            }

        try:
            logger.info(f"Searching: {query!r} (lang={lang}, country={country})")
            search_call = getattr(self.firecrawl, "search", None)
            if not callable(search_call):
                raise AttributeError("Firecrawl client does not expose search()")

            result = search_call(
                query,
                limit=params["limit"],
                tbs=params.get("tbs"),
                location=country or lang,
                scrape_options=params.get("scrape_options"),
            )
            items = self._normalize_search_results(result)
            logger.info(f"Search returned {len(items)} results")
            return {
                "success": True,
                "query": query,
                "total": len(items),
                "results": items,
                "scraper": self.__class__.__name__,
            }
        except Exception as e:
            logger.error(f"Search failed for {query!r}: {e}")
            return {
                "success": False,
                "query": query,
                "error": str(e),
                "results": [],
                "scraper": self.__class__.__name__,
            }

    # ------------------------------------------------------------------
    # NEW: scrape_with_actions() – interactive browser automation
    # ------------------------------------------------------------------

    async def scrape_with_actions(
        self,
        url: str,
        actions: List[Dict[str, Any]],
        formats: Optional[List[str]] = None,
        wait_for: Optional[int] = None,
        proxy: str = "stealth",
        location: Optional[Dict[str, Any]] = None,
        only_main_content: bool = True,
        mobile: bool = False,
    ) -> Dict[str, Any]:
        """
        Scrape a page after executing browser actions (click, scroll, write, etc.).

        Useful for SPAs (like KAP) that load content dynamically.

        Args:
            url: URL to scrape
            actions: List of action dicts, e.g.:
                [{"type": "wait", "milliseconds": 2000},
                 {"type": "click", "selector": "#loadMore"},
                 {"type": "scroll", "direction": "down"},
                 {"type": "scrape"}]
            formats: Output formats
            wait_for: Initial wait time (ms)
            proxy: Proxy type ('stealth' recommended for bot-protected sites)
            location: Geolocation, e.g. {"country": "TR", "languages": ["tr-TR"]}
            only_main_content: Strip nav/footer/ads
            mobile: Emulate mobile device

        Returns:
            Dict with scraped content after actions
        """
        formats = formats or ["markdown", "html"]
        wait_for = wait_for or config.firecrawl.wait_for

        scrape_params: Dict[str, Any] = {
            "formats": formats,
            "actions": actions,
            "waitFor": wait_for,
            "onlyMainContent": only_main_content,
            "proxy": proxy,
            "mobile": mobile,
        }
        if location:
            scrape_params["location"] = location

        try:
            logger.info(f"Scraping with {len(actions)} actions: {url}")
            result = self._call_scrape(url, scrape_params)
            data = self._normalize_document(result)

            logger.info(f"Action-based scrape completed: {url}")
            return {
                "success": bool(data),
                "url": url,
                "data": data,
                "scraper": self.__class__.__name__,
            }
        except Exception as e:
            logger.error(f"Action-based scrape failed for {url}: {e}")
            return {
                "success": False,
                "url": url,
                "error": str(e),
                "scraper": self.__class__.__name__,
            }

    # ------------------------------------------------------------------
    # UPGRADED: scrape_url() – add proxy, location, onlyMainContent
    # ------------------------------------------------------------------

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
