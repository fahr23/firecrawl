# Complete User Guide - Turkish Financial Data Scraper

## 📚 Table of Contents

1. [Getting Started](#getting-started)
2. [REST API Usage](#rest-api-usage)
3. [Sentiment Analysis](#sentiment-analysis)
4. [Batch Processing](#batch-processing)
5. [Webhook Notifications](#webhook-notifications)
6. [Querying Data](#querying-data)
7. [CLI Usage](#cli-usage)
8. [Python SDK Usage](#python-sdk-usage)
9. [Best Practices](#best-practices)
10. [Troubleshooting](#troubleshooting)

---

## Getting Started

### Prerequisites

- Python 3.8+
- PostgreSQL database
- Firecrawl API key or self-hosted Firecrawl instance

### Installation

```bash
# Clone or navigate to the project
cd examples/turkish-financial-data-scraper

# Install dependencies
pip install -r requirements.txt

# Configure environment
cp .env.example .env
# Edit .env with your credentials
```

### Configuration

Edit `.env` file:

```env
# Firecrawl Configuration
FIRECRAWL_API_KEY=your_api_key_here
# OR for self-hosted:
FIRECRAWL_BASE_URL=http://api:3002

# Database Configuration
DB_HOST=localhost
DB_PORT=5432
DB_NAME=backtofuture
DB_USER=backtofuture
DB_PASSWORD=back2future
DB_SCHEMA=turkish_financial

# LLM Configuration (for sentiment analysis)
OPENAI_API_KEY=your_openai_key  # Optional
# OR for local LLM:
OLLAMA_BASE_URL=http://localhost:11434
```

### Start the API Server

```bash
python api_server.py
```

The API will be available at:
- **Base URL**: http://localhost:8000
- **Interactive Docs**: http://localhost:8000/docs
- **ReDoc**: http://localhost:8000/redoc

---

## REST API Usage

### Health Check

```bash
curl http://localhost:8000/api/v1/health
```

**Response**:
```json
{
  "status": "healthy",
  "database": "connected",
  "timestamp": "2025-01-23T10:30:00"
}
```

---

### 1. Scraping KAP Reports

Scrape financial reports from KAP (Public Disclosure Platform).

#### Endpoint: `POST /api/v1/scrapers/kap`

**Request**:
```bash
curl -X POST http://localhost:8000/api/v1/scrapers/kap \
  -H "Content-Type: application/json" \
  -d '{
    "days_back": 7,
    "download_pdfs": true,
    "company_codes": ["AKBNK", "GARAN"],
    "report_types": ["Financial Statement", "Material Event"]
  }'
```

**Request Parameters**:
- `days_back` (int): Number of days to look back (default: 7)
- `download_pdfs` (bool): Download PDF attachments (default: false)
- `company_codes` (list, optional): Filter by specific companies
- `report_types` (list, optional): Filter by report types

**Response**:
```json
{
  "success": true,
  "message": "Successfully scraped KAP reports",
  "data": {
    "total_scraped": 45,
    "new_reports": 23,
    "updated_reports": 22,
    "companies": ["AKBNK", "GARAN", "THYAO"]
  }
}
```

#### Python Example

```python
import requests

url = "http://localhost:8000/api/v1/scrapers/kap"
payload = {
    "days_back": 7,
    "download_pdfs": True,
    "company_codes": ["AKBNK", "GARAN"]
}

response = requests.post(url, json=payload)
result = response.json()
print(f"Scraped {result['data']['total_scraped']} reports")
```

---

### 2. Scraping BIST Data

Scrape Borsa Istanbul company listings, indices, or commodity prices.

#### Endpoint: `POST /api/v1/scrapers/bist`

**Request**:
```bash
# Scrape companies
curl -X POST http://localhost:8000/api/v1/scrapers/bist \
  -H "Content-Type: application/json" \
  -d '{"data_type": "companies"}'

# Scrape indices
curl -X POST http://localhost:8000/api/v1/scrapers/bist \
  -H "Content-Type: application/json" \
  -d '{"data_type": "indices"}'

# Scrape commodity prices
curl -X POST http://localhost:8000/api/v1/scrapers/bist \
  -H "Content-Type: application/json" \
  -d '{
    "data_type": "commodities",
    "start_date": "20250101",
    "end_date": "20250131"
  }'
```

**Response**:
```json
{
  "success": true,
  "message": "Successfully scraped BIST companies data",
  "data": {
    "companies_scraped": 450,
    "new_companies": 5,
    "updated_companies": 445
  }
}
```

---

### 3. Scraping TradingView Data

Scrape sector and industry classifications.

#### Endpoint: `POST /api/v1/scrapers/tradingview`

**Request**:
```bash
curl -X POST http://localhost:8000/api/v1/scrapers/tradingview \
  -H "Content-Type: application/json" \
  -d '{"data_type": "both"}'
```

**Options for `data_type`**:
- `"sectors"`: Only sectors
- `"industries"`: Only industries
- `"crypto"`: Cryptocurrency symbols
- `"both"`: Sectors and industries

---

## Sentiment Analysis

Analyze KAP reports with structured sentiment analysis using LLMs.

### Endpoint: `POST /api/v1/scrapers/kap/sentiment`

**Request**:
```bash
curl -X POST http://localhost:8000/api/v1/scrapers/kap/sentiment \
  -H "Content-Type: application/json" \
  -d '{
    "report_ids": [1, 2, 3, 4, 5],
    "custom_prompt": "Focus on financial risks and opportunities"
  }'
```

**Request Parameters**:
- `report_ids` (list, required): List of report IDs to analyze
- `custom_prompt` (string, optional): Custom analysis prompt

**Response**:
```json
{
  "total_analyzed": 5,
  "successful": 4,
  "failed": 1,
  "results": [
    {
      "report_id": 1,
      "report_title": "Q4 2024 Financial Statement",
      "sentiment": {
        "overall_sentiment": "positive",
        "confidence": 0.85,
        "impact_horizon": "medium_term",
        "key_drivers": [
          "Revenue growth of 15%",
          "Strong market position",
          "Expansion into new markets"
        ],
        "risk_flags": [
          "Increased debt-to-equity ratio"
        ],
        "tone_descriptors": ["optimistic", "confident"],
        "target_audience": "retail_investors",
        "analysis_text": "Detaylı analiz metni Türkçe olarak..."
      },
      "analyzed_at": "2025-01-23T10:30:00"
    }
  ]
}
```

### Sentiment Fields Explained

- **overall_sentiment**: `"positive"`, `"neutral"`, or `"negative"`
- **confidence**: Score from 0.0 to 1.0
- **impact_horizon**: `"short_term"`, `"medium_term"`, or `"long_term"`
- **key_drivers**: List of positive/negative factors
- **risk_flags**: List of risk indicators
- **tone_descriptors**: Adjectives describing the tone
- **target_audience**: `"retail_investors"`, `"institutional"`, or `null`
- **analysis_text**: Detailed analysis in Turkish

### Python Example

```python
import requests

url = "http://localhost:8000/api/v1/scrapers/kap/sentiment"
payload = {
    "report_ids": [1, 2, 3],
    "custom_prompt": "Analyze financial risks and growth opportunities"
}

response = requests.post(url, json=payload)
result = response.json()

for item in result["results"]:
    sentiment = item["sentiment"]
    print(f"Report {item['report_id']}: {sentiment['overall_sentiment']}")
    print(f"Confidence: {sentiment['confidence']}")
    print(f"Key Drivers: {', '.join(sentiment['key_drivers'])}")
```

---

## Batch Processing

Process large-scale scraping jobs asynchronously with status tracking.

### Endpoint: `POST /api/v1/scrapers/kap/batch`

**Request**:
```bash
curl -X POST http://localhost:8000/api/v1/scrapers/kap/batch \
  -H "Content-Type: application/json" \
  -d '{
    "days_back": 30,
    "download_pdfs": false,
    "company_codes": ["AKBNK", "GARAN", "THYAO"]
  }'
```

**Response**:
```json
{
  "job_id": "batch_1234567890",
  "status": "pending",
  "message": "Batch job created successfully",
  "created_at": "2025-01-23T10:30:00"
}
```

### Check Job Status

#### Endpoint: `GET /api/v1/scrapers/jobs/{job_id}`

**Request**:
```bash
curl http://localhost:8000/api/v1/scrapers/jobs/batch_1234567890
```

**Response**:
```json
{
  "job_id": "batch_1234567890",
  "status": "running",
  "progress": 15,
  "total": 100,
  "message": "Processing 15 of 100 reports",
  "created_at": "2025-01-23T10:30:00",
  "updated_at": "2025-01-23T10:32:15",
  "result": null
}
```

**Job Status Values**:
- `"pending"`: Job created, not started
- `"running"`: Job in progress
- `"completed"`: Job finished successfully
- `"failed"`: Job failed with error

### Python Example

```python
import requests
import time

# Create batch job
url = "http://localhost:8000/api/v1/scrapers/kap/batch"
payload = {
    "days_back": 30,
    "company_codes": ["AKBNK", "GARAN"]
}

response = requests.post(url, json=payload)
job = response.json()
job_id = job["job_id"]

# Poll for status
while True:
    status_url = f"http://localhost:8000/api/v1/scrapers/jobs/{job_id}"
    status_response = requests.get(status_url)
    status = status_response.json()
    
    print(f"Status: {status['status']}, Progress: {status['progress']}/{status['total']}")
    
    if status["status"] in ["completed", "failed"]:
        break
    
    time.sleep(2)  # Poll every 2 seconds

if status["status"] == "completed":
    print(f"Job completed! Result: {status['result']}")
```

---

## Webhook Notifications

Configure webhooks to receive real-time notifications for scraping events.

### Configure Webhook

#### Endpoint: `POST /api/v1/scrapers/webhook/configure`

**Request**:
```bash
# Discord webhook
curl -X POST http://localhost:8000/api/v1/scrapers/webhook/configure \
  -H "Content-Type: application/json" \
  -d '{
    "webhook_url": "https://discord.com/api/webhooks/YOUR_WEBHOOK_ID/YOUR_TOKEN",
    "webhook_type": "discord",
    "notify_on_completion": true,
    "notify_on_error": true,
    "notify_on_sentiment": true
  }'

# Slack webhook
curl -X POST http://localhost:8000/api/v1/scrapers/webhook/configure \
  -H "Content-Type: application/json" \
  -d '{
    "webhook_url": "https://hooks.slack.com/services/YOUR/WEBHOOK/URL",
    "webhook_type": "slack",
    "notify_on_completion": true,
    "notify_on_error": true
  }'
```

**Request Parameters**:
- `webhook_url` (string, required): Webhook URL
- `webhook_type` (string, required): `"discord"`, `"slack"`, or `"generic"`
- `notify_on_completion` (bool): Notify when scraping completes
- `notify_on_error` (bool): Notify on errors
- `notify_on_sentiment` (bool): Notify when sentiment analysis completes

**Response**:
```json
{
  "success": true,
  "message": "Webhook configured successfully",
  "webhook_type": "discord"
}
```

### Webhook Payload Examples

**Scraping Completion**:
```json
{
  "event": "scraping_completed",
  "timestamp": "2025-01-23T10:30:00",
  "data": {
    "total_scraped": 45,
    "new_reports": 23,
    "duration_seconds": 120
  }
}
```

**Error Notification**:
```json
{
  "event": "scraping_error",
  "timestamp": "2025-01-23T10:30:00",
  "error": "Connection timeout",
  "details": "Failed to scrape company AKBNK"
}
```

**Sentiment Analysis Completion**:
```json
{
  "event": "sentiment_analysis_completed",
  "timestamp": "2025-01-23T10:30:00",
  "data": {
    "total_analyzed": 5,
    "positive": 3,
    "neutral": 1,
    "negative": 1
  }
}
```

---

## Querying Data

Query scraped data from the database.

### Query KAP Reports

#### Endpoint: `GET /api/v1/reports/kap`

**Request**:
```bash
# Get all reports
curl "http://localhost:8000/api/v1/reports/kap?limit=10"

# Filter by company
curl "http://localhost:8000/api/v1/reports/kap?company_code=AKBNK&limit=10"

# Filter by date range
curl "http://localhost:8000/api/v1/reports/kap?start_date=2025-01-01&end_date=2025-01-31"

# Filter by report type
curl "http://localhost:8000/api/v1/reports/kap?report_type=Financial%20Statement"

# Combined filters with pagination
curl "http://localhost:8000/api/v1/reports/kap?company_code=AKBNK&start_date=2025-01-01&limit=20&offset=0"
```

**Query Parameters**:
- `company_code` (string, optional): Filter by company code
- `start_date` (date, optional): Start date (YYYY-MM-DD)
- `end_date` (date, optional): End date (YYYY-MM-DD)
- `report_type` (string, optional): Filter by report type
- `limit` (int, default: 100): Number of results (1-1000)
- `offset` (int, default: 0): Pagination offset

**Response**:
```json
{
  "total": 150,
  "limit": 10,
  "offset": 0,
  "reports": [
    {
      "id": 1,
      "company_code": "AKBNK",
      "company_name": "Akbank T.A.Ş.",
      "report_type": "Financial Statement",
      "report_date": "2025-01-20",
      "title": "Q4 2024 Financial Statement",
      "summary": "Financial results for Q4 2024...",
      "scraped_at": "2025-01-20T10:00:00"
    }
  ]
}
```

### Query Sentiment Data

#### Endpoint: `GET /api/v1/reports/kap/sentiment/query`

**Request**:
```bash
# Query by sentiment type
curl "http://localhost:8000/api/v1/reports/kap/sentiment/query?sentiment=positive&limit=10"

# Query by confidence threshold
curl "http://localhost:8000/api/v1/reports/kap/sentiment/query?min_confidence=0.8"

# Query by impact horizon
curl "http://localhost:8000/api/v1/reports/kap/sentiment/query?impact_horizon=medium_term"

# Query by date range
curl "http://localhost:8000/api/v1/reports/kap/sentiment/query?start_date=2025-01-01&end_date=2025-01-31"
```

**Query Parameters**:
- `sentiment` (string, optional): `"positive"`, `"neutral"`, or `"negative"`
- `min_confidence` (float, optional): Minimum confidence score (0.0-1.0)
- `impact_horizon` (string, optional): `"short_term"`, `"medium_term"`, or `"long_term"`
- `start_date` (date, optional): Start date
- `end_date` (date, optional): End date
- `limit` (int, default: 100): Number of results
- `offset` (int, default: 0): Pagination offset

**Response**:
```json
{
  "total": 25,
  "limit": 10,
  "offset": 0,
  "results": [
    {
      "report_id": 1,
      "report_title": "Q4 2024 Financial Statement",
      "company_code": "AKBNK",
      "sentiment": {
        "overall_sentiment": "positive",
        "confidence": 0.85,
        "impact_horizon": "medium_term",
        "key_drivers": ["Revenue growth", "Market expansion"],
        "risk_flags": [],
        "tone_descriptors": ["optimistic"],
        "target_audience": "retail_investors",
        "analysis_text": "Detaylı analiz..."
      },
      "analyzed_at": "2025-01-23T10:30:00"
    }
  ]
}
```

### Get Sentiment for Specific Report

#### Endpoint: `GET /api/v1/reports/kap/sentiment/{report_id}`

**Request**:
```bash
curl http://localhost:8000/api/v1/reports/kap/sentiment/1
```

**Response**:
```json
{
  "report_id": 1,
  "report_title": "Q4 2024 Financial Statement",
  "company_code": "AKBNK",
  "sentiment": {
    "overall_sentiment": "positive",
    "confidence": 0.85,
    "impact_horizon": "medium_term",
    "key_drivers": ["Revenue growth"],
    "risk_flags": [],
    "tone_descriptors": ["optimistic"],
    "target_audience": "retail_investors",
    "analysis_text": "Detaylı analiz..."
  },
  "analyzed_at": "2025-01-23T10:30:00"
}
```

---

## CLI Usage

Use the command-line interface for direct scraping.

### Basic Usage

```bash
# Scrape all data sources
python main.py --all

# Scrape specific scraper
python main.py --scraper kap --days 7

# Scrape with PDF download
python main.py --scraper kap --days 7 --download-pdfs

# Scrape specific companies
python main.py --scraper kap --days 7 --companies AKBNK GARAN THYAO
```

### Available Commands

```bash
# KAP scraper
python main.py --scraper kap --days 7
python main.py --scraper kap --days 30 --download-pdfs
python main.py --scraper kap --days 7 --companies AKBNK GARAN

# BIST scraper
python main.py --scraper bist --data-type companies
python main.py --scraper bist --data-type indices
python main.py --scraper bist --data-type commodities --start-date 20250101 --end-date 20250131

# TradingView scraper
python main.py --scraper tradingview --data-type sectors
python main.py --scraper tradingview --data-type industries
python main.py --scraper tradingview --data-type both
```

### Scheduled Scraping

Use the scheduler for automated scraping:

```bash
python scheduler.py
```

Configure in `scheduler.py`:
- Daily scraping at specific times
- Hourly commodity price updates
- Weekly index updates

---

## Python SDK Usage

Use the Python SDK for programmatic access.

### Basic Scraping

```python
from scrapers.kap_scraper import KAPScraper
from database.db_manager import DatabaseManager

# Initialize
db = DatabaseManager()
scraper = KAPScraper(db_manager=db)

# Scrape reports
result = await scraper.scrape(days_back=7, download_pdfs=True)
print(f"Scraped {result['total_scraped']} reports")
```

### Sentiment Analysis

```python
from utils.llm_analyzer import LLMAnalyzer, LLMProvider
from database.db_manager import DatabaseManager

# Initialize analyzer
db = DatabaseManager()
provider = LLMProvider()  # Uses OPENAI_API_KEY or OLLAMA_BASE_URL
analyzer = LLMAnalyzer(provider=provider, db_manager=db)

# Analyze sentiment
content = "Financial report content here..."
sentiment = analyzer.analyze_sentiment(content, report_id=1)

if sentiment:
    print(f"Sentiment: {sentiment.overall_sentiment}")
    print(f"Confidence: {sentiment.confidence}")
    print(f"Key Drivers: {sentiment.key_drivers}")
```

### Batch Processing

```python
from utils.batch_job_manager import job_manager, JobStatus
import asyncio

# Create batch job
job = job_manager.create_job(
    job_type="kap_scraping",
    params={"days_back": 30, "company_codes": ["AKBNK"]}
)

print(f"Job ID: {job.job_id}")

# Check status
while True:
    job = job_manager.get_job(job.job_id)
    print(f"Status: {job.status}, Progress: {job.progress}/{job.total}")
    
    if job.status in [JobStatus.COMPLETED, JobStatus.FAILED]:
        break
    
    await asyncio.sleep(2)
```

### Parallel Pagination

```python
from scrapers.base_scraper import BaseScraper

class MyScraper(BaseScraper):
    async def scrape_page(self, page_num):
        # Your scraping logic
        return data

scraper = MyScraper()
results = await scraper.scrape_paginated_parallel(
    total_pages=10,
    max_concurrent=5
)
```

---

## Best Practices

### 1. Rate Limiting

- Use `RATE_LIMIT_PER_MINUTE` in `.env` to avoid overwhelming servers
- Default: 30 requests per minute
- Adjust based on target server capacity

### 2. Error Handling

```python
try:
    result = await scraper.scrape(days_back=7)
except Exception as e:
    logger.error(f"Scraping failed: {e}")
    # Implement retry logic
```

### 3. Batch Processing for Large Jobs

For scraping many reports:
- Use batch endpoint instead of synchronous scraping
- Poll job status instead of waiting
- Process results asynchronously

### 4. Sentiment Analysis

- Analyze reports in batches for efficiency
- Use custom prompts for specific analysis needs
- Store results for historical analysis
- Query sentiment data for trends

### 5. Webhook Configuration

- Configure webhooks for production monitoring
- Use Discord/Slack for team notifications
- Monitor error notifications closely

### 6. Database Schema Isolation

- Use `DB_SCHEMA` to isolate project data
- Default schema: `turkish_financial`
- Prevents conflicts with other applications

### 7. Parallel Processing

- Use parallel pagination for better performance
- Adjust `MAX_CONCURRENT_TASKS` based on resources
- Monitor system resources during scraping

---

## Troubleshooting

### Common Issues

#### 1. Database Connection Failed

**Error**: `could not connect to server`

**Solution**:
- Check database is running: `docker ps | grep postgres`
- Verify `.env` configuration
- Check network connectivity

#### 2. Firecrawl API Errors

**Error**: `Firecrawl API request failed`

**Solution**:
- Verify `FIRECRAWL_API_KEY` or `FIRECRAWL_BASE_URL` in `.env`
- Check API quota/limits
- Verify network connectivity

#### 3. Sentiment Analysis Fails

**Error**: `LLM analysis failed`

**Solution**:
- Check `OPENAI_API_KEY` or `OLLAMA_BASE_URL` in `.env`
- Verify LLM service is accessible
- Check content length (may be too long)

#### 4. Batch Job Stuck

**Error**: Job status remains "running"

**Solution**:
- Check server logs for errors
- Verify database connection
- Restart API server if needed

#### 5. Webhook Not Working

**Error**: No notifications received

**Solution**:
- Verify webhook URL is correct
- Check webhook service is accessible
- Test webhook URL manually
- Check notification flags in configuration

---

## Additional Resources

- [API Documentation](API_DOCUMENTATION.md) - Complete API reference
- [Enhanced Features](API_ENHANCED_FEATURES.md) - Advanced features guide
- [Architecture Guide](DDD_ARCHITECTURE.md) - System architecture
- [Testing Guide](TESTING_GUIDE.md) - Testing instructions
- [Quick Start](QUICK_START_ENHANCED.md) - Quick start guide

---

**Last Updated**: January 23, 2025
