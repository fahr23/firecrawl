# Architecture Overview

## System Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                     Turkish Financial Data Scraper               │
│                        (Firecrawl-based)                         │
└─────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────┐
│                         Entry Points                             │
├─────────────────────────────────────────────────────────────────┤
│  main.py          │  scheduler.py      │  example_*.py          │
│  (CLI)            │  (Automated)       │  (Examples)            │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                      Scraper Layer                               │
├──────────────────┬──────────────────┬──────────────────────────┤
│  KAPScraper      │  BISTScraper     │  TradingViewScraper      │
│  ├─ Reports      │  ├─ Companies    │  ├─ Sectors              │
│  ├─ Indices      │  ├─ Indices      │  ├─ Industries           │
│  └─ Companies    │  └─ Commodities  │  └─ Crypto Symbols       │
└──────────────────┴──────────────────┴──────────────────────────┘
                              │
                              ▼ (inherits)
┌─────────────────────────────────────────────────────────────────┐
│                     BaseScraper (Abstract)                       │
├─────────────────────────────────────────────────────────────────┤
│  Methods:                                                        │
│  • scrape_url(url, wait_for, formats)                          │
│  • crawl_website(start_url, limit, patterns)                   │
│  • extract_with_schema(url, schema, prompt)                    │
│  • retry_with_backoff(func, max_retries)                       │
│  • save_to_db(data, table_name)                                │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                      Firecrawl API                               │
├─────────────────────────────────────────────────────────────────┤
│  • Single page scraping (scrape_url)                            │
│  • Website crawling (crawl_url)                                 │
│  • LLM extraction (extract with schema)                         │
│  • JavaScript rendering (waitFor)                               │
│  • Multiple formats (markdown, html, structured)                │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                       Data Sources                               │
├──────────────────┬──────────────────┬──────────────────────────┤
│  KAP             │  BIST            │  TradingView             │
│  kap.org.tr      │  borsaistanbul   │  tr.tradingview.com      │
│                  │  .com            │                           │
└──────────────────┴──────────────────┴──────────────────────────┘

                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                    Database Layer                                │
├─────────────────────────────────────────────────────────────────┤
│  DatabaseManager                                                 │
│  ├─ Connection Pool                                             │
│  ├─ CRUD Operations                                             │
│  └─ Schema Management                                           │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                PostgreSQL / TimescaleDB                          │
├─────────────────────────────────────────────────────────────────┤
│  Tables:                                                         │
│  • kap_reports                                                   │
│  • bist_companies                                                │
│  • bist_index_members                                            │
│  • tradingview_sectors_tr                                        │
│  • tradingview_industry_tr                                       │
│  • historical_price_emtia                                        │
│  • cryptocurrency_symbols                                        │
└─────────────────────────────────────────────────────────────────┘
```

## Data Flow

```
┌──────────────┐
│  User/CLI    │
└──────┬───────┘
       │
       ▼
┌──────────────────────────────────────────────────────┐
│  1. Initialize Scraper                                │
│     - Load config (.env)                              │
│     - Create DB connection pool                       │
│     - Initialize Firecrawl client                     │
└──────┬───────────────────────────────────────────────┘
       │
       ▼
┌──────────────────────────────────────────────────────┐
│  2. Execute Scraping                                  │
│     - Call scraper method (e.g., scrape())            │
│     - Build Firecrawl request                         │
│     - Send to Firecrawl API                           │
└──────┬───────────────────────────────────────────────┘
       │
       ▼
┌──────────────────────────────────────────────────────┐
│  3. Firecrawl Processing                              │
│     - Fetch webpage                                   │
│     - Render JavaScript                               │
│     - Extract data (LLM if schema provided)           │
│     - Return structured JSON                          │
└──────┬───────────────────────────────────────────────┘
       │
       ▼
┌──────────────────────────────────────────────────────┐
│  4. Process Results                                   │
│     - Parse Firecrawl response                        │
│     - Transform data                                  │
│     - Validate against schema                         │
└──────┬───────────────────────────────────────────────┘
       │
       ▼
┌──────────────────────────────────────────────────────┐
│  5. Save to Database                                  │
│     - Insert/update records                           │
│     - Handle conflicts (ON CONFLICT)                  │
│     - Log results                                     │
└──────┬───────────────────────────────────────────────┘
       │
       ▼
┌──────────────┐
│  Complete    │
└──────────────┘
```

## Scraper Workflow Example: KAPScraper

```
scrape(days_back=7)
    │
    ├─► scrape_url(indices_url)
    │   └─► Firecrawl: Get company list
    │
    ├─► extract_with_schema(indices_url, schema)
    │   └─► Firecrawl LLM: Extract companies
    │
    └─► For each company:
        │
        ├─► scrape_url(reports_url)
        │   └─► Firecrawl: Get reports
        │
        ├─► extract_with_schema(reports_url, schema)
        │   └─► Firecrawl LLM: Structure data
        │
        └─► save_to_db(data, "kap_reports")
            └─► Database: Store report
```

## Configuration Flow

```
.env file
    │
    ├─► FIRECRAWL_API_KEY
    ├─► DB_HOST, DB_NAME, etc.
    ├─► MAX_CONCURRENT_TASKS
    └─► LOG_LEVEL
        │
        ▼
config.py (Config class)
    │
    ├─► DatabaseConfig
    ├─► FirecrawlConfig
    ├─► ScraperConfig
    └─► LoggingConfig
        │
        ▼
Used by all scrapers
```

## Scheduling Architecture

```
scheduler.py
    │
    ├─► AsyncIOScheduler
    │   │
    │   ├─► CronTrigger (daily/weekly)
    │   └─► IntervalTrigger (every N hours)
    │
    └─► Jobs:
        │
        ├─► job_scrape_kap_daily (08:00)
        ├─► job_scrape_bist_companies_weekly (Mon 09:00)
        ├─► job_scrape_tradingview_daily (09:30)
        └─► job_scrape_commodities_4h (every 4h)
```

## Error Handling & Retry Logic

```
Request
    │
    ▼
Try attempt 1
    │
    ├─ Success? ───► Return result
    │
    └─ Failure
        │
        ▼
    Wait (2^0 = 1s)
        │
        ▼
    Try attempt 2
        │
        ├─ Success? ───► Return result
        │
        └─ Failure
            │
            ▼
        Wait (2^1 = 2s)
            │
            ▼
        Try attempt 3
            │
            ├─ Success? ───► Return result
            │
            └─ Failure
                │
                ▼
            Return error
```

## Key Components

### 1. Scrapers (`scrapers/`)
- **Purpose**: Fetch and structure data from sources
- **Inheritance**: All extend `BaseScraper`
- **Firecrawl Methods**: `scrape_url()`, `crawl_website()`, `extract_with_schema()`

### 2. Database (`database/`)
- **Purpose**: Manage data persistence
- **Features**: Connection pooling, CRUD operations, schema management
- **Type**: PostgreSQL / TimescaleDB

### 3. Utilities (`utils/`)
- **Purpose**: Supporting functionality
- **Includes**: Logging, PDF extraction, text processing

### 4. Configuration (`config.py`)
- **Purpose**: Centralized settings
- **Source**: Environment variables (.env)
- **Scopes**: Database, Firecrawl, Scraper, Logging

### 5. Entry Points
- **main.py**: CLI for manual execution
- **scheduler.py**: Automated scheduled tasks
- **example_*.py**: Usage demonstrations

## Technology Stack

| Layer | Technology | Purpose |
|-------|-----------|---------|
| Web Scraping | **Firecrawl API** | Reliable web scraping with JS rendering |
| Data Extraction | **LLM (via Firecrawl)** | Intelligent data extraction |
| Database | **PostgreSQL/TimescaleDB** | Time-series data storage |
| Language | **Python 3.8+** | Core implementation |
| Async | **asyncio** | Concurrent scraping |
| Scheduling | **APScheduler** | Task automation |
| Logging | **Python logging** | Observability |
| Configuration | **python-dotenv** | Environment management |

---

This architecture provides a scalable, maintainable, and enterprise-ready solution for scraping Turkish financial data using Firecrawl.
