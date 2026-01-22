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

### 1. Basic Usage - Single Scraper

```python
from scrapers.kap_scraper import KAPScraper
from database.db_manager import DatabaseManager

# Initialize
db_manager = DatabaseManager()
scraper = KAPScraper(firecrawl_api_key="your_key", db_manager=db_manager)

# Scrape KAP reports
await scraper.scrape_recent_reports(days_back=7)
```

### 2. Full System with All Scrapers

```python
python main.py --all
```

### 3. Individual Scrapers

```python
# KAP Reports
python main.py --scraper kap --days 7

# BIST Companies
python main.py --scraper bist-companies

# TradingView Sectors
python main.py --scraper tradingview-sectors

# Commodity Prices
python main.py --scraper commodities
```

### 4. Scheduled Execution

```python
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
├── main.py                          # Main entry point
├── scheduler.py                     # Scheduled task runner
├── config.py                        # Configuration management
├── scrapers/
│   ├── __init__.py
│   ├── base_scraper.py             # Base scraper class with Firecrawl
│   ├── kap_scraper.py              # KAP reports scraper
│   ├── bist_scraper.py             # BIST company listings
│   ├── tradingview_scraper.py      # TradingView sectors/industries
│   └── commodity_scraper.py        # BIST commodity prices
├── database/
│   ├── __init__.py
│   ├── db_manager.py               # Database operations
│   └── schema.sql                  # Database schema
├── utils/
│   ├── __init__.py
│   ├── pdf_extractor.py            # PDF table extraction
│   ├── text_utils.py               # Text processing utilities
│   └── logger.py                   # Logging configuration
└── examples/
    ├── scrape_kap_example.py
    ├── scrape_bist_example.py
    └── full_pipeline_example.py
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

## Troubleshooting

### Common Issues

1. **Firecrawl API Rate Limit**
   - Solution: Adjust `RATE_LIMIT_PER_MINUTE` in `.env`

2. **Database Connection Errors**
   - Solution: Check TimescaleDB is running and credentials are correct

3. **PDF Extraction Fails**
   - Solution: Ensure `pdfplumber` is installed correctly

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
- **Turkish Financial Markets**: KAP, BIST, TradingView

## Disclaimer

This tool is for educational and research purposes. Always respect website terms of service and rate limits. Ensure compliance with data usage regulations.
