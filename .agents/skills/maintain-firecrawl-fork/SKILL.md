---
name: maintain-firecrawl-fork
description: Analyze, modify, test, and synchronize this Firecrawl fork without losing fork-specific behavior or mixing application logic into upstream runtime code. Use for changes under apps/api, apps/playwright-service-ts, apps/*-sdk, root Docker orchestration, scrape schemas/actions/proxy behavior, Firecrawl end-to-end snips, or merges and rebases from mendableai/firecrawl.
---

# Maintain Firecrawl Fork

Keep generic scraper-runtime work separate from the applications under `projects/`.

## Start safely

1. Run `git status --short --branch`, `git remote -v`, and a focused `git diff` before editing.
2. Treat root Docker Compose as the canonical integration runtime for Firecrawl and
   both project consumers. Validate service DNS, mounts, build contexts, and container
   environment variables when a change affects either project.
3. Preserve all existing changes. Never reset or overwrite a dirty worktree to simplify an
   upstream sync.
4. Read the root `AGENTS.md`.
5. Read [project-map.md](references/project-map.md) before changing schemas, the
   Playwright request contract, Docker topology, or upstream history.
6. Read [testing-and-sync.md](references/testing-and-sync.md) before implementing API
   behavior, running the harness, or synchronizing with upstream.

## Place changes at the correct boundary

- Put public API validation, job orchestration, and generic scrape behavior in `apps/api`.
- Put browser-context, navigation, and action execution behavior in
  `apps/playwright-service-ts`.
- Update an SDK only when its public contract must expose the behavior.
- Put KAP parsing, financial rules, literature-provider logic, persistence, and
  application APIs under their matching `projects/` package.
- Prefer an application option over a fork change unless the missing capability is
  genuinely reusable scraper infrastructure.

## Implement an API change

1. State the happy path and at least one failure path.
2. Add or update a focused API snip first when the behavior crosses the HTTP boundary.
3. Trace the option through every layer:
   request schema → normalized options → engine selection → Playwright request →
   renderer behavior → response mapping.
4. Use `scrapeTimeout` from the snip test library for scrape timeouts.
5. Gate tests exactly as required by `AGENTS.md`.
6. Keep v1 and v2 schemas aligned when the option is intentionally supported by both.
7. Treat proxy bypass, TLS bypass, browser JavaScript, headers, and local-network access
   as security capabilities. Validate authorization and scope; never expose them merely
   because an internal application needs them.
8. Run the narrowest relevant harness command and report the exact result.

## Synchronize upstream

1. Record the current fork base, branch, remotes, status, and custom diff.
2. Fetch without mutating user work.
3. Classify each conflict as upstream-only, fork capability, or application-specific.
4. Preserve a fork capability only with a focused regression test and an explicit owner.
5. Revalidate schemas, engine option propagation, Playwright payloads, action support,
   time budgets, and SDK compatibility after the merge or rebase.
6. Keep secrets, generated outputs, local environments, and experimental logs out of
   commits.

## Finish

- Run focused tests before broad tests.
- Inspect `git diff --check` and the final scoped diff.
- Distinguish verified behavior from live-network assumptions.
- Do not push, open a pull request, or mutate remotes unless the user asks.
