#!/usr/bin/env python3
"""
Simple test to verify Firecrawl base scraper integration
"""
import asyncio
import sys
import os
from pathlib import Path

# Add paths
sys.path.insert(0, "/workspaces/firecrawl/examples/turkish-financial-data-scraper")

print("🔄 Testing Firecrawl Base Integration...")

async def test_firecrawl_direct():
    """Test Firecrawl directly"""
    try:
        from firecrawl import FirecrawlApp
        
        # Initialize with same config as base scraper
        firecrawl = FirecrawlApp(
            api_key="",  # Empty for self-hosted
            api_url="http://api:3002"  # Self-hosted instance
        )
        
        print("✅ Firecrawl initialized")
        
        # Test scraping KAP
        print("📥 Scraping KAP website...")
        result = firecrawl.scrape(
            "https://kap.org.tr/en/",
            formats=["markdown", "html"],
            wait_for=3000
        )
        
        if result:
            # Handle new Firecrawl response format (Document object)
            html = getattr(result, 'html', '') or ''
            markdown = getattr(result, 'markdown', '') or ''
            
            html_len = len(html)
            md_len = len(markdown)
            
            print(f"✅ Firecrawl scraping successful")
            print(f"   HTML: {html_len:,} chars")
            print(f"   Markdown: {md_len:,} chars")
            
            # Show sample markdown
            if markdown:
                print(f"   Sample: {markdown[:200]}...")
            
            return {
                "html": html,
                "markdown": markdown
            }
        else:
            print("❌ No result from Firecrawl")
            return None
            
    except Exception as e:
        print(f"❌ Firecrawl test failed: {e}")
        import traceback
        traceback.print_exc()
        return None

async def test_minimal_scraper():
    """Test minimal scraper implementation"""
    try:
        # Minimal scraper class without complex dependencies
        class MinimalKAPScraper:
            def __init__(self):
                from firecrawl import FirecrawlApp
                self.firecrawl = FirecrawlApp(
                    api_key="",
                    api_url="http://api:3002"
                )
            
            async def scrape_url(self, url):
                """Simple scrape method"""
                try:
                    result = self.firecrawl.scrape(
                        url,
                        formats=["markdown", "html"],
                        wait_for=3000,
                        timeout=30000
                    )
                    
                    # Handle new Document object format
                    html = getattr(result, 'html', '') or ''
                    markdown = getattr(result, 'markdown', '') or ''
                    
                    return {
                        "success": True,
                        "url": url,
                        "data": {
                            "html": html,
                            "markdown": markdown
                        }
                    }
                except Exception as e:
                    return {
                        "success": False,
                        "url": url,
                        "error": str(e)
                    }
            
            def parse_content(self, html, markdown):
                """Parse scraped content"""
                items = []
                
                if "Notification not found" in html or "Notification not found" in markdown:
                    print("ℹ️  KAP shows 'Notification not found' - no recent disclosures")
                    return []
                
                # Simple parsing logic
                lines = markdown.split('\n') if markdown else []
                
                for i, line in enumerate(lines):
                    line = line.strip()
                    if 'A.Ş.' in line or 'BANKASI' in line:
                        items.append({
                            'id': f'kap_item_{i}',
                            'company_name': line[:50],
                            'content': line,
                            'scraped_at': 'now'
                        })
                
                return items
        
        # Test the minimal scraper
        print("\n🧪 Testing Minimal Scraper...")
        scraper = MinimalKAPScraper()
        
        # Scrape KAP
        result = await scraper.scrape_url("https://kap.org.tr/en/")
        
        if result.get("success"):
            data = result["data"]
            html = data.get("html", "")
            markdown = data.get("markdown", "")
            
            print(f"✅ Scraping successful")
            print(f"   HTML: {len(html):,} chars")
            print(f"   Markdown: {len(markdown):,} chars")
            
            # Parse content
            items = scraper.parse_content(html, markdown)
            print(f"   Parsed items: {len(items)}")
            
            if items:
                print("   Sample items:")
                for item in items[:3]:
                    print(f"     - {item['company_name']}")
            
            return True
        else:
            print(f"❌ Scraping failed: {result.get('error')}")
            return False
    
    except Exception as e:
        print(f"❌ Minimal scraper test failed: {e}")
        import traceback
        traceback.print_exc()
        return False

async def main():
    print("🚀 Firecrawl Base Integration Test")
    print("=" * 40)
    
    # Test 1: Direct Firecrawl
    direct_result = await test_firecrawl_direct()
    
    if direct_result:
        # Test 2: Minimal scraper pattern 
        scraper_success = await test_minimal_scraper()
        
        if scraper_success:
            print("\n🎉 Integration tests passed!")
            print("💡 Firecrawl base integration is working correctly.")
        else:
            print("\n⚠️  Scraper pattern needs adjustment.")
    else:
        print("\n❌ Firecrawl integration failed - check configuration.")

if __name__ == "__main__":
    asyncio.run(main())