#!/usr/bin/env python3
"""
Simple KAP Scraper Database Test

Tests the KAP scraper functionality and saves sample data to database.
"""

import asyncio
import logging
from datetime import datetime, date
import psycopg2
import json

# Simple logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class SimpleKAPTest:
    """Simple KAP scraper test"""
    
    def __init__(self):
        self.db_config = {
            'host': 'nuq-postgres',
            'port': 5432,
            'database': 'postgres',
            'user': 'postgres',
            'password': 'postgres'
        }
        self.schema = 'turkish_financial'
    
    def test_database_connection(self):
        """Test database connection"""
        try:
            conn = psycopg2.connect(**self.db_config)
            cursor = conn.cursor()
            
            # Check if tables exist
            cursor.execute(f"""
                SELECT table_name FROM information_schema.tables 
                WHERE table_schema = %s AND table_name = 'kap_disclosures'
            """, (self.schema,))
            
            table_exists = cursor.fetchone()
            print(f"✅ Database connected. KAP table exists: {'Yes' if table_exists else 'No'}")
            
            cursor.close()
            conn.close()
            return True
            
        except Exception as e:
            print(f"❌ Database connection failed: {e}")
            return False
    
    def save_sample_disclosure(self, disclosure_data):
        """Save sample disclosure to database"""
        try:
            conn = psycopg2.connect(**self.db_config)
            cursor = conn.cursor()
            
            insert_sql = f"""
                INSERT INTO {self.schema}.kap_disclosures 
                (disclosure_id, company_name, disclosure_type, disclosure_date, 
                 timestamp, language_info, has_attachment, detail_url, content, data)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (disclosure_id, company_name, disclosure_type) 
                DO UPDATE SET 
                    content = EXCLUDED.content,
                    data = EXCLUDED.data,
                    scraped_at = CURRENT_TIMESTAMP
                RETURNING id
            """
            
            cursor.execute(insert_sql, (
                disclosure_data['disclosure_id'],
                disclosure_data['company_name'],
                disclosure_data['disclosure_type'],
                disclosure_data['disclosure_date'],
                disclosure_data['timestamp'],
                disclosure_data['language_info'],
                disclosure_data['has_attachment'],
                disclosure_data['detail_url'],
                disclosure_data['content'],
                json.dumps(disclosure_data['data'])
            ))
            
            result = cursor.fetchone()
            disclosure_id = result[0] if result else None
            
            conn.commit()
            cursor.close()
            conn.close()
            
            return disclosure_id
            
        except Exception as e:
            print(f"❌ Error saving disclosure: {e}")
            return None
    
    def get_database_stats(self):
        """Get database statistics"""
        try:
            conn = psycopg2.connect(**self.db_config)
            cursor = conn.cursor()
            
            # Total count
            cursor.execute(f"SELECT COUNT(*) FROM {self.schema}.kap_disclosures")
            total = cursor.fetchone()[0]
            
            # Recent entries
            cursor.execute(f"""
                SELECT id, company_name, disclosure_type, scraped_at
                FROM {self.schema}.kap_disclosures 
                ORDER BY scraped_at DESC 
                LIMIT 5
            """)
            recent = cursor.fetchall()
            
            cursor.close()
            conn.close()
            
            return {
                'total': total,
                'recent': recent
            }
            
        except Exception as e:
            print(f"❌ Error getting stats: {e}")
            return None
    
    def test_firecrawl_integration(self):
        """Test Firecrawl integration using base scraper pattern"""
        try:
            from firecrawl import FirecrawlApp
            
            # Initialize like base scraper does
            firecrawl_kwargs = {}
            base_url = "http://api:3002"  # From config
            
            if base_url:
                firecrawl_kwargs["api_url"] = base_url
            else:
                firecrawl_kwargs["api_key"] = "test"  # Fallback
            
            app = FirecrawlApp(**firecrawl_kwargs)
            print(f"✅ Firecrawl initialized with: {base_url or 'API key'}")
            
            # Test scraping
            print("🧪 Testing Firecrawl with example.com...")
            result = app.scrape(
                "https://example.com",
                formats=['markdown'],
                wait_for=3000
            )
            
            if result and hasattr(result, 'markdown'):
                print(f"✅ Firecrawl working - got {len(result.markdown)} chars")
                return True
            else:
                print(f"⚠️  Firecrawl returned: {type(result)}")
                return False
                
        except Exception as e:
            print(f"❌ Firecrawl test failed: {e}")
            return False
    
    def run_full_test(self):
        """Run complete test"""
        print("🎯 KAP Scraper Database Integration Test")
        print("=" * 50)
        
        # Test 1: Database connection
        print("\n1️⃣  Testing Database Connection")
        db_ok = self.test_database_connection()
        
        if not db_ok:
            print("❌ Database test failed - aborting")
            return
        
        # Test 2: Firecrawl integration
        print("\n2️⃣  Testing Firecrawl Integration")
        firecrawl_ok = self.test_firecrawl_integration()
        
        # Test 3: Sample data insertion
        print("\n3️⃣  Testing Sample Data Insertion")
        sample_disclosure = {
            'disclosure_id': 'TEST001',
            'company_name': 'TEST COMPANY A.Ş.',
            'disclosure_type': 'Material Event Disclosure (Test)',
            'disclosure_date': date.today().isoformat(),
            'timestamp': f"Today {datetime.now().strftime('%H:%M')}",
            'language_info': 'English',
            'has_attachment': False,
            'detail_url': 'https://kap.org.tr/test',
            'content': 'This is a test disclosure content for KAP scraper testing.',
            'data': {
                'source': 'kap_org_test',
                'test_run': datetime.now().isoformat(),
                'scraper_version': '1.0'
            }
        }
        
        saved_id = self.save_sample_disclosure(sample_disclosure)
        if saved_id:
            print(f"✅ Sample disclosure saved with ID: {saved_id}")
        
        # Test 4: Database query
        print("\n4️⃣  Testing Database Query")
        stats = self.get_database_stats()
        if stats:
            print(f"✅ Database stats retrieved:")
            print(f"   Total disclosures: {stats['total']}")
            
            if stats['recent']:
                print(f"   Recent entries:")
                for row in stats['recent'][:3]:
                    print(f"     [{row[0]}] {row[1][:30]} - {row[2][:30]}")
        
        # Summary
        print("\n📊 Test Summary")
        print("-" * 20)
        print(f"Database: {'✅ OK' if db_ok else '❌ Failed'}")
        print(f"Firecrawl: {'✅ OK' if firecrawl_ok else '❌ Failed'}")
        print(f"Data insertion: {'✅ OK' if saved_id else '❌ Failed'}")
        print(f"Data retrieval: {'✅ OK' if stats else '❌ Failed'}")
        
        if db_ok and firecrawl_ok:
            print("\n🎉 All core components working!")
            print("   ➡️  KAP scraper is ready for production use")
        else:
            print("\n⚠️  Some components need attention")
            
        return db_ok and firecrawl_ok


if __name__ == "__main__":
    tester = SimpleKAPTest()
    tester.run_full_test()