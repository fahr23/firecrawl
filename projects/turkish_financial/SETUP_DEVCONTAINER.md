# Setting Up Turkish Financial Data Scraper in DevContainer

This guide will help you set up and run the Turkish Financial Data Scraper example project in your devcontainer environment.

## Prerequisites

The devcontainer already has:
- ✅ Python 3 installed
- ✅ PostgreSQL service (`nuq-postgres`) running
- ✅ All Firecrawl services (API, Playwright, etc.)
- ✅ Port 8000 forwarded for the API server

## Step 1: Install Python Dependencies

Navigate to the example project directory and install dependencies:

```bash
cd /workspaces/firecrawl/examples/turkish-financial-data-scraper
pip install -r requirements.txt
```

## Step 2: Create Database

The example project needs a database. You can either:

### Option A: Use the existing PostgreSQL database

Create a new database in the existing PostgreSQL service:

```bash
# Connect to PostgreSQL (from inside the devcontainer)
psql -h nuq-postgres -U postgres -d postgres

# Create the database
CREATE DATABASE backtofuture;

# Create a user (optional, or use postgres user)
CREATE USER backtofuture WITH PASSWORD 'back2future';
GRANT ALL PRIVILEGES ON DATABASE backtofuture TO backtofuture;

# The schema will be created automatically by the application
# Default schema name: turkish_financial
# You can change it via DB_SCHEMA environment variable

# Exit psql
\q
```

**Note:** The project uses its own schema (`turkish_financial` by default) to isolate all tables. The schema is created automatically when you first run the application. This keeps the project's data separate from other applications using the same database.

### Option B: Use the default postgres database

You can modify the `.env` file to use the existing `postgres` database instead.

## Step 3: Configure Environment Variables

Create a `.env` file in the example project directory:

```bash
cd /workspaces/firecrawl/examples/turkish-financial-data-scraper
cp .env.example .env
```

Edit the `.env` file with the following settings:

```env
# Firecrawl API Configuration
# Option 1: Use local Firecrawl API (running in devcontainer)
FIRECRAWL_BASE_URL=http://api:3002
# OR Option 2: Use Firecrawl API key (if you have one)
# FIRECRAWL_API_KEY=your_firecrawl_api_key_here

# Database Configuration (connect to nuq-postgres service)
DB_HOST=nuq-postgres
DB_PORT=5432
DB_NAME=backtofuture
DB_USER=postgres
DB_PASSWORD=postgres
DB_SCHEMA=turkish_financial

# Or if you created a custom user:
# DB_USER=backtofuture
# DB_PASSWORD=back2future

# Note: DB_SCHEMA creates an isolated schema for this project's tables

# Scraping Configuration
MAX_CONCURRENT_TASKS=10
RATE_LIMIT_PER_MINUTE=30
REQUEST_TIMEOUT=30

# Logging
LOG_LEVEL=INFO
LOG_FILE=logs/scraper.log

# Retry Configuration
MAX_RETRIES=3
RETRY_BACKOFF_FACTOR=2

# Firecrawl Options
FIRECRAWL_WAIT_FOR=3000
FIRECRAWL_TIMEOUT=30000
FIRECRAWL_FORMATS=markdown,html
```

**Important Notes:**
- Use `DB_HOST=nuq-postgres` (the service name) when connecting from inside the devcontainer
- Use `DB_HOST=localhost` and `DB_PORT=5433` if connecting from outside the container
- For Firecrawl, use `FIRECRAWL_BASE_URL=http://api:3002` to connect to the local Firecrawl API running in the devcontainer

## Step 4: Create Logs Directory

```bash
mkdir -p /workspaces/firecrawl/examples/turkish-financial-data-scraper/logs
```

## Step 5: Test the Setup

### Test Database Connection

```bash
cd /workspaces/firecrawl/examples/turkish-financial-data-scraper
python -c "from database.db_manager import DatabaseManager; db = DatabaseManager(); print('Database connection successful!')"
```

### Start the API Server

```bash
cd /workspaces/firecrawl/examples/turkish-financial-data-scraper
python api_server.py
```

The API will be available at:
- **API Base**: http://localhost:8000
- **Interactive Docs**: http://localhost:8000/docs
- **Health Check**: http://localhost:8000/api/v1/health

### Test with a Simple Scraper

```bash
# Run a simple test
python -c "
from scrapers.kap_scraper import KAPScraper
from database.db_manager import DatabaseManager
import asyncio

async def test():
    db = DatabaseManager()
    scraper = KAPScraper(db_manager=db)
    print('Scraper initialized successfully!')

asyncio.run(test())
"
```

## Step 6: Run the Full Example

### Using the REST API (Recommended)

1. Start the API server:
   ```bash
   python api_server.py
   ```

2. In another terminal, test the API:
   ```bash
   # Health check
   curl http://localhost:8000/api/v1/health
   
   # Scrape KAP reports (example)
   curl -X POST http://localhost:8000/api/v1/scrapers/kap \
     -H "Content-Type: application/json" \
     -d '{"days_back": 7, "download_pdfs": false}'
   ```

### Using the CLI

```bash
# Run all scrapers
python main.py --all

# Run specific scraper
python main.py --scraper kap --days 7
```

## Troubleshooting

### Database Connection Issues

If you get connection errors:
1. Verify PostgreSQL is running: `docker ps | grep nuq-postgres`
2. Check database exists: `psql -h nuq-postgres -U postgres -l`
3. Verify credentials in `.env` match PostgreSQL setup

### Firecrawl Connection Issues

If Firecrawl API calls fail:
1. Verify Firecrawl API is running: `curl http://api:3002/health` (from inside container)
2. Check if you need to use `FIRECRAWL_API_KEY` instead of `FIRECRAWL_BASE_URL`
3. For self-hosted, ensure the API service is accessible

### Port Already in Use

If port 8000 is already in use:
1. Check what's using it: `lsof -i :8000`
2. Modify `api_server.py` to use a different port
3. Update `forwardPorts` in `devcontainer.json` if needed

### Python Import Errors

If you get import errors:
1. Ensure all dependencies are installed: `pip install -r requirements.txt`
2. Check you're in the correct directory
3. Verify Python version: `python3 --version` (should be 3.8+)

## Next Steps

- Read the [README.md](README.md) for detailed usage instructions
- Check [API Documentation](docs/API_DOCUMENTATION.md) for API endpoints
- Review [Architecture Guide](ARCHITECTURE.md) for project structure
- See [Quick Start Guide](docs/QUICK_START_ENHANCED.md) for advanced features

## Notes

- The devcontainer automatically forwards port 8000, so you can access the API from your host machine
- All services (PostgreSQL, Redis, RabbitMQ) are already running in the docker-compose setup
- The workspace is mounted, so all changes persist
- You can use the local Firecrawl API or provide your own API key
