#!/usr/bin/env python3

import requests
from bs4 import BeautifulSoup
import re
import json

# Test KAP homepage parsing locally
def test_kap_parsing():
    try:
        print("Fetching KAP homepage...")
        response = requests.get('https://kap.org.tr/tr', timeout=10)
        content = response.text
        print(f"Content length: {len(content)}")
        
        # Look for API endpoints or data URLs in the HTML
        print("\n=== LOOKING FOR API ENDPOINTS ===")
        api_patterns = [
            r'(/api/[^"\'>\s]+)',
            r'(https?://[^"\'>\s]*api[^"\'>\s]*)',
            r'(/tr/[^"\'>\s]*bildirim[^"\'>\s]*)',
            r'fetch\(["\']([^"\']+)["\']',
            r'url:\s*["\']([^"\']+)["\']'
        ]
        
        for pattern in api_patterns:
            matches = re.findall(pattern, content, re.IGNORECASE)
            if matches:
                print(f"Pattern '{pattern}' found: {matches[:3]}")  # Show first 3 matches
        
        # Look for script tags that might contain data
        print("\n=== CHECKING SCRIPT TAGS FOR DATA ===")
        soup = BeautifulSoup(content, 'html.parser')
        scripts = soup.find_all('script')
        for i, script in enumerate(scripts):
            if script.string and ('bildirim' in script.string.lower() or 'disclosure' in script.string.lower() or 'api' in script.string.lower()):
                print(f"Script {i} contains relevant keywords (showing first 500 chars):")
                print(script.string[:500])
                print("---")
        
        # Try to access KAP API directly
        print("\n=== TRYING KAP API ENDPOINTS ===")
        api_urls = [
            'https://kap.org.tr/api/disclosures',
            'https://kap.org.tr/tr/api/disclosures',
            'https://kap.org.tr/api/bildirim',
            'https://kap.org.tr/tr/api/bildirimler',
            'https://kap.org.tr/api/v1/disclosures'
        ]
        
        for url in api_urls:
            try:
                api_response = requests.get(url, timeout=5)
                print(f"URL: {url} -> Status: {api_response.status_code}")
                if api_response.status_code == 200:
                    try:
                        json_data = api_response.json()
                        print(f"  JSON response with {len(json_data)} items" if isinstance(json_data, list) else f"  JSON response: {type(json_data)}")
                        if isinstance(json_data, list) and json_data:
                            print(f"  Sample item: {json.dumps(json_data[0], indent=2)[:300]}...")
                    except:
                        print(f"  Text response: {api_response.text[:200]}...")
            except requests.RequestException as e:
                print(f"URL: {url} -> Error: {e}")
        
        # Check for Next.js data
        print("\n=== LOOKING FOR NEXT.JS DATA ===")
        nextjs_pattern = r'__NEXT_DATA__["\']?\s*=\s*({.*?});'
        nextjs_matches = re.search(nextjs_pattern, content, re.DOTALL)
        if nextjs_matches:
            try:
                nextjs_data = json.loads(nextjs_matches.group(1))
                print(f"Found Next.js data with keys: {nextjs_data.keys()}")
                if 'props' in nextjs_data:
                    print(f"Props keys: {nextjs_data['props'].keys()}")
            except:
                print("Found Next.js data but couldn't parse as JSON")
        
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    test_kap_parsing()