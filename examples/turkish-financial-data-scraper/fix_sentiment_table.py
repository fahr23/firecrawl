#!/usr/bin/env python3
"""
Fix sentiment table by dropping and recreating it
"""
import sys
import psycopg2
from psycopg2 import sql
from database.db_manager import DatabaseManager
from config import config

def main():
    """Drop and recreate sentiment table"""
    try:
        # Initialize database manager
        db_manager = DatabaseManager()
        
        print("🔧 Starting sentiment table fix...")
        
        # Get connection
        conn = db_manager.get_connection()
        
        try:
            cursor = conn.cursor()
            
            # Drop existing sentiment table
            print("🗑️ Dropping existing sentiment table...")
            cursor.execute(sql.SQL('''
                DROP TABLE IF EXISTS {}.kap_report_sentiment CASCADE
            ''').format(sql.Identifier(config.database.schema)))
            
            # Recreate sentiment table
            print("🏗️ Creating new sentiment table...")
            cursor.execute(sql.SQL('''
                CREATE TABLE {}.kap_report_sentiment (
                    id SERIAL PRIMARY KEY,
                    report_id INTEGER REFERENCES {}.kap_reports(id) ON DELETE CASCADE,
                    overall_sentiment VARCHAR(20) NOT NULL,
                    confidence REAL CHECK (confidence >= 0 AND confidence <= 1),
                    impact_horizon VARCHAR(20),
                    key_drivers JSONB,
                    risk_flags JSONB,
                    tone_descriptors JSONB,
                    target_audience VARCHAR(50),
                    analysis_text TEXT,
                    analyzed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE(report_id)
                )
            ''').format(
                sql.Identifier(config.database.schema),
                sql.Identifier(config.database.schema)
            ))
            
            # Create indexes
            print("📊 Creating indexes...")
            cursor.execute(sql.SQL('''
                CREATE INDEX idx_sentiment_report_id 
                ON {}.kap_report_sentiment(report_id)
            ''').format(sql.Identifier(config.database.schema)))
            
            cursor.execute(sql.SQL('''
                CREATE INDEX idx_sentiment_overall 
                ON {}.kap_report_sentiment(overall_sentiment)
            ''').format(sql.Identifier(config.database.schema)))
            
            cursor.execute(sql.SQL('''
                CREATE INDEX idx_sentiment_analyzed_at 
                ON {}.kap_report_sentiment(analyzed_at)
            ''').format(sql.Identifier(config.database.schema)))
            
            # Commit changes
            conn.commit()
            
            # Verify table exists
            cursor.execute(sql.SQL('''
                SELECT COUNT(*) FROM information_schema.tables 
                WHERE table_schema = %s AND table_name = %s
            '''), (config.database.schema, 'kap_report_sentiment'))
            
            table_count = cursor.fetchone()[0]
            if table_count == 1:
                print("✅ Sentiment table created successfully!")
            else:
                print("❌ Failed to create sentiment table")
                
        except Exception as e:
            print(f"❌ Error: {e}")
            conn.rollback()
            return False
        finally:
            db_manager.return_connection(conn)
            
        return True
        
    except Exception as e:
        print(f"❌ Failed to fix sentiment table: {e}")
        return False

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)