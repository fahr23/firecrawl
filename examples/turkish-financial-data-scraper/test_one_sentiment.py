#!/usr/bin/env python3
"""
Test sentiment analysis with just one report for faster testing
"""
import asyncio
import logging
import sys
from config import config
from database.db_manager import DatabaseManager
from scrapers.bloomberg_ht_kap_scraper import BloombergHTKAPScraper
from utils.logger import setup_logging
import os

async def test_one_sentiment():
    """Test sentiment analysis with one report"""
    # Setup logging
    setup_logging(level="INFO", log_file="logs/test_sentiment.log")
    logger = logging.getLogger(__name__)
    
    try:
        # Initialize database manager
        db_manager = DatabaseManager()
        
        # Initialize scraper
        scraper = BloombergHTKAPScraper(db_manager=db_manager)
        
        # Configure LLM for sentiment analysis
        gemini_key = os.getenv("GEMINI_API_KEY")
        if gemini_key:
            try:
                scraper.configure_llm(
                    provider_type="gemini",
                    api_key=gemini_key
                )
                logger.info("✅ LLM configured for sentiment analysis (Gemini)")
                print("✅ LLM configured - sentiment analysis will be performed")
            except Exception as e:
                logger.warning(f"Failed to configure LLM: {e}")
                print(f"⚠️  LLM configuration failed: {e}")
                return False
        else:
            logger.error("GEMINI_API_KEY not set")
            print("❌ GEMINI_API_KEY not set - cannot test sentiment analysis")
            return False
        
        # Get one recent report from database for testing
        conn = db_manager.get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT id, company_code, title, data, scraped_at, report_date 
                FROM turkish_financial.kap_reports 
                WHERE data IS NOT NULL 
                AND LENGTH(data::text) > 100 
                ORDER BY scraped_at DESC 
                LIMIT 1
            """)
            
            row = cursor.fetchone()
            if not row:
                print("❌ No reports found in database to test with")
                return False
            
            report_id, company_code, title, data, scraped_at, report_date = row
            
            # Extract content from data JSON if it exists
            import json
            content = ""
            if isinstance(data, dict):
                content = data.get('content', data.get('summary', str(data)))
            elif isinstance(data, str):
                try:
                    data_dict = json.loads(data)
                    content = data_dict.get('content', data_dict.get('summary', data))
                except:
                    content = data
            else:
                content = str(data)
            
            print(f"🔍 Testing with report ID: {report_id}")
            print(f"🏢 Company: {company_code}")
            print(f"📄 Title: {title[:100]}..." if title else "No title")
            print(f"📅 Report Date: {report_date}")
            print(f"📝 Content length: {len(content)} chars")
            
        finally:
            db_manager.return_connection(conn)
        
        # Analyze sentiment for this specific report
        print(f"\n🤖 Analyzing sentiment for report {report_id}...")
        
        try:
            # Use the LLM analyzer directly
            if scraper.llm_analyzer:
                sentiment_result = scraper.llm_analyzer.analyze_sentiment(content, report_id)
                
                if sentiment_result:
                    print(f"✅ Sentiment analysis completed!")
                    print(f"   📊 Overall Sentiment: {sentiment_result.overall_sentiment}")
                    print(f"   🎯 Confidence: {sentiment_result.confidence:.2f}")
                    print(f"   ⏰ Impact Horizon: {sentiment_result.impact_horizon}")
                    print(f"   🔑 Key Drivers: {sentiment_result.key_drivers}")
                    print(f"   ⚠️  Risk Flags: {sentiment_result.risk_flags}")
                    
                    # Now test saving to database
                    print(f"\n💾 Saving sentiment to database...")
                    
                    # Get the sentiment repository and save
                    from infrastructure.repositories.sentiment_repository_impl import SentimentRepository
                    sentiment_repo = SentimentRepository(db_manager)
                    
                    # Convert to domain object for saving
                    from domain.value_objects.sentiment import SentimentAnalysis, SentimentType, Confidence, ImpactHorizon
                    from datetime import datetime
                    
                    sentiment_domain = SentimentAnalysis(
                        overall_sentiment=SentimentType(sentiment_result.overall_sentiment),
                        confidence=Confidence(sentiment_result.confidence),
                        impact_horizon=ImpactHorizon(sentiment_result.impact_horizon),
                        key_drivers=tuple(sentiment_result.key_drivers),  # Convert to tuple
                        risk_flags=tuple(sentiment_result.risk_flags),  # Convert to tuple
                        tone_descriptors=tuple(sentiment_result.tone_descriptors),  # Convert to tuple
                        target_audience=sentiment_result.target_audience,
                        analysis_text=sentiment_result.analysis_text,
                        analyzed_at=datetime.now()  # Add current timestamp
                    )
                    
                    await sentiment_repo.save(report_id, sentiment_domain)
                    print(f"✅ Successfully saved sentiment for report {report_id}")
                    
                    # Verify it was saved
                    saved_sentiment = await sentiment_repo.find_by_report_id(report_id)
                    if saved_sentiment:
                        print(f"✅ Verified: sentiment found in database")
                        return True
                    else:
                        print(f"❌ Error: sentiment not found in database after saving")
                        return False
                else:
                    print(f"❌ Failed to analyze sentiment")
                    return False
            else:
                print(f"❌ LLM analyzer not configured")
                return False
                
        except Exception as e:
            logger.error(f"Error during sentiment analysis: {e}", exc_info=True)
            print(f"❌ Error during sentiment analysis: {e}")
            return False
            
    except Exception as e:
        logger.error(f"Error in test_one_sentiment: {e}", exc_info=True)
        print(f"❌ Error: {e}")
        return False

if __name__ == "__main__":
    success = asyncio.run(test_one_sentiment())
    sys.exit(0 if success else 1)