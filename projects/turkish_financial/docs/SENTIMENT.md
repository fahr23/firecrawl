# Sentiment Analysis Guide

## Overview

Two analyzers are available for Turkish financial disclosures. Choose based on your speed vs. accuracy needs:

| | Keyword-Based | HuggingFace BERT |
|--|--|--|
| **Speed** | 0.1ms/item | 0.24s/item |
| **Accuracy** | ~51% confidence | ~87% confidence |
| **Dependencies** | None | `transformers`, `torch` |
| **Best for** | Real-time, high-volume | Batch, research/reporting |

---

## Analyzers

### Keyword-Based (default)

Detects Turkish financial keywords:

- **Positive:** artış, büyüme, başarı, kazanç, karlılık, yüksek, iyi, gelişme
- **Negative:** kayıp, düşüş, risk, kriz, zorluk, sorun, olumsuz, azalma
- **Risk:** riske, riski, belirsizlik, volatilite, kriz, düşüş, kayıp

### HuggingFace BERT

Model: `savasy/bert-base-turkish-sentiment-cased` — 442MB, GPU optional.

**Install:**
```bash
pip install transformers torch
```

**Enable via env var:**
```bash
export SENTIMENT_PROVIDER=huggingface
```

**Or inject directly:**
```python
from utils.llm_analyzer import HuggingFaceLocalProvider, LLMAnalyzer
from scrapers.kap_scraper import KAPScraper

provider = HuggingFaceLocalProvider(model_name="savasy/bert-base-turkish-sentiment-cased")
analyzer = LLMAnalyzer(provider)
scraper = KAPScraper()
scraper.llm_analyzer = analyzer
```

**Alternative Turkish models:**
```python
models = [
    "savasy/bert-base-turkish-sentiment-cased",  # Default (recommended)
    "dbmdz/bert-base-turkish-cased",             # Generic Turkish BERT
    "bert-base-multilingual-cased",              # Multilingual fallback
]
```

---

## API Endpoints

Full API documentation in [API_REFERENCE.md](API_REFERENCE.md). Key endpoints:

```bash
# Analyze specific disclosures
POST /api/v1/sentiment/analyze
{ "report_ids": [1, 2, 3], "analyzer_type": "keyword" }

# Auto-analyze recent disclosures
POST /api/v1/sentiment/analyze/auto
{ "days_back": 7, "analyzer_type": "huggingface" }

# Get statistics
GET /api/v1/sentiment/

# Company sentiment history
GET /api/v1/sentiment/company/{name}

# Sentiment trends
GET /api/v1/sentiment/trends
```

### Response shape

```json
{
  "total_analyzed": 3,
  "successful": 3,
  "failed": 0,
  "results": [
    {
      "report_id": 1,
      "success": true,
      "analyzer": "keyword",
      "sentiment": {
        "overall_sentiment": "positive",
        "confidence": 0.85,
        "impact_horizon": "medium_term",
        "key_drivers": ["Revenue growth of 15%", "Strong market position"],
        "risk_flags": [],
        "tone_descriptors": ["optimistic", "confident"],
        "target_audience": "retail_investors",
        "analysis_text": "Detaylı analiz metni..."
      }
    }
  ]
}
```

---

## PDF Content Analysis

Since 2026-01-28, sentiment analysis reads full PDF document content (10,000+ chars) rather than the brief HTML summary (~100-500 chars). This significantly improves accuracy for financial statements.

How it works:
1. KAP disclosure is fetched with its `disclosureIndex`
2. PDF is downloaded from `https://www.kap.org.tr/tr/BildirimPdf/{disclosureIndex}`
3. Text is extracted from the PDF
4. Extracted text (up to 4000 chars) is sent to the analyzer

---

## Cost Optimization (LLM-based analysis)

These optimizations reduce LLM API costs by ~75-80%:

### Model choice
```python
# Gemini 1.5 Flash is 60-70% cheaper than 2.5 Flash with comparable quality for Turkish
model = "gemini-1.5-flash"
temperature = 0.3   # Lower = shorter, more deterministic responses
```

### Smart content filtering
```python
# Skip LLM for minimal or boilerplate content
if len(content) < 20:
    return keyword_analysis()

boilerplate = ['genel kurul toplantısı', 'yönetim kurulu kararı']
if any(b in content.lower() for b in boilerplate):
    return keyword_analysis()

# Truncate long inputs
content = content[:800]
```

### Response caching
```python
# Cache by content hash to avoid re-analyzing identical disclosures
cache_key = get_content_hash(content, company_name, disclosure_type)
if cache_key in sentiment_cache:
    return sentiment_cache[cache_key]
```

### Concise prompts
```python
# Keep prompts under 100 chars, limit outputs
custom_prompt = """Türk finansal uzmanı olarak analiz yap.
JSON döndür: {sentiment, confidence, drivers...}
Kriterler: piyasa etkisi, risk/fırsat."""
```

**Result:** ~75-80% cost reduction, 40% faster, 30-40% cache hit rate.

### Free tier strategy

- Gemini 1.5 Flash: 15 calls/minute free tier
- Use keyword analysis for off-hours/routine disclosures
- Queue LLM analysis for business hours only
- Cache results in Redis for multi-instance deployments

---

## Production Deployment Patterns

### Speed-critical (real-time)
```python
from scrapers.kap_scraper import KAPScraper
scraper = KAPScraper()  # Uses keyword analyzer by default
```

### Accuracy-critical (batch)
```python
import os
os.environ['SENTIMENT_PROVIDER'] = 'huggingface'
from scrapers.kap_scraper import KAPScraper
scraper = KAPScraper(use_llm=True)
```

### Hybrid (recommended for production)
```python
from utils.llm_analyzer import HuggingFaceLocalProvider, LLMAnalyzer
from scrapers.kap_scraper import KAPScraper

try:
    provider = HuggingFaceLocalProvider()
    scraper = KAPScraper()
    scraper.llm_analyzer = LLMAnalyzer(provider)
except Exception:
    scraper = KAPScraper()  # fallback to keyword
```

---

## Monitoring

```bash
# Check which analyzer is active
grep -i "huggingface\|transformers\|bert\|keyword" scraper.log

# Sentiment distribution in DB
psql -h nuq-postgres -U postgres -d postgres -c "
SET search_path TO turkish_financial,public;
SELECT overall_sentiment, COUNT(*) FROM kap_disclosure_sentiment GROUP BY overall_sentiment;"

# Track processing time
LOG_LEVEL=DEBUG python3 production_kap_final.py 2>&1 | grep "sentiment\|Analyzing"
```

---

## Troubleshooting

| Issue | Fix |
|-------|-----|
| Model not downloading | `python3 -c "from transformers import AutoTokenizer; AutoTokenizer.from_pretrained('savasy/bert-base-turkish-sentiment-cased')"` |
| Out of memory | Use CPU-only mode or switch to keyword analyzer |
| Slow processing | Enable GPU or use keyword analyzer for real-time |
| Low confidence scores | Normal for conservative model; check `key_drivers` for context |
