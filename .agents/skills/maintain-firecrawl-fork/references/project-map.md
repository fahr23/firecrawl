# Firecrawl fork map

Snapshot inspected 2026-07-25. Re-check status-sensitive details before relying on them.

## Repository ownership

- `origin` currently points to the personal fork `fahr23/firecrawl`.
- `upstream` currently points to `mendableai/firecrawl`.
- `apps/api` contains the Node API, workers, scrape option schemas, engine selection,
  and API snips.
- `apps/playwright-service-ts` contains the browser renderer.
- `apps/*-sdk` contains public language SDKs.
- `docker-compose.yaml` runs the self-hosted Firecrawl stack and, in the current dirty
  worktree, a separate `turkish-financial-api` service.
- `projects/turkish_financial` and `projects/academic_search` are consumers, not part of
  the upstream Firecrawl product surface.

## Current runtime topology

- Firecrawl API: host port `3002` by default.
- Playwright renderer: host port `3001`, container port `3000`.
- Finance FastAPI service: host/container port `8000` when its current Compose service
  is retained.
- Academic FastAPI/UI service: host/container port `8010` by default.
- PostgreSQL, Redis, RabbitMQ, FoundationDB, and HTML-to-Markdown support the local
  Firecrawl/finance topology.

Both application projects are container-first. Inspect Compose rather than assuming
that publishing a port starts an application. Inside project containers, reach
Firecrawl through `http://api:3002`; never substitute host `localhost`.

## Fork-specific behavior currently present in the dirty worktree

The current diff adds or changes:

- `bypassProxy` in v1 and v2 scrape schemas;
- propagation as `bypass_proxy` to Playwright;
- per-request proxy bypass when creating a browser context;
- `executeJavascript` and marker `scrape` browser actions;
- longer proxy/action time allowances and configurable navigation timeout/wait mode;
- special treatment of a rendered SPA response whose initial navigation returned 404.

These capabilities are not safely assumed to exist in Firecrawl Cloud or future
upstream versions. Re-read the diff and add focused tests before depending on them.

## Boundary decision

Use this test:

1. Would a non-financial Firecrawl user benefit from the capability?
2. Can the behavior be expressed without KAP-, BIST-, or academic-specific names?
3. Can its security and failure semantics be tested at the generic API boundary?

If any answer is no, keep the change in the consuming project.

## Option-placement trap

Before adding a scrape option, inspect which schemas reuse the target object.
`baseScrapeOptions` can feed more than the single-scrape route, so placing an option
there may unintentionally expose it to crawl, batch, search, extract, or parse flows.

For Playwright-only behavior, also inspect feature flags, cache identity, index/fetch
eligibility, and engine routing. Do not accept an option and then silently execute it
through an engine that cannot honor it.
