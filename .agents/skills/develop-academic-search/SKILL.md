---
name: develop-academic-search
description: Analyze, maintain, test, and extend the multi-provider academic literature search package under projects/academic_search. Use for scholarly search providers, abstract enrichment, article models, deduplication, topic or LLM analysis, citation exports, CLI behavior, Firecrawl or API integrations, research reproducibility, and academic-data quality or ethics.
---

# Develop Academic Search

Build reproducible literature tooling while keeping provider data, derived analysis,
and user-facing claims distinguishable.

## Start safely

1. Run `git status --short --branch` and preserve existing changes and result artifacts.
2. Treat `projects/academic_search` as the package root and `academic_search` as the
   intended import name.
3. Read [project-map.md](references/project-map.md) before changing providers, models,
   orchestration, CLI behavior, or exporters.
4. Read [validation-and-integrity.md](references/validation-and-integrity.md) before
   testing, using credentials, running live searches, or making research-quality claims.

## Change a provider or pipeline

1. Trace the full path:
   provider response → `Article` normalization → `SearchResult` merge/deduplication →
   enrichment → analysis → exporter/CLI.
2. Keep provider adapters behind `BaseSearcher` or `BaseAbstractEnricher`.
3. Normalize DOI, title, authors, year, URL, abstract, source, and citation metadata at
   the adapter boundary.
4. Preserve provenance for every field that is enriched or derived.
5. Implement year, pagination, rate-limit, timeout, and authentication behavior
   explicitly per provider.
6. Return partial results with recorded provider errors when possible; do not silently
   turn a failed multi-source search into a claim of complete coverage.
7. Add mocked offline tests for response parsing, empty/malformed responses, rate
   limits, and deduplication. Gate live tests behind an explicit environment flag.

## Protect academic integrity

- Never fabricate an abstract, DOI, author, venue, citation count, or finding.
- Label LLM summaries, relevance judgments, and topics as derived outputs.
- Preserve the original abstract and provider/source identity.
- Record query, provider, filters, retrieval time, and deduplication logic for
  reproducibility.
- Verify cited papers against a provider record or DOI before presenting them as
  evidence.
- Respect provider terms, robots controls, rate limits, and licensing. Prefer official
  scholarly APIs over scraping protected publisher pages.
- Never describe search results as exhaustive unless the study design justifies it.

## Keep secrets safe

- Load provider and LLM credentials only from environment variables or an approved
  secret store.
- Never add default API keys, tokens, or private credentials to source, docs, fixtures,
  or result files.
- Redact credentials from logs and test output.
- Treat any credential already committed in this project as exposed and rotate it
  before reuse.

## Verify proportionally

- Run fast model, engine, parser, analyzer, and exporter tests offline.
- Run each provider's mocked tests before an optional live smoke test.
- Test CLI imports and one end-to-end export in a temporary directory.
- Validate JSON/CSV/Markdown/BibTeX/RIS escaping and round-trip expectations.
- Report provider failures separately from package defects and environment problems.
