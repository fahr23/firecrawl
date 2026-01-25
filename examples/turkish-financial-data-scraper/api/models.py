"""
Pydantic models for API requests and responses
"""
from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any
from datetime import datetime, date


# Request Models
class ScrapeKAPRequest(BaseModel):
    """Request model for KAP scraping"""
    days_back: int = Field(default=7, ge=1, le=365, description="Number of days to look back")
    company_symbols: Optional[List[str]] = Field(default=None, description="Specific company symbols to scrape")
    download_pdfs: bool = Field(default=False, description="Download PDF attachments")
    analyze_with_llm: bool = Field(default=False, description="Analyze reports with LLM")


class ScrapeBISTRequest(BaseModel):
    """Request model for BIST scraping"""
    data_type: str = Field(default="companies", description="Type: companies, indices, or commodities")
    start_date: Optional[str] = Field(default=None, description="Start date for commodities (YYYYMMDD)")
    end_date: Optional[str] = Field(default=None, description="End date for commodities (YYYYMMDD)")


class ScrapeTradingViewRequest(BaseModel):
    """Request model for TradingView scraping"""
    data_type: str = Field(default="both", description="Type: sectors, industries, crypto, or both")


class LLMConfigRequest(BaseModel):
    """Request model for LLM configuration"""
    provider_type: str = Field(default="local", description="Provider: local or openai")
    base_url: Optional[str] = Field(default="http://localhost:1234/v1", description="Local LLM base URL")
    api_key: Optional[str] = Field(default=None, description="API key for OpenAI")
    model: Optional[str] = Field(default=None, description="Model name")
    temperature: float = Field(default=0.7, ge=0.0, le=2.0)


class QueryReportsRequest(BaseModel):
    """Request model for querying reports"""
    company_code: Optional[str] = None
    start_date: Optional[date] = None
    end_date: Optional[date] = None
    report_type: Optional[str] = None
    limit: int = Field(default=100, ge=1, le=1000)
    offset: int = Field(default=0, ge=0)


# Response Models
class ScrapeResponse(BaseModel):
    """Generic scraping response"""
    success: bool
    message: str
    data: Optional[Dict[str, Any]] = None
    timestamp: datetime = Field(default_factory=datetime.now)


class ReportResponse(BaseModel):
    """Single report response"""
    id: int
    company_code: str
    company_name: Optional[str]
    report_type: Optional[str]
    report_date: Optional[date]
    title: Optional[str]
    summary: Optional[str]
    data: Optional[Dict[str, Any]] = None
    scraped_at: datetime


class ReportsListResponse(BaseModel):
    """List of reports response"""
    total: int
    limit: int
    offset: int
    reports: List[ReportResponse]


class CompanyResponse(BaseModel):
    """Company information response"""
    code: str
    name: str
    sector: Optional[str] = None
    industry: Optional[str] = None


class HealthResponse(BaseModel):
    """Health check response"""
    status: str
    database: str
    timestamp: datetime = Field(default_factory=datetime.now)


class SentimentAnalysisRequest(BaseModel):
    """Request for sentiment analysis"""
    report_ids: List[int] = Field(description="List of report IDs to analyze")
    prompt: Optional[str] = Field(default=None, description="Custom analysis prompt")


class SentimentResponse(BaseModel):
    """Sentiment analysis response"""
    report_id: int
    overall_sentiment: str  # positive, neutral, negative
    confidence: float
    impact_horizon: str  # short_term, medium_term, long_term
    key_drivers: List[str]
    risk_flags: List[str]
    analysis_text: str
    analyzed_at: datetime = Field(default_factory=datetime.now)


class BatchScrapeRequest(BaseModel):
    """Request model for batch scraping"""
    urls: List[str] = Field(description="List of URLs to scrape")
    formats: List[str] = Field(default=["markdown"], description="Output formats")
    max_pages: Optional[int] = Field(default=None, description="Maximum pages to scrape")


class BatchJobResponse(BaseModel):
    """Batch job response"""
    job_id: str
    status: str
    message: str
    status_url: Optional[str] = None
    created_at: datetime = Field(default_factory=datetime.now)


class JobStatusResponse(BaseModel):
    """Job status response"""
    job_id: str
    job_type: str
    status: str
    progress: int
    total: int
    created_at: datetime
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    result: Optional[Dict[str, Any]] = None
    error: Optional[str] = None


class SentimentAnalysisRequest(BaseModel):
    """Request for sentiment analysis"""
    report_ids: List[int] = Field(description="List of report IDs to analyze")
    custom_prompt: Optional[str] = Field(default=None, description="Custom analysis prompt")


class SentimentAnalysisResponse(BaseModel):
    """Sentiment analysis batch response"""
    total_analyzed: int
    successful: int
    failed: int
    results: List[Dict[str, Any]]


class WebhookConfigRequest(BaseModel):
    """Webhook configuration request"""
    webhook_url: str = Field(description="Webhook URL (Discord, Slack, or custom)")
    enabled: bool = Field(default=True, description="Enable/disable webhooks")
