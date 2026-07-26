# Turkish financial project map

Snapshot inspected 2026-07-25. Re-check the dirty worktree before relying on exact
status.

## Repository boundary

- Finance application: `projects/turkish_financial`.
- Self-hosted Firecrawl API: `apps/api`.
- Browser renderer: `apps/playwright-service-ts`.
- Local orchestration: root `docker-compose.yaml`.

The FastAPI service is independent from the Node Firecrawl API. It consumes Firecrawl
through `firecrawl-py` or raw local `/v2/scrape` calls.

## Canonical entry points

- FastAPI app: `api/main.py`
- FastAPI dependencies: `api/dependencies.py`
- Active database manager: `database/db_manager.py`
- Firecrawl compatibility adapter: `scrapers/base_scraper.py`
- KAP ingestion: `scrapers/kap_scraper.py`
- External contract routes: `api/routers/external_analysis.py`
- News/social/combined routes: `api/routers/news_sentiment.py`
- YouTube routes: `api/routers/youtube_sentiment.py`
- Fundamental runner: `run_financials.py`
- Recent-disclosure runner: `run_kap_4days.py`

Treat root/production scripts, `infrastructure/database/db_manager.py`,
`application/dependencies.py`, and older KAP flows as alternate or legacy until the
task explicitly selects them.

## Active pipelines

### KAP company disclosures

`KAPScraper.scrape_and_save_disclosures`
→ KAP disclosure query/fallback
→ normalize
→ `DatabaseManager.upsert_disclosure`
→ optional sentiment
→ external repository/routes.

### KAP fundamentals

instrument
→ resolve/cache `mkkMemberOid`
→ financial member-list GET
→ rendered disclosure page
→ `kap_financial_parser`
→ `FundamentalAnalyzer`
→ `FundamentalRepository`
→ statements/fundamentals tables
→ external routes.

Some point/batch routes can trigger network and database work on a cache miss. Treat
apparently read-only GET behavior as status-sensitive.

### News, social, and YouTube

- Portal RSS/HTML → `NewsArticle` → news collection use case → daily aggregate.
- X/FinTwit browser actions → `SocialPost` → social collection use case → aggregate.
- `yt-dlp` + transcript API → `YouTubeVideo` → YouTube use case → aggregate.
- Combined sentiment drops missing sources and renormalizes available weights.

Each collector currently reads persisted peer-source scores, replaces its own score,
and partially upserts the combined daily row. Serial collection is order-independent,
but concurrent collectors can race because read/compute/write is not atomic. YouTube
rollups are based on the current scrape batch rather than re-querying all stored daily
detail rows, so a partial rerun can shrink the aggregate while older videos remain.

## Runtime

The project is container-first. Root Compose defines `turkish-financial-api` on port
`8000`, connected to Firecrawl and PostgreSQL by Compose DNS. Its Dockerfile uses
Python 3.11 and `requirements.runtime.txt`. Bind-mounted development source can differ
from the image contents, so validate Compose, image build, mounted tests, and service
health before assuming deployment behavior.

`turkish-financial-api` is the persistent service used by external clients. Its stable
contract remains under `/api/external/v1`, health is `/api/external/v1/health`, and
OpenAPI is `/docs`. Host port is configurable with `TURKISH_FINANCIAL_PORT`; configure
browser origins with `FINANCIAL_CORS_ORIGINS` rather than changing route contracts.

The intended DDD split is incomplete: routes and scrapers still use the database
manager directly, schema changes happen during manager startup, and duplicate modules
remain. Improve incrementally and do not describe the boundary as stricter than it is.
