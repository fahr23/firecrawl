"""
ScienceDirect Demo
This script demonstrates using Firecrawl API v2 to search ScienceDirect and extract links.
"""

from firecrawl import Firecrawl
import base64
import os
import re
import time

def main():
    # Initialize the client (local instance)
    api_url = "http://localhost:3002"
    api_key = os.getenv("FIRECRAWL_API_KEY", "fc-USER_API_KEY")

    print(f"Initializing Firecrawl client with API URL: {api_url}")
    app = Firecrawl(api_url=api_url, api_key=api_key)

    # Define the actions to perform
    actions = [
        # Wait for results to load (ScienceDirect can be heavy)
        {"type": "wait", "milliseconds": 5000},
        
        # Scroll down to see more results
        {"type": "scroll", "direction": "down"},
        
        # Take a screenshot for verification
        {"type": "screenshot", "fullPage": False}
    ]

    print("Starting scrape of ScienceDirect via Bing (renewable energy)...")
    try:
        # Perform the scrape via Bing to avoid direct ScienceDirect blocking on search
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        }
        
        response = app.scrape(
            url="https://www.bing.com/search?q=ScienceDirect+renewable+energy",
            formats=["markdown", "screenshot"],
            actions=actions,
            headers=headers
        )

        # Helper to get value whether it's dict or object
        def get_val(obj, key):
            if isinstance(obj, dict):
                return obj.get(key)
            return getattr(obj, key, None)

        print("Scrape successful!")
        
        # Print Metadata
        metadata = get_val(response, "metadata") or {}
        title = get_val(metadata, "title") if metadata else "Unknown"
        source_url = get_val(metadata, "source_url") or get_val(metadata, "sourceURL") or "Unknown"
        
        print(f"Page Title: {title}")
        print(f"Source URL: {source_url}")

        # Save screenshot
        screenshot_data = get_val(response, "screenshot")
        if screenshot_data:
            filename = "sciencedirect_screenshot.png"
            try:
                if screenshot_data.startswith("http"):
                    print(f"Screenshot available at: {screenshot_data}")
                else:
                    if "," in screenshot_data:
                        screenshot_data = screenshot_data.split(",")[1]
                    with open(filename, "wb") as f:
                        f.write(base64.b64decode(screenshot_data))
                    print(f"Saved screenshot to {filename}")
            except Exception as e:
                print(f"Could not save screenshot: {e}")
        else:
            print("No screenshot returned.")

        # Extract links from markdown
        markdown = get_val(response, "markdown")
        if markdown:
            print("\n--- Scraped Content Snippet ---")
            print(markdown[:500] + "...")
            print("------------------------------")
            
            links = re.findall(r'\[([^\]]+)\]\((http[^)]+)\)', markdown)
            print(f"\nFound {len(links)} links.")
            
            with open("sciencedirect_links.txt", "w", encoding="utf-8") as f:
                for text, url in links:
                    # Clean up text (remove newlines etc)
                    text = text.replace("\n", " ").strip()
                    f.write(f"{text}: {url}\n")
            print("Saved links to sciencedirect_links.txt")
        else:
            print("No markdown content returned.")

    except Exception as e:
        print(f"An error occurred: {e}")

if __name__ == "__main__":
    main()
