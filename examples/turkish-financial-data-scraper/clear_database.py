#!/usr/bin/env python3
"""Clear the KAP disclosures database"""

import sys
import os

# Add parent directory to path to import production_kap_final
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

try:
    import psycopg2
    from psycopg2 import sql
    
    # Connect to PostgreSQL (using Docker container names)
    conn = psycopg2.connect(
        host='nuq-postgres',
        port=5432,
        database='postgres',
        user='postgres',
        password='postgres'
    )
    cursor = conn.cursor()
    
    # Clear the kap_disclosures table
    print("📊 Clearing kap_disclosures table...")
    cursor.execute("DELETE FROM kap_disclosures;")
    deleted_count = cursor.rowcount
    conn.commit()
    
    # Get count after deletion
    cursor.execute("SELECT COUNT(*) FROM kap_disclosures;")
    remaining = cursor.fetchone()[0]
    
    cursor.close()
    conn.close()
    
    print(f"✅ Deleted {deleted_count} records")
    print(f"✅ Remaining records: {remaining}")
    print("✅ Database cleared and ready for fresh scraping!")
    
except Exception as e:
    print(f"❌ Error connecting to database: {e}")
    print("\nNote: If running locally, the database might not be accessible.")
    print("The scraper will create/update the database when it runs inside Docker.")
    sys.exit(1)
