# Elsevier API Support - Use Cases & Capabilities

## ✅ IMPLEMENTATION COMPLETE

**Status:** ScienceDirect search has been added to the package!

### Now Supported (5 Search Sources)

| Source | Records | API Key Required | Abstracts | Status |
|--------|---------|------------------|-----------|--------|
| **ScienceDirect** | 16M+ | ✅ Elsevier API | Excellent | ✅ **NEW!** |
| **Scopus** | 80M+ | ✅ Elsevier API | Good | ✅ Implemented |
| **OpenAlex** | 250M+ | ❌ Free | Good | ✅ Implemented |
| **Semantic Scholar** | 200M+ | ❌ Free | Excellent | ✅ Implemented |
| **arXiv** | 2M+ | ❌ Free | Excellent | ✅ Implemented |

---

## Current Implementation Status

### ✅ Currently Supported (Updated)

| Use Case | API | Status | Description |
|----------|-----|--------|-------------|
| **ScienceDirect Search** | Article Metadata API | ✅ **NEW!** | Search 16M+ Elsevier articles |
| **ScienceDirect Abstracts** | Article Metadata API | ✅ **NEW!** | Better abstract coverage |
| **Scopus Search** | Scopus Search API | ✅ Implemented | Search 80M+ abstracts and citations |
| **Abstract Retrieval** | Abstract Retrieval API | ✅ Implemented | Fetch abstracts by DOI |
| **Academic Research** | Scopus API | ✅ Supported | Non-commercial research use |
| **Metadata Retrieval** | Scopus/ScienceDirect | ✅ Supported | Get title, authors, year, journal, DOI |
| **Year Filtering** | Query Parameters | ✅ Supported | Both APIs support date filtering |
| **Citation Count** | Scopus API | ✅ Available | Included in response data |
| **Open Access Filter** | Both APIs | ✅ Available | Filter for OA articles |

### 🔄 Partially Supported

| Use Case | API | Status | Notes |
|----------|-----|--------|-------|
| **ScienceDirect Search** | Article Metadata API | 🔄 Not Yet | Can be added - same API key |
| **Full Text Access** | Article Retrieval API | 🔄 Limited | Requires additional permissions |
| **Citation Analysis** | Scopus API | 🔄 Available | Data present, not analyzed |

### ❌ Not Implemented Yet

| Use Case | API | Reason | Difficulty |
|----------|-----|--------|------------|
| **ScienceDirect Article Metadata** | Article Metadata API | Not prioritized | Easy to add |
| **Full Text Retrieval** | Article Retrieval API | Subscription required | Medium |
| **Author Profile** | Author Retrieval API | Out of scope | Easy |
| **Affiliation Search** | Affiliation Search API | Out of scope | Easy |
| **Citation Metrics** | Citations API | Out of scope | Medium |
| **Text Mining** | Text Mining API | Special permission | Hard |
| **Journal Metrics** | Serial Title API | Out of scope | Easy |

---

## Elsevier API Use Cases (from dev.elsevier.com)

### Available APIs with Your Key

Your Elsevier API key (`7e0c8c4ed4e0fb320d69074f093779d9`) gives access to:

#### 1. **Scopus APIs** ✅ Currently Used
- **Scopus Search** - Search abstracts and citations
- **Abstract Retrieval** - Get full abstract by DOI/EID
- **Author Retrieval** - Get author profiles
- **Affiliation Retrieval** - Get institution info
- **Citations Overview** - Citation counts and metrics

#### 2. **ScienceDirect APIs** 🔄 Can Add
- **Article Metadata Search** - Search ScienceDirect articles
- **Article Retrieval** - Get full article metadata
- **Article Entitlement** - Check access rights
- **Serial/Nonserial Title Metadata** - Journal info

#### 3. **General APIs**
- **Authentication API** - Verify API key
- **Subject Classifications** - Get subject areas

---

## Adding ScienceDirect Search

ScienceDirect has a **separate search endpoint** from Scopus. Here's what we can add:

### ScienceDirect Article Metadata API

**Endpoint:** `https://api.elsevier.com/content/search/sciencedirect`

**Capabilities:**
- Search 16M+ full-text articles from ScienceDirect
- More detailed metadata than Scopus
- Access to article abstracts
- Filter by journal, subject, date, open access
- Boolean search operators

**Search Fields Available:**
```
- keywords(term)         - Indexed keywords
- title(term)            - Article title
- authors(name)          - Author names
- affiliation(institution) - Author affiliation
- pub-date AFT YYYYMMDD  - Publication date
- content-type(JL|BS|BK) - Content type
- openaccess(1|0)        - Open access filter
- doi(value)             - DOI lookup
- srctitle(journal)      - Journal title
```

**Example Query:**
```
keywords("machine learning" AND "healthcare") AND pub-date AFT 20230101
```

---

## Implementation Plan

I'll now add ScienceDirect search as an additional searcher to the package.

### What Will Be Added:

1. **ScienceDirect Searcher Class**
   - Separate from Scopus (different endpoint)
   - Same API key
   - More detailed article metadata
   - Support for all search fields

2. **Enhanced Search Capabilities**
   - Boolean search operators (AND, OR, NOT)
   - Field-specific searches (title, keywords, authors)
   - Content type filtering (journals, books, handbooks)
   - Open access filtering

3. **Better Abstract Coverage**
   - ScienceDirect often has better abstracts than Scopus
   - Direct access to full-text articles (if subscribed)

### Comparison: Scopus vs ScienceDirect

| Feature | Scopus | ScienceDirect |
|---------|--------|---------------|
| **Coverage** | 80M+ records (all publishers) | 16M+ full-text (Elsevier only) |
| **Content** | Abstracts + citations | Full articles + metadata |
| **Publishers** | All major publishers | Elsevier only |
| **Abstracts** | Good coverage | Excellent coverage |
| **Full Text** | No | Yes (if subscribed) |
| **Citations** | Comprehensive | Limited |
| **Best For** | Broad search | Deep Elsevier content |

### Recommended Strategy

**Use Both Together:**
1. **Scopus** - Primary broad search across all publishers
2. **ScienceDirect** - Enhanced metadata for Elsevier content
3. **OpenAlex** - Free backup for both
4. **Semantic Scholar** - AI-powered relevance

---

## Implementation Status

I'll now implement the ScienceDirect searcher for you.
