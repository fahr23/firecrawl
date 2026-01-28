# Turkish Financial Data Scraper API Documentation

## Overview

The Turkish Financial Data Scraper API provides comprehensive access to Turkish financial data with advanced AI-powered sentiment analysis. This REST API allows you to scrape, store, and analyze financial disclosures from KAP (Public Disclosure Platform), BIST data, and perform sophisticated sentiment analysis using optimized LLM models.

## Base URL
```
http://localhost:8000
```

## API Version
Current version: `v1.1.0`

---

## Authentication
Currently, no authentication is required. For production deployments, consider implementing API keys or OAuth2.

---

## Core Features

### 🔍 **Data Scraping**
- **KAP Disclosures**: Real-time scraping of Turkish corporate disclosures
- **BIST Data**: Stock market data and company information
- **TradingView Integration**: Market data and sector analysis

### 🤖 **AI-Powered Sentiment Analysis**
- **Configurable Providers**: Gemini, OpenAI, local LLM, or HuggingFace
- **Turkish Language Support**: Specialized analysis for Turkish financial content
- **Comprehensive Analysis**: Sentiment, risk assessment, impact horizon, and key drivers
- **Smart Caching**: Prevents duplicate analysis and reduces costs

### 📊 **Data Management**
- **PostgreSQL Integration**: Structured storage with dual-table design
- **Query Interface**: Flexible filtering and pagination
- **Trends Analysis**: Time-based sentiment and market trends

---

## Endpoints Overview

### 🏥 Health & Status
| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/v1/health` | System health check |
| GET | `/api/v1/health/database` | Database connectivity check |

### 🕷️ Scraping Operations  
| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/api/v1/scrapers/kap` | Scrape KAP disclosures |
| POST | `/api/v1/scrapers/bist` | Scrape BIST data |
| POST | `/api/v1/scrapers/tradingview` | Scrape TradingView data |
| POST | `/api/v1/scrapers/kap/sentiment` | Analyze sentiment for specific KAP reports |
| POST | `/api/v1/scrapers/llm/config` | Configure LLM settings |

### 📈 Data Queries & Reports
| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/v1/reports/kap` | Query KAP disclosures |
| GET | `/api/v1/reports/companies` | List companies |
| GET | `/api/v1/reports/stats` | Database statistics |

### 🧠 Sentiment Analysis (NEW)
| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/v1/sentiment/` | Sentiment overview & statistics |
| GET | `/api/v1/sentiment/disclosures/{id}` | Get sentiment for specific disclosure |
| GET | `/api/v1/sentiment/company/{name}` | Company sentiment history |
| GET | `/api/v1/sentiment/trends` | Sentiment trends over time |
| POST | `/api/v1/sentiment/analyze` | Analyze specific disclosures |
| POST | `/api/v1/sentiment/analyze/auto` | Auto-analyze recent disclosures |

---

## Detailed API Reference

### Sentiment Analysis Endpoints

#### POST `/api/v1/scrapers/kap/sentiment`
**Manual Sentiment Analysis (KAP Reports)**

Analyze sentiment for specific KAP report IDs and optionally override the LLM provider per request.

**Request Body:**
```json
{
  "report_ids": [1, 2, 3],
  "custom_prompt": "Focus on risks and opportunities",
  "use_llm": true,
  "llm_provider": "huggingface"
}
```

**Request Parameters:**
- `report_ids` (list, required)
- `custom_prompt` (string, optional)
- `use_llm` (bool, optional)
- `llm_provider` (string, optional): `gemini`, `openai`, `local_llm`, `huggingface`

**Response:**
```json
{
  "total_analyzed": 1,
  "successful": 1,
  "failed": 0,
  "results": [
    {
      "report_id": 1,
      "success": true,
      "sentiment": {
        "overall_sentiment": "neutral",
        "confidence": 0.52,
        "impact_horizon": "long_term",
        "key_drivers": [],
        "risk_flags": [],
        "tone_descriptors": ["informative", "neutral"],
        "target_audience": "investors",
        "analysis_text": "...",
        "provider": "HuggingFaceLocalProvider",
        "risk_level": "low"
      }
    }
  ]
}
```

#### GET `/api/v1/sentiment/`
**Sentiment Overview & Statistics**

Returns comprehensive statistics and overview of sentiment analysis data.

**Response:**
```json
{
  "success": true,
  "data": {
    "overview": {
      "total_analyses": 1247,
      "unique_disclosures": 1247,
      "average_confidence": 0.847,
      "sentiment_distribution": {
        "positive": 456,
        "neutral": 623,
        "negative": 168
      },
      "latest_analysis": "2024-01-15T10:30:00Z"
    },
    "trends": [...],
    "top_companies": [...]
  }
}
```

#### GET `/api/v1/sentiment/disclosures/{disclosure_id}`
**Get Sentiment for Specific Disclosure**

**Parameters:**
- `disclosure_id` (path): Database ID of the disclosure

**Response:**
```json
{
  "success": true,
  "data": {
    "disclosure": {
      "id": 123,
      "disclosure_id": "KAP-2024-001",
      "company_name": "AKBANK T.A.Ş.",
      "disclosure_type": "Genel Kurul",
      "disclosure_date": "2024-01-15",
      "content": "Disclosure content preview..."
    },
    "sentiment": {
      "overall_sentiment": "positive",
      "confidence": 0.87,
      "impact_horizon": "medium_term",
      "key_drivers": "Strong financial results, positive market outlook",
      "risk_flags": "None identified",
      "risk_level": "low",
      "analysis_text": "The disclosure indicates...",
      "analyzed_at": "2024-01-15T10:30:00Z"
    }
  }
}
```

#### GET `/api/v1/sentiment/company/{company_name}`
**Company Sentiment History**

**Parameters:**
- `company_name` (path): Name of the company
- `limit` (query): Number of results (1-200, default: 50)
- `days_back` (query): Days to look back (1-365, default: 30)

**Response:**
```json
{
  "success": true,
  "data": {
    "company_name": "AKBANK T.A.Ş.",
    "period": "Last 30 days",
    "summary": {
      "total_analyses": 15,
      "average_confidence": 0.84,
      "sentiment_distribution": {
        "positive": 8,
        "neutral": 5,
        "negative": 2
      }
    },
    "sentiment_history": [...]
  }
}
```

#### GET `/api/v1/sentiment/trends`
**Sentiment Trends Over Time**

**Parameters:**
- `days_back` (query): Days to analyze (1-365, default: 30)
- `company_name` (query): Optional company filter

**Response:**
```json
{
  "success": true,
  "data": {
    "period": "Last 30 days",
    "company_filter": null,
    "summary": {
      "total_analyses": 456,
      "total_companies": 67,
      "overall_confidence": 0.832,
      "sentiment_totals": {
        "positive": 189,
        "neutral": 201,
        "negative": 66
      }
    },
    "daily_trends": [
      {
        "date": "2024-01-15",
        "sentiment": "positive",
        "count": 12,
        "avg_confidence": 0.85,
        "unique_companies": 8
      }
    ]
  }
}
```

#### POST `/api/v1/sentiment/analyze`
**Analyze Specific Disclosures**

Perform sentiment analysis on specific disclosures by their database IDs.

**Request Body:**
```json
{
  "report_ids": [123, 124, 125],
  "custom_prompt": "Optional custom analysis prompt"
}
```

**Response:**
```json
{
  "total_analyzed": 3,
  "successful": 3,
  "failed": 0,
  "results": [
    {
      "report_id": 123,
      "success": true,
      "sentiment": {
        "overall_sentiment": "positive",
        "confidence": 0.87,
        "analysis_text": "..."
      }
    }
  ]
}
```

#### POST `/api/v1/sentiment/analyze/auto`
**Auto-Analyze Recent Disclosures**

Automatically analyze sentiment for recent disclosures that haven't been analyzed yet.

**Request Body:**
```json
{
  "days_back": 7,
  "company_codes": ["AKBNK", "GARAN"],
  "force_reanalyze": false
}
```

**Response:**
```json
{
  "success": true,
  "message": "Analyzed sentiment for 23 disclosures",
  "data": {
    "analyzed_count": 23,
    "total_found": 25,
    "period": "Last 7 days"
  }
}
```

---

## Cost-Optimized LLM Configuration

### Current Configuration
- **Model**: Gemini 1.5 Flash (75-80% cost reduction vs. 2.5 Flash)
- **Temperature**: 0.1 (reduced for consistency)
- **Max Tokens**: 800 (optimized for Turkish financial content)
- **Smart Caching**: Prevents duplicate analysis
- **Content Filtering**: Skips test data and duplicates

### LLM Analysis Features
- **Turkish Language Expertise**: Specialized for Turkish financial terminology
- **Comprehensive Analysis**: 
  - Overall sentiment (positive/neutral/negative)
  - Confidence score (0-1)
  - Impact horizon (short/medium/long term)
  - Key sentiment drivers
  - Risk flags and assessments
  - Tone descriptors
  - Target audience identification

---

## Data Models

### KAP Disclosure
```json
{
  "id": 123,
  "disclosure_id": "KAP-2024-001",
  "company_name": "AKBANK T.A.Ş.",
  "disclosure_type": "Genel Kurul",
  "disclosure_date": "2024-01-15",
  "content": "Full disclosure content...",
  "scraped_at": "2024-01-15T08:00:00Z"
}
```

### Sentiment Analysis
```json
{
  "disclosure_id": 123,
  "overall_sentiment": "positive",
  "confidence": 0.87,
  "impact_horizon": "medium_term",
  "key_drivers": "Strong financial results, positive outlook",
  "risk_flags": "None identified",
  "tone_descriptors": "confident, optimistic",
  "target_audience": "investors",
  "analysis_text": "Detailed analysis...",
  "risk_level": "low",
  "analyzed_at": "2024-01-15T10:30:00Z"
}
```

---

## Error Handling

### Database Pool Exhaustion (503)
If the database connection pool is exhausted due to heavy load, the API will return HTTP 503 Service Unavailable with a message indicating the database is temporarily unavailable. Configure retry/backoff via environment variables:

- `DB_CONN_RETRIES` (default: 3) — Number of short retries when acquiring a connection
- `DB_CONN_WAIT_MS` (default: 100) — Milliseconds to wait between retries

Clients should retry requests with exponential backoff when receiving a 503 response.


### HTTP Status Codes
- `200 OK`: Successful request
- `400 Bad Request`: Invalid parameters
- `404 Not Found`: Resource not found
- `422 Unprocessable Entity`: Validation error
- `500 Internal Server Error`: Server error

### Error Response Format
```json
{
  "detail": "Error description",
  "error": "Technical error message"
}
```

---

## Usage Examples

### Basic Sentiment Analysis Workflow

1. **Check Available Disclosures:**
```bash
curl "http://localhost:8000/api/v1/reports/kap?limit=10"
```

2. **Analyze Recent Disclosures:**
```bash
curl -X POST "http://localhost:8000/api/v1/sentiment/analyze/auto" \
  -H "Content-Type: application/json" \
  -d '{"days_back": 7}'
```

3. **Get Company Sentiment History:**
```bash
curl "http://localhost:8000/api/v1/sentiment/company/AKBANK%20T.A.Ş.?days_back=30"
```

4. **Check Sentiment Trends:**
```bash
curl "http://localhost:8000/api/v1/sentiment/trends?days_back=30"
```

### Advanced Analysis

**Custom Sentiment Analysis:**
```bash
curl -X POST "http://localhost:8000/api/v1/sentiment/analyze" \
  -H "Content-Type: application/json" \
  -d '{
    "report_ids": [123, 124, 125],
    "custom_prompt": "Focus on ESG implications and sustainability aspects"
  }'
```

---

## Performance & Optimization

### Cost Optimization Features
- **Model Selection**: Gemini 1.5 Flash provides excellent Turkish analysis at 60-70% lower cost
- **Smart Caching**: Content hashing prevents duplicate LLM calls
- **Content Filtering**: Skips test data and irrelevant content
- **Batch Processing**: Efficient bulk analysis capabilities

### Performance Metrics
- **Analysis Speed**: ~2-3 seconds per disclosure
- **Cost Reduction**: 75-80% vs. premium models
- **Accuracy**: High accuracy for Turkish financial content
- **Caching Hit Rate**: ~40-50% for duplicate content

---

## Database Schema

### Key Tables
- `kap_disclosures`: Raw disclosure data
- `kap_disclosure_sentiment`: LLM sentiment analysis results

### Relationships
```sql
kap_disclosures (id) -> kap_disclosure_sentiment (disclosure_id)
```

---

## Rate Limiting & Quotas

Currently no rate limiting is implemented. For production deployment, consider:
- Request rate limits per IP
- Daily/monthly quotas
- LLM usage limits to control costs

---

## Future Enhancements

### Planned Features
- **Real-time Websockets**: Live updates for new disclosures
- **Advanced Analytics**: ML-powered trend prediction
- **Multi-language Support**: Expand beyond Turkish
- **API Key Authentication**: Secure access control
- **Webhook Integration**: Real-time notifications

### Integration Opportunities
- **Bloomberg Terminal**: Data export compatibility
- **Excel Add-in**: Direct Excel integration
- **Slack/Discord Bots**: Automated notifications
- **Email Alerts**: Sentiment-based alerts

---

## Support & Resources

### Documentation
- **OpenAPI/Swagger**: Available at `/docs`
- **ReDoc**: Available at `/redoc`

### Contact
For technical support or feature requests, please contact the development team.

### Version History
- `v1.1.0`: Added comprehensive sentiment analysis endpoints
- `v1.0.0`: Initial release with basic scraping and querying

---

*Last updated: January 2024*