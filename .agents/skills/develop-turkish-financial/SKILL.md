---
name: develop-turkish-financial
description: Analyze, maintain, test, and improve the Turkish Financial Data Scraper and external analysis provider in this Firecrawl fork. Use for work under projects/turkish_financial involving KAP/BIST ingestion, Firecrawl or Playwright integration, Turkish news/X/YouTube sentiment, PostgreSQL persistence, FastAPI contracts, schedulers, proxies, anti-bot handling, containerization, or finance-service production hardening.
---

# Develop Turkish Financial

Change the finance provider without confusing it with the surrounding Firecrawl
monorepo or its older experimental paths.

## Start safely

1. Run `git status --short --branch` and preserve every existing change.
2. Treat `projects/turkish_financial` as the finance application. Treat `apps/api` and
   `apps/playwright-service-ts` as its self-hosted Firecrawl dependency.
3. Read [project-map.md](references/project-map.md) before changing architecture,
   persistence, entry points, or data flow.
4. Read [data-contract.md](references/data-contract.md) before changing routes, DTOs,
   scoring, database fields consumed by APIs, or instrument identity.
5. Read [sources-and-runtime.md](references/sources-and-runtime.md) before changing
   scraping, proxies, KAP access, schedulers, Docker, or Firecrawl compatibility.
6. Read [validation-and-risks.md](references/validation-and-risks.md) before testing,
   deployment, or security hardening.

## Follow the change workflow

1. Identify the pipeline:
   source adapter → domain entity → use case → repository/database → API envelope.
2. Put source parsing, business rules, aggregation, storage, and finance routes in this
   project. Put only generic browser/runtime capabilities in Firecrawl.
3. Keep I/O adapters thin and keep orchestration in use cases where the current
   architecture permits.
4. Preserve honest degradation. Return `unavailable`, `partial`, or an explicit error
   when a source yields no data; never invent financial values or neutral sentiment.
5. Preserve idempotency with stable source IDs and upserts.
6. Pace KAP requests and cache `mkkMemberOid`; never turn the slow GET fallback into a
   burst crawl.
7. Update the full stored/served shape when a contract changes, including migrations or
   compatibility behavior, repositories, DTOs, tests, and examples.
8. Add focused tests beside the changed layer and run incompatible legacy test modules
   separately.

## Protect core invariants

- Support `market=bist`; return honest `unavailable` envelopes for unsupported markets.
- Keep compatible responses on `contract_version: "1.0"`; negotiate a new version for
  removals, renames, or incompatible semantics.
- Keep sentiment scores in `[-1, 1]`, confidence in `[0, 1]`, and absent fundamentals
  null/omitted rather than fake zeroes.
- Keep this provider informational. Never emit investment instructions, price targets,
  or position sizing.
- Use `database/db_manager.py` as the active manager unless deliberately consolidating
  the duplicate under `infrastructure/database`.
- Keep scheduler behavior singleton-safe and bounded; in-memory scheduler state is not
  durable across processes.
- Treat public collection routes, `bypassProxy`, disabled TLS verification, arbitrary
  browser JavaScript, and logged payloads as security-sensitive.

## Verify proportionally

- Run domain/use-case/repository tests for business changes.
- Run API contract tests for every served-shape or provider-ID change.
- Run Firecrawl compatibility tests for scrape/map/search/batch/action changes.
- Use live KAP, portal, X, and YouTube checks only when authorized; label them as
  network-, anti-bot-, time-, and credential-sensitive.
- Report exact commands and classify environment, fixture, isolation, and product
  failures separately.
