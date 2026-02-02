# Data Flow: API Call to Services

This document explains the complete data flow from an external API call through all services in the Turkish Financial Data Scraper system.

## Architecture Overview

```
┌─────────────────────────────────────────────────────────────────┐
│                    EXTERNAL CLIENT                              │
│  (Browser, Postman, cURL, Python script, etc.)                  │
└────────────────────────────┬────────────────────────────────────┘
                             │ HTTP Request
                             │ (Port 8000)
                             ▼
┌─────────────────────────────────────────────────────────────────┐
│              TURKISH SCRAPER API (FastAPI)                       │
│  Port: 8000 (exposed to host)                                   │
│  - api/main.py                                                  │
│  - api/routers/scrapers.py                                      │
│  - api/routers/reports.py                                       │
│  - api/routers/health.py                                        │
└────────────┬────────────────────────────────────────────────────┘
             │
             ├─────────────────────────────────────────────────────┐
             │                                                     │
             ▼                                                     ▼
┌────────────────────────────┐                    ┌──────────────────────────────┐
│   SCRAPER LAYER            │                    │   DATABASE LAYER             │
│  - KAPScraper              │                    │  - DatabaseManager           │
│  - BISTScraper             │                    │  - Connection Pool          │
│  - TradingViewScraper      │                    │  - Schema: turkish_financial│
│                            │                    │  - Tables:                   │
│  All inherit from:         │                    │    • kap_reports              │
│  - BaseScraper             │                    │    • bist_companies          │
│    └─ FirecrawlApp SDK     │                    │    • sentiment_analysis      │
└────────────┬───────────────┘                    └──────────────┬─────────────┘
             │                                                   │
             │ HTTP Request                                      │ SQL Queries
             │ (Port 3002)                                       │ (Port 5433)
             ▼                                                   ▼
┌─────────────────────────────────────────────────────────────────┐
│              FIRECRAWL CORE API (Node.js)                       │
│  Port: 3002 (exposed to host)                                │
│  Service: api (in docker-compose.yaml)                         │
│  - Receives scrape/crawl requests                              │
│  - Manages job queues (RabbitMQ)                                │
│  - Coordinates workers                                          │
└────────────┬────────────────────────────────────────────────────┘
             │
             ├──────────────────────┬──────────────────────────────┐
             │                      │                              │
             ▼                      ▼                              ▼
┌──────────────────────┐  ┌──────────────────────┐  ┌──────────────────────┐
│  PLAYWRIGHT SERVICE  │  │  HTML-TO-MD SERVICE  │  │   RABBITMQ            │
│  Port: 3000          │  │  Port: 8080          │  │  Port: 5672          │
│  (internal only)     │  │  (exposed to host)   │  │  (internal only)     │
│                      │  │                      │  │                      │
│  - Browser automation│  │  - HTML → Markdown   │  │  - Job queue          │
│  - JS rendering      │  │  - Format conversion │  │  - Task distribution │
│  - Screenshots       │  │  - Text extraction   │  │                      │
└──────────────────────┘  └──────────────────────┘  └──────────────────────┘
             │
             │ (scrapes external websites)
             ▼
┌─────────────────────────────────────────────────────────────────┐
│                    EXTERNAL WEBSITES                            │
│  - https://www.kap.org.tr (KAP)                                 │
│  - https://www.borsaistanbul.com (BIST)                         │
│  - https://www.tradingview.com                                  │
└─────────────────────────────────────────────────────────────────┘
```

## Detailed Flow: KAP Scraping Example

### 1. **API Request Entry Point**

**Client → Turkish Scraper API**
```
POST http://localhost:8000/api/v1/scrapers/kap
Content-Type: application/json

{
  "days_back": 7,
  "company_symbols": ["AKBNK"],
  "download_pdfs": true,
  "analyze_with_llm": false
}
```

**Flow:**
- FastAPI receives request at `api/routers/scrapers.py:scrape_kap()`
- Dependency injection: `get_db_manager()` provides `DatabaseManager` instance
- Creates `KAPScraper(db_manager=db_manager)` instance

---

### 2. **Scraper Initialization**

**Turkish Scraper API → Scraper Layer**

**File:** `scrapers/base_scraper.py`

```python
class BaseScraper:
    def __init__(self, db_manager=None):
        self.db_manager = db_manager
        
        # Initialize Firecrawl SDK
        firecrawl_kwargs = {"api_key": config.firecrawl.api_key}
        if config.firecrawl.base_url:  # e.g., "http://api:3002"
            firecrawl_kwargs["api_url"] = config.firecrawl.base_url
        
        self.firecrawl = FirecrawlApp(**firecrawl_kwargs)
```

**Configuration:**
- `FIRECRAWL_BASE_URL=http://api:3002` (internal Docker network)
- Or `FIRECRAWL_API_KEY=...` (for cloud API)
- SDK uses HTTP client to make requests to Firecrawl API

---

### 3. **Scraping Request to Firecrawl**

**Scraper → Firecrawl Core API**

**File:** `scrapers/base_scraper.py:scrape_url()`

```python
result = self.firecrawl.scrape(
    url="https://www.kap.org.tr/tr/Endeksler",
    formats=["markdown", "html"],
    wait_for=3000,
    timeout=30000
)
```

**HTTP Request (Python SDK → Firecrawl API):**
```
POST http://api:3002/v1/scrape
Headers:
  Authorization: Bearer <api_key> (if using cloud)
  Content-Type: application/json
Body:
{
  "url": "https://www.kap.org.tr/tr/Endeksler",
  "formats": ["markdown", "html"],
  "waitFor": 3000,
  "timeout": 30000
}
```

**Network Path:**
- From: `turkish-scraper` container (or devcontainer `api` service)
- To: `api` service on Docker network `backend`
- Port: `3002` (internal, not exposed to host in this case)

---

### 4. **Firecrawl API Processing**

**Firecrawl Core API → Internal Services**

**File:** `apps/api/src/...` (Firecrawl core code)

**Flow:**
1. **API receives request** → Validates and queues job
2. **RabbitMQ** → Distributes job to worker
3. **Worker** → Calls Playwright Service for browser automation
4. **Playwright Service** → Renders page, executes JavaScript
5. **HTML-TO-MD Service** → Converts HTML to Markdown (if requested)
6. **Response** → Returns structured data to API
7. **API** → Returns JSON to Python SDK

**Service Communication:**
```
Firecrawl API (3002)
  ├─→ RabbitMQ (5672, internal)
  │   └─→ Workers consume jobs
  │
  ├─→ Playwright Service (3000, internal)
  │   └─→ HTTP POST http://playwright-service:3000/scrape
  │       └─→ Returns: { markdown, html, metadata }
  │
  └─→ HTML-to-MD Service (8080, internal)
      └─→ HTTP POST http://go-html-to-md-service:8080
          └─→ Returns: { markdown }
```

---

### 5. **Data Processing & Storage**

**Scraper → Database**

**File:** `scrapers/kap_scraper.py`

After receiving scraped data from Firecrawl:

```python
# Parse HTML/Markdown
soup = BeautifulSoup(html_content, 'html.parser')
# Extract report data
reports = extract_reports(soup)

# Store in database
for report in reports:
    db_manager.save_kap_report(
        company_code=report['code'],
        company_name=report['name'],
        report_type=report['type'],
        report_date=report['date'],
        title=report['title'],
        data=report['data']
    )
```

**Database Connection:**
```
Connection Pool → PostgreSQL (nuq-postgres:5432)
  - Host: nuq-postgres (Docker network)
  - Port: 5432 (internal)
  - Database: postgres
  - Schema: turkish_financial
  - Tables: kap_reports, bist_companies, etc.
```

**SQL Query Example:**
```sql
INSERT INTO turkish_financial.kap_reports 
  (company_code, company_name, report_type, report_date, title, data)
VALUES 
  ('AKBNK', 'Akbank T.A.Ş.', 'Financial Statement', '2025-01-20', '...', '{"key": "value"}')
ON CONFLICT (company_code, report_date, title) DO UPDATE SET ...
```

---

### 6. **LLM Analysis (Optional)**

**Scraper → LLM Service**

**File:** `scrapers/kap_scraper.py` (if `analyze_with_llm=True`)

```python
if analyze_with_llm:
    # Configure LLM provider
    if provider_type == "local":
        provider = LocalLLMProvider(base_url="http://localhost:1234/v1")
    else:
        provider = OpenAIProvider(api_key=os.getenv("OPENAI_API_KEY"))
    
    analyzer = LLMAnalyzer(provider)
    analysis = await analyzer.analyze_report(report_text)
```

**LLM Request:**
- **Local LLM:** `http://localhost:1234/v1/chat/completions` (LM Studio, Ollama)
- **OpenAI:** `https://api.openai.com/v1/chat/completions`

**Sentiment Analysis Flow:**
```
POST /api/v1/scrapers/kap/sentiment
  ↓
AnalyzeSentimentUseCase (DDD)
  ↓
SentimentAnalyzerService
  ↓
LLM Provider (Local/OpenAI)
  ↓
Store in sentiment_analysis table
```

---

### 7. **Response to Client**

**Turkish Scraper API → Client**

**File:** `api/routers/scrapers.py:scrape_kap()`

```python
return ScrapeResponse(
    success=True,
    message=f"Successfully scraped {reports_count} reports",
    data={
        "total_scraped": reports_count,
        "companies": companies
    }
)
```

**HTTP Response:**
```json
{
  "success": true,
  "message": "Successfully scraped 145 reports from 87/87 companies",
  "data": {
    "total_scraped": 145,
    "new_reports": 145,
    "updated_reports": 0,
    "companies": ["AKBNK", "THYAO", ...]
  },
  "timestamp": "2025-01-24T10:30:00"
}
```

---

## Port Exposure Summary

### **Exposed to Host (External Access)**

| Service | Port | Purpose | Required? |
|---------|------|---------|-----------|
| **Turkish Scraper API** | `8000` | Main API endpoint | ✅ **YES** |
| **Firecrawl Core API** | `3002` | Firecrawl API (if calling directly) | ⚠️ Optional |
| **PostgreSQL** | `5433` | Database access (DBeaver, psql) | ⚠️ Optional |
| **HTML-to-MD Service** | `8080` | Direct HTML conversion | ❌ No |

### **Internal Only (Docker Network)**

| Service | Port | Purpose |
|---------|------|---------|
| **Playwright Service** | `3000` | Browser automation |
| **RabbitMQ** | `5672` | Job queue |
| **Redis** | `6379` | Caching/rate limiting |
| **PostgreSQL (internal)** | `5432` | Database (internal) |

---

## Network Flow Diagram

```
┌─────────────────────────────────────────────────────────────┐
│                    HOST MACHINE                             │
│                                                             │
│  ┌──────────────────────────────────────────────────────┐  │
│  │  External Client (Browser, Postman, etc.)            │  │
│  └───────────────────────┬──────────────────────────────┘  │
│                          │                                   │
│                          │ http://localhost:8000            │
│                          ▼                                   │
│  ┌──────────────────────────────────────────────────────┐  │
│  │  Port Forward: 8000 → api:8000                       │  │
│  └───────────────────────┬──────────────────────────────┘  │
└──────────────────────────┼──────────────────────────────────┘
                           │
                           │ Docker Network: backend
                           │
┌──────────────────────────┼──────────────────────────────────┐
│                    DOCKER CONTAINERS                       │
│                                                             │
│  ┌──────────────────────────────────────────────────────┐  │
│  │  api (Turkish Scraper)                               │  │
│  │  Port: 8000 (internal)                               │  │
│  │  - FastAPI application                                │  │
│  │  - Scrapers (KAP, BIST, TradingView)                 │  │
│  └───────┬──────────────────────────────────────────────┘  │
│          │                                                   │
│          ├───────────────┬──────────────────┬──────────────┤
│          │               │                  │               │
│          ▼               ▼                  ▼               ▼
│  ┌──────────────┐ ┌──────────────┐ ┌──────────────┐ ┌──────────────┐
│  │ api:3002     │ │ nuq-postgres│ │ playwright-  │ │ go-html-to-  │
│  │ (Firecrawl)  │ │ :5432        │ │ service:3000 │ │ md-service   │
│  │              │ │              │ │              │ │ :8080        │
│  │ HTTP API     │ │ PostgreSQL   │ │ Browser     │ │ HTML→MD      │
│  │              │ │              │ │ Automation   │ │              │
│  └──────┬───────┘ └──────────────┘ └──────┬───────┘ └──────────────┘
│         │                                  │                          │
│         │                                  │                          │
│         ▼                                  ▼                          │
│  ┌──────────────┐                  ┌──────────────┐                 │
│  │ rabbitmq:5672│                  │ redis:6379   │                 │
│  │ Job Queue    │                  │ Cache/Rate   │                 │
│  │              │                  │ Limiting     │                 │
│  └──────────────┘                  └──────────────┘                 │
└─────────────────────────────────────────────────────────────────────┘
```

---

## Configuration for Service Communication

### **Environment Variables**

**Turkish Scraper API (.env):**
```bash
# Firecrawl connection (internal Docker network)
FIRECRAWL_BASE_URL=http://api:3002
# OR for cloud:
# FIRECRAWL_API_KEY=fc-...

# Database connection (internal Docker network)
DB_HOST=nuq-postgres
DB_PORT=5432
DB_NAME=postgres
DB_USER=postgres
DB_PASSWORD=postgres
DB_SCHEMA=turkish_financial

# LLM (optional)
LOCAL_LLM_BASE_URL=http://localhost:1234/v1
OPENAI_API_KEY=sk-...
```

**Firecrawl Core API (docker-compose.yaml):**
```yaml
services:
  api:
    environment:
      PORT: 3002
      REDIS_URL: redis://redis:6379
      PLAYWRIGHT_MICROSERVICE_URL: http://playwright-service:3000/scrape
      HTML_TO_MARKDOWN_SERVICE_URL: http://go-html-to-md-service:8080
      POSTGRES_HOST: nuq-postgres
      POSTGRES_PORT: 5432
```

---

## Example: Complete Request Flow

### **Scenario: Scrape KAP Reports**

1. **Client** → `POST http://localhost:8000/api/v1/scrapers/kap`
2. **FastAPI** → Routes to `scrape_kap()` handler
3. **KAPScraper** → Initializes with `FirecrawlApp(api_url="http://api:3002")`
4. **BaseScraper** → Calls `self.firecrawl.scrape(url="https://www.kap.org.tr/...")`
5. **Python SDK** → HTTP POST to `http://api:3002/v1/scrape`
6. **Firecrawl API** → Receives request, queues job in RabbitMQ
7. **Worker** → Consumes job, calls Playwright Service
8. **Playwright** → Renders page, returns HTML/Markdown
9. **Firecrawl API** → Returns JSON to Python SDK
10. **KAPScraper** → Parses data, extracts reports
11. **DatabaseManager** → Saves to `kap_reports` table
12. **FastAPI** → Returns success response to client

**Total Network Hops:**
- Client → Turkish API: 1 (external)
- Turkish API → Firecrawl API: 1 (internal Docker)
- Firecrawl API → Playwright: 1 (internal Docker)
- Turkish API → Database: 1 (internal Docker)

---

## Key Takeaways

1. **Only port 8000 needs to be exposed** for the Turkish scraper API
2. **Firecrawl services communicate internally** via Docker network (`backend`)
3. **Service names are DNS resolvable** within Docker network (e.g., `api:3002`, `nuq-postgres:5432`)
4. **Database is accessible** from host at `localhost:5433` (optional, for debugging)
5. **All internal services** (Playwright, RabbitMQ, Redis) are not exposed to host

---

## Troubleshooting

### **Cannot connect to Firecrawl API**
- Check `FIRECRAWL_BASE_URL=http://api:3002` in Turkish scraper `.env`
- Verify Firecrawl API is running: `docker-compose ps api`
- Test from Turkish scraper container: `curl http://api:3002/health`

### **Database connection errors**
- Check `DB_HOST=nuq-postgres` (not `localhost`)
- Verify PostgreSQL is running: `docker-compose ps nuq-postgres`
- Test connection: `psql -h nuq-postgres -U postgres -d postgres`

### **Port conflicts**
- Turkish API (8000) must be unique on host
- Firecrawl API (3002) can be exposed if needed
- PostgreSQL (5433) is optional for external access
