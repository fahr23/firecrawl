# Quick Start Guide

This guide will help you get started with the Turkish Financial Data Scraper using Firecrawl.

## Prerequisites

- Python 3.8+
- PostgreSQL or TimescaleDB
- Firecrawl API key ([Get one here](https://firecrawl.dev))

## Installation

### 1. Clone or navigate to the example directory

```bash
cd examples/turkish-financial-data-scraper
```

### 2. Install dependencies

```bash
pip install -r requirements.txt
```

### 3. Set up environment variables

```bash
cp .env.example .env
```

Edit `.env` file with your credentials:

```env
FIRECRAWL_API_KEY=fc-your-actual-api-key-here
DB_HOST=localhost
DB_NAME=backtofuture
DB_USER=backtofuture
DB_PASSWORD=back2future
```

### 4. Set up database

Make sure PostgreSQL/TimescaleDB is running:

```bash
# Using Docker (recommended)
docker run -d \
  --name timescaledb \
  -p 5432:5432 \
  -e POSTGRES_DB=backtofuture \
  -e POSTGRES_USER=backtofuture \
  -e POSTGRES_PASSWORD=back2future \
  timescale/timescaledb:latest-pg15
```

## Usage Examples

### Example 1: Scrape KAP Reports

```bash
python example_kap.py
```

This will:
- Scrape BIST indices
- Get recent KAP reports (last 7 days)
- Fetch specific company report (THYAO)

### Example 2: Scrape TradingView Data

```bash
python example_tradingview.py
```

This will:
- Scrape sector classifications
- Scrape industry classifications
- Get cryptocurrency symbols

### Example 3: Run Main Scraper

Scrape all sources:

```bash
python main.py --scraper all
```

Scrape specific source:

```bash
# KAP reports only
python main.py --scraper kap --days 7

# BIST companies only
python main.py --scraper bist

# TradingView only
python main.py --scraper tradingview
```

### Example 4: Run Scheduler

Start automated scheduled scraping:

```bash
python scheduler.py
```

This will run:
- KAP reports: Daily at 08:00
- BIST companies: Weekly on Monday at 09:00
- TradingView: Daily at 09:30
- Commodity prices: Every 4 hours

## Project Structure

```
turkish-financial-data-scraper/
├── scrapers/           # Scraper implementations
│   ├── base_scraper.py      # Base class with Firecrawl
│   ├── kap_scraper.py       # KAP reports
│   ├── bist_scraper.py      # BIST data
│   └── tradingview_scraper.py
├── database/           # Database operations
│   └── db_manager.py
├── utils/             # Utility functions
│   ├── logger.py
│   └── pdf_extractor.py
├── main.py            # Main CLI entry point
├── scheduler.py       # Automated scheduler
└── example_*.py       # Usage examples
```

## Key Features

### 1. Firecrawl Integration

All scrapers use Firecrawl for reliable web scraping:

```python
# Simple scraping
result = await scraper.scrape_url("https://example.com")

# Crawl entire website
result = await scraper.crawl_website(
    "https://example.com",
    limit=100
)

# Extract structured data with LLM
result = await scraper.extract_with_schema(
    url="https://example.com",
    schema={"field": "type"},
    prompt="Extract specific data"
)
```

### 2. Automatic Retries

Built-in retry logic with exponential backoff:

```python
result = await scraper.retry_with_backoff(
    scraper.scrape_url,
    url,
    max_retries=3
)
```

### 3. Database Integration

Automatic data persistence:

```python
# Data is automatically saved to database
result = await scraper.scrape(days_back=7)
```

## Configuration

Edit `config.py` or use environment variables to configure:

- **Firecrawl Settings**: API key, timeouts, formats
- **Database Settings**: Connection params, pool size
- **Scraper Settings**: Concurrency, rate limits
- **Logging**: Level, file path

## Common Issues

### Issue: "FIRECRAWL_API_KEY is required"

**Solution**: Make sure you've set the API key in `.env` file

### Issue: Database connection error

**Solution**: Verify PostgreSQL is running and credentials are correct:

```bash
psql -h localhost -U backtofuture -d backtofuture
```

### Issue: Rate limiting

**Solution**: Adjust rate limits in `.env`:

```env
RATE_LIMIT_PER_MINUTE=20
```

## Data Sources

1. **KAP** - Turkish Public Disclosure Platform
   - Financial reports
   - Company disclosures
   - Material events

2. **BIST** - Borsa Istanbul
   - Company listings
   - Index compositions
   - Commodity prices

3. **TradingView**
   - Sector classifications
   - Industry groupings
   - Stock symbols

## Next Steps

1. Review the scrapers in `scrapers/` directory
2. Customize extraction schemas for your needs
3. Add new scrapers by extending `BaseScraper`
4. Set up automated scheduling
5. Build analytics on top of collected data

## Support

For issues or questions:
- Check the main README.md
- Review Firecrawl documentation
- Check logs in `logs/scraper.log`

## License

MIT License - See LICENSE file
