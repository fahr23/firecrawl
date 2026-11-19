# Academic Literature Search Package

A modular, extensible Python package for searching academic literature across multiple databases with support for abstract enrichment, topic extraction, and LLM-based analysis.

## Features

- 🔍 **Multi-Source Search**: Search OpenAlex, Semantic Scholar, ArXiv, ScienceDirect, Scopus, **Web of Science (Clarivate)**, and Google Scholar (via Serper)
- 📊 **Advanced Sorting**: Sort by citations, publication year, or relevance (Clarivate)
- 🎯 **Field-Specific Search**: Search by title, author, organization, or topic (Clarivate)
- 📚 **Multiple Databases**: Access WOS, BIOABS, MEDLINE (Clarivate)
- 📝 **Abstract Enrichment**: Fetch missing abstracts from CrossRef, Semantic Scholar
- 🏷️ **Topic Extraction**: Automatic keyword and topic extraction
- 🤖 **LLM Analysis Ready**: Extension point for AI-powered abstract analysis
- 📤 **Multiple Export Formats**: JSON, Markdown, CSV, BibTeX, RIS
- 🔧 **Extensible Architecture**: Easy to add new sources, analyzers, exporters
- 📰 **Journal Explorer**: Resolve journals by OpenAlex source/ISSN, search their papers by topic, and save dated evidence snapshots
- 🗂️ **Provider Journal Catalogs**: Browse OpenAlex Fields, Web of Science/JCR categories, or Scopus subject areas before searching by title, publisher, or ISSN
- 🧭 **Manuscript Fit**: Compare a title, abstract, and keywords with an exact saved journal snapshot using transparent lexical scoring

## Web workspace

Run the Compose service and open `http://localhost:8010/`:

```bash
docker compose up -d academic-search-api
```

Create or switch between saved research projects from the **Topics** sidebar.
Each topic reopens its latest saved paper search, journal snapshot, and any fit
report for that snapshot. Open older runs from **Saved searches** or **Saved journal
snapshots**. Use **Temporary search** for paper searches outside a saved topic.

The publishing tabs use the same project store:

- **Discover** compares an OpenAlex topic's share across two completed publication
  years. Save recent papers or representative papers to your shortlist and turn
  documented limitations and conflicting evidence into research questions.
- **Submissions** finds related journals from an OpenAlex publication sample and
  checks supported official pages for submission status. Save regular routes or
  individual calls with dates, fees, article types, and indexing evidence. Use
  manual checks when a publisher's notice is unavailable to the service.
- **Manuscript** starts an outline from the chosen article type and research
  question. Link claims to shortlist papers, record journal requirements, and
  export the draft, evidence log, and checklist as Markdown or its references as
  BibTeX or RIS. Saving creates a version in project history.
- **Dossier** records a doçentlik or professorship target, the official criteria
  for that application, and dated evidence for each activity. Reviewed statuses
  reflect the researcher's assessment and the export retains the source clauses.

Configure `OPENALEX_API_KEY` for the optional OpenAlex cursor and a larger request
budget. Set `SEMANTIC_SCHOLAR_API_KEY` or `CORE_API_KEY` for authenticated requests
to their respective sources. The workspace shows source failures alongside any
partial results. Paper searches expose up to ten pages per query.

In **Papers**, **Live + saved** shows a saved preview when available and checks
the selected APIs each time you submit a search. Saved copies are identified
when a provider is unavailable. **Saved only** searches your local library by
keywords, quoted phrases, or DOI without calling any provider. The library
includes papers retrieved in saved topics and temporary searches. Use
**Save to shortlist** to add a library paper to the active topic.

See [the database guide](DATABASE.md) for cache behavior, the schema, and backups.

### Monitor a topic and revisit papers

Open a topic and select **Watch this search** in Papers. Use **Inbox** to check
manually or set a daily or weekly schedule. Automatic checks run while the
local service is running, even when the browser is closed. Each check compares
up to 50 returned matches with the watch's history. OpenAlex, arXiv, and PubMed
use date ordering for watches. Other providers use their normal ordering.
The inbox shows papers dated in the last 30 days, older or undated papers new
to your library, and related papers already in the library. A partial check
lists its provider failures and preserves the last fully successful check.

Paper cards show opens and a **Mark read** action. **Inbox → Reading activity**
lists which paper URLs or DOI links you opened in the app, the count for each
address, and the last open. Read markers are shared across topics.

### Follow journals

In **Journals**, search for and select a journal, then choose **Follow journal**.
Followed journals are shared across topics. **Journals** shows the recent
publications and **Today** shows how many papers are new for each journal.
Opening a paper, marking it read, or using **Mark all seen** clears its new badge.
Each check uses up to 30 of the latest OpenAlex records for that journal and
keeps earlier results in the local library. Journals without an OpenAlex match
can still be followed for submission information.

Check **Submission opportunities** for author guidelines, article types, fees,
submission links, and verified open special issues with deadlines where the
publisher supplies them. Unknown regular submission status is shown as
unverified. Journals refresh daily while the app is running. You can refresh
manually, and the saved feed stays available if a source fails.

### Set up daily reading

In **Daily reading**, select a topic and choose keywords, paper sources, a start
date, the local time and time zone, and one to ten papers per day. Each topic
has its own schedule. Use **Get today’s papers** for an on-demand edition or turn
on automatic checks. The local service builds the current day’s edition when
the schedule is due, including when it resumes later that day.

The app looks for recent papers and fills available slots with unopened matches
from the local library when appropriate. A work recommended by Daily reading
stays in its original edition across topics and dates. **Mark read** updates the
edition and the shared library, and the **Edition** menu opens previous lists.
The **All topics** view shows daily progress and trend highlights across schedules.

Trend suggestions use OpenAlex to compare a subtopic’s share of matching articles
and reviews across two complete 30-day publication windows. The app shows the
dates and counts, flags limited samples, and reports source failures. The comparison
describes the indexed sample.

### Deadlines and promotion evidence

In **Submissions**, track a manuscript through submission, revision, acceptance,
and publication. A revision can include a deadline, reviewer comments, and the
editorial reference. The calendar lists dated open or upcoming calls and pending
revisions across topics. Download the `.ics` file to add reminders one week and
one day before due dates to your calendar. Import a fresh export when dates change.

In **Dossier**, add academic evidence to **Shared evidence** once and link it to
criteria for any topic's application target. Earlier topic activities are copied
into the shared portfolio. Each target retains its official criteria and review
status. Edits to shared evidence return linked, previously reviewed criteria to
**In review** so you can check the updated evidence.

### Move from reading to a manuscript

- Open **Today** to see reading progress, upcoming calls and revisions, and
  manuscript actions across topics. Open a draft directly from its action card.
- From a paper or daily trend, use **Start research brief**. In **Discover**,
  compare saved study notes by method, dataset, findings, limitations, and source
  location. Record data access and the next investigation step in the brief,
  then open a manuscript outline from that brief.
- In **Manuscript**, assign a stage, next action, and due date. Each draft keeps
  a local server autosave and a browser recovery copy during editing. **Save version
  and review** creates a named point in the revision history. Insert inline
  citations from the topic shortlist and **Download Word** to export numbered
  citations and references from the latest autosave.
- In **Submissions**, **Find special issues** searches supported official listings
  by call keywords, journal or ISSN, and full-manuscript deadline. **Verify an
  official call by URL** checks a supported public page directly. Save a call to
  a topic or attach it to a draft. The local service rechecks saved calls and
  shows changes in **Today**. Some publishers require a visit to their own listing
  when the public page is unavailable to the service.

### Optional model assistance

The assistant can compare selected study records, suggest next steps for a saved
brief, review saved manuscript sections, or assess a draft abstract against a
publisher call. Choose a provider and click **Run assistant** to send the selected
saved material. Suggestions cite the supplied records and leave drafts and evidence
editable by the researcher.

Configure a key and a model ID in the local service environment:

| Provider | Environment variables |
| --- | --- |
| OpenAI | `OPENAI_API_KEY`, `ACADEMIC_OPENAI_MODEL` |
| Anthropic | `ANTHROPIC_API_KEY`, `ACADEMIC_ANTHROPIC_MODEL` |

See the [local deployment guide](../../deploy/academic-search/README.md) for Compose
and OrbStack configuration.

Journal searches belong to a research project. Repeating the same journal, topics,
years, and limit loads the saved SQLite snapshot without another provider request.
Use **Refresh from source** to retrieve and save a newer version. The UI always shows
the retrieval time and flags snapshots older than `ACADEMIC_JOURNAL_REFRESH_DAYS`
(seven days by default). Manuscript-fit reports are stored against the exact snapshot
used for comparison and are included in project evidence exports.

The journal profile, article alignment, and manuscript-fit values are derived outputs.
They describe the retrieved sample and must not be interpreted as an editorial decision
or acceptance prediction.

Catalog provider access:

- OpenAlex journal categories and source records work without a paid credential.
- Web of Science journal/category browsing uses the dedicated Journals API. Configure
  `CLARIVATE_JOURNALS_API_KEY`; `CLARIVATE_API_KEY` remains the Starter article-search
  credential and is used as a compatibility fallback when it also has JCR entitlement.
- Scopus journal/category browsing uses the Serial Title API and `ELSEVIER_API_KEY`.

Journal records are normalized with ISSN/ISSN-L and provider source IDs. DOI is an
article identifier, so it is displayed on paper results rather than represented as a
journal identifier. Paid-provider journal selections are crosswalked by ISSN to an
OpenAlex Source ID before journal-scoped article search.

TÜBİTAK UBYT list:

- The 2026 list (`data/ubyt_2026.csv`, converted from
  `docs/ubyt_2026_liste_v3-08102026.xlsx`) is bundled; no credential is needed.
- Choose **TÜBİTAK UBYT** as the catalog provider to search journals by name or ISSN
  and filter by SCIE/SSCI/AHCI/Scopus; selections are crosswalked to OpenAlex by ISSN.
- Every journal and paper result carries a `ubyt` entry (payment in TL, MEP score,
  indexes) matched by ISSN first, then exact normalized title (`matched_by` says which),
  or `null` when the journal is not listed.
- `GET /api/v1/ubyt/journals?q=&category=` searches the list;
  `GET /api/v1/ubyt/lookup?issn=&name=` returns one journal's entry.
- To load a new release: `python -m academic_search.ubyt_catalog convert <new.xlsx>
  data/ubyt_<year>.csv` (requires `openpyxl`) and point `ACADEMIC_UBYT_CATALOG_PATH`
  at it, or replace the bundled file.

## Quick Start

### Installation

```bash
# Install dependencies
pip install requests

# Optional: for LLM analysis
pip install openai anthropic
```

### Basic Usage

```python
from academic_search import create_engine

# Create engine (uses OpenAlex, Semantic Scholar, and ArXiv by default - free, no API key needed)
engine = create_engine()

# Search for papers
results = engine.search("machine learning healthcare", max_results=25)

# Export results
engine.export(results, "results.json")
engine.export(results, "results.md")  # Markdown format
```

### With Elsevier API Key (Scopus)

```python
from academic_search import create_engine

# With Scopus (Elsevier) API key for better results
engine = create_engine(elsevier_api_key="your-api-key")

# Or set environment variable
# export ELSEVIER_API_KEY=your-api-key

results = engine.search("deep learning", max_results=50)
```

### With Clarivate Web of Science

```python
from academic_search import create_engine

# With Clarivate API key
engine = create_engine(clarivate_api_key="your-api-key")

# Or set environment variable
# export CLARIVATE_API_KEY=your-api-key

# Search with sorting by citations
results = engine.search("machine learning", max_results=25, providers=["Web of Science"])

# Access citation counts
for article in results.articles:
    print(f"{article.title} - Citations: {article.citation_count}")
```

### Full Configuration

```python
from academic_search import AcademicSearchEngine, Config

config = Config(
    debug=True,
    max_results=50,
    enable_llm_analysis=True,
    llm_provider="openai",
    llm_api_key="sk-...",
)
config.api.elsevier_api_key = "your-elsevier-key"
config.api.clarivate_api_key = "your-clarivate-key"

engine = AcademicSearchEngine(config)
results = engine.search("quantum computing")
```

## CLI Usage

### Basic Commands

```bash
# Basic search
python -m academic_search.search_cli "machine learning" --max-results 25

# Export to file
python -m academic_search.search_cli "climate change" -o results.md -f markdown

# With analysis
python -m academic_search.search_cli "neural networks" --analyze --topics

# Search all sources
python -m academic_search.search_cli "renewable energy" --enrich

# With API key
python -m academic_search.search_cli "batteries" --elsevier-key YOUR_KEY

# Specific providers only
python -m academic_search.search_cli "AI safety" --providers google arxiv
```

### Clarivate Web of Science Features

```bash
# Find most cited papers
python -m academic_search.search_cli "deep learning" \
    --sort-by citations \
    --max-results 10 \
    --providers "Web of Science"

# Search by title only
python -m academic_search.search_cli "climate change" \
    --field-tag TI \
    --year-min 2020

# Search MEDLINE database
python -m academic_search.search_cli "cancer treatment" \
    --database MEDLINE \
    --sort-by year_desc

# Search by author
python -m academic_search.search_cli "Einstein A*" \
    --field-tag AU \
    --sort-by citations

# Search by organization
python -m academic_search.search_cli "MIT" \
    --field-tag OG \
    --sort-by citations \
    --max-results 20
```

**See full CLI documentation**: [docs/CLI_CLARIVATE_USAGE.md](docs/CLI_CLARIVATE_USAGE.md)

## Helper Tools

### Bulk Open URLs (`open_urls.py`)

A utility script is located in the `results/` directory to help you quickly open all article URLs from a generated Markdown report.

**Features:**

- AUTOMATICALLY finds the `.md` report in your target subfolder.
- OPENS unique URLs in your default browser.
- **BATCH PROCESSING**: Opens URLs in batches (default: 50) to prevent browser memory issues.
- **INTERACTIVE**: Pauses between batches and waits for your confirmation.

**Usage:**

```bash
# Navigate to results directory
cd results

# Run script targeting a specific result folder (the timestamped folder name)
python3 open_urls.py <subfolder_name> [batch_size]
```

**Example:**

```bash
# Open URLs from a specific report in batches of 50 (default)
python3 open_urls.py agent_based_learning_co2_emission_20260204_152644

# Open in smaller batches of 20
python3 open_urls.py agent_based_learning_co2_emission_20260204_152644 20
```

## Search Results

Results are returned as a `SearchResult` object containing `Article` objects:

```python
results = engine.search("deep learning")

# Access metadata
print(f"Total found: {results.total_found}")
print(f"Sources: {results.sources}")

# Iterate articles
for article in results.articles:
    print(f"Title: {article.title}")
    print(f"Authors: {article.authors}")
    print(f"Year: {article.year}")
    print(f"DOI: {article.doi}")
    print(f"Abstract: {article.abstract[:200]}...")
    print(f"Keywords: {article.keywords}")
    print("---")

# Filter results
with_abstracts = results.filter_with_abstracts()
recent = results.filter_by_year(2022, 2024)
```

## Abstract Enrichment

If articles are missing abstracts, you can enrich them from multiple sources:

```python
results = engine.search("machine learning")

# Before enrichment
print(f"With abstracts: {sum(1 for a in results.articles if a.abstract)}")

# Enrich from CrossRef, Semantic Scholar, etc.
results = engine.enrich_abstracts(results)

# After enrichment
print(f"With abstracts: {sum(1 for a in results.articles if a.abstract)}")
```

## Topic Extraction

Extract common topics and keywords from search results:

```python
# Get top topics
topics = engine.extract_topics(results, top_n=15)

for topic, score in topics:
    print(f"{topic}: {score:.1f}")
```

## Export Formats

### JSON

```python
engine.export(results, "output.json")

# Or get as string
json_str = engine.export_to_string(results, format="json")
```

### Markdown

```python
engine.export(results, "output.md")

# Generates a formatted document with table of contents
```

### CSV

```python
engine.export(results, "output.csv")

# Good for importing into spreadsheets or other tools
```

### BibTeX

```python
engine.export(results, "references.bib")

# Ready to use with LaTeX
```

## LLM-Based Analysis

The package includes an extension point for LLM-based abstract analysis:

### Setup

```python
from academic_search import create_engine

# With OpenAI
engine = create_engine(
    enable_llm=True,
    llm_provider="openai",
    llm_api_key="sk-..."
)

# With Anthropic
engine = create_engine(
    enable_llm=True,
    llm_provider="anthropic",
    llm_api_key="..."
)
```

### Usage

```python
results = engine.search("renewable energy storage")

# Analyze articles (summarizes, extracts key findings)
analysis = engine.analyze(results)

print(analysis["llm"])  # LLM analysis results
print(analysis["topics"])  # Topic extraction
```

### Custom Analysis

```python
from academic_search import LLMAnalyzer, Config

config = Config(
    enable_llm_analysis=True,
    llm_provider="openai",
    llm_api_key="sk-..."
)

# Custom analysis types
analyzer = LLMAnalyzer(
    config,
    analysis_types=["summary", "key_findings", "methodology", "research_gaps"]
)

for article in results.articles[:5]:
    analysis = analyzer.analyze(article, query=results.query)
    print(f"Title: {article.title}")
    print(f"Summary: {analysis.get('summary')}")
    print(f"Key Findings: {analysis.get('key_findings')}")
```

## Extending the Package

### Custom Search Provider

```python
from academic_search import BaseSearcher, Article, SearchResult, Config

class MyDatabaseSearcher(BaseSearcher):
    @property
    def source_name(self) -> str:
        return "MyDatabase"

    def search(self, query: str, max_results: int = 25) -> SearchResult:
        # Implement your search logic
        articles = []

        # ... fetch from your database ...

        for item in raw_results:
            articles.append(Article(
                title=item["title"],
                authors=item["authors"],
                year=item["year"],
                doi=item["doi"],
                abstract=item.get("abstract"),
                url=item["url"],
                source=self.source_name
            ))

        return SearchResult(
            query=query,
            articles=articles,
            total_found=total,
            sources=[self.source_name]
        )

# Use it
engine.add_searcher(MyDatabaseSearcher(config), priority=0)  # First priority
```

### Custom Abstract Enricher

```python
from academic_search import BaseAbstractEnricher, Article, Config

class MyEnricher(BaseAbstractEnricher):
    @property
    def source_name(self) -> str:
        return "MyEnricher"

    def get_abstract(self, article: Article) -> str | None:
        # Fetch abstract using DOI, title, etc.
        if article.doi:
            # ... fetch abstract ...
            return abstract
        return None

# Add to engine
engine.add_enricher(MyEnricher(config))
```

### Custom Analyzer

```python
from academic_search import BaseAnalyzer, Article, Config

class SentimentAnalyzer(BaseAnalyzer):
    @property
    def analyzer_name(self) -> str:
        return "SentimentAnalyzer"

    def analyze(self, article: Article) -> dict:
        # Analyze article sentiment, research direction, etc.
        return {
            "sentiment": "positive",
            "confidence": 0.85
        }

engine.add_analyzer(SentimentAnalyzer(config))
```

### Custom Exporter

```python
from academic_search import BaseExporter, SearchResult, Config

class XMLExporter(BaseExporter):
    @property
    def format_name(self) -> str:
        return "XML"

    @property
    def file_extension(self) -> str:
        return "xml"

    def export(self, result: SearchResult, filepath: str) -> str:
        # Generate XML
        filepath = self._ensure_extension(filepath)
        # ... write XML ...
        return filepath

engine.add_exporter("xml", XMLExporter(config))
engine.export(results, "output.xml", format="xml")
```

## Configuration

### Environment Variables

```bash
# API Keys
export ELSEVIER_API_KEY=your-elsevier-key
export SERPER_API_KEY=your-serper-key # For Google Scholar
export OPENAI_API_KEY=sk-...
export ANTHROPIC_API_KEY=...

# Settings
export ACADEMIC_SEARCH_DEBUG=true
export ACADEMIC_SEARCH_MAX_RESULTS=50
```

### Config File

```python
from academic_search import Config

# Load from environment
config = Config.from_env()

# Save to file
config.save("config.json")

# Load from file
config = Config.load("config.json")
```

### All Configuration Options

```python
from academic_search import Config, APIConfig

config = Config(
    # General
    debug=False,
    max_results=25,
    timeout=30,

    # LLM settings
    enable_llm_analysis=False,
    llm_provider=None,  # "openai" or "anthropic"
    llm_api_key=None,
    llm_model=None,  # "gpt-4o-mini" or "claude-3-sonnet-20240229"
)

# API keys
config.api = APIConfig(
    elsevier_api_key="...",
    semantic_scholar_api_key="...",
    serper_api_key="...", # For Google Scholar
)
```

## Package Structure

```
academic_search/
├── __init__.py          # Package exports
├── README.md            # This file
├── config.py            # Configuration management
├── models.py            # Article, SearchResult dataclasses
├── base.py              # Abstract base classes
├── providers.py         # Search providers (Scopus, OpenAlex)
├── analyzers.py         # Topic extraction, LLM analysis
├── exporters.py         # JSON, Markdown, CSV, BibTeX, RIS
├── engine.py            # Main orchestrator
├── search_cli.py        # Command-line interface
├── demos/               # Interactive demo scripts
│   ├── firecrawl_actions_demo.py
│   └── sciencedirect_demo.py
├── examples/            # Production search scripts
│   ├── academic_literature_search.py
│   ├── sciencedirect_literature_search.py
│   └── ...
├── results/             # Search output files
│   ├── renewable_energy/
│   ├── ml_healthcare/
│   └── misc/
├── screenshots/         # Demo screenshots
├── docs/                # Additional documentation
│   ├── ELSEVIER_API_SUPPORT.md
│   ├── QUICK_START.md
│   └── ...
└── tests/               # Unit tests
```

## API Reference

### AcademicSearchEngine

The main class that coordinates all components.

```python
engine = AcademicSearchEngine(config)

# Search
results = engine.search(
    query,
    max_results=25,
    use_all_sources=False,
    year_min=2020,
    year_max=2024
)

# Enrich
results = engine.enrich_abstracts(results, parallel=True)

# Analyze
analysis = engine.analyze(results, analyzer_type=None)
topics = engine.extract_topics(results, top_n=25)

# Export
engine.export(results, filepath, format=None)
output = engine.export_to_string(results, format="json")

# Convenience
results = engine.search_and_export(query, output_path, max_results=25, enrich=True)
articles = engine.quick_search(query, max_results=10)

# Component management
engine.add_searcher(searcher, priority=-1)
engine.add_enricher(enricher)
engine.add_analyzer(analyzer)
engine.add_exporter(name, exporter)

# Properties
engine.available_sources  # List of search source names
engine.available_exporters  # List of export formats
```

### Article

Data class representing an academic article.

```python
article = Article(
    title="...",
    authors="Author1, Author2",
    year=2024,
    journal="...",
    doi="10.1234/...",
    abstract="...",
    url="https://...",
    source="Scopus",
    keywords=["keyword1", "keyword2"]
)

article.to_dict()  # Convert to dictionary
article.to_bibtex()  # Generate BibTeX entry
```

### SearchResult

Container for search results.

```python
result = SearchResult(
    query="...",
    articles=[...],
    total_found=1000,
    sources=["Scopus", "OpenAlex"]
)

result.filter_by_year(2020, 2024)  # Filter by year range
result.filter_with_abstracts()  # Only articles with abstracts
```

## Contributing

Contributions are welcome! To add a new feature:

1. Create a new class extending the appropriate base class
2. Implement the required abstract methods
3. Register with the engine using `add_*` methods
4. Add tests and documentation

## License

MIT License

## Credits

- [Scopus/Elsevier API](https://dev.elsevier.com/)
- [OpenAlex](https://openalex.org/)
- [Semantic Scholar](https://www.semanticscholar.org/)
- [CrossRef](https://www.crossref.org/)
- [Serper.dev](https://serper.dev/)
