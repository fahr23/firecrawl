# Quick Start Guide - Academic Search Package

## Installation

No installation needed! Just make sure you have Python 3.7+ and `requests`:

```bash
pip install requests
```

## 5-Minute Quick Start

### 1. Basic Search (Simplest)

```python
from academic_search import create_engine

# Create engine
engine = create_engine()

# Search
results = engine.search("machine learning", max_results=10)

# Display results
for article in results.articles:
    print(f"{article.year}: {article.title}")
```

### 2. Search Recent Papers Only

```python
from academic_search import create_engine

engine = create_engine()

# Search papers from 2023-2024
results = engine.search(
    "artificial intelligence",
    max_results=20,
    year_min=2023,
    year_max=2024
)

print(f"Found {len(results.articles)} recent papers")
```

### 3. Get Abstracts

```python
from academic_search import create_engine

engine = create_engine()

# Search
results = engine.search("quantum computing", max_results=10)

# Enrich with abstracts (fast parallel processing)
results = engine.enrich_abstracts(results, parallel=True)

# Show papers with abstracts
for article in results.articles:
    if article.abstract:
        print(f"\n{article.title}")
        print(f"Abstract: {article.abstract[:200]}...")
```

### 4. Extract Topics

```python
from academic_search import create_engine

engine = create_engine()

# Search
results = engine.search("renewable energy", max_results=30)

# Extract top topics
topics = engine.extract_topics(results, top_n=10)

print("Top topics:")
for topic, score in topics:
    print(f"  - {topic}: {score}")
```

### 5. Export Results

```python
from academic_search import create_engine

engine = create_engine()

# Search
results = engine.search("deep learning", max_results=25)

# Export to different formats
engine.export(results, "results.json")       # JSON
engine.export(results, "results.md")         # Markdown
engine.export(results, "results.csv")        # CSV
engine.export(results, "references.bib")     # BibTeX
engine.export(results, "references.ris")     # RIS
```

## Command-Line Usage

### Basic Search

```bash
python -m academic_search.search_cli "machine learning"
```

### Search with Year Filter

```bash
python -m academic_search.search_cli "AI ethics" \
    --year-min 2023 --year-max 2024 \
    --max-results 50
```

### Export to File

```bash
python -m academic_search.search_cli "quantum computing" \
    -o results.md -f markdown
```

### Full-Featured Search

```bash
python -m academic_search.search_cli "renewable energy" \
    --year-min 2020 --year-max 2024 \
    --all-sources \
    --enrich \
    --topics \
    -o energy.json
```

## Complete Workflow Example

```python
from academic_search import create_engine, Config

# 1. Setup (optional: add API key)
config = Config()
config.api.elsevier_api_key = "YOUR_KEY_HERE"  # Optional
engine = create_engine(config)

# 2. Search with filters
results = engine.search(
    "transformer models NLP",
    max_results=30,
    year_min=2022,
    use_all_sources=True  # Search all databases
)

print(f"Found {len(results.articles)} articles from {results.sources}")

# 3. Enrich with abstracts
results = engine.enrich_abstracts(results, parallel=True)
print(f"{sum(1 for a in results.articles if a.abstract)} have abstracts")

# 4. Analyze topics
topics = engine.extract_topics(results, top_n=15)
print("\nTop topics:")
for topic, score in topics[:5]:
    print(f"  {topic}: {score}")

# 5. Export results
engine.export(results, "nlp_papers.json")
engine.export(results, "nlp_papers.md")
print("\n✅ Exported to JSON and Markdown")
```

## Available Search Sources

| Source | Records | API Key Required | Abstracts |
|--------|---------|------------------|-----------|
| **OpenAlex** | 250M+ | ❌ No (Free) | Good |
| **Semantic Scholar** | 200M+ | ❌ No (Free) | Excellent |
| **arXiv** | 2M+ | ❌ No (Free) | Excellent |
| **Scopus** | 80M+ | ✅ Yes | Excellent |

*Default: Uses OpenAlex (free, no key needed)*

## Common Use Cases

### Use Case 1: Literature Review

```python
engine = create_engine()

# Search your topic
results = engine.search("machine learning healthcare", max_results=50)

# Get abstracts
results = engine.enrich_abstracts(results, parallel=True)

# Export for reading
engine.export(results, "literature_review.md")
```

### Use Case 2: Find Recent Papers

```python
engine = create_engine()

# Last 2 years only
results = engine.search(
    "artificial intelligence",
    max_results=100,
    year_min=2023
)

# Export references
engine.export(results, "recent_ai_papers.bib")
```

### Use Case 3: Research Trends

```python
engine = create_engine()

# Search broad topic
results = engine.search("climate change", max_results=100)

# Extract trending topics
topics = engine.extract_topics(results, top_n=25)

print("Research trends:")
for topic, score in topics[:10]:
    print(f"  {topic}: {score}")
```

### Use Case 4: Multi-Database Search

```python
engine = create_engine()

# Search all available sources
results = engine.search(
    "quantum computing applications",
    max_results=50,
    use_all_sources=True  # Searches all 4 databases
)

# Group by source
by_source = {}
for article in results.articles:
    by_source[article.source] = by_source.get(article.source, 0) + 1

print("Results by database:")
for source, count in by_source.items():
    print(f"  {source}: {count} papers")
```

## CLI Quick Reference

```bash
# Basic
python -m academic_search.search_cli "QUERY"

# With options
python -m academic_search.search_cli "QUERY" \
    --year-min YEAR              # Minimum publication year
    --year-max YEAR              # Maximum publication year
    --max-results N              # Number of results (default: 25)
    --all-sources                # Search all databases
    --enrich                     # Fetch abstracts
    --topics                     # Extract topics
    --analyze                    # Run analysis
    -o FILE                      # Output file
    -f FORMAT                    # json|markdown|csv|bibtex|ris
    --elsevier-key KEY           # Scopus API key
    -v                           # Verbose output
```

## Tips & Best Practices

### ✅ Do's

- **Use year filters** for recent papers: `year_min=2023`
- **Enable parallel enrichment** for faster abstracts: `parallel=True`
- **Search all sources** for comprehensive results: `use_all_sources=True`
- **Export to multiple formats** for different tools
- **Extract topics** to understand research trends

### ❌ Don'ts

- Don't search too many results at once (start with 25-50)
- Don't skip abstract enrichment if you need full context
- Don't ignore year filters - they significantly narrow results
- Don't forget to export before closing Python session

## Troubleshooting

### Issue: "No results found"

**Solution:** Try:
- Broaden your search query
- Remove year filters
- Use `use_all_sources=True`
- Check internet connection

### Issue: "Few abstracts returned"

**Solution:**
- Use `engine.enrich_abstracts(results, parallel=True)`
- Some papers don't have abstracts in any database
- Try different search sources

### Issue: "Scopus authentication failed"

**Solution:**
- This is normal if no API key is configured
- System automatically falls back to OpenAlex (free)
- Get key from: https://dev.elsevier.com/

## Next Steps

1. **Run examples:**
   ```bash
   python examples_usage.py
   ```

2. **Read full documentation:**
   - [Project Report](ACADEMIC_SEARCH_PROJECT_REPORT.md)
   - [Package README](academic_search/README.md)

3. **Explore advanced features:**
   - Custom search providers
   - LLM-powered analysis
   - Citation network analysis

## Need Help?

- Check [examples_usage.py](examples_usage.py) for 10 detailed examples
- Review [academic_search/README.md](academic_search/README.md) for API details
- See [ACADEMIC_SEARCH_PROJECT_REPORT.md](ACADEMIC_SEARCH_PROJECT_REPORT.md) for comprehensive documentation

---

**Happy researching! 🔬📚**
