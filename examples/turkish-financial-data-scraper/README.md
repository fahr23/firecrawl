# Turkish Financial Data Scraper with Firecrawl

An enterprise-level financial data scraper for Turkish markets using Firecrawl. This example demonstrates how to scrape and process financial data from multiple Turkish financial sources including KAP (Public Disclosure Platform), BIST (Borsa Istanbul), and TradingView.

## Features

- 🔥 **Firecrawl Integration**: Uses Firecrawl API for reliable web scraping
- 📊 **Multiple Data Sources**: KAP, BIST, TradingView sector/industry data
- 🗄️ **TimescaleDB Integration**: Store time-series financial data efficiently
- 📄 **PDF Processing**: Extract financial tables from PDF reports
- 🔄 **Scheduled Tasks**: Automated daily/hourly data collection
- 🛡️ **Error Handling**: Robust retry logic and error recovery
- 📈 **Commodity Prices**: Gold, silver, platinum, palladium price tracking
- 🌐 **REST API**: Full REST API for programmatic access
- 🧠 **Sentiment Analysis**: Structured sentiment analysis with LLM (NEW!)
- ⚡ **Batch Processing**: Async batch scraping with job status tracking (NEW!)
- 🔔 **Webhook Notifications**: Real-time Discord/Slack notifications (NEW!)
- 🚀 **Parallel Pagination**: Concurrent scraping for better performance (NEW!)
- 🏗️ **DDD Architecture**: Domain-Driven Design for maintainability and testability (NEW!)

## Data Sources

1. **KAP (Kamuyu Aydınlatma Platformu)**: Turkish public disclosure platform for financial reports
2. **BIST (Borsa Istanbul)**: Turkish stock exchange company listings and indices
3. **TradingView**: Sector and industry classifications for Turkish stocks
4. **BIST Commodity Market**: Precious metal reference prices

## Installation

```bash
# Install dependencies
pip install -r requirements.txt

# Set up environment variables
cp .env.example .env
# Edit .env with your credentials
```

## Configuration

Create a `.env` file with:

```env
# Firecrawl API Key
FIRECRAWL_API_KEY=your_firecrawl_api_key_here

# Database Configuration
DB_HOST=localhost
DB_PORT=5432
DB_NAME=backtofuture
DB_USER=backtofuture
DB_PASSWORD=back2future

# Scraping Configuration
MAX_CONCURRENT_TASKS=10
RATE_LIMIT_PER_MINUTE=30
```

## Usage

### 1. REST API (Recommended)

Start the API server:

```bash
python api_server.py
```

The API will be available at:
- **API Base**: http://localhost:8000
- **Interactive Docs**: http://localhost:8000/docs
- **Health Check**: http://localhost:8000/api/v1/health

**Example API calls:**

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

See [API Documentation](docs/API_DOCUMENTATION.md) for complete API reference.

### Enhanced Features

The API now includes advanced features:

- **Sentiment Analysis**: `POST /api/v1/scrapers/kap/sentiment` - Analyze reports with structured JSON output
- **Batch Scraping**: `POST /api/v1/scrapers/kap/batch` - Async batch jobs with status tracking
- **Webhooks**: `POST /api/v1/scrapers/webhook/configure` - Real-time notifications
- **Sentiment Queries**: `GET /api/v1/reports/kap/sentiment/query` - Query sentiment data

## 📖 Documentation

- **[Complete User Guide](docs/USER_GUIDE.md)** - Comprehensive guide with examples for all features
- **[Quick Start Guide](docs/QUICK_START_GUIDE.md)** - Get started in 5 minutes
- **[API Quick Reference](docs/API_QUICK_REFERENCE.md)** - Quick reference for all endpoints
- **[Features Overview](docs/FEATURES_OVERVIEW.md)** - Overview of all features and use cases
- **[Enhanced Features Guide](docs/API_ENHANCED_FEATURES.md)** - Detailed documentation for advanced features
- **[API Documentation](docs/API_DOCUMENTATION.md)** - Complete API reference
- **[Architecture Guide](docs/DDD_ARCHITECTURE.md)** - System architecture and design
- **[Testing Guide](docs/TESTING_GUIDE.md)** - Testing instructions

### 2. CLI Usage

#### Basic Usage - Single Scraper

```python
from scrapers.kap_scraper import KAPScraper
from database.db_manager import DatabaseManager

# Initialize
db_manager = DatabaseManager()
scraper = KAPScraper(db_manager=db_manager)

# Scrape KAP reports
await scraper.scrape(days_back=7)
```

#### Full System with All Scrapers

```bash
python main.py --all
```

#### Individual Scrapers

```bash
# KAP Reports
python main.py --scraper kap --days 7

# BIST Companies
python main.py --scraper bist --data-type companies

# TradingView Sectors
python main.py --scraper tradingview --data-type sectors

# Commodity Prices
python main.py --scraper bist --data-type commodities
```

### 3. Scheduled Execution

```bash
python scheduler.py
```

This will run:
- KAP reports: Daily at 08:00
- BIST companies: Weekly on Monday
- TradingView sectors: Daily at 09:00
- Commodity prices: Every 4 hours

## Project Structure

```
turkish-financial-data-scraper/
├── README.md
├── requirements.txt
├── .env.example
├── main.py                          # Main CLI entry point
├── scheduler.py                     # Scheduled task runner
├── api_server.py                    # REST API server (NEW!)
├── config.py                        # Configuration management
├── api/                             # REST API (NEW!)
│   ├── main.py                      # FastAPI application
│   ├── dependencies.py              # Shared dependencies
│   ├── models.py                    # Pydantic models
│   └── routers/                     # API route handlers
│       ├── scrapers.py              # Scraping endpoints
│       ├── reports.py               # Report query endpoints
│       └── health.py                # Health check
├── domain/                          # Domain Layer (DDD)
│   ├── entities/                    # Business entities
│   ├── value_objects/               # Immutable value objects
│   ├── repositories/                # Repository interfaces
│   └── services/                     # Domain service interfaces
│
├── application/                      # Application Layer (DDD)
│   ├── use_cases/                   # Use cases (single responsibility)
│   └── dependencies.py              # Dependency injection
│
├── infrastructure/                   # Infrastructure Layer (DDD)
│   ├── repositories/                 # Repository implementations
│   └── services/                     # Service implementations
│
├── api/                              # Presentation Layer
│   ├── main.py                      # FastAPI application
│   ├── routers/                     # Thin API controllers
│   └── models.py                    # Pydantic DTOs
│
├── scrapers/                         # Scraper implementations
│   ├── base_scraper.py              # Base scraper with Firecrawl
│   ├── kap_scraper.py               # KAP reports scraper
│   └── bist_scraper.py              # BIST company listings
│
├── database/                         # Database layer
│   └── db_manager.py                # Database operations
│
├── utils/                            # Utilities
│   ├── llm_analyzer.py              # LLM analysis
│   ├── webhook_notifier.py           # Webhook notifications
│   └── batch_job_manager.py          # Batch job management
│
├── tests/                            # Tests (DDD structure)
│   ├── domain/                      # Domain tests
│   ├── application/                 # Use case tests
│   └── infrastructure/              # Integration tests
│
└── docs/                             # Documentation
    ├── DDD_ARCHITECTURE.md          # DDD architecture guide
    ├── TESTING_GUIDE.md              # Testing guide
    └── API_ENHANCED_FEATURES.md      # Enhanced features
```

## Database Schema

The system creates the following tables:

- `kap_reports`: Financial disclosure reports
- `kap_reports_attachments`: PDF attachments metadata
- `bist_companies`: Company listings from BIST
- `tradingview_sectors_tr`: Sector classifications (Turkish)
- `tradingview_industry_tr`: Industry classifications (Turkish)
- `historical_price_emtia`: Commodity prices (gold, silver, etc.)
- `{SYMBOL}_temel_analiz_*`: Dynamic tables for financial report data

## Example Output

```json
{
  "kap_reports": {
    "total_scraped": 145,
    "date_range": "2025-10-29 to 2025-11-05",
    "companies": 87,
    "report_types": ["Financial Statement", "Material Disclosure", "Special Case Disclosure"]
  },
  "bist_companies": {
    "total_companies": 523,
    "indices": ["BIST 100", "BIST 30", "BIST 50", "BIST TUM"]
  },
  "tradingview_sectors": {
    "sectors": 11,
    "total_stocks": 498
  }
}
```

## Advanced Features

### 1. Custom Extraction with Firecrawl

```python
# Extract specific data using LLM extraction
result = await scraper.extract_with_schema(
    url="https://www.kap.org.tr/tr/Bildirim/...",
    schema={
        "company_name": "string",
        "report_period": "string",
        "revenue": "number",
        "net_profit": "number"
    }
)
```

### 2. Crawl Entire Website

```python
# Crawl all pages from a starting URL
results = await scraper.crawl_website(
    start_url="https://www.kap.org.tr/tr/Endeksler",
    max_pages=100,
    include_pattern="/tr/Bildirim/*"
)
```

### 3. Batch Processing

```python
# Process multiple companies in parallel
await scraper.batch_process(
    company_symbols=["THYAO", "AKBNK", "EREGL"],
    date_range=("2025-01-01", "2025-11-05")
)
```

## Performance

- **Rate Limiting**: Respects source website rate limits
- **Concurrent Scraping**: Up to 10 concurrent tasks
- **Error Recovery**: Automatic retry with exponential backoff
- **Caching**: Results cached to minimize API calls
- **Database Pooling**: Connection pooling for optimal performance

## Monitoring

The system logs all activities:

```bash
# View logs
tail -f logs/scraper.log

# Monitor active tasks
python -c "from utils.monitor import get_status; print(get_status())"
```

## Architecture

The project follows **Domain-Driven Design (DDD)** principles:

- **Domain Layer**: Core business logic (entities, value objects)
- **Application Layer**: Use cases (single responsibility)
- **Infrastructure Layer**: Technical implementations (repositories, services)
- **Presentation Layer**: API controllers (thin, delegates to use cases)

**Benefits:**
- ✅ Maintainable - Clear separation of concerns
- ✅ Testable - Easy to test with mocks
- ✅ Single Responsibility - Each class has one job
- ✅ Extensible - Easy to add new features

See [DDD Architecture Guide](docs/DDD_ARCHITECTURE.md) for details.

## Testing

The codebase is fully testable:

```bash
# Run all tests
pytest tests/ -v

# Run domain tests (no dependencies)
pytest tests/domain/ -v

# Run use case tests (mocked dependencies)
pytest tests/application/ -v

# Run integration tests
pytest tests/infrastructure/ -v --integration
```

See [Testing Guide](docs/TESTING_GUIDE.md) for details.

## Troubleshooting

### Common Issues

1. **Firecrawl API Rate Limit**
   - Solution: Adjust `RATE_LIMIT_PER_MINUTE` in `.env`

2. **Database Connection Errors**
   - Solution: Check TimescaleDB is running and credentials are correct

3. **PDF Extraction Fails**
   - Solution: Ensure `pdfplumber` is installed correctly

4. **API Server Won't Start**
   - Solution: Check port 8000 is available, install FastAPI/uvicorn

5. **Import Errors After Refactoring**
   - Solution: Ensure all new packages are installed: `pip install -r requirements.txt`

## Contributing

Contributions are welcome! Please:
1. Fork the repository
2. Create a feature branch
3. Add tests for new features
4. Submit a pull request

## License

This project is licensed under the MIT License.

## Credits

- **Firecrawl**: Web scraping API
- **TimescaleDB**: Time-series database
- **FastAPI**: Modern REST API framework
- **Turkish Financial Markets**: KAP, BIST, TradingView

## Disclaimer

This tool is for educational and research purposes. Always respect website terms of service and rate limits. Ensure compliance with data usage regulations.
