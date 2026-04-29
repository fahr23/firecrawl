# Firecrawl Project Structure & External Endpoints Analysis

## Project Overview

Firecrawl is a web scraping and crawling API service that converts websites into clean markdown or structured data. It's a monorepo containing the API server, multiple SDKs, and supporting services.

## Project Structure

### Core Applications (`/apps`)

1. **`apps/api`** - Main API server (TypeScript/Express)
   - Contains all API routes, controllers, and business logic
   - Handles scraping, crawling, extraction, and search operations
   - Uses Express.js with WebSocket support
   - Main entry point: `apps/api/src/index.ts`

2. **`apps/js-sdk`** - JavaScript/TypeScript SDK
   - Client library for Node.js and browser environments

3. **`apps/python-sdk`** - Python SDK
   - Client library for Python applications

4. **`apps/rust-sdk`** - Rust SDK
   - Client library for Rust applications

5. **`apps/go-html-to-md-service`** - Go microservice
   - Converts HTML to Markdown

6. **`apps/playwright-service-ts`** - Playwright service
   - Handles browser automation and JavaScript rendering

7. **`apps/nuq-postgres`** - PostgreSQL database
   - Stores crawl jobs and metadata

8. **`apps/redis`** - Redis service
   - Used for caching, rate limiting, and job queues

9. **`apps/test-site`** - Test website
   - Astro-based test site for development

10. **`apps/test-suite`** - Test suite
    - End-to-end and integration tests

11. **`apps/ui`** - UI components
    - React/TypeScript UI components

### Supporting Directories

- **`examples/`** - Example implementations and tutorials
- **`getData_ff/`** - Financial data scraping utilities (appears to be custom/additional functionality)
- **`.github/`** - GitHub workflows and templates

## External API Endpoints

### Base URL
- **Production**: `https://api.firecrawl.dev`
- **Local Development**: `http://localhost:3002` (default)

### API Versions

The API supports three versions: **v0**, **v1**, and **v2**. **v2** is the current recommended version.

---

## V2 API Endpoints (Current/Recommended)

### Core Scraping & Crawling

#### 1. **POST `/v2/scrape`**
- **Purpose**: Scrape a single URL and get content in specified formats
- **Auth**: Required (Bearer token)
- **Rate Limit**: Scrape mode
- **Credits**: 1 credit minimum
- **Features**: 
  - Supports formats: markdown, html, links, screenshot, json (with LLM extraction)
  - Can perform actions (click, scroll, wait, etc.) before scraping
  - Supports LLM extraction with schema or prompt

#### 2. **GET `/v2/scrape/:jobId`**
- **Purpose**: Check status of an async scrape job
- **Auth**: Required
- **Rate Limit**: CrawlStatus mode

#### 3. **POST `/v2/batch/scrape`**
- **Purpose**: Batch scrape multiple URLs asynchronously
- **Auth**: Required
- **Rate Limit**: Scrape mode
- **Returns**: Job ID for status checking

#### 4. **GET `/v2/batch/scrape/:jobId`**
- **Purpose**: Check status of batch scrape job
- **Auth**: Required

#### 5. **DELETE `/v2/batch/scrape/:jobId`**
- **Purpose**: Cancel a batch scrape job
- **Auth**: Required

#### 6. **GET `/v2/batch/scrape/:jobId/errors`**
- **Purpose**: Get errors from batch scrape job
- **Auth**: Required

#### 7. **POST `/v2/crawl`**
- **Purpose**: Start crawling a website (all accessible subpages)
- **Auth**: Required
- **Rate Limit**: Crawl mode
- **Credits**: Variable (based on pages crawled)
- **Returns**: Job ID for status checking
- **Features**: 
  - Supports idempotency
  - Configurable limits, depth, filters

#### 8. **GET `/v2/crawl/:jobId`**
- **Purpose**: Check status and get results of crawl job
- **Auth**: Required
- **Rate Limit**: CrawlStatus mode
- **Supports**: WebSocket connection for real-time updates

#### 9. **DELETE `/v2/crawl/:jobId`**
- **Purpose**: Cancel an ongoing crawl job
- **Auth**: Required

#### 10. **GET `/v2/crawl/:jobId/errors`**
- **Purpose**: Get errors from crawl job
- **Auth**: Required

#### 11. **GET `/v2/crawl/ongoing`** or **`/v2/crawl/active`**
- **Purpose**: Get list of ongoing/active crawl jobs
- **Auth**: Required

#### 12. **POST `/v2/crawl/params-preview`**
- **Purpose**: Preview crawl parameters before starting
- **Auth**: Required

#### 13. **WS `/v2/crawl/:jobId`** (WebSocket)
- **Purpose**: Real-time updates for crawl job status
- **Auth**: Required (via query params or headers)

### Mapping & Discovery

#### 14. **POST `/v2/map`**
- **Purpose**: Map a website and get all URLs (fast discovery)
- **Auth**: Required
- **Rate Limit**: Map mode
- **Credits**: 1 credit
- **Features**: 
  - Can search for specific URLs within a website
  - Returns links with titles and descriptions

### Search

#### 15. **POST `/v2/search`**
- **Purpose**: Search the web and optionally scrape results
- **Auth**: Required
- **Rate Limit**: Search mode
- **Credits**: Variable
- **Features**: 
  - Web search with SERP results
  - Optional content scraping from results
  - Supports multiple sources (web, news, images)

#### 16. **POST `/v2/x402/search`**
- **Purpose**: Search endpoint with X402 micropayment protocol
- **Auth**: Required
- **Payment**: Micropayment required (X402 protocol)
- **Features**: Same as `/v2/search` but with payment gateway

### Extraction & AI

#### 17. **POST `/v2/extract`**
- **Purpose**: Extract structured data from URLs using AI
- **Auth**: Required
- **Rate Limit**: Extract mode
- **Credits**: 20 credits minimum
- **Features**: 
  - Supports single page, multiple pages, or wildcard patterns (`/*`)
  - Uses LLM to extract structured data based on schema or prompt
  - Returns job ID for async processing

#### 18. **GET `/v2/extract/:jobId`**
- **Purpose**: Check status of extract job
- **Auth**: Required

#### 19. **POST `/v2/agent`**
- **Purpose**: AI agent endpoint for complex web interactions
- **Auth**: Required
- **Rate Limit**: Extract mode
- **Credits**: 20 credits minimum
- **Features**: Advanced AI-powered web automation

#### 20. **GET `/v2/agent/:jobId`**
- **Purpose**: Check status of agent job
- **Auth**: Required

#### 21. **DELETE `/v2/agent/:jobId`**
- **Purpose**: Cancel an agent job
- **Auth**: Required

### Team & Usage

#### 22. **GET `/v2/team/credit-usage`**
- **Purpose**: Get current credit usage for team
- **Auth**: Required

#### 23. **GET `/v2/team/credit-usage/historical`**
- **Purpose**: Get historical credit usage data
- **Auth**: Required

#### 24. **GET `/v2/team/token-usage`**
- **Purpose**: Get current token usage for team
- **Auth**: Required

#### 25. **GET `/v2/team/token-usage/historical`**
- **Purpose**: Get historical token usage data
- **Auth**: Required

#### 26. **GET `/v2/team/queue-status`**
- **Purpose**: Get queue status for team jobs
- **Auth**: Required

#### 27. **GET `/v2/concurrency-check`**
- **Purpose**: Check concurrency limits and availability
- **Auth**: Required

---

## V1 API Endpoints (Legacy)

Most endpoints mirror v2, with some differences:

- **POST `/v1/scrape`** - Scrape single URL
- **POST `/v1/crawl`** - Start crawl job
- **GET `/v1/crawl/:jobId`** - Check crawl status
- **DELETE `/v1/crawl/:jobId`** - Cancel crawl
- **POST `/v1/batch/scrape`** - Batch scrape
- **GET `/v1/batch/scrape/:jobId`** - Batch scrape status
- **POST `/v1/map`** - Map website
- **POST `/v1/search`** - Web search
- **POST `/v1/extract`** - Extract structured data
- **GET `/v1/extract/:jobId`** - Extract status
- **POST `/v1/llmstxt`** - Generate LLMs.txt file
- **GET `/v1/llmstxt/:jobId`** - LLMs.txt status
- **POST `/v1/deep-research`** - Deep research feature
- **GET `/v1/deep-research/:jobId`** - Deep research status
- **GET `/v1/crawl/ongoing`** or **`/v1/crawl/active`** - Active crawls
- **GET `/v1/crawl/:jobId/errors`** - Crawl errors
- **GET `/v1/batch/scrape/:jobId/errors`** - Batch scrape errors
- **GET `/v1/scrape/:jobId`** - Scrape status
- **GET `/v1/concurrency-check`** - Concurrency check
- **WS `/v1/crawl/:jobId`** - WebSocket for crawl updates
- **GET `/v1/team/credit-usage`** - Credit usage
- **GET `/v1/team/credit-usage/historical`** - Historical credits
- **GET `/v1/team/token-usage`** - Token usage
- **GET `/v1/team/token-usage/historical`** - Historical tokens
- **GET `/v1/team/queue-status`** - Queue status
- **POST `/v1/x402/search`** - X402 search endpoint

---

## V0 API Endpoints (Deprecated)

- **POST `/v0/scrape`** - Scrape endpoint
- **POST `/v0/crawl`** - Crawl endpoint
- **GET `/v0/crawl/status/:jobId`** - Crawl status
- **DELETE `/v0/crawl/cancel/:jobId`** - Cancel crawl
- **POST `/v0/search`** - Search endpoint
- **GET `/v0/keyAuth`** - Key authentication
- **GET `/v0/health/liveness`** - Liveness probe
- **GET `/v0/health/readiness`** - Readiness probe

---

## Admin Endpoints

All admin endpoints require authentication via `BULL_AUTH_KEY`:

- **GET `/admin/{BULL_AUTH_KEY}/redis-health`** - Redis health check
- **POST `/admin/{BULL_AUTH_KEY}/acuc-cache-clear`** - Clear ACUC cache
- **GET `/admin/{BULL_AUTH_KEY}/feng-check`** - Fire engine check
- **GET `/admin/{BULL_AUTH_KEY}/cclog`** - CCLog endpoint
- **GET `/admin/{BULL_AUTH_KEY}/zdrcleaner`** - ZDR cleaner
- **GET `/admin/{BULL_AUTH_KEY}/index-queue-prometheus`** - Prometheus metrics
- **GET `/admin/{BULL_AUTH_KEY}/precrawl`** - Trigger precrawl
- **GET `/admin/{BULL_AUTH_KEY}/metrics`** - General metrics
- **GET `/admin/{BULL_AUTH_KEY}/nuq-metrics`** - NUQ metrics
- **POST `/admin/{BULL_AUTH_KEY}/fsearch`** - Realtime search
- **POST `/admin/{BULL_AUTH_KEY}/concurrency-queue-backfill`** - Queue backfill
- **POST `/admin/{BULL_AUTH_KEY}/crawl-monitor`** - Crawl monitoring
- **POST `/admin/integration/create-user`** - Create user (integration)
- **POST `/admin/integration/validate-api-key`** - Validate API key
- **POST `/admin/integration/rotate-api-key`** - Rotate API key
- **GET `/admin/{BULL_AUTH_KEY}/queues`** - Bull Board queue management UI

---

## Root Endpoints

- **GET `/`** - API information and documentation URL
- **GET `/e2e-test`** - E2E test endpoint
- **GET `/is-production`** - Production status check

---

## Authentication

### Production Authentication

All endpoints (except health checks and root) require:
- **Header**: `Authorization: Bearer {API_KEY}`
- API keys can be obtained from [firecrawl.dev](https://firecrawl.dev)

### Local Development Authentication

In local development, authentication can be **bypassed** or **configured** depending on your setup:

#### Option 1: Bypass Authentication (Default for Local Dev)

**Configuration:**
```bash
# In apps/api/.env
USE_DB_AUTHENTICATION=false
```

**How it works:**
- When `USE_DB_AUTHENTICATION=false`, the API automatically bypasses authentication
- Any API key (or no API key) will work
- A mock authentication chunk is created with:
  - **Team ID**: `"bypass"`
  - **Credits**: Unlimited (99,999,999 credits)
  - **Rate Limits**: Unlimited (99,999,999 requests/min)
  - **Concurrency**: Unlimited (99,999,999 concurrent jobs)

**Example Request (No Auth Required):**
```bash
# Works without any API key
curl -X POST http://localhost:3002/v2/scrape \
  -H "Content-Type: application/json" \
  -d '{
    "url": "https://firecrawl.dev"
  }'

# Also works with any dummy API key
curl -X POST http://localhost:3002/v2/scrape \
  -H "Authorization: Bearer any-key-works" \
  -H "Content-Type: application/json" \
  -d '{
    "url": "https://firecrawl.dev"
  }'
```

**Warning Messages:**
When bypassing authentication, you'll see warnings in logs:
```
WARN - You're bypassing authentication
```
This is expected and safe for local development.

#### Option 2: Use Database Authentication (Production-like)

**Configuration:**
```bash
# In apps/api/.env
USE_DB_AUTHENTICATION=true
SUPABASE_URL=https://your-project.supabase.co
SUPABASE_ANON_TOKEN=your-anon-token
SUPABASE_SERVICE_TOKEN=your-service-token
```

**How it works:**
- Authentication is validated against Supabase
- API keys must be valid UUIDs stored in the database
- Credits and rate limits are enforced based on your plan
- Requires Supabase setup with proper schema

**Creating API Keys:**
1. Set up Supabase project
2. Configure database schema (see Supabase setup docs)
3. Create API keys through your application or admin interface
4. Use the generated UUID as your API key

**Example Request (With Real Auth):**
```bash
curl -X POST http://localhost:3002/v2/scrape \
  -H "Authorization: Bearer fc-12345678-1234-1234-1234-123456789abc" \
  -H "Content-Type: application/json" \
  -d '{
    "url": "https://firecrawl.dev"
  }'
```

#### Option 3: Preview Token (Limited Access)

**Configuration:**
```bash
# In apps/api/.env
PREVIEW_TOKEN=your-preview-token-here
```

**How it works:**
- Special token for preview/playground access
- Limited rate limits:
  - Crawl: 2 req/min
  - Scrape: 10 req/min
  - Extract: 10 req/min
  - Search: 5 req/min
  - Map: 5 req/min
- Team ID format: `preview_{ip}_{token}`
- Credits: 99,999,999 (unlimited for preview)

**Example Request:**
```bash
curl -X POST http://localhost:3002/v2/scrape \
  -H "Authorization: Bearer your-preview-token-here" \
  -H "Content-Type: application/json" \
  -d '{
    "url": "https://firecrawl.dev"
  }'
```

### Authentication Flow

```
Request with Authorization Header
  ↓
Extract Bearer Token
  ↓
Check USE_DB_AUTHENTICATION
  ↓
├─ false → Return mockACUC() (bypass)
│         - Team ID: "bypass"
│         - Unlimited credits/rate limits
│
├─ true → Validate token against Supabase
│         ├─ Valid UUID → Get ACUC from DB
│         └─ Invalid → Return 401 Unauthorized
│
└─ PREVIEW_TOKEN → Return mockPreviewACUC()
                  - Limited rate limits
                  - Team ID: "preview_{ip}_{token}"
```

### Mock Authentication Details

When `USE_DB_AUTHENTICATION=false`, the system creates a mock authentication chunk:

```typescript
{
  api_key: "bypass",
  team_id: "bypass",
  remaining_credits: 99999999,
  rate_limits: {
    crawl: 99999999,
    scrape: 99999999,
    extract: 99999999,
    search: 99999999,
    map: 99999999,
    // ... all unlimited
  },
  concurrency: 99999999,
  flags: null
}
```

### Testing Authentication

**Test without authentication:**
```bash
# No auth header needed
curl -X POST http://localhost:3002/v2/scrape \
  -H "Content-Type: application/json" \
  -d '{"url": "https://example.com"}'
```

**Test with dummy key:**
```bash
# Any key works when USE_DB_AUTHENTICATION=false
curl -X POST http://localhost:3002/v2/scrape \
  -H "Authorization: Bearer test-key-123" \
  -H "Content-Type: application/json" \
  -d '{"url": "https://example.com"}'
```

**Test with real key (if DB auth enabled):**
```bash
# Requires valid UUID from Supabase
curl -X POST http://localhost:3002/v2/scrape \
  -H "Authorization: Bearer fc-valid-uuid-here" \
  -H "Content-Type: application/json" \
  -d '{"url": "https://example.com"}'
```

### SDK Usage in Local Development

**JavaScript/TypeScript:**
```javascript
import FirecrawlApp from '@mendable/firecrawl-js';

// Option 1: No API key needed (bypass mode)
const app = new FirecrawlApp({ 
  apiUrl: 'http://localhost:3002'
  // No apiKey needed when USE_DB_AUTHENTICATION=false
});

// Option 2: Any dummy key works
const app = new FirecrawlApp({ 
  apiKey: 'local-dev-key',
  apiUrl: 'http://localhost:3002'
});
```

**Python:**
```python
from firecrawl import FirecrawlApp

# Option 1: No API key needed (bypass mode)
app = FirecrawlApp(api_url="http://localhost:3002")

# Option 2: Any dummy key works
app = FirecrawlApp(
    api_key="local-dev-key",
    api_url="http://localhost:3002"
)
```

### Environment Variables Summary

| Variable | Default | Description |
|----------|---------|-------------|
| `USE_DB_AUTHENTICATION` | `false` | Enable/disable database authentication |
| `SUPABASE_URL` | - | Supabase project URL (required if `USE_DB_AUTHENTICATION=true`) |
| `SUPABASE_ANON_TOKEN` | - | Supabase anonymous token |
| `SUPABASE_SERVICE_TOKEN` | - | Supabase service role token |
| `PREVIEW_TOKEN` | - | Special preview/playground token |
| `TEST_API_KEY` | - | Optional test API key for integration tests |

### Notes

- **Local Development**: Default is `USE_DB_AUTHENTICATION=false` for easy testing
- **Production**: Always use `USE_DB_AUTHENTICATION=true` with proper Supabase setup
- **SDKs**: API keys are optional when connecting to local instances with bypass enabled
- **Security**: Never use bypass mode in production or exposed environments

---

## Rate Limiting

Different endpoints have different rate limit modes:
- **Scrape**: For single scrape operations
- **Crawl**: For crawl operations
- **CrawlStatus**: For status checks
- **Map**: For mapping operations
- **Search**: For search operations
- **Extract**: For extraction operations
- **ExtractStatus**: For extraction status checks

---

## Common Features Across Endpoints

1. **Credit System**: Most operations consume credits
2. **Blocklist**: URLs can be blocked via blocklist middleware
3. **Country Check**: Some endpoints check country restrictions
4. **Idempotency**: Crawl and batch operations support idempotency
5. **WebSocket Support**: Real-time updates for crawl jobs
6. **Async Processing**: Long-running operations return job IDs
7. **Error Tracking**: Errors can be retrieved per job

---

## Data Formats Supported

- **Markdown**: Clean markdown output
- **HTML**: Raw HTML content
- **Links**: Extracted links from pages
- **Screenshot**: Page screenshots
- **JSON**: Structured data via LLM extraction
- **Metadata**: Page metadata (title, description, etc.)

---

## External Services Integration

The API integrates with:
- **Supabase**: Database and authentication
- **Redis**: Caching, rate limiting, job queues
- **PostgreSQL (NUQ)**: Job storage
- **Playwright Service**: Browser automation
- **Go HTML-to-MD Service**: HTML conversion
- **OpenAI/Ollama**: LLM services for extraction
- **Stripe**: Payment processing
- **Sentry**: Error tracking

---

## Documentation

- **API Docs**: https://docs.firecrawl.dev
- **Playground**: https://firecrawl.dev/playground
- **Base URL**: https://api.firecrawl.dev

---

## Notes

- **v2** is the recommended API version
- **v1** is maintained for backward compatibility
- **v0** is deprecated
- Most operations are async and return job IDs
- WebSocket support available for real-time crawl updates
- X402 micropayment protocol supported for premium search features

---

# Request & Action Flows with Examples

## Overview

This section details the request/response flows and action sequences for major Firecrawl operations, including status transitions, error handling, and practical examples.

---

## 1. Scrape Flow (Synchronous & Asynchronous)

### Synchronous Scrape Flow

**Use Case**: Quick single-page scraping with immediate results

#### Request Flow

```
Client → POST /v2/scrape
  ↓
[Authentication Middleware] → Validates API key
  ↓
[Rate Limiter] → Checks scrape rate limits
  ↓
[Country Check] → Validates country restrictions
  ↓
[Credit Check] → Verifies sufficient credits (1 credit minimum)
  ↓
[Blocklist Check] → Validates URL not blocked
  ↓
[Scrape Controller] → Processes request
  ↓
[Scrape Worker] → Fetches and processes page
  ↓
[Response] → Returns scraped data immediately
```

#### Example Request

```bash
curl -X POST https://api.firecrawl.dev/v2/scrape \
  -H "Authorization: Bearer fc-YOUR_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "url": "https://firecrawl.dev",
    "formats": ["markdown", "html", "links"]
  }'
```

#### Example Response

```json
{
  "success": true,
  "data": {
    "markdown": "# Firecrawl\n\nTurn any website into LLM-ready data...",
    "html": "<!DOCTYPE html><html>...</html>",
    "links": [
      {
        "url": "https://firecrawl.dev/pricing",
        "text": "Pricing"
      }
    ],
    "metadata": {
      "title": "Firecrawl - Turn websites into LLM-ready data",
      "description": "Firecrawl crawls and converts any website...",
      "language": "en",
      "sourceURL": "https://firecrawl.dev",
      "statusCode": 200
    }
  }
}
```

### Asynchronous Scrape Flow (with Actions)

**Use Case**: Scraping pages that require interaction (clicks, scrolling, waiting)

#### Request Flow

```
Client → POST /v2/scrape (with actions)
  ↓
[Validation] → Validates actions array
  ↓
[Job Creation] → Creates async job (returns jobId)
  ↓
[Queue Job] → Adds to scrape queue
  ↓
[Response] → Returns jobId immediately
  ↓
[Worker Processing] → Executes actions sequentially
  ↓
[Scraping] → Scrapes page after actions complete
```

#### Example Request with Actions

```bash
curl -X POST https://api.firecrawl.dev/v2/scrape \
  -H "Authorization: Bearer fc-YOUR_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "url": "https://example.com/search",
    "formats": ["markdown"],
    "actions": [
      {"type": "wait", "milliseconds": 2000},
      {"type": "click", "selector": "#search-button"},
      {"type": "wait", "milliseconds": 3000},
      {"type": "scroll", "direction": "down"},
      {"type": "wait", "milliseconds": 1000}
    ]
  }'
```

#### Response (Async Job Created)

```json
{
  "success": true,
  "jobId": "abc123-def456-ghi789",
  "status": "active"
}
```

#### Check Status

```bash
curl -X GET https://api.firecrawl.dev/v2/scrape/abc123-def456-ghi789 \
  -H "Authorization: Bearer fc-YOUR_API_KEY"
```

#### Status Response (Processing)

```json
{
  "success": true,
  "status": "active",
  "jobId": "abc123-def456-ghi789"
}
```

#### Status Response (Completed)

```json
{
  "success": true,
  "status": "completed",
  "jobId": "abc123-def456-ghi789",
  "data": {
    "markdown": "# Search Results\n\n...",
    "metadata": {
      "title": "Search Results",
      "sourceURL": "https://example.com/search",
      "statusCode": 200
    }
  }
}
```

---

## 2. Crawl Flow (Asynchronous)

### Complete Crawl Lifecycle

**Use Case**: Crawling entire websites with multiple pages

#### Request Flow

```
Client → POST /v2/crawl
  ↓
[Authentication] → Validates API key
  ↓
[Idempotency Check] → Checks for existing crawl with same params
  ↓
[Job Creation] → Creates crawl job with UUID
  ↓
[Save to Redis] → Stores crawl metadata
  ↓
[Queue Initial Scrape] → Adds first URL to queue
  ↓
[Response] → Returns jobId immediately
  ↓
[Worker Loop] → Processes URLs from queue
  ↓
[Link Discovery] → Finds new links on each page
  ↓
[Queue New URLs] → Adds discovered URLs to queue
  ↓
[Status Updates] → Updates progress in Redis
```

#### Example Request

```bash
curl -X POST https://api.firecrawl.dev/v2/crawl \
  -H "Authorization: Bearer fc-YOUR_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "url": "https://docs.firecrawl.dev",
    "limit": 10,
    "maxDepth": 2,
    "scrapeOptions": {
      "formats": ["markdown", "html"]
    }
  }'
```

#### Initial Response

```json
{
  "success": true,
  "id": "crawl-123-456-789",
  "url": "https://api.firecrawl.dev/v2/crawl/crawl-123-456-789"
}
```

### Status Check Flow

#### Polling Method

```bash
# Check status repeatedly
curl -X GET https://api.firecrawl.dev/v2/crawl/crawl-123-456-789 \
  -H "Authorization: Bearer fc-YOUR_API_KEY"
```

#### Status Response (Scraping)

```json
{
  "success": true,
  "status": "scraping",
  "total": 10,
  "completed": 3,
  "inProgress": 2,
  "failed": 0,
  "creditsUsed": 3
}
```

#### Status Response (Completed)

```json
{
  "success": true,
  "status": "completed",
  "total": 10,
  "completed": 10,
  "failed": 0,
  "creditsUsed": 10,
  "expiresAt": "2024-12-31T23:59:59.000Z",
  "data": [
    {
      "markdown": "# Documentation\n\n...",
      "html": "<!DOCTYPE html>...",
      "metadata": {
        "title": "Firecrawl Documentation",
        "sourceURL": "https://docs.firecrawl.dev",
        "statusCode": 200
      }
    },
    {
      "markdown": "# Getting Started\n\n...",
      "metadata": {
        "title": "Getting Started",
        "sourceURL": "https://docs.firecrawl.dev/getting-started",
        "statusCode": 200
      }
    }
    // ... 8 more pages
  ],
  "next": "https://api.firecrawl.dev/v2/crawl/crawl-123-456-789?page=2"
}
```

### WebSocket Flow (Real-time Updates)

#### Connection

```javascript
const ws = new WebSocket(
  'wss://api.firecrawl.dev/v2/crawl/crawl-123-456-789?apiKey=fc-YOUR_API_KEY'
);

ws.onmessage = (event) => {
  const update = JSON.parse(event.data);
  console.log('Status update:', update);
};
```

#### WebSocket Messages

**Progress Update:**
```json
{
  "type": "update",
  "status": "scraping",
  "completed": 5,
  "total": 10,
  "currentUrl": "https://docs.firecrawl.dev/api-reference"
}
```

**Completion:**
```json
{
  "type": "done",
  "status": "completed",
  "total": 10,
  "completed": 10,
  "data": [...]
}
```

**Error:**
```json
{
  "type": "error",
  "status": "failed",
  "error": "Connection timeout"
}
```

### Status Transitions

```
pending → queued → scraping → completed
                ↓
            failed (on error)
                ↓
            cancelled (if deleted)
```

### Cancel Crawl Flow

```bash
curl -X DELETE https://api.firecrawl.dev/v2/crawl/crawl-123-456-789 \
  -H "Authorization: Bearer fc-YOUR_API_KEY"
```

**Response:**
```json
{
  "success": true,
  "message": "Crawl job cancelled"
}
```

---

## 3. Batch Scrape Flow

### Request Flow

```
Client → POST /v2/batch/scrape
  ↓
[Validation] → Validates URLs array
  ↓
[Job Creation] → Creates batch job
  ↓
[Queue Individual Scrapes] → Adds each URL to queue
  ↓
[Response] → Returns batch jobId
  ↓
[Parallel Processing] → Workers process URLs concurrently
  ↓
[Status Updates] → Updates progress per URL
```

#### Example Request

```bash
curl -X POST https://api.firecrawl.dev/v2/batch/scrape \
  -H "Authorization: Bearer fc-YOUR_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "urls": [
      "https://firecrawl.dev",
      "https://docs.firecrawl.dev",
      "https://firecrawl.dev/pricing"
    ],
    "formats": ["markdown"]
  }'
```

#### Initial Response

```json
{
  "success": true,
  "id": "batch-abc-123",
  "url": "https://api.firecrawl.dev/v2/batch/scrape/batch-abc-123"
}
```

#### Status Check

```bash
curl -X GET https://api.firecrawl.dev/v2/batch/scrape/batch-abc-123 \
  -H "Authorization: Bearer fc-YOUR_API_KEY"
```

#### Status Response (In Progress)

```json
{
  "success": true,
  "status": "scraping",
  "total": 3,
  "completed": 1,
  "failed": 0,
  "data": [
    {
      "url": "https://firecrawl.dev",
      "markdown": "# Firecrawl\n\n...",
      "metadata": {
        "title": "Firecrawl",
        "statusCode": 200
      }
    }
  ]
}
```

#### Status Response (Completed)

```json
{
  "success": true,
  "status": "completed",
  "total": 3,
  "completed": 3,
  "failed": 0,
  "data": [
    {
      "url": "https://firecrawl.dev",
      "markdown": "# Firecrawl\n\n...",
      "metadata": { "title": "Firecrawl", "statusCode": 200 }
    },
    {
      "url": "https://docs.firecrawl.dev",
      "markdown": "# Documentation\n\n...",
      "metadata": { "title": "Documentation", "statusCode": 200 }
    },
    {
      "url": "https://firecrawl.dev/pricing",
      "markdown": "# Pricing\n\n...",
      "metadata": { "title": "Pricing", "statusCode": 200 }
    }
  ]
}
```

#### Get Errors

```bash
curl -X GET https://api.firecrawl.dev/v2/batch/scrape/batch-abc-123/errors \
  -H "Authorization: Bearer fc-YOUR_API_KEY"
```

**Response:**
```json
{
  "success": true,
  "errors": [
    {
      "url": "https://example.com/404",
      "error": "Page not found",
      "statusCode": 404
    }
  ]
}
```

---

## 4. Extract Flow (AI-Powered)

### Request Flow

```
Client → POST /v2/extract
  ↓
[Validation] → Validates URLs and schema/prompt
  ↓
[Credit Check] → Verifies 20 credits minimum
  ↓
[Job Creation] → Creates extract job
  ↓
[URL Processing] → Expands wildcards, validates URLs
  ↓
[Response] → Returns jobId
  ↓
[LLM Processing] → Extracts structured data using AI
  ↓
[Schema Validation] → Validates extracted data against schema
  ↓
[Result Storage] → Stores results
```

#### Example Request (with Schema)

```bash
curl -X POST https://api.firecrawl.dev/v2/extract \
  -H "Authorization: Bearer fc-YOUR_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "urls": ["https://firecrawl.dev"],
    "schema": {
      "type": "object",
      "properties": {
        "companyName": {
          "type": "string"
        },
        "companyDescription": {
          "type": "string"
        },
        "isOpenSource": {
          "type": "boolean"
        }
      },
      "required": ["companyName", "companyDescription"]
    }
  }'
```

#### Example Request (with Prompt Only)

```bash
curl -X POST https://api.firecrawl.dev/v2/extract \
  -H "Authorization: Bearer fc-YOUR_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "urls": ["https://firecrawl.dev/*"],
    "prompt": "Extract company name, description, and whether it is open source"
  }'
```

#### Initial Response

```json
{
  "success": true,
  "id": "extract-xyz-789",
  "urlTrace": []
}
```

#### Status Check

```bash
curl -X GET https://api.firecrawl.dev/v2/extract/extract-xyz-789 \
  -H "Authorization: Bearer fc-YOUR_API_KEY"
```

#### Status Response (Processing)

```json
{
  "success": true,
  "status": "processing",
  "id": "extract-xyz-789"
}
```

#### Status Response (Completed)

```json
{
  "success": true,
  "status": "completed",
  "id": "extract-xyz-789",
  "data": {
    "companyName": "Firecrawl",
    "companyDescription": "Firecrawl crawls and converts any website into clean markdown or structured data.",
    "isOpenSource": true
  }
}
```

---

## 5. Search Flow

### Request Flow

```
Client → POST /v2/search
  ↓
[Validation] → Validates query
  ↓
[SERP Query] → Performs web search
  ↓
[Result Processing] → Processes search results
  ↓
[Optional Scraping] → Scrapes result pages if requested
  ↓
[Response] → Returns search results + scraped content
```

#### Example Request (Search Only)

```bash
curl -X POST https://api.firecrawl.dev/v2/search \
  -H "Authorization: Bearer fc-YOUR_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "query": "what is firecrawl?",
    "limit": 5
  }'
```

#### Response

```json
{
  "success": true,
  "data": [
    {
      "url": "https://firecrawl.dev",
      "title": "Firecrawl | Home Page",
      "description": "Turn websites into LLM-ready data with Firecrawl"
    },
    {
      "url": "https://docs.firecrawl.dev",
      "title": "Documentation | Firecrawl",
      "description": "Learn how to use Firecrawl in your applications"
    }
  ]
}
```

#### Example Request (Search + Scrape)

```bash
curl -X POST https://api.firecrawl.dev/v2/search \
  -H "Authorization: Bearer fc-YOUR_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "query": "what is firecrawl?",
    "limit": 3,
    "scrapeOptions": {
      "formats": ["markdown"]
    }
  }'
```

#### Response (with Content)

```json
{
  "success": true,
  "data": [
    {
      "url": "https://firecrawl.dev",
      "title": "Firecrawl | Home Page",
      "description": "Turn websites into LLM-ready data",
      "markdown": "# Firecrawl\n\nTurn any website into LLM-ready data..."
    },
    {
      "url": "https://docs.firecrawl.dev",
      "title": "Documentation | Firecrawl",
      "description": "Learn how to use Firecrawl",
      "markdown": "# Documentation\n\n..."
    }
  ],
  "creditsUsed": 3
}
```

---

## 6. Map Flow

### Request Flow

```
Client → POST /v2/map
  ↓
[Validation] → Validates URL
  ↓
[Fast Discovery] → Quickly discovers URLs (sitemap, links)
  ↓
[Optional Search] → Filters by search term if provided
  ↓
[Response] → Returns discovered URLs
```

#### Example Request

```bash
curl -X POST https://api.firecrawl.dev/v2/map \
  -H "Authorization: Bearer fc-YOUR_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "url": "https://firecrawl.dev"
  }'
```

#### Response

```json
{
  "success": true,
  "links": [
    {
      "url": "https://firecrawl.dev",
      "title": "Firecrawl",
      "description": "Turn any website into LLM-ready data"
    },
    {
      "url": "https://firecrawl.dev/pricing",
      "title": "Pricing",
      "description": "Firecrawl pricing plans"
    },
    {
      "url": "https://firecrawl.dev/docs",
      "title": "Documentation",
      "description": "API documentation and guides"
    }
  ]
}
```

#### Example Request (with Search)

```bash
curl -X POST https://api.firecrawl.dev/v2/map \
  -H "Authorization: Bearer fc-YOUR_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "url": "https://firecrawl.dev",
    "search": "pricing"
  }'
```

#### Response (Filtered)

```json
{
  "success": true,
  "links": [
    {
      "url": "https://firecrawl.dev/pricing",
      "title": "Pricing",
      "description": "Firecrawl pricing plans"
    }
  ]
}
```

---

## 7. Error Handling Flow

### Error Response Structure

```json
{
  "success": false,
  "code": "ERROR_CODE",
  "error": "Human-readable error message",
  "details": {
    // Additional error context
  }
}
```

### Common Error Codes

#### Authentication Errors

```json
{
  "success": false,
  "code": "UNAUTHORIZED",
  "error": "Invalid API key"
}
```

#### Credit Errors

```json
{
  "success": false,
  "code": "INSUFFICIENT_CREDITS",
  "error": "Insufficient credits. Required: 20, Available: 5"
}
```

#### Rate Limit Errors

```json
{
  "success": false,
  "code": "RATE_LIMIT_EXCEEDED",
  "error": "Rate limit exceeded. Please try again later.",
  "retryAfter": 60
}
```

#### Validation Errors

```json
{
  "success": false,
  "code": "BAD_REQUEST",
  "error": "Invalid URL format",
  "details": [
    {
      "path": ["url"],
      "message": "Invalid URL"
    }
  ]
}
```

#### Job Errors

```json
{
  "success": false,
  "code": "JOB_FAILED",
  "error": "Failed to scrape URL: Connection timeout",
  "jobId": "abc-123"
}
```

---

## 8. Complete Workflow Examples

### Example 1: Scrape → Extract → Process

```bash
# Step 1: Scrape a page
SCRAPE_RESPONSE=$(curl -X POST https://api.firecrawl.dev/v2/scrape \
  -H "Authorization: Bearer fc-YOUR_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "url": "https://example.com/product",
    "formats": ["markdown"]
  }')

# Step 2: Extract structured data
EXTRACT_RESPONSE=$(curl -X POST https://api.firecrawl.dev/v2/extract \
  -H "Authorization: Bearer fc-YOUR_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "urls": ["https://example.com/product"],
    "schema": {
      "type": "object",
      "properties": {
        "productName": {"type": "string"},
        "price": {"type": "number"},
        "description": {"type": "string"}
      }
    }
  }')

# Step 3: Get extract job ID
EXTRACT_ID=$(echo $EXTRACT_RESPONSE | jq -r '.id')

# Step 4: Poll for completion
while true; do
  STATUS=$(curl -X GET https://api.firecrawl.dev/v2/extract/$EXTRACT_ID \
    -H "Authorization: Bearer fc-YOUR_API_KEY" | jq -r '.status')
  
  if [ "$STATUS" = "completed" ]; then
    echo "Extraction completed!"
    break
  fi
  
  sleep 2
done
```

### Example 2: Crawl → Monitor → Process Results

```bash
# Step 1: Start crawl
CRAWL_RESPONSE=$(curl -X POST https://api.firecrawl.dev/v2/crawl \
  -H "Authorization: Bearer fc-YOUR_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "url": "https://docs.firecrawl.dev",
    "limit": 50,
    "scrapeOptions": {
      "formats": ["markdown"]
    }
  }')

CRAWL_ID=$(echo $CRAWL_RESPONSE | jq -r '.id')

# Step 2: Monitor with WebSocket (JavaScript example)
# Or poll with curl:
while true; do
  STATUS_RESPONSE=$(curl -X GET https://api.firecrawl.dev/v2/crawl/$CRAWL_ID \
    -H "Authorization: Bearer fc-YOUR_API_KEY")
  
  STATUS=$(echo $STATUS_RESPONSE | jq -r '.status')
  COMPLETED=$(echo $STATUS_RESPONSE | jq -r '.completed // 0')
  TOTAL=$(echo $STATUS_RESPONSE | jq -r '.total // 0')
  
  echo "Progress: $COMPLETED/$TOTAL - Status: $STATUS"
  
  if [ "$STATUS" = "completed" ] || [ "$STATUS" = "failed" ]; then
    break
  fi
  
  sleep 5
done

# Step 3: Process results
curl -X GET https://api.firecrawl.dev/v2/crawl/$CRAWL_ID \
  -H "Authorization: Bearer fc-YOUR_API_KEY" | jq '.data[] | .markdown'
```

### Example 3: Batch Scrape → Error Handling

```bash
# Step 1: Start batch scrape
BATCH_RESPONSE=$(curl -X POST https://api.firecrawl.dev/v2/batch/scrape \
  -H "Authorization: Bearer fc-YOUR_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "urls": [
      "https://example.com/page1",
      "https://example.com/page2",
      "https://example.com/404"
    ],
    "formats": ["markdown"]
  }')

BATCH_ID=$(echo $BATCH_RESPONSE | jq -r '.id')

# Step 2: Wait for completion
while true; do
  STATUS=$(curl -X GET https://api.firecrawl.dev/v2/batch/scrape/$BATCH_ID \
    -H "Authorization: Bearer fc-YOUR_API_KEY" | jq -r '.status')
  
  [ "$STATUS" = "completed" ] && break
  sleep 2
done

# Step 3: Check for errors
ERRORS=$(curl -X GET https://api.firecrawl.dev/v2/batch/scrape/$BATCH_ID/errors \
  -H "Authorization: Bearer fc-YOUR_API_KEY")

echo "Errors found:"
echo $ERRORS | jq '.errors[]'
```

---

## 9. Status State Machine

### Crawl Status States

```
┌─────────┐
│ pending │  (Initial state)
└────┬────┘
     │
     ▼
┌─────────┐
│ queued │  (Added to queue)
└────┬────┘
     │
     ▼
┌──────────┐
│ scraping │  (Actively processing)
└────┬─────┘
     │
     ├─────────────┬──────────────┐
     ▼             ▼              ▼
┌──────────┐  ┌────────┐  ┌──────────┐
│completed │  │ failed │  │cancelled │
└──────────┘  └────────┘  └──────────┘
```

### Extract Status States

```
┌──────────┐
│pending   │
└────┬─────┘
     │
     ▼
┌──────────┐
│processing│
└────┬─────┘
     │
     ├──────────┐
     ▼          ▼
┌──────────┐ ┌────────┐
│completed │ │ failed │
└──────────┘ └────────┘
```

### Batch Scrape Status States

```
┌─────────┐
│pending  │
└────┬────┘
     │
     ▼
┌──────────┐
│ scraping │
└────┬─────┘
     │
     ├──────────┐
     ▼          ▼
┌──────────┐ ┌────────┐
│completed │ │ failed │
└──────────┘ └────────┘
```

---

## 10. Best Practices

### 1. Polling Intervals

- **Crawl jobs**: Poll every 2-5 seconds
- **Extract jobs**: Poll every 3-5 seconds
- **Batch scrape**: Poll every 2-3 seconds
- Use exponential backoff for rate-limited requests

### 2. Timeout Handling

```javascript
// Example: Timeout after 5 minutes
const startTime = Date.now();
const timeout = 5 * 60 * 1000; // 5 minutes

while (status !== 'completed') {
  if (Date.now() - startTime > timeout) {
    throw new Error('Job timeout');
  }
  
  await sleep(2000);
  status = await checkStatus(jobId);
}
```

### 3. Error Recovery

```javascript
// Retry with exponential backoff
async function retryWithBackoff(fn, maxRetries = 3) {
  for (let i = 0; i < maxRetries; i++) {
    try {
      return await fn();
    } catch (error) {
      if (i === maxRetries - 1) throw error;
      await sleep(Math.pow(2, i) * 1000);
    }
  }
}
```

### 4. WebSocket Reconnection

```javascript
function connectWebSocket(jobId, apiKey) {
  const ws = new WebSocket(
    `wss://api.firecrawl.dev/v2/crawl/${jobId}?apiKey=${apiKey}`
  );
  
  ws.onclose = () => {
    // Reconnect after 1 second
    setTimeout(() => connectWebSocket(jobId, apiKey), 1000);
  };
  
  return ws;
}
```

### 5. Pagination Handling

```javascript
// Handle paginated crawl results
async function getAllCrawlResults(jobId) {
  let allData = [];
  let nextUrl = `/v2/crawl/${jobId}`;
  
  while (nextUrl) {
    const response = await fetch(nextUrl, {
      headers: { 'Authorization': `Bearer ${apiKey}` }
    });
    const data = await response.json();
    
    allData = allData.concat(data.data);
    nextUrl = data.next || null;
  }
  
  return allData;
}
```

---

## 11. SDK Usage Examples

### Python SDK

```python
from firecrawl import FirecrawlApp

app = FirecrawlApp(api_key="fc-YOUR_API_KEY")

# Scrape
doc = app.scrape("https://firecrawl.dev", {
    "formats": ["markdown", "html"]
})
print(doc.markdown)

# Crawl (with auto-polling)
crawl_result = app.crawl(
    "https://docs.firecrawl.dev",
    limit=10,
    scrape_options={"formats": ["markdown"]},
    poll_interval=2
)
print(f"Crawled {len(crawl_result.data)} pages")

# Extract
extract_result = app.extract(
    urls=["https://firecrawl.dev"],
    schema={
        "type": "object",
        "properties": {
            "companyName": {"type": "string"}
        }
    }
)
print(extract_result.data)
```

### JavaScript SDK

```javascript
import FirecrawlApp from '@mendable/firecrawl-js';

const app = new FirecrawlApp({ apiKey: 'fc-YOUR_API_KEY' });

// Scrape
const doc = await app.scrape('https://firecrawl.dev', {
  formats: ['markdown', 'html']
});
console.log(doc.markdown);

// Crawl (with auto-polling)
const crawlResult = await app.crawl('https://docs.firecrawl.dev', {
  limit: 10,
  scrapeOptions: { formats: ['markdown'] }
});
console.log(`Crawled ${crawlResult.data.length} pages`);

// Extract
const extractResult = await app.extract({
  urls: ['https://firecrawl.dev'],
  schema: {
    type: 'object',
    properties: {
      companyName: { type: 'string' }
    }
  }
});
console.log(extractResult.data);
```

---

This comprehensive flow documentation covers all major operations, status transitions, error handling, and practical examples for using the Firecrawl API effectively.

---

# New Features & Advanced Capabilities

## Overview of New Features

Firecrawl has introduced several powerful new features that enhance performance, intelligence, and capabilities:

| Feature | Description | Performance Impact |
|---------|-------------|-------------------|
| 🤖 **Agent** | AI-powered autonomous web scraping with natural language prompts | High Intelligence |
| 🛠️ **Go Service** | 10x faster HTML-to-Markdown conversion microservice | 10x Speed Boost |
| 🎨 **Branding** | Advanced logo detection and brand color extraction | Enhanced Data |
| ⚙️ **Engine Forcing** | Smart domain-specific scraping engine selection | Optimized Routes |
| 🚀 **Performance** | Enhanced resource management and queue systems | 3x Efficiency |
| 🔗 **Webhooks** | Reliable delivery system with retry mechanisms | 99.9% Reliability |

---

## 1. 🤖 Agent Feature (AI-Powered Extraction)

### Overview

The Agent feature enables AI-driven autonomous web scraping using natural language instructions. It understands context, extracts structured data, and adapts to different website structures automatically.

### Endpoint

**POST `/v2/agent`**

### Request Flow

```
Client → POST /v2/agent
  ↓
[Validation] → Validates prompt, schema, and URLs
  ↓
[Credit Check] → Verifies 20 credits minimum
  ↓
[Job Creation] → Creates agent job with UUID
  ↓
[AI Processing] → LLM analyzes pages and extracts data
  ↓
[Schema Validation] → Validates extracted data against schema
  ↓
[Response] → Returns jobId for async processing
```

### Example Request (Basic)

```bash
curl -X POST https://api.firecrawl.dev/v2/agent \
  -H "Authorization: Bearer fc-YOUR_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "urls": ["https://news.ycombinator.com"],
    "prompt": "Extract the top 5 article titles, their URLs, and scores",
    "schema": {
      "type": "object",
      "properties": {
        "articles": {
          "type": "array",
          "maxItems": 5,
          "items": {
            "type": "object",
            "properties": {
              "title": { "type": "string" },
              "url": { "type": "string", "format": "uri" },
              "score": { "type": "number" }
            },
            "required": ["title", "url"]
          }
        }
      },
      "required": ["articles"]
    },
    "model": "spark-1-pro"
  }'
```

### Example Request (E-commerce)

```bash
curl -X POST https://api.firecrawl.dev/v2/agent \
  -H "Authorization: Bearer fc-YOUR_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "urls": ["https://shop.example.com"],
    "prompt": "Extract all products with names, prices, availability, and images",
    "schema": {
      "type": "object",
      "properties": {
        "products": {
          "type": "array",
          "items": {
            "type": "object",
            "properties": {
              "name": { "type": "string" },
              "price": { "type": "string" },
              "currency": { "type": "string", "enum": ["USD", "EUR", "GBP"] },
              "available": { "type": "boolean" },
              "image_url": { "type": "string", "format": "uri" }
            },
            "required": ["name", "price", "available"]
          }
        }
      }
    },
    "model": "spark-1-pro",
    "maxCredits": 200
  }'
```

### Initial Response

```json
{
  "success": true,
  "id": "agent-xyz-789",
  "urlTrace": []
}
```

### Status Check

```bash
curl -X GET https://api.firecrawl.dev/v2/agent/agent-xyz-789 \
  -H "Authorization: Bearer fc-YOUR_API_KEY"
```

### Status Response (Processing)

```json
{
  "success": true,
  "status": "processing",
  "id": "agent-xyz-789"
}
```

### Status Response (Completed)

```json
{
  "success": true,
  "status": "completed",
  "id": "agent-xyz-789",
  "data": {
    "articles": [
      {
        "title": "Firecrawl launches AI agent feature",
        "url": "https://news.ycombinator.com/item?id=123",
        "score": 256
      },
      {
        "title": "New Rust-based HTML parser",
        "url": "https://news.ycombinator.com/item?id=124",
        "score": 189
      }
    ]
  }
}
```

### Cancel Agent Job

```bash
curl -X DELETE https://api.firecrawl.dev/v2/agent/agent-xyz-789 \
  -H "Authorization: Bearer fc-YOUR_API_KEY"
```

### Supported Models

- **`spark-1-pro`** (default): High accuracy, best for complex extractions
- **`spark-1-mini`**: Faster, cost-effective for simple extractions

### Agent vs Extract

| Feature | Agent | Extract |
|---------|-------|---------|
| **Intelligence** | High - understands context | Medium - follows schema |
| **Adaptability** | Adapts to site structure | Fixed extraction pattern |
| **Use Case** | Complex, variable structures | Known, consistent structures |
| **Cost** | Higher (20+ credits) | Lower (20 credits) |

---

## 2. 🎨 Branding Feature (Logo & Color Extraction)

### Overview

The Branding feature automatically detects logos and extracts brand colors from websites using advanced computer vision principles and multi-factor scoring algorithms.

### Usage

Branding data is automatically included when scraping with the `branding` format or when `onlyMainContent: false`.

### Example Request

```bash
curl -X POST https://api.firecrawl.dev/v2/scrape \
  -H "Authorization: Bearer fc-YOUR_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "url": "https://stripe.com",
    "formats": ["markdown", "branding"],
    "onlyMainContent": false
  }'
```

### Response with Branding

```json
{
  "success": true,
  "data": {
    "markdown": "# Stripe\n\n...",
    "branding": {
      "logos": [
        {
          "src": "https://stripe.com/img/logo.svg",
          "alt": "Stripe",
          "confidence": 0.95,
          "location": "header",
          "position": {
            "top": 20,
            "left": 40,
            "width": 120,
            "height": 40
          }
        }
      ],
      "colors": {
        "primary": "#635BFF",
        "secondary": "#00D4FF",
        "palette": ["#635BFF", "#00D4FF", "#FFFFFF", "#000000"]
      }
    },
    "metadata": {
      "title": "Stripe | Payment Processing Platform",
      "sourceURL": "https://stripe.com"
    }
  }
}
```

### Logo Detection Algorithm

The logo detection uses a scoring system based on:

- **Position** (35 points): Header placement, top-left position
- **Content Analysis** (40 points): Alt text, URL patterns, CSS classes
- **Technical Factors** (25 points): SVG format, size, visibility

Logos with confidence scores above 0.7 are considered high-quality matches.

### Color Extraction

Colors are extracted from:
- Text colors (`color` CSS property)
- Background colors (`background-color`)
- Border colors (`border-color`)
- Computed styles (handles transparency and blending)

---

## 3. ⚙️ Engine Forcing (Intelligent Scraping Strategy)

### Overview

Engine Forcing allows you to configure domain-specific scraping engines for optimal performance and success rates. This reduces failed requests and improves speed by using the right tool for each website.

### Configuration

Set via environment variable `FORCED_ENGINE_DOMAINS`:

```json
{
  "linkedin.com": "playwright",
  "twitter.com": "playwright",
  "*.cloudflare.com": "fire-engine;tlsclient;stealth",
  "google.com": ["fire-engine;chrome-cdp", "playwright"],
  "wikipedia.org": "fetch",
  "github.com": "fetch"
}
```

### Engine Types

- **`fetch`**: Simple HTTP requests (fastest, for static sites)
- **`playwright`**: Full browser automation (for JavaScript-heavy sites)
- **`fire-engine`**: Custom browser engine with advanced features
- **`fire-engine;chrome-cdp`**: Chrome DevTools Protocol
- **`fire-engine;tlsclient;stealth`**: Stealth mode with TLS client

### Example Usage

```bash
# Engine forcing is automatic based on domain
curl -X POST https://api.firecrawl.dev/v2/scrape \
  -H "Authorization: Bearer fc-YOUR_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "url": "https://linkedin.com/company/openai",
    "formats": ["markdown"]
  }'
# Automatically uses playwright engine for LinkedIn
```

### Performance Impact

- **Traditional**: Try engines sequentially (~30s for complex sites)
- **Engine Forcing**: Use optimal engine directly (~3s)
- **Performance Gain**: 10x faster with higher success rates

---

## 4. 🛠️ Go HTML-to-Markdown Service

### Overview

A high-performance Go microservice that converts HTML to Markdown 10x faster than JavaScript-based solutions, with minimal memory usage.

### Architecture

```
API Request → Go Service (Port 8080) → Markdown Output
     ↓
Fallback to Local Conversion (if service unavailable)
```

### Performance

- **Speed**: 10x faster than JavaScript (20ms vs 200ms per 1MB HTML)
- **Memory**: 10x more efficient (5MB vs 50MB peak)
- **Throughput**: ~50 conversions/second

### Service Endpoint

**POST `http://localhost:8080/convert`** (internal)

### Example Direct Service Call

```bash
curl -X POST http://localhost:8080/convert \
  -H "Content-Type: application/json" \
  -d '{
    "html": "<h1>Test</h1><p>Content</p>"
  }'
```

### Response

```json
{
  "success": true,
  "markdown": "# Test\n\nContent"
}
```

### Automatic Integration

The Go service is automatically used for all scrape operations. No configuration needed - it's transparent to API users.

---

## 5. 🔗 Webhooks

### Overview

Webhooks provide reliable, asynchronous notifications when jobs complete. The system includes automatic retry mechanisms for 99.9% delivery success.

### Webhook Configuration

Add `webhook` to any crawl, extract, or agent request:

```json
{
  "webhook": {
    "url": "https://your-server.com/webhook",
    "secret": "optional-secret-key",
    "events": ["completed", "failed"]
  }
}
```

### Example Request with Webhook

```bash
curl -X POST https://api.firecrawl.dev/v2/crawl \
  -H "Authorization: Bearer fc-YOUR_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "url": "https://docs.firecrawl.dev",
    "limit": 10,
    "webhook": {
      "url": "https://your-server.com/firecrawl-webhook",
      "secret": "your-webhook-secret"
    }
  }'
```

### Webhook Payload

```json
{
  "event": "completed",
  "jobId": "crawl-123-456",
  "status": "completed",
  "timestamp": "2024-01-22T10:30:00Z",
  "data": {
    "total": 10,
    "completed": 10,
    "failed": 0
  }
}
```

### Webhook Events

- **`completed`**: Job finished successfully
- **`failed`**: Job encountered an error
- **`progress`**: Periodic progress updates (for long jobs)

### Retry Mechanism

- **Initial**: Immediate delivery
- **Retry 1**: After 1 minute
- **Retry 2**: After 5 minutes
- **Retry 3**: After 15 minutes
- **Max Retries**: 3 attempts

### Webhook Security

Use the `secret` field to verify webhook authenticity:

```javascript
const crypto = require('crypto');

function verifyWebhook(payload, signature, secret) {
  const expectedSignature = crypto
    .createHmac('sha256', secret)
    .update(JSON.stringify(payload))
    .digest('hex');
  
  return crypto.timingSafeEqual(
    Buffer.from(signature),
    Buffer.from(expectedSignature)
  );
}
```

---

## 6. 🦀 Rust Integration

### Overview

Firecrawl uses Rust modules for performance-critical operations, providing 50-100x speed improvements for HTML parsing, PDF processing, and document conversion.

### Rust Components

1. **HTML Processing** (`apps/api/native/src/html.rs`)
   - Base href extraction
   - Link resolution
   - Image extraction
   - 50x faster than JavaScript

2. **PDF Processing** (`apps/api/native/src/document/mod.rs`)
   - Metadata extraction
   - Text extraction
   - 100x faster than PDF.js

3. **Engine Picker** (`apps/api/native/src/engpicker.rs`)
   - Intelligent engine selection
   - Content similarity analysis
   - Performance optimization

### Performance Benchmarks

```
HTML Base Href Extraction:
- JavaScript (Cheerio):  ~50ms per document
- Rust (kuchikiki):      ~1ms per document
- Performance Gain:     50x faster

PDF Metadata Extraction:
- JavaScript (PDF.js):  ~500ms per file
- Rust (lopdf):        ~5ms per file
- Performance Gain:    100x faster
```

### Automatic Usage

Rust modules are automatically used - no configuration needed. They're transparent to API users and provide significant performance improvements behind the scenes.

---

## 7. 🚀 Performance Enhancements

### Team Semaphore System

Limits concurrent jobs per team to prevent resource exhaustion:

```typescript
// Automatic concurrency control
MAX_CONCURRENT_JOBS=5  // Per team
```

### Extract Queue System

Prioritized queue system for extract jobs:

- **High Priority**: Small jobs (≤5 URLs)
- **Medium Priority**: Medium jobs (6-20 URLs)
- **Low Priority**: Large jobs (>20 URLs)

### Resource Management

- **Browser Pool**: Reusable browser instances
- **Connection Pooling**: Efficient HTTP connections
- **Memory Management**: Automatic cleanup and garbage collection

### Performance Tips

1. **Use Engine Forcing**: Configure optimal engines for your domains
2. **Batch Operations**: Use batch scrape for multiple URLs
3. **Async Processing**: Use job IDs for long-running operations
4. **Webhooks**: Avoid polling for better performance

---

## 8. Complete Feature Examples

### Example 1: Agent + Branding + Webhook

```bash
curl -X POST https://api.firecrawl.dev/v2/agent \
  -H "Authorization: Bearer fc-YOUR_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "urls": ["https://company.com"],
    "prompt": "Extract company information including name, description, and logo",
    "schema": {
      "type": "object",
      "properties": {
        "companyName": { "type": "string" },
        "description": { "type": "string" },
        "logoUrl": { "type": "string", "format": "uri" },
        "brandColors": {
          "type": "array",
          "items": { "type": "string" }
        }
      }
    },
    "webhook": {
      "url": "https://your-server.com/webhook"
    }
  }'
```

### Example 2: Scrape with All Features

```bash
curl -X POST https://api.firecrawl.dev/v2/scrape \
  -H "Authorization: Bearer fc-YOUR_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "url": "https://example.com",
    "formats": ["markdown", "html", "links", "screenshot", "branding"],
    "actions": [
      {"type": "wait", "milliseconds": 2000},
      {"type": "scroll", "direction": "down"}
    ],
    "webhook": {
      "url": "https://your-server.com/webhook"
    }
  }'
```

### Example 3: Python SDK with New Features

```python
from firecrawl import FirecrawlApp

app = FirecrawlApp(api_key="fc-YOUR_API_KEY")

# Agent extraction
result = app.agent(
    urls=["https://shop.example.com"],
    prompt="Extract all products with prices",
    schema={
        "type": "object",
        "properties": {
            "products": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "name": {"type": "string"},
                        "price": {"type": "string"}
                    }
                }
            }
        }
    },
    model="spark-1-pro"
)

# Scrape with branding
doc = app.scrape("https://company.com", {
    "formats": ["markdown", "branding"],
    "onlyMainContent": False
})

if doc.branding:
    print(f"Logo: {doc.branding.logos[0].src}")
    print(f"Primary Color: {doc.branding.colors.primary}")
```

### Example 4: JavaScript SDK with New Features

```javascript
import FirecrawlApp from '@mendable/firecrawl-js';

const app = new FirecrawlApp({ apiKey: 'fc-YOUR_API_KEY' });

// Agent extraction
const agentResult = await app.agent({
  urls: ['https://news.example.com'],
  prompt: 'Extract article headlines and authors',
  schema: {
    type: 'object',
    properties: {
      articles: {
        type: 'array',
        items: {
          type: 'object',
          properties: {
            headline: { type: 'string' },
            author: { type: 'string' }
          }
        }
      }
    }
  },
  model: 'spark-1-pro',
  webhook: {
    url: 'https://your-server.com/webhook'
  }
});

// Scrape with branding
const doc = await app.scrape('https://company.com', {
  formats: ['markdown', 'branding'],
  onlyMainContent: false
});

console.log('Logo:', doc.branding?.logos[0]?.src);
console.log('Colors:', doc.branding?.colors?.palette);
```

---

## 9. Feature Comparison Matrix

| Feature | Endpoint | Credits | Async | WebSocket | Webhook |
|---------|----------|---------|-------|-----------|---------|
| **Scrape** | `/v2/scrape` | 1 | Optional | No | Yes |
| **Crawl** | `/v2/crawl` | Variable | Yes | Yes | Yes |
| **Extract** | `/v2/extract` | 20 | Yes | No | Yes |
| **Agent** | `/v2/agent` | 20 | Yes | No | Yes |
| **Search** | `/v2/search` | Variable | Optional | No | No |
| **Map** | `/v2/map` | 1 | No | No | No |
| **Batch Scrape** | `/v2/batch/scrape` | Variable | Yes | No | Yes |

---

## 10. Migration Guide

### From Extract to Agent

**Before (Extract):**
```javascript
await app.extract({
  urls: ['https://example.com'],
  schema: { /* fixed schema */ }
});
```

**After (Agent):**
```javascript
await app.agent({
  urls: ['https://example.com'],
  prompt: 'Extract data based on this description...',
  schema: { /* same schema, but more flexible */ }
});
```

### Benefits of Agent

- Better understanding of context
- Adapts to site structure changes
- Handles edge cases automatically
- More natural language interface

---

## 11. Best Practices for New Features

### Agent Best Practices

1. **Clear Prompts**: Be specific about what to extract
2. **Schema Validation**: Always define required fields
3. **Model Selection**: Use `spark-1-pro` for complex extractions
4. **Credit Management**: Monitor `maxCredits` for large jobs

### Branding Best Practices

1. **Set `onlyMainContent: false`**: Required for branding extraction
2. **Check Confidence Scores**: Use logos with confidence > 0.7
3. **Handle Multiple Logos**: Select the highest confidence logo
4. **Color Validation**: Verify extracted colors match brand guidelines

### Engine Forcing Best Practices

1. **Start Simple**: Use `fetch` for static sites
2. **Test Engines**: Try different engines for problematic domains
3. **Fallback Chains**: Configure multiple engines for reliability
4. **Monitor Performance**: Track success rates per engine

### Webhook Best Practices

1. **Idempotency**: Handle duplicate webhook deliveries
2. **Timeouts**: Set appropriate timeout for webhook endpoints
3. **Retries**: Implement retry logic on your side
4. **Security**: Always verify webhook signatures

---

## 12. Troubleshooting New Features

### Agent Issues

**Problem**: Agent returns empty data
- **Solution**: Check prompt clarity, verify URLs are accessible, try different model

**Problem**: Schema validation fails
- **Solution**: Review schema syntax, ensure required fields match prompt

### Branding Issues

**Problem**: No logos detected
- **Solution**: Set `onlyMainContent: false`, check if site has visible logos

**Problem**: Wrong logo selected
- **Solution**: Review confidence scores, check logo positions

### Engine Forcing Issues

**Problem**: Engine forcing not working
- **Solution**: Verify `FORCED_ENGINE_DOMAINS` format, check domain matching

**Problem**: Wrong engine selected
- **Solution**: Test engines manually, update configuration

### Webhook Issues

**Problem**: Webhooks not received
- **Solution**: Check endpoint accessibility, verify URL format, check retry logs

**Problem**: Duplicate webhooks
- **Solution**: Implement idempotency checks using jobId

---

This comprehensive documentation now includes all new features, their usage patterns, performance characteristics, and integration examples. All features work seamlessly together to provide a powerful, intelligent web scraping platform.
