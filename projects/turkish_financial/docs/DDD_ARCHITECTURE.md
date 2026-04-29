# Domain-Driven Design Architecture

## Overview

The Turkish Financial Data Scraper follows **Domain-Driven Design (DDD)** principles for maintainability, testability, and single responsibility.

---

## 🏗️ Architecture Layers

### 1. Domain Layer (`domain/`)

**Purpose**: Core business logic, independent of infrastructure

#### Entities (`domain/entities/`)
- **KAPReport**: Domain entity representing financial disclosure reports
- Contains business logic (validation, content extraction, date checks)
- Immutable identity and business invariants

#### Value Objects (`domain/value_objects/`)
- **SentimentAnalysis**: Immutable sentiment analysis result
- **Confidence**: Validated confidence score (0.0-1.0)
- **SentimentType**: Enumeration (positive/neutral/negative)
- **ImpactHorizon**: Enumeration (short/medium/long term)

#### Repository Interfaces (`domain/repositories/`)
- **IKAPReportRepository**: Contract for report data access
- **ISentimentRepository**: Contract for sentiment data access
- No implementation details - pure interfaces

#### Domain Services (`domain/services/`)
- **ISentimentAnalyzer**: Interface for sentiment analysis
- Business logic that doesn't belong to a single entity

---

### 2. Application Layer (`application/`)

**Purpose**: Use cases and application services

#### Use Cases (`application/use_cases/`)
- **AnalyzeSentimentUseCase**: Single responsibility - analyze sentiment
- **BatchScrapeUseCase**: Single responsibility - batch scraping
- Each use case coordinates domain objects and infrastructure
- Testable with mocked dependencies

**Example:**
```python
class AnalyzeSentimentUseCase:
    def __init__(
        self,
        report_repository: IKAPReportRepository,
        sentiment_repository: ISentimentRepository,
        sentiment_analyzer: ISentimentAnalyzer
    ):
        # Dependency injection
        
    async def execute(self, report_ids: List[int]) -> Dict:
        # Use case logic
```

---

### 3. Infrastructure Layer (`infrastructure/`)

**Purpose**: Technical implementations

#### Repository Implementations (`infrastructure/repositories/`)
- **KAPReportRepository**: PostgreSQL implementation of IKAPReportRepository
- **SentimentRepository**: PostgreSQL implementation of ISentimentRepository
- Handles database operations, converts DB rows to domain entities

#### Service Implementations (`infrastructure/services/`)
- **SentimentAnalyzerService**: LLM-based implementation of ISentimentAnalyzer
- Converts LLM responses to domain value objects

---

### 4. Presentation Layer (`api/`)

**Purpose**: HTTP API endpoints

#### Routers (`api/routers/`)
- **scrapers.py**: Scraping endpoints
- **reports.py**: Report query endpoints
- Thin controllers that delegate to use cases

**Example:**
```python
@router.post("/kap/sentiment")
async def analyze_sentiment(request: SentimentAnalysisRequest):
    # Create use case with dependencies
    use_case = AnalyzeSentimentUseCase(...)
    
    # Execute use case
    result = await use_case.execute(request.report_ids)
    
    return result
```

---

## 📐 Design Principles Applied

### 1. Single Responsibility Principle (SRP)

Each class has one reason to change:

- **KAPReport**: Manages report entity logic
- **AnalyzeSentimentUseCase**: Coordinates sentiment analysis workflow
- **KAPReportRepository**: Handles report data access
- **SentimentAnalyzerService**: Converts LLM output to domain objects

### 2. Dependency Inversion Principle (DIP)

High-level modules depend on abstractions:

```python
# Use case depends on interface, not implementation
class AnalyzeSentimentUseCase:
    def __init__(
        self,
        report_repository: IKAPReportRepository,  # Interface
        sentiment_repository: ISentimentRepository,  # Interface
        sentiment_analyzer: ISentimentAnalyzer  # Interface
    ):
        ...
```

### 3. Open/Closed Principle (OCP)

Open for extension, closed for modification:

- New sentiment analyzers: Implement `ISentimentAnalyzer`
- New repositories: Implement `IKAPReportRepository`
- No need to modify existing code

### 4. Interface Segregation Principle (ISP)

Small, focused interfaces:

- `IKAPReportRepository`: Only report-related methods
- `ISentimentRepository`: Only sentiment-related methods
- No fat interfaces

---

## 🧪 Testability

### Unit Tests

**Domain entities** (no dependencies):
```python
def test_kap_report_validation():
    with pytest.raises(ValueError):
        KAPReport(company_code="")  # Invalid
```

**Use cases** (mocked dependencies):
```python
@pytest.mark.asyncio
async def test_analyze_sentiment(use_case, mock_repo, mock_analyzer):
    mock_repo.find_by_id.return_value = report
    mock_analyzer.analyze.return_value = sentiment
    
    result = await use_case.execute([1])
    
    assert result["successful"] == 1
```

### Integration Tests

Test repository implementations with test database:
```python
@pytest.mark.integration
async def test_repository_save_and_find():
    repo = KAPReportRepository(test_db)
    report = KAPReport(...)
    
    saved = await repo.save(report)
    found = await repo.find_by_id(saved.id)
    
    assert found.company_code == report.company_code
```

---

## 📁 Directory Structure

```
turkish-financial-data-scraper/
├── domain/                    # Domain layer
│   ├── entities/              # Domain entities
│   │   └── kap_report.py
│   ├── value_objects/         # Value objects
│   │   └── sentiment.py
│   ├── repositories/          # Repository interfaces
│   │   ├── kap_report_repository.py
│   │   └── sentiment_repository.py
│   └── services/              # Domain service interfaces
│       └── sentiment_analyzer_service.py
│
├── application/               # Application layer
│   └── use_cases/            # Use cases
│       ├── analyze_sentiment_use_case.py
│       └── batch_scrape_use_case.py
│
├── infrastructure/            # Infrastructure layer
│   ├── repositories/         # Repository implementations
│   │   ├── kap_report_repository_impl.py
│   │   └── sentiment_repository_impl.py
│   └── services/             # Service implementations
│       └── sentiment_analyzer_impl.py
│
├── api/                       # Presentation layer
│   ├── routers/              # API endpoints
│   └── models.py             # DTOs
│
└── tests/                     # Tests
    ├── domain/               # Domain tests
    ├── application/           # Use case tests
    └── infrastructure/       # Integration tests
```

---

## 🔄 Data Flow

### Sentiment Analysis Flow

```
1. API Request
   ↓
2. Router (api/routers/scrapers.py)
   ↓
3. Use Case (application/use_cases/analyze_sentiment_use_case.py)
   ↓
4. Repository (infrastructure/repositories/kap_report_repository_impl.py)
   ↓
5. Database
   ↓
6. Domain Entity (domain/entities/kap_report.py)
   ↓
7. Domain Service (infrastructure/services/sentiment_analyzer_impl.py)
   ↓
8. Value Object (domain/value_objects/sentiment.py)
   ↓
9. Repository Save
   ↓
10. Response
```

---

## ✅ Benefits

### Maintainability
- Clear separation of concerns
- Easy to locate code
- Changes isolated to specific layers

### Testability
- Domain logic testable without infrastructure
- Use cases testable with mocks
- Integration tests for repositories

### Single Responsibility
- Each class has one job
- Easy to understand and modify

### Extensibility
- New features: Add new use cases
- New data sources: Implement repository interface
- New analyzers: Implement service interface

---

## 📚 References

- **Domain-Driven Design** by Eric Evans
- **Clean Architecture** by Robert C. Martin
- **SOLID Principles**

---

**Last Updated**: January 23, 2025
