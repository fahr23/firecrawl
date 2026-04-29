"""
BIST (Borsa Istanbul) Companies Scraper using Firecrawl
"""
import logging
from typing import Dict, Any, List
from datetime import datetime
from scrapers.base_scraper import BaseScraper
from bs4 import BeautifulSoup
import csv
import os

logger = logging.getLogger(__name__)


class BISTScraper(BaseScraper):
    """Scraper for BIST (Borsa Istanbul) company listings"""
    
    BASE_URL = "https://www.kap.org.tr"
    
    async def scrape(self) -> Dict[str, Any]:
        """
        Scrape all BIST companies
        
        Returns:
            All BIST companies data
        """
        from pathlib import Path
        import csv
        import re

        logger.info("Loading BIST companies from local CSV fallback")

        # Repo root: .../examples/turkish-financial-data-scraper/scrapers -> go up 3 levels
        repo_root = Path(__file__).resolve().parents[3]
        csv_path = repo_root / "bist_companies.csv"

        companies: List[Dict[str, Any]] = []
        try:
            with csv_path.open("r", encoding="utf-8") as f:
                reader = csv.reader(f)
                next(reader, None)  # skip header
                for row in reader:
                    if not row or len(row) < 2:
                        continue
                    raw_code = row[0].strip()
                    name = row[1].strip()

                    m = re.search(r"([A-Z0-9]+)\.IS", raw_code)
                    if not m:
                        continue
                    code = m.group(1)

                    # Enforce DB constraint: code VARCHAR(10)
                    if len(code) > 10:
                        continue

                    companies.append({
                        "code": code,
                        "name": name,
                        "sector": None,
                    })

            logger.info(f"Found {len(companies)} BIST companies from CSV")

            if self.db_manager:
                for company in companies:
                    company_data = {
                        **company,
                        "symbol": f"{company['code']}.IS",
                        "scraped_at": datetime.now().isoformat(),
                    }
                    self.save_to_db(company_data, "bist_companies")

            return {
                "success": True,
                "total_companies": len(companies),
                "companies": companies,
                "source": "csv_fallback",
            }
        except Exception as e:
            logger.error(f"Failed to load CSV, falling back to online extraction: {e}")
            url = f"{self.BASE_URL}/tr/bist-sirketler"
            schema = {
                "type": "object",
                "properties": {
                    "companies": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "code": {"type": "string"},
                                "name": {"type": "string"},
                                "sector": {"type": "string"},
                            },
                        },
                    }
                },
            }
            result = await self.extract_with_schema(
                url,
                schema=schema,
                prompt="Extract all company codes and full names from the table",
            )
            return result
    
    async def scrape_indices(self) -> Dict[str, Any]:
        """
        Scrape BIST indices and their company members
        
        Returns:
            Indices data with company listings
        """
        url = f"{self.BASE_URL}/tr/Endeksler"
        logger.info(f"Scraping BIST indices: {url}")
        
        # Crawl indices pages
        result = await self.crawl_website(
            url,
            limit=10,
            include_patterns=["/tr/Endeksler/*"]
        )
        
        if not result.get("success"):
            return result
        
        # Extract index data from crawled pages
        all_indices = []
        crawl_data = result.get("data", {})
        
        for page_data in crawl_data.get("data", []):
            page_url = page_data.get("url", "")
            markdown = page_data.get("markdown", "")
            
            # Extract index info using schema
            schema = {
                "type": "object",
                "properties": {
                    "index_name": {"type": "string"},
                    "companies": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "code": {"type": "string"},
                                "name": {"type": "string"}
                            }
                        }
                    }
                }
            }
            
            index_result = await self.extract_with_schema(
                page_url,
                schema=schema,
                prompt="Extract index name and all company codes/names"
            )
            
            if index_result.get("success"):
                index_data = index_result.get("data", {})
                all_indices.append(index_data)
                
                # Save to database
                if self.db_manager:
                    for company in index_data.get("companies", []):
                        data = {
                            "index_name": index_data.get("index_name"),
                            "company_code": company.get("code"),
                            "company_name": company.get("name"),
                            "scraped_at": datetime.now().isoformat()
                        }
                        self.save_to_db(data, "bist_index_members")
        
        return {
            "success": True,
            "total_indices": len(all_indices),
            "indices": all_indices
        }
    
    async def scrape_commodity_prices(
        self,
        start_date: str,
        end_date: str,
        price_types: List[str] = None
    ) -> Dict[str, Any]:
        """
        Scrape commodity prices from BIST
        
        Args:
            start_date: Start date (YYYYMMDD)
            end_date: End date (YYYYMMDD)
            price_types: Price types to scrape (AG, AU, PD, PT)
            
        Returns:
            Commodity prices data
        """
        if price_types is None:
            price_types = ["AG", "AU", "PD", "PT"]
        
        base_url = "https://www.borsaistanbul.com"
        all_prices = []
        
        for price_type in price_types:
            url = (
                f"{base_url}/datfile/kmtprfrnstrh"
                f"?startDate={start_date}&endDate={end_date}"
                f"&priceType={price_type}"
            )
            
            logger.info(f"Scraping {price_type} prices: {url}")
            
            result = await self.scrape_url(url, formats=["markdown"])
            
            if result.get("success"):
                # Extract price data
                schema = {
                    "type": "object",
                    "properties": {
                        "prices": {
                            "type": "array",
                            "items": {
                                "type": "object",
                                "properties": {
                                    "date": {"type": "string"},
                                    "price": {"type": "number"},
                                    "currency": {"type": "string"}
                                }
                            }
                        }
                    }
                }
                
                extract_result = await self.extract_with_schema(
                    url,
                    schema=schema,
                    prompt=f"Extract {price_type} commodity prices with dates"
                )
                
                if extract_result.get("success"):
                    prices_data = extract_result.get("data", {})
                    prices = prices_data.get("prices", [])
                    
                    # Save to database
                    if self.db_manager:
                        for price in prices:
                            data = {
                                "commodity_type": price_type,
                                "date": price.get("date"),
                                "price": price.get("price"),
                                "currency": price.get("currency"),
                                "scraped_at": datetime.now().isoformat()
                            }
                            self.save_to_db(data, "historical_price_emtia")
                    
                    all_prices.extend(prices)
        
        return {
            "success": True,
            "total_prices": len(all_prices),
            "price_types": price_types,
            "date_range": {
                "start": start_date,
                "end": end_date
            },
            "prices": all_prices
        }
