# Testing Guide - DDD Architecture

## Overview

This guide explains how to test the refactored DDD architecture codebase.

---

## 🧪 Testing Strategy

### 1. Domain Layer Tests (Unit Tests)

**No dependencies** - Pure business logic

#### Test Entities
```python
# tests/domain/test_kap_report_entity.py
def test_kap_report_validation():
    """Test entity validation"""
    with pytest.raises(ValueError):
        KAPReport(company_code="")  # Invalid
```

#### Test Value Objects
```python
# tests/domain/test_sentiment_value_objects.py
def test_confidence_validation():
    """Test value object validation"""
    with pytest.raises(ValueError):
        Confidence(1.5)  # Invalid
```

**Run:**
```bash
pytest tests/domain/ -v
```

---

### 2. Application Layer Tests (Use Case Tests)

**Mocked dependencies** - Test business workflows

#### Test Use Cases
```python
# tests/application/test_analyze_sentiment_use_case.py
@pytest.mark.asyncio
async def test_analyze_sentiment_success(use_case, mock_repo, mock_analyzer):
    mock_repo.find_by_id.return_value = report
    mock_analyzer.analyze.return_value = sentiment
    
    result = await use_case.execute([1])
    
    assert result["successful"] == 1
    mock_repo.save.assert_called_once()
```

**Run:**
```bash
pytest tests/application/ -v
```

---

### 3. Infrastructure Layer Tests (Integration Tests)

**Real dependencies** - Test technical implementations

#### Test Repositories
```python
# tests/infrastructure/test_repositories.py
@pytest.mark.integration
async def test_repository_save_and_find():
    repo = KAPReportRepository(test_db)
    report = KAPReport(...)
    
    saved = await repo.save(report)
    found = await repo.find_by_id(saved.id)
    
    assert found.company_code == report.company_code
```

**Run:**
```bash
pytest tests/infrastructure/ -v --integration
```

---

## 📋 Test Structure

```
tests/
├── domain/                    # Domain layer tests
│   ├── test_kap_report_entity.py
│   └── test_sentiment_value_objects.py
│
├── application/               # Use case tests
│   └── test_analyze_sentiment_use_case.py
│
└── infrastructure/            # Integration tests
    ├── test_repositories.py
    └── test_services.py
```

---

## 🔧 Test Setup

### 1. Install Test Dependencies

```bash
pip install pytest pytest-asyncio pytest-mock
```

### 2. Create Test Database

```python
# tests/conftest.py
import pytest
from database.db_manager import DatabaseManager

@pytest.fixture
def test_db():
    """Test database manager"""
    return DatabaseManager()  # Uses test database
```

### 3. Mock Dependencies

```python
# tests/conftest.py
@pytest.fixture
def mock_report_repository():
    """Mock report repository"""
    return AsyncMock(spec=IKAPReportRepository)

@pytest.fixture
def mock_sentiment_repository():
    """Mock sentiment repository"""
    return AsyncMock(spec=ISentimentRepository)
```

---

## ✅ Test Examples

### Domain Entity Test
```python
def test_kap_report_get_content():
    report = KAPReport(
        id=1,
        company_code="AKBNK",
        title="Q4 Results",
        summary="Strong performance",
        ...
    )
    
    content = report.get_content()
    assert "Q4 Results" in content
    assert "Strong performance" in content
```

### Use Case Test
```python
@pytest.mark.asyncio
async def test_analyze_sentiment_multiple_reports():
    # Setup
    use_case = AnalyzeSentimentUseCase(
        report_repository=mock_report_repo,
        sentiment_repository=mock_sentiment_repo,
        sentiment_analyzer=mock_analyzer
    )
    
    mock_report_repo.find_by_id.side_effect = [report1, report2]
    mock_analyzer.analyze.side_effect = [sentiment1, sentiment2]
    
    # Execute
    result = await use_case.execute([1, 2])
    
    # Verify
    assert result["total_analyzed"] == 2
    assert result["successful"] == 2
    assert mock_sentiment_repo.save.call_count == 2
```

### Repository Integration Test
```python
@pytest.mark.integration
async def test_repository_find_by_company_code():
    repo = KAPReportRepository(test_db)
    
    # Save test data
    report = KAPReport(...)
    await repo.save(report)
    
    # Find by company code
    results = await repo.find_by_company_code("AKBNK")
    
    assert len(results) > 0
    assert all(r.company_code == "AKBNK" for r in results)
```

---

## 🎯 Test Coverage Goals

- **Domain Layer**: 100% coverage (pure logic, easy to test)
- **Application Layer**: 90%+ coverage (use cases)
- **Infrastructure Layer**: 80%+ coverage (integration tests)

---

## 🚀 Running Tests

### Run All Tests
```bash
pytest tests/ -v
```

### Run by Layer
```bash
# Domain tests only
pytest tests/domain/ -v

# Application tests only
pytest tests/application/ -v

# Integration tests
pytest tests/infrastructure/ -v --integration
```

### Run with Coverage
```bash
pytest tests/ --cov=domain --cov=application --cov=infrastructure --cov-report=html
```

---

## 📝 Best Practices

1. **Test Domain Logic First**: Entities and value objects
2. **Mock Dependencies**: Use mocks for use case tests
3. **Test Edge Cases**: Validation, error handling
4. **Keep Tests Fast**: Unit tests should be instant
5. **Isolate Tests**: Each test should be independent

---

**See existing tests in `tests/` directory for examples.**
