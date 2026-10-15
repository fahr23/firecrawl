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

## Kubernetes workspace

The finance API runs in its own workspace, `deploy/turkish-financial/` (read its
README first). It no longer lives in the shared `k8s/` Firecrawl manifests.

- `base/`: finance API, one Postgres (`turkish_financial` DB + Firecrawl's NuQ DB), and
  its own Firecrawl stack (`firecrawl-api`, playwright, go-html-to-md, redis, rabbitmq)
  at **replicas: 0**. The `collector-window` CronJob (07:00 Europe/Istanbul) wakes the
  stack, posts to the finance collect endpoints, and scales it back to 0;
  `collector-window-sleeper` is the hourly safety net. Limits are deliberately tight.
- `overlays/local`: OrbStack context `orbstack`, namespace `turkish-financial`,
  `localhost:30080` and `turkish.localhost:32080`, arm64 images built by skaffold.
- `overlays/hetzner`: context `hetzner-production` (single amd64 node `f23`), namespace
  `turkish-financial`, private `ghcr.io/fahr23/*` images, ResourceQuota, PSA
  baseline, default-deny NetworkPolicies; only `app: strategy-management` pods in
  `backtofuture-prod` may call
  `turkish-financial-api.turkish-financial.svc.cluster.local:8000`. No Ingress.
- Ship to production with `build-push.sh <tag>` (amd64) then `deploy-hetzner.sh`.

Gotchas: base Firecrawl env vars `NUM_WORKERS_PER_QUEUE`, `MAX_CONCURRENT_JOBS`,
`CRAWL_CONCURRENT_REQUESTS` and `BROWSER_POOL_SIZE` are not read by the API; the real
browser bound is playwright `MAX_CONCURRENT_PAGES`. `production_kap_final.py` needs
`PLAYWRIGHT_SERVICE_URL` (defaults to localhost). Kustomize overlays cannot live inside
their base directory (why `k8s/overlays/*` fail to render).

## Docker Compose

Use the root `docker-compose.yaml` for local dev and tests. Inside
`turkish-financial-api`, Firecrawl is `http://api:3002` and PostgreSQL is addressed by
its Compose service name; `localhost` refers only to the finance container. Run tests
through `docker compose run --rm --no-deps turkish-financial-test ...` when dependencies
are not required, and include dependencies for integration/health checks.

External clients reach the persistent finance service on
`${TURKISH_FINANCIAL_PORT:-8000}`. Keep `/api/external/v1` backward compatible and set
`FINANCIAL_CORS_ORIGINS` to a comma-separated allowlist for browser clients in
non-local deployments.

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
