# Clarivate Web of Science Starter API - Advanced Features Guide

## Overview

The `ClarivateSearcher` class provides comprehensive access to the Web of Science Starter API with advanced search capabilities, sorting options, and metadata extraction.

## API Endpoints Used

### 1. GET `/documents` - Search Documents

Primary endpoint for searching the Web of Science database.

### 2. GET `/documents/{uid}` - Get Document by UID

Retrieve specific document by Web of Science Accession Number.

### 3. GET `/journals` - Search Journals (Available but not yet implemented)

Search for journals by ISSN.

### 4. GET `/journals/{id}` - Get Journal by ID (Available but not yet implemented)

Retrieve specific journal metadata.

---

## Field Tags for Advanced Queries

The Web of Science API supports field-specific searches using tags:

| Tag  | Field                                  | Example                    |
| ---- | -------------------------------------- | -------------------------- |
| `TS` | Topic (Title, Abstract, Keywords)      | `TS=(machine learning)`    |
| `TI` | Title only                             | `TI=(climate change)`      |
| `AU` | Author name                            | `AU=(Einstein A*)`         |
| `AI` | Author Identifier (ORCID/ResearcherID) | `AI=(0000-0001-2345-6789)` |
| `OG` | Organization-Enhanced                  | `OG=(MIT)`                 |
| `DO` | Digital Object Identifier              | `DO=(10.1038/nature12345)` |
| `PY` | Publication Year                       | `PY=(2020-2024)`           |
| `SO` | Source (Journal) Title                 | `SO=(Nature)`              |

### Boolean Operators

- `AND` - Both terms must be present
- `OR` - Either term must be present
- `NOT` - Exclude term
- `NEAR/n` - Terms within n words of each other
- `SAME` - Terms in the same sentence

### Example Queries

```python
# Topic search (default if no tag specified)
"machine learning"  # Automatically becomes: TS=(machine learning)

# Title-only search
"TI=(deep learning)"

# Author search with wildcard
"AU=(Smith J*)"

# Complex boolean query
"TS=(machine learning OR deep learning) AND TS=(healthcare)"

# Organization + topic
"OG=(Stanford University) AND TS=(artificial intelligence)"

# Year range
"TS=(quantum computing) AND PY=(2020-2024)"
```

---

## Sorting Options

Control result ordering with the `sort_by` parameter:

| Option       | Description               | API Value |
| ------------ | ------------------------- | --------- |
| `relevance`  | Relevance score (default) | `RS`      |
| `citations`  | Most cited first          | `TC+D`    |
| `most_cited` | Alias for citations       | `TC+D`    |
| `year_desc`  | Newest first              | `PY+D`    |
| `newest`     | Alias for year_desc       | `PY+D`    |
| `year_asc`   | Oldest first              | `PY+A`    |
| `oldest`     | Alias for year_asc        | `PY+A`    |

---

## Database Selection

Search specific databases with the `database` parameter:

- `WOS` - Web of Science Core Collection (default)
- `BIOABS` - Biological Abstracts
- `MEDLINE` - MEDLINE database

---

## Detail Levels

Control metadata richness with the `detail` parameter:

- `full` - Complete metadata including author keywords, identifiers (default)
- `short` - Basic metadata only

---

## Enhanced Metadata Extraction

The enhanced parser extracts:

### Basic Fields

- Title
- Authors (with display names)
- Journal/Source
- Publication year
- DOI

### Advanced Fields

- **Citation Count** - Times cited in Web of Science
- **Author Identifiers** - ResearcherID and ORCID
- **Volume, Issue, Pages** - Complete citation information
- **PMID** - PubMed ID (when available)
- **ISSN/eISSN** - Journal identifiers
- **Author Keywords** - In full detail mode
- **WoS Record Link** - Direct link to full record

---

## Usage Examples

### 1. Basic Search

```python
from api_academic_search import create_engine

engine = create_engine()
result = engine.search("machine learning", max_results=10, providers=["Web of Science"])

for article in result.articles:
    print(f"{article.title} - Citations: {article.citation_count}")
```

### 2. Highly Cited Papers

```python
from api_academic_search.providers import ClarivateSearcher
from api_academic_search.config import Config

searcher = ClarivateSearcher(Config())
result = searcher.search_highly_cited("deep learning", min_year=2020, max_results=10)
```

### 3. Author Search

```python
searcher = ClarivateSearcher(Config())
result = searcher.search_by_author("Einstein A*", max_results=10, sort_by="citations")
```

### 4. Organization Search

```python
result = searcher.search_by_organization("MIT", max_results=10, sort_by="citations")
```

### 5. Advanced Query with Custom Parameters

```python
result = searcher.search(
    query="TS=(climate change) AND TS=(machine learning)",
    max_results=20,
    year_min=2020,
    year_max=2024,
    sort_by="citations",
    database="WOS",
    detail="full"
)
```

### 6. Get Specific Document by UID

```python
article = searcher.get_document_by_uid("WOS:000123456789012", detail="full")
```

### 7. Title-Only Search

```python
result = searcher.search(
    query="TI=(renewable energy)",
    max_results=10,
    sort_by="year_desc"
)
```

### 8. Search Specific Database

```python
result = searcher.search(
    query="cancer treatment",
    max_results=10,
    database="MEDLINE",
    sort_by="year_desc"
)
```

---

## Convenience Methods

### `search_by_author(author_name, max_results, sort_by)`

Search for papers by author name (uses `AU=` tag).

### `search_by_organization(org_name, max_results, sort_by)`

Search for papers by institution (uses `OG=` tag).

### `search_highly_cited(topic, min_year, max_results)`

Find highly cited papers on a topic (sorted by citations descending).

### `get_document_by_uid(uid, detail)`

Retrieve a specific document by its Web of Science UID.

---

## Rate Limiting

The implementation includes automatic rate limiting:

- 200ms delay between pagination requests
- Respects API rate limits (5 requests/second, 5000/day for Starter API)

---

## API Limitations (Starter API)

1. **No Abstracts** - Starter API does not include article abstracts
2. **Limited to 50 results per page** - Pagination required for larger result sets
3. **Basic Metadata** - Some advanced features require full WoS subscription
4. **Rate Limits** - 5 requests/second, 5000 requests/day

---

## Future Enhancements

Potential additions based on available endpoints:

1. **Journal Metadata Integration**
   - Use `/journals` endpoint to enrich results with journal rankings
   - Add JCR (Journal Citation Reports) data

2. **Cited References**
   - Extract cited references from full records
   - Build citation networks

3. **Related Records**
   - Use WoS "related records" links for recommendation

4. **Author Disambiguation**
   - Leverage ResearcherID and ORCID for precise author tracking

5. **Time-Based Filtering**
   - Use `modifiedTimeSpan` for delta syncing
   - Track citation count changes over time

---

## Configuration

Add to your `.env` file or set environment variable:

```bash
CLARIVATE_API_KEY=your_api_key_here
```

Or configure programmatically:

```python
from api_academic_search import create_engine

engine = create_engine(clarivate_api_key="your_api_key_here")
```

---

## Error Handling

The implementation handles:

- Authentication failures (401/403)
- Rate limiting (429)
- Invalid queries (400)
- Network timeouts
- Malformed responses

All errors are logged and gracefully handled, returning empty results rather than crashing.

---

## Performance Tips

1. **Use Specific Field Tags** - `TI=` searches are faster than `TS=`
2. **Limit Result Sets** - Request only what you need
3. **Enable Pagination** - For large result sets, process in batches
4. **Use Short Detail Level** - When full metadata isn't needed
5. **Cache Results** - Store frequently accessed documents locally

---

## Integration with Academic Search Engine

The `ClarivateSearcher` is automatically integrated into the main `AcademicSearchEngine`:

```python
from api_academic_search import create_engine

# Clarivate is automatically included if API key is configured
engine = create_engine()

# Search across all sources including WoS
result = engine.search("machine learning", max_results=50, use_all_sources=True)

# Search only WoS
result = engine.search("machine learning", max_results=50, providers=["Web of Science"])
```

---

## References

- [Clarivate Developer Portal](https://developer.clarivate.com/)
- [WoS Starter API Documentation](https://developer.clarivate.com/apis/wos-starter)
- [Swagger UI](https://api.clarivate.com/swagger-ui/)
- [Web of Science Query Language Guide](https://webofscience.help.clarivate.com/en-us/Content/advanced-search.html)
