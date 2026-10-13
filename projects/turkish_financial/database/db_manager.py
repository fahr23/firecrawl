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

            # FA-10: dated sector/industry classification history, one row per
            # (stock_code, valid_from) — a re-classification closes the prior
            # row's valid_to and opens a new one, instead of overwriting it, so
            # "classification at a past date" stays answerable.
            cursor.execute(sql.SQL('''
                CREATE TABLE IF NOT EXISTS {}.stock_classification_history (
                    id SERIAL PRIMARY KEY,
                    stock_code VARCHAR(20) NOT NULL,
                    sector VARCHAR(100),
                    industry VARCHAR(100),
                    taxonomy VARCHAR(50) NOT NULL DEFAULT 'kap',
                    valid_from DATE NOT NULL,
                    valid_to DATE,
                    recorded_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE(stock_code, taxonomy, valid_from)
                )
            ''').format(sql.Identifier(self.schema)))
            cursor.execute(sql.SQL('''
                CREATE INDEX IF NOT EXISTS idx_stock_classification_current
                ON {}.stock_classification_history(stock_code, valid_to)
            ''').format(sql.Identifier(self.schema)))

            # FA-10: dated index-membership history, parallel to the undated
            # bist_index_members snapshot above — a membership change closes the
            # prior row's valid_to and opens a new one.
            cursor.execute(sql.SQL('''
                CREATE TABLE IF NOT EXISTS {}.index_membership_history (
                    id SERIAL PRIMARY KEY,
                    index_code VARCHAR(20) NOT NULL,
                    stock_code VARCHAR(20) NOT NULL,
                    valid_from DATE NOT NULL,
                    valid_to DATE,
                    recorded_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE(index_code, stock_code, valid_from)
                )
            ''').format(sql.Identifier(self.schema)))
            cursor.execute(sql.SQL('''
                CREATE INDEX IF NOT EXISTS idx_index_membership_current
                ON {}.index_membership_history(index_code, valid_to)
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
            
            # TCMB Macro Data table
            cursor.execute(sql.SQL('''
                CREATE TABLE IF NOT EXISTS {}.tcmb_macro_data (
                    id SERIAL PRIMARY KEY,
                    indicator_code VARCHAR(50) NOT NULL,
                    date DATE NOT NULL,
                    value REAL,
                    scraped_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE(indicator_code, date)
                )
            ''').format(sql.Identifier(self.schema)))

            # FA-11: the "date" column above is the observation's reference date,
            # not when the statistic was actually released — point-in-time macro
            # (§3.2) needs both kept distinct. series_alias is the F23-facing name
            # (e.g. "CPI_INDEX"); indicator_code stays the raw EVDS series code so
            # existing rows/readers keep working untouched.
            cursor.execute(sql.SQL('''
                ALTER TABLE {}.tcmb_macro_data
                    ADD COLUMN IF NOT EXISTS series_alias VARCHAR(50),
                    ADD COLUMN IF NOT EXISTS reference_period VARCHAR(20),
                    ADD COLUMN IF NOT EXISTS release_date DATE,
                    ADD COLUMN IF NOT EXISTS unit VARCHAR(50),
                    ADD COLUMN IF NOT EXISTS frequency VARCHAR(20),
                    ADD COLUMN IF NOT EXISTS publisher VARCHAR(20),
                    ADD COLUMN IF NOT EXISTS revision_id VARCHAR(100)
            ''').format(sql.Identifier(self.schema)))
            cursor.execute(sql.SQL('''
                CREATE INDEX IF NOT EXISTS idx_tcmb_macro_alias
                ON {}.tcmb_macro_data(series_alias, date DESC)
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

            # --- FA-02 point-in-time columns (idempotent ALTERs) -------------
            # Every KAP financial-table member (not just the latest annual) is now
            # kept, and a restatement gets a NEW revision row rather than overwriting
            # the first-published one. revision_id defaults to a synthetic
            # "legacy:<id>" for rows written before this migration so the unique key
            # swap below never collides with pre-existing data.
            cursor.execute(sql.SQL('''
                ALTER TABLE {0}.kap_financial_statements
                    ADD COLUMN IF NOT EXISTS consolidation VARCHAR(20) NOT NULL DEFAULT 'consolidated',
                    ADD COLUMN IF NOT EXISTS revision_id VARCHAR(100),
                    ADD COLUMN IF NOT EXISTS published_at TIMESTAMP,
                    ADD COLUMN IF NOT EXISTS available_at TIMESTAMP,
                    ADD COLUMN IF NOT EXISTS period_end DATE,
                    ADD COLUMN IF NOT EXISTS statement_template VARCHAR(20) NOT NULL DEFAULT 'industrial',
                    ADD COLUMN IF NOT EXISTS flow_basis VARCHAR(10) NOT NULL DEFAULT 'ytd'
            ''').format(sql.Identifier(self.schema)))
            cursor.execute(sql.SQL('''
                UPDATE {0}.kap_financial_statements
                SET revision_id = 'legacy:' || id::text
                WHERE revision_id IS NULL
            ''').format(sql.Identifier(self.schema)))
            cursor.execute(sql.SQL('''
                ALTER TABLE {0}.kap_financial_statements
                    ALTER COLUMN revision_id SET NOT NULL
            ''').format(sql.Identifier(self.schema)))
            cursor.execute(sql.SQL('''
                ALTER TABLE {0}.kap_financial_statements
                    DROP CONSTRAINT IF EXISTS kap_financial_statements_stock_code_period_key
            ''').format(sql.Identifier(self.schema)))
            cursor.execute(sql.SQL('''
                CREATE UNIQUE INDEX IF NOT EXISTS idx_fin_stmt_pit_key
                ON {0}.kap_financial_statements(stock_code, period, consolidation, revision_id)
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

            # --- FA-02/FA-03 point-in-time + statement line items (idempotent ALTERs) ---
            # Mirrors the kap_financial_statements migration above: every KAP member is
            # kept as its own revision, and FundamentalPayload's new line items (contract
            # 1.1 §3.2 / FA-03) are stored alongside the existing computed ratios so the
            # repository can serve both from one row.
            cursor.execute(sql.SQL('''
                ALTER TABLE {0}.kap_fundamentals
                    ADD COLUMN IF NOT EXISTS consolidation VARCHAR(20) NOT NULL DEFAULT 'consolidated',
                    ADD COLUMN IF NOT EXISTS revision_id VARCHAR(100),
                    ADD COLUMN IF NOT EXISTS published_at TIMESTAMP,
                    ADD COLUMN IF NOT EXISTS available_at TIMESTAMP,
                    ADD COLUMN IF NOT EXISTS period_end DATE,
                    ADD COLUMN IF NOT EXISTS statement_template VARCHAR(20) NOT NULL DEFAULT 'industrial',
                    ADD COLUMN IF NOT EXISTS flow_basis VARCHAR(10) NOT NULL DEFAULT 'ytd',

                    ADD COLUMN IF NOT EXISTS cost_of_sales REAL,
                    ADD COLUMN IF NOT EXISTS gross_profit REAL,
                    ADD COLUMN IF NOT EXISTS operating_profit REAL,
                    ADD COLUMN IF NOT EXISTS ebit REAL,
                    ADD COLUMN IF NOT EXISTS depreciation_amortization REAL,
                    ADD COLUMN IF NOT EXISTS interest_expense REAL,
                    ADD COLUMN IF NOT EXISTS net_finance_expense REAL,
                    ADD COLUMN IF NOT EXISTS tax_expense REAL,
                    ADD COLUMN IF NOT EXISTS pretax_profit REAL,
                    ADD COLUMN IF NOT EXISTS net_income_parent REAL,

                    ADD COLUMN IF NOT EXISTS total_assets REAL,
                    ADD COLUMN IF NOT EXISTS current_assets REAL,
                    ADD COLUMN IF NOT EXISTS cash_and_equivalents REAL,
                    ADD COLUMN IF NOT EXISTS trade_receivables REAL,
                    ADD COLUMN IF NOT EXISTS inventories REAL,
                    ADD COLUMN IF NOT EXISTS current_liabilities REAL,
                    ADD COLUMN IF NOT EXISTS trade_payables REAL,
                    ADD COLUMN IF NOT EXISTS short_term_financial_debt REAL,
                    ADD COLUMN IF NOT EXISTS long_term_financial_debt REAL,
                    ADD COLUMN IF NOT EXISTS total_liabilities REAL,
                    ADD COLUMN IF NOT EXISTS total_equity REAL,
                    ADD COLUMN IF NOT EXISTS equity_parent REAL,
                    ADD COLUMN IF NOT EXISTS minority_interest REAL,
                    ADD COLUMN IF NOT EXISTS retained_earnings REAL,

                    ADD COLUMN IF NOT EXISTS operating_cash_flow REAL,
                    ADD COLUMN IF NOT EXISTS capex REAL,
                    ADD COLUMN IF NOT EXISTS dividends_paid REAL,
                    ADD COLUMN IF NOT EXISTS interest_paid REAL,
                    ADD COLUMN IF NOT EXISTS taxes_paid REAL,

                    ADD COLUMN IF NOT EXISTS shares_outstanding REAL
            ''').format(sql.Identifier(self.schema)))
            cursor.execute(sql.SQL('''
                UPDATE {0}.kap_fundamentals
                SET revision_id = 'legacy:' || id::text
                WHERE revision_id IS NULL
            ''').format(sql.Identifier(self.schema)))
            cursor.execute(sql.SQL('''
                ALTER TABLE {0}.kap_fundamentals
                    ALTER COLUMN revision_id SET NOT NULL
            ''').format(sql.Identifier(self.schema)))
            cursor.execute(sql.SQL('''
                ALTER TABLE {0}.kap_fundamentals
                    DROP CONSTRAINT IF EXISTS kap_fundamentals_stock_code_period_key
            ''').format(sql.Identifier(self.schema)))
            cursor.execute(sql.SQL('''
                CREATE UNIQUE INDEX IF NOT EXISTS idx_fundamentals_pit_key
                ON {0}.kap_fundamentals(stock_code, period, consolidation, revision_id)
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

            # FA-07: normalized event classification per disclosure, one row per
            # disclosure (idempotent on disclosure_index). A re-classification with
            # a newer mapping_version replaces the row for that disclosure — the
            # disclosure itself never changes, only which taxonomy mapped it.
            cursor.execute(sql.SQL('''
                CREATE TABLE IF NOT EXISTS {}.kap_events (
                    id SERIAL PRIMARY KEY,
                    stock_code VARCHAR(20),
                    disclosure_index VARCHAR(100) NOT NULL,
                    event_type VARCHAR(30) NOT NULL,
                    mapping_version VARCHAR(20) NOT NULL,
                    title TEXT,
                    published_at TIMESTAMP,
                    available_at TIMESTAMP,
                    classified_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE(disclosure_index)
                )
            ''').format(sql.Identifier(self.schema)))
            cursor.execute(sql.SQL('''
                CREATE INDEX IF NOT EXISTS idx_kap_events_stock_code
                ON {}.kap_events(stock_code, published_at DESC)
            ''').format(sql.Identifier(self.schema)))
            cursor.execute(sql.SQL('''
                CREATE INDEX IF NOT EXISTS idx_kap_events_type
                ON {}.kap_events(event_type)
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
                    kap_score REAL,
                    kap_count INTEGER DEFAULT 0,
                    combined_score REAL,
                    computed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE(ticker, period_date)
                )
            ''').format(sql.Identifier(self.schema)))

            # Migrate: add youtube columns to existing DBs
            for col, coldef in [
                ("youtube_score", "REAL"),
                ("youtube_count", "INTEGER DEFAULT 0"),
                ("kap_score", "REAL"),
                ("kap_count", "INTEGER DEFAULT 0"),
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

            # Public daily market observations are stored by ticker and trading
            # date.  A repeated collection replaces that date's source row instead
            # of accumulating duplicates.
            cursor.execute(sql.SQL('''
                CREATE TABLE IF NOT EXISTS {}.isyatirim_market_history (
                    ticker VARCHAR(20) NOT NULL,
                    market_date DATE NOT NULL,
                    data JSONB NOT NULL,
                    fetched_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    PRIMARY KEY (ticker, market_date)
                )
            ''').format(sql.Identifier(self.schema)))

            # FA-06 corporate actions with back-adjustment price factors. Keyed on
            # (ticker, ex_date, event_type) so a re-run of the detection job is
            # idempotent; `match_status` distinguishes a verified KAP match from an
            # unmatched share-count change (never a fabricated factor either way).
            cursor.execute(sql.SQL('''
                CREATE TABLE IF NOT EXISTS {}.corporate_actions (
                    id SERIAL PRIMARY KEY,
                    ticker VARCHAR(20) NOT NULL,
                    ex_date DATE NOT NULL,
                    event_type VARCHAR(30) NOT NULL,
                    ratio REAL,
                    subscription_price REAL,
                    cash_amount REAL,
                    price_factor REAL,
                    source_disclosure_index VARCHAR(100),
                    method_version VARCHAR(20) NOT NULL DEFAULT '1',
                    match_status VARCHAR(20) NOT NULL,
                    detected_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE(ticker, ex_date, event_type)
                )
            ''').format(sql.Identifier(self.schema)))
            cursor.execute(sql.SQL('''
                CREATE INDEX IF NOT EXISTS idx_corporate_actions_ticker
                ON {}.corporate_actions(ticker, ex_date DESC)
            ''').format(sql.Identifier(self.schema)))

            # FA-09 daily ownership snapshots. The public company card only ever
            # exposes the CURRENT foreign-ownership / free-float percentage (no
            # upstream history endpoint), so this table is how the history accrues:
            # one row per ticker per day a collection actually ran.
            cursor.execute(sql.SQL('''
                CREATE TABLE IF NOT EXISTS {}.isyatirim_ownership_history (
                    ticker VARCHAR(20) NOT NULL,
                    snapshot_date DATE NOT NULL,
                    foreign_ownership_pct REAL,
                    free_float_pct REAL,
                    fetched_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    PRIMARY KEY (ticker, snapshot_date)
                )
            ''').format(sql.Identifier(self.schema)))

            cursor.execute(sql.SQL('''
                CREATE TABLE IF NOT EXISTS {}.isyatirim_fundamentals (
                    ticker VARCHAR(20) PRIMARY KEY,
                    report_period VARCHAR(20),
                    data JSONB NOT NULL,
                    fetched_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''').format(sql.Identifier(self.schema)))
            cursor.execute(sql.SQL('''
                CREATE TABLE IF NOT EXISTS {}.isyatirim_fundamental_periods (
                    ticker VARCHAR(20) NOT NULL,
                    report_period VARCHAR(20) NOT NULL,
                    data JSONB NOT NULL,
                    fetched_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    PRIMARY KEY (ticker, report_period)
                )
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

    class PoolExhaustedError(Exception):
        """Raised when the database connection pool is exhausted after retries"""
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
                try:
                    cursor = conn.cursor()
                    cursor.execute(sql.SQL("SET search_path TO {}").format(
                        sql.Identifier(self.schema)
                    ))
                    conn.commit()
                except Exception as e:
                    self.pool.putconn(conn)
                    logger.error(f"Failed to set search_path: {e}")
                    raise
                return conn
            except pool.PoolError as e:
                if attempt == retries:
                    logger.error(f"Connection pool exhausted after {retries} retries")
                    raise DatabaseManager.PoolExhaustedError("connection pool exhausted") from e
                logger.warning(f"Pool exhausted, retrying in {wait_ms}ms (attempt {attempt}/{retries})")
                time.sleep(wait_ms / 1000.0)
    
    def return_connection(self, conn):
        """Return a connection to the pool"""
        if conn:
            self.pool.putconn(conn)

    def get_advisory_lock(self, lock_id: int):
        """Try to acquire a session-level Postgres advisory lock.
        Returns the connection if successful, None otherwise.
        """
        conn = self.get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute("SELECT pg_try_advisory_lock(%s)", (lock_id,))
            acquired = cursor.fetchone()[0]
            if acquired:
                return conn
            self.return_connection(conn)
            return None
        except Exception as e:
            logger.error(f"Failed to acquire advisory lock {lock_id}: {e}")
            self.return_connection(conn)
            return None

    def release_advisory_lock(self, conn, lock_id: int):
        """Release the advisory lock and return the connection to the pool."""
        if not conn:
            return
        try:
            cursor = conn.cursor()
            cursor.execute("SELECT pg_advisory_unlock(%s)", (lock_id,))
            conn.commit()
        except Exception as e:
            logger.error(f"Failed to release advisory lock {lock_id}: {e}")
        finally:
            self.return_connection(conn)
    
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

    def record_stock_classification(
        self,
        stock_code: str,
        sector: Optional[str],
        industry: Optional[str],
        as_of: Any,
        taxonomy: str = "kap",
    ) -> bool:
        """
        Record a classification observed as of `as_of` (FA-10). If the most
        recent open row for this (stock_code, taxonomy) already has the same
        (sector, industry), this is a no-op (repeated collection stays
        idempotent). Otherwise the prior open row's valid_to is closed and a
        new row opens at `as_of`.
        """
        code = stock_code.strip().upper()
        conn = self.get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute(
                """SELECT id, sector, industry FROM stock_classification_history
                   WHERE stock_code = %s AND taxonomy = %s AND valid_to IS NULL
                   ORDER BY valid_from DESC LIMIT 1""",
                (code, taxonomy),
            )
            current = cursor.fetchone()
            if current and current[1] == sector and current[2] == industry:
                return True  # unchanged — idempotent no-op

            if current:
                cursor.execute(
                    "UPDATE stock_classification_history SET valid_to = %s WHERE id = %s",
                    (as_of, current[0]),
                )
            cursor.execute(
                """INSERT INTO stock_classification_history
                       (stock_code, sector, industry, taxonomy, valid_from)
                   VALUES (%s, %s, %s, %s, %s)
                   ON CONFLICT (stock_code, taxonomy, valid_from) DO UPDATE SET
                       sector = EXCLUDED.sector, industry = EXCLUDED.industry""",
                (code, sector, industry, taxonomy, as_of),
            )
            conn.commit()
            return True
        except Exception as exc:
            logger.warning("record_stock_classification failed for %s: %s", stock_code, exc)
            conn.rollback()
            return False
        finally:
            self.return_connection(conn)

    def record_index_membership(self, index_code: str, stock_code: str, as_of: Any, is_member: bool) -> bool:
        """
        Record `stock_code`'s membership state in `index_code` as of `as_of`
        (FA-10). `is_member=True` opens a new row if none is currently open;
        `is_member=False` closes the currently-open row, if any. Both
        directions are idempotent no-ops when the state already matches.
        """
        idx = index_code.strip().upper()
        code = stock_code.strip().upper()
        conn = self.get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute(
                """SELECT id FROM index_membership_history
                   WHERE index_code = %s AND stock_code = %s AND valid_to IS NULL""",
                (idx, code),
            )
            open_row = cursor.fetchone()

            if is_member and open_row is None:
                cursor.execute(
                    """INSERT INTO index_membership_history (index_code, stock_code, valid_from)
                       VALUES (%s, %s, %s)
                       ON CONFLICT (index_code, stock_code, valid_from) DO NOTHING""",
                    (idx, code, as_of),
                )
            elif not is_member and open_row is not None:
                cursor.execute(
                    "UPDATE index_membership_history SET valid_to = %s WHERE id = %s",
                    (as_of, open_row[0]),
                )
            conn.commit()
            return True
        except Exception as exc:
            logger.warning("record_index_membership failed for %s/%s: %s", index_code, stock_code, exc)
            conn.rollback()
            return False
        finally:
            self.return_connection(conn)

    def upsert_corporate_action(self, action: Dict[str, Any]) -> bool:
        """
        Upsert one detected corporate action (FA-06), keyed on
        (ticker, ex_date, event_type). Idempotent: re-running detection over the
        same range updates the row in place rather than duplicating it.
        """
        conn = self.get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute(
                """INSERT INTO corporate_actions
                       (ticker, ex_date, event_type, ratio, subscription_price,
                        cash_amount, price_factor, source_disclosure_index,
                        method_version, match_status)
                   VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                   ON CONFLICT (ticker, ex_date, event_type) DO UPDATE SET
                       ratio = EXCLUDED.ratio,
                       subscription_price = EXCLUDED.subscription_price,
                       cash_amount = EXCLUDED.cash_amount,
                       price_factor = EXCLUDED.price_factor,
                       source_disclosure_index = EXCLUDED.source_disclosure_index,
                       method_version = EXCLUDED.method_version,
                       match_status = EXCLUDED.match_status,
                       detected_at = CURRENT_TIMESTAMP""",
                (
                    action["ticker"].strip().upper(),
                    action["ex_date"],
                    action["event_type"],
                    action.get("ratio"),
                    action.get("subscription_price"),
                    action.get("cash_amount"),
                    action.get("price_factor"),
                    action.get("source_disclosure_index"),
                    action.get("method_version", "1"),
                    action["match_status"],
                ),
            )
            conn.commit()
            return True
        except Exception as exc:
            logger.warning("Could not persist corporate action for %s %s: %s", action.get("ticker"), action.get("ex_date"), exc)
            conn.rollback()
            return False
        finally:
            self.return_connection(conn)

    def upsert_kap_event(self, event: Dict[str, Any]) -> bool:
        """
        Upsert one classified event into kap_events, keyed on disclosure_index
        (FA-07). A re-run with the same mapping_version is idempotent; a newer
        mapping_version replaces the prior classification for that disclosure.
        """
        if not event.get("source_disclosure_index"):
            return False
        conn = self.get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute(
                """INSERT INTO kap_events
                       (stock_code, disclosure_index, event_type, mapping_version,
                        title, published_at, available_at)
                   VALUES (%s, %s, %s, %s, %s, %s, %s)
                   ON CONFLICT (disclosure_index) DO UPDATE SET
                       stock_code = EXCLUDED.stock_code,
                       event_type = EXCLUDED.event_type,
                       mapping_version = EXCLUDED.mapping_version,
                       title = EXCLUDED.title,
                       published_at = EXCLUDED.published_at,
                       available_at = EXCLUDED.available_at,
                       classified_at = CURRENT_TIMESTAMP""",
                (
                    event.get("stock_code"),
                    event["source_disclosure_index"],
                    event["event_type"],
                    event["mapping_version"],
                    event.get("title"),
                    event.get("published_at"),
                    event.get("available_at"),
                ),
            )
            conn.commit()
            return True
        except Exception as exc:
            logger.warning("Could not persist KAP event for disclosure %s: %s", event.get("source_disclosure_index"), exc)
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
                    "kap_score", "kap_count", "combined_score"]
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
            "social_count, youtube_score, youtube_count, kap_score, kap_count, combined_score "
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

    # ── İş Yatırım public market-history cache ──────────────────────────────

    def upsert_isyatirim_market_history(self, ticker: str, series: List[Dict[str, Any]]) -> bool:
        """Replace stored source rows by `(ticker, trading_date)`.

        The normalized JSON is retained intact so future UI fields can be added
        without a destructive migration or another upstream request.
        """
        rows = []
        for item in series:
            try:
                market_date = datetime.strptime(str(item["trading_date"]), "%d-%m-%Y").date()
            except (KeyError, TypeError, ValueError):
                continue
            rows.append((ticker.strip().upper(), market_date, Json(item)))
        if not rows:
            return False
        conn = self.get_connection()
        try:
            cursor = conn.cursor()
            cursor.executemany(
                """INSERT INTO isyatirim_market_history (ticker, market_date, data)
                   VALUES (%s, %s, %s)
                   ON CONFLICT (ticker, market_date) DO UPDATE SET
                       data = EXCLUDED.data, fetched_at = CURRENT_TIMESTAMP""",
                rows,
            )
            conn.commit()
            return True
        except Exception as exc:
            logger.warning("Could not persist İş Yatırım market history for %s: %s", ticker, exc)
            conn.rollback()
            return False
        finally:
            self.return_connection(conn)

    def get_isyatirim_market_history(self, ticker: str, days: int, max_age_seconds: int) -> Dict[str, Any]:
        """Read a bounded database cache, ordered oldest to newest."""
        rows = self.query(
            """SELECT data,
                      EXTRACT(EPOCH FROM (CURRENT_TIMESTAMP - fetched_at))::BIGINT AS age_seconds
               FROM isyatirim_market_history
               WHERE ticker = %s
               ORDER BY market_date DESC
               LIMIT %s""",
            (ticker.strip().upper(), days),
        )
        series = [row["data"] for row in reversed(rows) if isinstance(row.get("data"), dict)]
        ages = [int(row["age_seconds"]) for row in rows if row.get("age_seconds") is not None]
        age = min(ages) if ages else None
        return {
            "series": series,
            "age_seconds": age,
            "fresh": bool(series) and age is not None and age <= max_age_seconds,
        }

    # ── İş Yatırım daily ownership snapshots (FA-09) ────────────────────────

    def upsert_isyatirim_ownership_snapshot(
        self,
        ticker: str,
        snapshot_date: Any,
        foreign_ownership_pct: Optional[float],
        free_float_pct: Optional[float],
    ) -> bool:
        """Record one daily ownership snapshot (idempotent per ticker/day)."""
        conn = self.get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute(
                """INSERT INTO isyatirim_ownership_history
                       (ticker, snapshot_date, foreign_ownership_pct, free_float_pct)
                   VALUES (%s, %s, %s, %s)
                   ON CONFLICT (ticker, snapshot_date) DO UPDATE SET
                       foreign_ownership_pct = EXCLUDED.foreign_ownership_pct,
                       free_float_pct = EXCLUDED.free_float_pct,
                       fetched_at = CURRENT_TIMESTAMP""",
                (ticker.strip().upper(), snapshot_date, foreign_ownership_pct, free_float_pct),
            )
            conn.commit()
            return True
        except Exception as exc:
            logger.warning("Could not persist ownership snapshot for %s: %s", ticker, exc)
            conn.rollback()
            return False
        finally:
            self.return_connection(conn)

    def upsert_isyatirim_fundamentals(self, ticker: str, payload: Dict[str, Any]) -> bool:
        """Store one current İş Yatırım fundamental snapshot per ticker."""
        conn = self.get_connection()
        try:
            cursor = conn.cursor()
            periods = payload.get("reported_periods") or []
            cursor.execute(
                """INSERT INTO isyatirim_fundamentals (ticker, report_period, data)
                   VALUES (%s, %s, %s)
                   ON CONFLICT (ticker) DO UPDATE SET
                       report_period = EXCLUDED.report_period,
                       data = EXCLUDED.data,
                       fetched_at = CURRENT_TIMESTAMP""",
                (ticker.strip().upper(), periods[0] if periods else None, Json(payload)),
            )
            cursor.executemany(
                """INSERT INTO isyatirim_fundamental_periods (ticker, report_period, data)
                   VALUES (%s, %s, %s)
                   ON CONFLICT (ticker, report_period) DO UPDATE SET
                       data = EXCLUDED.data, fetched_at = CURRENT_TIMESTAMP""",
                [
                    (ticker.strip().upper(), period["report_period"], Json(period))
                    for period in payload.get("one_year_statement_history", [])
                    if period.get("report_period")
                ],
            )
            conn.commit()
            return True
        except Exception as exc:
            logger.warning("Could not persist İş Yatırım fundamentals for %s: %s", ticker, exc)
            conn.rollback()
            return False
        finally:
            self.return_connection(conn)

    def get_isyatirim_fundamentals(self, ticker: str, max_age_seconds: int) -> Dict[str, Any]:
        """Read a fresh current fundamental snapshot from PostgreSQL if present."""
        rows = self.query(
            """SELECT data,
                      EXTRACT(EPOCH FROM (CURRENT_TIMESTAMP - fetched_at))::BIGINT AS age_seconds
               FROM isyatirim_fundamentals WHERE ticker = %s LIMIT 1""",
            (ticker.strip().upper(),),
        )
        if not rows or not isinstance(rows[0].get("data"), dict):
            return {"fresh": False, "payload": None, "age_seconds": None}
        age = rows[0].get("age_seconds")
        age = int(age) if age is not None else None
        return {
            "fresh": age is not None and age <= max_age_seconds,
            "payload": rows[0]["data"],
            "age_seconds": age,
        }

    def list_isyatirim_fundamentals(self, query_text: str, limit: int = 50) -> List[Dict[str, Any]]:
        """Search the locally cached current snapshots; no upstream request occurs."""
        rows = self.query(
            """SELECT ticker, report_period, data,
                      EXTRACT(EPOCH FROM (CURRENT_TIMESTAMP - fetched_at))::BIGINT AS age_seconds
               FROM isyatirim_fundamentals
               WHERE ticker ILIKE %s
               ORDER BY ticker LIMIT %s""",
            (f"%{query_text.strip().upper()}%", limit),
        )
        return rows

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
