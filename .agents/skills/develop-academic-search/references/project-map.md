# Academic search project map

Snapshot inspected 2026-07-25.

## Package

- Root: `projects/academic_search`
- Intended import: `academic_search`
- Public exports: `__init__.py`
- Configuration: `config.py`
- Domain records: `models.py`
- Extension interfaces: `base.py`
- Search and enrichment adapters: `providers.py`
- Orchestrator: `engine.py`
- Topic/LLM analysis: `analyzers.py`
- JSON, Markdown, CSV, BibTeX, and RIS output: `exporters.py`
- CLI: `search_cli.py`
- Tests: `tests/`

There is no observed package-specific `pyproject.toml` or locked dependency file. Run
from the repository with `PYTHONPATH=projects` until packaging is made explicit.

## Pipeline

`AcademicSearchEngine`
→ configured `BaseSearcher` implementations
→ provider-specific `Article` normalization
→ merge and DOI deduplication
→ optional abstract enrichers
→ topic or LLM analyzers
→ exporters/CLI.

Configured providers currently include ScienceDirect, Scopus, OpenAlex, Semantic
Scholar, arXiv, Google Scholar through Serper/Firecrawl fallback, and Clarivate Web of
Science. Crossref, Semantic Scholar, and Scopus can enrich abstracts.

## Firecrawl boundary

Academic search is primarily API-based. Firecrawl appears in:

- optional Google Scholar fallback;
- browser-action and publisher demos;
- experiments around pages that block direct scraping.

Keep scholarly metadata retrieval in official APIs when available. Put only generic
runtime capabilities in Firecrawl itself.

## Known naming drift

`search_cli.py` and the Clarivate demo still import the old name
`api_academic_search`, while the package directory and tests use `academic_search`.
The CLI also inserts `projects/academic_search` into `sys.path` rather than the parent
`projects`, so changing only the import string does not make direct-script execution
reliable. `projects/search.sh` also invokes the old module name. Resolve imports,
launchers, packaging, and a console entry point consistently before treating the CLI as
supported.

## Extension workflow

To add a source:

1. implement `BaseSearcher`;
2. define availability and credential behavior;
3. normalize a stable `Article`;
4. register it in the engine;
5. add mocked success, empty, malformed, auth, and rate-limit tests;
6. update CLI provider selection and documentation.

To add an analysis method, implement `BaseAnalyzer` and keep derived output separate
from source metadata.
