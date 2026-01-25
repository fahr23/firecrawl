"""
Database Manager for Turkish Financial Data Scraper
"""
import logging
import json
import psycopg2
from psycopg2 import pool, sql
from psycopg2.extras import RealDictCursor, Json
from typing import Dict, Any, List, Optional
from config import config

logger = logging.getLogger(__name__)


class DatabaseManager:
    """Database connection and operations manager"""
    
    def __init__(self):
        """Initialize database connection pool"""
        try:
            self.schema = config.database.schema
            self.pool = pool.SimpleConnectionPool(
                minconn=1,
                maxconn=config.database.pool_size,
                **config.database.get_connection_params()
            )
            logger.info(f"Database connection pool created with schema: {self.schema}")
            self._create_schema()
            self._create_tables()
        except Exception as e:
            logger.error(f"Failed to create database pool: {e}")
            raise
    
    def _create_schema(self):
        """Create the schema if it doesn't exist"""
        # Get connection directly from pool (don't use get_connection to avoid circular dependency)
        conn = self.pool.getconn()
        try:
            cursor = conn.cursor()
            # Create schema if it doesn't exist
            cursor.execute(sql.SQL("CREATE SCHEMA IF NOT EXISTS {}").format(
                sql.Identifier(self.schema)
            ))
            conn.commit()
            logger.info(f"Schema '{self.schema}' created/verified")
        except Exception as e:
            logger.error(f"Error creating schema: {e}")
            conn.rollback()
            raise
        finally:
            self.pool.putconn(conn)
    
    def _create_tables(self):
        """Create necessary database tables"""
        conn = self.get_connection()
        try:
            cursor = conn.cursor()
            
            # Set search_path for this connection
            cursor.execute(sql.SQL("SET search_path TO {}, public").format(
                sql.Identifier(self.schema)
            ))
            
            # KAP Reports table
            cursor.execute(sql.SQL('''
                CREATE TABLE IF NOT EXISTS {}.kap_reports (
                    id SERIAL PRIMARY KEY,
                    company_code VARCHAR(10),
                    company_name VARCHAR(255),
                    report_type VARCHAR(100),
                    report_date DATE,
                    title TEXT,
                    summary TEXT,
                    data JSONB,
                    scraped_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE(company_code, report_date, title)
                )
            ''').format(sql.Identifier(self.schema)))
            
            # BIST Companies table
            cursor.execute(sql.SQL('''
                CREATE TABLE IF NOT EXISTS {}.bist_companies (
                    id SERIAL PRIMARY KEY,
                    code VARCHAR(10) UNIQUE,
                    name VARCHAR(255),
                    symbol VARCHAR(20),
                    sector VARCHAR(100),
                    scraped_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''').format(sql.Identifier(self.schema)))
            
            # BIST Index Members table
            cursor.execute(sql.SQL('''
                CREATE TABLE IF NOT EXISTS {}.bist_index_members (
                    id SERIAL PRIMARY KEY,
                    index_name VARCHAR(100),
                    company_code VARCHAR(10),
                    company_name VARCHAR(255),
                    scraped_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE(index_name, company_code)
                )
            ''').format(sql.Identifier(self.schema)))
            
            # TradingView Sectors table
            cursor.execute(sql.SQL('''
                CREATE TABLE IF NOT EXISTS {}.tradingview_sectors_tr (
                    id SERIAL PRIMARY KEY,
                    sector_name VARCHAR(255),
                    stock_symbol VARCHAR(50),
                    stock_name VARCHAR(255),
                    scraped_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE(sector_name, stock_symbol)
                )
            ''').format(sql.Identifier(self.schema)))
            
            # TradingView Industries table
            cursor.execute(sql.SQL('''
                CREATE TABLE IF NOT EXISTS {}.tradingview_industry_tr (
                    id SERIAL PRIMARY KEY,
                    industry_name VARCHAR(255),
                    stock_symbol VARCHAR(50),
                    stock_name VARCHAR(255),
                    scraped_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE(industry_name, stock_symbol)
                )
            ''').format(sql.Identifier(self.schema)))
            
            # Commodity Prices table
            cursor.execute(sql.SQL('''
                CREATE TABLE IF NOT EXISTS {}.historical_price_emtia (
                    id SERIAL PRIMARY KEY,
                    commodity_type VARCHAR(10),
                    date DATE,
                    price REAL,
                    currency VARCHAR(10),
                    scraped_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE(commodity_type, date)
                )
            ''').format(sql.Identifier(self.schema)))
            
            # Cryptocurrency Symbols table
            cursor.execute(sql.SQL('''
                CREATE TABLE IF NOT EXISTS {}.cryptocurrency_symbols (
                    id SERIAL PRIMARY KEY,
                    symbol VARCHAR(50) UNIQUE,
                    name VARCHAR(255),
                    price REAL,
                    scraped_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''').format(sql.Identifier(self.schema)))
            
            # Sentiment Analysis table
            cursor.execute(sql.SQL('''
                CREATE TABLE IF NOT EXISTS {}.kap_report_sentiment (
                    id SERIAL PRIMARY KEY,
                    report_id INTEGER REFERENCES {}.kap_reports(id) ON DELETE CASCADE,
                    overall_sentiment VARCHAR(20) NOT NULL,
                    confidence REAL DEFAULT 0.0,
                    impact_horizon VARCHAR(20),
                    key_drivers TEXT[],
                    risk_flags TEXT[],
                    tone_descriptors TEXT[],
                    target_audience VARCHAR(50),
                    analysis_text TEXT,
                    risk_level VARCHAR(20),
                    summary TEXT,
                    raw_analysis JSONB,
                    analyzed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE(report_id)
                )
            ''').format(
                sql.Identifier(self.schema),
                sql.Identifier(self.schema)
            ))
            
            # Create indexes for faster queries
            cursor.execute(sql.SQL('''
                CREATE INDEX IF NOT EXISTS idx_sentiment_report_id 
                ON {}.kap_report_sentiment(report_id)
            ''').format(sql.Identifier(self.schema)))
            
            cursor.execute(sql.SQL('''
                CREATE INDEX IF NOT EXISTS idx_sentiment_overall 
                ON {}.kap_report_sentiment(overall_sentiment)
            ''').format(sql.Identifier(self.schema)))
            
            cursor.execute(sql.SQL('''
                CREATE INDEX IF NOT EXISTS idx_sentiment_analyzed_at 
                ON {}.kap_report_sentiment(analyzed_at)
            ''').format(sql.Identifier(self.schema)))
            
            conn.commit()
            logger.info("Database tables created/verified")
            
        except Exception as e:
            logger.error(f"Error creating tables: {e}")
            conn.rollback()
            raise
        finally:
            self.return_connection(conn)
    
    def get_connection(self):
        """Get a connection from the pool and set search_path"""
        try:
            conn = self.pool.getconn()
            # Set search_path for this connection to use our schema
            cursor = conn.cursor()
            cursor.execute(sql.SQL("SET search_path TO {}, public").format(
                sql.Identifier(self.schema)
            ))
            cursor.close()
            return conn
        except Exception as e:
            logger.error(f"Error getting connection: {e}")
            raise
    
    def return_connection(self, conn):
        """Return a connection to the pool"""
        try:
            self.pool.putconn(conn)
        except Exception as e:
            logger.error(f"Error returning connection: {e}")
    
    def insert_data(
        self,
        table_name: str,
        data: Dict[str, Any]
    ) -> bool:
        """
        Insert data into a table
        
        Args:
            table_name: Target table name
            data: Data dictionary to insert
            
        Returns:
            Success status
        """
        conn = self.get_connection()
        try:
            cursor = conn.cursor()
            
            # Build INSERT query with ON CONFLICT DO UPDATE
            columns = list(data.keys())
            # Convert dict values to Json objects for JSONB columns
            values = []
            for col in columns:
                val = data[col]
                # If value is dict or list, wrap in psycopg2.extras.Json for JSONB
                if isinstance(val, (dict, list)):
                    values.append(Json(val))
                else:
                    values.append(val)
            
            query = sql.SQL(
                "INSERT INTO {} ({}) VALUES ({}) "
                "ON CONFLICT DO NOTHING"
            ).format(
                sql.Identifier(table_name),
                sql.SQL(', ').join(map(sql.Identifier, columns)),
                sql.SQL(', ').join(sql.Placeholder() * len(columns))
            )
            
            cursor.execute(query, values)
            conn.commit()
            
            logger.debug(f"Inserted data into {table_name}")
            return True
            
        except Exception as e:
            logger.error(f"Error inserting data into {table_name}: {e}")
            conn.rollback()
            return False
        finally:
            self.return_connection(conn)
    
    def bulk_insert(
        self,
        table_name: str,
        data_list: List[Dict[str, Any]]
    ) -> bool:
        """
        Bulk insert data into a table
        
        Args:
            table_name: Target table name
            data_list: List of data dictionaries
            
        Returns:
            Success status
        """
        if not data_list:
            return True
        
        conn = self.get_connection()
        try:
            cursor = conn.cursor()
            
            # Get columns from first item
            columns = list(data_list[0].keys())
            
            # Build INSERT query
            query = sql.SQL(
                "INSERT INTO {}.{} ({}) VALUES ({}) "
                "ON CONFLICT DO NOTHING"
            ).format(
                sql.Identifier(self.schema),
                sql.Identifier(table_name),
                sql.SQL(', ').join(map(sql.Identifier, columns)),
                sql.SQL(', ').join(sql.Placeholder() * len(columns))
            )
            
            # Execute for each row
            for data in data_list:
                values = [data.get(col) for col in columns]
                cursor.execute(query, values)
            
            conn.commit()
            logger.info(f"Bulk inserted {len(data_list)} rows into {table_name}")
            return True
            
        except Exception as e:
            logger.error(f"Error bulk inserting into {table_name}: {e}")
            conn.rollback()
            return False
        finally:
            self.return_connection(conn)
    
    def query(
        self,
        query: str,
        params: Optional[tuple] = None
    ) -> List[Dict[str, Any]]:
        """
        Execute a SELECT query
        
        Args:
            query: SQL query string
            params: Query parameters
            
        Returns:
            List of result dictionaries
        """
        conn = self.get_connection()
        try:
            cursor = conn.cursor(cursor_factory=RealDictCursor)
            cursor.execute(query, params or ())
            results = cursor.fetchall()
            return [dict(row) for row in results]
        except Exception as e:
            logger.error(f"Error executing query: {e}")
            return []
        finally:
            self.return_connection(conn)
    
    def execute(
        self,
        query: str,
        params: Optional[tuple] = None
    ) -> bool:
        """
        Execute a non-SELECT query
        
        Args:
            query: SQL query string
            params: Query parameters
            
        Returns:
            Success status
        """
        conn = self.get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute(query, params or ())
            conn.commit()
            return True
        except Exception as e:
            logger.error(f"Error executing query: {e}")
            conn.rollback()
            return False
        finally:
            self.return_connection(conn)
    
    def close_all(self):
        """Close all connections in the pool"""
        if self.pool:
            self.pool.closeall()
            logger.info("All database connections closed")
