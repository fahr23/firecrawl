# API Reference

## Overview

REST API built with FastAPI. Base URL: `http://localhost:8000`

Interactive docs available at `http://localhost:8000/docs` (Swagger) and `http://localhost:8000/redoc`.

## Starting the Server

```bash
# Option A: startup script
python api_server.py

# Option B: uvicorn directly
uvicorn api.main:app --host 0.0.0.0 --port 8000 --reload

# Production (multi-worker)
uvicorn api.main:app --host 0.0.0.0 --port 8000 --workers 4
```

---

## Endpoints

### Health

#### `GET /api/v1/health`

```json
{ "status": "healthy", "database": "connected", "timestamp": "2025-01-23T10:30:00" }
```

---

### Scrapers

#### `POST /api/v1/scrapers/kap`

Scrape KAP public disclosure reports.

```json
// Request
{ "days_back": 7, "company_symbols": ["AKBNK", "THYAO"], "download_pdfs": true, "analyze_with_llm": false }

// Response
{ "success": true, "message": "Successfully scraped 145 KAP reports", "data": { "total_reports": 145, "companies": 87, "date_range": "2025-01-16 to 2025-01-23" } }
```

#### `POST /api/v1/scrapers/kap/batch`

Start an async batch scraping job.

```json
// Request
{ "urls": ["https://www.kap.org.tr/tr/Bildirim/12345"], "formats": ["markdown", "html"], "max_pages": 100 }

// Response
{ "job_id": "job_abc123", "status": "pending", "message": "Batch job started", "total_urls": 2, "estimated_time": "30-60 seconds" }
```

#### `GET /api/v1/scrapers/kap/batch/{job_id}`

Poll batch job status.

```json
{ "job_id": "job_abc123", "status": "completed", "progress": 100, "total": 2, "completed": 2 }
```

#### `POST /api/v1/scrapers/bist`

```json
// Request
{ "data_type": "companies", "start_date": "20250101", "end_date": "20250123" }
```

`data_type`: `companies` | `indices` | `commodities`

#### `POST /api/v1/scrapers/tradingview`

```json
{ "data_type": "both" }
```

`data_type`: `sectors` | `industries` | `crypto` | `both`

#### `POST /api/v1/scrapers/kap/configure-llm`

```json
{ "provider_type": "local", "base_url": "http://localhost:1234/v1", "model": "Llama-3-8B-Instruct-Finance-RAG", "temperature": 0.7 }
```

`provider_type`: `local` | `openai`

#### `POST /api/v1/scrapers/webhook/configure`

Configure webhook notifications.

```json
// Request
{ "webhook_url": "https://hooks.slack.com/...", "events": ["scrape_complete", "error"], "secret": "optional_secret" }
```

---

### Reports

#### `GET /api/v1/reports/kap`

```
GET /api/v1/reports/kap?company_code=AKBNK&start_date=2025-01-01&limit=50
```

Query params: `company_code`, `start_date`, `end_date`, `report_type`, `limit` (default 100, max 1000), `offset`

```json
// Response
{ "total": 145, "limit": 50, "offset": 0, "reports": [{ "id": 1, "company_code": "AKBNK", "report_type": "Financial Statement", "report_date": "2025-01-20", "title": "Q4 2024 Financial Results", "data": {} }] }
```

#### `GET /api/v1/reports/kap/{report_id}`

Get a single report by ID.

#### `GET /api/v1/reports/companies`

```
GET /api/v1/reports/companies?sector=Banking&limit=100
```

#### `GET /api/v1/reports/kap/sentiment/query`

Query stored sentiment results.

---

### Sentiment Analysis

See [SENTIMENT.md](SENTIMENT.md) for full sentiment analysis documentation.

#### `POST /api/v1/sentiment/analyze`

Analyze specific disclosures by ID.

```json
// Request
{ "report_ids": [1, 2, 3], "analyzer_type": "keyword", "custom_prompt": null }
```

`analyzer_type`: `"keyword"` (fast, default) | `"huggingface"` (accurate)

```json
// Response
{ "total_analyzed": 3, "successful": 3, "failed": 0, "results": [{ "report_id": 1, "success": true, "sentiment": { "overall_sentiment": "positive", "confidence": 0.85, "key_sentiments": ["growth"], "analysis_notes": "..." }, "analyzer": "keyword" }] }
```

#### `POST /api/v1/sentiment/analyze/auto`

Auto-analyze recent disclosures.

```json
// Request
{ "days_back": 7, "company_codes": ["ASELS", "AKBNK"], "analyzer_type": "keyword", "force_reanalyze": false }
```

#### `GET /api/v1/sentiment/`

Overall sentiment statistics.

#### `GET /api/v1/sentiment/disclosures/{id}`

Sentiment for one disclosure.

#### `GET /api/v1/sentiment/company/{name}`

Sentiment history for a company.

#### `GET /api/v1/sentiment/trends`

Sentiment trends over time.

---

## Error Handling

All errors return standard HTTP codes with:

```json
{ "detail": "Error message description" }
```

Codes: `200` success · `400` bad request · `404` not found · `500` server error

---

## Client Examples

### cURL

```bash
curl http://localhost:8000/api/v1/health

curl -X POST http://localhost:8000/api/v1/scrapers/kap \
  -H "Content-Type: application/json" \
  -d '{"days_back": 7, "download_pdfs": true}'

curl "http://localhost:8000/api/v1/reports/kap?company_code=AKBNK&limit=10"

curl -X POST http://localhost:8000/api/v1/sentiment/analyze \
  -H "Content-Type: application/json" \
  -d '{"report_ids": [1, 2, 3], "analyzer_type": "huggingface"}'
```

### Python

```python
import requests

BASE = "http://localhost:8000"

# Scrape
requests.post(f"{BASE}/api/v1/scrapers/kap", json={"days_back": 7}).json()

# Query
requests.get(f"{BASE}/api/v1/reports/kap", params={"company_code": "AKBNK", "limit": 10}).json()

# Sentiment
requests.post(f"{BASE}/api/v1/sentiment/analyze", json={"report_ids": [1, 2], "analyzer_type": "keyword"}).json()
```

---

## API Structure

```
api/
├── main.py              # FastAPI app + CORS
├── dependencies.py      # Shared DB/config
├── models.py            # Pydantic DTOs
└── routers/
    ├── scrapers.py      # Scraping endpoints
    ├── reports.py       # Report query endpoints
    ├── sentiment.py     # Sentiment endpoints
    └── health.py        # Health check
```

---

## Production Checklist

- Set `allow_origins` to your domain in `api/main.py` (not `*`)
- Add API key or JWT authentication
- Put nginx/caddy in front as reverse proxy
- Enable HTTPS
- Set `--workers N` equal to CPU cores

---

## External Analysis API v1

All endpoints below are mounted at `/api/external/v1`.  
Base URL: `http://localhost:8000/api/external/v1`  
Auth: none (open CORS)  
Full interactive docs: `http://localhost:8000/docs`

---

### `GET /health`

Check whether the service and database are reachable.

```json
// Response
{
  "status": "ok",
  "contract_version": "1.0",
  "provider": "kap-scraper"
}
```

`status` is `"degraded"` when DB is unreachable but the process is still up.

---

### `GET /instruments`

List every registered BIST company and which data types are available for each.  
Call this first to build a picker UI or discover what is populated.

**Query params**

| Param | Type | Default | Notes |
|-------|------|---------|-------|
| `market` | `bist` | `bist` | only `bist` is supported |

```bash
curl "http://localhost:8000/api/external/v1/instruments?market=bist"
```

```json
{
  "contract_version": "1.0",
  "market": "bist",
  "total": 20,
  "items": [
    {
      "ticker": "THYAO",
      "company_name": "Türk Hava Yolları A.O.",
      "sector": "Havacılık",
      "market": "bist",
      "available_data": ["sentiment", "fundamental", "news_sentiment", "combined_sentiment"]
    }
  ]
}
```

`available_data` values: `sentiment` (KAP disclosure-based), `fundamental`, `news_sentiment` (portal), `combined_sentiment` (0.6·news + 0.4·social).

---

### KAP Sentiment (disclosure-based)

#### `GET /sentiment/{instrument}?market=bist&as_of=`

Most-recent (or `as_of` date) KAP disclosure sentiment for one ticker.

**Query params**

| Param | Required | Notes |
|-------|----------|-------|
| `market` | yes | `bist` |
| `as_of` | no | ISO date `YYYY-MM-DD` — returns data ≤ this date |

```bash
curl "http://localhost:8000/api/external/v1/sentiment/THYAO?market=bist"
```

**Response envelope** — see [data_contract_v1.md](data_contract_v1.md) §1 for full field list.  
`payload.overall_sentiment`: `positive | neutral | negative`  
`payload.score`: float –1.0 → +1.0

#### `GET /sentiment/{instrument}/history`

Time-series of daily sentiment for one ticker.

**Query params**

| Param | Default | Notes |
|-------|---------|-------|
| `market` | required | `bist` |
| `from` | — | ISO date lower bound |
| `to` | — | ISO date upper bound |
| `limit` | 100 | max 1000 |
| `cursor` | — | pagination token from previous response |

```bash
curl "http://localhost:8000/api/external/v1/sentiment/THYAO/history?market=bist&from=2026-06-01&limit=30"
```

#### `POST /sentiment/batch`

Fetch sentiment for multiple tickers in one call.

```json
// Request
{
  "market": "bist",
  "instruments": ["THYAO", "AKBNK", "GARAN"],
  "as_of": "2026-06-28"
}

// Response
{
  "contract_version": "1.0",
  "items": [ { /* point envelope */ }, ... ]
}
```

#### `GET /sentiment/overview?market=bist`

Market-wide aggregate — distribution of positive/neutral/negative across all tickers.

```bash
curl "http://localhost:8000/api/external/v1/sentiment/overview?market=bist&from=2026-06-01"
```

---

### Fundamental Data

Sourced from KAP financial statements (quarterly/annual).

#### `GET /fundamental/{instrument}?market=bist&as_of=`

Latest financials for one ticker. `payload` includes `pe_ratio`, `pb_ratio`, `ev_ebitda`, `net_margin`, `revenue`, `net_income`, `period`, `period_type`.

```bash
curl "http://localhost:8000/api/external/v1/fundamental/AKBNK?market=bist"
```

#### `GET /fundamental/{instrument}/history`

Same query params as sentiment history.

#### `POST /fundamental/batch`

Same shape as `POST /sentiment/batch`.

---

### News (KAP / Portal announcements)

#### `GET /news`

List all news articles (KAP announcements + Bloomberg HT / portal articles), newest first.

**Query params**

| Param | Notes |
|-------|-------|
| `category` | filter by source category: `SPK`, `MKK`, `BIST`, `KAP`, `bloomberght`, ... |
| `from` | ISO date |
| `to` | ISO date |
| `limit` | default 50, max 1000 |
| `cursor` | pagination |

```bash
curl "http://localhost:8000/api/external/v1/news?limit=20"
```

```json
{
  "contract_version": "1.0",
  "kind": "news",
  "items": [
    {
      "news_id": "abc123",
      "title": "THYAO 1Ç26 kârı beklentileri aştı",
      "content": "...",
      "source_url": "https://www.bloomberght.com/...",
      "publish_date": "2026-06-29T07:45:00Z",
      "news_category": "bloomberght",
      "overall_sentiment": "positive",
      "sentiment_score": 0.72
    }
  ],
  "next_cursor": "eyJpZCI6MTIzfQ=="
}
```

#### `GET /news/{news_id}`

Single news item by ID.

---

### News-Portal Sentiment

Sentiment aggregated per ticker from Turkish financial portals (Bloomberg HT, Mynet Finans, Foreks, Bigpara).

#### `GET /news-sentiment/{instrument}?market=bist&as_of=`

Latest portal-news sentiment for one ticker.

#### `GET /news-sentiment/{instrument}/history`

Same query params as `/sentiment/{instrument}/history`.

#### `POST /news-sentiment/collect`

Manually trigger a scrape → analyse → persist run.

```json
// Request body (all optional)
{
  "tickers": ["THYAO", "AKBNK"],
  "days_back": 1,
  "sources": ["bloomberght", "mynetfinans"],
  "include_investing_comments": false
}

// Response
{
  "contract_version": "1.0",
  "scraped": 18,
  "saved": 11,
  "analyzed": 11,
  "triggered_at": "2026-06-29T08:12:04Z"
}
```

**Available sources:** `bloomberght`, `mynetfinans`, `foreks`, `bigpara`

#### `GET /news-sentiment/schedule`

Return the current collection schedule state.

```json
{
  "contract_version": "1.0",
  "mode": "manual",
  "interval_minutes": 30,
  "sources": ["bloomberght", "mynetfinans"],
  "days_back": 1,
  "is_running": false,
  "last_run": "2026-06-29T08:12:04Z",
  "next_run": null,
  "last_result": { "scraped": 18, "saved": 11, "analyzed": 11 }
}
```

#### `POST /news-sentiment/schedule`

Switch between `manual` and `interval` collection modes.

```json
// Request body
{
  "mode": "interval",
  "interval_minutes": 60,
  "sources": ["bloomberght"],
  "days_back": 1
}

// Response adds: "ok": true, "message": "...", plus updated schedule state
```

| Body field | Type | Notes |
|------------|------|-------|
| `mode` | `"manual"` \| `"interval"` | required |
| `interval_minutes` | int 5–1440 | default 30; ignored in manual mode |
| `sources` | list[str] | default `["bloomberght","mynetfinans"]` |
| `days_back` | int 1–30 | default 1 |

---

### Social Sentiment (X / FinTwit)

#### `GET /social-sentiment/{instrument}?market=bist&as_of=`

Latest X/FinTwit-derived sentiment for one ticker.

#### `GET /social-sentiment/{instrument}/history`

Time series. Same params as other history endpoints.

#### `POST /social-sentiment/collect`

Trigger social scrape for specific tickers.

```json
// Request body
{
  "tickers": ["THYAO", "GARAN"],
  "days_back": 7,
  "limit_per_ticker": 30
}
```

---

### Combined Sentiment

Weighted blend: **0.6 × news_score + 0.4 × social_score**.

#### `GET /combined-sentiment/{instrument}?market=bist&as_of=`

Latest blended sentiment for one ticker.

#### `GET /combined-sentiment/{instrument}/history`

Time series. Same params as other history endpoints.

---

## Proposed Endpoints (Roadmap)

These endpoints **do not exist yet** but are suggested for the next iteration.  
Each entry explains the use case and the response shape.

---

### `GET /sector/overview?market=bist`

**Why:** Clients want a macro view before drilling into individual tickers — "which BIST sectors are bullish today?". Currently only `sentiment/overview` returns a market-wide aggregate with no sector breakdown.

**Suggested response:**
```json
{
  "contract_version": "1.0",
  "market": "bist",
  "as_of": "2026-06-29",
  "sectors": [
    {
      "sector": "Bankacılık",
      "ticker_count": 12,
      "avg_score": 0.42,
      "overall_sentiment": "positive",
      "positive_pct": 67,
      "neutral_pct": 25,
      "negative_pct": 8
    }
  ]
}
```

**Implementation note:** Add a GROUP BY `sector` aggregation over `aggregated_ticker_sentiment` joined with `bist_companies`.

---

### `GET /instruments/{ticker}?market=bist`

**Why:** A client building a ticker detail screen today must make 4+ separate calls (sentiment, fundamental, news-sentiment, combined). A single consolidated endpoint would cut latency and simplify the UI.

**Suggested response:**
```json
{
  "contract_version": "1.0",
  "ticker": "THYAO",
  "company_name": "Türk Hava Yolları A.O.",
  "sector": "Havacılık",
  "market": "bist",
  "as_of": "2026-06-29",
  "kap_sentiment": { "overall_sentiment": "positive", "score": 0.61 },
  "fundamental": { "pe_ratio": 8.4, "net_margin": 0.12 },
  "news_sentiment": { "overall_sentiment": "positive", "score": 0.72 },
  "combined_sentiment": { "score": 0.67 },
  "freshness_seconds": 3600
}
```

**Implementation note:** Parallel DB queries inside the handler — one per data type. Return `null` for types with no data.

---

### `GET /news?ticker=THYAO`

**Why:** The current `GET /news` endpoint has `category` and date filters but no ticker filter. Clients that want to show a news feed for one company must download all news and filter client-side.

**Suggested change:** Add an optional `ticker` query param to `GET /news` that joins with a `news_article_tickers` mapping table (or filters on headline keyword match as a first pass).

```bash
curl "http://localhost:8000/api/external/v1/news?ticker=THYAO&limit=20"
```

---

### `GET /sentiment/{ticker}/peers?peers=AKBNK,GARAN,YKBNK`

**Why:** Relative sentiment comparison is more useful than an absolute score. Analysts want to see "AKBNK is at +0.5 vs sector average +0.2 vs peer GARAN at +0.4".

**Suggested response:**
```json
{
  "contract_version": "1.0",
  "anchor": "AKBNK",
  "as_of": "2026-06-29",
  "items": [
    { "ticker": "AKBNK", "score": 0.50, "rank": 1 },
    { "ticker": "GARAN", "score": 0.40, "rank": 2 },
    { "ticker": "YKBNK", "score": 0.31, "rank": 3 }
  ]
}
```

---

### `POST /instruments/refresh`

**Why:** The `bist_companies` table is seeded manually. When new BIST listings happen or sectors change, clients have no way to trigger a refresh. This endpoint would re-scrape the official BIST company list and upsert into the table.

```bash
curl -s -X POST "http://localhost:8000/api/external/v1/instruments/refresh"
```

```json
{ "ok": true, "added": 3, "updated": 12, "unchanged": 485 }
```

---

### `GET /news-sentiment/schedule/runs?limit=20`

**Why:** Operators debugging collection issues need an audit trail of past runs — how many articles were scraped, whether any runs failed, how long they took. Currently `last_result` in `GET /schedule` holds only the most recent run.

**Suggested response:**
```json
{
  "contract_version": "1.0",
  "items": [
    {
      "triggered_at": "2026-06-29T09:00:01Z",
      "mode": "interval",
      "scraped": 18, "saved": 11, "analyzed": 11,
      "duration_seconds": 4.2,
      "error": null
    }
  ]
}
```

**Implementation note:** Persist each run's result to a `news_collection_runs` table and query it here. The scheduler's `run_collect()` already has the right data — just needs a `INSERT INTO news_collection_runs ...` call added.
