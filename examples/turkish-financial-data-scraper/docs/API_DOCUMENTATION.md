# REST API Documentation

## Overview

The Turkish Financial Data Scraper now includes a **REST API** built with FastAPI, providing programmatic access to all scraping and analysis features.

## Base URL

```
http://localhost:8000
```

## API Endpoints

### Health Check

#### `GET /api/v1/health`

Check API and database health status.

**Response:**
```json
{
  "status": "healthy",
  "database": "connected",
  "timestamp": "2025-01-23T10:30:00"
}
```

---

### Scrapers

#### `POST /api/v1/scrapers/kap`

Scrape KAP (Public Disclosure Platform) reports.

**Request Body:**
```json
{
  "days_back": 7,
  "company_symbols": ["AKBNK", "THYAO"],
  "download_pdfs": true,
  "analyze_with_llm": false
}
```

**Response:**
```json
{
  "success": true,
  "message": "Successfully scraped 145 KAP reports",
  "data": {
    "total_reports": 145,
    "companies": 87,
    "date_range": "2025-01-16 to 2025-01-23"
  },
  "timestamp": "2025-01-23T10:30:00"
}
```

#### `POST /api/v1/scrapers/bist`

Scrape BIST (Borsa Istanbul) data.

**Request Body:**
```json
{
  "data_type": "companies",
  "start_date": "20250101",
  "end_date": "20250123"
}
```

**Data Types:**
- `companies` - Company listings
- `indices` - Index members
- `commodities` - Commodity prices (requires start_date and end_date)

#### `POST /api/v1/scrapers/tradingview`

Scrape TradingView data.

**Request Body:**
```json
{
  "data_type": "both"
}
```

**Data Types:**
- `sectors` - Sector classifications
- `industries` - Industry classifications
- `crypto` - Cryptocurrency symbols
- `both` - Sectors and industries

#### `POST /api/v1/scrapers/kap/configure-llm`

Configure LLM for KAP analysis.

**Request Body:**
```json
{
  "provider_type": "local",
  "base_url": "http://localhost:1234/v1",
  "model": "Llama-3-8B-Instruct-Finance-RAG",
  "temperature": 0.7
}
```

**Provider Types:**
- `local` - Local LLM (LM Studio, Ollama)
- `openai` - OpenAI API (requires api_key)

---

### Reports

#### `GET /api/v1/reports/kap`

Query KAP reports from database.

**Query Parameters:**
- `company_code` (optional) - Filter by company code
- `start_date` (optional) - Start date (YYYY-MM-DD)
- `end_date` (optional) - End date (YYYY-MM-DD)
- `report_type` (optional) - Filter by report type
- `limit` (default: 100) - Number of results (1-1000)
- `offset` (default: 0) - Pagination offset

**Example:**
```
GET /api/v1/reports/kap?company_code=AKBNK&start_date=2025-01-01&limit=50
```

**Response:**
```json
{
  "total": 145,
  "limit": 50,
  "offset": 0,
  "reports": [
    {
      "id": 1,
      "company_code": "AKBNK",
      "company_name": "Akbank T.A.Ş.",
      "report_type": "Financial Statement",
      "report_date": "2025-01-20",
      "title": "Q4 2024 Financial Results",
      "summary": "...",
      "data": {...},
      "scraped_at": "2025-01-23T10:30:00"
    }
  ]
}
```

#### `GET /api/v1/reports/kap/{report_id}`

Get a specific KAP report by ID.

**Response:**
```json
{
  "id": 1,
  "company_code": "AKBNK",
  "company_name": "Akbank T.A.Ş.",
  "report_type": "Financial Statement",
  "report_date": "2025-01-20",
  "title": "Q4 2024 Financial Results",
  "summary": "...",
  "data": {...},
  "scraped_at": "2025-01-23T10:30:00"
}
```

#### `GET /api/v1/reports/companies`

Get list of companies from BIST.

**Query Parameters:**
- `sector` (optional) - Filter by sector
- `limit` (default: 100) - Number of results

**Response:**
```json
[
  {
    "code": "AKBNK",
    "name": "Akbank T.A.Ş.",
    "sector": "Banking"
  }
]
```

---

## Starting the API Server

### Option 1: Using the startup script

```bash
python api_server.py
```

### Option 2: Using uvicorn directly

```bash
uvicorn api.main:app --host 0.0.0.0 --port 8000 --reload
```

### Option 3: Using Python module

```bash
python -m api.main
```

## Interactive API Documentation

Once the server is running, visit:

- **Swagger UI**: http://localhost:8000/docs
- **ReDoc**: http://localhost:8000/redoc

These provide interactive documentation where you can test endpoints directly.

## Example Usage

### Using cURL

```bash
# Health check
curl http://localhost:8000/api/v1/health

# Scrape KAP reports
curl -X POST http://localhost:8000/api/v1/scrapers/kap \
  -H "Content-Type: application/json" \
  -d '{"days_back": 7, "download_pdfs": true}'

# Query reports
curl "http://localhost:8000/api/v1/reports/kap?company_code=AKBNK&limit=10"
```

### Using Python

```python
import requests

# Health check
response = requests.get("http://localhost:8000/api/v1/health")
print(response.json())

# Scrape KAP
response = requests.post(
    "http://localhost:8000/api/v1/scrapers/kap",
    json={"days_back": 7, "download_pdfs": True}
)
print(response.json())

# Query reports
response = requests.get(
    "http://localhost:8000/api/v1/reports/kap",
    params={"company_code": "AKBNK", "limit": 10}
)
print(response.json())
```

### Using JavaScript/TypeScript

```javascript
// Health check
const health = await fetch('http://localhost:8000/api/v1/health')
  .then(r => r.json());

// Scrape KAP
const result = await fetch('http://localhost:8000/api/v1/scrapers/kap', {
  method: 'POST',
  headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify({ days_back: 7, download_pdfs: true })
}).then(r => r.json());

// Query reports
const reports = await fetch(
  'http://localhost:8000/api/v1/reports/kap?company_code=AKBNK&limit=10'
).then(r => r.json());
```

## Architecture

The API is structured as follows:

```
api/
├── main.py              # FastAPI application
├── dependencies.py      # Shared dependencies (DB, config)
├── models.py            # Pydantic request/response models
└── routers/
    ├── scrapers.py      # Scraping endpoints
    ├── reports.py       # Report query endpoints
    └── health.py        # Health check endpoints
```

## Error Handling

All endpoints return standard HTTP status codes:

- `200` - Success
- `400` - Bad Request (invalid parameters)
- `404` - Not Found
- `500` - Internal Server Error

Error responses follow this format:

```json
{
  "detail": "Error message description"
}
```

## CORS Configuration

The API includes CORS middleware. For production, update `allow_origins` in `api/main.py`:

```python
app.add_middleware(
    CORSMiddleware,
    allow_origins=["https://yourdomain.com"],  # Production domain
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
```

## Production Deployment

For production deployment:

1. **Use a production ASGI server:**
   ```bash
   uvicorn api.main:app --host 0.0.0.0 --port 8000 --workers 4
   ```

2. **Use a reverse proxy (nginx):**
   ```nginx
   location / {
       proxy_pass http://localhost:8000;
       proxy_set_header Host $host;
       proxy_set_header X-Real-IP $remote_addr;
   }
   ```

3. **Add authentication** (recommended):
   - Implement API key authentication
   - Use OAuth2 or JWT tokens
   - Add rate limiting

4. **Enable HTTPS** using Let's Encrypt or similar

## Next Steps

- Add authentication/authorization
- Implement rate limiting
- Add webhook support for long-running scrapes
- Add sentiment analysis endpoints
- Add real-time scraping status endpoints
