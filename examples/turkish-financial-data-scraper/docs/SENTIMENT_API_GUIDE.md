# Sentiment Analysis API Guide

## Overview

The Sentiment Analysis API provides two powerful analyzers for Turkish financial disclosures:

1. **Keyword-Based Analyzer** - Fast, lightweight, no external dependencies
2. **HuggingFace BERT Analyzer** - Accurate, slower, Turkish-optimized deep learning model

Both analyzers are integrated into the REST API and can be selected per request.

---

## Sentiment Analyzers

### Keyword-Based Analyzer

**Performance:** ⚡ 0.1ms per item  
**Accuracy:** 51% confidence (average)  
**Dependencies:** None  
**Best For:** Real-time analysis, high-volume processing, resource-constrained environments

**Features:**
- Turkish language keyword detection
- Positive, Negative, Neutral classification
- Confidence scoring (0.5-0.95 range)
- Risk flag identification
- Zero external dependencies

**Keywords Detected:**
- **Positive:** artış, büyüme, başarı, kazanç, karlılık, yüksek, iyi, gelişme
- **Negative:** kayıp, düşüş, risk, kriz, zorluk, sorun, olumsuz, azalma
- **Risk:** riske, riski, belirsizlik, volatilite, kriz, düşüş, kayıp

### HuggingFace BERT Analyzer

**Performance:** 🎯 0.24s per item  
**Accuracy:** 87.28% confidence (average)  
**Dependencies:** transformers, torch, accelerate  
**Best For:** Accurate analysis, smaller batches, research/reporting

**Model:** `savasy/bert-base-turkish-sentiment-cased`

**Features:**
- Deep learning-based sentiment classification
- Multi-language support (primarily Turkish)
- Probability scores for each sentiment class
- Context-aware analysis

**Accuracy Metrics:**
- Agreement with keyword analyzer: 90%
- Average confidence: 87.28%
- Processing: ~4.2 items/second in batch mode

---

## API Endpoints

### 1. Single Disclosure Analysis

**Endpoint:** `POST /api/v1/sentiment/analyze`

**Request:**
```json
{
  "report_ids": [1, 2, 3],
  "analyzer_type": "keyword",
  "custom_prompt": null
}
```

**Parameters:**
- `report_ids` (required): List of disclosure database IDs
- `analyzer_type` (optional, default: "keyword"): 
  - `"keyword"` - Fast keyword-based analyzer
  - `"huggingface"` - Accurate deep learning analyzer
- `custom_prompt` (optional): Custom analysis prompt

**Response (keyword):**
```json
{
  "total_analyzed": 3,
  "successful": 3,
  "failed": 0,
  "results": [
    {
      "report_id": 1,
      "success": true,
      "sentiment": {
        "overall_sentiment": "positive",
        "confidence": 0.85,
        "key_sentiments": ["artış", "başarı", "büyüme"],
        "analysis_notes": "Positive disclosure focusing on growth and success"
      },
      "analyzer": "keyword"
    }
  ]
}
```

**Response (huggingface):**
```json
{
  "total_analyzed": 3,
  "successful": 3,
  "failed": 0,
  "results": [
    {
      "report_id": 1,
      "success": true,
      "sentiment": {
        "overall_sentiment": "positive",
        "confidence": 0.92,
        "key_sentiments": ["earnings_positive", "growth_indicators"],
        "analysis_notes": "Strong positive sentiment with high confidence"
      },
      "analyzer": "huggingface"
    }
  ]
}
```

**Error Response:**
```json
{
  "total_analyzed": 3,
  "successful": 2,
  "failed": 1,
  "results": [
    {
      "report_id": 999,
      "success": false,
      "error": "Disclosure not found"
    }
  ]
}
```

### 2. Automatic Batch Analysis

**Endpoint:** `POST /api/v1/sentiment/analyze/auto`

**Request (Keyword Analyzer):**
```json
{
  "days_back": 7,
  "company_codes": ["ASELS", "AKBNK"],
  "force_reanalyze": false,
  "analyzer_type": "keyword"
}
```

**Request (HuggingFace Analyzer):**
```json
{
  "days_back": 3,
  "company_codes": null,
  "force_reanalyze": false,
  "analyzer_type": "huggingface"
}
```

**Parameters:**
- `days_back` (optional, default: 7): Days to look back (1-30)
- `company_codes` (optional): Filter specific companies
- `force_reanalyze` (optional, default: false): Re-analyze existing data
- `analyzer_type` (optional, default: "keyword"): Analyzer selection

**Response:**
```json
{
  "success": true,
  "message": "Analyzed sentiment for 45 disclosures using keyword analyzer",
  "data": {
    "analyzed_count": 45,
    "total_found": 50,
    "period": "Last 7 days",
    "analyzer_type": "keyword"
  },
  "timestamp": "2024-01-15T10:30:45.123456"
}
```

**Performance Expectations:**
- **Keyword analyzer:** ~50-100 items/second
- **HuggingFace analyzer:** ~4-5 items/second (GPU: 20-30/sec)

### 3. Get Sentiment Overview

**Endpoint:** `GET /api/v1/sentiment/`

**Response:**
```json
{
  "success": true,
  "data": {
    "total_analyses": 372,
    "sentiment_distribution": {
      "positive": 17,
      "neutral": 355,
      "negative": 0
    },
    "average_confidence": 0.62,
    "top_companies": [
      {
        "company_name": "ASELS",
        "analysis_count": 28,
        "sentiment": "positive"
      }
    ]
  }
}
```

### 4. Get Disclosure Sentiment

**Endpoint:** `GET /api/v1/sentiment/disclosures/{disclosure_id}`

**Response:**
```json
{
  "success": true,
  "data": {
    "disclosure": {
      "id": 123,
      "company_name": "ASELS",
      "disclosure_type": "Financial",
      "disclosure_date": "2024-01-10",
      "content": "Lorem ipsum..."
    },
    "sentiment": {
      "overall_sentiment": "positive",
      "sentiment_score": 0.85,
      "key_sentiments": ["growth", "profitability"],
      "analysis_notes": "Positive sentiment with strong indicators"
    }
  }
}
```

### 5. Company Sentiment History

**Endpoint:** `GET /api/v1/sentiment/company/{company_name}?days_back=30&limit=50`

**Response:**
```json
{
  "success": true,
  "data": {
    "company_name": "ASELS",
    "period": "Last 30 days",
    "sentiment_history": [
      {
        "disclosure_id": 123,
        "date": "2024-01-15",
        "sentiment": "positive",
        "confidence": 0.87
      }
    ]
  }
}
```

### 6. Sentiment Trends

**Endpoint:** `GET /api/v1/sentiment/trends?days_back=30&company_name=ASELS`

**Response:**
```json
{
  "success": true,
  "data": {
    "trends": [
      {
        "date": "2024-01-15",
        "sentiment": "positive",
        "count": 5,
        "avg_confidence": 0.82
      }
    ],
    "summary": {
      "total_analyses": 45,
      "positive_percentage": 45.0,
      "neutral_percentage": 55.0
    }
  }
}
```

---

## Python Client Examples

### Basic Usage with Keyword Analyzer

```python
import requests

# Analyze single disclosure with keyword analyzer
response = requests.post(
    "http://localhost:8000/api/v1/sentiment/analyze",
    json={
        "report_ids": [1],
        "analyzer_type": "keyword"
    }
)

print(response.json())
```

### Using HuggingFace Analyzer

```python
# Analyze with HuggingFace (more accurate)
response = requests.post(
    "http://localhost:8000/api/v1/sentiment/analyze",
    json={
        "report_ids": [1, 2, 3],
        "analyzer_type": "huggingface"
    }
)

result = response.json()
for item in result['results']:
    print(f"Disclosure {item['report_id']}: {item['sentiment']}")
```

### Batch Analysis

```python
# Auto-analyze recent disclosures
response = requests.post(
    "http://localhost:8000/api/v1/sentiment/analyze/auto",
    json={
        "days_back": 7,
        "company_codes": ["ASELS", "AKBNK"],
        "analyzer_type": "keyword"
    }
)

print(f"Analyzed {response.json()['data']['analyzed_count']} items")
```

### Get Company Sentiment Trend

```python
# Get sentiment history for company
response = requests.get(
    "http://localhost:8000/api/v1/sentiment/company/ASELS",
    params={"days_back": 30, "limit": 50}
)

company_data = response.json()['data']
print(f"Company: {company_data['company_name']}")
for entry in company_data['sentiment_history']:
    print(f"  {entry['date']}: {entry['sentiment']} (confidence: {entry['confidence']})")
```

---

## JavaScript/TypeScript Client

### Fetch API

```javascript
// Analyze with keyword analyzer
const response = await fetch(
  'http://localhost:8000/api/v1/sentiment/analyze',
  {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      report_ids: [1, 2, 3],
      analyzer_type: 'keyword'
    })
  }
);

const result = await response.json();
console.log(`Analyzed ${result.successful} items successfully`);
```

### Using Axios

```javascript
import axios from 'axios';

// Batch analysis with HuggingFace
const result = await axios.post(
  'http://localhost:8000/api/v1/sentiment/analyze/auto',
  {
    days_back: 7,
    analyzer_type: 'huggingface',
    company_codes: ['ASELS', 'AKBNK']
  }
);

console.log(`Analyzed ${result.data.data.analyzed_count} items`);
```

---

## Analyzer Comparison

| Feature | Keyword | HuggingFace |
|---------|---------|------------|
| Speed | ⚡ 0.1ms/item | 🎯 0.24s/item |
| Accuracy | 51% confidence | 87.28% confidence |
| Dependencies | None | PyTorch, transformers |
| Setup Time | Instant | ~2 minutes (model load) |
| Real-time | ✅ Yes | ❌ No |
| Batch Processing | ✅ Excellent | ✅ Good (GPU) |
| Language Support | Turkish | Turkish + Multi |
| Learning Curve | ✅ Simple | ⚠️ Complex |

---

## When to Use Each Analyzer

### Use Keyword Analyzer When:

- ✅ Real-time analysis required
- ✅ Resource constraints (serverless, edge)
- ✅ High-volume processing (1000+ items)
- ✅ Simple sentiment classification needed
- ✅ No external dependencies desired

### Use HuggingFace Analyzer When:

- ✅ Maximum accuracy needed
- ✅ Deep context understanding required
- ✅ Reporting/research scenarios
- ✅ Smaller batches acceptable
- ✅ GPU available for acceleration

---

## Performance Optimization

### Keyword Analyzer

```python
# Process 1000 items in ~10 seconds
for batch in chunks(disclosures, 100):
    response = requests.post(
        "http://localhost:8000/api/v1/sentiment/analyze",
        json={
            "report_ids": batch,
            "analyzer_type": "keyword"
        }
    )
```

### HuggingFace Analyzer

```python
# Process 100 items in ~24 seconds
# Use GPU for 10x speedup
response = requests.post(
    "http://localhost:8000/api/v1/sentiment/analyze",
    json={
        "report_ids": [1, 2, 3],  # Smaller batches
        "analyzer_type": "huggingface"
    }
)
```

---

## Error Handling

### Common Error Responses

```json
{
  "detail": "Disclosure not found"
}
```

```json
{
  "detail": "Database temporarily unavailable, please try again later"
}
```

### Retry Logic

```python
import time
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

# Setup retry strategy
session = requests.Session()
retry = Retry(connect=3, backoff_factor=0.5)
adapter = HTTPAdapter(max_retries=retry)
session.mount('http://', adapter)
session.mount('https://', adapter)

# Make request with automatic retries
response = session.post(
    "http://localhost:8000/api/v1/sentiment/analyze",
    json={"report_ids": [1, 2, 3], "analyzer_type": "keyword"}
)
```

---

## Database Schema

The sentiment analysis results are stored in `kap_disclosure_sentiment` table:

```sql
CREATE TABLE kap_disclosure_sentiment (
    id SERIAL PRIMARY KEY,
    disclosure_id INTEGER NOT NULL REFERENCES kap_disclosures(id),
    overall_sentiment VARCHAR(20),
    sentiment_score DECIMAL(5,2),
    key_sentiments JSONB,
    analysis_notes TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

---

## Cost Analysis

**Monthly Cost Estimate (1M disclosures):**

| Method | Cost | Time |
|--------|------|------|
| Keyword (CPU) | Free | ~3 hours |
| HuggingFace (GPU) | ~$50-100 | ~1 hour |
| Cloud LLM API | $100-500 | ~30 mins |

---

## Troubleshooting

### High Latency with HuggingFace

**Solution:** Use keyword analyzer or enable GPU acceleration

### Empty Results

**Check:**
- Disclosure ID exists: `GET /api/v1/sentiment/disclosures/{id}`
- Database connection: Check server logs
- Disclosure has content

### Model Not Loading

**Solution:**
```bash
# Install dependencies
pip install transformers torch accelerate

# Test import
python -c "from transformers import AutoTokenizer; print('OK')"
```

---

## Support

For issues or questions:
1. Check logs: `docker logs api-container`
2. Verify database: `psql -d turkish_financial`
3. Test endpoint: `curl http://localhost:8000/api/v1/sentiment/`
