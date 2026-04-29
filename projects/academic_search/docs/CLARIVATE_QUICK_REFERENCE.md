# Clarivate Web of Science - Quick Reference

## Installation & Setup

```bash
# Set API key in environment
export CLARIVATE_API_KEY="25c3c04668c64cd41731c51b0dc253d790b262dd"
```

## Quick Start Examples

### 1. Basic Search

```python
from api_academic_search import create_engine

engine = create_engine()
result = engine.search("machine learning", max_results=10, providers=["Web of Science"])
```

### 2. Find Highly Cited Papers

```python
from api_academic_search.providers import ClarivateSearcher
from api_academic_search.config import Config

searcher = ClarivateSearcher(Config())
result = searcher.search_highly_cited("deep learning", min_year=2020, max_results=10)
```

### 3. Search by Author

```python
result = searcher.search_by_author("Einstein A*", max_results=10)
```

### 4. Search by Organization

```python
result = searcher.search_by_organization("MIT", max_results=10, sort_by="citations")
```

### 5. Advanced Query

```python
result = searcher.search(
    query="TS=(climate change) AND TS=(machine learning)",
    max_results=20,
    year_min=2020,
    sort_by="citations"
)
```

## Field Tags Cheat Sheet

| Tag  | Field        | Example                 |
| ---- | ------------ | ----------------------- |
| `TS` | Topic        | `TS=(machine learning)` |
| `TI` | Title        | `TI=(climate change)`   |
| `AU` | Author       | `AU=(Smith J*)`         |
| `OG` | Organization | `OG=(MIT)`              |
| `PY` | Year         | `PY=(2020-2024)`        |
| `SO` | Journal      | `SO=(Nature)`           |
| `DO` | DOI          | `DO=(10.1038/...)`      |

## Sorting Options

- `"relevance"` - Most relevant (default)
- `"citations"` - Most cited first
- `"year_desc"` - Newest first
- `"year_asc"` - Oldest first

## Boolean Operators

- `AND` - Both terms required
- `OR` - Either term required
- `NOT` - Exclude term
- `NEAR/n` - Within n words

Example: `TS=(machine learning OR deep learning) AND TS=(healthcare)`

## Databases

- `"WOS"` - Web of Science Core (default)
- `"BIOABS"` - Biological Abstracts
- `"MEDLINE"` - Medical literature

## Access Article Data

```python
for article in result.articles:
    print(article.title)
    print(article.authors)
    print(article.year)
    print(article.doi)
    print(article.citation_count)  # Times cited
    print(article.journal)
    print(article.keywords)
```

## CLI Usage

### Basic Commands

```bash
# Run from firecrawl directory
cd /Users/FF/Projects/myProjects/backtofuture_scraper/firecrawl

# Most cited papers
python -m api_academic_search.search_cli "machine learning" --sort-by citations --max-results 10

# Title search
python -m api_academic_search.search_cli "climate change" --field-tag TI --year-min 2020

# Author search
python -m api_academic_search.search_cli "Einstein A*" --field-tag AU --sort-by citations

# Organization search
python -m api_academic_search.search_cli "MIT" --field-tag OG --sort-by citations

# MEDLINE database
python -m api_academic_search.search_cli "cancer" --database MEDLINE --sort-by year_desc
```

### CLI Options Quick Reference

| Option        | Values                                          | Description             |
| ------------- | ----------------------------------------------- | ----------------------- |
| `--sort-by`   | citations, year_desc, newest, oldest, relevance | Sort order              |
| `--field-tag` | TS, TI, AU, OG, SO                              | Field to search         |
| `--database`  | WOS, BIOABS, MEDLINE                            | Database selection      |
| `--year-min`  | YYYY                                            | Minimum year            |
| `--year-max`  | YYYY                                            | Maximum year            |
| `--format`    | json, markdown, csv, bibtex, ris                | Output format           |
| `--providers` | "Web of Science"                                | Force specific provider |

### Full CLI Documentation

See: `docs/CLI_CLARIVATE_USAGE.md`

## Run Interactive Demo

```bash
cd api_academic_search
python demo_clarivate_features.py
```

## Documentation

- **Full Guide**: `docs/CLARIVATE_FEATURES.md`
- **Summary**: `CLARIVATE_INTEGRATION_SUMMARY.md`
- **Swagger API**: https://api.clarivate.com/swagger-ui/

## Rate Limits

- 5 requests/second
- 5,000 requests/day
- 50 results/page max
