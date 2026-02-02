#!/usr/bin/env python3
"""Test the academic search package with working Elsevier API"""

from academic_search import AcademicSearchEngine, Config

# Create config with API key
config = Config()
config.api.elsevier_api_key = '7e0c8c4ed4e0fb320d69074f093779d9'

# Create engine
engine = AcademicSearchEngine(config)

# Show available sources
print('Available sources:', [s.source_name for s in engine._searchers])
print()

# Test search
print('Searching for "neural networks" (max 3 results)...')
result = engine.search('neural networks', max_results=3)

print(f'\nTotal results found: {result.total_found:,}')
print(f'Returned {len(result.articles)} articles')
print('='*70)

for i, article in enumerate(result.articles, 1):
    print(f'\n{i}. {article.title}')
    print(f'   Source: {article.source}')
    print(f'   Year: {article.year}')
    print(f'   DOI: {article.doi or "N/A"}')
    if article.authors:
        print(f'   Authors: {", ".join(article.authors[:3])}{"..." if len(article.authors) > 3 else ""}')
