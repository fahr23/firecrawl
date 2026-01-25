"""
Scraper endpoints
"""
import logging
import asyncio
from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks
from typing import Dict, Any, Optional
from datetime import datetime, timedelta

from api.models import (
    ScrapeKAPRequest, ScrapeBISTRequest, ScrapeTradingViewRequest,
    ScrapeResponse, LLMConfigRequest, BatchScrapeRequest, BatchJobResponse,
    JobStatusResponse, SentimentAnalysisRequest, SentimentAnalysisResponse,
    WebhookConfigRequest
)
from api.dependencies import get_db_manager, get_config
from scrapers.kap_scraper import KAPScraper
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
        scraper = KAPScraper(db_manager=db_manager)
        
        # Run scraping (can be async background task for long operations)
        result = await scraper.scrape_with_analysis(
            days_back=request.days_back,
            company_symbols=request.company_symbols,
            download_pdfs=request.download_pdfs,
            analyze_with_llm=request.analyze_with_llm
        )
        
        return ScrapeResponse(
            success=True,
            message=f"Successfully scraped {result.get('total_reports', 0)} KAP reports",
            data=result
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
        
        return ScrapeResponse(
            success=True,
            message=f"Successfully scraped TradingView {request.data_type} data",
            data=result
        )
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
        scraper = KAPScraper(db_manager=db_manager)
        
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
    request: BatchScrapeRequest,
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
                "urls": request.urls,
                "formats": request.formats,
                "max_pages": request.max_pages
            }
        )
        
        # Update total
        job_manager.update_job_status(
            job.job_id,
            JobStatus.PENDING,
            total=len(request.urls)
        )
        
        # Start background task
        async def run_batch_scrape():
            scraper = KAPScraper(db_manager=db_manager)
            results = []
            
            for i, url in enumerate(request.urls):
                try:
                    result = await scraper.scrape_url(url, formats=request.formats)
                    results.append(result)
                    job_manager.update_job_status(
                        job.job_id,
                        JobStatus.RUNNING,
                        progress=i + 1
                    )
                except Exception as e:
                    logger.error(f"Error scraping {url}: {e}")
                    results.append({"url": url, "success": False, "error": str(e)})
            
            job_manager.update_job_status(
                job.job_id,
                JobStatus.COMPLETED,
                result={"total": len(results), "successful": sum(1 for r in results if r.get("success"))}
            )
            
            # Send webhook notification if configured
            global _webhook_notifier
            if _webhook_notifier:
                await _webhook_notifier.send_scraping_complete(
                    "kap_batch",
                    {"total_urls": len(request.urls), "successful": sum(1 for r in results if r.get("success"))}
                )
        
        # Schedule background task
        asyncio.create_task(run_batch_scrape())
        
        return BatchJobResponse(
            job_id=job.job_id,
            status=job.status.value,
            message="Batch scraping job started",
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
        # Use DDD architecture with dependency injection
        from application.dependencies import get_analyze_sentiment_use_case
        
        # Get configured use case
        use_case = get_analyze_sentiment_use_case(db_manager)
        
        # Execute use case
        result = await use_case.execute(
            report_ids=request.report_ids,
            custom_prompt=request.custom_prompt
        )
        
        # Send webhook notification if configured
        global _webhook_notifier
        if _webhook_notifier:
            positive = sum(1 for r in result["results"] if r['sentiment']['overall_sentiment'] == 'positive')
            neutral = sum(1 for r in result["results"] if r['sentiment']['overall_sentiment'] == 'neutral')
            negative = sum(1 for r in result["results"] if r['sentiment']['overall_sentiment'] == 'negative')
            
            await _webhook_notifier.send_sentiment_analysis_complete(
                len(result["results"]), positive, neutral, negative
            )
        
        return SentimentAnalysisResponse(**result)
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Sentiment analysis failed: {e}", exc_info=True)
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
