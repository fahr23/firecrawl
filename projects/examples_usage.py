#!/usr/bin/env python3
"""
Academic Search Package - Usage Examples

This script demonstrates how to use the academic_search package
for searching academic literature across multiple databases.
"""

from academic_search import create_engine, Config

def example_1_basic_search():
    """Example 1: Basic search with default settings."""
    print("\n" + "="*70)
    print("Example 1: Basic Search")
    print("="*70)
    
    # Create engine with default settings
    engine = create_engine()
    
    # Simple search
    results = engine.search("machine learning", max_results=10)
    
    print(f"\nFound {len(results.articles)} articles from {results.sources}")
    print(f"Total available: {results.total_found:,}")
    
    # Display first 3 results
    for i, article in enumerate(results.articles[:3], 1):
        print(f"\n{i}. {article.title}")
        print(f"   Authors: {article.authors or 'N/A'}")
        print(f"   Year: {article.year or 'N/A'}")
        print(f"   Source: {article.source}")
        print(f"   DOI: {article.doi or 'N/A'}")


def example_2_year_filtering():
    """Example 2: Search with year filtering."""
    print("\n" + "="*70)
    print("Example 2: Year-Based Filtering")
    print("="*70)
    
    engine = create_engine()
    
    # Search for recent papers (2023-2024)
    results = engine.search(
        "artificial intelligence ethics",
        max_results=10,
        year_min=2023,
        year_max=2024
    )
    
    print(f"\nSearching for papers from 2023-2024...")
    print(f"Found {len(results.articles)} articles")
    
    for i, article in enumerate(results.articles[:5], 1):
        print(f"\n{i}. [{article.year}] {article.title[:60]}...")


def example_3_all_sources():
    """Example 3: Search all available sources."""
    print("\n" + "="*70)
    print("Example 3: Search All Sources")
    print("="*70)
    
    engine = create_engine()
    
    # Search across all sources
    results = engine.search(
        "renewable energy storage",
        max_results=15,
        use_all_sources=True
    )
    
    print(f"\nSearched sources: {results.sources}")
    print(f"Total articles: {len(results.articles)}")
    
    # Group by source
    by_source = {}
    for article in results.articles:
        source = article.source
        by_source[source] = by_source.get(source, 0) + 1
    
    print("\nArticles by source:")
    for source, count in by_source.items():
        print(f"  {source}: {count} articles")


def example_4_abstract_enrichment():
    """Example 4: Enrich articles with abstracts."""
    print("\n" + "="*70)
    print("Example 4: Abstract Enrichment")
    print("="*70)
    
    engine = create_engine()
    
    # Search
    results = engine.search("quantum computing", max_results=10)
    
    # Check initial abstract coverage
    with_abstracts = sum(1 for a in results.articles if a.abstract)
    print(f"\nBefore enrichment: {with_abstracts}/{len(results.articles)} have abstracts")
    
    # Enrich with abstracts (parallel processing)
    results = engine.enrich_abstracts(results, parallel=True)
    
    # Check after enrichment
    with_abstracts = sum(1 for a in results.articles if a.abstract)
    print(f"After enrichment: {with_abstracts}/{len(results.articles)} have abstracts")
    
    # Show first article with abstract
    for article in results.articles:
        if article.abstract:
            print(f"\nSample article:")
            print(f"Title: {article.title}")
            print(f"Abstract: {article.abstract[:200]}...")
            break


def example_5_topic_extraction():
    """Example 5: Extract topics from search results."""
    print("\n" + "="*70)
    print("Example 5: Topic Extraction")
    print("="*70)
    
    engine = create_engine()
    
    # Search
    results = engine.search(
        "climate change mitigation strategies",
        max_results=20
    )
    
    # Extract top topics
    topics = engine.extract_topics(results, top_n=15)
    
    print(f"\nTop 15 topics from {len(results.articles)} articles:")
    for i, (topic, score) in enumerate(topics, 1):
        print(f"  {i:2d}. {topic:20s} (score: {score:.1f})")


def example_6_export_formats():
    """Example 6: Export results to different formats."""
    print("\n" + "="*70)
    print("Example 6: Export to Multiple Formats")
    print("="*70)
    
    engine = create_engine()
    
    # Search
    results = engine.search("deep learning", max_results=10)
    
    # Export to different formats
    formats = {
        'json': 'results.json',
        'markdown': 'results.md',
        'csv': 'results.csv',
        'bibtex': 'references.bib',
        'ris': 'references.ris'
    }
    
    print(f"\nExporting {len(results.articles)} articles to multiple formats:")
    for format_name, filename in formats.items():
        engine.export(results, filename, format=format_name)
        print(f"  ✓ {filename} ({format_name.upper()})")


def example_7_with_api_key():
    """Example 7: Using Elsevier API key for Scopus access."""
    print("\n" + "="*70)
    print("Example 7: Using Scopus API (with API key)")
    print("="*70)
    
    # Configure with API key
    config = Config()
    config.api.elsevier_api_key = "7e0c8c4ed4e0fb320d69074f093779d9"
    
    engine = create_engine(config)
    
    print(f"\nAvailable sources: {engine.available_sources}")
    
    # Search (will try Scopus first if API key is valid)
    results = engine.search("neural networks", max_results=5)
    
    print(f"Results from: {results.sources}")
    print(f"Found: {len(results.articles)} articles")


def example_8_comprehensive_workflow():
    """Example 8: Complete workflow - search, enrich, analyze, export."""
    print("\n" + "="*70)
    print("Example 8: Complete Research Workflow")
    print("="*70)
    
    engine = create_engine()
    
    query = "transformer models natural language processing"
    
    print(f"\nQuery: '{query}'")
    print("\nStep 1: Searching...")
    results = engine.search(
        query,
        max_results=20,
        year_min=2022,
        use_all_sources=True
    )
    print(f"  ✓ Found {len(results.articles)} articles from {results.sources}")
    
    print("\nStep 2: Enriching abstracts...")
    results = engine.enrich_abstracts(results, parallel=True)
    with_abstracts = sum(1 for a in results.articles if a.abstract)
    print(f"  ✓ {with_abstracts}/{len(results.articles)} now have abstracts")
    
    print("\nStep 3: Extracting topics...")
    topics = engine.extract_topics(results, top_n=10)
    print(f"  ✓ Top 5 topics:")
    for topic, score in topics[:5]:
        print(f"    - {topic} ({score:.1f})")
    
    print("\nStep 4: Exporting results...")
    engine.export(results, "nlp_transformers.json")
    engine.export(results, "nlp_transformers.md")
    print(f"  ✓ Exported to JSON and Markdown")
    
    print("\n✅ Workflow complete!")


def example_9_filtering_results():
    """Example 9: Filter results after search."""
    print("\n" + "="*70)
    print("Example 9: Filtering Search Results")
    print("="*70)
    
    engine = create_engine()
    
    # Search without year filter
    results = engine.search("artificial intelligence", max_results=20)
    
    print(f"\nInitial results: {len(results.articles)} articles")
    
    # Filter to recent papers only
    recent = results.filter_by_year(2020, 2024)
    print(f"After year filter (2020-2024): {len(recent.articles)} articles")
    
    # Filter to only papers with abstracts
    with_abstracts = results.filter_with_abstracts()
    print(f"Papers with abstracts: {len(with_abstracts.articles)} articles")


def example_10_cli_usage():
    """Example 10: Command-line usage examples."""
    print("\n" + "="*70)
    print("Example 10: CLI Usage")
    print("="*70)
    
    print("\nCommand-line examples:")
    print("\n1. Basic search:")
    print('   python -m academic_search.search_cli "machine learning"')
    
    print("\n2. With year filter:")
    print('   python -m academic_search.search_cli "AI ethics" \\')
    print('       --year-min 2023 --year-max 2024 \\')
    print('       --max-results 50')
    
    print("\n3. Search all sources and export:")
    print('   python -m academic_search.search_cli "quantum computing" \\')
    print('       --all-sources \\')
    print('       -o results.md -f markdown')
    
    print("\n4. With abstract enrichment and topic analysis:")
    print('   python -m academic_search.search_cli "renewable energy" \\')
    print('       --year-min 2020 \\')
    print('       --enrich --topics \\')
    print('       -o energy.json')
    
    print("\n5. Comprehensive search:")
    print('   python -m academic_search.search_cli "deep learning healthcare" \\')
    print('       --year-min 2022 --year-max 2024 \\')
    print('       --all-sources --enrich \\')
    print('       --analyze --topics \\')
    print('       -o healthcare_ai.json -f json')


def main():
    """Run all examples."""
    print("\n" + "="*70)
    print("ACADEMIC SEARCH PACKAGE - USAGE EXAMPLES")
    print("="*70)
    
    examples = [
        ("Basic Search", example_1_basic_search),
        ("Year Filtering", example_2_year_filtering),
        ("All Sources", example_3_all_sources),
        ("Abstract Enrichment", example_4_abstract_enrichment),
        ("Topic Extraction", example_5_topic_extraction),
        ("Export Formats", example_6_export_formats),
        ("With API Key", example_7_with_api_key),
        ("Complete Workflow", example_8_comprehensive_workflow),
        ("Filtering Results", example_9_filtering_results),
        ("CLI Usage", example_10_cli_usage),
    ]
    
    print("\nAvailable examples:")
    for i, (name, _) in enumerate(examples, 1):
        print(f"  {i:2d}. {name}")
    
    print("\n" + "="*70)
    choice = input("\nEnter example number to run (1-10, or 'all' for all): ").strip().lower()
    
    if choice == 'all':
        for name, func in examples:
            try:
                func()
            except KeyboardInterrupt:
                print("\n\nStopped by user.")
                break
            except Exception as e:
                print(f"\n❌ Error in {name}: {e}")
    elif choice.isdigit() and 1 <= int(choice) <= len(examples):
        idx = int(choice) - 1
        name, func = examples[idx]
        try:
            func()
        except Exception as e:
            print(f"\n❌ Error: {e}")
            import traceback
            traceback.print_exc()
    else:
        print("Invalid choice. Please run again and select 1-10 or 'all'.")
    
    print("\n" + "="*70)
    print("Examples complete!")
    print("="*70)


if __name__ == "__main__":
    main()
