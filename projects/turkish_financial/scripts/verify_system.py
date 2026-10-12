import os
import sys
import logging
from pathlib import Path

# Add project root to path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from fastapi.testclient import TestClient
from api.main import app
from database.db_manager import DatabaseManager

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)

def verify_database():
    logger.info("=== Verifying Database Integrity ===")
    try:
        db = DatabaseManager()
        conn = db.get_connection()
        try:
            cursor = conn.cursor()
            
            # Check schema exists
            cursor.execute("SELECT schema_name FROM information_schema.schemata WHERE schema_name = 'turkish_financial'")
            if not cursor.fetchone():
                logger.error("Schema 'turkish_financial' does not exist!")
                return False
                
            cursor.execute("SET search_path TO turkish_financial,public;")
            
            # List of expected tables
            expected_tables = [
                "kap_disclosures",
                "kap_disclosure_sentiment",
                "bist_companies",
                "bist_index_members",
                "tradingview_sectors_tr",
                "tradingview_industry_tr",
                "commodity_prices"
            ]
            
            all_passed = True
            for table in expected_tables:
                cursor.execute(f"SELECT EXISTS (SELECT FROM information_schema.tables WHERE table_schema = 'turkish_financial' AND table_name = '{table}')")
                if cursor.fetchone()[0]:
                    cursor.execute(f"SELECT COUNT(*) FROM {table}")
                    count = cursor.fetchone()[0]
                    logger.info(f"Table '{table}' exists. Row count: {count}")
                else:
                    logger.error(f"Table '{table}' is MISSING!")
                    all_passed = False
                    
            return all_passed
        finally:
            db.return_connection(conn)
    except Exception as e:
        logger.error(f"Database verification failed: {e}")
        return False

def verify_endpoints():
    logger.info("\n=== Verifying API Endpoints ===")
    
    # We use TestClient as a context manager to run startup events (so BIST catalog is seeded)
    all_passed = True
    with TestClient(app) as client:
        # Define endpoints to test
        endpoints_to_test = [
            ("GET", "/api/v1/health"),
            ("GET", "/api/external/v1/health"),
            ("GET", "/api/v1/reports/companies"),
            ("GET", "/api/v1/reports/kap?limit=1"),
            ("GET", "/api/v1/reports/instrument/THYAO"),
            ("GET", "/api/v1/scrapers/status"),
            ("GET", "/api/external/v1/sentiment/news/THYAO")
        ]
        
        for method, url in endpoints_to_test:
            try:
                if method == "GET":
                    response = client.get(url)
                elif method == "POST":
                    response = client.post(url)
                    
                if response.status_code == 200:
                    logger.info(f"✅ {method} {url} -> 200 OK")
                    try:
                        data = response.json()
                        # Just testing json decode
                    except Exception:
                        logger.warning(f"⚠️ {method} {url} returned non-JSON")
                else:
                    logger.error(f"❌ {method} {url} -> {response.status_code}")
                    logger.error(f"Response: {response.text}")
                    all_passed = False
            except Exception as e:
                logger.error(f"❌ {method} {url} -> FAILED with exception {e}")
                all_passed = False
                
    return all_passed

if __name__ == "__main__":
    db_ok = verify_database()
    api_ok = verify_endpoints()
    
    if db_ok and api_ok:
        logger.info("\n✅ System verification PASSED")
        sys.exit(0)
    else:
        logger.error("\n❌ System verification FAILED")
        sys.exit(1)
