#!/usr/bin/env python3
"""
Demonstration of Clarivate Web of Science Starter API Advanced Features

This script showcases all the enhanced capabilities added to the ClarivateSearcher:
1. Field-specific queries (TS, TI, AU, AI, OG, DO, PY, SO)
2. Sorting by citations, publication year, relevance
3. Multiple database support (WOS, BIOABS, MEDLINE)
4. Citation counts and author identifiers
5. Convenience methods for common searches
"""

import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from api_academic_search.engine import create_engine
from api_academic_search.providers import ClarivateSearcher
from api_academic_search.config import Config
import logging

def print_separator(title=""):
    """Print a visual separator."""
    print("\n" + "="*80)
    if title:
        print(f"  {title}")
        print("="*80)
    print()

def print_article(article, index=1):
    """Print article details in a formatted way."""
    print(f"{index}. {article.title}")
    print(f"   Authors: {article.authors[:100]}..." if len(article.authors) > 100 else f"   Authors: {article.authors}")
    print(f"   Journal: {article.journal} ({article.year})")
    if article.doi:
        print(f"   DOI: {article.doi}")
    if article.citation_count is not None:
        print(f"   Citations: {article.citation_count}")
    if article.keywords:
        print(f"   Keywords: {', '.join(article.keywords[:5])}")
    print()

def demo_basic_search():
    """Demo 1: Basic topic search with default settings."""
    print_separator("Demo 1: Basic Topic Search (TS=)")
    
    engine = create_engine(debug=False)
    
    print("Searching for 'machine learning' in all fields (TS=)...")
    result = engine.search("machine learning", max_results=5, providers=["Web of Science"])
    
    print(f"Found {result.total_found:,} total results, showing {len(result.articles)}:\n")
    for i, article in enumerate(result.articles, 1):
        print_article(article, i)

def demo_highly_cited():
    """Demo 2: Search for highly cited papers."""
    print_separator("Demo 2: Highly Cited Papers (Sorted by Citations)")
    
    config = Config()
    searcher = ClarivateSearcher(config)
    
    print("Searching for highly cited papers on 'deep learning' since 2020...")
    result = searcher.search_highly_cited("deep learning", min_year=2020, max_results=5)
    
    print(f"Found {result.total_found:,} total results, showing top {len(result.articles)} by citations:\n")
    for i, article in enumerate(result.articles, 1):
        print_article(article, i)

def demo_author_search():
    """Demo 3: Search by author name."""
    print_separator("Demo 3: Author Search (AU=)")
    
    config = Config()
    searcher = ClarivateSearcher(config)
    
    author = "Einstein A*"
    print(f"Searching for papers by '{author}'...")
    result = searcher.search_by_author(author, max_results=5)
    
    print(f"Found {result.total_found:,} total results, showing {len(result.articles)}:\n")
    for i, article in enumerate(result.articles, 1):
        print_article(article, i)

def demo_organization_search():
    """Demo 4: Search by organization."""
    print_separator("Demo 4: Organization Search (OG=)")
    
    config = Config()
    searcher = ClarivateSearcher(config)
    
    org = "MIT"
    print(f"Searching for papers from '{org}'...")
    result = searcher.search_by_organization(org, max_results=5, sort_by="citations")
    
    print(f"Found {result.total_found:,} total results, showing top {len(result.articles)} by citations:\n")
    for i, article in enumerate(result.articles, 1):
        print_article(article, i)

def demo_advanced_query():
    """Demo 5: Advanced query with boolean operators."""
    print_separator("Demo 5: Advanced Boolean Query")
    
    config = Config()
    searcher = ClarivateSearcher(config)
    
    # Complex query: (machine learning OR deep learning) AND healthcare
    query = "TS=(machine learning OR deep learning) AND TS=(healthcare)"
    print(f"Query: {query}")
    result = searcher.search(query, max_results=5, sort_by="citations")
    
    print(f"\nFound {result.total_found:,} total results, showing {len(result.articles)}:\n")
    for i, article in enumerate(result.articles, 1):
        print_article(article, i)

def demo_year_filtering():
    """Demo 6: Year range filtering."""
    print_separator("Demo 6: Year Range Filtering")
    
    config = Config()
    searcher = ClarivateSearcher(config)
    
    print("Searching for 'quantum computing' papers from 2022-2024...")
    result = searcher.search(
        "quantum computing",
        max_results=5,
        year_min=2022,
        year_max=2024,
        sort_by="year_desc"
    )
    
    print(f"Found {result.total_found:,} total results, showing {len(result.articles)}:\n")
    for i, article in enumerate(result.articles, 1):
        print_article(article, i)

def demo_title_only_search():
    """Demo 7: Title-only search."""
    print_separator("Demo 7: Title-Only Search (TI=)")
    
    config = Config()
    searcher = ClarivateSearcher(config)
    
    query = "TI=(climate change)"
    print(f"Query: {query}")
    result = searcher.search(query, max_results=5, sort_by="year_desc")
    
    print(f"\nFound {result.total_found:,} total results, showing {len(result.articles)}:\n")
    for i, article in enumerate(result.articles, 1):
        print_article(article, i)

def demo_database_selection():
    """Demo 8: Search specific database."""
    print_separator("Demo 8: Database Selection (MEDLINE)")
    
    config = Config()
    searcher = ClarivateSearcher(config)
    
    print("Searching MEDLINE database for 'cancer treatment'...")
    result = searcher.search(
        "cancer treatment",
        max_results=5,
        database="MEDLINE",
        sort_by="year_desc"
    )
    
    print(f"Found {result.total_found:,} total results, showing {len(result.articles)}:\n")
    for i, article in enumerate(result.articles, 1):
        print_article(article, i)

def main():
    """Run all demonstrations."""
    logging.basicConfig(level=logging.WARNING)
    
    print("\n" + "="*80)
    print("  CLARIVATE WEB OF SCIENCE STARTER API - ADVANCED FEATURES DEMO")
    print("="*80)
    
    demos = [
        ("Basic Topic Search", demo_basic_search),
        ("Highly Cited Papers", demo_highly_cited),
        ("Author Search", demo_author_search),
        ("Organization Search", demo_organization_search),
        ("Advanced Boolean Query", demo_advanced_query),
        ("Year Range Filtering", demo_year_filtering),
        ("Title-Only Search", demo_title_only_search),
        ("Database Selection", demo_database_selection),
    ]
    
    print("\nAvailable Demos:")
    for i, (name, _) in enumerate(demos, 1):
        print(f"  {i}. {name}")
    print(f"  {len(demos)+1}. Run All Demos")
    print(f"  0. Exit")
    
    choice = input("\nSelect demo to run (0-{}): ".format(len(demos)+1))
    
    try:
        choice = int(choice)
        if choice == 0:
            print("Exiting...")
            return
        elif choice == len(demos) + 1:
            # Run all demos
            for name, demo_func in demos:
                try:
                    demo_func()
                    input("\nPress Enter to continue to next demo...")
                except Exception as e:
                    print(f"Error in {name}: {e}")
        elif 1 <= choice <= len(demos):
            demos[choice-1][1]()
        else:
            print("Invalid choice!")
    except ValueError:
        print("Invalid input!")
    except KeyboardInterrupt:
        print("\n\nInterrupted by user.")
    except Exception as e:
        print(f"\nError: {e}")

if __name__ == "__main__":
    main()
