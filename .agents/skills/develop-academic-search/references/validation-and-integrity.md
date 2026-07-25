# Academic search validation and integrity

Snapshot inspected 2026-07-25.

## Offline baseline

This focused command passed:

```bash
PYTHONPATH=projects python3 -m pytest -q \
  projects/academic_search/tests/test_academic_search.py
```

Observed result: `17 passed, 1 skipped` on Python 3.9.7. The skipped test is a live
integration test.

Do not equate this result with CLI or provider integration coverage.

## Known issues to check first

1. `search_cli.py` imports `api_academic_search`, not the current package name.
2. Configuration and several docs/tests contain committed provider credentials.
   Do not copy or print them. Remove defaults, scrub history where appropriate, and
   rotate the credentials.
3. Default credentials activate paid/keyed providers implicitly, so a nominal default
   engine is not truly free-only.
4. Multi-source deduplication uses DOI only; papers without a DOI can duplicate.
5. Multi-source `max_results` is applied per provider and the merged list is not capped,
   which may surprise callers and inflate cost.
6. Broad exception handling logs and continues, but `SearchResult` does not provide
   structured per-provider failure metadata.
7. Several files named as tests are live diagnostic scripts with embedded credentials
   or network assumptions.
8. Documentation contains historical performance and coverage claims. Re-measure before
   repeating them.
9. Abstract enrichment mutates `Article.abstract` without field-level source provenance.
10. The CLI writes default results beneath the source package; installed tools should
    use stdout, an explicit destination, or an appropriate user-data directory.

## Test lanes

### Fast offline

- article normalization and DOI/title matching;
- search-result filters and deduplication;
- provider parsing from saved fixtures;
- engine selection and merge semantics;
- enrichment provenance;
- analyzer behavior with mocked LLMs;
- export escaping and deterministic output;
- CLI import and argument parsing.

Run CLI smoke tests from a temporary directory after installation so the repository
working directory cannot hide package-boundary defects. Assert that import, `--help`,
provider listing, and argument errors make no network calls.

### Optional live

Require an explicit flag and environment-provided credentials. Test one low-volume
request per selected provider, respect rate limits, and avoid storing raw licensed
content in fixtures.

### Firecrawl integration

Use only for a feature that genuinely requires rendered browsing. Add a deterministic
local-page test before any publisher-site smoke test.

## Reproducibility record

For research output, retain:

- exact query and field syntax;
- providers and database editions;
- year and other filters;
- retrieval timestamp;
- pagination/result limits;
- deduplication rules and counts;
- enrichment sources;
- exclusions and provider failures;
- analysis model/version/prompt when LLMs are used.

Keep source abstracts immutable. Store summaries, topics, and relevance scores in
separate derived fields with provenance.
