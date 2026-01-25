# DevContainer Setup and Testing Guide

## 🚀 Quick Setup

### Step 1: Install Dependencies

The devcontainer has Python 3, but dependencies need to be installed:

```bash
cd /workspaces/firecrawl/examples/turkish-financial-data-scraper

# Option A: Install system-wide (if you have permissions)
pip3 install -r requirements.txt

# Option B: Use virtual environment (recommended)
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

### Step 2: Verify Environment

Check `.env` file has correct settings:

```bash
cat .env | grep -E "DB_|FIRECRAWL"
```

Should show:
```
DB_HOST=nuq-postgres
DB_PORT=5432
DB_NAME=postgres
DB_USER=postgres
DB_PASSWORD=postgres
DB_SCHEMA=turkish_financial
FIRECRAWL_BASE_URL=http://api:3002
```

### Step 3: Create Database (if needed)

```bash
# Connect to PostgreSQL
docker exec -it nuq-postgres psql -U postgres -d postgres

# Create database (if it doesn't exist)
CREATE DATABASE backtofuture;

# Or use existing postgres database (already configured in .env)
# Exit psql
\q
```

### Step 4: Run Tests

```bash
# Simple structure test (no dependencies needed)
python3 test_services_simple.py

# Full service test (requires dependencies)
python3 test_devcontainer_services.py
```

---

## ✅ Service Verification

### 1. Check Docker Services

```bash
# List running services
docker ps --format "table {{.Names}}\t{{.Status}}\t{{.Ports}}"

# Should show:
# - nuq-postgres (PostgreSQL)
# - redis (Redis)
# - rabbitmq (RabbitMQ)
# - api (Firecrawl API)
# - playwright-service (Playwright)
# - go-html-to-md-service (Go service)
```

### 2. Test Database Connection

```bash
cd /workspaces/firecrawl/examples/turkish-financial-data-scraper
source venv/bin/activate  # if using venv

python3 -c "
from database.db_manager import DatabaseManager
from config import config

print(f'Connecting to: {config.database.host}:{config.database.port}/{config.database.database}')
print(f'Schema: {config.database.schema}')

db = DatabaseManager()
print('✅ Database connected!')
print(f'✅ Schema: {db.schema}')

# Verify schema exists
conn = db.get_connection()
cursor = conn.cursor()
cursor.execute('SELECT schema_name FROM information_schema.schemata WHERE schema_name = %s', (db.schema,))
result = cursor.fetchone()
db.return_connection(conn)

if result:
    print(f'✅ Schema {db.schema} exists')
else:
    print(f'⚠️ Schema {db.schema} will be created on first use')
"
```

### 3. Test Domain Layer

```bash
python3 -c "
from domain.entities.kap_report import KAPReport
from domain.value_objects.sentiment import SentimentAnalysis, SentimentType, ImpactHorizon, Confidence
from datetime import datetime, date

# Test entity
report = KAPReport(
    id=1,
    company_code='AKBNK',
    company_name='Akbank',
    report_type='Financial',
    report_date=date(2025, 1, 20),
    title='Test Report',
    summary='Test summary',
    data={'revenue': 1000000},
    scraped_at=datetime.now()
)

print('✅ KAPReport entity created')
print(f'   Company: {report.company_code}')
print(f'   Content length: {len(report.get_content())} chars')
print(f'   Is recent: {report.is_recent()}')
print(f'   Has financial data: {report.has_financial_data()}')

# Test value object
sentiment = SentimentAnalysis(
    overall_sentiment=SentimentType.POSITIVE,
    confidence=Confidence(0.85),
    impact_horizon=ImpactHorizon.MEDIUM_TERM,
    key_drivers=('Growth', 'Expansion'),
    risk_flags=('Debt',),
    tone_descriptors=('Optimistic',),
    target_audience='retail_investors',
    analysis_text='Test analysis',
    analyzed_at=datetime.now()
)

print('✅ SentimentAnalysis value object created')
print(f'   Sentiment: {sentiment.overall_sentiment.value}')
print(f'   Confidence: {sentiment.confidence.value}')
print(f'   Is positive: {sentiment.is_positive()}')
print(f'   Risk level: {sentiment.get_risk_level()}')
"
```

### 4. Test API Server

```bash
# Start API server
cd /workspaces/firecrawl/examples/turkish-financial-data-scraper
source venv/bin/activate
python3 api_server.py

# In another terminal, test health
curl http://localhost:8000/api/v1/health

# Expected response:
# {"status":"healthy","database":"connected","timestamp":"..."}
```

---

## 🧪 Running Full Test Suite

### Automated Test

```bash
./setup_and_test.sh
```

### Manual Test

```bash
# 1. Install dependencies
pip install -r requirements.txt

# 2. Run tests
python3 test_devcontainer_services.py
```

---

## 📋 Test Checklist

### Infrastructure Services (Docker Compose)

- [ ] PostgreSQL (`nuq-postgres`) - Port 5432
- [ ] Redis (`redis`) - Port 6379
- [ ] RabbitMQ (`rabbitmq`) - Port 5672
- [ ] Firecrawl API (`api`) - Port 3002
- [ ] Playwright Service (`playwright-service`) - Port 3000
- [ ] Go HTML-to-MD Service (`go-html-to-md-service`) - Port 8080

### Project Components

- [ ] Database connection works
- [ ] Schema created automatically
- [ ] All tables created
- [ ] Domain entities work
- [ ] Repositories instantiate
- [ ] Use cases work
- [ ] API server starts
- [ ] Sentiment analysis structure works
- [ ] Batch job manager works
- [ ] Webhook notifier works

---

## 🔧 Troubleshooting

### Issue: Dependencies Not Installed

**Solution**:
```bash
# Install pip if missing
apt-get update && apt-get install -y python3-pip

# Install dependencies
pip3 install -r requirements.txt
```

### Issue: Database Connection Fails

**Check**:
1. PostgreSQL is running: `docker ps | grep nuq-postgres`
2. `.env` has correct host: `DB_HOST=nuq-postgres`
3. Database exists: Create if needed

**Solution**:
```bash
# Create database
docker exec -it nuq-postgres psql -U postgres -c "CREATE DATABASE backtofuture;"
```

### Issue: Schema Not Found

**Solution**:
1. Ensure `DB_SCHEMA=turkish_financial` in `.env`
2. Run application once - schema auto-creates
3. Or manually: `CREATE SCHEMA turkish_financial;`

### Issue: Port 8000 Already in Use

**Solution**:
```bash
# Find what's using the port
lsof -i :8000

# Kill process or change port in api_server.py
```

---

## 📊 Expected Test Results

### All Services Working

```
✅ Database Connection - Connected to database 'postgres' on nuq-postgres:5432
✅ Schema Creation - Schema 'turkish_financial' exists
✅ Tables Creation - All 8 tables created
✅ Domain Entities - Domain entities and value objects work correctly
✅ Repositories - Repository implementations instantiated successfully
✅ Use Cases - Use cases can be instantiated with dependency injection
✅ Sentiment Analysis - Sentiment analysis structure works correctly
✅ Batch Jobs - Batch job manager works correctly
✅ Webhooks - Webhook notifier can be instantiated
⚠️ API Health - API server not running (optional)
```

---

## 🎯 Next Steps After Setup

1. **Start API Server**:
   ```bash
   python3 api_server.py
   ```

2. **Test API Endpoints**:
   ```bash
   curl http://localhost:8000/api/v1/health
   curl http://localhost:8000/docs  # Interactive docs
   ```

3. **Run Scraper**:
   ```bash
   python3 main.py --scraper kap --days 7
   ```

4. **Test Sentiment Analysis**:
   ```bash
   curl -X POST http://localhost:8000/api/v1/scrapers/kap/sentiment \
     -H "Content-Type: application/json" \
     -d '{"report_ids": [1, 2, 3]}'
   ```

---

## 📚 Documentation

- [SETUP_DEVCONTAINER.md](SETUP_DEVCONTAINER.md) - Complete setup guide
- [SCHEMA_ISOLATION.md](SCHEMA_ISOLATION.md) - Schema isolation details
- [DEVCONTAINER_TEST_REPORT.md](DEVCONTAINER_TEST_REPORT.md) - Test report format
- [DDD_ARCHITECTURE.md](docs/DDD_ARCHITECTURE.md) - Architecture guide

---

**Last Updated**: January 23, 2025
