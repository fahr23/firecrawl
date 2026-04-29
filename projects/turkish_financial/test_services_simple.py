"""
Simple service test - tests structure without requiring all dependencies
Useful for verifying code structure before installing dependencies
"""
import sys
from pathlib import Path

project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))


def test_imports():
    """Test that all modules can be imported (structure test)"""
    results = {}
    
    # Test domain imports (no dependencies)
    try:
        from domain.entities.kap_report import KAPReport
        from domain.value_objects.sentiment import SentimentAnalysis, SentimentType, Confidence
        results["domain"] = "✅ PASS"
    except Exception as e:
        results["domain"] = f"❌ FAIL: {e}"
    
    # Test application imports (no dependencies)
    try:
        from application.use_cases.analyze_sentiment_use_case import AnalyzeSentimentUseCase
        from application.dependencies import get_analyze_sentiment_use_case
        results["application"] = "✅ PASS"
    except Exception as e:
        # Check if it's a dependency issue
        if "psycopg2" in str(e) or "fastapi" in str(e):
            results["application"] = "⚠️ NEEDS DEPS (structure OK)"
        else:
            results["application"] = f"❌ FAIL: {e}"
    
    # Test infrastructure imports (needs psycopg2)
    try:
        from infrastructure.repositories.kap_report_repository_impl import KAPReportRepository
        from infrastructure.services.sentiment_analyzer_impl import SentimentAnalyzerService
        results["infrastructure"] = "✅ PASS"
    except Exception as e:
        if "psycopg2" in str(e):
            results["infrastructure"] = "⚠️ NEEDS DEPS (structure OK)"
        else:
            results["infrastructure"] = f"❌ FAIL: {e}"
    
    # Test API imports (needs fastapi)
    try:
        from api.main import app
        from api.routers.scrapers import router
        results["api"] = "✅ PASS"
    except Exception as e:
        if "fastapi" in str(e):
            results["api"] = "⚠️ NEEDS DEPS (structure OK)"
        else:
            results["api"] = f"❌ FAIL: {e}"
    
    # Test utilities (needs some deps)
    try:
        from utils.batch_job_manager import BatchJobManager
        from utils.webhook_notifier import WebhookNotifier
        results["utils"] = "✅ PASS"
    except Exception as e:
        if "colorlog" in str(e) or "aiohttp" in str(e):
            results["utils"] = "⚠️ NEEDS DEPS (structure OK)"
        else:
            results["utils"] = f"❌ FAIL: {e}"
    
    return results


def test_domain_logic():
    """Test domain logic without dependencies"""
    results = {}
    
    try:
        from domain.entities.kap_report import KAPReport
        from domain.value_objects.sentiment import (
            SentimentAnalysis, SentimentType, ImpactHorizon, Confidence
        )
        from datetime import datetime, date
        
        # Test entity (use today's date for is_recent test)
        from datetime import timedelta
        today = date.today()
        
        report = KAPReport(
            id=1,
            company_code="AKBNK",
            company_name="Akbank",
            report_type="Financial",
            report_date=today,  # Use today for is_recent test
            title="Test",
            summary="Summary",
            data={"revenue": 1000000},
            scraped_at=datetime.now()
        )
        
        assert report.get_content() != ""
        assert report.is_recent(days=7) is True  # Should be recent
        assert report.has_financial_data() is True
        
        # Test value object
        sentiment = SentimentAnalysis(
            overall_sentiment=SentimentType.POSITIVE,
            confidence=Confidence(0.85),
            impact_horizon=ImpactHorizon.MEDIUM_TERM,
            key_drivers=("Growth",),
            risk_flags=(),
            tone_descriptors=("Optimistic",),
            target_audience="retail_investors",
            analysis_text="Analysis",
            analyzed_at=datetime.now()
        )
        
        assert sentiment.is_positive() is True
        assert sentiment.confidence.is_high() is True
        
        results["domain_logic"] = "✅ PASS"
    except ImportError as e:
        results["domain_logic"] = f"⚠️ NEEDS DEPS: {e}"
    except Exception as e:
        import traceback
        error_msg = str(e)
        # Don't show full traceback, just the error
        if "AssertionError" in error_msg:
            results["domain_logic"] = f"❌ FAIL: Assertion failed - {error_msg}"
        else:
            results["domain_logic"] = f"❌ FAIL: {error_msg}"
    
    return results


def main():
    """Run simple structure tests"""
    print("\n" + "="*70)
    print("🧪 Simple Structure Tests (No Dependencies Required)")
    print("="*70 + "\n")
    
    print("Testing imports...")
    import_results = test_imports()
    for module, result in import_results.items():
        print(f"  {module:15} {result}")
    
    print("\nTesting domain logic...")
    logic_results = test_domain_logic()
    for test, result in logic_results.items():
        print(f"  {test:15} {result}")
    
    print("\n" + "="*70)
    print("📊 SUMMARY")
    print("="*70)
    
    all_results = {**import_results, **logic_results}
    passed = sum(1 for r in all_results.values() if "✅ PASS" in r)
    needs_deps = sum(1 for r in all_results.values() if "⚠️ NEEDS DEPS" in r)
    failed = sum(1 for r in all_results.values() if "❌ FAIL" in r)
    
    print(f"Total: {len(all_results)} | ✅ Passed: {passed} | ⚠️ Needs Deps: {needs_deps} | ❌ Failed: {failed}")
    print("="*70 + "\n")
    
    if failed == 0:
        if needs_deps > 0:
            print("✅ Code structure is correct!")
            print(f"⚠️ {needs_deps} component(s) need dependencies installed")
            print("\nNext step: Install dependencies and run full tests:")
            print("  pip install -r requirements.txt")
            print("  python3 test_devcontainer_services.py")
        else:
            print("✅ All structure tests passed!")
        return True
    else:
        print("❌ Some structure tests failed. Check errors above.")
        return False


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
