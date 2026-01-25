# Quick Start Guide

Get up and running with the Turkish Financial Data Scraper in 5 minutes!

## 🚀 Installation

```bash
# 1. Navigate to project
cd examples/turkish-financial-data-scraper

# 2. Install dependencies
pip install -r requirements.txt

# 3. Configure environment
cp .env.example .env
# Edit .env with your credentials
```

## ⚙️ Configuration

Minimal `.env` configuration:

```env
# Required: Firecrawl API
FIRECRAWL_API_KEY=your_api_key_here
# OR for self-hosted:
FIRECRAWL_BASE_URL=http://api:3002

# Required: Database
DB_HOST=localhost
DB_PORT=5432
DB_NAME=backtofuture
DB_USER=backtofuture
DB_PASSWORD=back2future
DB_SCHEMA=turkish_financial
```

## 🎯 Quick Examples

### 1. Start API Server

```bash
python api_server.py
```

Visit http://localhost:8000/docs for interactive API docs.

### 2. Scrape KAP Reports

```bash
curl -X POST http://localhost:8000/api/v1/scrapers/kap \
  -H "Content-Type: application/json" \
  -d '{"days_back": 7}'
```

### 3. Analyze Sentiment

```bash
# First, get some report IDs
curl "http://localhost:8000/api/v1/reports/kap?limit=5"

# Then analyze them
curl -X POST http://localhost:8000/api/v1/scrapers/kap/sentiment \
  -H "Content-Type: application/json" \
  -d '{"report_ids": [1, 2, 3]}'
```

### 4. Query Data

```bash
# Get reports for a company
curl "http://localhost:8000/api/v1/reports/kap?company_code=AKBNK"

# Get sentiment data
curl "http://localhost:8000/api/v1/reports/kap/sentiment/query?sentiment=positive"
```

## 📚 Next Steps

- Read [Complete User Guide](USER_GUIDE.md) for detailed usage
- Check [API Documentation](API_DOCUMENTATION.md) for all endpoints
- See [Enhanced Features](API_ENHANCED_FEATURES.md) for advanced features

---

**Ready to go!** 🎉
