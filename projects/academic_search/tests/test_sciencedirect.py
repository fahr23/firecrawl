"""
Test script for ScienceDirect scraping
"""
from firecrawl import Firecrawl
import os
import re

def main():
    app = Firecrawl(
        api_url="http://localhost:3002", 
        api_key=os.getenv("FIRECRAWL_API_KEY", "fc-USER_API_KEY")
    )

    print("Testing ScienceDirect search page...")
    response = app.scrape(
        url="https://www.sciencedirect.com/search?qs=renewable+energy&show=25",
        formats=["markdown"],
        actions=[
            {"type": "wait", "milliseconds": 6000},
            {"type": "scroll", "direction": "down"},
            {"type": "wait", "milliseconds": 2000},
            {"type": "scroll", "direction": "down"},
            {"type": "wait", "milliseconds": 2000},
        ],
        timeout=120000
    )

    md = response.get("markdown") if isinstance(response, dict) else getattr(response, "markdown", "")
    if md:
        print(f"Got {len(md)} chars")
        print("\n--- Content sample ---")
        print(md[:4000])
        
        # Find article links
        pattern = r'\[([^\]]+)\]\((https?://[^\)]*(?:/pii/|/article/)[^\)]+)\)'
        matches = re.findall(pattern, md)
        print(f"\n\nFound {len(matches)} article links")
        for title, url in matches[:5]:
            print(f"  - {title[:60]}...")
            print(f"    {url}")
    else:
        print("No content")

if __name__ == "__main__":
    main()
