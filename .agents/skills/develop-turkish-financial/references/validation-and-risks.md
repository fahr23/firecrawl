# Validation and risks

Snapshot inspected 2026-07-25. Re-run tests and classify failures before changing code.

## Python environment

The project is container-first and its image uses Python 3.11. Local environments may
resolve to Python 3.9 and fail on supported syntax such as `DatabaseManager | None`.
Use the `turkish-financial-api` container as the authoritative environment.

Build the service image from `requirements.runtime.txt` before interpreting collection
failures as product regressions.

## Focused results observed

- Pure domain plus sentiment-use-case lane: `36 passed` on Python 3.9.7.
- API contract lane: collection failed on Python 3.9 syntax incompatibility.

Older test modules mutate `sys.modules` during collection. Until isolation is repaired,
run these separately:

```bash
python -m pytest -q tests/test_upstream_features.py
python -m pytest -q tests/test_kap_scraper_new_methods.py
python -m pytest -q tests/test_db_helpers.py
python -m pytest -q --ignore=tests/test_upstream_features.py \
  --ignore=tests/test_kap_scraper_new_methods.py \
  --ignore=tests/test_db_helpers.py
```

Use the narrowest lane applicable to the change.

Container equivalents should be preferred, for example:

```bash
docker compose config --quiet
docker compose build turkish-financial-api turkish-financial-test
docker compose run --rm --no-deps turkish-financial-test \
  python -m pytest -q tests/test_upstream_features.py
```

## Highest risks

1. Fork-specific Firecrawl behavior and the Compose finance service are still in the
   dirty worktree; preserve and test them before relying on deployment.
2. Constructor-time schema mutation substitutes for versioned migrations.
3. Duplicate managers, dependency modules, and entry points can route changes through
   the wrong path.
4. Blocking network/model work can stall the FastAPI event loop.
5. In-memory schedulers can duplicate jobs across processes and lose state on restart.
6. Cache-miss GET routes may perform scraping and writes.
7. Combined-sentiment catalog/provider/sample-size semantics still contain two-source
   assumptions in some tests and routes; test news-only, social-only, YouTube-only, and
   mixed records.
8. Concurrent collectors and partial YouTube reruns can make daily rollups inconsistent
   unless recomputation becomes atomic and its source-of-truth semantics are defined.

## Security

- Collection and scheduler routes have no visible authentication.
- Wildcard CORS is combined with credentials.
- Middleware logs request/response bodies and buffers responses.
- Raw exception text is returned in the global 500 response.
- Some fallbacks disable TLS verification.
- Proxy bypass and arbitrary browser JavaScript expand egress/code-execution power.
- Development database credentials are used as defaults.

Require authentication, secret redaction, sanitized errors, egress policy, and bounded
resources before internet-facing deployment.
