#!/usr/bin/env python3
"""
Academic Literature Search CLI

Command-line interface for searching academic databases.

Usage:
    python search_cli.py "machine learning healthcare" --max-results 50
    python search_cli.py "deep learning" --format markdown --output results.md
    python search_cli.py "quantum computing" --analyze --topics
    
Clarivate Web of Science:
    python search_cli.py "machine learning" --sort-by citations --max-results 10
    python search_cli.py "climate change" --field-tag TI --year-min 2020
    python search_cli.py "cancer treatment" --database MEDLINE --sort-by year_desc

For help:
    python search_cli.py --help
"""

import argparse
import sys
import os
import re

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from api_academic_search import create_engine, Config


def main():
    parser = argparse.ArgumentParser(
        description="Search academic literature across multiple databases",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  Basic search:
    %(prog)s "machine learning" --max-results 25
    %(prog)s "climate change" --format markdown --output results.md
    %(prog)s "neural networks" --analyze --topics
    %(prog)s "renewable energy" --use-single-source --enrich
  
  Clarivate Web of Science features:
    %(prog)s "deep learning" --sort-by citations --max-results 10
    %(prog)s "quantum computing" --field-tag TI --year-min 2020
    %(prog)s "cancer treatment" --database MEDLINE --sort-by year_desc
    %(prog)s "AU=(Einstein A*)" --providers "Web of Science" --sort-by citations
    %(prog)s "OG=(MIT)" --sort-by citations --max-results 20
        """
    )
    
    # Required arguments
    parser.add_argument(
        "query",
        help="Search query (use quotes for multi-word queries)"
    )
    
    # Output options
    parser.add_argument(
        "-o", "--output",
        help="Output file path (default: prints to stdout)"
    )
    parser.add_argument(
        "-f", "--format",
        choices=["json", "markdown", "csv", "bibtex", "ris"],
        default="json",
        help="Output format (default: json)"
    )
    
    # Search options
    parser.add_argument(
        "-n", "--max-results",
        type=int,
        default=25,
        help="Maximum number of results (default: 25)"
    )
    parser.add_argument(
        "--year-min",
        type=int,
        help="Minimum publication year (e.g., 2020)"
    )
    parser.add_argument(
        "--year-max",
        type=int,
        help="Maximum publication year (e.g., 2024)"
    )
    parser.add_argument(
        "--use-single-source",
        action="store_true",
        help="Search only the first available source (default: search all sources)"
    )
    parser.add_argument(
        "--enrich",
        action="store_true",
        help="Enrich articles with abstracts from multiple sources"
    )
    
    parser.add_argument(
        "--providers",
        nargs="+",
        help="List of providers to use (e.g. 'google', 'scopus'). Default: all"
    )
    
    # Analysis options
    parser.add_argument(
        "--analyze",
        action="store_true",
        help="Run analysis on results"
    )
    parser.add_argument(
        "--topics",
        action="store_true",
        help="Extract and display top topics"
    )
    
    # API keys
    parser.add_argument(
        "--elsevier-key",
        help="Elsevier/Scopus API key (or set ELSEVIER_API_KEY env var)"
    )
    parser.add_argument(
        "--clarivate-key",
        help="Clarivate Web of Science API key (or set CLARIVATE_API_KEY env var)"
    )
    
    # Clarivate-specific options
    parser.add_argument(
        "--sort-by",
        choices=["relevance", "citations", "most_cited", "year_desc", "year_asc", "newest", "oldest"],
        default="relevance",
        help="Sort order for results (default: relevance). 'citations' for most cited first."
    )
    parser.add_argument(
        "--database",
        choices=["WOS", "BIOABS", "MEDLINE"],
        default="WOS",
        help="Database to search (Clarivate only). WOS=Web of Science, BIOABS=Biological Abstracts, MEDLINE=Medical literature"
    )
    parser.add_argument(
        "--field-tag",
        choices=["TS", "TI", "AU", "OG", "SO"],
        help="Field tag for query (Clarivate). TS=Topic, TI=Title, AU=Author, OG=Organization, SO=Source/Journal"
    )
    
    # LLM options
    parser.add_argument(
        "--llm",
        action="store_true",
        help="Enable LLM-based analysis"
    )
    parser.add_argument(
        "--llm-provider",
        choices=["openai", "anthropic"],
        help="LLM provider to use"
    )
    parser.add_argument(
        "--llm-key",
        help="LLM API key"
    )
    
    # Other options
    parser.add_argument(
        "--debug",
        action="store_true",
        help="Enable debug output"
    )
    parser.add_argument(
        "-v", "--verbose",
        action="store_true",
        help="Verbose output"
    )
    
    args = parser.parse_args()
    
    # Build query with field tag if specified
    query = args.query
    if args.field_tag:
        # Wrap query with field tag if not already present
        if '=' not in query:
            query = f"{args.field_tag}=({query})"
    
    # Create engine
    engine = create_engine(
        elsevier_api_key=args.elsevier_key,
        clarivate_api_key=args.clarivate_key,
        enable_llm=args.llm,
        llm_provider=args.llm_provider,
        llm_api_key=args.llm_key,
        debug=args.debug
    )
    
    if args.verbose:
        print(f"Available sources: {engine.available_sources}")
        print(f"Searching for: '{query}'")
        if args.field_tag:
            print(f"Field tag: {args.field_tag}")
        if args.sort_by != "relevance":
            print(f"Sort by: {args.sort_by}")
        if args.database != "WOS":
            print(f"Database: {args.database}")
        print()
    
    # Search with Clarivate-specific parameters
    # Check if we're using Clarivate provider
    using_clarivate = (
        args.providers and any("web of science" in p.lower() or "clarivate" in p.lower() for p in args.providers)
    ) or (
        not args.providers and args.clarivate_key  # Clarivate available and no specific providers
    )
    
    # Fetch a buffer (4x) to account for filtering losses
    search_limit = args.max_results * 4
    
    # If using Clarivate with specific features, use direct searcher
    if using_clarivate and (args.sort_by != "relevance" or args.database != "WOS"):
        from api_academic_search.providers import ClarivateSearcher
        from api_academic_search.config import Config
        
        searcher = ClarivateSearcher(Config())
        results = searcher.search(
            query,
            max_results=search_limit,
            year_min=args.year_min,
            year_max=args.year_max,
            sort_by=args.sort_by,
            database=args.database
        )
    else:
        # Standard search through engine
        results = engine.search(
            query,
            max_results=search_limit,
            use_all_sources=not args.use_single_source,
            year_min=args.year_min,
            year_max=args.year_max,
            providers=args.providers
        )
    
    if args.verbose:
        print(f"Found {results.total_found:,} total results")
        print(f"Retrieved {len(results.articles)} articles (buffer)")
        print()
    
    # Always enrich to ensure we can verify content
    if args.verbose or True: # Force verbose logging for this
        print("Enriching abstracts for accuracy check...")
    results = engine.enrich_abstracts(results)
    
    # Filter by content Relevance
    # (The user specifically asked to "read abstract for search accuracy")
    original_count = len(results.articles)
    
    # Extract filter terms: if query has field tags, extract what's inside the tags
    filter_query = args.query
    if '(' in filter_query and ')' in filter_query:
        # Simple extraction of terms inside any parentheses
        terms_in_tags = re.findall(r'\((.*?)\)', filter_query)
        if terms_in_tags:
            # Join all extracted parts and remove boolean operators
            filter_query = ' '.join(terms_in_tags)
            filter_query = re.sub(r'\b(AND|OR|NOT)\b', ' ', filter_query, flags=re.IGNORECASE)
    
    filtered_articles = [a for a in results.articles if a.matches_query(filter_query)]
    
    if len(filtered_articles) < original_count and args.verbose:
        print(f"Filtered {original_count - len(filtered_articles)} articles with low relevance (missing query terms)")

    # If filtering was too aggressive (resulted in 0), fall back to original results
    # but only for specialized providers like Clarivate where the API already filtered
    if not filtered_articles and original_count > 0 and using_clarivate:
        if args.verbose:
            print("Post-filtering returned 0 results for Clarivate search. Falling back to API results as they are already pre-filtered.")
        filtered_articles = results.articles

    # Truncate to requested max_results
    if len(filtered_articles) > args.max_results:
        filtered_articles = filtered_articles[:args.max_results]

    # Update results
    results.articles = filtered_articles
    results.total_found = len(filtered_articles) # Adjust total to shown


    # Analysis
    if args.analyze or args.topics:
        if args.topics:
            topics = engine.extract_topics(results)
            print("\n=== Top Topics ===")
            for topic, score in topics[:15]:
                print(f"  {topic}: {score:.1f}")
            print()
        
        if args.analyze:
            analysis = engine.analyze(results)
            print("\n=== Analysis ===")
            for key, value in analysis.items():
                print(f"\n{key}:")
                if isinstance(value, list):
                    for item in value[:10]:
                        print(f"  - {item}")
                else:
                    print(f"  {value}")
            print()
    
    # Output
    # Output
    if args.output:
        filepath = engine.export(results, args.output, format=args.format)
        print(f"Results saved to: {filepath}")
    else:
        # Default: Save to api_academic_search/results/query_timestamp/
        from datetime import datetime
        
        # Get results directory
        base_dir = os.path.dirname(os.path.abspath(__file__))
        results_root = os.path.join(base_dir, "results")
        
        # Create folder name from query and timestamp
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        safe_query = re.sub(r'[^\w\s-]', '', args.query).strip().lower()
        safe_query = re.sub(r'[-\s]+', '_', safe_query)[:50]
        
        # Create the specific result directory
        folder_name = f"{safe_query}_{timestamp}"
        save_dir = os.path.join(results_root, folder_name)
        os.makedirs(save_dir, exist_ok=True)
        
        print(f"Saving results to directory: {save_dir}")
        
        # Export in multiple formats
        formats = [
            'json',
            'csv',
            'markdown',
            'bibtex'
        ]
        
        # Map formats to extensions
        ext_map = {
            'json': 'json',
            'csv': 'csv',
            'markdown': 'md',
            'bibtex': 'bib'
        }
        
        for fmt in formats:
            ext = ext_map.get(fmt, fmt)
            filename = f"{folder_name}.{ext}"
            filepath = os.path.join(save_dir, filename)
            try:
                engine.export(results, filepath, format=fmt)
                print(f"  - Saved {fmt.upper()}: {filename}")
            except Exception as e:
                print(f"  - Failed to save {fmt}: {e}")
    
    # Summary
    if args.verbose:
        with_abstracts = sum(1 for a in results.articles if a.abstract)
        print(f"\n=== Summary ===")
        print(f"Query: {args.query}")
        print(f"Sources: {', '.join(results.sources)}")
        print(f"Total found: {results.total_found:,}")
        print(f"Retrieved: {len(results.articles)}")
        print(f"With abstracts: {with_abstracts}")


if __name__ == "__main__":
    main()
