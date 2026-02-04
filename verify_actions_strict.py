
from firecrawl import Firecrawl
import os
import sys

def get_val(obj, key):
    """Helper to get value whether it's dict or object"""
    if isinstance(obj, dict):
        return obj.get(key)
    return getattr(obj, key, None)

def verify_actions():
    api_url = "http://localhost:3002"
    api_key = os.getenv("FIRECRAWL_API_KEY", "fc-USER_API_KEY")
    app = Firecrawl(api_url=api_url, api_key=api_key)

    print("=== VERIFYING SEARCH ACTION ===")
    # 1. Search Test on DuckDuckGo
    # We expect the page title to change from "DuckDuckGo..." to "term at DuckDuckGo"
    actions = [
        {"type": "wait", "milliseconds": 2000},
        # Use ID selector which is more robust
        {"type": "write", "text": "firecrawl agent", "selector": "#searchbox_input"},
        {"type": "wait", "milliseconds": 1000},
        # Press Enter usually works, but let's try clicking the button if it exists, or just Enter
        {"type": "press", "key": "Enter"},
        {"type": "wait", "milliseconds": 5000} # Wait for results to load
    ]
    
    print("Running Search Action on DuckDuckGo...")
    try:
        response = app.scrape(
            url="https://duckduckgo.com",
            formats=["markdown"],
            actions=actions
        )
        
        metadata = get_val(response, "metadata") or {}
        # metadata might also be an object
        title = get_val(metadata, "title") or "No Title"
        source_url = get_val(metadata, "sourceURL") or get_val(metadata, "source_url") or "No URL"
        content = (get_val(response, "markdown") or "")[:500].replace('\n', ' ')
        
        print(f"Final URL: {source_url}")
        print(f"Final Title: {title}")
        print(f"Content Snippet: {content}")
        
        if "firecrawl agent" in title.lower() or "firecrawl agent" in content.lower():
            print("SUCCESS: Search query found in results.")
        else:
            print("FAILURE: Search query NOT found in results (actions may have failed).")
            
    except Exception as e:
        print(f"Error: {e}")

    print("\n=== VERIFYING CLICK ACTION ===")
    # 2. Click Test on Wikipedia
    # Navigate from main page to English page
    actions = [
        {"type": "wait", "milliseconds": 2000},
        # Try specifically clicking the 'strong' tag which catches the click often
        {"type": "click", "selector": "#js-link-box-en > strong"}, 
        {"type": "wait", "milliseconds": 5000}
    ]
    
    print("Running Click Action on Wikipedia...")
    try:
        response = app.scrape(
            url="https://www.wikipedia.org",
            formats=["markdown"],
            actions=actions
        )
        
        metadata = get_val(response, "metadata") or {}
        title = get_val(metadata, "title") or "No Title"
        source_url = get_val(metadata, "sourceURL") or get_val(metadata, "source_url") or "No URL"
        
        print(f"Final URL: {source_url}")
        print(f"Final Title: {title}")
        
        if "en.wikipedia.org" in source_url:
            print("SUCCESS: Navigated to English Wikipedia.")
        else:
            print("FAILURE: Did not navigate to English Wikipedia.")

    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    verify_actions()
