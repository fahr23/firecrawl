# Architecture

## Domain-Driven Design Layers

```
Presentation (api/)          ←  HTTP controllers, Pydantic DTOs
    ↓
Application (application/)   ←  Use cases, one class per operation
    ↓
Domain (domain/)             ←  Entities, value objects, interfaces
    ↑
Infrastructure (infrastructure/)  ←  Repository and service implementations
```

Each layer depends only on the layer above it (or on abstractions). Infrastructure implements domain interfaces, never the reverse.

---

## Layer Details

### Domain (`domain/`)

No external dependencies. Contains the core business logic.

- **Entities** (`domain/entities/`): `KAPReport` — domain entity with validation and business methods (`is_recent()`, `has_financial_data()`, `get_content()`)
- **Value Objects** (`domain/value_objects/`): `SentimentAnalysis`, `Confidence` (0.0-1.0), `SentimentType` (positive/neutral/negative), `ImpactHorizon` (short/medium/long)
- **Repository Interfaces** (`domain/repositories/`): `IKAPReportRepository`, `ISentimentRepository` — contracts only, no SQL
- **Service Interfaces** (`domain/services/`): `ISentimentAnalyzer` — contract for any LLM backend

### Application (`application/`)

Coordinates domain objects. Each use case has a single responsibility.

- `AnalyzeSentimentUseCase` — orchestrates sentiment pipeline
- `BatchScrapeUseCase` — coordinates async batch scraping

Use cases receive their dependencies via constructor injection (interfaces, not implementations):

```python
class AnalyzeSentimentUseCase:
    def __init__(
        self,
        report_repository: IKAPReportRepository,      # interface
        sentiment_repository: ISentimentRepository,    # interface
        sentiment_analyzer: ISentimentAnalyzer         # interface
    ): ...
```

### Infrastructure (`infrastructure/`)

Concrete implementations. Depends on domain interfaces.

- `KAPReportRepository` — PostgreSQL implementation of `IKAPReportRepository`
- `SentimentRepository` — PostgreSQL implementation of `ISentimentRepository`
- `SentimentAnalyzerService` — LLM-backed implementation of `ISentimentAnalyzer`

### Presentation (`api/`)

Thin controllers that delegate to use cases. No business logic here.

```python
@router.post("/kap/sentiment")
async def analyze_sentiment(request: SentimentAnalysisRequest):
    use_case = AnalyzeSentimentUseCase(repo, sentiment_repo, analyzer)
    return await use_case.execute(request.report_ids)
```

---

## Data Flow

### Sentiment Analysis Request

```
1. POST /api/v1/sentiment/analyze
2. api/routers/sentiment.py          → validates request, creates use case
3. AnalyzeSentimentUseCase.execute() → fetches reports from repository
4. IKAPReportRepository.find_by_id() → KAPReportRepository (SQL query)
5. KAPReport entity                  → domain entity with business logic
6. ISentimentAnalyzer.analyze()      → SentimentAnalyzerService (LLM call)
7. SentimentAnalysis value object    → immutable result
8. ISentimentRepository.save()       → SentimentRepository (SQL insert)
9. JSON response
```

### KAP Scraping Request

```
1. POST /api/v1/scrapers/kap
2. api/routers/scrapers.py           → validates request
3. KAPScraper.scrape()               → direct API call to kap.org.tr
4. kap.org.tr/tr/api/memberDisclosureQuery (POST, JSON)
5. Parse JSON response               → extract disclosureIndex, stockCodes, etc.
6. DatabaseManager.save_reports()    → bulk insert to kap_reports
7. (optional) PDFDownloader          → fetch PDFs from BildirimPdf/{index}
8. (optional) SentimentAnalyzer      → analyze PDF text
9. JSON response with counts
```

---

## Directory Structure

```
projects/turkish_financial/
├── domain/
│   ├── entities/kap_report.py
│   ├── value_objects/sentiment.py
│   ├── repositories/kap_report_repository.py    # interfaces
│   └── services/sentiment_analyzer_service.py   # interfaces
├── application/
│   └── use_cases/
│       ├── analyze_sentiment_use_case.py
│       └── batch_scrape_use_case.py
├── infrastructure/
│   ├── repositories/
│   │   ├── kap_report_repository_impl.py
│   │   └── sentiment_repository_impl.py
│   └── services/sentiment_analyzer_impl.py
├── api/
│   ├── main.py
│   ├── models.py
│   └── routers/
│       ├── scrapers.py
│       ├── reports.py
│       ├── sentiment.py
│       └── health.py
├── scrapers/
│   ├── base_scraper.py       # Firecrawl integration
│   ├── kap_scraper.py        # KAP API client
│   └── bist_scraper.py
├── database/db_manager.py    # PostgreSQL connection pool + schema init
├── utils/
│   ├── llm_analyzer.py       # LLM provider abstraction
│   ├── webhook_notifier.py
│   └── batch_job_manager.py
└── tests/
    ├── domain/               # pure unit tests, no deps
    ├── application/          # use cases with mocked repos
    └── infrastructure/       # integration tests (real DB)
```

---

## Database Schema

All tables live in the `turkish_financial` schema (configurable via `DB_SCHEMA`).

| Table | Contents |
|-------|----------|
| `kap_reports` | KAP disclosure metadata |
| `kap_reports_attachments` | PDF attachment metadata |
| `kap_disclosure_sentiment` | Sentiment analysis results |
| `bist_companies` | BIST company listings + `mkkMemberOid` |
| `bist_index_members` | Index membership (BIST 30/50/100) |
| `tradingview_sectors_tr` | Sector classifications (Turkish) |
| `tradingview_industry_tr` | Industry classifications (Turkish) |
| `historical_price_emtia` | Commodity prices (gold, silver, etc.) |
| `kap_financial_statements` | Raw financial table data from KAP |
| `kap_fundamentals` | Computed ratios from financial statements |

Schema is created automatically on first run by `DatabaseManager.__init__()`.

---

## SOLID Principles Applied

**SRP** — One class, one reason to change: `KAPReport` manages entity logic; `AnalyzeSentimentUseCase` manages the workflow; `KAPReportRepository` manages data access.

**OCP** — New sentiment backend? Implement `ISentimentAnalyzer`. New data source? Implement `IKAPReportRepository`. No existing code changes.

**DIP** — Use cases depend on interfaces, not implementations. Swap PostgreSQL for any other store without touching application logic.

**ISP** — Small focused interfaces: `IKAPReportRepository` only has report methods; `ISentimentRepository` only has sentiment methods.
