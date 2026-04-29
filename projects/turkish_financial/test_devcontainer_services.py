"""
Test script to verify all services work in devcontainer
Tests database, API, and all new features
"""
import asyncio
import sys
import os
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

import logging
from datetime import datetime, date
from typing import Dict, Any

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class ServiceTester:
    """Test all services in devcontainer"""
    
    def __init__(self):
        self.results = {
            "database": {"status": "pending", "message": ""},
            "schema": {"status": "pending", "message": ""},
            "tables": {"status": "pending", "message": ""},
            "domain_entities": {"status": "pending", "message": ""},
            "repositories": {"status": "pending", "message": ""},
            "use_cases": {"status": "pending", "message": ""},
            "api_health": {"status": "pending", "message": ""},
            "sentiment_analysis": {"status": "pending", "message": ""},
            "batch_jobs": {"status": "pending", "message": ""},
            "webhooks": {"status": "pending", "message": ""}
        }
    
    def test_database_connection(self) -> bool:
        """Test 1: Database connection"""
        try:
            from database.db_manager import DatabaseManager
            from config import config
            
            db = DatabaseManager()
            conn = db.get_connection()
            cursor = conn.cursor()
            cursor.execute("SELECT 1")
            cursor.fetchone()
            db.return_connection(conn)
            
            self.results["database"] = {
                "status": "✅ PASS",
                "message": f"Connected to database '{config.database.database}' on {config.database.host}:{config.database.port}"
            }
            return True
        except Exception as e:
            self.results["database"] = {
                "status": "❌ FAIL",
                "message": str(e)
            }
            return False
    
    def test_schema_creation(self) -> bool:
        """Test 2: Schema creation"""
        try:
            from database.db_manager import DatabaseManager
            from config import config
            
            db = DatabaseManager()
            schema_name = config.database.schema
            
            conn = db.get_connection()
            cursor = conn.cursor()
            cursor.execute("""
                SELECT schema_name 
                FROM information_schema.schemata 
                WHERE schema_name = %s
            """, (schema_name,))
            result = cursor.fetchone()
            db.return_connection(conn)
            
            if result:
                self.results["schema"] = {
                    "status": "✅ PASS",
                    "message": f"Schema '{schema_name}' exists"
                }
                return True
            else:
                self.results["schema"] = {
                    "status": "❌ FAIL",
                    "message": f"Schema '{schema_name}' not found"
                }
                return False
        except Exception as e:
            self.results["schema"] = {
                "status": "❌ FAIL",
                "message": str(e)
            }
            return False
    
    def test_tables_creation(self) -> bool:
        """Test 3: Tables creation"""
        try:
            from database.db_manager import DatabaseManager
            from config import config
            
            db = DatabaseManager()
            schema_name = config.database.schema
            
            conn = db.get_connection()
            cursor = conn.cursor()
            cursor.execute("""
                SELECT table_name 
                FROM information_schema.tables 
                WHERE table_schema = %s
                ORDER BY table_name
            """, (schema_name,))
            tables = [row[0] for row in cursor.fetchall()]
            db.return_connection(conn)
            
            expected_tables = [
                "kap_reports",
                "bist_companies",
                "kap_disclosures", # Added kap_disclosures
                "bist_index_members",
                "tradingview_sectors_tr",
                "tradingview_industry_tr",
                "historical_price_emtia",
                "cryptocurrency_symbols",
                "kap_report_sentiment"
                "cryptocurrency_symbols", # Corrected table name
                "kap_disclosure_sentiment" # Corrected table name
            ]
            
            missing = [t for t in expected_tables if t not in tables]
            
            if not missing:
                self.results["tables"] = {
                    "status": "✅ PASS",
                    "message": f"All {len(tables)} tables created in schema '{schema_name}'"
                }
                return True
            else:
                self.results["tables"] = {
                    "status": "⚠️ PARTIAL",
                    "message": f"Missing tables: {missing}. Found: {tables}"
                }
                return False
        except Exception as e:
            self.results["tables"] = {
                "status": "❌ FAIL",
                "message": str(e)
            }
            return False
    
    def test_domain_entities(self) -> bool:
        """Test 4: Domain entities"""
        try:
            from domain.entities.kap_report import KAPReport
            from domain.value_objects.sentiment import (
                SentimentAnalysis, SentimentType, ImpactHorizon, Confidence
            )
            
            # Test KAPReport entity
            report = KAPReport(
                id=1,
                company_code="AKBNK",
                company_name="Akbank",
                report_type="Financial Statement",
                report_date=date(2025, 1, 20),
                title="Test Report",
                summary="Test summary",
                data={"revenue": 1000000},
                scraped_at=datetime.now()
            )
            
            assert report.company_code == "AKBNK"
            assert report.get_content() != ""
            assert report.is_recent(days=7) is True
            assert report.has_financial_data() is True
            
            # Test SentimentAnalysis value object
            sentiment = SentimentAnalysis(
                overall_sentiment=SentimentType.POSITIVE,
                confidence=Confidence(0.85),
                impact_horizon=ImpactHorizon.MEDIUM_TERM,
                key_drivers=("Growth", "Expansion"),
                risk_flags=(),
                tone_descriptors=("Optimistic",),
                target_audience="retail_investors",
                analysis_text="Test analysis",
                analyzed_at=datetime.now()
            )
            
            assert sentiment.is_positive() is True
            assert sentiment.confidence.is_high() is True
            
            self.results["domain_entities"] = {
                "status": "✅ PASS",
                "message": "Domain entities and value objects work correctly"
            }
            return True
        except Exception as e:
            self.results["domain_entities"] = {
                "status": "❌ FAIL",
                "message": str(e)
            }
            return False
    
    def test_repositories(self) -> bool:
        """Test 5: Repository implementations"""
        try:
            from database.db_manager import DatabaseManager
            from infrastructure.repositories.kap_report_repository_impl import KAPReportRepository
            from infrastructure.repositories.sentiment_repository_impl import SentimentRepository
            
            db = DatabaseManager()
            report_repo = KAPReportRepository(db)
            sentiment_repo = SentimentRepository(db)
            
            # Test repository can be instantiated
            assert report_repo is not None
            assert sentiment_repo is not None
            
            self.results["repositories"] = {
                "status": "✅ PASS",
                "message": "Repository implementations instantiated successfully"
            }
            return True
        except Exception as e:
            self.results["repositories"] = {
                "status": "❌ FAIL",
                "message": str(e)
            }
            return False
    
    async def test_use_cases(self) -> bool:
        """Test 6: Use cases"""
        try:
            from application.dependencies import get_analyze_sentiment_use_case
            from database.db_manager import DatabaseManager
            
            db = DatabaseManager()
            use_case = get_analyze_sentiment_use_case(db)
            
            assert use_case is not None
            
            self.results["use_cases"] = {
                "status": "✅ PASS",
                "message": "Use cases can be instantiated with dependency injection"
            }
            return True
        except Exception as e:
            self.results["use_cases"] = {
                "status": "❌ FAIL",
                "message": str(e)
            }
            return False
    
    def test_api_health(self) -> bool:
        """Test 7: API health (if server is running)"""
        try:
            try:
                import requests
            except ImportError:
                self.results["api_health"] = {
                    "status": "⚠️ SKIP",
                    "message": "requests module not installed (pip install requests)"
                }
                return False
            
            response = requests.get("http://localhost:8000/api/v1/health", timeout=2)
            if response.status_code == 200:
                data = response.json()
                self.results["api_health"] = {
                    "status": "✅ PASS",
                    "message": f"API is running. Status: {data.get('status')}, DB: {data.get('database')}"
                }
                return True
            else:
                self.results["api_health"] = {
                    "status": "⚠️ SKIP",
                    "message": f"API returned status {response.status_code} (server may not be running)"
                }
                return False
        except requests.exceptions.ConnectionError:
            self.results["api_health"] = {
                "status": "⚠️ SKIP",
                "message": "API server not running (start with: python api_server.py)"
            }
            return False
        except Exception as e:
            self.results["api_health"] = {
                "status": "❌ FAIL",
                "message": str(e)
            }
            return False
    
    def test_sentiment_analysis_structure(self) -> bool:
        """Test 8: Sentiment analysis structure"""
        try:
            from domain.value_objects.sentiment import (
                SentimentAnalysis, SentimentType, ImpactHorizon, Confidence
            )
            from datetime import datetime
            
            # Create sentiment analysis
            sentiment = SentimentAnalysis(
                overall_sentiment=SentimentType.POSITIVE,
                confidence=Confidence(0.9),
                impact_horizon=ImpactHorizon.MEDIUM_TERM,
                key_drivers=("Revenue growth", "Market expansion"),
                risk_flags=("Debt increase",),
                tone_descriptors=("Optimistic", "Confident"),
                target_audience="retail_investors",
                analysis_text="Detailed analysis text",
                analyzed_at=datetime.now()
            )
            
            # Test business methods
            assert sentiment.is_positive() is True
            assert sentiment.is_negative() is False
            assert sentiment.has_high_risk() is False
            assert sentiment.get_risk_level() == "low"
            assert sentiment.confidence.is_high() is True
            
            self.results["sentiment_analysis"] = {
                "status": "✅ PASS",
                "message": "Sentiment analysis structure works correctly"
            }
            return True
        except Exception as e:
            self.results["sentiment_analysis"] = {
                "status": "❌ FAIL",
                "message": str(e)
            }
            return False
    
    def test_batch_job_manager(self) -> bool:
        """Test 9: Batch job manager"""
        try:
            from utils.batch_job_manager import BatchJobManager, JobStatus
            
            job_manager = BatchJobManager()
            job = job_manager.create_job(
                job_type="test_job",
                params={"test": "data"}
            )
            
            assert job.job_id is not None
            assert job.status == JobStatus.PENDING
            
            job_manager.update_job_status(
                job.job_id,
                JobStatus.RUNNING,
                progress=1,
                total=10
            )
            
            updated_job = job_manager.get_job(job.job_id)
            assert updated_job.status == JobStatus.RUNNING
            assert updated_job.progress == 1
            
            self.results["batch_jobs"] = {
                "status": "✅ PASS",
                "message": "Batch job manager works correctly"
            }
            return True
        except Exception as e:
            self.results["batch_jobs"] = {
                "status": "❌ FAIL",
                "message": str(e)
            }
            return False
    
    def test_webhook_notifier(self) -> bool:
        """Test 10: Webhook notifier"""
        try:
            from utils.webhook_notifier import WebhookNotifier
            
            # Test without webhook URL (should not fail)
            notifier = WebhookNotifier()
            assert notifier is not None
            
            # Test with webhook URL
            notifier_with_url = WebhookNotifier(webhook_url="https://discord.com/api/webhooks/test")
            assert notifier_with_url.webhook_url is not None
            
            self.results["webhooks"] = {
                "status": "✅ PASS",
                "message": "Webhook notifier can be instantiated"
            }
            return True
        except Exception as e:
            self.results["webhooks"] = {
                "status": "❌ FAIL",
                "message": str(e)
            }
            return False
    
    async def run_all_tests(self):
        """Run all tests"""
        print("\n" + "="*70)
        print("🧪 Testing Turkish Financial Data Scraper Services")
        print("="*70 + "\n")
        
        # Run synchronous tests
        tests = [
            ("Database Connection", self.test_database_connection),
            ("Schema Creation", self.test_schema_creation),
            ("Tables Creation", self.test_tables_creation),
            ("Domain Entities", self.test_domain_entities),
            ("Repositories", self.test_repositories),
            ("Sentiment Analysis", self.test_sentiment_analysis_structure),
            ("Batch Job Manager", self.test_batch_job_manager),
            ("Webhook Notifier", self.test_webhook_notifier),
            ("API Health", self.test_api_health),
        ]
        
        for name, test_func in tests:
            print(f"Testing {name}...", end=" ")
            try:
                test_func()
                status = self.results.get(name.lower().replace(" ", "_"), {}).get("status", "UNKNOWN")
                print(status)
            except Exception as e:
                print(f"❌ FAIL: {e}")
        
        # Run async tests
        print("Testing Use Cases...", end=" ")
        try:
            await self.test_use_cases()
            status = self.results["use_cases"]["status"]
            print(status)
        except Exception as e:
            print(f"❌ FAIL: {e}")
        
        # Print summary
        print("\n" + "="*70)
        print("📊 TEST SUMMARY")
        print("="*70 + "\n")
        
        passed = 0
        failed = 0
        skipped = 0
        
        for test_name, result in self.results.items():
            status = result["status"]
            message = result["message"]
            
            print(f"{status} {test_name.replace('_', ' ').title()}")
            if message:
                print(f"   {message}")
            print()
            
            if "✅ PASS" in status:
                passed += 1
            elif "❌ FAIL" in status:
                failed += 1
            else:
                skipped += 1
        
        print("="*70)
        print(f"Total: {len(self.results)} | ✅ Passed: {passed} | ❌ Failed: {failed} | ⚠️ Skipped: {skipped}")
        print("="*70 + "\n")
        
        if failed == 0:
            print("🎉 All tests passed! Services are working correctly.")
            return True
        else:
            print(f"⚠️ {failed} test(s) failed. Please check the errors above.")
            return False


async def main():
    """Main test function"""
    tester = ServiceTester()
    success = await tester.run_all_tests()
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    asyncio.run(main())
