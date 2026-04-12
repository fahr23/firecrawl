# CLI Usage Guide - Clarivate Web of Science Features

## Overview

The `search_cli.py` command-line interface now supports advanced Clarivate Web of Science features including sorting by citations, field-specific searches, and database selection.

## Installation & Setup

```bash
# Set API key (optional - default key is already configured)
export CLARIVATE_API_KEY="your_api_key_here"

# Or use command-line argument
python -m api_academic_search.search_cli "query" --clarivate-key "your_key"
```

## Basic Usage

```bash
# Run from the firecrawl directory
cd /Users/FF/Projects/myProjects/backtofuture_scraper/firecrawl

# Basic search
python -m api_academic_search.search_cli "machine learning" --max-results 10

# Get help
python -m api_academic_search.search_cli --help
```

---

## Clarivate-Specific Features

### 1. Sort by Citations (Find Most Impactful Papers)

```bash
# Find most cited papers on machine learning
python -m api_academic_search.search_cli "machine learning" \
    --sort-by citations \
    --max-results 10 \
    --providers "Web of Science"

# Alternative: use 'most_cited' alias
python -m api_academic_search.search_cli "deep learning" \
    --sort-by most_cited \
    --max-results 20
```

**Sort Options:**

- `relevance` - Most relevant (default)
- `citations` or `most_cited` - Most cited first
- `year_desc` or `newest` - Newest first
- `year_asc` or `oldest` - Oldest first

### 2. Field-Specific Searches

```bash
# Search only in titles
python -m api_academic_search.search_cli "climate change" \
    --field-tag TI \
    --max-results 10

# Search by author
python -m api_academic_search.search_cli "Einstein A*" \
    --field-tag AU \
    --sort-by citations

# Search by organization
python -m api_academic_search.search_cli "MIT" \
    --field-tag OG \
    --sort-by citations \
    --max-results 20

# Search in journal/source
python -m api_academic_search.search_cli "Nature" \
    --field-tag SO \
    --year-min 2020
```

**Field Tags:**

- `TS` - Topic (title, abstract, keywords) - **Most comprehensive**
- `TI` - Title only
- `AU` - Author name
- `OG` - Organization/Institution
- `SO` - Source (journal name)

### 3. Database Selection

```bash
# Search MEDLINE database for medical literature
python -m api_academic_search.search_cli "cancer treatment" \
    --database MEDLINE \
    --sort-by year_desc \
    --max-results 10

# Search Biological Abstracts
python -m api_academic_search.search_cli "protein structure" \
    --database BIOABS \
    --sort-by citations

# Web of Science Core Collection (default)
python -m api_academic_search.search_cli "quantum computing" \
    --database WOS
```

**Database Options:**

- `WOS` - Web of Science Core Collection (default)
- `BIOABS` - Biological Abstracts
- `MEDLINE` - Medical literature

### 4. Year Filtering

```bash
# Papers from 2020 onwards
python -m api_academic_search.search_cli "machine learning" \
    --year-min 2020 \
    --sort-by citations

# Papers from specific year range
python -m api_academic_search.search_cli "quantum computing" \
    --year-min 2020 \
    --year-max 2024 \
    --sort-by year_desc

# Recent papers sorted by newest
python -m api_academic_search.search_cli "deep learning" \
    --year-min 2023 \
    --sort-by newest
```

### 5. Advanced Boolean Queries

```bash
# Complex query with field tags (don't use --field-tag for these)
python -m api_academic_search.search_cli "TS=(machine learning OR deep learning) AND TS=(healthcare)" \
    --sort-by citations \
    --max-results 20

# Author and topic combination
python -m api_academic_search.search_cli "AU=(Smith J*) AND TS=(climate change)" \
    --sort-by year_desc

# Organization and topic
python -m api_academic_search.search_cli "OG=(Stanford University) AND TS=(artificial intelligence)" \
    --sort-by citations
```

---

## Combined Examples

### Example 1: Find Highly Cited Recent Papers

```bash
python -m api_academic_search.search_cli "deep learning" \
    --sort-by citations \
    --year-min 2020 \
    --max-results 10 \
    --providers "Web of Science" \
    --format markdown \
    --output highly_cited_dl.md
```

### Example 2: Search Medical Literature by Title

```bash
python -m api_academic_search.search_cli "COVID-19 vaccine" \
    --field-tag TI \
    --database MEDLINE \
    --sort-by year_desc \
    --year-min 2020 \
    --max-results 20
```

### Example 3: Find Author's Most Cited Work

```bash
python -m api_academic_search.search_cli "Smith J*" \
    --field-tag AU \
    --sort-by citations \
    --max-results 10 \
    --verbose
```

### Example 4: Institution Research Output

```bash
python -m api_academic_search.search_cli "MIT" \
    --field-tag OG \
    --sort-by citations \
    --year-min 2020 \
    --max-results 50 \
    --format csv \
    --output mit_research.csv
```

### Example 5: Topic Search with Analysis

```bash
python -m api_academic_search.search_cli "renewable energy" \
    --sort-by citations \
    --year-min 2020 \
    --max-results 30 \
    --analyze \
    --topics \
    --verbose
```

---

## Output Formats

```bash
# JSON (default)
python -m api_academic_search.search_cli "query" --format json --output results.json

# Markdown
python -m api_academic_search.search_cli "query" --format markdown --output results.md

# CSV (for Excel/spreadsheets)
python -m api_academic_search.search_cli "query" --format csv --output results.csv

# BibTeX (for LaTeX)
python -m api_academic_search.search_cli "query" --format bibtex --output results.bib

# RIS (for reference managers)
python -m api_academic_search.search_cli "query" --format ris --output results.ris
```

---

## Additional Options

### Verbose Output

```bash
python -m api_academic_search.search_cli "machine learning" \
    --verbose \
    --sort-by citations
```

Shows:

- Available sources
- Search parameters
- Total results found
- Number of articles with abstracts

### Debug Mode

```bash
python -m api_academic_search.search_cli "machine learning" \
    --debug \
    --sort-by citations
```

Enables detailed logging for troubleshooting.

### Topic Extraction

```bash
python -m api_academic_search.search_cli "machine learning" \
    --topics \
    --max-results 50
```

Extracts and displays top keywords/topics from results.

### LLM Analysis

```bash
python -m api_academic_search.search_cli "machine learning" \
    --llm \
    --llm-provider openai \
    --llm-key "your-openai-key" \
    --max-results 10
```

---

## Complete Command Reference

### All Clarivate Options

```bash
python -m api_academic_search.search_cli "QUERY" \
    --clarivate-key "API_KEY" \
    --sort-by {relevance|citations|year_desc|year_asc|newest|oldest} \
    --database {WOS|BIOABS|MEDLINE} \
    --field-tag {TS|TI|AU|OG|SO} \
    --year-min YEAR \
    --year-max YEAR \
    --max-results N \
    --providers "Web of Science" \
    --format {json|markdown|csv|bibtex|ris} \
    --output FILENAME \
    --verbose \
    --debug
```

---

## Tips & Best Practices

### 1. Finding High-Impact Papers

Always use `--sort-by citations` when looking for influential research:

```bash
python -m api_academic_search.search_cli "topic" --sort-by citations --max-results 10
```

### 2. Recent Research

Use `--year-min` with `--sort-by newest` for latest publications:

```bash
python -m api_academic_search.search_cli "topic" --year-min 2024 --sort-by newest
```

### 3. Specific Provider

Use `--providers "Web of Science"` to ensure Clarivate features are used:

```bash
python -m api_academic_search.search_cli "topic" \
    --providers "Web of Science" \
    --sort-by citations
```

### 4. Title-Only Searches

Use `--field-tag TI` for more precise results:

```bash
python -m api_academic_search.search_cli "exact phrase" --field-tag TI
```

### 5. Author Wildcards

Use `*` for partial author names:

```bash
python -m api_academic_search.search_cli "Smith J*" --field-tag AU
```

---

## Troubleshooting

### Issue: "No results found"

- Try using `TS` field tag instead of `TI` for broader search
- Check year range isn't too restrictive
- Verify API key is configured

### Issue: "Module not found"

Run from the firecrawl directory:

```bash
cd /Users/FF/Projects/myProjects/backtofuture_scraper/firecrawl
python -m api_academic_search.search_cli "query"
```

### Issue: "Rate limit exceeded"

- Add delays between searches
- Reduce `--max-results`
- Check daily quota (5000 requests/day for Starter API)

---

## Quick Reference Card

| Task                | Command                                     |
| ------------------- | ------------------------------------------- |
| Most cited papers   | `--sort-by citations`                       |
| Newest papers       | `--sort-by newest` or `--sort-by year_desc` |
| Title search        | `--field-tag TI`                            |
| Author search       | `--field-tag AU`                            |
| Organization search | `--field-tag OG`                            |
| Medical literature  | `--database MEDLINE`                        |
| Year filter         | `--year-min 2020 --year-max 2024`           |
| Save to file        | `--output filename.ext --format FORMAT`     |
| Verbose output      | `--verbose`                                 |

---

## See Also

- **Full Feature Guide**: `docs/CLARIVATE_FEATURES.md`
- **Quick Reference**: `CLARIVATE_QUICK_REFERENCE.md`
- **Integration Summary**: `CLARIVATE_INTEGRATION_SUMMARY.md`
- **Interactive Demo**: `python demo_clarivate_features.py`
