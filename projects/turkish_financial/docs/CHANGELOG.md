# Changelog

## [2.0.0] - 2025-01-23

### Added

#### 🧠 Sentiment Analysis
- Structured sentiment analysis with JSON schema
- Confidence scores (0-1)
- Impact horizon classification (short/medium/long term)
- Risk flags and key drivers extraction
- Sentiment database table with indexes
- API endpoints for sentiment analysis and querying

#### ⚡ Batch Processing
- Async batch scraping with job management
- Job status tracking and progress monitoring
- Background task execution
- Job cleanup for old completed jobs
- REST API endpoints for batch operations

#### 🔔 Webhook Notifications
- Discord webhook support
- Slack webhook support
- Custom webhook endpoints
- Notifications for scraping completion
- Notifications for sentiment analysis completion
- Error notifications

#### 🚀 Performance Improvements
- Parallel pagination scraping
- Concurrent request handling with semaphores
- Optimized database queries with indexes
- Batch sentiment analysis

#### 📚 Documentation
- Enhanced API features documentation
- Quick start guide for new features
- Complete workflow examples
- Python client examples
- Troubleshooting guides

### Changed

- Updated `LLMAnalyzer` to support structured sentiment output
- Enhanced `DatabaseManager` with sentiment storage methods
- Extended API models with new request/response types
- Improved error handling across all endpoints

### Technical Details

#### New Database Tables
- `kap_report_sentiment` - Stores sentiment analysis results
- Indexes on `report_id`, `overall_sentiment`, and `analyzed_at`

#### New API Endpoints
- `POST /api/v1/scrapers/kap/batch` - Start batch scraping
- `GET /api/v1/scrapers/jobs/{job_id}` - Get job status
- `POST /api/v1/scrapers/kap/sentiment` - Analyze sentiment
- `GET /api/v1/reports/kap/{report_id}/sentiment` - Get report sentiment
- `GET /api/v1/reports/kap/sentiment/query` - Query sentiment data
- `POST /api/v1/scrapers/webhook/configure` - Configure webhooks

#### New Utilities
- `utils/webhook_notifier.py` - Webhook notification system
- `utils/batch_job_manager.py` - Batch job management
- Enhanced `utils/llm_analyzer.py` - Structured sentiment analysis

---

## [1.0.0] - Previous Release

### Features
- Basic KAP, BIST, TradingView scraping
- REST API with basic endpoints
- PDF extraction
- LLM analysis (text output)
- Database storage
- Scheduled tasks

---

**For detailed migration guide, see [MIGRATION_SUMMARY.md](MIGRATION_SUMMARY.md)**
