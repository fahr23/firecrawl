"""
Database Manager for Turkish Financial Data Scraper
"""
import logging
import json
import os
import time
from datetime import datetime
import psycopg2
import psycopg2.errors
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
            self.schema = config.database.db_schema
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
        """Create the schema if it doesn't exist
        
        Handles race conditions when multiple connections try to create the same schema
        simultaneously by catching UniqueViolation and treating it as success.
        """
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
        except psycopg2.errors.UniqueViolation:
            # Race condition: another connection created the schema first
            # This is fine - the schema exists, which is what we wanted
            conn.rollback()
            logger.info(f"Schema '{self.schema}' already exists (concurrent creation)")
        except psycopg2.errors.DuplicateSchema:
            # Schema already exists - this is also fine
            conn.rollback()
            logger.info(f"Schema '{self.schema}' already exists")
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
            # KAP Disclosures table (Main table for scraped data)
            cursor.execute(sql.SQL('''
                CREATE TABLE IF NOT EXISTS {}.kap_disclosures (
                    id SERIAL PRIMARY KEY,
                    disclosure_id VARCHAR(100) UNIQUE,
                    company_name VARCHAR(255),
                    disclosure_type VARCHAR(100),
                    disclosure_date DATE,
                    timestamp VARCHAR(20),
                    language_info VARCHAR(50),
                    has_attachment BOOLEAN DEFAULT FALSE,
                    detail_url TEXT,
                    pdf_url TEXT,
                    pdf_text TEXT,
                    content TEXT,
                    data JSONB,
                    scraped_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''').format(sql.Identifier(self.schema)))

            # KAP Disclosure Sentiment table
            cursor.execute(sql.SQL('''
                CREATE TABLE IF NOT EXISTS {}.kap_disclosure_sentiment (
                    id SERIAL PRIMARY KEY,
                    disclosure_id INTEGER REFERENCES {}.kap_disclosures(id) ON DELETE CASCADE,
                    overall_sentiment VARCHAR(20),
                    sentiment_score REAL DEFAULT 0.0,
                    confidence REAL DEFAULT 0.0,
                    key_sentiments TEXT,
                    analysis_notes TEXT,
                    impact_horizon VARCHAR(20),
                    key_drivers TEXT,
                    risk_flags TEXT,
                    tone_descriptors TEXT,
                    target_audience VARCHAR(50),
                    analysis_text TEXT,
                    risk_level VARCHAR(20),
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    analyzed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE(disclosure_id)
                )
            ''').format(
                sql.Identifier(self.schema),
                sql.Identifier(self.schema)
            ))

            # KAP Reports table (Legacy)
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
            cursor.execute(sql.SQL('''
                ALTER TABLE {}.bist_companies
                    ADD COLUMN IF NOT EXISTS is_active BOOLEAN NOT NULL DEFAULT TRUE
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
            
            # --- Data Contract v1.0 alignment -------------------------------
            # External Analysis Provider contract (§2) needs analyzer provenance
            # and sample size on the sentiment row, plus an exact stock_code on the
            # disclosure so instrument↔company resolution can be exact going forward.
            # ALTER ... ADD COLUMN IF NOT EXISTS is idempotent and safe for existing DBs.
            cursor.execute(sql.SQL('''
                ALTER TABLE {}.kap_disclosure_sentiment
                    ADD COLUMN IF NOT EXISTS analyzer VARCHAR(100),
                    ADD COLUMN IF NOT EXISTS sample_size INTEGER
            ''').format(sql.Identifier(self.schema)))

            cursor.execute(sql.SQL('''
                ALTER TABLE {}.kap_disclosures
                    ADD COLUMN IF NOT EXISTS stock_code VARCHAR(20)
            ''').format(sql.Identifier(self.schema)))

            cursor.execute(sql.SQL('''
                CREATE INDEX IF NOT EXISTS idx_kap_disclosures_stock_code
                ON {}.kap_disclosures(stock_code)
            ''').format(sql.Identifier(self.schema)))

            # KAP financialTable API addresses companies by mkkMemberOid; cache the
            # ticker→oid mapping here so resolve_member_oid() can avoid re-querying KAP.
            cursor.execute(sql.SQL('''
                ALTER TABLE {}.bist_companies
                    ADD COLUMN IF NOT EXISTS mkk_member_oid VARCHAR(64)
            ''').format(sql.Identifier(self.schema)))

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

            # --- Fundamental analysis (KAP "Finansal Tablolar") -------------
            # Raw structured financial-statement facts fetched from KAP's
            # financial-report (FR) disclosures, one row per instrument/period.
            # `facts` holds the canonical line items (see scrapers/kap_financial_parser.py)
            # so we can recompute ratios later without re-fetching from KAP.
            cursor.execute(sql.SQL('''
                CREATE TABLE IF NOT EXISTS {}.kap_financial_statements (
                    id SERIAL PRIMARY KEY,
                    stock_code VARCHAR(20) NOT NULL,
                    company_name VARCHAR(255),
                    period VARCHAR(20) NOT NULL,
                    fiscal_period VARCHAR(20),
                    currency VARCHAR(10),
                    reporting_standard VARCHAR(50),
                    disclosure_index VARCHAR(100),
                    facts JSONB NOT NULL,
                    scraped_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE(stock_code, period)
                )
            ''').format(sql.Identifier(self.schema)))

            cursor.execute(sql.SQL('''
                CREATE INDEX IF NOT EXISTS idx_fin_stmt_stock_code
                ON {}.kap_financial_statements(stock_code)
            ''').format(sql.Identifier(self.schema)))

            # Computed fundamental ratios per instrument/period. Column set mirrors
            # the External Analysis Provider FundamentalPayload (contract v1.0 §3) so
            # the contract endpoints can map rows to envelopes 1:1.
            cursor.execute(sql.SQL('''
                CREATE TABLE IF NOT EXISTS {}.kap_fundamentals (
                    id SERIAL PRIMARY KEY,
                    stock_code VARCHAR(20) NOT NULL,
                    company_name VARCHAR(255),
                    period VARCHAR(20) NOT NULL,
                    fiscal_period VARCHAR(20),
                    currency VARCHAR(10),
                    reporting_standard VARCHAR(50),

                    pe_ratio REAL,
                    pb_ratio REAL,
                    ps_ratio REAL,
                    ev_ebitda REAL,
                    peg_ratio REAL,

                    eps REAL,
                    book_value_per_share REAL,
                    dividend_per_share REAL,
                    dividend_yield REAL,

                    gross_margin REAL,
                    operating_margin REAL,
                    net_margin REAL,
                    roe REAL,
                    roa REAL,
                    roic REAL,

                    debt_to_equity REAL,
                    net_debt_to_ebitda REAL,
                    current_ratio REAL,
                    quick_ratio REAL,
                    interest_coverage REAL,

                    revenue REAL,
                    ebitda REAL,
                    net_income REAL,
                    free_cash_flow REAL,
                    revenue_growth_yoy REAL,
                    eps_growth_yoy REAL,

                    is_estimated BOOLEAN DEFAULT FALSE,
                    restated BOOLEAN DEFAULT FALSE,
                    data_completeness REAL,

                    source_disclosure_index VARCHAR(100),
                    effective_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    computed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE(stock_code, period)
                )
            ''').format(sql.Identifier(self.schema)))

            cursor.execute(sql.SQL('''
                CREATE INDEX IF NOT EXISTS idx_fundamentals_stock_code
                ON {}.kap_fundamentals(stock_code)
            ''').format(sql.Identifier(self.schema)))

            cursor.execute(sql.SQL('''
                CREATE INDEX IF NOT EXISTS idx_fundamentals_effective_at
                ON {}.kap_fundamentals(effective_at)
            ''').format(sql.Identifier(self.schema)))

            # --- kap_disclosures extra columns (idempotent ALTERs) ----------
            # subject / subject_code / is_late were missing from the original schema;
            # add them now so scrape_and_save_disclosures() can populate them properly.
            cursor.execute(sql.SQL('''
                ALTER TABLE {}.kap_disclosures
                    ADD COLUMN IF NOT EXISTS subject TEXT,
                    ADD COLUMN IF NOT EXISTS subject_code VARCHAR(50),
                    ADD COLUMN IF NOT EXISTS is_late BOOLEAN DEFAULT FALSE
            ''').format(sql.Identifier(self.schema)))

            # Unique index on disclosure_index for fast upsert-by-id.
            cursor.execute(sql.SQL('''
                CREATE UNIQUE INDEX IF NOT EXISTS idx_kap_disclosures_disclosure_id
                ON {}.kap_disclosures(disclosure_id)
                WHERE disclosure_id IS NOT NULL
            ''').format(sql.Identifier(self.schema)))

            # --- KAP platform-level news (SPK/MKK/BIS announcements) -------
            # These are not company disclosures but regulatory/platform news that
            # affects whole sectors or the market. Separate table to keep company
            # disclosures and market-wide news queryable independently.
            cursor.execute(sql.SQL('''
                CREATE TABLE IF NOT EXISTS {}.kap_news (
                    id SERIAL PRIMARY KEY,
                    news_id VARCHAR(100) UNIQUE,
                    news_category VARCHAR(50),
                    title TEXT NOT NULL,
                    content TEXT,
                    publish_date TIMESTAMP,
                    source_url TEXT,
                    data JSONB,
                    scraped_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''').format(sql.Identifier(self.schema)))

            cursor.execute(sql.SQL('''
                CREATE INDEX IF NOT EXISTS idx_kap_news_publish_date
                ON {}.kap_news(publish_date DESC)
            ''').format(sql.Identifier(self.schema)))

            cursor.execute(sql.SQL('''
                CREATE INDEX IF NOT EXISTS idx_kap_news_category
                ON {}.kap_news(news_category)
            ''').format(sql.Identifier(self.schema)))

            # Sentiment table for platform-level news (mirrors kap_disclosure_sentiment).
            cursor.execute(sql.SQL('''
                CREATE TABLE IF NOT EXISTS {}.kap_news_sentiment (
                    id SERIAL PRIMARY KEY,
                    news_id INTEGER REFERENCES {}.kap_news(id) ON DELETE CASCADE,
                    overall_sentiment VARCHAR(20),
                    sentiment_score REAL DEFAULT 0.0,
                    confidence REAL DEFAULT 0.0,
                    analysis_text TEXT,
                    analyzer VARCHAR(100),
                    analyzed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE(news_id)
                )
            ''').format(sql.Identifier(self.schema), sql.Identifier(self.schema)))

            # --- Financial news portals (institutional sentiment) ----------
            # Articles scraped from Turkish financial portals (Bloomberg HT, Foreks,
            # Mynet Finans, Bigpara, Investing.com TR). `ticker` is nullable: macro/sector
            # headlines belong to no single instrument. Analysed individually, then rolled
            # up per ticker/day into aggregated_ticker_sentiment.
            cursor.execute(sql.SQL('''
                CREATE TABLE IF NOT EXISTS {}.news_articles (
                    id SERIAL PRIMARY KEY,
                    article_id VARCHAR(200) UNIQUE,
                    source VARCHAR(50),
                    ticker VARCHAR(20),
                    headline TEXT NOT NULL,
                    body TEXT,
                    url TEXT,
                    published_at TIMESTAMP,
                    scraped_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''').format(sql.Identifier(self.schema)))

            cursor.execute(sql.SQL('''
                CREATE INDEX IF NOT EXISTS idx_news_articles_ticker_pub
                ON {}.news_articles(ticker, published_at DESC)
            ''').format(sql.Identifier(self.schema)))

            cursor.execute(sql.SQL('''
                CREATE INDEX IF NOT EXISTS idx_news_articles_source
                ON {}.news_articles(source)
            ''').format(sql.Identifier(self.schema)))

            # Per-article sentiment (mirrors kap_news_sentiment shape).
            cursor.execute(sql.SQL('''
                CREATE TABLE IF NOT EXISTS {}.news_article_sentiment (
                    id SERIAL PRIMARY KEY,
                    article_id INTEGER REFERENCES {}.news_articles(id) ON DELETE CASCADE,
                    overall_sentiment VARCHAR(20),
                    sentiment_score REAL DEFAULT 0.0,
                    confidence REAL DEFAULT 0.0,
                    key_drivers TEXT,
                    tone_descriptors TEXT,
                    analyzer VARCHAR(100),
                    analyzed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE(article_id)
                )
            ''').format(sql.Identifier(self.schema), sql.Identifier(self.schema)))

            # Aggregated daily sentiment per ticker. `social_*` columns are reserved for
            # Phase 2 (X/social) and stay NULL for now; combined_score == news_score today.
            cursor.execute(sql.SQL('''
                CREATE TABLE IF NOT EXISTS {}.aggregated_ticker_sentiment (
                    id SERIAL PRIMARY KEY,
                    ticker VARCHAR(20),
                    period_date DATE,
                    news_score REAL,
                    news_count INTEGER DEFAULT 0,
                    social_score REAL,
                    social_count INTEGER DEFAULT 0,
                    youtube_score REAL,
                    youtube_count INTEGER DEFAULT 0,
                    combined_score REAL,
                    computed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE(ticker, period_date)
                )
            ''').format(sql.Identifier(self.schema)))

            # Migrate: add youtube columns to existing DBs
            for col, coldef in [
                ("youtube_score", "REAL"),
                ("youtube_count", "INTEGER DEFAULT 0"),
            ]:
                cursor.execute(sql.SQL(
                    "ALTER TABLE {}.aggregated_ticker_sentiment "
                    "ADD COLUMN IF NOT EXISTS {} {}"
                ).format(
                    sql.Identifier(self.schema),
                    sql.Identifier(col),
                    sql.SQL(coldef),
                ))

            cursor.execute(sql.SQL('''
                CREATE INDEX IF NOT EXISTS idx_agg_ticker_sentiment_ticker
                ON {}.aggregated_ticker_sentiment(ticker, period_date DESC)
            ''').format(sql.Identifier(self.schema)))

            # --- Social media (X / FinTwit) — Phase 2 -----------------------
            # Tweets/posts scraped from X by searching ticker cashtags/hashtags. Always
            # ticker-tagged (searched per ticker). Analysed individually, then rolled up
            # into the social_* columns of aggregated_ticker_sentiment.
            cursor.execute(sql.SQL('''
                CREATE TABLE IF NOT EXISTS {}.social_media_posts (
                    id SERIAL PRIMARY KEY,
                    post_id VARCHAR(200) UNIQUE,
                    platform VARCHAR(20),
                    ticker VARCHAR(20),
                    text TEXT NOT NULL,
                    author VARCHAR(100),
                    posted_at TIMESTAMP,
                    likes INTEGER DEFAULT 0,
                    retweets INTEGER DEFAULT 0,
                    scraped_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''').format(sql.Identifier(self.schema)))

            cursor.execute(sql.SQL('''
                CREATE INDEX IF NOT EXISTS idx_social_posts_ticker_posted
                ON {}.social_media_posts(ticker, posted_at DESC)
            ''').format(sql.Identifier(self.schema)))

            cursor.execute(sql.SQL('''
                CREATE TABLE IF NOT EXISTS {}.social_media_sentiment (
                    id SERIAL PRIMARY KEY,
                    post_id INTEGER REFERENCES {}.social_media_posts(id) ON DELETE CASCADE,
                    overall_sentiment VARCHAR(20),
                    sentiment_score REAL DEFAULT 0.0,
                    confidence REAL DEFAULT 0.0,
                    analyzer VARCHAR(100),
                    analyzed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE(post_id)
                )
            ''').format(sql.Identifier(self.schema), sql.Identifier(self.schema)))

            # --- YouTube finance channels — Phase 3 --------------------------
            # Videos from Turkish finance YouTube channels. Each video may mention
            # multiple BIST tickers; sentiment is recorded per (video, ticker) pair
            # and rolled up into youtube_* columns of aggregated_ticker_sentiment.
            cursor.execute(sql.SQL('''
                CREATE TABLE IF NOT EXISTS {}.youtube_videos (
                    id SERIAL PRIMARY KEY,
                    video_id VARCHAR(20) UNIQUE,
                    channel TEXT,
                    title TEXT,
                    url TEXT,
                    transcript TEXT,
                    transcript_method VARCHAR(30),
                    transcript_status VARCHAR(30),
                    transcript_attempted_at TIMESTAMP,
                    published_at TIMESTAMP,
                    duration INTEGER,
                    lang VARCHAR(10),
                    scraped_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''').format(sql.Identifier(self.schema)))

            # These fields are additive so existing local databases can adopt the
            # native macOS transcript runner without a destructive migration.
            cursor.execute(sql.SQL('''
                ALTER TABLE {}.youtube_videos
                    ADD COLUMN IF NOT EXISTS transcript_method VARCHAR(30)
            ''').format(sql.Identifier(self.schema)))
            cursor.execute(sql.SQL('''
                ALTER TABLE {}.youtube_videos
                    ADD COLUMN IF NOT EXISTS transcript_status VARCHAR(30)
            ''').format(sql.Identifier(self.schema)))
            cursor.execute(sql.SQL('''
                ALTER TABLE {}.youtube_videos
                    ADD COLUMN IF NOT EXISTS transcript_attempted_at TIMESTAMP
            ''').format(sql.Identifier(self.schema)))

            cursor.execute(sql.SQL('''
                CREATE INDEX IF NOT EXISTS idx_youtube_videos_channel_published
                ON {}.youtube_videos(channel, published_at DESC)
            ''').format(sql.Identifier(self.schema)))

            cursor.execute(sql.SQL('''
                CREATE TABLE IF NOT EXISTS {}.youtube_video_sentiment (
                    id SERIAL PRIMARY KEY,
                    video_id INTEGER REFERENCES {}.youtube_videos(id) ON DELETE CASCADE,
                    ticker VARCHAR(20) NOT NULL,
                    overall_sentiment VARCHAR(20),
                    sentiment_score REAL DEFAULT 0.0,
                    confidence REAL DEFAULT 0.0,
                    analyzer VARCHAR(100),
                    analyzed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE(video_id, ticker)
                )
            ''').format(sql.Identifier(self.schema), sql.Identifier(self.schema)))

            cursor.execute(sql.SQL('''
                CREATE INDEX IF NOT EXISTS idx_youtube_sentiment_ticker
                ON {}.youtube_video_sentiment(ticker, analyzed_at DESC)
            ''').format(sql.Identifier(self.schema)))

            conn.commit()
            logger.info("Database tables created/verified")
            
        except Exception as e:
            logger.error(f"Error creating tables: {e}")
            conn.rollback()
            raise
        finally:
            self.return_connection(conn)
    
    class PoolExhaustedError(Exception):
        """Raised when connection pool is exhausted"""
        pass

    def get_connection(self):
        """Get a connection from the pool and set search_path

        Implements a short retry strategy when the pool is temporarily exhausted.
        Raises:
            PoolExhaustedError: if connections cannot be acquired after retries
        """
        retries = int(os.getenv("DB_CONN_RETRIES", "3"))
        wait_ms = int(os.getenv("DB_CONN_WAIT_MS", "100"))

        for attempt in range(1, retries + 1):
            try:
                conn = self.pool.getconn()
                # Set search_path for this connection to use our schema
                cursor = conn.cursor()
                cursor.execute(sql.SQL("SET search_path TO {}, public").format(
                    sql.Identifier(self.schema)
                ))
                cursor.close()
                return conn
            except pool.PoolError as e:
                logger.warning(f"Connection pool exhausted (attempt {attempt}/{retries}): {e}")
                if attempt == retries:
                    logger.error("Connection pool exhausted after retries")
                    raise DatabaseManager.PoolExhaustedError("connection pool exhausted")
                time.sleep(wait_ms / 1000.0)
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

    # ------------------------------------------------------------------
    # Domain-specific upsert helpers
    # ------------------------------------------------------------------

    def upsert_disclosure(self, data: Dict[str, Any]) -> bool:
        """
        Upsert one row into kap_disclosures keyed on disclosure_id.

        ``data`` must contain ``disclosure_id``; all other columns are optional.
        On conflict the row is updated so repeated scrapes reflect the latest state.
        """
        conn = self.get_connection()
        try:
            cursor = conn.cursor()
            cols = [
                "disclosure_id", "stock_code", "company_name", "disclosure_type",
                "disclosure_date", "timestamp", "has_attachment", "detail_url",
                "pdf_url", "content", "data", "subject", "subject_code", "is_late",
            ]
            row = {c: data.get(c) for c in cols}
            row["data"] = Json(row["data"]) if isinstance(row["data"], (dict, list)) else row["data"]

            non_null = {k: v for k, v in row.items() if v is not None}
            if not non_null.get("disclosure_id"):
                return False

            set_clause = sql.SQL(", ").join(
                sql.SQL("{} = EXCLUDED.{}").format(sql.Identifier(k), sql.Identifier(k))
                for k in non_null if k != "disclosure_id"
            )
            q = sql.SQL(
                "INSERT INTO {schema}.kap_disclosures ({cols}) VALUES ({vals}) "
                "ON CONFLICT (disclosure_id) DO UPDATE SET {set}"
            ).format(
                schema=sql.Identifier(self.schema),
                cols=sql.SQL(", ").join(sql.Identifier(k) for k in non_null),
                vals=sql.SQL(", ").join(sql.Placeholder() * len(non_null)),
                set=set_clause,
            )
            cursor.execute(q, list(non_null.values()))
            conn.commit()
            return True
        except Exception as e:
            logger.error(f"upsert_disclosure failed for {data.get('disclosure_id')}: {e}")
            conn.rollback()
            return False
        finally:
            self.return_connection(conn)

    def upsert_bist_company(
        self,
        code: str,
        name: Optional[str] = None,
        mkk_member_oid: Optional[str] = None,
    ) -> bool:
        """
        Insert or update a row in bist_companies.

        On conflict (code already exists) only non-None provided fields are updated,
        so callers can safely call this with partial data without wiping existing values.
        """
        conn = self.get_connection()
        try:
            cursor = conn.cursor()
            updates: Dict[str, Any] = {"code": code}
            if name is not None:
                updates["name"] = name
            if mkk_member_oid is not None:
                updates["mkk_member_oid"] = mkk_member_oid

            set_parts = [
                sql.SQL("{} = EXCLUDED.{}").format(sql.Identifier(k), sql.Identifier(k))
                for k in updates if k != "code"
            ]
            if not set_parts:
                # Nothing to update except code (which is the conflict target).
                q = sql.SQL(
                    "INSERT INTO {}.bist_companies (code) VALUES (%s) ON CONFLICT DO NOTHING"
                ).format(sql.Identifier(self.schema))
                cursor.execute(q, (code,))
            else:
                q = sql.SQL(
                    "INSERT INTO {schema}.bist_companies ({cols}) VALUES ({vals}) "
                    "ON CONFLICT (code) DO UPDATE SET {set}"
                ).format(
                    schema=sql.Identifier(self.schema),
                    cols=sql.SQL(", ").join(sql.Identifier(k) for k in updates),
                    vals=sql.SQL(", ").join(sql.Placeholder() * len(updates)),
                    set=sql.SQL(", ").join(set_parts),
                )
                cursor.execute(q, list(updates.values()))

            conn.commit()
            return True
        except Exception as e:
            logger.error(f"upsert_bist_company failed for {code}: {e}")
            conn.rollback()
            return False
        finally:
            self.return_connection(conn)

    def seed_bist_catalog(self, catalog: Dict[str, str]) -> int:
        """Insert the versioned BIST catalogue without overwriting scraped metadata.

        The local CSV is only the bootstrap source. Once rows exist, KAP refreshes
        may add sectors and member OIDs; this seed fills missing names and symbols
        only and is safe to run at every service startup.
        """
        rows = [
            (code.strip().upper(), name.strip(), f"{code.strip().upper()}.IS")
            for code, name in catalog.items()
            if code and name
        ]
        if not rows:
            return 0

        conn = self.get_connection()
        try:
            cursor = conn.cursor()
            query = sql.SQL(
                "INSERT INTO {}.bist_companies (code, name, symbol, is_active) VALUES (%s, %s, %s, TRUE) "
                "ON CONFLICT (code) DO UPDATE SET "
                "name = COALESCE(NULLIF({}.bist_companies.name, ''), EXCLUDED.name), "
                "symbol = COALESCE(NULLIF({}.bist_companies.symbol, ''), EXCLUDED.symbol), "
                "is_active = TRUE"
            ).format(
                sql.Identifier(self.schema),
                sql.Identifier(self.schema),
                sql.Identifier(self.schema),
            )
            # One connection and transaction keep this inexpensive while avoiding a
            # dependency on psycopg2 bulk helpers (the project's DB test doubles
            # intentionally expose only the normal cursor interface).
            for row in rows:
                cursor.execute(query, row)
            # A complete BIST TÜM snapshot represents the active-share universe.
            # Keep old rows for historic sentiment/fundamental queries, but omit them
            # from discovery rather than presenting certificates or stale instruments.
            if len(rows) >= 500:
                cursor.execute(
                    sql.SQL("UPDATE {}.bist_companies SET is_active = FALSE WHERE code <> ALL(%s)").format(
                        sql.Identifier(self.schema)
                    ),
                    ([row[0] for row in rows],),
                )
            conn.commit()
            return len(rows)
        except Exception as e:
            logger.error(f"seed_bist_catalog failed: {e}")
            conn.rollback()
            raise
        finally:
            self.return_connection(conn)

    def upsert_news(self, data: Dict[str, Any]) -> Optional[int]:
        """
        Upsert one row into kap_news keyed on news_id. Returns the row id.

        ``data`` must contain ``news_id`` and ``title``.
        """
        conn = self.get_connection()
        try:
            cursor = conn.cursor()
            cols = ["news_id", "news_category", "title", "content",
                    "publish_date", "source_url", "data"]
            row = {c: data.get(c) for c in cols if data.get(c) is not None}
            if not row.get("news_id") or not row.get("title"):
                return None

            row_data = row.get("data")
            if isinstance(row_data, (dict, list)):
                row["data"] = Json(row_data)

            set_clause = sql.SQL(", ").join(
                sql.SQL("{} = EXCLUDED.{}").format(sql.Identifier(k), sql.Identifier(k))
                for k in row if k != "news_id"
            )
            q = sql.SQL(
                "INSERT INTO {schema}.kap_news ({cols}) VALUES ({vals}) "
                "ON CONFLICT (news_id) DO UPDATE SET {set} RETURNING id"
            ).format(
                schema=sql.Identifier(self.schema),
                cols=sql.SQL(", ").join(sql.Identifier(k) for k in row),
                vals=sql.SQL(", ").join(sql.Placeholder() * len(row)),
                set=set_clause,
            )
            cursor.execute(q, list(row.values()))
            result = cursor.fetchone()
            conn.commit()
            return result[0] if result else None
        except Exception as e:
            logger.error(f"upsert_news failed for {data.get('news_id')}: {e}")
            conn.rollback()
            return None
        finally:
            self.return_connection(conn)

    def upsert_news_article(self, data: Dict[str, Any]) -> Optional[int]:
        """
        Upsert one row into news_articles keyed on article_id. Returns the row id.

        ``data`` must contain ``article_id`` and ``headline``. On conflict the row is
        updated so repeated scrapes reflect the latest body/ticker tagging.
        """
        conn = self.get_connection()
        try:
            cursor = conn.cursor()
            cols = ["article_id", "source", "ticker", "headline",
                    "body", "url", "published_at"]
            row = {c: data.get(c) for c in cols if data.get(c) is not None}
            if not row.get("article_id") or not row.get("headline"):
                return None

            set_clause = sql.SQL(", ").join(
                sql.SQL("{} = EXCLUDED.{}").format(sql.Identifier(k), sql.Identifier(k))
                for k in row if k != "article_id"
            )
            set_clause += sql.SQL(", scraped_at = CURRENT_TIMESTAMP")
            q = sql.SQL(
                "INSERT INTO {schema}.news_articles ({cols}) VALUES ({vals}) "
                "ON CONFLICT (article_id) DO UPDATE SET {set} RETURNING id"
            ).format(
                schema=sql.Identifier(self.schema),
                cols=sql.SQL(", ").join(sql.Identifier(k) for k in row),
                vals=sql.SQL(", ").join(sql.Placeholder() * len(row)),
                set=set_clause,
            )
            cursor.execute(q, list(row.values()))
            result = cursor.fetchone()
            conn.commit()
            return result[0] if result else None
        except Exception as e:
            logger.error(f"upsert_news_article failed for {data.get('article_id')}: {e}")
            conn.rollback()
            return None
        finally:
            self.return_connection(conn)

    def upsert_news_article_sentiment(self, article_id: int, data: Dict[str, Any]) -> bool:
        """
        Upsert the sentiment row for a news article (keyed on the integer article_id FK).

        ``data`` carries overall_sentiment / sentiment_score / confidence and optionally
        key_drivers, tone_descriptors (stored as TEXT) and analyzer.
        """
        conn = self.get_connection()
        try:
            cursor = conn.cursor()
            row: Dict[str, Any] = {"article_id": article_id}
            for col in ("overall_sentiment", "sentiment_score", "confidence",
                        "key_drivers", "tone_descriptors", "analyzer"):
                if data.get(col) is not None:
                    row[col] = data[col]

            set_clause = sql.SQL(", ").join(
                sql.SQL("{} = EXCLUDED.{}").format(sql.Identifier(k), sql.Identifier(k))
                for k in row if k != "article_id"
            )
            q = sql.SQL(
                "INSERT INTO {schema}.news_article_sentiment ({cols}) VALUES ({vals}) "
                "ON CONFLICT (article_id) DO UPDATE SET {set}"
            ).format(
                schema=sql.Identifier(self.schema),
                cols=sql.SQL(", ").join(sql.Identifier(k) for k in row),
                vals=sql.SQL(", ").join(sql.Placeholder() * len(row)),
                set=set_clause,
            )
            cursor.execute(q, list(row.values()))
            conn.commit()
            return True
        except Exception as e:
            logger.error(f"upsert_news_article_sentiment failed for {article_id}: {e}")
            conn.rollback()
            return False
        finally:
            self.return_connection(conn)

    def upsert_aggregated_ticker_sentiment(self, data: Dict[str, Any]) -> bool:
        """
        Upsert one daily aggregate row keyed on (ticker, period_date).

        ``data`` must contain ``ticker`` and ``period_date``; score/count columns are
        optional. On conflict the row is overwritten with the freshly recomputed values.
        """
        conn = self.get_connection()
        try:
            cursor = conn.cursor()
            cols = ["ticker", "period_date", "news_score", "news_count",
                    "social_score", "social_count", "youtube_score", "youtube_count",
                    "combined_score"]
            row = {c: data.get(c) for c in cols if data.get(c) is not None}
            if not row.get("ticker") or not row.get("period_date"):
                return False
            row["computed_at"] = datetime.now()

            set_clause = sql.SQL(", ").join(
                sql.SQL("{} = EXCLUDED.{}").format(sql.Identifier(k), sql.Identifier(k))
                for k in row if k not in ("ticker", "period_date")
            )
            q = sql.SQL(
                "INSERT INTO {schema}.aggregated_ticker_sentiment ({cols}) VALUES ({vals}) "
                "ON CONFLICT (ticker, period_date) DO UPDATE SET {set}"
            ).format(
                schema=sql.Identifier(self.schema),
                cols=sql.SQL(", ").join(sql.Identifier(k) for k in row),
                vals=sql.SQL(", ").join(sql.Placeholder() * len(row)),
                set=set_clause,
            )
            cursor.execute(q, list(row.values()))
            conn.commit()
            return True
        except Exception as e:
            logger.error(f"upsert_aggregated_ticker_sentiment failed for {data.get('ticker')}: {e}")
            conn.rollback()
            return False
        finally:
            self.return_connection(conn)

    def upsert_social_post(self, data: Dict[str, Any]) -> Optional[int]:
        """
        Upsert one row into social_media_posts keyed on post_id. Returns the row id.

        ``data`` must contain ``post_id`` and ``text``.
        """
        conn = self.get_connection()
        try:
            cursor = conn.cursor()
            cols = ["post_id", "platform", "ticker", "text",
                    "author", "posted_at", "likes", "retweets"]
            row = {c: data.get(c) for c in cols if data.get(c) is not None}
            if not row.get("post_id") or not row.get("text"):
                return None

            set_clause = sql.SQL(", ").join(
                sql.SQL("{} = EXCLUDED.{}").format(sql.Identifier(k), sql.Identifier(k))
                for k in row if k != "post_id"
            )
            set_clause += sql.SQL(", scraped_at = CURRENT_TIMESTAMP")
            q = sql.SQL(
                "INSERT INTO {schema}.social_media_posts ({cols}) VALUES ({vals}) "
                "ON CONFLICT (post_id) DO UPDATE SET {set} RETURNING id"
            ).format(
                schema=sql.Identifier(self.schema),
                cols=sql.SQL(", ").join(sql.Identifier(k) for k in row),
                vals=sql.SQL(", ").join(sql.Placeholder() * len(row)),
                set=set_clause,
            )
            cursor.execute(q, list(row.values()))
            result = cursor.fetchone()
            conn.commit()
            return result[0] if result else None
        except Exception as e:
            logger.error(f"upsert_social_post failed for {data.get('post_id')}: {e}")
            conn.rollback()
            return None
        finally:
            self.return_connection(conn)

    def upsert_social_post_sentiment(self, post_id: int, data: Dict[str, Any]) -> bool:
        """Upsert the sentiment row for a social post (keyed on the integer post_id FK)."""
        conn = self.get_connection()
        try:
            cursor = conn.cursor()
            row: Dict[str, Any] = {"post_id": post_id}
            for col in ("overall_sentiment", "sentiment_score", "confidence", "analyzer"):
                if data.get(col) is not None:
                    row[col] = data[col]

            set_clause = sql.SQL(", ").join(
                sql.SQL("{} = EXCLUDED.{}").format(sql.Identifier(k), sql.Identifier(k))
                for k in row if k != "post_id"
            )
            q = sql.SQL(
                "INSERT INTO {schema}.social_media_sentiment ({cols}) VALUES ({vals}) "
                "ON CONFLICT (post_id) DO UPDATE SET {set}"
            ).format(
                schema=sql.Identifier(self.schema),
                cols=sql.SQL(", ").join(sql.Identifier(k) for k in row),
                vals=sql.SQL(", ").join(sql.Placeholder() * len(row)),
                set=set_clause,
            )
            cursor.execute(q, list(row.values()))
            conn.commit()
            return True
        except Exception as e:
            logger.error(f"upsert_social_post_sentiment failed for {post_id}: {e}")
            conn.rollback()
            return False
        finally:
            self.return_connection(conn)

    def get_aggregated_ticker_sentiment(self, ticker: str, period_date) -> Optional[Dict[str, Any]]:
        """Fetch the existing daily aggregate row for (ticker, period_date), or None."""
        rows = self.query(
            "SELECT ticker, period_date, news_score, news_count, social_score, "
            "social_count, youtube_score, youtube_count, combined_score "
            "FROM aggregated_ticker_sentiment "
            "WHERE ticker = %s AND period_date = %s",
            (ticker.strip().upper(), period_date),
        )
        return rows[0] if rows else None

    def get_source_refresh_cache(
        self, ticker: str, max_age_seconds: int
    ) -> Dict[str, Dict[str, Any]]:
        """Return independent database freshness for news, social, and YouTube."""
        ticker = ticker.strip().upper()
        rows = self.query(
            """SELECT source, updated_at,
                      CASE WHEN updated_at IS NULL THEN NULL
                           ELSE EXTRACT(EPOCH FROM (CURRENT_TIMESTAMP - updated_at))::BIGINT
                      END AS age_seconds
               FROM (
                   SELECT 'news' AS source, MAX(scraped_at) AS updated_at
                   FROM news_articles WHERE ticker = %s
                   UNION ALL
                   SELECT 'social' AS source, MAX(scraped_at) AS updated_at
                   FROM social_media_posts WHERE ticker = %s
                   UNION ALL
                   SELECT 'youtube' AS source, MAX(v.scraped_at) AS updated_at
                   FROM youtube_videos v
                   JOIN youtube_video_sentiment s ON s.video_id = v.id
                   WHERE s.ticker = %s
               ) source_updates""",
            (ticker, ticker, ticker),
        )
        result = {
            source: {"fresh": False, "age_seconds": None}
            for source in ("news", "social", "youtube")
        }
        for row in rows:
            source = row.get("source")
            age_seconds = row.get("age_seconds")
            if source not in result:
                continue
            age = int(age_seconds) if age_seconds is not None else None
            result[source] = {
                "fresh": age is not None and age <= max_age_seconds,
                "age_seconds": age,
            }
        return result

    # ── YouTube video persistence ─────────────────────────────────────────────

    def get_youtube_transcript_cache(self, video_id: str) -> Dict[str, Any]:
        """Return whether a video should be skipped by the native transcript runner.

        A stored transcript is immutable for collection purposes. A failed fetch is
        retried only after 24 hours, which keeps repeated dashboard/manual runs from
        hammering YouTube when an IP is rate limited.
        """
        rows = self.query(
            """SELECT video_id,
                      CASE WHEN COALESCE(LENGTH(BTRIM(transcript)), 0) > 0
                           THEN TRUE ELSE FALSE END AS ready,
                      transcript_status,
                      CASE WHEN transcript_status = 'retry_later'
                                AND transcript_attempted_at > CURRENT_TIMESTAMP - INTERVAL '24 hours'
                           THEN TRUE ELSE FALSE END AS retry_later
               FROM youtube_videos
               WHERE video_id = %s
               LIMIT 1""",
            (video_id.strip(),),
        )
        if not rows:
            return {"exists": False, "ready": False, "retry_later": False}

        row = rows[0]
        return {
            "exists": True,
            "ready": bool(row.get("ready")),
            "retry_later": bool(row.get("retry_later")),
            "transcript_status": row.get("transcript_status"),
        }

    def list_ready_youtube_transcripts(
        self, days_back: int = 7, limit: int = 500,
    ) -> List[Dict[str, Any]]:
        """Return persisted caption/Whisper text ready for local score analysis.

        The native host collector is the source of truth for caption-less videos.
        Keep this read bounded and based on the video publication date so replaying a
        score window never needs to download the same audio again.
        """
        return self.query(
            """SELECT video_id, channel, title, url, transcript, published_at,
                      duration, lang, transcript_method, transcript_status,
                      transcript_attempted_at, scraped_at
               FROM youtube_videos
               WHERE COALESCE(LENGTH(BTRIM(transcript)), 0) > 0
                 AND transcript_status = 'ready'
                 AND COALESCE(published_at, scraped_at) >=
                     CURRENT_TIMESTAMP - (%s * INTERVAL '1 day')
               ORDER BY COALESCE(published_at, scraped_at) DESC
               LIMIT %s""",
            (max(1, min(int(days_back), 90)), max(1, min(int(limit), 1000))),
        )

    def upsert_youtube_video(self, data: Dict[str, Any]) -> Optional[int]:
        """
        Upsert one row into youtube_videos keyed on video_id. Returns the row id.

        ``data`` must contain ``video_id``.
        """
        conn = self.get_connection()
        try:
            cursor = conn.cursor()
            cols = ["video_id", "channel", "title", "url", "transcript",
                    "transcript_method", "transcript_status", "transcript_attempted_at",
                    "published_at", "duration", "lang"]
            row = {c: data.get(c) for c in cols if data.get(c) is not None}
            if not row.get("video_id"):
                return None

            set_clause = sql.SQL(", ").join(
                sql.SQL("{} = EXCLUDED.{}").format(sql.Identifier(k), sql.Identifier(k))
                for k in row if k != "video_id"
            )
            set_clause += sql.SQL(", scraped_at = CURRENT_TIMESTAMP")
            q = sql.SQL(
                "INSERT INTO {schema}.youtube_videos ({cols}) VALUES ({vals}) "
                "ON CONFLICT (video_id) DO UPDATE SET {set} RETURNING id"
            ).format(
                schema=sql.Identifier(self.schema),
                cols=sql.SQL(", ").join(sql.Identifier(k) for k in row),
                vals=sql.SQL(", ").join(sql.Placeholder() * len(row)),
                set=set_clause,
            )
            cursor.execute(q, list(row.values()))
            result = cursor.fetchone()
            conn.commit()
            return result[0] if result else None
        except Exception as e:
            logger.error(f"upsert_youtube_video failed for {data.get('video_id')}: {e}")
            conn.rollback()
            return None
        finally:
            self.return_connection(conn)

    def upsert_youtube_video_sentiment(
        self, video_db_id: int, ticker: str, data: Dict[str, Any]
    ) -> bool:
        """Upsert the sentiment row for a (video, ticker) pair."""
        conn = self.get_connection()
        try:
            cursor = conn.cursor()
            row: Dict[str, Any] = {"video_id": video_db_id, "ticker": ticker.strip().upper()}
            for col in ("overall_sentiment", "sentiment_score", "confidence", "analyzer"):
                if data.get(col) is not None:
                    row[col] = data[col]

            set_clause = sql.SQL(", ").join(
                sql.SQL("{} = EXCLUDED.{}").format(sql.Identifier(k), sql.Identifier(k))
                for k in row if k not in ("video_id", "ticker")
            )
            q = sql.SQL(
                "INSERT INTO {schema}.youtube_video_sentiment ({cols}) VALUES ({vals}) "
                "ON CONFLICT (video_id, ticker) DO UPDATE SET {set}"
            ).format(
                schema=sql.Identifier(self.schema),
                cols=sql.SQL(", ").join(sql.Identifier(k) for k in row),
                vals=sql.SQL(", ").join(sql.Placeholder() * len(row)),
                set=set_clause,
            )
            cursor.execute(q, list(row.values()))
            conn.commit()
            return True
        except Exception as e:
            logger.error(
                f"upsert_youtube_video_sentiment failed for video {video_db_id}/{ticker}: {e}"
            )
            conn.rollback()
            return False
        finally:
            self.return_connection(conn)
