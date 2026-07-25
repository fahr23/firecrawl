# Firecrawl testing and upstream synchronization

## API test rules

Follow root `AGENTS.md` as the controlling instruction:

- Prefer API E2E tests, called snips, over unit tests.
- Cover one happy path and one or more failure paths.
- Use `scrapeTimeout` from the local snip test library.
- Gate fire-engine tests with `!process.env.TEST_SUITE_SELF_HOSTED`.
- Gate AI tests with
  `!process.env.TEST_SUITE_SELF_HOSTED || process.env.OPENAI_API_KEY || process.env.OLLAMA_BASE_URL`.
- Run tests through `pnpm harness jest ...`; do not manually start API/workers.

Typical narrow command from `apps/api`:

```bash
pnpm harness jest path/to/focused.test.ts
```

Confirm the current workspace and script names in `apps/api/package.json` before running.

## Fork-capability test matrix

For proxy, action, or renderer changes, cover the relevant rows:

| Surface | Success | Failure/security |
|---|---|---|
| schema | accepted in intended API versions | unknown/wrong type rejected |
| propagation | exact normalized field reaches renderer | absent field preserves default |
| action | content changes as expected | invalid action/script fails safely |
| proxy | request follows selected policy | bypass cannot escape its intended scope |
| timeout | waits/actions complete in budget | cancellation and upper bound remain enforced |
| SPA status | known rendered route succeeds | a real error page is not promoted to success |

Do not make live KAP the only regression test. Use a deterministic fixture or local test
page, then optionally perform an authorized live smoke test.

Prefer a pure, import-safe browser-context-options builder when testing renderer
configuration. The Playwright service entry point has startup side effects, so importing
it directly into a unit test can accidentally launch runtime behavior. Verify available
scripts in its current `package.json`; do not assume it has a test command.

## Upstream sync checklist

1. Inspect `git merge-base`, recent fork commits, and `git diff <base>...HEAD`.
2. Fetch `upstream` and inspect incoming changes before choosing merge or rebase.
3. Preserve user changes and avoid destructive cleanup.
4. Resolve generated files through their normal generator when applicable.
5. Re-run the focused fork-capability tests plus affected upstream snips.
6. Inspect SDK types if a public option changed.
7. Document any capability intentionally carried as fork debt.

Treat successful compilation as necessary but insufficient for browser/runtime changes.
