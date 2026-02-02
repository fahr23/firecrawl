"""
TradingView Scraper using Firecrawl
Scrapes sector and industry classifications for Turkish stocks
"""
import logging
from typing import Dict, Any
from datetime import datetime
from scrapers.base_scraper import BaseScraper

logger = logging.getLogger(__name__)


class TradingViewScraper(BaseScraper):
    """Scraper for TradingView sector and industry data"""
    
    BASE_URL = "https://tr.tradingview.com"
    
    async def scrape(self, data_type: str = "both") -> Dict[str, Any]:
        """
        Scrape TradingView sector/industry data
        
        Args:
            data_type: "sectors", "industries", or "both"
            
        Returns:
            Scraped sector/industry data
        """
        results = {}
        
        if data_type in ["sectors", "both"]:
            sectors_result = await self.scrape_sectors()
            results["sectors"] = sectors_result
        
        if data_type in ["industries", "both"]:
            industries_result = await self.scrape_industries()
            results["industries"] = industries_result
        
        return {
            "success": True,
            "data": results
        }
    
    async def scrape_sectors(self) -> Dict[str, Any]:
        """
        Scrape sector classifications
        
        Returns:
            Sector data with stock symbols
        """
        url = f"{self.BASE_URL}/markets/stocks-turkey/sectorandindustry-sector/"
        logger.info(f"Scraping sectors: {url}")
        
        # Extract sector data using LLM
        schema = {
            "type": "object",
            "properties": {
                "sectors": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "sector_name": {"type": "string"},
                            "stocks": {
                                "type": "array",
                                "items": {
                                    "type": "object",
                                    "properties": {
                                        "symbol": {"type": "string"},
                                        "name": {"type": "string"}
                                    }
                                }
                            }
                        }
                    }
                }
            }
        }
        
        result = await self.extract_with_schema(
            url,
            schema=schema,
            prompt="Extract all sectors and their associated stock symbols"
        )
        
        if result.get("success"):
            # Handle different result structures
            extracted_data = result.get("data", {})
            if isinstance(extracted_data, dict):
                sectors = extracted_data.get("sectors", [])
            elif isinstance(extracted_data, list) and len(extracted_data) > 0:
                sectors = extracted_data[0].get("sectors", []) if isinstance(extracted_data[0], dict) else []
            else:
                sectors = []
            
            logger.info(f"Found {len(sectors)} sectors")
            
            # Save to database
            saved_count = 0
            if self.db_manager and sectors:
                for sector in sectors:
                    if not isinstance(sector, dict):
                        continue
                    sector_name = sector.get("sector_name")
                    if not sector_name:
                        continue
                    stocks = sector.get("stocks", [])
                    if not stocks:
                        continue
                    for stock in stocks:
                        if not isinstance(stock, dict):
                            continue
                        data = {
                            "sector_name": sector_name,
                            "stock_symbol": stock.get("symbol"),
                            "stock_name": stock.get("name"),
                            "scraped_at": datetime.now().isoformat()
                        }
                        try:
                            self.save_to_db(data, "tradingview_sectors_tr")
                            saved_count += 1
                        except Exception as e:
                            logger.error(f"Error saving sector data: {e}")
            
            return {
                "success": True,
                "total_sectors": len(sectors),
                "saved_records": saved_count,
                "sectors": sectors
            }
        
        logger.warning(f"Sector extraction failed: {result.get('error', 'Unknown error')}")
        return result
    
    async def scrape_industries(self) -> Dict[str, Any]:
        """
        Scrape industry classifications
        
        Returns:
            Industry data with stock symbols
        """
        url = f"{self.BASE_URL}/markets/stocks-turkey/sectorandindustry-industry/"
        logger.info(f"Scraping industries: {url}")
        
        # Extract industry data using LLM
        schema = {
            "type": "object",
            "properties": {
                "industries": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "industry_name": {"type": "string"},
                            "stocks": {
                                "type": "array",
                                "items": {
                                    "type": "object",
                                    "properties": {
                                        "symbol": {"type": "string"},
                                        "name": {"type": "string"}
                                    }
                                }
                            }
                        }
                    }
                }
            }
        }
        
        result = await self.extract_with_schema(
            url,
            schema=schema,
            prompt="Extract all industries and their stock symbols"
        )
        
        if result.get("success"):
            # Handle different result structures
            extracted_data = result.get("data", {})
            if isinstance(extracted_data, dict):
                industries = extracted_data.get("industries", [])
            elif isinstance(extracted_data, list) and len(extracted_data) > 0:
                industries = extracted_data[0].get("industries", []) if isinstance(extracted_data[0], dict) else []
            else:
                industries = []
            
            logger.info(f"Found {len(industries)} industries")
            
            # Save to database
            saved_count = 0
            if self.db_manager and industries:
                for industry in industries:
                    if not isinstance(industry, dict):
                        continue
                    industry_name = industry.get("industry_name")
                    if not industry_name:
                        continue
                    stocks = industry.get("stocks", [])
                    if not stocks:
                        continue
                    for stock in stocks:
                        if not isinstance(stock, dict):
                            continue
                        data = {
                            "industry_name": industry_name,
                            "stock_symbol": stock.get("symbol"),
                            "stock_name": stock.get("name"),
                            "scraped_at": datetime.now().isoformat()
                        }
                        try:
                            self.save_to_db(data, "tradingview_industry_tr")
                            saved_count += 1
                        except Exception as e:
                            logger.error(f"Error saving industry data: {e}")
            
            return {
                "success": True,
                "total_industries": len(industries),
                "saved_records": saved_count,
                "industries": industries
            }
        
        logger.warning(f"Industry extraction failed: {result.get('error', 'Unknown error')}")
        return result
    
    async def scrape_crypto_symbols(self) -> Dict[str, Any]:
        """
        Scrape cryptocurrency symbols from TradingView
        
        Returns:
            Crypto symbols data
        """
        url = f"{self.BASE_URL}/markets/cryptocurrencies/prices-all/"
        logger.info(f"Scraping crypto symbols: {url}")
        
        # Extract crypto symbols
        schema = {
            "type": "object",
            "properties": {
                "cryptocurrencies": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "symbol": {"type": "string"},
                            "name": {"type": "string"},
                            "price": {"type": "number"}
                        }
                    }
                }
            }
        }
        
        result = await self.extract_with_schema(
            url,
            schema=schema,
            prompt="Extract all cryptocurrency symbols and names"
        )
        
        if result.get("success"):
            cryptos = result.get("data", {}).get("cryptocurrencies", [])
            logger.info(f"Found {len(cryptos)} cryptocurrencies")
            
            # Save to database
            if self.db_manager:
                for crypto in cryptos:
                    data = {
                        "symbol": crypto.get("symbol"),
                        "name": crypto.get("name"),
                        "price": crypto.get("price"),
                        "scraped_at": datetime.now().isoformat()
                    }
                    self.save_to_db(data, "cryptocurrency_symbols")
            
            return {
                "success": True,
                "total_cryptos": len(cryptos),
                "cryptocurrencies": cryptos
            }
        
        return result
