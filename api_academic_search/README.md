# Academic Literature Search Package

A modular, extensible Python package for searching academic literature across multiple databases with support for abstract enrichment, topic extraction, and LLM-based analysis.

## Features

- 🔍 **Multi-Source Search**: Search OpenAlex, Semantic Scholar, ArXiv, ScienceDirect, and Scopus
- 📝 **Abstract Enrichment**: Fetch missing abstracts from CrossRef, Semantic Scholar
- 🏷️ **Topic Extraction**: Automatic keyword and topic extraction
- 🤖 **LLM Analysis Ready**: Extension point for AI-powered abstract analysis
- 📤 **Multiple Export Formats**: JSON, Markdown, CSV, BibTeX, RIS
- 🔧 **Extensible Architecture**: Easy to add new sources, analyzers, exporters

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

engine = AcademicSearchEngine(config)
results = engine.search("quantum computing")
```

## CLI Usage

```bash
# Basic search
python -m academic_search.search_cli "machine learning" --max-results 25

# Export to file
python -m academic_search.search_cli "climate change" -o results.md -f markdown

# With analysis
python -m academic_search.search_cli "neural networks" --analyze --topics

# Search all sources
python -m academic_search.search_cli "renewable energy" --all-sources --enrich

# With API key
python -m academic_search.search_cli "batteries" --elsevier-key YOUR_KEY
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
