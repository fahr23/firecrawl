# Enhanced API Features Documentation

## Overview

The Turkish Financial Data Scraper API now includes advanced features for batch processing, sentiment analysis, webhook notifications, and parallel pagination.

---

## 🚀 New Features

### 1. Structured Sentiment Analysis

Analyze KAP reports with structured JSON output including confidence scores, risk flags, and impact horizons.

#### Endpoint: `POST /api/v1/scrapers/kap/sentiment`

**Request:**
```json
{
  "report_ids": [1, 2, 3, 4, 5],
  "custom_prompt": "Optional custom analysis prompt"
}
```

**Response:**
```json
{
  "total_analyzed": 5,
  "successful": 4,
  "failed": 1,
  "results": [
    {
      "report_id": 1,
      "sentiment": {
        "overall_sentiment": "positive",
        "confidence": 0.85,
        "impact_horizon": "medium_term",
        "key_drivers": [
          "Revenue growth of 15%",
          "Strong market position"
        ],
        "risk_flags": [],
        "tone_descriptors": ["optimistic", "confident"],
        "target_audience": "retail_investors",
        "analysis_text": "Detaylı analiz metni..."
      }
    }
  ]
}
```

**Example:**
```bash
curl -X POST http://localhost:8000/api/v1/scrapers/kap/sentiment \
  -H "Content-Type: application/json" \
  -d '{
    "report_ids": [1, 2, 3]
  }'
```

---

### 2. Async Batch Scraping

Start long-running batch scraping jobs and check status asynchronously.

#### Endpoint: `POST /api/v1/scrapers/kap/batch`

**Request:**
```json
{
  "urls": [
    "https://www.kap.org.tr/tr/Bildirim/12345",
    "https://www.kap.org.tr/tr/Bildirim/12346"
  ],
  "formats": ["markdown", "html"],
  "max_pages": 100
}
```

**Response:**
```json
{
  "job_id": "550e8400-e29b-41d4-a716-446655440000",
  "status": "pending",
  "message": "Batch scraping job started",
  "status_url": "/api/v1/scrapers/jobs/550e8400-e29b-41d4-a716-446655440000"
}
```

#### Endpoint: `GET /api/v1/scrapers/jobs/{job_id}`

**Response:**
```json
{
  "job_id": "550e8400-e29b-41d4-a716-446655440000",
  "job_type": "kap_batch",
  "status": "running",
  "progress": 5,
  "total": 10,
  "created_at": "2025-01-23T10:00:00",
  "started_at": "2025-01-23T10:00:05",
  "completed_at": null,
  "result": null,
  "error": null
}
```

**Example:**
```bash
# Start batch job
JOB_ID=$(curl -X POST http://localhost:8000/api/v1/scrapers/kap/batch \
  -H "Content-Type: application/json" \
  -d '{"urls": ["url1", "url2"]}' \
  | jq -r '.job_id')

# Check status
curl http://localhost:8000/api/v1/scrapers/jobs/$JOB_ID
```

---

### 3. Webhook Notifications

Configure webhooks to receive real-time notifications for scraping completion and errors.

#### Endpoint: `POST /api/v1/scrapers/webhook/configure`

**Request:**
```json
{
  "webhook_url": "https://discord.com/api/webhooks/...",
  "enabled": true
}
```

**Response:**
```json
{
  "success": true,
  "message": "Webhook configured",
  "webhook_url": "https://discord.com/api/webhooks/..."
}
```

**Supported Webhooks:**
- **Discord**: `https://discord.com/api/webhooks/...`
- **Slack**: `https://hooks.slack.com/services/...`
- **Custom**: Any HTTP endpoint that accepts JSON

**Notification Types:**
- Scraping completion (with statistics)
- Scraping errors
- Sentiment analysis completion (with breakdown)

**Example:**
```bash
curl -X POST http://localhost:8000/api/v1/scrapers/webhook/configure \
  -H "Content-Type: application/json" \
  -d '{
    "webhook_url": "https://discord.com/api/webhooks/YOUR_WEBHOOK_URL",
    "enabled": true
  }'
```

---

### 4. Sentiment Query Endpoints

Query sentiment data from the database with filters.

#### Endpoint: `GET /api/v1/reports/kap/{report_id}/sentiment`

Get sentiment for a specific report.

**Response:**
```json
{
  "id": 1,
  "report_id": 123,
  "overall_sentiment": "positive",
  "confidence": 0.85,
  "impact_horizon": "medium_term",
  "key_drivers": ["Revenue growth", "Market expansion"],
  "risk_flags": [],
  "tone_descriptors": ["optimistic"],
  "target_audience": "retail_investors",
  "analysis_text": "...",
  "analyzed_at": "2025-01-23T10:30:00"
}
```

#### Endpoint: `GET /api/v1/reports/kap/sentiment/query`

Query sentiment with filters.

**Query Parameters:**
- `company_code` - Filter by company code
- `sentiment` - Filter by sentiment (positive/neutral/negative)
- `start_date` - Start date (YYYY-MM-DD)
- `end_date` - End date (YYYY-MM-DD)
- `limit` - Maximum results (default: 100)

**Example:**
```bash
curl "http://localhost:8000/api/v1/reports/kap/sentiment/query?company_code=AKBNK&sentiment=positive&limit=50"
```

---

## 📊 Complete Workflow Example

### Step 1: Configure Webhook
```bash
curl -X POST http://localhost:8000/api/v1/scrapers/webhook/configure \
  -H "Content-Type: application/json" \
  -d '{
    "webhook_url": "https://discord.com/api/webhooks/YOUR_URL",
    "enabled": true
  }'
```

### Step 2: Start Batch Scraping
```bash
JOB_ID=$(curl -X POST http://localhost:8000/api/v1/scrapers/kap/batch \
  -H "Content-Type: application/json" \
  -d '{
    "urls": ["url1", "url2", "url3"],
    "formats": ["markdown"]
  }' | jq -r '.job_id')
```

### Step 3: Monitor Job Status
```bash
# Poll until complete
while true; do
  STATUS=$(curl -s http://localhost:8000/api/v1/scrapers/jobs/$JOB_ID | jq -r '.status')
  echo "Status: $STATUS"
  if [ "$STATUS" = "completed" ] || [ "$STATUS" = "failed" ]; then
    break
  fi
  sleep 5
done
```

### Step 4: Analyze Sentiment
```bash
# Get report IDs from database
REPORT_IDS=$(curl -s "http://localhost:8000/api/v1/reports/kap?limit=10" | jq -r '.reports[].id')

# Analyze sentiment
curl -X POST http://localhost:8000/api/v1/scrapers/kap/sentiment \
  -H "Content-Type: application/json" \
  -d "{\"report_ids\": $REPORT_IDS}"
```

### Step 5: Query Sentiment Results
```bash
# Get positive sentiments for a company
curl "http://localhost:8000/api/v1/reports/kap/sentiment/query?company_code=AKBNK&sentiment=positive"
```

---

## 🔧 Configuration

### Environment Variables

Add to `.env`:
```env
# Webhook (optional)
WEBHOOK_URL=https://discord.com/api/webhooks/...
DISCORD_WEBHOOK_URL=https://discord.com/api/webhooks/...

# LLM Configuration (for sentiment analysis)
OPENAI_API_KEY=sk-...  # For OpenAI provider
# OR use local LLM (default)
LOCAL_LLM_BASE_URL=http://localhost:1234/v1
```

---

## 📝 Python Client Example

```python
import requests
import time

BASE_URL = "http://localhost:8000"

# 1. Configure webhook
requests.post(f"{BASE_URL}/api/v1/scrapers/webhook/configure", json={
    "webhook_url": "https://discord.com/api/webhooks/YOUR_URL",
    "enabled": True
})

# 2. Start batch job
response = requests.post(f"{BASE_URL}/api/v1/scrapers/kap/batch", json={
    "urls": ["url1", "url2", "url3"],
    "formats": ["markdown"]
})
job_id = response.json()["job_id"]

# 3. Poll job status
while True:
    status_response = requests.get(f"{BASE_URL}/api/v1/scrapers/jobs/{job_id}")
    status = status_response.json()
    
    print(f"Progress: {status['progress']}/{status['total']}")
    
    if status["status"] in ["completed", "failed"]:
        print(f"Job {status['status']}: {status.get('result') or status.get('error')}")
        break
    
    time.sleep(5)

# 4. Analyze sentiment
reports_response = requests.get(f"{BASE_URL}/api/v1/reports/kap?limit=10")
report_ids = [r["id"] for r in reports_response.json()["reports"]]

sentiment_response = requests.post(f"{BASE_URL}/api/v1/scrapers/kap/sentiment", json={
    "report_ids": report_ids
})
print(sentiment_response.json())

# 5. Query sentiment
sentiment_query = requests.get(
    f"{BASE_URL}/api/v1/reports/kap/sentiment/query",
    params={"company_code": "AKBNK", "sentiment": "positive"}
)
print(sentiment_query.json())
```

---

## 🎯 Use Cases

### 1. Daily Sentiment Monitoring
```bash
# Scrape daily reports
curl -X POST http://localhost:8000/api/v1/scrapers/kap \
  -d '{"days_back": 1}'

# Analyze sentiment
curl -X POST http://localhost:8000/api/v1/scrapers/kap/sentiment \
  -d '{"report_ids": [1,2,3,4,5]}'

# Get positive sentiments
curl "http://localhost:8000/api/v1/reports/kap/sentiment/query?sentiment=positive"
```

### 2. Large-Scale Batch Processing
```bash
# Start batch job for 1000 URLs
JOB_ID=$(curl -X POST http://localhost:8000/api/v1/scrapers/kap/batch \
  -d '{"urls": ["url1", "url2", ...]}' | jq -r '.job_id')

# Monitor in background
watch -n 5 "curl -s http://localhost:8000/api/v1/scrapers/jobs/$JOB_ID | jq ."
```

### 3. Company-Specific Analysis
```bash
# Get all reports for a company
curl "http://localhost:8000/api/v1/reports/kap?company_code=AKBNK"

# Analyze sentiment
curl -X POST http://localhost:8000/api/v1/scrapers/kap/sentiment \
  -d '{"report_ids": [1,2,3]}'

# Query sentiment trends
curl "http://localhost:8000/api/v1/reports/kap/sentiment/query?company_code=AKBNK&start_date=2025-01-01"
```

---

## 🔍 Error Handling

All endpoints return standard HTTP status codes:

- `200` - Success
- `400` - Bad Request (invalid parameters)
- `404` - Not Found (job/report not found)
- `500` - Internal Server Error

Error responses:
```json
{
  "detail": "Error message description"
}
```

---

## 📚 Related Documentation

- [API Documentation](API_DOCUMENTATION.md) - Complete API reference
- [Examples Analysis](EXAMPLES_ANALYSIS.md) - Features from other examples
- [Quick Reference](QUICK_REFERENCE.md) - Quick start guide

---

**Last Updated**: January 23, 2025
