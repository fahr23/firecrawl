#!/usr/bin/env python3
"""
Test script for Sentiment Analysis API endpoints
Tests both keyword-based and HuggingFace analyzers
"""

import requests
import json
from typing import Dict, Any, List
import time

BASE_URL = "http://localhost:8000"

class SentimentAPITester:
    """Test sentiment analysis API endpoints"""
    
    def __init__(self, base_url: str = BASE_URL):
        self.base_url = base_url
        self.session = requests.Session()
        self.results = []
    
    def test_health_check(self) -> bool:
        """Test health check endpoint"""
        print("\n📋 Testing: Health Check")
        print("-" * 50)
        
        try:
            response = self.session.get(f"{self.base_url}/api/v1/health")
            if response.status_code == 200:
                print("✅ Health check: OK")
                print(f"   Response: {response.json()}")
                return True
            else:
                print(f"❌ Health check failed: {response.status_code}")
                return False
        except Exception as e:
            print(f"❌ Error: {e}")
            return False
    
    def test_sentiment_overview(self) -> bool:
        """Test sentiment overview endpoint"""
        print("\n📊 Testing: Sentiment Overview")
        print("-" * 50)
        
        try:
            response = self.session.get(f"{self.base_url}/api/v1/sentiment/")
            if response.status_code == 200:
                data = response.json()
                print("✅ Sentiment overview: OK")
                print(f"   Total analyses: {data.get('data', {}).get('total_analyses')}")
                print(f"   Sentiment distribution: {data.get('data', {}).get('sentiment_distribution')}")
                return True
            else:
                print(f"❌ Failed: {response.status_code}")
                return False
        except Exception as e:
            print(f"❌ Error: {e}")
            return False
    
    def test_analyze_keyword(self, report_ids: List[int] = [1, 2]) -> bool:
        """Test sentiment analysis with keyword analyzer"""
        print("\n⚡ Testing: Sentiment Analysis (Keyword)")
        print("-" * 50)
        
        try:
            payload = {
                "report_ids": report_ids,
                "analyzer_type": "keyword"
            }
            
            print(f"   Analyzing {len(report_ids)} disclosures...")
            start_time = time.time()
            
            response = self.session.post(
                f"{self.base_url}/api/v1/sentiment/analyze",
                json=payload
            )
            
            elapsed = time.time() - start_time
            
            if response.status_code == 200:
                data = response.json()
                print(f"✅ Analysis complete ({elapsed:.2f}s)")
                print(f"   Successful: {data.get('successful')}/{data.get('total_analyzed')}")
                print(f"   Analyzer: {data['results'][0].get('analyzer')}")
                
                if data['results'][0].get('success'):
                    sentiment = data['results'][0].get('sentiment', {})
                    print(f"   Sample result:")
                    print(f"     - Sentiment: {sentiment.get('overall_sentiment')}")
                    print(f"     - Confidence: {sentiment.get('confidence')}")
                    print(f"     - Key sentiments: {sentiment.get('key_sentiments')}")
                
                return True
            else:
                print(f"❌ Failed: {response.status_code}")
                print(f"   Error: {response.text}")
                return False
        except Exception as e:
            print(f"❌ Error: {e}")
            return False
    
    def test_analyze_huggingface(self, report_ids: List[int] = [1]) -> bool:
        """Test sentiment analysis with HuggingFace analyzer"""
        print("\n🎯 Testing: Sentiment Analysis (HuggingFace)")
        print("-" * 50)
        
        try:
            payload = {
                "report_ids": report_ids,
                "analyzer_type": "huggingface"
            }
            
            print(f"   Analyzing {len(report_ids)} disclosure(s) with HuggingFace...")
            print("   (This may take ~0.25s per disclosure)")
            start_time = time.time()
            
            response = self.session.post(
                f"{self.base_url}/api/v1/sentiment/analyze",
                json=payload
            )
            
            elapsed = time.time() - start_time
            
            if response.status_code == 200:
                data = response.json()
                print(f"✅ Analysis complete ({elapsed:.2f}s)")
                print(f"   Successful: {data.get('successful')}/{data.get('total_analyzed')}")
                print(f"   Analyzer: {data['results'][0].get('analyzer')}")
                
                if data['results'][0].get('success'):
                    sentiment = data['results'][0].get('sentiment', {})
                    print(f"   Sample result:")
                    print(f"     - Sentiment: {sentiment.get('overall_sentiment')}")
                    print(f"     - Confidence: {sentiment.get('confidence')}")
                
                return True
            else:
                print(f"❌ Failed: {response.status_code}")
                print(f"   Error: {response.text}")
                return False
        except Exception as e:
            print(f"❌ Error: {e}")
            return False
    
    def test_auto_analyze(self) -> bool:
        """Test automatic sentiment analysis"""
        print("\n🔄 Testing: Auto-Analyze Recent Disclosures")
        print("-" * 50)
        
        try:
            payload = {
                "days_back": 7,
                "analyzer_type": "keyword",
                "force_reanalyze": False
            }
            
            print(f"   Auto-analyzing last 7 days with keyword analyzer...")
            response = self.session.post(
                f"{self.base_url}/api/v1/sentiment/analyze/auto",
                json=payload
            )
            
            if response.status_code == 200:
                data = response.json()
                analyzed = data.get('data', {}).get('analyzed_count', 0)
                print(f"✅ Auto-analysis complete")
                print(f"   Analyzed: {analyzed} disclosures")
                print(f"   Analyzer type: {data.get('data', {}).get('analyzer_type')}")
                return True
            else:
                print(f"❌ Failed: {response.status_code}")
                print(f"   Error: {response.text}")
                return False
        except Exception as e:
            print(f"❌ Error: {e}")
            return False
    
    def test_get_disclosure_sentiment(self, disclosure_id: int = 1) -> bool:
        """Test getting sentiment for specific disclosure"""
        print(f"\n🔍 Testing: Get Disclosure Sentiment (ID: {disclosure_id})")
        print("-" * 50)
        
        try:
            response = self.session.get(
                f"{self.base_url}/api/v1/sentiment/disclosures/{disclosure_id}"
            )
            
            if response.status_code == 200:
                data = response.json()
                print("✅ Disclosure sentiment retrieved")
                
                if data.get('data', {}).get('sentiment'):
                    sentiment = data['data']['sentiment']
                    print(f"   Sentiment: {sentiment.get('overall_sentiment')}")
                    print(f"   Confidence: {sentiment.get('sentiment_score')}")
                else:
                    print("   No sentiment data available")
                
                return True
            else:
                print(f"❌ Failed: {response.status_code}")
                return False
        except Exception as e:
            print(f"❌ Error: {e}")
            return False
    
    def test_company_sentiment(self, company_name: str = "ASELS") -> bool:
        """Test getting company sentiment history"""
        print(f"\n📈 Testing: Company Sentiment History ({company_name})")
        print("-" * 50)
        
        try:
            response = self.session.get(
                f"{self.base_url}/api/v1/sentiment/company/{company_name}",
                params={"days_back": 30, "limit": 10}
            )
            
            if response.status_code == 200:
                data = response.json()
                print("✅ Company sentiment history retrieved")
                
                history = data.get('data', {}).get('sentiment_history', [])
                print(f"   History entries: {len(history)}")
                
                if history:
                    print(f"   Recent sentiments:")
                    for entry in history[:3]:
                        print(f"     - {entry.get('date')}: {entry.get('sentiment')} ({entry.get('confidence')})")
                
                return True
            else:
                print(f"❌ Failed: {response.status_code}")
                return False
        except Exception as e:
            print(f"❌ Error: {e}")
            return False
    
    def test_sentiment_trends(self) -> bool:
        """Test sentiment trends"""
        print("\n📊 Testing: Sentiment Trends")
        print("-" * 50)
        
        try:
            response = self.session.get(
                f"{self.base_url}/api/v1/sentiment/trends",
                params={"days_back": 30}
            )
            
            if response.status_code == 200:
                data = response.json()
                print("✅ Sentiment trends retrieved")
                
                trends = data.get('data', {}).get('trends', [])
                print(f"   Trend entries: {len(trends)}")
                
                summary = data.get('data', {}).get('summary', {})
                print(f"   Summary:")
                print(f"     - Total analyses: {summary.get('total_analyses')}")
                print(f"     - Positive: {summary.get('positive_percentage'):.1f}%")
                print(f"     - Neutral: {summary.get('neutral_percentage'):.1f}%")
                
                return True
            else:
                print(f"❌ Failed: {response.status_code}")
                return False
        except Exception as e:
            print(f"❌ Error: {e}")
            return False
    
    def run_all_tests(self):
        """Run all tests"""
        print("=" * 70)
        print("🧪 SENTIMENT ANALYSIS API TEST SUITE")
        print("=" * 70)
        
        tests = [
            ("Health Check", self.test_health_check),
            ("Sentiment Overview", self.test_sentiment_overview),
            ("Keyword Analyzer", lambda: self.test_analyze_keyword([1, 2])),
            ("Get Disclosure Sentiment", lambda: self.test_get_disclosure_sentiment(1)),
            ("Company Sentiment History", lambda: self.test_company_sentiment("ASELS")),
            ("Sentiment Trends", self.test_sentiment_trends),
            ("Auto-Analyze", self.test_auto_analyze),
        ]
        
        results = {}
        for test_name, test_func in tests:
            try:
                result = test_func()
                results[test_name] = "✅ PASS" if result else "❌ FAIL"
            except Exception as e:
                print(f"\n❌ Exception in {test_name}: {e}")
                results[test_name] = "❌ ERROR"
        
        # Optional: HuggingFace test (slower)
        print("\n\n" + "=" * 70)
        print("Optional: HuggingFace Analyzer Test (slower, ~25 seconds for 1 item)")
        print("=" * 70)
        print("Run: python test_sentiment_api.py --huggingface")
        print("or manually: curl -X POST http://localhost:8000/api/v1/sentiment/analyze \\")
        print("  -H 'Content-Type: application/json' \\")
        print("  -d '{\"report_ids\": [1], \"analyzer_type\": \"huggingface\"}'")
        
        # Print summary
        print("\n\n" + "=" * 70)
        print("📋 TEST SUMMARY")
        print("=" * 70)
        
        passed = sum(1 for v in results.values() if "PASS" in v)
        total = len(results)
        
        for test_name, result in results.items():
            print(f"{result:12} - {test_name}")
        
        print("=" * 70)
        print(f"Result: {passed}/{total} tests passed")
        print("=" * 70)
        
        return passed == total


def main():
    import sys
    
    tester = SentimentAPITester()
    
    # Check for HuggingFace flag
    if "--huggingface" in sys.argv or "-hf" in sys.argv:
        print("Running HuggingFace analyzer test (this will take ~30 seconds)...")
        tester.test_analyze_huggingface([1])
    else:
        success = tester.run_all_tests()
        sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
