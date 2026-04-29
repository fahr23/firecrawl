# Sentiment Analysis API Integration Guide

## 📚 Overview

This guide explains how the sentiment analysis features have been integrated into the REST API and how to use them effectively.

---

## 🔧 What's Been Integrated

### 1. **Sentiment Analyzers**

Two analyzers are now available via the API:

| Analyzer | Endpoint | Speed | Accuracy | Use Case |
|----------|----------|-------|----------|----------|
| **Keyword** | POST `/api/v1/sentiment/analyze` | ⚡ 0.1ms/item | 51% | Real-time, high-volume |
| **HuggingFace** | POST `/api/v1/sentiment/analyze` | 🎯 0.24s/item | 87.28% | Accurate, reporting |

### 2. **API Models Updated**

The following models now support analyzer selection:

**`SentimentAnalysisRequest`** (lines ~150-160 in api/models.py)
```python
analyzer_type: str = Field(
    default="keyword",
    description="Sentiment analyzer: 'keyword' (fast) or 'huggingface' (accurate)"
)
```

**`AutoSentimentRequest`** (lines ~170-180 in api/models.py)
```python
analyzer_type: str = Field(
    default="keyword",
    description="Sentiment analyzer: 'keyword' (fast) or 'huggingface' (accurate)"
)
```

### 3. **API Endpoints Enhanced**

Two endpoints now support dynamic analyzer selection:

**POST `/api/v1/sentiment/analyze`** (lines ~325-430 in api/routers/sentiment.py)
- Accepts `analyzer_type` parameter
- Automatically selects LLM provider based on analyzer
- Returns sentiment data with analyzer info

**POST `/api/v1/sentiment/analyze/auto`** (lines ~475-575 in api/routers/sentiment.py)
- Accepts `analyzer_type` parameter
- Auto-analyzes recent disclosures with selected analyzer
- Returns analysis count and analyzer type used

### 4. **Database Schema**

Sentiment data is stored in `kap_disclosure_sentiment`:
```sql
CREATE TABLE kap_disclosure_sentiment (
    id SERIAL PRIMARY KEY,
    disclosure_id INTEGER NOT NULL,
    overall_sentiment VARCHAR(20),           -- positive, neutral, negative
    sentiment_score DECIMAL(5,2),            -- confidence/score 0-1
    key_sentiments JSONB,                    -- array of detected sentiments
    analysis_notes TEXT,                     -- detailed notes
    created_at TIMESTAMP DEFAULT NOW()
);
```

---

## 🚀 Quick Start

### 1. Health Check

```bash
curl http://localhost:8000/api/v1/sentiment/
```

### 2. Analyze with Keyword (Fast)

```bash
curl -X POST http://localhost:8000/api/v1/sentiment/analyze \
  -H "Content-Type: application/json" \
  -d '{
    "report_ids": [1, 2, 3],
    "analyzer_type": "keyword"
  }'
```

### 3. Analyze with HuggingFace (Accurate)

```bash
curl -X POST http://localhost:8000/api/v1/sentiment/analyze \
  -H "Content-Type: application/json" \
  -d '{
    "report_ids": [1],
    "analyzer_type": "huggingface"
  }'
```

### 4. Auto-Analyze Recent (Last 7 Days)

```bash
curl -X POST http://localhost:8000/api/v1/sentiment/analyze/auto \
  -H "Content-Type: application/json" \
  -d '{
    "days_back": 7,
    "analyzer_type": "keyword"
  }'
```

---

## 📖 Detailed API Documentation

### Endpoint: POST `/api/v1/sentiment/analyze`

**Purpose:** Analyze sentiment of specific disclosures

**Request Body:**
```json
{
  "report_ids": [1, 2, 3],
  "analyzer_type": "keyword",
  "custom_prompt": null
}
```

**Parameters:**
- `report_ids` (required, List[int]): IDs of disclosures to analyze
- `analyzer_type` (optional, str, default: "keyword"): 
  - `"keyword"` - Fast, keyword-based (0.1ms/item)
  - `"huggingface"` - Deep learning, accurate (0.24s/item)
- `custom_prompt` (optional, str): Custom analysis instructions

**Response (Success):**
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
        "analysis_notes": "Strong positive sentiment with growth indicators"
      },
      "analyzer": "keyword"
    }
  ]
}
```

**Response (Partial Failure):**
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

**HTTP Status Codes:**
- `200` - Success (some or all analyzed)
- `400` - Invalid request format
- `503` - Database connection error

### Endpoint: POST `/api/v1/sentiment/analyze/auto`

**Purpose:** Automatically analyze recent disclosures

**Request Body:**
```json
{
  "days_back": 7,
  "analyzer_type": "keyword",
  "company_codes": ["ASELS", "AKBNK"],
  "force_reanalyze": false
}
```

**Parameters:**
- `days_back` (optional, int, default: 7): Look back N days (1-30)
- `analyzer_type` (optional, str, default: "keyword"): Analyzer selection
- `company_codes` (optional, List[str]): Filter specific companies
- `force_reanalyze` (optional, bool, default: false): Re-analyze existing

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
  "timestamp": "2025-01-23T10:30:00"
}
```

---

## 🐍 Python Integration Examples

### Example 1: Simple Analysis

```python
import requests

def analyze_disclosures(disclosure_ids: list, use_huggingface: bool = False):
    """Analyze disclosures with selected analyzer"""
    
    analyzer = "huggingface" if use_huggingface else "keyword"
    
    response = requests.post(
        'http://localhost:8000/api/v1/sentiment/analyze',
        json={
            'report_ids': disclosure_ids,
            'analyzer_type': analyzer
        }
    )
    
    result = response.json()
    
    print(f"Analyzed: {result['successful']}/{result['total_analyzed']}")
    print(f"Analyzer: {analyzer}")
    
    for item in result['results']:
        if item['success']:
            sentiment = item['sentiment']
            print(f"  ID {item['report_id']}: {sentiment['overall_sentiment']} "
                  f"({sentiment['confidence']})")
        else:
            print(f"  ID {item['report_id']}: ERROR - {item['error']}")

# Usage
analyze_disclosures([1, 2, 3], use_huggingface=False)  # Fast
analyze_disclosures([1], use_huggingface=True)         # Accurate
```

### Example 2: Batch Processing with Progress

```python
import requests
from tqdm import tqdm

def batch_analyze(disclosure_ids: list, batch_size: int = 100, 
                  analyzer: str = "keyword"):
    """Process disclosures in batches with progress bar"""
    
    results = []
    
    for i in tqdm(range(0, len(disclosure_ids), batch_size)):
        batch = disclosure_ids[i:i+batch_size]
        
        response = requests.post(
            'http://localhost:8000/api/v1/sentiment/analyze',
            json={
                'report_ids': batch,
                'analyzer_type': analyzer
            }
        )
        
        results.extend(response.json()['results'])
    
    return results

# Usage
all_ids = list(range(1, 1001))
results = batch_analyze(all_ids, batch_size=50, analyzer="keyword")
print(f"Total successful: {sum(1 for r in results if r['success'])}")
```

### Example 3: Performance Comparison

```python
import requests
import time

def compare_analyzers(disclosure_ids: list):
    """Compare keyword vs HuggingFace performance"""
    
    analyzers = ["keyword", "huggingface"]
    
    for analyzer in analyzers:
        start = time.time()
        
        response = requests.post(
            'http://localhost:8000/api/v1/sentiment/analyze',
            json={
                'report_ids': disclosure_ids,
                'analyzer_type': analyzer
            }
        )
        
        elapsed = time.time() - start
        result = response.json()
        
        print(f"\n{analyzer.upper()} Analyzer:")
        print(f"  Time: {elapsed:.2f}s ({elapsed/len(disclosure_ids)*1000:.2f}ms/item)")
        print(f"  Success rate: {result['successful']}/{result['total_analyzed']}")
        
        if result['results'][0]['success']:
            sentiment = result['results'][0]['sentiment']
            print(f"  Sample confidence: {sentiment['confidence']}")

# Usage
compare_analyzers([1, 2, 3])
```

### Example 4: Auto-Analysis with Filters

```python
import requests

def auto_analyze_companies(company_codes: list = None, 
                           days_back: int = 7,
                           analyzer: str = "keyword"):
    """Auto-analyze recent disclosures"""
    
    response = requests.post(
        'http://localhost:8000/api/v1/sentiment/analyze/auto',
        json={
            'days_back': days_back,
            'company_codes': company_codes,
            'analyzer_type': analyzer
        }
    )
    
    result = response.json()
    data = result['data']
    
    print(f"Auto-Analysis Results:")
    print(f"  Analyzed: {data['analyzed_count']}/{data['total_found']}")
    print(f"  Period: {data['period']}")
    print(f"  Analyzer: {data['analyzer_type']}")
    
    return result

# Usage: All companies, last 7 days, keyword analyzer
auto_analyze_companies()

# Usage: Specific companies, last 3 days, HuggingFace
auto_analyze_companies(
    company_codes=['ASELS', 'AKBNK'],
    days_back=3,
    analyzer='huggingface'
)
```

### Example 5: Get Company Sentiment History

```python
import requests

def get_company_trend(company_name: str, days_back: int = 30):
    """Get sentiment trend for company"""
    
    response = requests.get(
        f'http://localhost:8000/api/v1/sentiment/company/{company_name}',
        params={'days_back': days_back, 'limit': 50}
    )
    
    result = response.json()['data']
    
    print(f"Sentiment History for {result['company_name']}:")
    print(f"Period: {result['period']}\n")
    
    for entry in result['sentiment_history']:
        print(f"  {entry['date']}: {entry['sentiment']:10} "
              f"(confidence: {entry['confidence']:.2f})")

# Usage
get_company_trend('ASELS', days_back=30)
```

---

## 📊 JavaScript/TypeScript Integration

### React Component Example

```javascript
import React, { useState } from 'react';
import axios from 'axios';

function SentimentAnalyzer() {
  const [disclosureIds, setDisclosureIds] = useState('1,2,3');
  const [analyzer, setAnalyzer] = useState('keyword');
  const [results, setResults] = useState(null);
  const [loading, setLoading] = useState(false);

  const handleAnalyze = async () => {
    setLoading(true);
    try {
      const ids = disclosureIds.split(',').map(id => parseInt(id.trim()));
      
      const response = await axios.post(
        'http://localhost:8000/api/v1/sentiment/analyze',
        {
          report_ids: ids,
          analyzer_type: analyzer
        }
      );
      
      setResults(response.data);
    } catch (error) {
      console.error('Error:', error);
      alert('Analysis failed: ' + error.message);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div>
      <h2>Sentiment Analysis</h2>
      
      <div>
        <label>Disclosure IDs:</label>
        <input
          value={disclosureIds}
          onChange={e => setDisclosureIds(e.target.value)}
          placeholder="1,2,3"
        />
      </div>
      
      <div>
        <label>Analyzer:</label>
        <select value={analyzer} onChange={e => setAnalyzer(e.target.value)}>
          <option value="keyword">Keyword (Fast)</option>
          <option value="huggingface">HuggingFace (Accurate)</option>
        </select>
      </div>
      
      <button onClick={handleAnalyze} disabled={loading}>
        {loading ? 'Analyzing...' : 'Analyze'}
      </button>
      
      {results && (
        <div>
          <p>Successful: {results.successful}/{results.total_analyzed}</p>
          <p>Analyzer: {results.results[0].analyzer}</p>
          {results.results[0].success && (
            <div>
              <p>Sentiment: {results.results[0].sentiment.overall_sentiment}</p>
              <p>Confidence: {results.results[0].sentiment.confidence}</p>
            </div>
          )}
        </div>
      )}
    </div>
  );
}

export default SentimentAnalyzer;
```

---

## 🎯 Performance Optimization

### For High-Volume Keyword Analysis

```python
# Process 1000 items in ~100ms
import concurrent.futures

def process_in_parallel(all_ids: list, workers: int = 4):
    """Process disclosures in parallel batches"""
    
    batch_size = len(all_ids) // workers
    batches = [all_ids[i:i+batch_size] for i in range(0, len(all_ids), batch_size)]
    
    results = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as executor:
        futures = [
            executor.submit(
                requests.post,
                'http://localhost:8000/api/v1/sentiment/analyze',
                json={'report_ids': batch, 'analyzer_type': 'keyword'}
            )
            for batch in batches
        ]
        
        for future in concurrent.futures.as_completed(futures):
            response = future.result()
            results.extend(response.json()['results'])
    
    return results
```

### For HuggingFace Accuracy with GPU

```python
# Note: Make sure GPU is available in Docker
# Set environment variable: CUDA_VISIBLE_DEVICES=0

def analyze_with_gpu(disclosure_ids: list):
    """Analyze with GPU acceleration"""
    
    # Smaller batches for GPU memory
    batch_size = 16
    
    for i in range(0, len(disclosure_ids), batch_size):
        batch = disclosure_ids[i:i+batch_size]
        
        response = requests.post(
            'http://localhost:8000/api/v1/sentiment/analyze',
            json={
                'report_ids': batch,
                'analyzer_type': 'huggingface'
            }
        )
        
        print(f"Processed {i+len(batch)}/{len(disclosure_ids)}")
```

---

## 🧪 Testing

### Run Test Suite

```bash
# Test all endpoints
python test_sentiment_api.py

# Test HuggingFace analyzer (slower)
python test_sentiment_api.py --huggingface
```

### Manual Testing with cURL

```bash
# Health check
curl http://localhost:8000/api/v1/health

# Sentiment overview
curl http://localhost:8000/api/v1/sentiment/

# Analyze with keyword
curl -X POST http://localhost:8000/api/v1/sentiment/analyze \
  -H "Content-Type: application/json" \
  -d '{"report_ids": [1, 2], "analyzer_type": "keyword"}'

# Get company sentiment
curl "http://localhost:8000/api/v1/sentiment/company/ASELS?days_back=30"
```

---

## 📈 Monitoring & Analytics

### Track API Usage

```python
import requests
from datetime import datetime

def log_sentiment_analysis(analyzer: str, count: int, success: bool):
    """Log sentiment analysis events"""
    
    log_entry = {
        'timestamp': datetime.now().isoformat(),
        'analyzer': analyzer,
        'count': count,
        'success': success
    }
    
    # Save to database or log file
    print(f"[{log_entry['timestamp']}] {analyzer}: {count} items - {'OK' if success else 'FAIL'}")
```

### Performance Metrics

```python
def get_api_metrics():
    """Get API performance metrics"""
    
    response = requests.get('http://localhost:8000/api/v1/sentiment/')
    data = response.json()['data']
    
    print("API Metrics:")
    print(f"  Total Analyses: {data['total_analyses']}")
    print(f"  Sentiments: {data['sentiment_distribution']}")
    print(f"  Avg Confidence: {data['average_confidence']:.2f}")
```

---

## 🔐 Security Best Practices

1. **Rate Limiting**: Implement per-user/IP limits
   - Recommendation: 100 requests/min

2. **Input Validation**: Always validate disclosure IDs
   - Check ID exists before analysis
   - Limit batch sizes (max 100 per request)

3. **Error Handling**: Never expose internal errors
   - Log errors server-side
   - Return generic messages to client

4. **Authentication**: Add API keys for production
   ```python
   # Example: validate API key
   def validate_api_key(key: str) -> bool:
       return key in VALID_API_KEYS
   ```

---

## 🚨 Troubleshooting

### API Not Responding

```bash
# Check if running
curl http://localhost:8000/api/v1/health

# Check logs
docker logs <api-container-id>

# Check database connection
psql -d turkish_financial -c "SELECT COUNT(*) FROM kap_disclosure_sentiment;"
```

### High Latency with Keyword Analyzer

- This shouldn't happen (should be <1ms/item)
- Check system load: `top`
- Check database connection pool

### HuggingFace Model Not Loading

```bash
# Test model import
python -c "from transformers import AutoTokenizer; print('OK')"

# Install dependencies
pip install transformers torch accelerate

# Check GPU availability
python -c "import torch; print(torch.cuda.is_available())"
```

### Memory Issues with Large Batches

- Reduce batch size
- Use keyword analyzer instead
- Enable GPU if available

---

## 📚 Additional Resources

- **Full API Guide:** [SENTIMENT_API_GUIDE.md](SENTIMENT_API_GUIDE.md)
- **Quick Reference:** [SENTIMENT_API_QUICK_REFERENCE.md](SENTIMENT_API_QUICK_REFERENCE.md)
- **Main API Docs:** [API_DOCUMENTATION.md](API_DOCUMENTATION.md)
- **Test Script:** [test_sentiment_api.py](test_sentiment_api.py)

---

## ✅ Integration Checklist

- ✅ API models updated with `analyzer_type` field
- ✅ POST `/analyze` endpoint supports both analyzers
- ✅ POST `/analyze/auto` endpoint supports both analyzers  
- ✅ Database schema properly mapped
- ✅ Sentiment router fully functional
- ✅ Documentation created and updated
- ✅ Test suite provided
- ✅ Python examples included
- ✅ JavaScript examples included
- ✅ Performance metrics documented

---

## 🎓 Next Steps

1. **Run Tests**: `python test_sentiment_api.py`
2. **Try Endpoints**: Use cURL or Postman to test
3. **Integrate**: Add to your application
4. **Monitor**: Track performance and accuracy
5. **Optimize**: Choose right analyzer for your use case

---

For questions or issues, check the test output or logs:

```bash
docker logs -f api-service
```
