# Operations Guide — Start, Restart & Debug

## Prerequisites

These services must be running before starting the API:

| Service | Check |
|---------|-------|
| PostgreSQL | `pg_isready -h nuq-postgres -U postgres` |
| Firecrawl | `curl -s http://localhost:3002/health` |

---

## Start the Server

Always run from the project root:

```bash
cd /workspaces/firecrawl/projects/turkish_financial
```

### Foreground (see logs in terminal)

```bash
SENTIMENT_PROVIDER=keyword \
APP_DB_HOST=nuq-postgres APP_DB_PORT=5432 APP_DB_NAME=postgres \
APP_DB_USER=postgres APP_DB_PASSWORD=postgres \
DB_SCHEMA=turkish_financial \
FIRECRAWL_BASE_URL=http://localhost:3002 FIRECRAWL_API_KEY=fc-local \
venv/bin/python3 -m uvicorn api.main:app --host 0.0.0.0 --port 8000
```

Press `Ctrl+C` to stop.

### Background (log to file)

```bash
SENTIMENT_PROVIDER=keyword \
APP_DB_HOST=nuq-postgres APP_DB_PORT=5432 APP_DB_NAME=postgres \
APP_DB_USER=postgres APP_DB_PASSWORD=postgres \
DB_SCHEMA=turkish_financial \
FIRECRAWL_BASE_URL=http://localhost:3002 FIRECRAWL_API_KEY=fc-local \
venv/bin/python3 -m uvicorn api.main:app --host 0.0.0.0 --port 8000 \
  > /tmp/api_server.log 2>&1 &

echo "Server PID: $!"
```

Verify it started:

```bash
sleep 5 && curl -s http://localhost:8000/api/external/v1/health
# Expected: {"status":"ok","contract_version":"1.0","provider":"kap-scraper"}
```

---

## Restart the Server

```bash
# 1. Kill the existing process
fuser -k 8000/tcp 2>/dev/null
sleep 2

# 2. Start again (background)
cd /workspaces/firecrawl/projects/turkish_financial

SENTIMENT_PROVIDER=keyword \
APP_DB_HOST=nuq-postgres APP_DB_PORT=5432 APP_DB_NAME=postgres \
APP_DB_USER=postgres APP_DB_PASSWORD=postgres \
DB_SCHEMA=turkish_financial \
FIRECRAWL_BASE_URL=http://localhost:3002 FIRECRAWL_API_KEY=fc-local \
venv/bin/python3 -m uvicorn api.main:app --host 0.0.0.0 --port 8000 \
  > /tmp/api_server.log 2>&1 &

sleep 5 && curl -s http://localhost:8000/api/external/v1/health
```

---

## Stop the Server

```bash
fuser -k 8000/tcp 2>/dev/null
```

Or find the PID manually:

```bash
lsof -i :8000
kill <PID>
```

---

## Read Logs

### Live log stream

```bash
tail -f /tmp/api_server.log
```

### Last 50 lines

```bash
tail -50 /tmp/api_server.log
```

### Only errors

```bash
grep -i "error\|exception\|traceback" /tmp/api_server.log | tail -30
```

### Specific request path

```bash
grep "POST /api/v1/scrapers/kap\|GET /api/external" /tmp/api_server.log | tail -20
```

---

## Log Format

Every request logs an INCOMING block and an OUTGOING block:

```
📥 INCOMING REQUEST
   Method: POST
   Path: /api/v1/scrapers/kap
   Payload: {"days_back": 7}

📤 OUTGOING RESPONSE
   Status Code: 200
   Process Time: 3.142s
   Payload: {"success": true, ...}
```

Errors appear as `ERROR` lines (red in terminal, prefixed with logger name):

```
2026-06-28 20:37:04 - production_kap_final - ERROR - Scraping failed: ...
2026-06-28 20:44:52 - utils.llm_analyzer   - ERROR - Error with OpenAI API: 429 ...
```

---

## Common Bugs and Fixes

### `ModuleNotFoundError: No module named 'api'`

**Cause:** Not running from the project root directory.

```bash
# Wrong — run from anywhere else
python3 -m uvicorn api.main:app ...

# Correct
cd /workspaces/firecrawl/projects/turkish_financial
venv/bin/python3 -m uvicorn api.main:app ...
```

---

### `connection pool exhausted` / `connection refused to nuq-postgres`

**Cause:** Wrong DB env vars or database not reachable.

```bash
# Test DB connection
pg_isready -h nuq-postgres -p 5432 -U postgres

# Check env vars are set
echo $APP_DB_HOST   # should print: nuq-postgres
```

The config reads `APP_DB_*` variables, not `DB_*`. Make sure the server is started with:
```
APP_DB_HOST=nuq-postgres
APP_DB_PORT=5432
APP_DB_NAME=postgres
APP_DB_USER=postgres
APP_DB_PASSWORD=postgres
```

---

### `429 Too Many Requests` / `insufficient_quota` from OpenAI

**Cause:** `SENTIMENT_PROVIDER` is unset or set to `openai`, but the OpenAI key has no quota.

**Fix:** Force keyword provider (no external calls):

```bash
SENTIMENT_PROVIDER=keyword venv/bin/python3 -m uvicorn api.main:app ...
```

Available values for `SENTIMENT_PROVIDER`:

| Value | Behaviour |
|-------|-----------|
| `keyword` | Built-in Turkish keyword matching. Fast, free, no network. |
| `huggingface` | Local BERT model (`savasy/bert-base-turkish-sentiment-cased`). Needs ~500 MB RAM. |
| `openai` | OpenAI GPT. Needs `OPENAI_API_KEY` with quota. |
| `gemini` | Google Gemini. Needs `GEMINI_API_KEY`. |

---

### `[Errno 98] Address already in use`

**Cause:** Old server process still holds port 8000.

```bash
fuser -k 8000/tcp 2>/dev/null
sleep 2
# then start again
```

---

### `ProductionKAPScraper has no attribute '_fallback_scrape_url'` / `Cannot connect to host localhost:3000`

**Cause:** `POST /api/v1/scrapers/kap` uses `ProductionKAPScraper` which calls the Playwright service on port 3000. That service is not running.

**Status:** Known issue — KAP's website also blocks automated scraping. Disclosures must be seeded via the database directly or via a working proxy setup.

See [ANTI_BOT.md](ANTI_BOT.md) for proxy options.

---

### `scraped: 20, analyzed: 0, saved: 0` from news-sentiment/collect

**Cause:** Sentiment analyzer is calling OpenAI (quota exceeded) and returning no results.

**Fix:** Restart with `SENTIMENT_PROVIDER=keyword`.

---

### API returns `"status": "unavailable"` on a GET endpoint

**Cause:** That ticker has no data in the database yet.

```bash
# Check what's in the DB for that ticker
psql -h nuq-postgres -U postgres -d postgres -c \
  "SELECT ticker, period_date, combined_score FROM turkish_financial.aggregated_ticker_sentiment WHERE ticker='THYAO';"
```

Trigger a data collection to populate it:

```bash
curl -X POST http://localhost:8000/api/external/v1/news-sentiment/collect \
  -H "Content-Type: application/json" \
  -d '{"days_back": 7, "sources": ["bloomberght"], "include_investing_comments": false}'
```

---

## Trigger Data Collection

Run these after starting the server to populate data:

### News sentiment (Bloomberg HT RSS — works reliably)

```bash
curl -X POST http://localhost:8000/api/external/v1/news-sentiment/collect \
  -H "Content-Type: application/json" \
  -d '{"days_back": 7, "sources": ["bloomberght", "mynetfinans"], "include_investing_comments": false}'
```

### KAP regulatory news

```bash
curl -X POST http://localhost:8000/api/v1/scrapers/kap \
  -H "Content-Type: application/json" \
  -d '{"days_back": 3, "download_pdfs": false}'
# Note: may fail if KAP blocks the request — see ANTI_BOT.md
```

---

## Verify All Endpoints Are Working

```bash
BASE=http://localhost:8000/api/external/v1

curl -s $BASE/health
curl -s "$BASE/sentiment/THYAO?market=bist"
curl -s "$BASE/fundamental/THYAO?market=bist"
curl -s "$BASE/news-sentiment/THYAO?market=bist"
curl -s "$BASE/combined-sentiment/THYAO?market=bist"
curl -s "$BASE/sentiment/overview?market=bist"
curl -s "$BASE/news?limit=3"

# Batch
curl -s -X POST "$BASE/sentiment/batch" \
  -H "Content-Type: application/json" \
  -d '{"instruments":["THYAO","GARAN","AKBNK"],"market":"bist"}'
```

Expected: every response has `"status": "ok"` or `"contract_version": "1.0"`. Anything with `"status": "unavailable"` means that ticker has no data yet.

---

## Interactive API Docs

When the server is running, open:

```
http://localhost:8000/docs
```

This is Swagger UI — you can call every endpoint directly from the browser.
