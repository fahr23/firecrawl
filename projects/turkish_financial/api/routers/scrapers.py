"""
Scraper endpoints
"""
import logging
import asyncio
import json
from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks
from typing import Dict, Any, Optional, List
from datetime import datetime, timedelta

from api.models import (
    ScrapeKAPRequest, ScrapeBISTRequest, ScrapeTradingViewRequest,
    ScrapeResponse, LLMConfigRequest, BatchScrapeRequest, KAPBatchScrapeRequest,
    BatchJobResponse, JobStatusResponse, SentimentAnalysisRequest, SentimentAnalysisResponse,
    AutoSentimentRequest, WebhookConfigRequest, URLSentimentRequest
)
from api.dependencies import get_db_manager, get_config
from production_kap_final import ProductionKAPScraper
from scrapers.bist_scraper import BISTScraper
from scrapers.tradingview_scraper import TradingViewScraper
from database.db_manager import DatabaseManager
from config import Config
from utils.batch_job_manager import job_manager, JobStatus
from utils.webhook_notifier import WebhookNotifier

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/scrapers", tags=["scrapers"])

# Global webhook notifier (can be configured via API)
_webhook_notifier: Optional[WebhookNotifier] = None


def parse_kap_homepage_disclosures(content: str) -> List[Dict[str, Any]]:
    """
    Parse KAP homepage to extract individual disclosure entries from the table.
    Handles markdown tables, HTML tables, and raw checkbox patterns.
    
    Returns:
        List of disclosure dictionaries, each with meaningful_text, company_name, disclosure_type
    """
    try:
        from bs4 import BeautifulSoup
        import re
        
        disclosures = []
        if not content:
            return disclosures
        
        logger.info(f"Parsing KAP content, length: {len(content)}")
        
        # Check for empty page first
        if 'Bildirim bulunamadı' in content or 'No disclosures found' in content.lower():
            logger.info("Page indicates no disclosures available: 'Bildirim bulunamadı'")
            return disclosures
        
        soup = BeautifulSoup(content, 'html.parser')
        
        # APPROACH 1: Extract from HTML table rows that contain company indicators
        logger.info("Attempting HTML table parsing for disclosures")
        tables = soup.find_all('table')
        for table in tables:
            rows = table.find_all('tr')
            for i, row in enumerate(rows):
                cells = row.find_all(['td', 'th'])
                if len(cells) >= 2:
                    cell_texts = [cell.get_text(strip=True) for cell in cells]
                    row_text = ' | '.join(cell_texts)
                    
                    # Check if row contains company name (not header row or empty message row)
                    has_company = any(indicator in row_text for indicator in ['A.Ş.', 'BANKASI', 'HOLDİNG', 'T.A.Ş.'])
                    if has_company and len(row_text) > 20:
                        # Extract disclosure details
                        company_name = "Unknown"
                        disclosure_id = ""
                        disclosure_type = "General Disclosure"
                        disclosure_date = ""
                        
                        # Company name extraction
                        company_patterns = [
                            r'([A-ZÇĞİÖŞÜ][A-ZÇĞİÖŞÜa-zçğıöşü\s\.\-]{2,50}A\.Ş\.?)',
                            r'([A-ZÇĞİÖŞÜ][A-ZÇĞİÖŞÜa-zçğıöşü\s\.\-]{2,40}BANKASI)',
                            r'([A-ZÇĞİÖŞÜ][A-ZÇĞİÖŞÜa-zçğıöşü\s\.\-]{2,40}HOLDİNG)',
                            r'([A-ZÇĞİÖŞÜ][A-ZÇĞİÖŞÜa-zçğıöşü\s\.\-]{2,50}T\.A\.Ş\.?)',
                        ]
                        
                        for pattern in company_patterns:
                            match = re.search(pattern, row_text)
                            if match:
                                company_name = match.group(1).strip()[:255]
                                break
                        
                        # Extract disclosure ID if present (often first column)
                        if cell_texts and cell_texts[0]:
                            disclosure_id = cell_texts[0].strip()[:50]
                        
                        # Disclosure type detection
                        content_lower = row_text.lower()
                        if 'özel durum açıklaması' in content_lower:
                            disclosure_type = "Special Situation"
                        elif 'finansal rapor' in content_lower or 'mali' in content_lower:
                            disclosure_type = "Financial Report"
                        elif 'pay' in content_lower and 'geri' in content_lower:
                            disclosure_type = "Share Buyback"
                        elif 'genel kurul' in content_lower:
                            disclosure_type = "General Assembly"
                        elif 'temettü' in content_lower:
                            disclosure_type = "Dividend"
                        elif 'sermaye' in content_lower:
                            disclosure_type = "Capital Change"
                        elif 'transfer' in content_lower:
                            disclosure_type = "Transfer"
                        elif 'sorumluluk beyanı' in content_lower:
                            disclosure_type = "Responsibility Statement"
                        elif 'faaliyet raporu' in content_lower:
                            disclosure_type = "Activity Report"
                        
                        # Create disclosure record
                        disclosure = {
                            "meaningful_text": row_text[:5000],
                            "company_name": company_name,
                            "disclosure_type": disclosure_type,
                            "disclosure_id": disclosure_id or f"table_row_{i}",
                            "disclosure_date": disclosure_date
                        }
                        
                        disclosures.append(disclosure)
                        logger.info(f"Extracted disclosure from table: {company_name} - {disclosure_type}")
        
        logger.info(f"HTML table parsing found {len(disclosures)} disclosures")
        
        if disclosures:
            logger.info(f"Total extracted disclosures: {len(disclosures)}")
            return disclosures
        
        # APPROACH 2: Regex pattern for checkbox-based entries in markdown or text
        logger.info("Attempting regex/checkbox pattern parsing")
        # Look for patterns like "checkbox 292 Dün 22:26 | Company Name | Type"
        checkbox_pattern = r'checkbox\s+(\d+)\s+(.+?)(?=checkbox|$)'
        matches = re.findall(checkbox_pattern, content, re.MULTILINE | re.IGNORECASE | re.DOTALL)
        
        for match in matches:
            disclosure_id = match[0].strip()
            disclosure_text = match[1].strip()
            
            # Split by pipes to extract fields
            parts = [p.strip() for p in disclosure_text.split('|')]
            
            company_name = "Unknown"
            disclosure_type = "General Disclosure"
            disclosure_date = ""
            
            # Try to extract company name and type from the disclosure text
            if parts:
                disclosure_date = parts[0] if parts else ""
                
                # Company name is usually in the next part
                if len(parts) > 1:
                    potential_company = parts[1]
                    company_patterns = [
                        r'([A-ZÇĞİÖŞÜ][A-ZÇĞİÖŞÜa-zçğıöşü\s\.\-]{2,50}A\.Ş\.?)',
                        r'([A-ZÇĞİÖŞÜ][A-ZÇĞİÖŞÜa-zçğıöşü\s\.\-]{2,40}BANKASI)',
                        r'([A-ZÇĞİÖŞÜ][A-ZÇĞİÖŞÜa-zçğıöşü\s\.\-]{2,40}HOLDİNG)',
                        r'([A-ZÇĞİÖŞÜ][A-ZÇĞİÖŞÜa-zçğıöşü\s\.\-]{2,50}T\.A\.Ş\.?)',
                    ]
                    for pattern in company_patterns:
                        match_company = re.search(pattern, potential_company)
                        if match_company:
                            company_name = match_company.group(1).strip()[:255]
                            break
                
                # Disclosure type from the text
                full_text = ' '.join(parts).lower()
                if 'özel durum açıklaması' in full_text:
                    disclosure_type = "Special Situation"
                elif 'finansal rapor' in full_text:
                    disclosure_type = "Financial Report"
                elif 'pay' in full_text and 'geri' in full_text:
                    disclosure_type = "Share Buyback"
                elif 'genel kurul' in full_text:
                    disclosure_type = "General Assembly"
            
            # Only add if we found a valid company name
            if company_name != "Unknown":
                disclosure = {
                    "meaningful_text": disclosure_text[:5000],
                    "company_name": company_name,
                    "disclosure_type": disclosure_type,
                    "disclosure_id": disclosure_id,
                    "disclosure_date": disclosure_date
                }
                disclosures.append(disclosure)
                logger.info(f"Extracted disclosure from checkbox: {company_name} - {disclosure_type}")
        
        logger.info(f"Total extracted disclosures: {len(disclosures)}")
        return disclosures
        
    except Exception as e:
        logger.error(f"Error parsing KAP homepage disclosures: {e}", exc_info=True)
        return []


def parse_html_content(content: str) -> Dict[str, Any]:
    """
    Parse HTML/text content to extract meaningful disclosure information.
    For KAP homepage, extract multiple disclosures. For other pages, extract single content.
    
    Args:
        content: Raw HTML or text content from URL
        
    Returns:
        Dictionary with parsed data including meaningful_text, company_name, disclosure_type
    """
    try:
        from bs4 import BeautifulSoup
        import re
        
        parsed = {
            "meaningful_text": "",
            "company_name": "",
            "disclosure_type": "Web Content"
        }
        
        if not content:
            return parsed
        
        # Try to parse as HTML
        try:
            soup = BeautifulSoup(content, 'html.parser')
            
            # Remove script, style, and navigation elements
            for script in soup(["script", "style", "meta", "link", "nav", "header", "footer"]):
                script.decompose()
            
            # Remove common navigation/menu classes (based on KAP HTML structure)
            nav_classes = ['menu', 'navigation', 'nav', 'header', 'footer', 'sidebar', 'breadcrumb']
            for nav_class in nav_classes:
                for element in soup.find_all(class_=re.compile(nav_class, re.I)):
                    element.decompose()
            
            disclosure_content = []
            
            # STRATEGY 1: Look for actual disclosure tables (working pattern from yesterday)
            tables = soup.find_all('table')
            meaningful_tables_found = False
            
            if tables:
                for table in tables:
                    rows = table.find_all('tr')
                    table_content = []
                    
                    for row in rows:
                        cells = row.find_all(['td', 'th'])
                        if len(cells) >= 2:
                            cell_texts = []
                            for cell in cells:
                                cell_text = cell.get_text(strip=True)
                                # Skip cells that are just navigation/menu items
                                if cell_text and len(cell_text) > 3 and not any(nav_word in cell_text.lower() for nav_word in 
                                    ['menu', 'gir', 'çık', 'login', 'logout', 'ara', 'search', 'menü']):
                                    cell_texts.append(cell_text)
                            
                            if cell_texts:
                                row_text = ' | '.join(cell_texts)
                                # Only include rows that look like actual disclosure data
                                if len(row_text) > 20 and any(keyword in row_text.lower() for keyword in 
                                    ['a.ş.', 'bankası', 'holding', 'ltd', 'şti', 'tl', 'usd', 'eur', 'milyon', 'bin']):
                                    table_content.append(row_text)
                                    meaningful_tables_found = True
                    
                    if table_content:
                        disclosure_content.extend(table_content)
            
            # STRATEGY 2: Extract from disclosure-specific content areas
            # Look for content containers that typically hold disclosure text
            content_areas = ['article', 'main', '.disclosure-content', '.content', '.detail']
            for area in content_areas:
                if area.startswith('.'):
                    elements = soup.find_all(class_=re.compile(area[1:], re.I))
                else:
                    elements = soup.find_all(area)
                
                for element in elements:
                    text = element.get_text(strip=True)
                    # Only extract substantial content that looks like disclosure text
                    if text and len(text) > 50:
                        # Filter out navigation-heavy text
                        lines = text.split('\n')
                        meaningful_lines = []
                        for line in lines:
                            line = line.strip()
                            if (len(line) > 15 and 
                                not any(nav_word in line.lower() for nav_word in 
                                ['menü', 'menu', 'giriş', 'çıkış', 'arama', 'search', 'login']) and
                                any(content_word in line.lower() for content_word in 
                                ['şirket', 'company', 'bildirim', 'disclosure', 'finansal', 'financial', 
                                 'rapor', 'report', 'açıklama', 'statement', 'yönetim', 'management'])):
                                meaningful_lines.append(line)
                        
                        if meaningful_lines:
                            disclosure_content.extend(meaningful_lines[:10])  # Limit per area
            
            # STRATEGY 3: If no meaningful content found, this might be a navigation page
            if not disclosure_content:
                # Extract any substantial paragraphs as fallback
                paragraphs = soup.find_all(['p', 'div'])
                for p in paragraphs:
                    text = p.get_text(strip=True)
                    if (text and len(text) > 30 and 
                        any(keyword in text.lower() for keyword in 
                        ['açıklama', 'bildirim', 'şirket', 'company', 'finansal', 'mali'])):
                        disclosure_content.append(text)
            
            # Combine and clean the extracted content
            if disclosure_content:
                meaningful_text = " ".join(disclosure_content[:50])  # Limit content
                meaningful_text = re.sub(r'\s+', ' ', meaningful_text).strip()
            else:
                # This is likely a navigation/menu page with no disclosure content
                logger.info("No meaningful disclosure content found - likely navigation page")
                meaningful_text = "Navigation page with no disclosure content"
            
            # Extract company name (only from meaningful content)
            company_patterns = [
                r'([A-ZÇĞİÖŞÜ][A-ZÇĞİÖŞÜa-zçğıöşü\s\.\-]{3,40}(?:A\.Ş\.?|A\.S\.?))',
                r'([A-ZÇĞİÖŞÜ][A-ZÇĞİÖŞÜa-zçğıöşü\s\.\-]{3,30}BANKASI)',
                r'([A-ZÇĞİÖŞÜ][A-ZÇĞİÖŞÜa-zçğıöşü\s\.\-]{3,30}HOLDİNG)',
                r'([A-ZÇĞİÖŞÜ][A-ZÇĞİÖŞÜa-zçğıöşü\s\.\-]{3,30}T\.A\.Ş\.?)'
            ]
            
            for pattern in company_patterns:
                match = re.search(pattern, meaningful_text)
                if match:
                    company_name = match.group(1).strip()
                    # Verify this isn't a menu item
                    if len(company_name) > 10 and 'menü' not in company_name.lower():
                        parsed["company_name"] = company_name[:50]  # Truncate long names
                        break
            
            # Detect disclosure type from meaningful content only
            if len(meaningful_text) > 50:  # Only if we have substantial content
                disclosure_keywords = {
                    'finansal|rapor|mali|bilanço': 'Financial Report',
                    'genel kurul|toplantı|karar': 'General Assembly', 
                    'sermaye|hisse': 'Capital Change',
                    'temettü|kar': 'Dividend',
                    'birleşme|devir|satın alma': 'M&A Activity',
                    'özel durum|önemli gelişme': 'Special Situation'
                }
                
                text_lower = meaningful_text.lower()
                for keywords, disc_type in disclosure_keywords.items():
                    if any(keyword in text_lower for keyword in keywords.split('|')):
                        parsed["disclosure_type"] = disc_type
                        break
            
            # Store the meaningful text (limit for BERT)
            parsed["meaningful_text"] = meaningful_text[:5000]
            
        except Exception as parse_err:
            logger.warning(f"HTML parsing failed: {parse_err}, using cleaned text")
            # Clean fallback
            cleaned = re.sub(r'<[^>]+>', '', content)
            cleaned = re.sub(r'\s+', ' ', cleaned).strip()
            parsed["meaningful_text"] = cleaned[:5000]
        
        return parsed
        
    except Exception as e:
        logger.error(f"Error parsing content: {e}")
        return {
            "meaningful_text": content[:5000] if content else "",
            "company_name": "",
            "disclosure_type": "Web Content"
        }


@router.post("/kap", response_model=ScrapeResponse)
async def scrape_kap(
    request: ScrapeKAPRequest,
    background_tasks: BackgroundTasks,
    db_manager: DatabaseManager = Depends(get_db_manager)
):
    """
    Scrape KAP (Public Disclosure Platform) reports
    
    - **days_back**: Number of days to look back (1-365)
    - **company_symbols**: Optional list of specific company symbols
    - **download_pdfs**: Whether to download PDF attachments
    - **analyze_with_llm**: Whether to analyze reports with LLM
    """
    try:
        scraper = ProductionKAPScraper(
            use_test_data=False,
            use_llm=request.analyze_with_llm
        )

        # Run production KAP scraping
        result = await scraper.run_production_scrape()

        if not isinstance(result, dict):
            raise HTTPException(status_code=500, detail=f"Unexpected result type: {type(result)}")

        if not result.get("success", True):
            error_msg = result.get("error", "Unknown error")
            raise HTTPException(status_code=500, detail=f"Scraping failed: {error_msg}")

        reports_count = result.get("items_scraped", 0)
        saved_count = result.get("items_saved", 0)
        sentiment_count = result.get("sentiment_analyses", 0)

        return ScrapeResponse(
            success=True,
            message=f"Production KAP scraping completed: {reports_count} items scraped",
            data={
                "total_scraped": reports_count,
                "items_saved": saved_count,
                "sentiment_analyses": sentiment_count,
                "content_stats": result.get("content_stats", {})
            }
        )
    except Exception as e:
        logger.error(f"KAP scraping failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/bist", response_model=ScrapeResponse)
async def scrape_bist(
    request: ScrapeBISTRequest,
    db_manager: DatabaseManager = Depends(get_db_manager)
):
    """
    Scrape BIST (Borsa Istanbul) data
    
    - **data_type**: Type of data (companies, indices, commodities)
    - **start_date**: Start date for commodities (YYYYMMDD format)
    - **end_date**: End date for commodities (YYYYMMDD format)
    """
    try:
        scraper = BISTScraper(db_manager=db_manager)
        
        if request.data_type == "companies":
            result = await scraper.scrape()
        elif request.data_type == "indices":
            result = await scraper.scrape_indices()
        elif request.data_type == "commodities":
            if not request.start_date or not request.end_date:
                raise HTTPException(
                    status_code=400,
                    detail="start_date and end_date required for commodities"
                )
            result = await scraper.scrape_commodity_prices(
                request.start_date,
                request.end_date
            )
        else:
            result = await scraper.scrape()
        
        return ScrapeResponse(
            success=True,
            message=f"Successfully scraped BIST {request.data_type} data",
            data=result
        )
    except Exception as e:
        logger.error(f"BIST scraping failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/tradingview", response_model=ScrapeResponse)
async def scrape_tradingview(
    request: ScrapeTradingViewRequest,
    db_manager: DatabaseManager = Depends(get_db_manager)
):
    """
    Scrape TradingView data
    
    - **data_type**: Type of data (sectors, industries, crypto, or both)
    """
    try:
        scraper = TradingViewScraper(db_manager=db_manager)
        result = await scraper.scrape(data_type=request.data_type)
        
        # Handle result (can be dict or list)
        if not isinstance(result, dict):
            logger.error(f"TradingView returned unexpected type: {type(result)}")
            raise HTTPException(status_code=500, detail=f"Unexpected result type: {type(result)}")
        
        if not result.get('success', True):
            error_msg = result.get('error', 'Unknown error')
            raise HTTPException(status_code=500, detail=f"Scraping failed: {error_msg}")
        
        # Extract summary from result data
        result_data = result.get('data', {})
        if isinstance(result_data, dict):
            sectors = result_data.get('sectors', {})
            industries = result_data.get('industries', {})
            
            # Count records
            sectors_count = sectors.get('total_scraped', 0) if isinstance(sectors, dict) else 0
            industries_count = industries.get('total_scraped', 0) if isinstance(industries, dict) else 0
            total_scraped = sectors_count + industries_count
        else:
            total_scraped = 0
        
        data_type_name = request.data_type
        
        return ScrapeResponse(
            success=True,
            message=f"Successfully scraped TradingView {data_type_name} data",
            data={
                "total_scraped": total_scraped,
                "data_type": data_type_name,
                "details": result
            }
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"TradingView scraping failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/kap/configure-llm")
async def configure_kap_llm(
    request: LLMConfigRequest,
    db_manager: DatabaseManager = Depends(get_db_manager)
):
    """
    Configure LLM for KAP analysis
    
    This sets up the LLM provider that will be used for subsequent analysis requests.
    """
    try:
        scraper = ProductionKAPScraper(use_test_data=False, use_llm=False)
        
        config_dict = {}
        if request.base_url:
            config_dict["base_url"] = request.base_url
        if request.api_key:
            config_dict["api_key"] = request.api_key
        if request.model:
            config_dict["model"] = request.model
        if request.temperature is not None:
            config_dict["temperature"] = request.temperature
        
        scraper.configure_llm(
            provider_type=request.provider_type,
            **config_dict
        )
        
        return {
            "success": True,
            "message": f"LLM configured: {request.provider_type}",
            "provider": request.provider_type
        }
    except Exception as e:
        logger.error(f"LLM configuration failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/kap/batch", response_model=BatchJobResponse)
async def scrape_kap_batch(
    request: KAPBatchScrapeRequest,
    background_tasks: BackgroundTasks,
    db_manager: DatabaseManager = Depends(get_db_manager)
):
    """
    Start async batch scraping job for KAP reports
    
    Returns immediately with job ID. Use GET /api/v1/scrapers/jobs/{job_id} to check status.
    """
    try:
        # Create batch job
        job = job_manager.create_job(
            job_type="kap_batch",
            params={
                "days_back": request.days_back,
                "company_symbols": request.company_symbols or [],
                "download_pdfs": request.download_pdfs
            }
        )
        
        # Start background task
        async def run_batch_scrape():
            scraper = ProductionKAPScraper(use_test_data=False, use_llm=False)
            try:
                result = await scraper.run_production_scrape()
                
                reports_count = result.get("items_scraped", 0)
                saved_count = result.get("items_saved", 0)
                job_manager.update_job_status(
                    job.job_id,
                    JobStatus.COMPLETED,
                    result={
                        "total_scraped": reports_count,
                        "items_saved": saved_count,
                        "success": result.get("success", False)
                    }
                )
                
                # Send webhook notification if configured
                global _webhook_notifier
                if _webhook_notifier:
                    await _webhook_notifier.send_scraping_complete(
                        "kap_batch",
                        {"total_reports": reports_count, "success": True}
                    )
            except Exception as e:
                logger.error(f"Batch scraping failed: {e}")
                job_manager.update_job_status(
                    job.job_id,
                    JobStatus.FAILED,
                    result={"error": str(e)}
                )
        
        # Schedule background task
        asyncio.create_task(run_batch_scrape())
        
        return BatchJobResponse(
            job_id=job.job_id,
            status=job.status.value,
            message="KAP batch scraping job started",
            status_url=f"/api/v1/scrapers/jobs/{job.job_id}"
        )
        
    except Exception as e:
        logger.error(f"Failed to start batch job: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/jobs/{job_id}", response_model=JobStatusResponse)
async def get_job_status(job_id: str):
    """
    Get batch job status
    
    Returns current status, progress, and result (if completed).
    """
    job = job_manager.get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    
    return JobStatusResponse(**job.to_dict())


@router.post("/kap/sentiment", response_model=SentimentAnalysisResponse)
async def analyze_sentiment(
    request: SentimentAnalysisRequest,
    db_manager: DatabaseManager = Depends(get_db_manager)
):
    """
    Analyze sentiment for KAP reports
    
    Returns structured sentiment analysis with confidence scores, risk flags, etc.
    """
    try:
        scraper = ProductionKAPScraper(
            use_test_data=False,
            use_llm=request.use_llm,
            llm_provider=request.llm_provider
        )

        conn = db_manager.get_connection()
        cursor = None

        successful = 0
        failed = 0
        results = []

        try:
            cursor = conn.cursor()

            cursor.execute("SET search_path TO turkish_financial,public;")

            for report_id in request.report_ids:
                try:
                    cursor.execute("""
                        SELECT id, disclosure_id, company_name, disclosure_type, content
                        FROM kap_disclosures WHERE id = %s
                    """, (report_id,))

                    disclosure = cursor.fetchone()
                    if not disclosure:
                        failed += 1
                        results.append({
                            "report_id": report_id,
                            "success": False,
                            "error": "Disclosure not found"
                        })
                        continue

                    sentiment_data = scraper.analyze_sentiment(
                        content=disclosure[4],
                        company_name=disclosure[2],
                        disclosure_type=disclosure[3],
                        use_llm=request.use_llm
                    )

                    cursor.execute("SELECT id FROM kap_disclosure_sentiment WHERE disclosure_id = %s", (disclosure[0],))
                    existing = cursor.fetchone()

                    if existing:
                        cursor.execute("""
                            UPDATE kap_disclosure_sentiment SET
                                overall_sentiment = %s,
                                confidence = %s,
                                impact_horizon = %s,
                                key_drivers = %s,
                                risk_flags = %s,
                                tone_descriptors = %s,
                                target_audience = %s,
                                analysis_text = %s,
                                risk_level = %s,
                                analyzed_at = %s
                            WHERE disclosure_id = %s
                        """, (
                            sentiment_data['overall_sentiment'],
                            sentiment_data['confidence'],
                            sentiment_data['impact_horizon'],
                            sentiment_data['key_drivers'],
                            sentiment_data['risk_flags'],
                            sentiment_data['tone_descriptors'],
                            sentiment_data['target_audience'],
                            sentiment_data['analysis_text'],
                            sentiment_data['risk_level'],
                            datetime.now(),
                            disclosure[0]
                        ))
                    else:
                        cursor.execute("""
                            INSERT INTO kap_disclosure_sentiment 
                            (disclosure_id, overall_sentiment, confidence, impact_horizon, 
                             key_drivers, risk_flags, tone_descriptors, target_audience, 
                             analysis_text, risk_level, analyzed_at)
                            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                        """, (
                            disclosure[0],
                            sentiment_data['overall_sentiment'],
                            sentiment_data['confidence'],
                            sentiment_data['impact_horizon'],
                            sentiment_data['key_drivers'],
                            sentiment_data['risk_flags'],
                            sentiment_data['tone_descriptors'],
                            sentiment_data['target_audience'],
                            sentiment_data['analysis_text'],
                            sentiment_data['risk_level'],
                            datetime.now()
                        ))

                    successful += 1
                    results.append({
                        "report_id": report_id,
                        "success": True,
                        "sentiment": sentiment_data
                    })

                except Exception as e:
                    failed += 1
                    results.append({
                        "report_id": report_id,
                        "success": False,
                        "error": str(e)
                    })

            conn.commit()
        finally:
            if cursor:
                cursor.close()
            db_manager.return_connection(conn)

        # Send webhook notification if configured
        global _webhook_notifier
        if _webhook_notifier:
            positive = sum(1 for r in results if r.get("sentiment", {}).get('overall_sentiment') == 'positive')
            neutral = sum(1 for r in results if r.get("sentiment", {}).get('overall_sentiment') == 'neutral')
            negative = sum(1 for r in results if r.get("sentiment", {}).get('overall_sentiment') == 'negative')

            await _webhook_notifier.send_sentiment_analysis_complete(
                len(results), positive, neutral, negative
            )

        return SentimentAnalysisResponse(
            total_analyzed=len(results),
            successful=successful,
            failed=failed,
            results=results
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Sentiment analysis failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/kap/sentiment/auto", response_model=SentimentAnalysisResponse)
async def analyze_recent_sentiment(
    request: AutoSentimentRequest,
    background_tasks: BackgroundTasks,
    db_manager: DatabaseManager = Depends(get_db_manager)
):
    """
    Automatically analyze sentiment for recent KAP reports
    
    Finds reports from the last N days that don't have sentiment analysis
    and processes them automatically.
    """
    try:
        from psycopg2.extras import RealDictCursor

        # Get disclosures that need sentiment analysis
        conn = db_manager.get_connection()
        try:
            cursor = conn.cursor(cursor_factory=RealDictCursor)

            query = """
                SELECT d.id, d.company_name
                FROM turkish_financial.kap_disclosures d
                LEFT JOIN turkish_financial.kap_disclosure_sentiment s ON d.id = s.disclosure_id
                WHERE d.scraped_at >= NOW() - INTERVAL '%s days'
                AND d.content IS NOT NULL
                AND LENGTH(d.content) > 100
            """

            params = [request.days_back]

            if not request.force_reanalyze:
                query += " AND s.disclosure_id IS NULL"

            if request.company_codes:
                placeholders = ','.join(['%s'] * len(request.company_codes))
                query += f" AND d.company_name ILIKE ANY (ARRAY[{placeholders}])"
                params.extend([f"%{code}%" for code in request.company_codes])

            query += " ORDER BY d.scraped_at DESC LIMIT 50"

            cursor.execute(query, params)
            disclosures_to_analyze = cursor.fetchall()
        finally:
            db_manager.return_connection(conn)

        if not disclosures_to_analyze:
            return SentimentAnalysisResponse(
                total_analyzed=0,
                successful=0,
                failed=0,
                results=[]
            )

        report_ids = [row['id'] for row in disclosures_to_analyze]
        logger.info(f"Auto-analyzing sentiment for {len(report_ids)} disclosures")

        # Reuse the same logic as manual analysis
        result = await analyze_sentiment(
            SentimentAnalysisRequest(report_ids=report_ids, custom_prompt=None, use_llm=False),
            db_manager
        )

        return result
        
    except Exception as e:
        logger.error(f"Auto sentiment analysis failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/webhook/configure")
async def configure_webhook(request: WebhookConfigRequest):
    """
    Configure webhook notifications
    
    Set webhook URL for Discord, Slack, or custom endpoints.
    """
    global _webhook_notifier
    
    if request.enabled and request.webhook_url:
        _webhook_notifier = WebhookNotifier(request.webhook_url)
        return {
            "success": True,
            "message": "Webhook configured",
            "webhook_url": request.webhook_url[:50] + "..." if len(request.webhook_url) > 50 else request.webhook_url
        }
    else:
        _webhook_notifier = None
        return {
            "success": True,
            "message": "Webhook disabled"
        }

@router.post("/url/analyze", response_model=ScrapeResponse)
async def scrape_url_with_sentiment(
    request: URLSentimentRequest,
    db_manager: DatabaseManager = Depends(get_db_manager)
):
    """
    Scrape a URL and perform sentiment analysis, then insert to database
    
    - **url**: URL to scrape
    - **use_llm**: Use LLM for sentiment analysis (default: True)
    - **llm_provider**: LLM provider to use (default: huggingface)
    - **company_name**: Company name for context
    - **custom_prompt**: Custom analysis prompt
    
    Returns sentiment analysis result and inserts to database
    """
    try:
        from firecrawl import FirecrawlApp
        
        # Initialize Firecrawl to scrape the URL
        firecrawl = FirecrawlApp(api_key="", api_url="http://api:3002")
        
        logger.info(f"Scraping URL: {request.url}")
        
        # Attempt to scrape with Firecrawl
        try:
            scrape_result = firecrawl.scrape(
                request.url,
                formats=["markdown", "html"],
                wait_for=1500,
                timeout=15000
            )

            def _extract_scrape_content(result: Any) -> Dict[str, str]:
                extracted = {"markdown": "", "html": "", "content": ""}
                if not result:
                    return extracted

                if isinstance(result, dict):
                    extracted["markdown"] = result.get("markdown", "") or ""
                    extracted["html"] = result.get("html", "") or ""
                    extracted["content"] = result.get("content", "") or ""
                    if not extracted["content"]:
                        extracted["content"] = result.get("text", "") or ""
                    return extracted

                for key in ["markdown", "html", "content", "text", "page_content"]:
                    if hasattr(result, key):
                        value = getattr(result, key)
                        if isinstance(value, str) and value:
                            if key == "markdown":
                                extracted["markdown"] = value
                            elif key == "html":
                                extracted["html"] = value
                            else:
                                extracted["content"] = value

                return extracted

            extracted = _extract_scrape_content(scrape_result)
            scraped_markdown = extracted["markdown"]
            scraped_html = extracted["html"]
            content = extracted["content"] or scraped_markdown or scraped_html
        except Exception as scrape_err:
            logger.warning(f"Firecrawl scrape failed for {request.url}: {scrape_err}. Using fallback.")
            content = ""
            scraped_markdown = ""
            scraped_html = ""
        
        # Fallback: if no content from Firecrawl, try simple fetch
        raw_html = ""
        if not content or len(content.strip()) == 0:
            logger.info(f"Attempting fallback content retrieval from {request.url}")
            try:
                import httpx
                async with httpx.AsyncClient(timeout=10.0) as client:
                    response = await client.get(request.url, follow_redirects=True)
                    if response.status_code == 200:
                        raw_html = response.text
                        # Extract text from HTML (simple approach)
                        from html.parser import HTMLParser
                        class TextExtractor(HTMLParser):
                            def __init__(self):
                                super().__init__()
                                self.text = []
                            def handle_data(self, data):
                                text = data.strip()
                                if text:
                                    self.text.append(text)
                        
                        parser = TextExtractor()
                        parser.feed(response.text)
                        content = " ".join(parser.text[:2000])  # Limit to first 2000 words
            except Exception as fallback_err:
                logger.warning(f"Fallback fetch also failed: {fallback_err}")
        
        # Parse HTML content to extract meaningful data
        logger.info(f"Parsing content for meaningful information")
        
        # Check if this is KAP homepage with multiple disclosures
        kap_candidates = [scraped_markdown, scraped_html, raw_html, content]
        kap_candidates = [c for c in kap_candidates if isinstance(c, str) and c]
        kap_content = max(kap_candidates, key=len) if kap_candidates else content

        is_kap_homepage = (
            'kap.org.tr' in request.url and
            any(indicator in (kap_content or "").lower() for indicator in ['checkbox', 'bildirimler', 'dün', 'bugün', 'a.ş.', 'bankası', 'bildirim'])
        )
        
        if is_kap_homepage:
            logger.info("Detected KAP homepage with multiple disclosures")
            
            kap_disclosures = parse_kap_homepage_disclosures(kap_content)
            
            if kap_disclosures:
                # Process each disclosure separately
                total_inserted = 0
                total_sentiment = 0
                
                for disclosure in kap_disclosures:
                    try:
                        # Extract data
                        analysis_content = disclosure["meaningful_text"]
                        disclosure_type = disclosure.get("disclosure_type", "General Disclosure")
                        company_name = disclosure.get("company_name", "Unknown")
                        kap_disclosure_id = disclosure.get("disclosure_id", "unknown")
                        
                        # Ensure fields fit database constraints
                        company_name = company_name[:255]
                        disclosure_type = disclosure_type[:255]
                        
                        # Initialize scraper for sentiment analysis
                        scraper = ProductionKAPScraper(
                            use_llm=request.use_llm,
                            llm_provider=request.llm_provider
                        )
                        
                        # Analyze sentiment for each disclosure
                        content_for_analysis = analysis_content[:400] if len(analysis_content) > 400 else analysis_content
                        sentiment_data = scraper.analyze_sentiment(
                            content=content_for_analysis,
                            company_name=company_name,
                            disclosure_type=disclosure_type
                        )
                        
                        if sentiment_data:
                            # Insert to database
                            conn = db_manager.get_connection()
                            try:
                                cursor = conn.cursor()
                                cursor.execute("SET search_path TO turkish_financial,public;")
                                
                                # Create disclosure_id using KAP disclosure ID
                                from datetime import datetime
                                db_disclosure_id = f"kap_{kap_disclosure_id}"
                                
                                # Check if already exists
                                cursor.execute("""
                                    SELECT id FROM kap_disclosures 
                                    WHERE disclosure_id = %s
                                """, (db_disclosure_id,))
                                
                                existing_disclosure = cursor.fetchone()
                                
                                if not existing_disclosure:
                                    # Build disclosure data JSON
                                    disclosure_data = {
                                        "url": request.url,
                                        "source": "kap_homepage",
                                        "scraped_at": datetime.now().isoformat(),
                                        "kap_disclosure_id": kap_disclosure_id,
                                        "disclosure_date": disclosure.get("disclosure_date", ""),
                                        "content_length": len(analysis_content),
                                        "parsed_data": disclosure
                                    }
                                    
                                    cursor.execute("""
                                        INSERT INTO kap_disclosures 
                                        (disclosure_id, company_name, disclosure_type, content, data, scraped_at)
                                        VALUES (%s, %s, %s, %s, %s, CURRENT_TIMESTAMP)
                                        RETURNING id
                                    """, (
                                        db_disclosure_id,
                                        company_name,
                                        disclosure_type,
                                        analysis_content,
                                        json.dumps(disclosure_data)
                                    ))
                                    db_record_id = cursor.fetchone()[0]
                                    total_inserted += 1
                                else:
                                    db_record_id = existing_disclosure[0]
                                
                                # Insert sentiment analysis
                                cursor.execute("""
                                    INSERT INTO kap_disclosure_sentiment 
                                    (disclosure_id, overall_sentiment, confidence, impact_horizon, key_drivers, 
                                     risk_flags, tone_descriptors, target_audience, analysis_text, risk_level, analyzed_at)
                                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, CURRENT_TIMESTAMP)
                                    ON CONFLICT (disclosure_id) DO UPDATE SET
                                        overall_sentiment = EXCLUDED.overall_sentiment,
                                        confidence = EXCLUDED.confidence,
                                        analyzed_at = CURRENT_TIMESTAMP
                                """, (
                                    db_record_id,
                                    sentiment_data.get("overall_sentiment", "neutral"),
                                    sentiment_data.get("confidence", 0.0),
                                    sentiment_data.get("impact_horizon", "short-term"),
                                    json.dumps(sentiment_data.get("key_drivers", [])),
                                    json.dumps(sentiment_data.get("risk_flags", [])),
                                    json.dumps(sentiment_data.get("tone_descriptors", [])),
                                    sentiment_data.get("target_audience", "investors"),
                                    sentiment_data.get("analysis_text", ""),
                                    sentiment_data.get("risk_level", "low")
                                ))
                                total_sentiment += 1
                                
                                conn.commit()
                                logger.info(f"Processed disclosure {kap_disclosure_id} for {company_name}")
                                
                            except Exception as db_err:
                                logger.error(f"Database error for disclosure {kap_disclosure_id}: {db_err}")
                                conn.rollback()
                            finally:
                                db_manager.return_connection(conn)
                        
                    except Exception as disclosure_err:
                        logger.error(f"Error processing disclosure {disclosure.get('disclosure_id', 'unknown')}: {disclosure_err}")
                        continue
                
                return ScrapeResponse(
                    success=True,
                    message=f"Processed {len(kap_disclosures)} KAP disclosures from homepage",
                    data={
                        "total_disclosures": len(kap_disclosures),
                        "inserted_disclosures": total_inserted,
                        "sentiment_analyses": total_sentiment,
                        "url": request.url,
                        "source": "kap_homepage_multi_scrape"
                    }
                )
            else:
                logger.warning("No disclosures found on KAP homepage")
                return ScrapeResponse(
                    success=True,
                    message="No disclosures found on KAP homepage",
                    data={"url": request.url, "disclosures_found": 0}
                )
        
        # For non-KAP URLs or single content, use original logic
        parsed_data = parse_html_content(content)
        
        # Use parsed content if available, otherwise use raw content
        if parsed_data.get("meaningful_text"):
            analysis_content = parsed_data["meaningful_text"]
            disclosure_type = parsed_data.get("disclosure_type", "Web Content")
            company_name = parsed_data.get("company_name", request.company_name or "Unknown")
        else:
            analysis_content = content
            disclosure_type = "Web Content"
            company_name = request.company_name or "Unknown"
        
        # Ensure fields fit within database constraints (VARCHAR(255))
        company_name = (company_name or "Unknown")[:255]
        disclosure_type = (disclosure_type or "Web Content")[:255]
        
        if not analysis_content or len(analysis_content.strip()) == 0:
            raise HTTPException(status_code=400, detail="Failed to extract meaningful content from URL")
        
        # Initialize scraper with specified LLM provider
        scraper = ProductionKAPScraper(
            use_llm=request.use_llm,
            llm_provider=request.llm_provider
        )
        
        # Truncate content for sentiment analysis (BERT has 512 token limit, ~400 chars = ~100 tokens)
        # Use first 400 chars to stay well under the limit
        content_for_analysis = analysis_content[:400] if len(analysis_content) > 400 else analysis_content
        
        # Analyze sentiment
        logger.info(f"Analyzing sentiment for URL: {request.url}")
        sentiment_data = scraper.analyze_sentiment(
            content=content_for_analysis,
            company_name=company_name,
            disclosure_type=disclosure_type
        )
        
        if not sentiment_data:
            raise HTTPException(status_code=500, detail="Sentiment analysis failed")
        
        # Insert to database
        conn = db_manager.get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute("SET search_path TO turkish_financial,public;")
            
            # Create proper disclosure_id (short, unique identifier like working scrapers use)
            from datetime import datetime
            import hashlib
            url_hash = hashlib.md5(request.url.encode()).hexdigest()[:8]
            disclosure_id = f"url_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{url_hash}"
            
            # Check if similar disclosure already exists
            cursor.execute("""
                SELECT id FROM kap_disclosures 
                WHERE LOWER(company_name) = LOWER(%s) 
                ORDER BY scraped_at DESC LIMIT 1
            """, (company_name,))
            
            existing_disclosure = cursor.fetchone()
            
            if not existing_disclosure:
                # Build proper data JSON matching working records
                disclosure_data = {
                    "url": request.url,
                    "source": "url_scrape",
                    "scraped_at": datetime.now().isoformat(),
                    "company_provided": request.company_name,
                    "content_length": len(analysis_content),
                    "parsed_data": parsed_data
                }
                
                cursor.execute("""
                    INSERT INTO kap_disclosures 
                    (disclosure_id, company_name, disclosure_type, content, data, scraped_at)
                    VALUES (%s, %s, %s, %s, %s, CURRENT_TIMESTAMP)
                    RETURNING id
                """, (
                    disclosure_id,
                    company_name,
                    disclosure_type,
                    analysis_content,
                    json.dumps(disclosure_data)
                ))
                disclosure_id = cursor.fetchone()[0]
            else:
                disclosure_id = existing_disclosure[0]
            
            # Check if sentiment already exists
            cursor.execute(
                "SELECT id FROM kap_disclosure_sentiment WHERE disclosure_id = %s",
                (disclosure_id,)
            )
            existing_sentiment = cursor.fetchone()
            
            if existing_sentiment:
                # Update existing record
                cursor.execute("""
                    UPDATE kap_disclosure_sentiment SET
                        overall_sentiment = %s,
                        confidence = %s,
                        impact_horizon = %s,
                        key_drivers = %s,
                        risk_flags = %s,
                        tone_descriptors = %s,
                        target_audience = %s,
                        analysis_text = %s,
                        risk_level = %s,
                        analyzed_at = CURRENT_TIMESTAMP
                    WHERE disclosure_id = %s
                """, (
                    sentiment_data['overall_sentiment'],
                    sentiment_data['confidence'],
                    sentiment_data['impact_horizon'],
                    sentiment_data['key_drivers'],
                    sentiment_data['risk_flags'],
                    sentiment_data['tone_descriptors'],
                    sentiment_data['target_audience'],
                    sentiment_data['analysis_text'],
                    sentiment_data['risk_level'],
                    disclosure_id
                ))
            else:
                # Insert new record
                cursor.execute("""
                    INSERT INTO kap_disclosure_sentiment 
                    (disclosure_id, overall_sentiment, confidence, impact_horizon, 
                     key_drivers, risk_flags, tone_descriptors, target_audience, 
                     analysis_text, risk_level, analyzed_at)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, CURRENT_TIMESTAMP)
                """, (
                    disclosure_id,
                    sentiment_data['overall_sentiment'],
                    sentiment_data['confidence'],
                    sentiment_data['impact_horizon'],
                    sentiment_data['key_drivers'],
                    sentiment_data['risk_flags'],
                    sentiment_data['tone_descriptors'],
                    sentiment_data['target_audience'],
                    sentiment_data['analysis_text'],
                    sentiment_data['risk_level']
                ))
            
            conn.commit()
            db_manager.return_connection(conn)
            
            logger.info(f"Successfully analyzed and stored sentiment for URL: {request.url}")
            
            return ScrapeResponse(
                success=True,
                message="URL scraped, sentiment analyzed, and data inserted to database",
                data={
                    "url": request.url,
                    "disclosure_id": disclosure_id,
                    "sentiment": sentiment_data,
                    "provider": scraper.llm_analyzer.provider.__class__.__name__ if scraper.llm_analyzer else "None",
                    "content_length": len(content)
                }
            )
            
        except DatabaseManager.PoolExhaustedError as e:
            logger.error(f"Database connection pool exhausted: {e}")
            raise HTTPException(status_code=503, detail="Database temporarily unavailable")
        except Exception as e:
            logger.error(f"Database error during URL sentiment analysis: {e}", exc_info=True)
            if conn:
                db_manager.return_connection(conn)
            raise HTTPException(status_code=500, detail=f"Database error: {str(e)}")
            
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"URL sentiment analysis failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))