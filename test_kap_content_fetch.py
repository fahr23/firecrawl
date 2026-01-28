#!/usr/bin/env python3
"""Test fetching KAP content and check what format it comes in."""

import sys
sys.path.insert(0, '/workspaces/firecrawl/examples/turkish-financial-data-scraper')

import requests
from firecrawl import FirecrawlApp

def test_content_sources():
    url = "https://kap.org.tr/tr"
    
    print("=== Testing content sources for KAP homepage ===\n")
    
    # Test 1: FirecrawlApp
    print("1. FirecrawlApp scrape:")
    try:
        firecrawl = FirecrawlApp(api_key="", api_url="http://api:3002")
        result = firecrawl.scrape(url, formats=["markdown", "html"], wait_for=1500, timeout=15000)
        
        if result:
            if isinstance(result, dict):
                md = result.get("markdown", "")[:300]
                html = result.get("html", "")[:300]
                print(f"  Result is dict")
                print(f"  markdown: {bool(md)} - {md}...")
                print(f"  html: {bool(html)} - {html}...")
            else:
                print(f"  Result type: {type(result)}")
                print(f"  Has markdown attr: {hasattr(result, 'markdown')}")
                if hasattr(result, 'markdown'):
                    print(f"  markdown: {result.markdown[:300]}...")
                print(f"  Has html attr: {hasattr(result, 'html')}")
                if hasattr(result, 'html'):
                    print(f"  html: {result.html[:300]}...")
        else:
            print("  Result is None")
    except Exception as e:
        print(f"  Error: {e}")
    
    # Test 2: httpx fallback
    print("\n2. httpx GET fallback:")
    try:
        import httpx
        response = requests.get(url, timeout=10)
        print(f"  Status: {response.status_code}")
        content = response.text
        print(f"  Content length: {len(content)}")
        print(f"  Contains 'checkbox': {'checkbox' in content}")
        print(f"  Contains 'A.Ş.': {'A.Ş.' in content}")
        print(f"  Contains 'bildirimler': {'bildirimler' in content.lower()}")
        
        # Find markdown table lines
        table_lines = [line for line in content.splitlines() if line.strip().startswith("|")]
        print(f"  Markdown table lines found: {len(table_lines)}")
        if table_lines:
            print(f"  Sample lines:")
            for line in table_lines[:3]:
                print(f"    {line[:100]}...")
    except Exception as e:
        print(f"  Error: {e}")
    
    # Test 3: BeautifulSoup parsing
    print("\n3. BeautifulSoup parsing:")
    try:
        from bs4 import BeautifulSoup
        response = requests.get(url, timeout=10)
        soup = BeautifulSoup(response.text, 'html.parser')
        
        tables = soup.find_all('table')
        print(f"  Tables found: {len(tables)}")
        for i, table in enumerate(tables):
            rows = table.find_all('tr')
            print(f"  Table {i}: {len(rows)} rows")
            for j, row in enumerate(rows[:2]):
                cells = row.find_all(['td', 'th'])
                cell_text = [c.get_text(strip=True)[:30] for c in cells]
                print(f"    Row {j}: {cell_text}")
    except Exception as e:
        print(f"  Error: {e}")

if __name__ == "__main__":
    test_content_sources()
