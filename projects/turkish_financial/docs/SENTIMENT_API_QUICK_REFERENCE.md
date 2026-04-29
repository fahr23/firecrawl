# Sentiment Analysis API - Quick Reference

## 📊 Endpoints Summary

| Method | Endpoint | Purpose |
|--------|----------|---------|
| POST | `/api/v1/sentiment/analyze` | Analyze specific disclosures |
| POST | `/api/v1/sentiment/analyze/auto` | Auto-analyze recent disclosures |
| GET | `/api/v1/sentiment/` | Overall statistics |
| GET | `/api/v1/sentiment/disclosures/{id}` | Single disclosure sentiment |
| GET | `/api/v1/sentiment/company/{name}` | Company sentiment history |
| GET | `/api/v1/sentiment/trends` | Sentiment trends |

---

## ⚡ Quick Examples

### Analyze 3 Disclosures (Keyword)

```bash
curl -X POST http://localhost:8000/api/v1/sentiment/analyze \
  -H "Content-Type: application/json" \
  -d '{
    "report_ids": [1, 2, 3],
    "analyzer_type": "keyword"
  }'
```

### Analyze with HuggingFace (Accurate)

```bash
curl -X POST http://localhost:8000/api/v1/sentiment/analyze \
  -H "Content-Type: application/json" \
  -d '{
    "report_ids": [1, 2, 3],
    "analyzer_type": "huggingface"
  }'
```

### Auto-Analyze Last 7 Days

```bash
curl -X POST http://localhost:8000/api/v1/sentiment/analyze/auto \
  -H "Content-Type: application/json" \
  -d '{
    "days_back": 7,
    "analyzer_type": "keyword"
  }'
```

### Get Company Sentiment (Last 30 Days)

```bash
curl http://localhost:8000/api/v1/sentiment/company/ASELS?days_back=30
```

### Get Sentiment Trends

```bash
curl http://localhost:8000/api/v1/sentiment/trends?days_back=30&company_name=ASELS
```

### Get Overall Statistics

```bash
curl http://localhost:8000/api/v1/sentiment/
```

---

## 🐍 Python Quick Start

### Installation

```bash
pip install requests
```

### Basic Analysis

```python
import requests

# Keyword analyzer (fast)
response = requests.post(
    'http://localhost:8000/api/v1/sentiment/analyze',
    json={
        'report_ids': [1, 2, 3],
        'analyzer_type': 'keyword'
    }
)

print(response.json())
```

### HuggingFace Analysis (Accurate)

```python
# For better accuracy
response = requests.post(
    'http://localhost:8000/api/v1/sentiment/analyze',
    json={
        'report_ids': [1, 2, 3],
        'analyzer_type': 'huggingface'
    }
)

for result in response.json()['results']:
    print(f"ID {result['report_id']}: {result['sentiment']['overall_sentiment']}")
```

### Batch Processing

```python
# Auto-analyze with specific companies
response = requests.post(
    'http://localhost:8000/api/v1/sentiment/analyze/auto',
    json={
        'days_back': 7,
        'company_codes': ['ASELS', 'AKBNK'],
        'analyzer_type': 'keyword'
    }
)

data = response.json()['data']
print(f"Analyzed: {data['analyzed_count']}/{data['total_found']}")
```

### Get Company Trend

```python
response = requests.get(
    'http://localhost:8000/api/v1/sentiment/company/ASELS',
    params={'days_back': 30, 'limit': 50}
)

history = response.json()['data']['sentiment_history']
for entry in history:
    print(f"{entry['date']}: {entry['sentiment']} ({entry['confidence']})")
```

---

## 🔧 Parameter Reference

### POST /analyze

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `report_ids` | List[int] | **Required** | Disclosure IDs to analyze |
| `analyzer_type` | string | "keyword" | "keyword" or "huggingface" |
| `custom_prompt` | string | null | Custom analysis prompt |

### POST /analyze/auto

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `days_back` | int | 7 | Look back period (1-30 days) |
| `analyzer_type` | string | "keyword" | "keyword" or "huggingface" |
| `company_codes` | List[str] | null | Filter specific companies |
| `force_reanalyze` | bool | false | Re-analyze existing data |

### GET /company/{name}

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `days_back` | int | 30 | Look back period |
| `limit` | int | 50 | Max results (1-200) |

### GET /trends

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `days_back` | int | 30 | Look back period |
| `company_name` | string | null | Filter by company |

---

## 📊 Response Format

### Success Response

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
        "key_sentiments": ["growth", "success"],
        "analysis_notes": "Positive outlook"
      },
      "analyzer": "keyword"
    }
  ]
}
```

### Error Response

```json
{
  "detail": "Disclosure not found"
}
```

---

## ⏱️ Performance Guide

| Analyzer | Speed | Accuracy | Best For |
|----------|-------|----------|----------|
| **Keyword** | 0.1ms/item | 51% | Real-time, high-volume |
| **HuggingFace** | 0.24s/item | 87.28% | Accuracy, reporting |

**Processing Time Estimates:**

- 100 items (keyword): ~10ms
- 100 items (huggingface): ~24 seconds
- 1000 items (keyword): ~100ms
- 1000 items (huggingface): ~240 seconds

---

## 🔀 Analyzer Selection Guide

### Choose Keyword When:
- ✅ Need immediate results
- ✅ Processing 1000+ items
- ✅ Running on low-power device
- ✅ Don't need deep learning

### Choose HuggingFace When:
- ✅ Need high accuracy
- ✅ Smaller batches OK
- ✅ Have GPU available
- ✅ Doing research/reporting

---

## 📱 JavaScript/TypeScript

### Fetch API

```javascript
// Keyword analyzer
const response = await fetch('http://localhost:8000/api/v1/sentiment/analyze', {
  method: 'POST',
  headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify({
    report_ids: [1, 2, 3],
    analyzer_type: 'keyword'
  })
});

const result = await response.json();
console.log(`Success: ${result.successful}, Failed: ${result.failed}`);
```

### Axios

```javascript
import axios from 'axios';

const result = await axios.post(
  'http://localhost:8000/api/v1/sentiment/analyze',
  {
    report_ids: [1, 2, 3],
    analyzer_type: 'huggingface'
  }
);

console.log(result.data.results);
```

---

## 🐳 Docker Compose

```yaml
services:
  sentiment-api:
    build: ./api
    ports:
      - "8000:8000"
    environment:
      - DATABASE_URL=postgresql://user:pass@db:5432/turkish_financial
      - USE_GPU=false  # Set to true for HuggingFace GPU
    depends_on:
      - db
```

---

## 🛠️ Troubleshooting

### API Not Responding

```bash
# Check if running
curl http://localhost:8000/api/v1/sentiment/

# Check logs
docker logs <container-id>

# Verify database
psql -d turkish_financial -c "SELECT COUNT(*) FROM kap_disclosure_sentiment;"
```

### HuggingFace Model Error

```bash
# Install dependencies
pip install transformers torch accelerate

# Test model
python -c "
from transformers import AutoModelForSequenceClassification
model = AutoModelForSequenceClassification.from_pretrained(
    'savasy/bert-base-turkish-sentiment-cased'
)
print('Model loaded OK')
"
```

### Slow Performance

```python
# For HuggingFace, check batch size
# Smaller batches = faster but less efficient
# Larger batches = slower but more efficient

# Recommended:
# - GPU: batches of 16-32
# - CPU: batches of 4-8
```

---

## 📚 Additional Resources

- **Full Guide:** [SENTIMENT_API_GUIDE.md](SENTIMENT_API_GUIDE.md)
- **Database Schema:** Check `kap_disclosure_sentiment` table
- **Models:** [Pydantic Models](../api/models.py)
- **Router:** [Sentiment Router](../api/routers/sentiment.py)

---

## 📞 Support

1. Check endpoint: `curl http://localhost:8000/api/v1/sentiment/`
2. View logs: `docker logs api`
3. Verify database: `psql -d turkish_financial`
4. Check code: Review [sentiment.py](../api/routers/sentiment.py)
