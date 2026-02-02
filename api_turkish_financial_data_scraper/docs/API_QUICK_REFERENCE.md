# API Quick Reference

Quick reference for all API endpoints.

## Base URL

```
http://localhost:8000
```

## Endpoints

### Health

```
GET /api/v1/health
```

### Scraping

#### KAP Reports
```
POST /api/v1/scrapers/kap
Body: {
  "days_back": 7,
  "download_pdfs": false,
  "company_codes": ["AKBNK"],
  "report_types": ["Financial Statement"]
}
```

#### BIST Data
```
POST /api/v1/scrapers/bist
Body: {
  "data_type": "companies" | "indices" | "commodities",
  "start_date": "20250101",  // for commodities
  "end_date": "20250131"      // for commodities
}
```

#### TradingView
```
POST /api/v1/scrapers/tradingview
Body: {
  "data_type": "sectors" | "industries" | "crypto" | "both"
}
```

### Sentiment Analysis

```
POST /api/v1/scrapers/kap/sentiment
Body: {
  "report_ids": [1, 2, 3],
  "custom_prompt": "Optional prompt"
}
```

### Batch Processing

#### Create Batch Job
```
POST /api/v1/scrapers/kap/batch
Body: {
  "days_back": 30,
  "download_pdfs": false,
  "company_codes": ["AKBNK"]
}
```

#### Check Job Status
```
GET /api/v1/scrapers/jobs/{job_id}
```

### Webhooks

```
POST /api/v1/scrapers/webhook/configure
Body: {
  "webhook_url": "https://...",
  "webhook_type": "discord" | "slack" | "generic",
  "notify_on_completion": true,
  "notify_on_error": true,
  "notify_on_sentiment": true
}
```

### Query Reports

```
GET /api/v1/reports/kap
Query Params:
  - company_code: string
  - start_date: date (YYYY-MM-DD)
  - end_date: date (YYYY-MM-DD)
  - report_type: string
  - limit: int (1-1000)
  - offset: int
```

### Query Sentiment

```
GET /api/v1/reports/kap/sentiment/query
Query Params:
  - sentiment: "positive" | "neutral" | "negative"
  - min_confidence: float (0.0-1.0)
  - impact_horizon: "short_term" | "medium_term" | "long_term"
  - start_date: date
  - end_date: date
  - limit: int
  - offset: int
```

```
GET /api/v1/reports/kap/sentiment/{report_id}
```

## Response Codes

- `200`: Success
- `400`: Bad Request
- `404`: Not Found
- `500`: Internal Server Error

## Interactive Docs

Visit http://localhost:8000/docs for interactive API documentation with try-it-out functionality.

---

**See [User Guide](USER_GUIDE.md) for detailed examples.**
