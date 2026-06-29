"""
KAP (Kamuyu Aydınlatma Platformu) Scraper

IMPORTANT: KAP is a Single Page Application (SPA) that loads data dynamically via API.
The HTML interface doesn't contain the actual report links - they're generated from JSON responses.

STRATEGY:
1. Bypass HTML interface and use API endpoint directly: /tr/api/memberDisclosureQuery
2. POST request with JSON payload (date range, filters)
3. Parse JSON response to extract disclosureIndex
4. Construct PDF URL: /tr/BildirimPdf/{disclosureIndex}
5. Download and process PDFs as needed

This approach is much more efficient than HTML crawling because:
- API returns 500+ records in seconds
- No need to render JavaScript or scroll infinitely
- Direct access to structured data
"""
import logging
import asyncio
import aiohttp
from typing import Dict, Any, List, Optional, Tuple
from datetime import datetime, timedelta
from pathlib import Path
from bs4 import BeautifulSoup
import re
from scrapers.base_scraper import BaseScraper
from utils.text_extractor import TextExtractorFactory
from utils.pdf_downloader import PDFDownloader
from utils.llm_analyzer import LLMAnalyzer, LocalLLMProvider, OpenAIProvider, GeminiProvider
import csv
import os

logger = logging.getLogger(__name__)

# --- Module-level schema constants ---
# Keeping these as module-level singletons ensures Firecrawl's deterministic JSON
# billing kicks in: repeated calls with the same schema object are billed at
# 3 credits (cached script) instead of 10 (codegen). See upstream #3750.

KAP_REPORT_SCHEMA: Dict[str, Any] = {
    "type": "object",
    "properties": {
        "company": {"type": "string"},
        "report_type": {"type": "string"},
        "date": {"type": "string"},
        "title": {"type": "string"},
        "summary": {"type": "string"},
        "attachments": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "name": {"type": "string"},
                    "url": {"type": "string"},
                    "type": {"type": "string"},
                },
            },
        },
    },
}
KAP_REPORT_PROMPT = "Extract report details including attachments"

BIST_INDICES_SCHEMA: Dict[str, Any] = {
    "type": "object",
    "properties": {
        "indices": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "name": {"type": "string"},
                    "companies": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "code": {"type": "string"},
                                "name": {"type": "string"},
                            },
                        },
                    },
                },
            },
        }
    },
}
BIST_INDICES_PROMPT = "Extract all indices and their company codes and names"


class KAPScraper(BaseScraper):
    """Scraper for KAP (Turkish Public Disclosure Platform) with PDF extraction and LLM analysis"""
    
    BASE_URL = "https://www.kap.org.tr"

    # Ordered Firecrawl proxy tiers to try when clearing KAP's anti-bot on /api/ JSON
    # endpoints. Self-hosted Firecrawl clears it with `basic`; Cloud usually needs `stealth`.
    # Override via env, e.g. KAP_FIRECRAWL_PROXY="stealth,basic".
    KAP_FIRECRAWL_PROXIES = [
        p.strip() for p in os.getenv("KAP_FIRECRAWL_PROXY", "basic,auto,stealth").split(",")
        if p.strip()
    ]

    def __init__(self, *args, **kwargs):
        """Initialize KAP scraper with extractors and analyzers"""
        super().__init__(*args, **kwargs)
        
        # Initialize text extractor factory
        self.text_extractor_factory = TextExtractorFactory()
        
        # Initialize LLM analyzer (can be configured)
        self.llm_analyzer = None  # Lazy initialization
        
        # Storage paths
        self.pdf_storage_path = Path("data/kap_pdfs")
        self.text_storage_path = Path("data/kap_texts")
        self.analysis_storage_path = Path("data/kap_analysis")
        
        # Create directories
        for path in [self.pdf_storage_path, self.text_storage_path, self.analysis_storage_path]:
            path.mkdir(parents=True, exist_ok=True)

        # Initialize PDF downloader utility
        self.pdf_downloader = PDFDownloader(
            download_dir=self.pdf_storage_path,
            text_dir=self.text_storage_path,
            extractor_factory=self.text_extractor_factory,
            max_attempts=3,
            backoff_initial=2.0,
        )
    
    def configure_llm(
        self,
        provider_type: str = "local",
        **provider_config
    ):
        """
        Configure LLM provider for analysis
        
        Args:
            provider_type: 'local', 'openai', or 'gemini'
            **provider_config: Provider-specific configuration
        """
        if provider_type == "local":
            provider = LocalLLMProvider(**provider_config)
        elif provider_type == "openai":
            provider = OpenAIProvider(**provider_config)
        elif provider_type == "gemini":
            provider = GeminiProvider(**provider_config)
        else:
            raise ValueError(f"Unknown provider type: {provider_type}. Supported: local, openai, gemini")
        
        self.llm_analyzer = LLMAnalyzer(provider)
        logger.info(f"Configured {provider_type} LLM provider")
    
    async def scrape_bloomberg_ht(
        self,
        days_back: int = 7,
        company_symbols: Optional[List[str]] = None
    ) -> Dict[str, Any]:
        """
        Scrape KAP reports from Bloomberg HT KAP news page (alternative source)
        
        Args:
            days_back: Number of days to look back
            company_symbols: Specific company symbols to scrape (filters results)
            
        Returns:
            Scraped reports data
        """
        logger.info(f"Scraping KAP reports from Bloomberg HT for last {days_back} days")
        
        # Bloomberg HT KAP news page
        bloomberg_url = "https://www.bloomberght.com/borsa/hisseler/kap-haberleri"
        
        logger.info(f"Scraping Bloomberg HT KAP page: {bloomberg_url}")
        print(f"🔗 Bloomberg HT URL: {bloomberg_url}")
        
        # Calculate date range
        end_date = datetime.now()
        start_date = end_date - timedelta(days=days_back)
        
        all_reports = []
        
        try:
            # Scrape the main page
            result = await self.scrape_url(
                bloomberg_url,
                wait_for=5000,
                formats=["markdown", "html"]
            )
            
            if not result.get("success"):
                logger.error("Failed to scrape Bloomberg HT page")
                return {
                    "success": False,
                    "error": "Failed to access Bloomberg HT page",
                    "total_companies": 0,
                    "processed_companies": 0,
                    "reports": []
                }
            
            # Get HTML content
            doc = result.get("data")
            html_content = None
            if doc:
                if hasattr(doc, 'html') and doc.html:
                    html_content = doc.html
                elif hasattr(doc, 'raw_html') and doc.raw_html:
                    html_content = doc.raw_html
            
            if not html_content:
                logger.error("No HTML content received")
                return {
                    "success": False,
                    "error": "No HTML content received",
                    "total_companies": 0,
                    "processed_companies": 0,
                    "reports": []
                }
            
            # Parse HTML to extract KAP news items
            soup = BeautifulSoup(html_content, 'html.parser')
            
            # Find all KAP news items - they appear to be in links or list items
            # Pattern: "COMPANY_CODE/COMPANY_NAME - TITLE DATE TIME"
            news_items = []
            
            # Try to find links that contain KAP news
            links = soup.find_all('a', href=True)
            for link in links:
                link_text = link.get_text(strip=True)
                href = link.get('href', '')
                
                # Look for pattern: COMPANY_CODE/COMPANY_NAME - TITLE
                if '/' in link_text and ' - ' in link_text:
                    # Extract company code (before first /)
                    parts = link_text.split('/')
                    if len(parts) >= 2:
                        company_code_part = parts[0].strip()
                        rest = '/'.join(parts[1:])
                        
                        # Extract company name and title (after -)
                        if ' - ' in rest:
                            company_name = rest.split(' - ')[0].strip()
                            title_part = ' - '.join(rest.split(' - ')[1:])
                            
                            # Extract date and time from title
                            # Pattern: "TITLE DD.MM.YYYY HH:MM"
                            date_match = re.search(r'(\d{2}\.\d{2}\.\d{4})\s+(\d{2}:\d{2})', title_part)
                            if date_match:
                                date_str = date_match.group(1)
                                time_str = date_match.group(2)
                                title = title_part[:date_match.start()].strip()
                                
                                # Parse date
                                try:
                                    report_date = datetime.strptime(date_str, "%d.%m.%Y").date()
                                    
                                    # Check if date is within range
                                    days_diff = (end_date.date() - report_date).days
                                    if days_diff <= days_back and days_diff >= 0:
                                        # Filter by company symbols if provided
                                        if company_symbols and company_code_part not in company_symbols:
                                            continue
                                        
                                        news_items.append({
                                            "company_code": company_code_part,
                                            "company_name": company_name,
                                            "title": title,
                                            "date": date_str,
                                            "time": time_str,
                                            "report_date": report_date,
                                            "url": href if href.startswith('http') else f"https://www.bloomberght.com{href}" if href.startswith('/') else None
                                        })
                                except Exception as e:
                                    logger.debug(f"Error parsing date {date_str}: {e}")
            
            logger.info(f"Found {len(news_items)} KAP news items from Bloomberg HT")
            
            # Process each news item
            for item in news_items:
                report_data = {
                    "company_code": item["company_code"],
                    "company_name": item["company_name"],
                    "report_date": item["report_date"].isoformat(),
                    "title": item["title"],
                    "report_type": "",  # Bloomberg HT doesn't provide this directly
                    "summary": "",
                    "data": {
                        "url": item.get("url", bloomberg_url),
                        "format": "html",
                        "extracted": True,
                        "source": "bloomberg_ht",
                        "time": item["time"],
                        "original_date_str": item["date"]
                    },
                    "scraped_at": datetime.now().isoformat()
                }
                
                # If we have a detail URL, try to scrape it for more info
                if item.get("url"):
                    try:
                        detail_result = await self.scrape_url(
                            item["url"],
                            wait_for=3000,
                            formats=["markdown"]
                        )
                        if detail_result.get("success"):
                            detail_doc = detail_result.get("data")
                            if detail_doc and hasattr(detail_doc, 'markdown'):
                                report_data["summary"] = detail_doc.markdown[:500]  # First 500 chars
                                report_data["data"]["detail_content"] = detail_doc.markdown[:2000]
                    except Exception as e:
                        logger.debug(f"Error scraping detail page {item['url']}: {e}")
                
                # Save to database
                if self.db_manager:
                    try:
                        self.save_to_db(report_data, "kap_reports")
                        all_reports.append(report_data)
                    except Exception as e:
                        logger.error(f"Error saving report for {item['company_code']}: {e}")
            
        except Exception as e:
            logger.error(f"Error scraping Bloomberg HT: {e}", exc_info=True)
            return {
                "success": False,
                "error": f"Error: {str(e)}",
                "total_companies": 0,
                "processed_companies": 0,
                "reports": []
            }
        
        # Get unique companies processed
        processed_companies = len(set(r.get("company_code") for r in all_reports if r.get("company_code")))
        
        return {
            "success": True,
            "total_companies": processed_companies,
            "processed_companies": processed_companies,
            "reports": all_reports,
            "total_reports": len(all_reports),
            "date_range": {
                "start": start_date.isoformat(),
                "end": end_date.isoformat()
            },
            "source": "bloomberg_ht"
        }
    
    async def scrape(
        self,
        days_back: int = 7,
        company_symbols: Optional[List[str]] = None
    ) -> Dict[str, Any]:
        """
        Scrape recent KAP reports - tries API first, falls back to Bloomberg HT
        
        Args:
            days_back: Number of days to look back
            company_symbols: Specific company symbols to scrape (filters results)
            
        Returns:
            Scraped reports data
        """
        logger.info(f"Scraping KAP reports for last {days_back} days (trying multiple sources)")
        
        # Try Bloomberg HT first (more reliable, no API timeout issues)
        logger.info("Attempting to scrape from Bloomberg HT...")
        bloomberg_result = await self.scrape_bloomberg_ht(days_back=days_back, company_symbols=company_symbols)
        
        if bloomberg_result.get("success") and bloomberg_result.get("total_reports", 0) > 0:
            logger.info(f"✅ Successfully scraped {bloomberg_result.get('total_reports', 0)} reports from Bloomberg HT")
            return bloomberg_result
        
        # Fallback to KAP API if Bloomberg HT didn't work
        logger.info("Bloomberg HT didn't return results, trying KAP API...")
        
        # Calculate date range
        end_date = datetime.now()
        start_date = end_date - timedelta(days=days_back)
        
        # Use KAP API endpoint (same as working getKAPReports.py)
        # This is the endpoint KAP uses to populate its search results
        api_url = f"{self.BASE_URL}/tr/api/memberDisclosureQuery"
        
        logger.info(f"KAP API URL: {api_url}")
        logger.info(f"Date range: {start_date.date()} to {end_date.date()}")
        print(f"🔗 KAP API URL: {api_url}")
        print(f"📅 Date range: {start_date.date()} to {end_date.date()}")
        
        # Prepare payload (matching working implementation)
        # Note: KAP API accepts YYYY-MM-DD format (verified in getKAPReports.py)
        # Alternative format DD.MM.YYYY may also work, but YYYY-MM-DD is confirmed working
        payload = {
            "fromDate": start_date.strftime("%Y-%m-%d"),
            "toDate": end_date.strftime("%Y-%m-%d"),
            "year": "",
            "prd": "",
            "term": "",
            "ruleType": "",
            "bdkReview": "",
            "disclosureClass": "",
            "index": "",
            "market": "",
            "isLate": "",
            "subjectList": [],
            "mkkMemberOidList": [],
            "inactiveMkkMemberOidList": [],
            "bdkMemberOidList": [],
            "mainSector": "",
            "sector": "",
            "subSector": "",
            "memberType": "IGS",  # BIST companies
            "fromSrc": "N",
            "srcCategory": "",
            "discIndex": []
        }
        
        # Headers to mimic browser request
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/58.0.3029.110 Safari/537.3",
            "Accept": "application/json, text/plain, */*",
            "Accept-Language": "en-US,en;q=0.9,tr;q=0.8",
            "Referer": "https://www.kap.org.tr/",
            "Content-Type": "application/json"
        }
        
        all_reports = []
        
        try:
            # Make POST request to KAP API with timeout
            timeout = aiohttp.ClientTimeout(total=30)  # 30 second timeout
            logger.info(f"Making POST request to: {api_url}")
            print(f"📤 Making POST request to: {api_url}")
            print(f"📦 Payload: fromDate={payload['fromDate']}, toDate={payload['toDate']}, memberType={payload['memberType']}")
            
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.post(api_url, json=payload, headers=headers) as response:
                    if response.status != 200:
                        error_text = await response.text()
                        logger.error(f"KAP API returned status {response.status}: {error_text[:200]}")
                        return {
                            "success": False,
                            "error": f"API returned status {response.status}",
                            "total_companies": 0,
                            "processed_companies": 0,
                            "reports": []
                        }
                    
                    data = await response.json()
                    logger.info(f"KAP API returned {len(data)} disclosures")
                    
                    # Process each disclosure
                    for item in data:
                        try:
                            # Extract stock codes (can be comma-separated)
                            stock_codes_str = item.get("stockCodes", "")
                            if not stock_codes_str:
                                continue
                            
                            # Parse stock codes (format: "AKBNK,THYAO" or single code)
                            stock_codes = [code.strip() for code in stock_codes_str.split(",") if code.strip()]
                            
                            # Filter by company symbols if provided
                            if company_symbols:
                                # Check if any of the stock codes match
                                if not any(code in company_symbols for code in stock_codes):
                                    continue
                            
                            # Use first stock code as primary company code
                            company_code = stock_codes[0] if stock_codes else ""
                            if not company_code:
                                continue
                            
                            # Parse publish date
                            publish_date_str = item.get("publishDate", "")
                            report_date = None
                            if publish_date_str:
                                try:
                                    # KAP API returns dates in format: "2026-01-25T00:00:00" or "2026-01-25"
                                    date_str_clean = publish_date_str.split("T")[0]  # Get date part
                                    report_date = datetime.strptime(date_str_clean, "%Y-%m-%d").date()
                                except Exception as e:
                                    logger.debug(f"Error parsing date {publish_date_str}: {e}")
                            
                            # Extract disclosureIndex - this is the key ID for PDF download
                            disclosure_index = item.get("disclosureIndex")
                            
                            # Construct PDF download URL: /tr/BildirimPdf/{disclosureIndex}
                            pdf_url = f"{self.BASE_URL}/tr/BildirimPdf/{disclosure_index}" if disclosure_index else None
                            
                            # Prepare report data (matching database schema)
                            report_data = {
                                "company_code": company_code,
                                "company_name": "",  # API doesn't provide company name directly
                                "report_date": report_date.isoformat() if report_date else None,
                                "title": item.get("kapTitle", "").strip() or item.get("subject", "").strip(),
                                "report_type": item.get("disclosureType", "").strip() or item.get("disclosureClass", "").strip(),
                                "summary": item.get("summary", "").strip(),
                                "data": {
                                    "url": pdf_url,  # PDF download URL
                                    "format": "api_json",
                                    "extracted": True,
                                    "source": "kap_api",
                                    "disclosure_index": disclosure_index,  # Key ID for PDF retrieval
                                    "disclosure_class": item.get("disclosureClass"),
                                    "disclosure_category": item.get("disclosureCategory"),
                                    "rule_type_term": item.get("ruleTypeTerm"),
                                    "is_late": item.get("isLate", False),
                                    "stock_codes": stock_codes_str,
                                    "attachment_count": item.get("attachmentCount", 0),
                                    "has_multi_language_support": item.get("hasMultiLanguageSupport", False),
                                    "api_response": {
                                        "kapTitle": item.get("kapTitle"),
                                        "subject": item.get("subject"),
                                        "publishDate": item.get("publishDate")
                                    }
                                },
                                "scraped_at": datetime.now().isoformat()
                            }
                            
                            # Save to database
                            if self.db_manager:
                                try:
                                    self.save_to_db(report_data, "kap_reports")
                                    all_reports.append(report_data)
                                except Exception as e:
                                    logger.error(f"Error saving report for {company_code}: {e}")
                        
                        except Exception as e:
                            logger.error(f"Error processing disclosure item: {e}")
                            continue
                    
        except asyncio.TimeoutError:
            logger.error("KAP API request timed out (API may be slow or network issue)")
            return {
                "success": False,
                "error": "API request timed out - KAP API may be slow or unreachable",
                "total_companies": 0,
                "processed_companies": 0,
                "reports": []
            }
        except aiohttp.ClientError as e:
            logger.error(f"HTTP error calling KAP API: {e}")
            return {
                "success": False,
                "error": f"HTTP error: {str(e)}",
                "total_companies": 0,
                "processed_companies": 0,
                "reports": []
            }
        except Exception as e:
            logger.error(f"Unexpected error calling KAP API: {e}", exc_info=True)
            return {
                "success": False,
                "error": f"Unexpected error: {str(e)}",
                "total_companies": 0,
                "processed_companies": 0,
                "reports": []
            }
        
        # Get unique companies processed
        processed_companies = len(set(r.get("company_code") for r in all_reports if r.get("company_code")))
        
        return {
            "success": True,
            "total_companies": processed_companies,
            "processed_companies": processed_companies,
            "reports": all_reports,
            "total_reports": len(all_reports),
            "date_range": {
                "start": start_date.isoformat(),
                "end": end_date.isoformat()
            }
        }
    
    async def scrape_company_report(
        self,
        company_code: str,
        report_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Scrape specific company report
        
        Args:
            company_code: Company symbol
            report_id: Specific report ID (optional)
            
        Returns:
            Report data
        """
        if report_id:
            url = f"{self.BASE_URL}/tr/Bildirim/{report_id}"
        else:
            url = f"{self.BASE_URL}/tr/api/memberDisclosureQuery?member={company_code}"
        
        logger.info(f"Scraping report: {url}")

        result = await self.extract_with_schema(
            url,
            schema=KAP_REPORT_SCHEMA,
            prompt=KAP_REPORT_PROMPT,
        )
        
        if result.get("success") and self.db_manager:
            report_data = result.get("data", {})
            report_data["company_code"] = company_code
            report_data["scraped_at"] = datetime.now().isoformat()
            self.save_to_db(report_data, "kap_reports")
        
        return result
    
    async def scrape_bist_indices(self) -> Dict[str, Any]:
        """
        Scrape all BIST indices and their companies
        
        Returns:
            Indices data with company listings
        """
        url = f"{self.BASE_URL}/tr/Endeksler"
        logger.info(f"Scraping BIST indices: {url}")

        result = await self.extract_with_schema(
            url,
            schema=BIST_INDICES_SCHEMA,
            prompt=BIST_INDICES_PROMPT,
        )
        
        if result.get("success") and self.db_manager:
            indices_data = result.get("data", {}).get("indices", [])
            
            for index in indices_data:
                for company in index.get("companies", []):
                    company_data = {
                        "code": company.get("code"),
                        "name": company.get("name"),
                        "index": index.get("name"),
                        "scraped_at": datetime.now().isoformat()
                    }
                    self.save_to_db(company_data, "bist_companies")
        
        return result
    
    async def download_pdf_attachment(
        self,
        pdf_url: str,
        filename: Optional[str] = None
    ) -> Optional[Dict[str, Any]]:
        """
        Download PDF attachment and extract text
        
        Args:
            pdf_url: URL of the PDF file
            filename: Optional custom filename
            
        Returns:
            Dict with pdf_path, text_path, and extracted_text
        """
        try:
            result = await self.pdf_downloader.download_and_extract(pdf_url, filename)
            if result and result.get("pdf_path"):
                return result
            logger.error(f"PDF download failed: {result.get('error') if isinstance(result, dict) else 'Unknown error'}")
            return None
        except Exception as e:
            logger.error(f"Error downloading/extracting PDF {pdf_url}: {e}")
            return None
    
    async def analyze_reports_with_llm(
        self,
        reports: List[Dict[str, Any]],
        generate_pdf: bool = True,
        output_filename: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Analyze reports using configured LLM
        
        Args:
            reports: List of report dictionaries with 'content' or 'extracted_text'
            generate_pdf: Whether to generate PDF report
            output_filename: Optional output filename for PDF
            
        Returns:
            Analysis results and PDF path if generated
        """
        if not self.llm_analyzer:
            logger.warning("LLM analyzer not configured. Call configure_llm() first.")
            return {
                'success': False,
                'error': 'LLM analyzer not configured'
            }
        
        try:
            # Prepare reports for analysis
            analysis_inputs = []
            for i, report in enumerate(reports):
                content = report.get('extracted_text') or report.get('content', '')
                if content:
                    analysis_inputs.append({
                        'title': report.get('title', f'Report {i + 1}'),
                        'url': report.get('url', ''),
                        'content': content
                    })
            
            if not analysis_inputs:
                logger.warning("No content to analyze")
                return {
                    'success': False,
                    'error': 'No content to analyze'
                }
            
            logger.info(f"Analyzing {len(analysis_inputs)} reports with LLM")
            
            # Perform analysis
            analyses = self.llm_analyzer.analyze_reports(analysis_inputs)
            
            result = {
                'success': True,
                'total_analyzed': len(analyses),
                'analyses': analyses
            }
            
            # Generate PDF report if requested
            if generate_pdf and analyses:
                if not output_filename:
                    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
                    output_filename = f"kap_analysis_{timestamp}.pdf"
                
                pdf_path = self.analysis_storage_path / output_filename
                
                success = self.llm_analyzer.generate_pdf_report(
                    analyses,
                    str(pdf_path)
                )
                
                if success:
                    result['pdf_report'] = str(pdf_path)
                    logger.info(f"Generated PDF analysis report: {pdf_path}")
            
            return result
            
        except Exception as e:
            logger.error(f"Error analyzing reports with LLM: {e}")
            return {
                'success': False,
                'error': str(e)
            }
    
    async def scrape_with_analysis(
        self,
        days_back: int = 7,
        company_symbols: Optional[List[str]] = None,
        download_pdfs: bool = True,
        analyze_with_llm: bool = False
    ) -> Dict[str, Any]:
        """
        Complete workflow: scrape reports, download PDFs, extract text, and optionally analyze with LLM
        
        Args:
            days_back: Number of days to look back
            company_symbols: Specific company symbols to scrape
            download_pdfs: Whether to download PDF attachments
            analyze_with_llm: Whether to analyze with LLM (requires configure_llm() first)
            
        Returns:
            Complete results including scraping, extraction, and analysis
        """
        # First, scrape reports
        scrape_result = await self.scrape(days_back, company_symbols)
        
        if not scrape_result.get('success'):
            return scrape_result
        
        reports = scrape_result.get('reports', [])
        
        # Download PDFs and extract text if requested
        if download_pdfs:
            logger.info("Downloading PDFs and extracting text")
            for report in reports:
                # Look for PDF URLs in report data
                data = report.get('data', {})
                if isinstance(data, dict):
                    pdf_url = data.get('pdf_url') or data.get('attachment_url')
                    if pdf_url:
                        extraction_result = await self.download_pdf_attachment(pdf_url)
                        if extraction_result:
                            report['pdf_extraction'] = extraction_result
        
        # Analyze with LLM if requested
        if analyze_with_llm:
            analysis_result = await self.analyze_reports_with_llm(reports)
            scrape_result['llm_analysis'] = analysis_result
        
        return scrape_result

    # ------------------------------------------------------------------
    # NEW: map_kap_disclosures() – discover all KAP disclosure URLs
    # ------------------------------------------------------------------

    async def map_kap_disclosures(
        self,
        company_code: Optional[str] = None,
        limit: int = 1000,
    ) -> Dict[str, Any]:
        """
        Use Firecrawl map() to discover disclosure URLs on KAP.

        Because KAP is a SPA, the map call crawls the sitemap and indexed
        pages to surface direct disclosure links.

        Args:
            company_code: If given, filter discovered links to this company code
            limit: Maximum links to return

        Returns:
            Dict with 'links' list filtered to KAP disclosure URLs
        """
        search_query = f"{company_code} bildirimi" if company_code else None
        result = await self.map_url(
            self.BASE_URL,
            search=search_query,
            limit=limit,
        )
        # Filter to known disclosure URL patterns
        if result.get("success"):
            links = result.get("links", [])
            disclosure_links = [
                lnk for lnk in links
                if "/BildirimPdf/" in lnk
                or "/bildirimi/" in lnk
                or "/tr/Bildirim" in lnk
            ]
            result["disclosure_links"] = disclosure_links
            result["disclosure_count"] = len(disclosure_links)
            logger.info(
                f"Found {len(disclosure_links)} disclosure links out of {len(links)} total"
            )
        return result

    # ------------------------------------------------------------------
    # NEW: search_kap_news() – web search for KAP financial news
    # ------------------------------------------------------------------

    async def search_kap_news(
        self,
        company_code: str,
        days_back: int = 7,
        limit: int = 20,
    ) -> Dict[str, Any]:
        """
        Use Firecrawl search() to find recent KAP news for a company.

        Args:
            company_code: Turkish stock symbol (e.g. 'AKBNK', 'THYAO')
            days_back: Restrict to news from the past N days
            limit: Max search results

        Returns:
            Dict with 'results' list of news articles
        """
        tbs_map = {1: "qdr:d", 7: "qdr:w", 30: "qdr:m"}
        tbs = tbs_map.get(days_back, "qdr:w")

        query = f"{company_code} KAP bildirimi finansal"
        return await self.search_web(
            query=query,
            limit=limit,
            lang="tr",
            country="TR",
            tbs=tbs,
            scrape_results=False,  # Just URLs; caller can batch-scrape if needed
        )

    # ------------------------------------------------------------------
    # NEW: scrape_kap_page_with_actions() – handle KAP SPA with actions
    # ------------------------------------------------------------------

    async def scrape_kap_page_with_actions(
        self,
        url: str,
        extra_actions: Optional[List[Dict[str, Any]]] = None,
    ) -> Dict[str, Any]:
        """
        Scrape a KAP page using browser actions to handle SPA rendering.

        KAP is a Single Page Application so content loads after JS execution.
        This method uses stealth proxy + wait actions to get the real content.

        Args:
            url: KAP URL to scrape
            extra_actions: Additional actions to perform before extracting
                          (e.g. clicking "load more" buttons)

        Returns:
            Scraped content after JS rendering
        """
        # Base actions: wait for SPA to hydrate then grab content
        base_actions: List[Dict[str, Any]] = [
            {"type": "wait", "milliseconds": 3000},
            {"type": "scroll", "direction": "down"},
            {"type": "wait", "milliseconds": 1000},
        ]
        if extra_actions:
            base_actions.extend(extra_actions)
        base_actions.append({"type": "scrape"})

        return await self.scrape_with_actions(
            url=url,
            actions=base_actions,
            formats=["markdown", "html"],
            proxy="stealth",
            location={"country": "TR", "languages": ["tr-TR", "tr"]},
            only_main_content=True,
        )

    # ------------------------------------------------------------------
    # NEW: batch_scrape_company_pages() – scrape multiple company pages
    # ------------------------------------------------------------------

    async def batch_scrape_company_pages(
        self,
        company_codes: List[str],
        proxy: str = "stealth",
    ) -> Dict[str, Any]:
        """
        Batch-scrape KAP company summary pages for a list of stock symbols.

        Much more efficient than scraping one-by-one when processing many
        companies simultaneously.

        Args:
            company_codes: List of Turkish stock symbols (e.g. ['AKBNK', 'THYAO'])
            proxy: Proxy type – 'stealth' recommended for KAP

        Returns:
            Dict with results keyed by company code
        """
        urls = [
            f"{self.BASE_URL}/tr/sirket-bilgileri/ozet/{code.lower()}"
            for code in company_codes
        ]
        batch_result = await self.batch_scrape_urls(
            urls=urls,
            formats=["markdown"],
            wait_for=3000,
            proxy=proxy,
            only_main_content=True,
        )

        # Map results back to company codes
        per_company: Dict[str, Any] = {}
        pages = batch_result.get("data", [])
        for code, page in zip(company_codes, pages):
            per_company[code] = page

        return {
            "success": batch_result.get("success", False),
            "total": len(company_codes),
            "scraped": len(pages),
            "results": per_company,
        }

    # ------------------------------------------------------------------
    # NEW: financial statements ("Finansal Tablolar") → fundamental analysis
    #
    # KAP serves financial tables through its financialTable API (verified routes):
    #   GET /tr/api/financialTable/listCompanyExcelMembers/{mkkMemberOid}/{year}/{term}
    #       → JSON list of {disclosureIndex, pdOid, year, period, stockCode, ...}
    #         (term "T" returns every period; period 4 == annual, 1-3 == interim)
    #   GET /tr/api/financialTable/download/{disclosureIndex}/{lang}  → .xlsx workbook
    #
    # The JSON list is fetched through Firecrawl (proxy=stealth, TR) to clear KAP's
    # anti-bot SPA layer; the binary .xlsx is fetched directly (Firecrawl returns
    # rendered text, not binary). Both degrade to a direct request as a fallback.
    # ------------------------------------------------------------------

    # KAP `period` codes on financial-table members.
    _ANNUAL_PERIOD = 4

    @staticmethod
    def _extract_json(text: Optional[str]) -> Optional[Any]:
        """Pull the first JSON array/object out of a (possibly HTML-wrapped) body."""
        import json

        if not text:
            return None
        text = text.strip()
        try:
            return json.loads(text)
        except (ValueError, TypeError):
            pass
        for open_c, close_c in (("[", "]"), ("{", "}")):
            i, j = text.find(open_c), text.rfind(close_c)
            if i != -1 and j > i:
                try:
                    return json.loads(text[i:j + 1])
                except ValueError:
                    continue
        return None

    async def _kap_api_via_js(
        self,
        api_path: str,
        method: str = "GET",
        body: Optional[Dict[str, Any]] = None,
        landing_url: Optional[str] = None,
    ) -> Optional[Any]:
        """
        Call a KAP JSON API endpoint from *within* a Firecrawl browser session.

        KAP's ``/api/...`` endpoints are guarded by anti-bot checks and CSRF
        validation that block direct aiohttp requests (404 on POST, 429 on GET).
        This method loads a real KAP SPA page via Firecrawl's stealth proxy so the
        browser acquires a valid KAP session, then injects a ``fetch()`` call that
        hits the API endpoint with ``credentials: "same-origin"`` — giving us the
        session cookies, SPA tokens, and proper Origin/Referer headers that KAP's
        anti-bot requires.

        The response text is stored in a ``<pre id="__kap_api_result">`` DOM node
        so we can reliably read it from the captured rawHtml without depending on the
        exact shape of Firecrawl's ``actions.results`` envelope.

        Args:
            api_path: URL path relative to BASE_URL, e.g. ``/tr/api/memberDisclosureQuery``
            method: HTTP method (``"GET"`` or ``"POST"``)
            body: Request body dict (for POST); ignored for GET
            landing_url: KAP page to load first; defaults to /tr/Bildirimler

        Returns:
            Parsed JSON (list or dict), or None when every strategy fails.
        """
        import json as _json

        landing = landing_url or f"{self.BASE_URL}/tr/Bildirimler"
        full_api_url = f"{self.BASE_URL}{api_path}"

        # Build the fetch() options string for the injected JS.
        if method.upper() == "POST" and body is not None:
            # Double-encode so the body JSON is a JS string literal we can JSON.parse.
            body_js_literal = _json.dumps(_json.dumps(body))
            fetch_options = (
                f'method:"POST",'
                f'headers:{{"Content-Type":"application/json","Accept":"application/json"}},'
                f'credentials:"same-origin",'
                f'body:JSON.parse({body_js_literal})'
            )
        else:
            fetch_options = 'method:"GET",credentials:"same-origin"'

        # Async IIFE that calls the API and injects the result into a <pre> node.
        # Uses document.documentElement (not body) so it works before body is ready.
        js_script = (
            "(async()=>{"
            "try{"
            f'const r=await fetch({_json.dumps(full_api_url)},{{{fetch_options}}});'
            "const t=await r.text();"
            'let el=document.getElementById("__kap_api_result");'
            'if(!el){el=document.createElement("pre");el.id="__kap_api_result";'
            "document.documentElement.appendChild(el);}"
            'el.setAttribute("data-status",String(r.status));'
            "el.textContent=t;"
            "}catch(e){"
            'let el=document.getElementById("__kap_api_result");'
            'if(!el){el=document.createElement("pre");el.id="__kap_api_result";'
            "document.documentElement.appendChild(el);}"
            'el.setAttribute("data-error",e.message);'
            "}"
            "})()"
        )

        actions: List[Dict[str, Any]] = [
            {"type": "wait", "milliseconds": 5000},    # SPA hydration + cookie init
            {"type": "executeJavascript", "script": js_script},
            {"type": "wait", "milliseconds": 5000},    # async fetch completes
            {"type": "scrape"},
        ]

        for proxy in self.KAP_FIRECRAWL_PROXIES:
            try:
                result = await self.scrape_with_actions(
                    url=landing,
                    actions=actions,
                    formats=["rawHtml"],
                    proxy=proxy,
                    location={"country": "TR", "languages": ["tr-TR", "tr"]},
                    only_main_content=False,
                )
                if not result.get("success"):
                    logger.debug(f"KAP JS-API (proxy={proxy}): scrape_with_actions failed")
                    continue

                data = result.get("data") or {}
                raw = (
                    data.get("rawHtml") if isinstance(data, dict)
                    else getattr(data, "rawHtml", None)
                )
                if not raw:
                    logger.debug(f"KAP JS-API (proxy={proxy}): no rawHtml in response")
                    continue

                # Extract JSON from <pre id="__kap_api_result">
                m = re.search(
                    r'<pre[^>]*id=["\']__kap_api_result["\'][^>]*>(.*?)</pre>',
                    raw, re.DOTALL | re.IGNORECASE,
                )
                if m:
                    content = m.group(1).strip()
                    parsed = self._extract_json(content)
                    if parsed is not None:
                        logger.info(
                            f"KAP JS-API (proxy={proxy}): got JSON via fetch() for {api_path}"
                        )
                        return parsed
                    # data-error attribute means fetch succeeded but API returned no JSON
                    if "data-error" in raw[m.start():m.end()]:
                        logger.warning(
                            f"KAP JS-API fetch error in browser: {content[:200]}"
                        )

                # Also check Firecrawl actions.results envelope as a secondary source.
                actions_data = (
                    data.get("actions") if isinstance(data, dict)
                    else getattr(data, "actions", None)
                )
                if isinstance(actions_data, dict):
                    for k in ("results", "result", "output"):
                        inner = actions_data.get(k)
                        if inner:
                            parsed = self._extract_json(
                                str(inner[0].get("result", ""))
                                if isinstance(inner, list) else str(inner)
                            )
                            if parsed is not None:
                                return parsed

                logger.debug(f"KAP JS-API (proxy={proxy}): no JSON found for {api_path}")
            except Exception as e:
                logger.debug(f"KAP JS-API (proxy={proxy}) exception for {api_path}: {e}")

        return None

    async def _fetch_kap_api_json(
        self, url: str, prefer_firecrawl: bool = True
    ) -> Optional[Any]:
        """
        Fetch a KAP JSON API endpoint, clearing the anti-bot SPA via Firecrawl.

        Strategy order:
        1. JS injection via _kap_api_via_js() — makes the GET from within a real KAP
           browser session, so session cookies + SPA context are in place. This is the
           primary path for endpoints that return 429/anti-bot to standalone requests.
        2. Direct Firecrawl scrape of the URL (proxy tiers basic→auto→stealth) — works
           for endpoints that accept bare browser GETs.
        3. Direct aiohttp GET with 429 backoff as last resort.
        """
        api_path = url.replace(self.BASE_URL, "") if url.startswith(self.BASE_URL) else url

        # 1. JS injection (browser-context GET — bypasses CSRF/session requirements)
        parsed = await self._kap_api_via_js(api_path=api_path, method="GET")
        if parsed is not None:
            return parsed

        # 2. Firecrawl proxy scrape (direct URL load in headless browser)
        if prefer_firecrawl:
            for proxy in self.KAP_FIRECRAWL_PROXIES:
                try:
                    result = await self.scrape_url(
                        url,
                        formats=["markdown", "rawHtml"],
                        proxy=proxy,
                        only_main_content=False,
                        location={"country": "TR", "languages": ["tr-TR", "tr"]},
                    )
                    if result.get("success"):
                        data = result.get("data") or {}
                        for attr in ("rawHtml", "markdown", "html"):
                            chunk = data.get(attr) if isinstance(data, dict) else getattr(data, attr, None)
                            chunk_parsed = self._extract_json(chunk)
                            if chunk_parsed is not None:
                                return chunk_parsed
                    logger.debug(f"KAP JSON via Firecrawl proxy={proxy} yielded no JSON for {url}")
                except Exception as e:
                    logger.debug(f"Firecrawl JSON fetch (proxy={proxy}) failed for {url}: {e}")

        # 3. Direct aiohttp GET with 429-aware backoff.
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "Accept": "application/json, text/plain, */*",
            "Referer": f"{self.BASE_URL}/",
        }
        try:
            timeout = aiohttp.ClientTimeout(total=30)
            async with aiohttp.ClientSession(timeout=timeout, headers=headers) as session:
                for attempt in range(3):
                    async with session.get(url) as resp:
                        if resp.status == 200:
                            return self._extract_json(await resp.text())
                        if resp.status == 429:
                            wait = 10 * (2 ** attempt)
                            logger.warning(
                                f"KAP API 429 on {url} (attempt {attempt+1}), waiting {wait}s"
                            )
                            await asyncio.sleep(wait)
                            continue
                        logger.warning(f"KAP API {url} returned HTTP {resp.status}")
                        break
        except Exception as e:
            logger.error(f"Direct KAP API fetch failed for {url}: {e}")
        return None

    async def list_company_excel_members(
        self, member_oid: str, year: int, term: str = "T"
    ) -> List[Dict[str, Any]]:
        """
        List a company's financial-table members for a year via the financialTable API.

        Each item carries `disclosureIndex`, `pdOid`, `period` (1-4) and `year`. Term
        "T" returns all periods of the year.
        """
        url = (
            f"{self.BASE_URL}/tr/api/financialTable/listCompanyExcelMembers/"
            f"{member_oid}/{year}/{term}"
        )
        data = await self._fetch_kap_api_json(url)
        if isinstance(data, list):
            return data
        logger.warning(f"No excel members for oid={member_oid} year={year}")
        return []

    async def download_financial_table_xlsx(
        self, disclosure_index: Any, pd_oid: Optional[str] = None, lang: str = "tr"
    ) -> Optional[bytes]:
        """
        Download a financial-table workbook (.xlsx) for a member.

        Mirrors KAP's own frontend call (reverse-engineered from the SPA):
            GET /{lang}/api/financialTable/download/{idA}/{idB}   Accept-Language: {lang}
        which streams the workbook as a binary blob (Content-Disposition filename).
        The two trailing ids are the member's `disclosureIndex` and `pdOid`; the exact
        order is not documented, so we try both and return the first binary workbook.
        Fetched directly (binary → not Firecrawl-able), like the existing PDF flow.
        Returns the workbook bytes, or None when KAP has no file for that member.
        """
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "Accept": "*/*",
            "Accept-Language": lang,
            "Referer": f"{self.BASE_URL}/tr/finansal-tablolar",
        }
        # Candidate id orderings (with and without pdOid, in case templates differ).
        pairs = []
        if pd_oid:
            pairs = [(disclosure_index, pd_oid), (pd_oid, disclosure_index)]
        else:
            pairs = [(disclosure_index, lang)]

        try:
            timeout = aiohttp.ClientTimeout(total=60)
            async with aiohttp.ClientSession(timeout=timeout, headers=headers) as session:
                for a, b in pairs:
                    url = f"{self.BASE_URL}/{lang}/api/financialTable/download/{a}/{b}"
                    try:
                        async with session.get(url) as resp:
                            if resp.status != 200:
                                continue
                            body = await resp.read()
                            # xlsx is a zip: must start with the PK local-file signature.
                            if body[:2] == b"PK":
                                return body
                    except Exception as e:  # pragma: no cover - per-candidate variability
                        logger.debug(f"FT download attempt failed ({url}): {e}")
            logger.warning(f"FT download produced no workbook for {disclosure_index}")
        except Exception as e:
            logger.error(f"FT download failed for {disclosure_index}: {e}")
        return None

    async def fetch_financial_statement_facts(
        self, disclosure_index: Any, pd_oid: Optional[str] = None
    ) -> Tuple[Dict[str, Any], Dict[str, Any]]:
        """
        Fetch one financial-report's (current, prior) canonical facts.

        KAP removed the public .xlsx download (it 404s even via a real browser), so the
        primary source is now the financial-report **disclosure page**
        (`/tr/Bildirim/{disclosureIndex}`), scraped to markdown via Firecrawl (the
        anti-bot SPA clears with the same proxy tiers as the JSON API) and parsed by
        `kap_financial_parser.parse_financial_table_markdown`. Falls back to the legacy
        .xlsx path when the page yields nothing. Returns ({}, {}) when both fail.
        """
        from scrapers.kap_financial_parser import (
            parse_financial_table_markdown,
            parse_financial_table_xlsx,
            normalize_facts,
        )

        url = f"{self.BASE_URL}/tr/Bildirim/{disclosure_index}"
        for proxy in self.KAP_FIRECRAWL_PROXIES:
            try:
                result = await self.scrape_url(
                    url, formats=["markdown"], proxy=proxy, only_main_content=False,
                    wait_for=6000, timeout=90000,
                    location={"country": "TR", "languages": ["tr-TR", "tr"]},
                )
                if not result.get("success"):
                    continue
                data = result.get("data") or {}
                md = data.get("markdown") if isinstance(data, dict) else getattr(data, "markdown", None)
                current, prior = parse_financial_table_markdown(md or "")
                if current:
                    return current, prior
            except Exception as e:
                logger.debug(f"FR markdown fetch (proxy={proxy}) failed for {disclosure_index}: {e}")

        # Legacy .xlsx fallback (currently dead at KAP, kept for resilience).
        xlsx = await self.download_financial_table_xlsx(disclosure_index, pd_oid=pd_oid)
        if xlsx:
            raw_current, raw_prior = parse_financial_table_xlsx(xlsx)
            return normalize_facts(raw_current), normalize_facts(raw_prior)
        return {}, {}

    def process_financial_statement(
        self,
        *,
        stock_code: str,
        period: str,
        raw_statement: Any,
        company_name: Optional[str] = None,
        fiscal_period: Optional[str] = None,
        currency: Optional[str] = None,
        reporting_standard: Optional[str] = None,
        disclosure_index: Optional[str] = None,
        prior_statement: Any = None,
        market: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        Parse → analyze → persist one instrument/period financial statement.

        Pure orchestration over the parser, the FundamentalAnalyzer, and the
        FundamentalRepository, so it is testable without any network access. Persists
        both the canonical facts and the computed ratios when a db_manager is set.
        Returns ``{stock_code, period, facts, payload, saved}``.
        """
        # Lazy imports: keep the scraper importable without pydantic (see tests/conftest).
        from scrapers.kap_financial_parser import normalize_facts
        from domain.services.fundamental_analyzer_service import FundamentalAnalyzer
        from infrastructure.repositories.fundamental_repository import FundamentalRepository

        facts = normalize_facts(raw_statement)
        prior_facts = normalize_facts(prior_statement) if prior_statement is not None else None
        payload = FundamentalAnalyzer().analyze(facts, prior_facts=prior_facts, market=market)

        saved = False
        if self.db_manager is not None:
            try:
                repo = FundamentalRepository(self.db_manager)
                repo.upsert_statement(
                    stock_code=stock_code,
                    period=period,
                    facts=facts,
                    company_name=company_name,
                    fiscal_period=fiscal_period,
                    currency=currency,
                    reporting_standard=reporting_standard,
                    disclosure_index=disclosure_index,
                )
                repo.upsert_fundamentals(
                    stock_code=stock_code,
                    period=period,
                    payload=payload,
                    company_name=company_name,
                    fiscal_period=fiscal_period,
                    currency=currency,
                    reporting_standard=reporting_standard,
                    source_disclosure_index=disclosure_index,
                )
                saved = True
            except Exception as e:
                logger.error(f"Persisting fundamentals failed for {stock_code} {period}: {e}")

        return {
            "stock_code": stock_code.upper(),
            "period": period,
            "facts": facts,
            "payload": payload,
            "saved": saved,
        }

    def _select_member(
        self, members: List[Dict[str, Any]]
    ) -> Optional[Dict[str, Any]]:
        """Pick the most relevant statement: latest annual if present, else latest period."""
        if not members:
            return None
        annual = [m for m in members if m.get("period") == self._ANNUAL_PERIOD]
        pool = annual or members
        return max(pool, key=lambda m: (m.get("year") or 0, m.get("period") or 0))

    async def scrape_financial_statements(
        self,
        instruments: Optional[List[str]] = None,
        year: Optional[int] = None,
        term: str = "T",
        market_data: Optional[Dict[str, Dict[str, Any]]] = None,
    ) -> Dict[str, Any]:
        """
        Fetch KAP "Finansal Tablolar" via the financialTable API and save fundamentals.

        For each instrument we resolve its `mkkMemberOid`, list the year's financial-table
        members, pick the latest annual statement, download its .xlsx, parse the current
        and comparative period columns, derive the §3 fundamental metrics, and persist
        them. The comparative column gives the prior period used for YoY growth.

        Args:
            instruments: BIST tickers; defaults to those resolvable to an mkkMemberOid.
            year: reporting year to list; defaults to the current calendar year.
            term: KAP term code ("T" = all periods of the year).
            market_data: optional ``{ticker: {"price": .., "shares_outstanding": ..}}``
                to enable price multiples (P/E, P/B, EV/EBITDA, dividend yield).

        Returns a per-instrument summary; instruments we could not resolve / fetch /
        parse are reported under ``failed`` (we never fabricate data).
        """
        from infrastructure.contracts.instrument_identity_map import (
            STATIC_MEMBER_OID_MAP,
            resolve_member_oid,
        )

        if not instruments:
            instruments = sorted(STATIC_MEMBER_OID_MAP.keys())
        year = year or datetime.now().year
        market_data = market_data or {}

        processed: List[Dict[str, Any]] = []
        failed: List[Dict[str, Any]] = []

        for ticker in instruments:
            code = ticker.strip().upper()
            oid = resolve_member_oid(code, db_manager=self.db_manager)
            if not oid:
                failed.append({"stock_code": code, "reason": "no_member_oid"})
                continue

            members = await self.list_company_excel_members(oid, year, term)
            member = self._select_member(members)
            if not member:
                failed.append({"stock_code": code, "reason": "no_financial_table"})
                continue

            disclosure_index = member.get("disclosureIndex")
            current_labels, prior_labels = await self.fetch_financial_statement_facts(
                disclosure_index, pd_oid=member.get("pdOid")
            )
            if not current_labels:
                failed.append({"stock_code": code, "reason": "no_parsable_facts"})
                continue

            period_code = member.get("period") or self._ANNUAL_PERIOD
            is_annual = period_code == self._ANNUAL_PERIOD
            member_year = member.get("year") or year
            period = str(member_year) if is_annual else f"{member_year}-Q{period_code}"

            result = self.process_financial_statement(
                stock_code=code,
                period=period,
                raw_statement=current_labels,
                prior_statement=prior_labels or None,
                company_name=member.get("title"),
                fiscal_period="annual" if is_annual else "interim",
                currency="TRY",
                reporting_standard="TFRS",
                disclosure_index=str(disclosure_index) if disclosure_index is not None else None,
                market=market_data.get(code),
            )
            (processed if result["facts"] else failed).append(
                result if result["facts"]
                else {"stock_code": code, "reason": "no_parsable_facts"}
            )

        return {
            "success": True,
            "requested": len(instruments),
            "processed": len(processed),
            "failed": failed,
            "results": processed,
        }

    async def download_real_pdfs(
        self,
        days_back: int = 3,
        subject_list: Optional[List[str]] = None,
        kap_pdf_directory: str = "/root/kap_pdfs",
        kap_txt_directory: str = "/root/kap_txts",
        kap_pdf_ek_directory: str = "/root/kap_pdfs_ek",
        kap_txt_ek_directory: str = "/root/kap_txts_ek",
        download_limit: int = 10,
        wait_time_seconds: int = 60,
        max_retries: int = 1,
    ) -> Dict[str, Any]:
        """
        Download real KAP disclosure PDFs and their attachments to provided directories.

        Mirrors legacy behavior using POST /tr/api/memberDisclosureQuery and parsing popup page
        for attachment links.

        Args:
            days_back: Number of days in the past to include.
            subject_list: Optional KAP subject codes list to filter.
            kap_pdf_directory: Directory to save main disclosure PDFs.
            kap_txt_directory: Directory to save extracted text for main PDFs.
            kap_pdf_ek_directory: Directory to save attachment PDFs.
            kap_txt_ek_directory: Directory to save extracted text for attachments.
            download_limit: Number of files to download before waiting.
            wait_time_seconds: Wait between batches to be polite.
            max_retries: Retries per file on failure.

        Returns:
            Dict with totals and lists of saved files.
        """
        # Ensure directories
        for d in [kap_pdf_directory, kap_txt_directory, kap_pdf_ek_directory, kap_txt_ek_directory]:
            Path(d).mkdir(parents=True, exist_ok=True)

        # Create two downloaders (main + attachments)
        main_downloader = PDFDownloader(
            download_dir=Path(kap_pdf_directory),
            text_dir=Path(kap_txt_directory),
            extractor_factory=self.text_extractor_factory,
            max_attempts=max_retries,
            backoff_initial=2.0,
        )
        att_downloader = PDFDownloader(
            download_dir=Path(kap_pdf_ek_directory),
            text_dir=Path(kap_txt_ek_directory),
            extractor_factory=self.text_extractor_factory,
            max_attempts=max_retries,
            backoff_initial=2.0,
        )

        end_date = datetime.now().date()
        start_date = end_date - timedelta(days=days_back)

        url = f"{self.BASE_URL}/tr/api/memberDisclosureQuery"
        payload = {
            "fromDate": start_date.strftime("%Y-%m-%d"),
            "toDate": end_date.strftime("%Y-%m-%d"),
            "year": "",
            "prd": "",
            "term": "",
            "ruleType": "",
            "bdkReview": "",
            "disclosureClass": "",
            "index": "",
            "market": "",
            "isLate": "",
            "subjectList": subject_list if subject_list else [],
            "mkkMemberOidList": [],
            "inactiveMkkMemberOidList": [],
            "bdkMemberOidList": [],
            "mainSector": "",
            "sector": "",
            "subSector": "",
            "memberType": "IGS",
            "fromSrc": "N",
            "srcCategory": "",
            "discIndex": []
        }
        headers = {
            "User-Agent": "Mozilla/5.0",
            "Accept": "application/json, text/plain, */*",
            "Referer": f"{self.BASE_URL}/",
        }

        total_downloads = 0
        main_saved: List[str] = []
        att_saved: List[str] = []
        batch_count = 0

        async with aiohttp.ClientSession(headers=headers) as session:
            data: List[Dict[str, Any]] = []
            try:
                async with session.post(url, json=payload) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                    else:
                        logger.warning(f"POST disclosureQuery returned HTTP {resp.status}, will try fallback")
            except Exception as e:
                logger.warning(f"POST disclosureQuery failed: {e}, trying fallback via member queries")

            # Fallback: query a few member codes directly if POST failed/empty
            if not data:
                # Build companies list from CSV fallback
                companies: List[str] = []
                try:
                    root_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
                    csv_path = os.path.join(root_dir, "bist_companies.csv")
                    with open(csv_path, newline="", encoding="utf-8") as f:
                        import csv as _csv
                        reader = _csv.reader(f)
                        for row in reader:
                            if not row or len(row) < 1:
                                continue
                            sym = row[0].strip().split(",")[0]
                            if not sym:
                                continue
                            code = sym.split(".")[0]
                            companies.append(code)
                except Exception as e:
                    logger.error(f"CSV fallback failed: {e}")

                companies = companies[:10]  # limit fallback
                logger.info(f"Fallback: querying member disclosures for {len(companies)} companies")
                for code in companies:
                    # Use Firecrawl-powered scraper to bypass anti-bot and get HTML
                    member_url = f"{self.BASE_URL}/tr/api/memberDisclosureQuery?member={code}"
                    try:
                        result = await self.scrape_url(member_url, wait_for=1500, formats=["html"])
                        if result.get("success") and result.get("data") and hasattr(result["data"], "html"):
                            html = result["data"].html or ""
                            # Find BildirimPdf links
                            indices = set(re.findall(r"/tr/ BildirimPdf /(\d+)", html)) if False else set(re.findall(r"/tr/BildirimPdf/(\d+)", html))
                            for idx in indices:
                                data.append({"disclosureIndex": idx})
                    except Exception as e:
                        logger.debug(f"Fallback member scrape failed for {code}: {e}")

            logger.info(f"Total disclosures found: {len(data)}")

            # Iterate from oldest to newest to mirror legacy reversed(data)
            for item in reversed(data):
                disclosure_index = item.get("disclosureIndex")
                if not disclosure_index:
                    continue

                # Main PDF
                main_pdf_url = f"{self.BASE_URL}/tr/BildirimPdf/{disclosure_index}"
                main_filename = f"{disclosure_index}.pdf"

                # Skip if file exists already
                main_pdf_path = Path(kap_pdf_directory) / main_filename
                if not main_pdf_path.exists():
                    try:
                        result = await main_downloader.download_and_extract(main_pdf_url, main_filename, session=session)
                        if result and result.get("pdf_path"):
                            main_saved.append(result["pdf_path"])
                            total_downloads += 1
                            batch_count += 1
                    except Exception as e:
                        logger.warning(f"Main PDF download failed for {disclosure_index}: {e}")

                # Attachments
                try:
                    att_url = f"{self.BASE_URL}/tr/BildirimPopup/{disclosure_index}"
                    async with session.get(att_url) as r:
                        if r.status == 200:
                            html = await r.text()
                            soup = BeautifulSoup(html, "html.parser")
                            links = soup.find_all("a", class_="modal-attachment")
                            for a in links:
                                href = a.get("href")
                                if not href:
                                    continue
                                attachment_url = f"{self.BASE_URL}{href}"
                                link_text = (a.text or "attachment").strip().replace(" ", "_")
                                att_filename = f"{disclosure_index}_{link_text}.pdf"
                                try:
                                    result = await att_downloader.download_and_extract(attachment_url, att_filename, session=session)
                                    if result and result.get("pdf_path"):
                                        att_saved.append(result["pdf_path"])
                                        total_downloads += 1
                                        batch_count += 1
                                except Exception as e:
                                    logger.warning(f"Attachment download failed for {disclosure_index}: {e}")
                except Exception as e:
                    logger.debug(f"Attachment fetch error for {disclosure_index}: {e}")

                # Batch throttling
                if batch_count >= download_limit:
                    logger.info(f"Reached download limit of {download_limit}. Waiting {wait_time_seconds}s...")
                    await asyncio.sleep(wait_time_seconds)
                    batch_count = 0

        return {
            "success": True,
            "total_downloads": total_downloads,
            "main_pdfs": main_saved,
            "attachment_pdfs": att_saved,
            "date_range": {"start": start_date.isoformat(), "end": end_date.isoformat()},
            "output_dirs": {
                "kap_pdf_directory": kap_pdf_directory,
                "kap_txt_directory": kap_txt_directory,
                "kap_pdf_ek_directory": kap_pdf_ek_directory,
                "kap_txt_ek_directory": kap_txt_ek_directory,
            },
        }

    async def download_pdfs_by_indices(
        self,
        disclosure_indices: List[str],
        kap_pdf_directory: str = "/root/kap_pdfs",
        kap_txt_directory: str = "/root/kap_txts",
        kap_pdf_ek_directory: str = "/root/kap_pdfs_ek",
        kap_txt_ek_directory: str = "/root/kap_txts_ek",
        max_retries: int = 1,
    ) -> Dict[str, Any]:
        """
        Download main PDFs (and attachments) for provided KAP disclosure indices.
        Useful when indices are known or fetched externally.
        """
        for d in [kap_pdf_directory, kap_txt_directory, kap_pdf_ek_directory, kap_txt_ek_directory]:
            Path(d).mkdir(parents=True, exist_ok=True)

        main_downloader = PDFDownloader(
            download_dir=Path(kap_pdf_directory),
            text_dir=Path(kap_txt_directory),
            extractor_factory=self.text_extractor_factory,
            max_attempts=max_retries,
            backoff_initial=2.0,
        )
        att_downloader = PDFDownloader(
            download_dir=Path(kap_pdf_ek_directory),
            text_dir=Path(kap_txt_ek_directory),
            extractor_factory=self.text_extractor_factory,
            max_attempts=max_retries,
            backoff_initial=2.0,
        )

        headers = {
            "User-Agent": "Mozilla/5.0",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
            "Referer": f"{self.BASE_URL}/",
        }

        main_saved: List[str] = []
        att_saved: List[str] = []
        async with aiohttp.ClientSession(headers=headers) as session:
            for idx in disclosure_indices:
                # Main PDF
                main_pdf_url = f"{self.BASE_URL}/tr/BildirimPdf/{idx}"
                main_filename = f"{idx}.pdf"
                try:
                    result = await main_downloader.download_and_extract(main_pdf_url, main_filename, session=session)
                    if result and result.get("pdf_path"):
                        main_saved.append(result["pdf_path"])
                except Exception as e:
                    logger.warning(f"Main PDF download failed for {idx}: {e}")

                # Attachments via popup
                try:
                    att_url = f"{self.BASE_URL}/tr/BildirimPopup/{idx}"
                    async with session.get(att_url) as r:
                        if r.status == 200:
                            html = await r.text()
                            soup = BeautifulSoup(html, "html.parser")
                            links = soup.find_all("a", class_="modal-attachment")
                            for a in links:
                                href = a.get("href")
                                if not href:
                                    continue
                                attachment_url = f"{self.BASE_URL}{href}"
                                link_text = (a.text or "attachment").strip().replace(" ", "_")
                                att_filename = f"{idx}_{link_text}.pdf"
                                try:
                                    result = await att_downloader.download_and_extract(attachment_url, att_filename, session=session)
                                    if result and result.get("pdf_path"):
                                        att_saved.append(result["pdf_path"])
                                except Exception as e:
                                    logger.warning(f"Attachment download failed for {idx}: {e}")
                except Exception as e:
                    logger.debug(f"Attachment fetch error for {idx}: {e}")

        return {
            "success": True,
            "main_pdfs": main_saved,
            "attachment_pdfs": att_saved,
            "output_dirs": {
                "kap_pdf_directory": kap_pdf_directory,
                "kap_txt_directory": kap_txt_directory,
                "kap_pdf_ek_directory": kap_pdf_ek_directory,
                "kap_txt_ek_directory": kap_txt_ek_directory,
            },
        }

    # ------------------------------------------------------------------
    # POST helper — mirrors _fetch_kap_api_json but for POST bodies
    # ------------------------------------------------------------------

    async def _post_kap_api_json(
        self, url: str, body: Dict[str, Any]
    ) -> Optional[Any]:
        """
        POST JSON to a KAP API endpoint and return the parsed JSON response.

        Strategy order:
        1. JS injection via _kap_api_via_js() — makes the POST from within a real KAP
           SPA browser session. This is the primary fix for the "POST APIs → 404" failure
           mode: direct aiohttp POSTs return 404/403 because KAP requires a properly
           initialised SPA session with CSRF context, but a fetch() issued from within
           the page itself has all of that automatically.
        2. Cookie-warmed direct POST via aiohttp — first GETs the KAP landing page so
           the CookieJar acquires the session cookie that KAP sets via HTTP Set-Cookie,
           then POSTs with those cookies. Handles cases where KAP's CSRF is cookie-only.
        3. Bare direct POST (original behaviour) as last resort.
        """
        api_path = url.replace(self.BASE_URL, "") if url.startswith(self.BASE_URL) else url

        # 1. JS injection — POST from within a live KAP browser session.
        parsed = await self._kap_api_via_js(api_path=api_path, method="POST", body=body)
        if parsed is not None:
            return parsed

        # 2. Cookie-warmed direct POST: acquire session cookies via a landing GET first.
        headers = {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
            ),
            "Accept": "application/json, text/plain, */*",
            "Accept-Language": "tr-TR,tr;q=0.9,en-US;q=0.8",
            "Content-Type": "application/json",
            "Origin": self.BASE_URL,
            "Referer": f"{self.BASE_URL}/tr/Bildirimler",
        }
        try:
            timeout = aiohttp.ClientTimeout(total=45)
            jar = aiohttp.CookieJar()
            async with aiohttp.ClientSession(timeout=timeout, headers=headers, cookie_jar=jar) as session:
                # Warm up cookies via the HTML landing page (Set-Cookie via HTTP).
                try:
                    async with session.get(
                        f"{self.BASE_URL}/tr/Bildirimler",
                        headers={**headers, "Accept": "text/html,*/*"},
                        allow_redirects=True,
                    ) as warm:
                        logger.debug(
                            f"KAP POST cookie warm-up: HTTP {warm.status}, "
                            f"cookies: {[c.key for c in jar]}"
                        )
                except Exception as e:
                    logger.debug(f"KAP POST cookie warm-up failed (non-fatal): {e}")

                # Now POST with the warmed session.
                async with session.post(url, json=body) as resp:
                    if resp.status == 200:
                        return self._extract_json(await resp.text())
                    logger.warning(f"KAP cookie-warmed POST {url} → HTTP {resp.status}")
        except Exception as e:
            logger.debug(f"KAP cookie-warmed POST failed for {url}: {e}")

        # 3. Bare direct POST (original behaviour, no cookie warm-up).
        try:
            timeout = aiohttp.ClientTimeout(total=30)
            async with aiohttp.ClientSession(timeout=timeout, headers=headers) as session:
                async with session.post(url, json=body) as resp:
                    if resp.status == 200:
                        return self._extract_json(await resp.text())
                    logger.warning(f"KAP POST {url} → HTTP {resp.status}")
        except Exception as e:
            logger.error(f"KAP POST failed {url}: {e}")
        return None

    # ------------------------------------------------------------------
    # GET-only member-OID resolution (avoids the blocked member/filter POST)
    # ------------------------------------------------------------------
    _OZET_LINK_RE = re.compile(
        r"\[([A-ZÇĞİÖŞÜ0-9.,& ]{2,15})\]\("
        r"(https://www\.kap\.org\.tr/tr/sirket-bilgileri/ozet/[0-9]+-[^)]+)\)"
    )
    _TICKER_RE = re.compile(r"^[A-Z0-9]{3,6}$")
    # Seconds to pace between company-page fetches. KAP's anti-bot is rate-based, so a
    # gentle crawl (resolve OIDs slowly, cache them in bist_companies) avoids tripping it
    # on a self-hosted Firecrawl without rotating proxies. Crank up via KAP_PAGE_DELAY_S.
    KAP_PAGE_DELAY_S = float(os.getenv("KAP_PAGE_DELAY_S", "4.0"))
    # Tolerant of JSON-in-HTML escaping: the key appears as  mkkMemberOid\":\"<32hex>\"
    _MEMBER_OID_RE = re.compile(r'mkkMemberOid[\\":\s]{1,10}([0-9a-f]{32})')

    async def list_bist_companies_via_get(self) -> Dict[str, Dict[str, str]]:
        """
        Scrape KAP's public BIST companies page (GET) → {ticker: {url, name}}.

        The page renders a table of every BIST company linking to its summary page
        (`/tr/sirket-bilgileri/ozet/{kapId}-{slug}`). We map each ticker to that URL so
        we can then read the company's `mkkMemberOid` off the summary page — all over
        GET, sidestepping the blocked `member/filter` POST.
        """
        result = await self._scrape_kap_page("https://www.kap.org.tr/tr/bist-sirketler")
        md = result or ""
        companies: Dict[str, Dict[str, str]] = {}
        for text, url in self._OZET_LINK_RE.findall(md):
            code = text.strip().upper()
            if not self._TICKER_RE.match(code):
                continue
            companies.setdefault(code, {"url": url, "name": ""})
        logger.info(f"Discovered {len(companies)} BIST tickers via GET page")
        return companies

    async def resolve_member_oid_via_get(self, company_url: str) -> Optional[str]:
        """Read a company's `mkkMemberOid` (32-hex) off its summary page (GET)."""
        # The summary page hydrates its company data client-side, so wait for it and
        # require the marker to be present before accepting the render.
        result = await self._scrape_kap_page(
            company_url, wait_for=8000, must_contain="mkkMemberOid"
        )
        if not result:
            return None
        m = self._MEMBER_OID_RE.search(result)
        return m.group(1) if m else None

    async def _scrape_kap_page(
        self,
        url: str,
        wait_for: int = 6000,
        must_contain: Optional[str] = None,
        attempts: int = 2,
    ) -> Optional[str]:
        """
        Scrape a KAP HTML page to rawHtml+markdown, clearing anti-bot via proxy tiers.

        KAP pages hydrate their data client-side, so ``wait_for`` matters and
        ``must_contain`` lets callers reject a not-yet-rendered shell (the page returns
        a ~15 KB app shell before hydration and the full ~250 KB doc after). KAP's
        anti-bot is rate-based and intermittently flags bursts with ``document_antibot``,
        so we retry the proxy tiers a few times with exponential backoff.
        """
        for attempt in range(1, attempts + 1):
            for proxy in self.KAP_FIRECRAWL_PROXIES:
                try:
                    res = await self.scrape_url(
                        url, formats=["rawHtml", "markdown"], proxy=proxy,
                        only_main_content=False, wait_for=wait_for,
                        # KAP pages are heavy (~250 KB) and clear anti-bot in-engine;
                        # the 30 s default is too tight and aborts as document_antibot.
                        timeout=90000,
                        location={"country": "TR", "languages": ["tr-TR", "tr"]},
                    )
                    if res.get("success"):
                        data = res.get("data") or {}
                        raw = data.get("rawHtml") if isinstance(data, dict) else getattr(data, "rawHtml", None)
                        md = data.get("markdown") if isinstance(data, dict) else getattr(data, "markdown", None)
                        body = (raw or "") + "\n" + (md or "")
                        if body.strip() and (must_contain is None or must_contain in body):
                            return body
                except Exception as e:
                    logger.debug(f"KAP page scrape (proxy={proxy}) failed for {url}: {e}")
            if attempt < attempts:
                await asyncio.sleep(2.0 * attempt)  # back off; KAP anti-bot is rate-based
        return None

    async def refresh_member_oids_via_get(
        self, instruments: Optional[List[str]] = None
    ) -> Dict[str, Any]:
        """
        Resolve mkkMemberOids over GET only and persist them to `bist_companies`.

        Lists BIST companies from the public page, then for each requested ticker (or all
        of STATIC_BIST_MAP when none given) reads its `mkkMemberOid` off the summary page.
        Avoids the anti-bot-blocked `member/filter` POST entirely. Returns a summary.
        """
        from infrastructure.contracts.instrument_identity_map import (
            STATIC_BIST_MAP,
            STATIC_MEMBER_OID_MAP,
        )

        directory = await self.list_bist_companies_via_get()
        if not directory:
            return {"success": False, "error": "company_list_unavailable", "resolved": 0, "updated": 0}

        wanted = [t.strip().upper() for t in (instruments or list(STATIC_BIST_MAP.keys()))]
        resolved, updated, missing = {}, 0, []
        for idx, code in enumerate(wanted):
            entry = directory.get(code)
            if not entry:
                missing.append(code)
                continue
            if idx:
                await asyncio.sleep(self.KAP_PAGE_DELAY_S)  # pace; KAP anti-bot is rate-based
            oid = await self.resolve_member_oid_via_get(entry["url"])
            if not oid:
                missing.append(code)
                continue
            resolved[code] = oid
            STATIC_MEMBER_OID_MAP[code] = oid  # benefit this session immediately
            if self.db_manager is not None:
                try:
                    self.db_manager.upsert_bist_company(code, mkk_member_oid=oid)
                    updated += 1
                except Exception as e:
                    logger.debug(f"upsert_bist_company({code}) failed: {e}")

        return {
            "success": True,
            "method": "get",
            "total_in_directory": len(directory),
            "requested": len(wanted),
            "resolved": len(resolved),
            "updated": updated,
            "missing": missing,
            "oids": resolved,
        }

    # ------------------------------------------------------------------
    # refresh_member_oids — populate bist_companies.mkk_member_oid
    # ------------------------------------------------------------------

    async def refresh_member_oids(self) -> Dict[str, Any]:
        """
        Query KAP's member/filter API to discover mkkMemberOid for every BIST company.

        Fetches the full list of BIST (IGS) members from KAP, cross-references each
        member's stockCodes with STATIC_BIST_MAP, and upserts the matched OIDs to
        `bist_companies.mkk_member_oid` so that subsequent calls to
        `resolve_member_oid()` use the DB-authoritative value instead of the static
        seed (which currently only has ASELS).

        Returns a summary dict with counts.
        """
        from infrastructure.contracts.instrument_identity_map import (
            STATIC_BIST_MAP,
            STATIC_MEMBER_OID_MAP,
        )

        url = f"{self.BASE_URL}/tr/api/member/filter"
        body: Dict[str, Any] = {
            "memberType": "IGS",
            "keyword": "",
            "isActive": "",
            "pagingDto": {"currentPage": 1, "rowCount": 9999},
        }
        members = await self._post_kap_api_json(url, body)

        if not isinstance(members, list):
            # Some KAP endpoints wrap in {"data": [...]}
            if isinstance(members, dict):
                members = members.get("data") or members.get("members") or []
        if not isinstance(members, list) or not members:
            logger.warning("refresh_member_oids: no members returned from KAP")
            return {"success": False, "error": "empty_response", "resolved": 0, "updated": 0}

        # Build stockCode → mkkMemberOid
        oid_by_code: Dict[str, str] = {}
        for m in members:
            oid = (
                m.get("mkkMemberOid")
                or m.get("memberOid")
                or m.get("oid")
                or ""
            ).strip()
            if not oid:
                continue
            raw_codes = m.get("stockCodes") or m.get("stockCode") or []
            if isinstance(raw_codes, str):
                raw_codes = [c.strip() for c in raw_codes.split(",") if c.strip()]
            for code in raw_codes:
                oid_by_code[code.upper()] = oid

        # Update in-memory static map so this session benefits immediately.
        STATIC_MEMBER_OID_MAP.update(oid_by_code)

        # Persist to DB so future sessions benefit even without re-fetching.
        updated = 0
        errors: List[str] = []
        if self.db_manager is not None:
            # Upsert ALL discovered members (not just the ones in STATIC_BIST_MAP)
            # because the DB may know about tickers we haven't hardcoded yet.
            for code, oid in oid_by_code.items():
                try:
                    # Also carry the company name if the member record provides it.
                    m_name = next(
                        (
                            (m.get("shortName") or m.get("companyName") or "").strip()
                            for m in members
                            if oid in (
                                m.get("mkkMemberOid", ""),
                                m.get("memberOid", ""),
                                m.get("oid", ""),
                            )
                        ),
                        None,
                    )
                    self.db_manager.upsert_bist_company(
                        code, name=m_name or None, mkk_member_oid=oid
                    )
                    updated += 1
                except Exception as e:
                    errors.append(f"{code}: {e}")

        return {
            "success": True,
            "total_kap_members": len(members),
            "resolved": len(oid_by_code),
            "updated": updated,
            "errors": errors,
        }

    # ------------------------------------------------------------------
    # scrape_and_save_disclosures — proper company disclosures → kap_disclosures
    # ------------------------------------------------------------------

    async def scrape_and_save_disclosures(
        self,
        days_back: int = 7,
        instruments: Optional[List[str]] = None,
        subject_list: Optional[List[str]] = None,
        fetch_pdf_text: bool = False,
    ) -> Dict[str, Any]:
        """
        Fetch KAP company disclosures via memberDisclosureQuery and save to kap_disclosures.

        Unlike the legacy ``scrape()`` method (which targets ``kap_reports``), this
        method uses the canonical ``kap_disclosures`` table with proper columns for
        ``stock_code``, ``disclosure_id`` (=disclosureIndex), ``subject``, ``is_late``,
        and ``has_attachment`` so downstream sentiment analysis can query them cleanly.

        Args:
            days_back: How many calendar days back to fetch.
            instruments: Optional list of BIST tickers to filter (resolves to OIDs).
            subject_list: Optional KAP subject codes to filter (e.g. ["FR", "ÖZKD"]).
            fetch_pdf_text: Whether to download and extract main PDF text content.

        Returns:
            {"success": bool, "total": int, "saved": int, "disclosures": list}
        """
        from infrastructure.contracts.instrument_identity_map import resolve_member_oid

        end_date = datetime.now()
        start_date = end_date - timedelta(days=days_back)

        # Resolve tickers to OIDs for server-side filtering (faster than client filter).
        oid_list: List[str] = []
        if instruments:
            for ticker in instruments:
                oid = resolve_member_oid(ticker, db_manager=self.db_manager)
                if oid:
                    oid_list.append(oid)

        body: Dict[str, Any] = {
            "fromDate": start_date.strftime("%Y-%m-%d"),
            "toDate": end_date.strftime("%Y-%m-%d"),
            "year": "",
            "prd": "",
            "term": "",
            "ruleType": "",
            "bdkReview": "",
            "disclosureClass": "",
            "index": "",
            "market": "",
            "isLate": "",
            "subjectList": subject_list or [],
            "mkkMemberOidList": oid_list,
            "inactiveMkkMemberOidList": [],
            "bdkMemberOidList": [],
            "mainSector": "",
            "sector": "",
            "subSector": "",
            "memberType": "IGS",
            "fromSrc": "N",
            "srcCategory": "",
            "discIndex": [],
        }

        url = f"{self.BASE_URL}/tr/api/memberDisclosureQuery"
        data = await self._post_kap_api_json(url, body)

        if not isinstance(data, list):
            logger.error(f"memberDisclosureQuery returned unexpected type: {type(data)}")
            return {
                "success": False,
                "error": "invalid_response",
                "total": 0,
                "saved": 0,
                "disclosures": [],
            }

        saved = 0
        disclosures: List[Dict[str, Any]] = []

        for item in data:
            disclosure_index = str(item.get("disclosureIndex") or "").strip()
            if not disclosure_index:
                continue

            # Parse stock codes — KAP returns a comma-separated string.
            raw_codes = (item.get("stockCodes") or "").strip()
            stock_codes = [c.strip() for c in raw_codes.split(",") if c.strip()]
            primary_code = stock_codes[0] if stock_codes else None

            # Parse date.
            publish_date = None
            date_str = (item.get("publishDate") or "").split("T")[0]
            if date_str:
                try:
                    publish_date = datetime.strptime(date_str, "%Y-%m-%d").date()
                except ValueError:
                    pass

            title = (item.get("kapTitle") or item.get("subject") or "").strip()
            subject = (item.get("subject") or "").strip()
            disclosure_type = (
                item.get("disclosureType")
                or item.get("disclosureClass")
                or ""
            ).strip()
            subject_code = str(item.get("disclosureClass") or "").strip()
            has_attachment = bool(item.get("attachmentCount"))
            is_late = bool(item.get("isLate"))

            detail_url = f"{self.BASE_URL}/tr/Bildirim/{disclosure_index}"
            pdf_url = f"{self.BASE_URL}/tr/BildirimPdf/{disclosure_index}"

            pdf_text: Optional[str] = None
            if fetch_pdf_text and self.pdf_downloader:
                try:
                    result = await self.pdf_downloader.download_and_extract(pdf_url)
                    if result:
                        pdf_text = result.get("extracted_text")
                except Exception as e:
                    logger.debug(f"PDF extraction failed for {disclosure_index}: {e}")

            disc_row: Dict[str, Any] = {
                "disclosure_id": disclosure_index,
                "stock_code": primary_code,
                "company_name": item.get("memberName") or raw_codes,
                "disclosure_type": disclosure_type,
                "disclosure_date": publish_date,
                "timestamp": item.get("publishDate") or "",
                "has_attachment": has_attachment,
                "detail_url": detail_url,
                "pdf_url": pdf_url,
                "content": title,
                "subject": subject,
                "subject_code": subject_code,
                "is_late": is_late,
                "data": {
                    "stock_codes": stock_codes,
                    "disclosure_class": item.get("disclosureClass"),
                    "rule_type_term": item.get("ruleTypeTerm"),
                    "attachment_count": item.get("attachmentCount", 0),
                    "has_multi_language": item.get("hasMultiLanguageSupport", False),
                    "pdf_text": pdf_text,
                },
            }

            if self.db_manager is not None:
                try:
                    self.db_manager.upsert_disclosure(disc_row)
                    saved += 1
                except Exception as e:
                    logger.error(f"Failed to save disclosure {disclosure_index}: {e}")

            disclosures.append(disc_row)

        return {
            "success": True,
            "total": len(data),
            "saved": saved,
            "disclosures": disclosures,
            "date_range": {
                "from": start_date.strftime("%Y-%m-%d"),
                "to": end_date.strftime("%Y-%m-%d"),
            },
        }

    # ------------------------------------------------------------------
    # scrape_kap_news — KAP / SPK / MKK platform-level announcements
    # ------------------------------------------------------------------

    async def scrape_kap_news(
        self,
        days_back: int = 7,
        categories: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        """
        Fetch KAP platform-level news (SPK decisions, MKK announcements, BIS notices).

        These are NOT company disclosures — they are regulatory/system announcements
        published by KAP itself. Tries several known API endpoints and falls back to
        scraping the KAP duyurular page via Firecrawl with stealth proxy.

        The scraped items are saved to ``kap_news`` and keyed by a content-derived
        news_id so repeated runs are idempotent.

        Args:
            days_back: How many days back to look.
            categories: Optional category filter (e.g. ["SPK", "MKK"]). None = all.

        Returns:
            {"success": bool, "total": int, "saved": int, "items": list}
        """
        import hashlib

        end_date = datetime.now()
        start_date = end_date - timedelta(days=days_back)

        raw_items: List[Dict[str, Any]] = []

        # --- Attempt 1: known KAP duyuru API endpoints (GET) ---
        for path in [
            "/tr/api/duyuru/list",
            "/tr/api/announcement/list",
            f"/tr/api/duyuru/list/{end_date.year}",
        ]:
            url = f"{self.BASE_URL}{path}"
            data = await self._fetch_kap_api_json(url, prefer_firecrawl=False)
            if isinstance(data, list) and data:
                raw_items = data
                logger.info(f"Fetched {len(raw_items)} news items from {path}")
                break
            if isinstance(data, dict):
                inner = data.get("data") or data.get("items") or data.get("announcements") or []
                if inner:
                    raw_items = inner
                    break

        # --- Attempt 2: Firecrawl scrape of duyurular page ---
        if not raw_items:
            try:
                result = await self.scrape_kap_page_with_actions(
                    f"{self.BASE_URL}/tr/duyurular"
                )
                if result.get("success"):
                    # Extract structured items from the rendered page text.
                    raw_items = self._parse_news_page(result, start_date)
                    logger.info(f"Scraped {len(raw_items)} news items from duyurular page")
            except Exception as e:
                logger.error(f"Firecrawl duyurular scrape failed: {e}")

        # --- Normalize + filter + save ---
        saved = 0
        processed: List[Dict[str, Any]] = []

        for item in raw_items:
            # Normalise across possible API response shapes.
            title = (
                item.get("title")
                or item.get("baslik")
                or item.get("subject")
                or item.get("kapTitle")
                or ""
            ).strip()
            if not title:
                continue

            content = (
                item.get("content")
                or item.get("icerik")
                or item.get("summary")
                or item.get("description")
                or ""
            ).strip()
            category = (
                item.get("category")
                or item.get("news_category")
                or item.get("type")
                or item.get("duyuruTipi")
                or "KAP"
            ).strip()

            if categories and category.upper() not in [c.upper() for c in categories]:
                continue

            raw_date = (
                item.get("publish_date")
                or item.get("publishDate")
                or item.get("tarih")
                or item.get("date")
                or ""
            )
            publish_dt: Optional[datetime] = None
            if isinstance(raw_date, datetime):
                publish_dt = raw_date
            elif raw_date:
                for fmt in ("%Y-%m-%dT%H:%M:%S", "%Y-%m-%d", "%d.%m.%Y"):
                    try:
                        publish_dt = datetime.strptime(str(raw_date).split(".")[0], fmt)
                        break
                    except ValueError:
                        continue

            # Apply date filter.
            if publish_dt and publish_dt.date() < start_date.date():
                continue

            source_url = item.get("source_url") or item.get("url") or item.get("link") or ""
            news_id = item.get("id") or item.get("news_id")
            if not news_id:
                news_id = hashlib.sha1(
                    f"{category}|{title}|{(publish_dt or '').isoformat() if publish_dt else ''}".encode()
                ).hexdigest()[:16]

            news_row: Dict[str, Any] = {
                "news_id": str(news_id),
                "news_category": category,
                "title": title,
                "content": content or None,
                "publish_date": publish_dt,
                "source_url": source_url or None,
                "data": {k: v for k, v in item.items()
                         if k not in ("title", "content", "category", "publish_date", "source_url")},
            }

            if self.db_manager is not None:
                try:
                    row_id = self.db_manager.upsert_news(news_row)
                    if row_id is not None:
                        saved += 1
                        news_row["db_id"] = row_id
                except Exception as e:
                    logger.error(f"Failed to save news '{title[:40]}': {e}")

            processed.append(news_row)

        return {
            "success": True,
            "total": len(raw_items),
            "returned": len(processed),
            "saved": saved,
            "items": processed,
            "date_range": {
                "from": start_date.strftime("%Y-%m-%d"),
                "to": end_date.strftime("%Y-%m-%d"),
            },
        }

    def _parse_news_page(
        self, scrape_result: Dict[str, Any], since: datetime
    ) -> List[Dict[str, Any]]:
        """
        Extract news items from a Firecrawl-scraped duyurular page.

        KAP's duyurular page renders a list of announcement cards. We parse the
        markdown or HTML to extract title / date / category / URL for each item.
        Returns a list of raw dicts compatible with scrape_kap_news normalisation.
        """
        items: List[Dict[str, Any]] = []
        data = scrape_result.get("data") or {}
        text = ""
        if isinstance(data, dict):
            text = data.get("markdown") or data.get("html") or data.get("content") or ""
        elif isinstance(data, str):
            text = data

        if not text:
            return items

        # Date pattern used in KAP's UI: "DD.MM.YYYY" or "YYYY-MM-DD"
        date_re = re.compile(r"(\d{2}\.\d{2}\.\d{4}|\d{4}-\d{2}-\d{2})")
        lines = [l.strip() for l in text.splitlines() if l.strip()]

        current: Dict[str, Any] = {}
        for line in lines:
            dm = date_re.search(line)
            if dm:
                if current.get("title"):
                    items.append(current)
                date_str = dm.group(1)
                try:
                    if "." in date_str:
                        publish_dt: Optional[datetime] = datetime.strptime(date_str, "%d.%m.%Y")
                    else:
                        publish_dt = datetime.strptime(date_str, "%Y-%m-%d")
                except ValueError:
                    publish_dt = None
                current = {
                    "title": line[:dm.start()].strip("- |#").strip(),
                    "publish_date": publish_dt,
                    "category": "KAP",
                }
            elif current and not current.get("content"):
                if len(line) > 20 and not line.startswith("http"):
                    current["content"] = line

        if current.get("title"):
            items.append(current)

        return items
