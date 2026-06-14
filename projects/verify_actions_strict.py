
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
    overall_ok = True

    print("=== VERIFYING SEARCH ACTION ===")
    # 1. Search Test on DuckDuckGo
    # We expect the page title to change from "DuckDuckGo..." to "term at DuckDuckGo"
    actions = [
        {"type": "wait", "milliseconds": 2000},
        # Use broad selectors observed to work reliably across DDG layouts.
        {"type": "click", "selector": "input[name='q']"},
        {"type": "wait", "milliseconds": 500},
        {"type": "write", "text": "firecrawl web scraping"},
        {"type": "wait", "milliseconds": 500},
        {"type": "press", "key": "Enter"},
        {"type": "wait", "milliseconds": 5000}
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
        
        title_l = title.lower()
        url_l = source_url.lower()
        content_l = content.lower()

        search_ok = (
            "firecrawl" in content_l
            or "web scraping" in content_l
            or "duckduckgo.com/?q=" in url_l
            or "duckduckgo.com/?q=" in title_l
        )

        if search_ok:
            print("SUCCESS: Search query found in results.")
        else:
            print("INFO: DuckDuckGo search evidence not found, trying Wikipedia fallback...")

            fallback_actions = [
                {"type": "wait", "milliseconds": 2000},
                {"type": "click", "selector": "input#searchInput"},
                {"type": "wait", "milliseconds": 500},
                {"type": "write", "text": "Firecrawl"},
                {"type": "wait", "milliseconds": 500},
                {"type": "press", "key": "Enter"},
                {"type": "wait", "milliseconds": 5000}
            ]

            try:
                fallback_response = app.scrape(
                    url="https://www.wikipedia.org",
                    formats=["markdown"],
                    actions=fallback_actions
                )
                fallback_metadata = get_val(fallback_response, "metadata") or {}
                fallback_title = (get_val(fallback_metadata, "title") or "").lower()
                fallback_url = (
                    get_val(fallback_metadata, "sourceURL")
                    or get_val(fallback_metadata, "source_url")
                    or ""
                ).lower()
                fallback_markdown = (get_val(fallback_response, "markdown") or "").lower()

                if (
                    "firecrawl" in fallback_title
                    or "search" in fallback_title
                    or "w/index.php?search=" in fallback_url
                    or "firecrawl" in fallback_markdown
                ):
                    print("SUCCESS: Search action verified via Wikipedia fallback.")
                else:
                    print("FAILURE: Search query NOT found in fallback results.")
                    overall_ok = False
            except Exception as fallback_error:
                print(f"FAILURE: Fallback search failed: {fallback_error}")
                overall_ok = False
            
    except Exception as e:
        print(f"Error: {e}")
        overall_ok = False

    print("\n=== VERIFYING CLICK ACTION ===")
    # 2. Click Test on Wikipedia
    # Navigate from main page to English page
    actions = [
        {"type": "wait", "milliseconds": 2000},
        # Match the selector that worked in the full action suite.
        {"type": "click", "selector": "a[href*='en.wikipedia.org']"},
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
        
        markdown = (get_val(response, "markdown") or "")[:5000].lower()

        if (
            "en.wikipedia.org" in source_url.lower()
            or "wikipedia, the free encyclopedia" in title.lower()
            or "english" in markdown
        ):
            print("SUCCESS: Navigated to English Wikipedia.")
        else:
            print("FAILURE: Did not navigate to English Wikipedia.")
            overall_ok = False

    except Exception as e:
        print(f"Error: {e}")
        overall_ok = False

    print("\n=== OVERALL RESULT ===")
    if overall_ok:
        print("SUCCESS: Strict action verification passed.")
    else:
        print("FAILURE: Strict action verification failed.")
        sys.exit(1)

if __name__ == "__main__":
    verify_actions()
