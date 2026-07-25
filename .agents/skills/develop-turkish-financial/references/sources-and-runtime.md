# Source adapters and runtime

## Firecrawl adapter

`scrapers/base_scraper.py` normalizes Python SDK versions and exposes scrape, crawl,
extract, map, batch, search, and action operations. Some SDK calls are synchronous even
inside async methods; move blocking work to a thread or queue when hardening load.

The current fork carries `bypassProxy`, JavaScript actions, extended renderer timing,
and SPA-status behavior in an uncommitted diff. Verify the exact Firecrawl schema and
never assume Firecrawl Cloud accepts custom fields.

## KAP fallback strategy

KAP is a rate- and session-sensitive SPA. Prefer:

1. same-origin browser fetch after loading KAP;
2. Firecrawl through ordered proxy tiers;
3. paced direct HTTP with 429 backoff;
4. configured third-party proxy fallback.

For fundamentals, prefer the GET-only path:

1. scrape the BIST company list;
2. resolve and persist `mkkMemberOid`;
3. call the financial member-list GET endpoint;
4. render `/tr/Bildirim/{disclosureIndex}`;
5. parse English XBRL labels.

Keep the old XLSX path only as a verified fallback. Do not aggressively parallelize OID
discovery.

## Other sources

- Portal RSS uses `feedparser`; dynamic pages may use Firecrawl.
- X uses browser actions with an optional alternative frontend.
- YouTube uses `yt-dlp` and `youtube-transcript-api`, not Firecrawl.
- Binary PDF/XLSX downloads use direct HTTP utilities.

Record which fallback succeeded without logging credentials or proxy URLs.

## Deployment

The current worktree adds a Python 3.11 Docker image and a Compose service for the
finance API. Verify:

- local Firecrawl URL and container network name;
- `APP_DB_*` variables rather than obsolete `DB_*`-only examples;
- health route `/api/external/v1/health`;
- schema initialization/migration behavior;
- required runtime dependencies;
- authentication, CORS, egress policy, request limits, and secret redaction.

Do not expose collection or scheduling endpoints directly to the internet without an
explicit security boundary.
