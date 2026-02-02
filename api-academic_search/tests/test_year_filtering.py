#!/usr/bin/env python3
"""
Test script for year-based filtering across all search providers.
"""

from academic_search import create_engine, Config

def test_year_filtering():
    """Test year filtering with all search providers."""
    print("="*70)
    print("Testing Year-Based Filtering")
    print("="*70)
    
    # Create engine with API key
    config = Config()
    config.api.elsevier_api_key = "7e0c8c4ed4e0fb320d69074f093779d9"
    engine = create_engine(config)
    
    test_query = "artificial intelligence"
    year_min = 2023
    year_max = 2024
    max_results = 5
    
    print(f"\nTest Query: '{test_query}'")
    print(f"Year Range: {year_min}-{year_max}")
    print(f"Max Results: {max_results}")
    
    # Test 1: Primary source (Scopus/OpenAlex)
    print("\n" + "="*70)
    print("Test 1: Primary Source (Scopus)")
    print("="*70)
    
    try:
        results = engine.search(
            test_query,
            max_results=max_results,
            year_min=year_min,
            year_max=year_max
        )
        
        print(f"\n✓ Found {len(results.articles)} articles from {results.sources}")
        print(f"  Total available: {results.total_found}")
        
        # Check years
        years_found = []
        for i, article in enumerate(results.articles, 1):
            year = article.year
            years_found.append(year)
            status = "✓" if year and year_min <= int(year) <= year_max else "✗"
            print(f"  {status} Article {i}: {year if year else 'N/A'} - {article.title[:60]}...")
        
        # Validate
        invalid_years = [y for y in years_found if y and (int(y) < year_min or int(y) > year_max)]
        if invalid_years:
            print(f"\n✗ FAILED: Found {len(invalid_years)} articles outside year range: {invalid_years}")
        else:
            print(f"\n✓ PASSED: All articles within year range {year_min}-{year_max}")
            
    except Exception as e:
        print(f"\n✗ ERROR: {e}")
        import traceback
        traceback.print_exc()
    
    # Test 2: All sources
    print("\n" + "="*70)
    print("Test 2: All Sources (Scopus, OpenAlex, Semantic Scholar, arXiv)")
    print("="*70)
    
    try:
        results = engine.search(
            test_query,
            max_results=max_results,
            use_all_sources=True,
            year_min=year_min,
            year_max=year_max
        )
        
        print(f"\n✓ Found {len(results.articles)} articles from {results.sources}")
        
        # Check years by source
        by_source = {}
        for article in results.articles:
            source = article.source
            if source not in by_source:
                by_source[source] = []
            by_source[source].append(article)
        
        print("\nResults by source:")
        for source, articles in by_source.items():
            print(f"\n  {source}: {len(articles)} articles")
            invalid_count = 0
            for article in articles[:3]:  # Show first 3
                year = article.year
                if year:
                    try:
                        year_int = int(year)
                        status = "✓" if year_min <= year_int <= year_max else "✗"
                        if status == "✗":
                            invalid_count += 1
                    except ValueError:
                        status = "?"
                        year = year
                else:
                    status = "?"
                    year = "N/A"
                print(f"    {status} {year} - {article.title[:50]}...")
            
            if invalid_count > 0:
                print(f"    ✗ WARNING: {invalid_count} articles outside year range")
        
        # Overall validation
        all_years = [int(a.year) for a in results.articles if a.year and a.year.isdigit()]
        invalid_years = [y for y in all_years if y < year_min or y > year_max]
        
        if invalid_years:
            print(f"\n✗ FAILED: Found {len(invalid_years)} articles outside year range")
            print(f"  Invalid years: {sorted(set(invalid_years))}")
        else:
            print(f"\n✓ PASSED: All articles with year data are within range {year_min}-{year_max}")
            
    except Exception as e:
        print(f"\n✗ ERROR: {e}")
        import traceback
        traceback.print_exc()
    
    # Test 3: Edge cases
    print("\n" + "="*70)
    print("Test 3: Edge Cases")
    print("="*70)
    
    # Test 3a: Only min year
    print("\nTest 3a: Only minimum year (2023+)")
    try:
        results = engine.search(
            test_query,
            max_results=3,
            year_min=2023
        )
        print(f"✓ Found {len(results.articles)} articles from {year_min}+")
        for article in results.articles:
            print(f"  - {article.year if article.year else 'N/A'}: {article.title[:50]}...")
    except Exception as e:
        print(f"✗ ERROR: {e}")
    
    # Test 3b: Only max year
    print("\nTest 3b: Only maximum year (up to 2024)")
    try:
        results = engine.search(
            test_query,
            max_results=3,
            year_max=2024
        )
        print(f"✓ Found {len(results.articles)} articles up to {year_max}")
        for article in results.articles:
            print(f"  - {article.year if article.year else 'N/A'}: {article.title[:50]}...")
    except Exception as e:
        print(f"✗ ERROR: {e}")
    
    # Test 3c: No year filter
    print("\nTest 3c: No year filter (all years)")
    try:
        results = engine.search(
            test_query,
            max_results=3
        )
        print(f"✓ Found {len(results.articles)} articles (all years)")
        years = [a.year for a in results.articles if a.year]
        print(f"  Year range in results: {min(years) if years else 'N/A'} - {max(years) if years else 'N/A'}")
    except Exception as e:
        print(f"✗ ERROR: {e}")
    
    print("\n" + "="*70)
    print("Testing Complete")
    print("="*70)

if __name__ == "__main__":
    test_year_filtering()
