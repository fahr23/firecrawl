# Setup Guide

## Prerequisites

- Docker + Docker Compose (all services run in containers)
- Python 3.11+
- The devcontainer is pre-configured with all services

## Docker Services

| Service | Host | Port |
|---------|------|------|
| PostgreSQL | `nuq-postgres` | 5432 |
| Redis | `redis` | 6379 |
| RabbitMQ | `rabbitmq` | 5672 |
| Firecrawl API | `api` | 3002 |
| Playwright | `playwright-service` | 3000 |
| Go HTML-to-MD | `go-html-to-md-service` | 8080 |

```bash
# Verify all services are running
docker ps --format "table {{.Names}}\t{{.Status}}\t{{.Ports}}"
```

---

## Installation

```bash
cd /workspaces/firecrawl/projects/turkish_financial

# Recommended: virtual environment
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

---

## Environment Configuration

Copy `.env.example` to `.env` and fill in values:

```env
# Firecrawl
FIRECRAWL_API_KEY=your_firecrawl_api_key_here
FIRECRAWL_BASE_URL=http://api:3002

# Database
DB_HOST=nuq-postgres
DB_PORT=5432
DB_NAME=postgres
DB_USER=postgres
DB_PASSWORD=postgres
DB_SCHEMA=turkish_financial

# Scraping limits
MAX_CONCURRENT_TASKS=10
RATE_LIMIT_PER_MINUTE=30

# LLM (choose one or more)
LOCAL_LLM_BASE_URL=http://localhost:1234/v1   # LM Studio / Ollama
OPENAI_API_KEY=sk-...
GEMINI_API_KEY=...                             # Google AI Studio

# KAP anti-bot (proxy order to try)
KAP_FIRECRAWL_PROXY=basic,auto,stealth
KAP_PAGE_DELAY_S=4                            # delay between KAP page requests

# Sentiment
SENTIMENT_PROVIDER=keyword                    # keyword | huggingface
HUGGINGFACE_MODEL=savasy/bert-base-turkish-sentiment-cased
```

---

## Database Schema Isolation

All tables live in their own PostgreSQL schema (`turkish_financial` by default) so they don't conflict with other apps sharing the same database.

The schema is created automatically on first run. To use a different name:

```env
DB_SCHEMA=my_custom_schema
```

### Migrate existing tables from `public`

```sql
-- Option 1: keep using public
DB_SCHEMA=public

-- Option 2: move tables
psql -h nuq-postgres -U postgres -d postgres
CREATE SCHEMA turkish_financial;
ALTER TABLE kap_reports SET SCHEMA turkish_financial;
-- repeat for all tables
```

### Verify schema

```sql
psql -h nuq-postgres -U postgres -d postgres
SET search_path TO turkish_financial, public;
\dt   -- list tables
```

---

## Verify Installation

```bash
# Test domain layer (no external deps)
python3 -c "
from domain.entities.kap_report import KAPReport
from domain.value_objects.sentiment import SentimentAnalysis, SentimentType, ImpactHorizon, Confidence
from datetime import datetime, date

report = KAPReport(id=1, company_code='AKBNK', company_name='Akbank',
    report_type='Financial', report_date=date(2025, 1, 20),
    title='Test', summary='Test', data={}, scraped_at=datetime.now())
print('Domain layer OK:', report.company_code)
"

# Test database connection
python3 -c "
from database.db_manager import DatabaseManager
db = DatabaseManager()
print('DB connected, schema:', db.schema)
"

# Start API server
python3 api_server.py
# Then: curl http://localhost:8000/api/v1/health
```

---

## Troubleshooting

### Database won't connect
1. `docker ps | grep nuq-postgres` — confirm container is running
2. Check `DB_HOST=nuq-postgres` (not `localhost`) in `.env`
3. Create DB if missing: `docker exec -it nuq-postgres psql -U postgres -c "CREATE DATABASE backtofuture;"`

### Schema not found
1. Check `DB_SCHEMA=turkish_financial` in `.env`
2. Run the app once — schema auto-creates
3. Or manually: `CREATE SCHEMA turkish_financial;`

### Permission errors on schema
```sql
GRANT ALL ON SCHEMA turkish_financial TO your_user;
GRANT ALL PRIVILEGES ON ALL TABLES IN SCHEMA turkish_financial TO your_user;
```

### Port 8000 in use
```bash
lsof -i :8000   # find conflicting process
# then kill it or change port in api_server.py
```

### Import errors after adding packages
```bash
pip install -r requirements.txt   # re-run after any requirements change
```

### Tables in wrong schema
If tables landed in `public` instead of `turkish_financial`, set `DB_SCHEMA=public` temporarily, then migrate (see above).
