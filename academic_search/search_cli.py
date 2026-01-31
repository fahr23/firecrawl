#!/usr/bin/env python3
"""
Academic Literature Search CLI

Command-line interface for searching academic databases.

Usage:
    python search_cli.py "machine learning healthcare" --max-results 50
    python search_cli.py "deep learning" --format markdown --output results.md
    python search_cli.py "quantum computing" --analyze --topics

For help:
    python search_cli.py --help
"""

import argparse
import sys
import os

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from academic_search import create_engine, Config


def main():
    parser = argparse.ArgumentParser(
        description="Search academic literature across multiple databases",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s "machine learning" --max-results 25
  %(prog)s "climate change" --format markdown --output results.md
  %(prog)s "neural networks" --analyze --topics
  %(prog)s "renewable energy" --all-sources --enrich
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
        "--all-sources",
        action="store_true",
        help="Search all available sources and merge results"
    )
    parser.add_argument(
        "--enrich",
        action="store_true",
        help="Enrich articles with abstracts from multiple sources"
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
    
    # Create engine
    engine = create_engine(
        elsevier_api_key=args.elsevier_key,
        enable_llm=args.llm,
        llm_provider=args.llm_provider,
        llm_api_key=args.llm_key,
        debug=args.debug
    )
    
    if args.verbose:
        print(f"Available sources: {engine.available_sources}")
        print(f"Searching for: '{args.query}'")
        print()
    
    # Search
    results = engine.search(
        args.query,
        max_results=args.max_results,
        use_all_sources=args.all_sources
    )
    
    if args.verbose:
        print(f"Found {results.total_found:,} total results")
        print(f"Retrieved {len(results.articles)} articles")
        print()
    
    # Enrich if requested
    if args.enrich:
        if args.verbose:
            print("Enriching abstracts...")
        results = engine.enrich_abstracts(results)
    
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
    if args.output:
        filepath = engine.export(results, args.output, format=args.format)
        print(f"Results saved to: {filepath}")
    else:
        # Print to stdout
        output = engine.export_to_string(results, format=args.format)
        print(output)
    
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
