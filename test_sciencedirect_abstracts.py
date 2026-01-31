#!/usr/bin/env python3
"""
Test ScienceDirect Search and Abstract Extraction
Uses Firecrawl with actions to:
1. Search ScienceDirect for articles
2. Get article links from search results
3. Visit each article page to extract abstract
"""

from firecrawl import FirecrawlApp
import json
import re
import time

# Initialize Firecrawl
app = FirecrawlApp(api_url="http://localhost:3002", api_key="fc-USER_API_KEY")

def test_sciencedirect_search():
    """Test scraping ScienceDirect search page"""
    
    search_url = "https://www.sciencedirect.com/search?qs=renewable+energy"
    
    print(f"\n{'='*60}")
    print("Testing ScienceDirect Search Page")
    print(f"URL: {search_url}")
    print(f"{'='*60}\n")
    
    # Try with actions - wait for page to load, scroll to get more results
    actions = [
        {"type": "wait", "milliseconds": 3000},
        {"type": "scroll", "direction": "down", "amount": 500},
        {"type": "wait", "milliseconds": 2000},
    ]
    
    try:
        result = app.scrape(
            search_url,
            formats=["markdown", "html", "links"],
            actions=actions,
            wait_for=5000,
        )
        
        print(f"✓ Scrape successful!")
        print(f"\nMetadata:")
        if hasattr(result, 'metadata') and result.metadata:
            print(f"  Title: {result.metadata.get('title', 'N/A')}")
            print(f"  Status: {result.metadata.get('statusCode', 'N/A')}")
        
        # Check for article links
        links = []
        if hasattr(result, 'links') and result.links:
            links = result.links
            print(f"\nFound {len(links)} total links")
            
            # Filter for article links
            article_links = [l for l in links if '/science/article/' in l]
            print(f"Found {len(article_links)} article links")
            
            if article_links:
                print("\nFirst 5 article links:")
                for i, link in enumerate(article_links[:5], 1):
                    print(f"  {i}. {link}")
        
        # Show some content
        if hasattr(result, 'markdown') and result.markdown:
            content = result.markdown[:2000]
            print(f"\nContent preview (first 2000 chars):")
            print("-" * 40)
            print(content)
            print("-" * 40)
        
        return result, article_links if links else []
        
    except Exception as e:
        print(f"✗ Error: {e}")
        return None, []


def extract_abstract_from_article(article_url: str) -> dict:
    """Visit article page and extract abstract"""
    
    print(f"\n{'='*60}")
    print(f"Extracting abstract from: {article_url[:80]}...")
    print(f"{'='*60}\n")
    
    # Actions to wait for page load and scroll to abstract section
    actions = [
        {"type": "wait", "milliseconds": 3000},
        {"type": "scroll", "direction": "down", "amount": 300},
        {"type": "wait", "milliseconds": 1000},
    ]
    
    try:
        result = app.scrape(
            article_url,
            formats=["markdown", "html"],
            actions=actions,
            wait_for=5000,
        )
        
        article_data = {
            "url": article_url,
            "title": "",
            "abstract": "",
            "authors": "",
            "journal": "",
            "doi": "",
        }
        
        # Extract metadata
        if hasattr(result, 'metadata') and result.metadata:
            article_data["title"] = result.metadata.get('title', '')
            article_data["doi"] = result.metadata.get('doi', '')
        
        # Try to extract abstract from markdown
        if hasattr(result, 'markdown') and result.markdown:
            content = result.markdown
            
            # Look for abstract section
            abstract_patterns = [
                r'(?:^|\n)#+\s*Abstract\s*\n+(.*?)(?=\n#+|\n\n[A-Z]|\Z)',
                r'(?:^|\n)Abstract\s*\n+(.*?)(?=\n#+|\n\n[A-Z]|Keywords|\Z)',
                r'(?:^|\n)\*\*Abstract\*\*\s*\n*(.*?)(?=\n#+|\n\n\*\*|\Z)',
                r'Abstract[:\s]+(.*?)(?=Keywords|Introduction|Highlights|\Z)',
            ]
            
            for pattern in abstract_patterns:
                match = re.search(pattern, content, re.IGNORECASE | re.DOTALL)
                if match:
                    abstract = match.group(1).strip()
                    # Clean up
                    abstract = re.sub(r'\s+', ' ', abstract)
                    if len(abstract) > 100:  # Valid abstract
                        article_data["abstract"] = abstract[:1500]  # Limit length
                        break
            
            # Try to find authors
            author_match = re.search(r'(?:Authors?|By)[:\s]+(.*?)(?:\n|$)', content, re.IGNORECASE)
            if author_match:
                article_data["authors"] = author_match.group(1).strip()[:200]
            
            # Show preview
            print(f"Title: {article_data['title'][:100]}...")
            print(f"Abstract found: {len(article_data['abstract']) > 0}")
            if article_data['abstract']:
                print(f"Abstract preview: {article_data['abstract'][:300]}...")
        
        return article_data
        
    except Exception as e:
        print(f"✗ Error extracting from {article_url}: {e}")
        return {"url": article_url, "error": str(e)}


def test_full_workflow():
    """Test complete workflow: search -> get links -> extract abstracts"""
    
    print("\n" + "="*70)
    print("FULL WORKFLOW TEST: ScienceDirect Search → Article → Abstract")
    print("="*70)
    
    # Step 1: Search
    search_result, article_links = test_sciencedirect_search()
    
    if not article_links:
        print("\n⚠ No article links found from search page")
        print("Trying with a direct article URL as fallback test...")
        
        # Test with a known article URL
        test_article_url = "https://www.sciencedirect.com/science/article/pii/S0960148124014496"
        article_links = [test_article_url]
    
    # Step 2: Extract abstracts from first few articles
    print(f"\n{'='*70}")
    print(f"Extracting abstracts from {min(3, len(article_links))} articles...")
    print("="*70)
    
    articles_with_abstracts = []
    for i, url in enumerate(article_links[:3], 1):
        print(f"\n[{i}/{min(3, len(article_links))}] Processing article...")
        article_data = extract_abstract_from_article(url)
        articles_with_abstracts.append(article_data)
        time.sleep(2)  # Be polite to the server
    
    # Summary
    print("\n" + "="*70)
    print("SUMMARY")
    print("="*70)
    
    abstracts_found = sum(1 for a in articles_with_abstracts if a.get('abstract'))
    print(f"\nTotal articles processed: {len(articles_with_abstracts)}")
    print(f"Abstracts extracted: {abstracts_found}")
    
    for i, article in enumerate(articles_with_abstracts, 1):
        print(f"\n--- Article {i} ---")
        print(f"Title: {article.get('title', 'N/A')[:80]}...")
        print(f"URL: {article.get('url', 'N/A')[:80]}...")
        if article.get('abstract'):
            print(f"Abstract: {article['abstract'][:200]}...")
        elif article.get('error'):
            print(f"Error: {article['error']}")
        else:
            print("Abstract: Not found")
    
    return articles_with_abstracts


if __name__ == "__main__":
    results = test_full_workflow()
    
    # Save results
    with open("sciencedirect_test_results.json", "w") as f:
        json.dump(results, f, indent=2)
    print(f"\nResults saved to sciencedirect_test_results.json")
