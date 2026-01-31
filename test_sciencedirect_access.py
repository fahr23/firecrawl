#!/usr/bin/env python3
"""
Test ScienceDirect with different approaches:
1. Different user agents
2. Using actions for more realistic browsing
3. Using stealth mode if available
"""

from firecrawl import FirecrawlApp
import json

app = FirecrawlApp(api_url='http://localhost:3002', api_key='fc-USER_API_KEY')

def test_with_actions():
    """Try scraping with realistic browser actions"""
    
    url = 'https://www.sciencedirect.com/science/article/pii/S0960148124014496'
    print(f"\n{'='*60}")
    print("Test 1: Using browser actions for realistic behavior")
    print(f"URL: {url}")
    print('='*60)
    
    # Actions to simulate real user behavior
    actions = [
        {"type": "wait", "milliseconds": 2000},
        {"type": "scroll", "direction": "down", "amount": 200},
        {"type": "wait", "milliseconds": 1000},
        {"type": "scroll", "direction": "down", "amount": 300},
        {"type": "wait", "milliseconds": 1000},
    ]
    
    try:
        result = app.scrape(
            url,
            formats=["markdown", "html", "links"],
            actions=actions,
            wait_for=5000,
            timeout=60000,
        )
        
        print(f"\nTitle: {result.metadata.title if result.metadata else 'N/A'}")
        print(f"Markdown length: {len(result.markdown) if result.markdown else 0}")
        
        if result.markdown:
            print("\nContent preview:")
            print("-" * 50)
            print(result.markdown[:1500])
            
        return result
        
    except Exception as e:
        print(f"Error: {e}")
        return None


def test_search_page():
    """Try scraping the search page directly"""
    
    url = 'https://www.sciencedirect.com/search?qs=renewable+energy'
    print(f"\n{'='*60}")
    print("Test 2: Search page scraping")
    print(f"URL: {url}")
    print('='*60)
    
    actions = [
        {"type": "wait", "milliseconds": 3000},
        {"type": "scroll", "direction": "down", "amount": 500},
        {"type": "wait", "milliseconds": 2000},
    ]
    
    try:
        result = app.scrape(
            url,
            formats=["markdown", "html", "links"],
            actions=actions,
            wait_for=5000,
            timeout=60000,
        )
        
        print(f"\nTitle: {result.metadata.title if result.metadata else 'N/A'}")
        print(f"Status: {result.metadata.status_code if result.metadata else 'N/A'}")
        print(f"Markdown length: {len(result.markdown) if result.markdown else 0}")
        
        if result.links:
            article_links = [l for l in result.links if '/science/article/' in l]
            print(f"\nTotal links: {len(result.links)}")
            print(f"Article links: {len(article_links)}")
            if article_links:
                print("First 5 article links:")
                for link in article_links[:5]:
                    print(f"  - {link}")
        
        if result.markdown:
            print("\nContent preview:")
            print("-" * 50)
            print(result.markdown[:2000])
            
        return result
        
    except Exception as e:
        print(f"Error: {e}")
        return None


def test_open_access_article():
    """Try an open access article that should be freely available"""
    
    # Open access article example
    url = 'https://www.sciencedirect.com/science/article/pii/S2352484723001439'
    print(f"\n{'='*60}")
    print("Test 3: Open Access Article")
    print(f"URL: {url}")
    print('='*60)
    
    actions = [
        {"type": "wait", "milliseconds": 3000},
        {"type": "scroll", "direction": "down", "amount": 400},
        {"type": "wait", "milliseconds": 1500},
    ]
    
    try:
        result = app.scrape(
            url,
            formats=["markdown", "html"],
            actions=actions,
            wait_for=5000,
            timeout=60000,
        )
        
        print(f"\nTitle: {result.metadata.title if result.metadata else 'N/A'}")
        print(f"Description: {result.metadata.description[:200] if result.metadata and result.metadata.description else 'N/A'}...")
        print(f"Markdown length: {len(result.markdown) if result.markdown else 0}")
        
        if result.markdown:
            print("\nContent preview:")
            print("-" * 50)
            print(result.markdown[:2500])
            
        return result
        
    except Exception as e:
        print(f"Error: {e}")
        return None


def test_via_google():
    """Try accessing ScienceDirect via Google search"""
    
    url = 'https://www.google.com/search?q=site:sciencedirect.com+renewable+energy+abstract'
    print(f"\n{'='*60}")
    print("Test 4: Via Google Search (site:sciencedirect.com)")
    print(f"URL: {url}")
    print('='*60)
    
    actions = [
        {"type": "wait", "milliseconds": 2000},
    ]
    
    try:
        result = app.scrape(
            url,
            formats=["markdown", "links"],
            actions=actions,
            wait_for=3000,
        )
        
        print(f"\nTitle: {result.metadata.title if result.metadata else 'N/A'}")
        
        if result.links:
            sd_links = [l for l in result.links if 'sciencedirect.com/science/article' in l]
            print(f"\nTotal links: {len(result.links)}")
            print(f"ScienceDirect article links: {len(sd_links)}")
            if sd_links:
                print("First 5 ScienceDirect links:")
                for link in sd_links[:5]:
                    print(f"  - {link}")
        
        if result.markdown:
            print("\nContent preview:")
            print("-" * 50)
            print(result.markdown[:1500])
            
        return result
        
    except Exception as e:
        print(f"Error: {e}")
        return None


if __name__ == "__main__":
    print("\n" + "="*70)
    print("SCIENCEDIRECT ACCESS TESTING")
    print("="*70)
    
    # Test search page
    result2 = test_search_page()
    
    # Test direct article
    result1 = test_with_actions()
    
    # Test open access
    result3 = test_open_access_article()
    
    # Test via Google
    result4 = test_via_google()
    
    print("\n" + "="*70)
    print("SUMMARY")
    print("="*70)
    print(f"Search page: {'Success' if result2 and result2.markdown and len(result2.markdown) > 1000 else 'Blocked/Limited'}")
    print(f"Direct article: {'Success' if result1 and result1.markdown and len(result1.markdown) > 1000 else 'Blocked/Limited'}")
    print(f"Open access: {'Success' if result3 and result3.markdown and len(result3.markdown) > 1000 else 'Blocked/Limited'}")
    print(f"Via Google: {'Success' if result4 and result4.links else 'Failed'}")
