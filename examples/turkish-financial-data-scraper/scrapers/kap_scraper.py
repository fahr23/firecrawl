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
from typing import Dict, Any, List, Optional
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


class KAPScraper(BaseScraper):
    """Scraper for KAP (Turkish Public Disclosure Platform) with PDF extraction and LLM analysis"""
    
    BASE_URL = "https://www.kap.org.tr"
    
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
        
        # Extract structured report data
        schema = {
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
                            "type": {"type": "string"}
                        }
                    }
                }
            }
        }
        
        result = await self.extract_with_schema(
            url,
            schema=schema,
            prompt="Extract report details including attachments"
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
        
        # Extract indices and companies
        schema = {
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
            prompt="Extract all indices and their company codes and names"
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
