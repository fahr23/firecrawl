"""
Firecrawl Actions Demo
This script demonstrates how to use Firecrawl API v2 with actions to interact with a page.
We will:
1. Go to Google.com
2. Accept cookies (omitted for simplicity, but often handled by headless browsers or regions)
3. Click the search bar (to focus)
4. Type "firecrawl agentic web scraping"
5. Press Enter
6. Wait for results
7. Scroll down
8. Take a screenshot

Prerequisites:
    pip install firecrawl-py
"""

from firecrawl import Firecrawl
import base64
import os
import time

def main():
    # Initialize the client
    # If running against local Firecrawl instance:
    api_url = "http://localhost:3002"
    
    # If using the cloud version:
    # api_url = "https://api.firecrawl.dev"
    # api_key = "YOUR_API_KEY"
    
    # We use a dummy key for local dev (if auth is disabled) or assuming properly configured
    api_key = os.getenv("FIRECRAWL_API_KEY", "fc-USER_API_KEY")

    print(f"Initializing Firecrawl client with API URL: {api_url}")
    app = Firecrawl(api_url=api_url, api_key=api_key)

    # Define the actions to perform
    actions = [
        # Wait for results to load
        {"type": "wait", "milliseconds": 2000},
        
        # Scroll down
        {"type": "scroll", "direction": "down"},
        
        # Take a screenshot
        {"type": "screenshot", "fullPage": False}
    ]

    print("Starting scrape with actions (Bing Search)...")
    try:
        # Perform the scrape
        response = app.scrape(
            url="https://www.bing.com/search?q=elazığ",
            formats=["markdown", "screenshot"],
            actions=actions
        )

        # Handle response
        is_dict = isinstance(response, dict)
        
        # Helper to get value whether it's dict or object
        def get_val(obj, key):
            if isinstance(obj, dict):
                return obj.get(key)
            return getattr(obj, key, None)

        print("Scrape successful!")
        
        # Print Metadata
        metadata = get_val(response, "metadata") or {}
        # metadata might be an object too
        title = get_val(metadata, "title") if metadata else "Unknown"
        source_url = get_val(metadata, "source_url") or get_val(metadata, "sourceURL") or "Unknown"
        
        print(f"Page Title: {title}")
        print(f"Source URL: {source_url}")

        # Save screenshot
        screenshot_data = get_val(response, "screenshot")
        if screenshot_data:
            if screenshot_data.startswith("http"):
                print(f"Screenshot available at: {screenshot_data}")
            else:
                # Assuming base64
                try:
                    # Remove header if present (e.g. data:image/png;base64,)
                    if "," in screenshot_data:
                        screenshot_data = screenshot_data.split(",")[1]
                    
                    filename = "google_search_screenshot.png"
                    with open(filename, "wb") as f:
                        f.write(base64.b64decode(screenshot_data))
                    print(f"Saved screenshot to {filename}")
                except Exception as e:
                    print(f"Could not save screenshot: {e}")
        else:
            print("No screenshot returned.")

        # Print a snippet of the markdown
        markdown = get_val(response, "markdown")
        if markdown:
            print("\n--- Scraped Content Snippet ---")
            print(markdown[:500] + "...")
            print("------------------------------")
            
            # Extract links
            import re
            links = re.findall(r'\[([^\]]+)\]\((http[^)]+)\)', markdown)
            print(f"\nFound {len(links)} links.")
            
            with open("elazig_links.txt", "w", encoding="utf-8") as f:
                for text, url in links:
                    f.write(f"{text}: {url}\n")
            print("Saved links to elazig_links.txt")
            
        else:
            print("No markdown content returned.")

    except Exception as e:
        print(f"An error occurred: {e}")
        # Hint about possible issues
        if "Connection refused" in str(e):
            print("Hint: Make sure the Firecrawl API server is running locally on port 3002.")

if __name__ == "__main__":
    main()
