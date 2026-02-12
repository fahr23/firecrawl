"""
Script Name: open_urls.py
Description: 
    This script automates the process of opening academic article URLs found in a markdown report.
    It is useful when you have a folder containing search results (like 'api_academic_search/results/some_search_folder')
    and you want to quickly open all the source URLs in your browser.
    
    To avoid browser memory issues with large numbers of tabs, this script processes URLs in batches (default: 50).
    It will pause after each batch and wait for user confirmation before proceeding.

Usage:
    python3 open_urls.py <subfolder_path> [batch_size]

Example:
    python3 open_urls.py agent_based_learning_co2_emission_20260204_152644
    python3 open_urls.py agent_based_learning_co2_emission_20260204_152644 20

How it works:
    1. Looks for the first .md file in the provided directory.
    2. Scans for lines formatted as `**URL:** [link](url)`.
    3. Opens unique URLs in batches, pausing for user input between batches.
"""

import os
import re
import webbrowser
import time
import sys

def open_urls_in_md(directory, batch_size=50):
    # Check if directory exists
    if not os.path.isdir(directory):
        print(f"Error: Directory '{directory}' does not exist.")
        return

    # Find .md file in the directory
    md_files = [f for f in os.listdir(directory) if f.endswith(".md")]
    
    if not md_files:
        print(f"No markdown file found in directory: {directory}")
        return

    # Use the first one
    target_file = md_files[0]
    file_path = os.path.join(directory, target_file)
    print(f"Reading file: {file_path}")

    with open(file_path, "r", encoding="utf-8") as f:
        content = f.read()

    # Extract URLs from **URL:** lines
    # Format: **URL:** [link text](actual_url)
    urls = re.findall(r"\*\*URL:\*\* \[.*?\]\((.*?)\)", content)
    
    # Remove duplicates while preserving order
    unique_urls = list(dict.fromkeys(urls))
    total_urls = len(unique_urls)

    if not unique_urls:
        print("No URLs found.")
        return

    print(f"Found {total_urls} unique URLs.")
    
    # Process in batches
    for i in range(0, total_urls, batch_size):
        batch = unique_urls[i : i + batch_size]
        start_idx = i + 1
        end_idx = i + len(batch)
        
        print(f"\nReady to open URLs {start_idx} to {end_idx} (Batch size: {len(batch)})...")
        if i > 0:
            user_input = input("Press Enter to continue (or type 'q' to quit): ")
            if user_input.lower() == 'q':
                print("Stopping script.")
                break
        
        print(f"Opening batch...")
        for j, url in enumerate(batch):
            print(f"  Opening ({i + j + 1}/{total_urls}): {url}")
            webbrowser.open(url)
            time.sleep(0.5) # Slight delay to be nice to the browser
            
        if end_idx < total_urls:
             print(f"\nBatch complete. {total_urls - end_idx} URLs remaining.")
        else:
             print("\nAll URLs have been opened.")

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python open_urls.py <subfolder_name_or_path> [batch_size]")
        sys.exit(1)
    
    target_arg = sys.argv[1]
    
    # Optional batch size argument
    batch_size = 50
    if len(sys.argv) > 2:
        try:
            batch_size = int(sys.argv[2])
        except ValueError:
            print(f"Invalid batch size '{sys.argv[2]}', defaulting to 50.")

    # Resolve path: allow relative or absolute paths
    if os.path.isabs(target_arg):
        target_dir = target_arg
    else:
        target_dir = os.path.join(os.getcwd(), target_arg)
        
    open_urls_in_md(target_dir, batch_size)
