"""
Tests for KAPReport entity
Following DDD principles - test domain logic
"""
import pytest
from datetime import date, datetime
from domain.entities.kap_report import KAPReport


def test_kap_report_creation():
    """Test creating a valid KAP report"""
    report = KAPReport(
        id=1,
        company_code="AKBNK",
        company_name="Akbank",
        report_type="Financial Statement",
        report_date=date(2025, 1, 20),
        title="Q4 2024 Results",
        summary="Strong performance",
        data={"revenue": 1000000},
        scraped_at=datetime.now()
    )
    
    assert report.company_code == "AKBNK"
    assert report.id == 1


def test_kap_report_validation():
    """Test entity validation"""
    with pytest.raises(ValueError, match="Company code is required"):
        KAPReport(
            id=None,
            company_code="",
            company_name=None,
            report_type=None,
            report_date=None,
            title=None,
            summary=None,
            data=None,
            scraped_at=datetime.now()
        )


def test_kap_report_get_content():
    """Test content extraction"""
    report = KAPReport(
        id=1,
        company_code="AKBNK",
        company_name="Akbank",
        report_type="Financial Statement",
        report_date=date(2025, 1, 20),
        title="Q4 Results",
        summary="Strong performance",
        data={"revenue": 1000000},
        scraped_at=datetime.now()
    )
    
    content = report.get_content()
    assert "Q4 Results" in content
    assert "Strong performance" in content
    assert "revenue" in content


def test_kap_report_is_recent():
    """Test recent report check"""
    from datetime import timedelta
    
    recent_date = date.today() - timedelta(days=3)
    old_date = date.today() - timedelta(days=10)
    
    recent_report = KAPReport(
        id=1,
        company_code="AKBNK",
        company_name="Akbank",
        report_type=None,
        report_date=recent_date,
        title=None,
        summary=None,
        data=None,
        scraped_at=datetime.now()
    )
    
    old_report = KAPReport(
        id=2,
        company_code="AKBNK",
        company_name="Akbank",
        report_type=None,
        report_date=old_date,
        title=None,
        summary=None,
        data=None,
        scraped_at=datetime.now()
    )
    
    assert recent_report.is_recent(days=7) is True
    assert old_report.is_recent(days=7) is False


def test_kap_report_has_financial_data():
    """Test financial data detection"""
    report_with_data = KAPReport(
        id=1,
        company_code="AKBNK",
        company_name="Akbank",
        report_type=None,
        report_date=None,
        title=None,
        summary=None,
        data={"revenue": 1000000, "profit": 500000},
        scraped_at=datetime.now()
    )
    
    report_without_data = KAPReport(
        id=2,
        company_code="AKBNK",
        company_name="Akbank",
        report_type=None,
        report_date=None,
        title=None,
        summary=None,
        data={"other": "data"},
        scraped_at=datetime.now()
    )
    
    assert report_with_data.has_financial_data() is True
    assert report_without_data.has_financial_data() is False
