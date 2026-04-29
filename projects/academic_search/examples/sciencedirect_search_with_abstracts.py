#!/usr/bin/env python3
"""
ScienceDirect Literature Search with Abstracts
Strategy: Use Firecrawl's search feature + alternative abstract sources

Since ScienceDirect blocks direct scraping (Cloudflare), we use:
1. Firecrawl's search feature (if available)
2. CrossRef API for DOI lookup and abstracts
3. Semantic Scholar API for abstracts
4. OpenAlex API for abstracts
"""

from firecrawl import FirecrawlApp
import requests
import json
import re
import time
from dataclasses import dataclass, asdict
from typing import List, Optional
from urllib.parse import quote

app = FirecrawlApp(api_url='http://localhost:3002', api_key='fc-USER_API_KEY')


@dataclass
class Article:
    title: str
    url: str
    doi: Optional[str] = None
    abstract: Optional[str] = None
    authors: Optional[str] = None
    journal: Optional[str] = None
    year: Optional[str] = None
    source: str = "unknown"


def get_abstract_from_openalex(doi: str) -> Optional[str]:
    """Get abstract from OpenAlex API using DOI"""
    try:
        url = f"https://api.openalex.org/works/doi:{doi}"
        resp = requests.get(url, timeout=10)
        if resp.status_code == 200:
            data = resp.json()
            # OpenAlex uses inverted index format for abstract
            if data.get('abstract_inverted_index'):
                # Reconstruct abstract from inverted index
                inverted = data['abstract_inverted_index']
                word_positions = []
                for word, positions in inverted.items():
                    for pos in positions:
                        word_positions.append((pos, word))
                word_positions.sort()
                abstract = ' '.join([w for _, w in word_positions])
                return abstract
    except Exception as e:
        print(f"  OpenAlex error: {e}")
    return None


def get_abstract_from_crossref(doi: str) -> Optional[str]:
    """Get abstract from CrossRef API using DOI"""
    try:
        url = f"https://api.crossref.org/works/{doi}"
        headers = {'User-Agent': 'AcademicSearchTool/1.0 (mailto:research@example.com)'}
        resp = requests.get(url, headers=headers, timeout=10)
        if resp.status_code == 200:
            data = resp.json()
            message = data.get('message', {})
            abstract = message.get('abstract', '')
            if abstract:
                # Clean HTML tags
                abstract = re.sub(r'<[^>]+>', '', abstract)
                return abstract.strip()
    except Exception as e:
        print(f"  CrossRef error: {e}")
    return None


def get_abstract_from_semantic_scholar(title: str) -> Optional[dict]:
    """Search Semantic Scholar by title and get abstract"""
    try:
        url = f"https://api.semanticscholar.org/graph/v1/paper/search"
        params = {
            'query': title,
            'limit': 1,
            'fields': 'title,abstract,authors,year,externalIds,url'
        }
        resp = requests.get(url, params=params, timeout=10)
        if resp.status_code == 200:
            data = resp.json()
            papers = data.get('data', [])
            if papers:
                paper = papers[0]
                return {
                    'abstract': paper.get('abstract', ''),
                    'authors': ', '.join([a.get('name', '') for a in paper.get('authors', [])]),
                    'year': paper.get('year', ''),
                    'doi': paper.get('externalIds', {}).get('DOI', '')
                }
    except Exception as e:
        print(f"  Semantic Scholar error: {e}")
    return None


def search_openalex_for_topic(query: str, max_results: int = 20) -> List[Article]:
    """Search OpenAlex API directly for papers on a topic"""
    articles = []
    try:
        url = "https://api.openalex.org/works"
        params = {
            'search': query,
            'per_page': max_results,
            'filter': 'has_abstract:true',
            'sort': 'relevance_score:desc'
        }
        resp = requests.get(url, params=params, timeout=15)
        if resp.status_code == 200:
            data = resp.json()
            for work in data.get('results', []):
                # Reconstruct abstract
                abstract = ""
                if work.get('abstract_inverted_index'):
                    inverted = work['abstract_inverted_index']
                    word_positions = []
                    for word, positions in inverted.items():
                        for pos in positions:
                            word_positions.append((pos, word))
                    word_positions.sort()
                    abstract = ' '.join([w for _, w in word_positions])
                
                # Get DOI
                doi = work.get('doi', '').replace('https://doi.org/', '') if work.get('doi') else None
                
                # Get authors
                authors = ', '.join([a.get('author', {}).get('display_name', '') 
                                    for a in work.get('authorships', [])[:5]])
                
                article = Article(
                    title=work.get('title', 'No title'),
                    url=work.get('primary_location', {}).get('landing_page_url', work.get('doi', '')),
                    doi=doi,
                    abstract=abstract,
                    authors=authors,
                    journal=work.get('primary_location', {}).get('source', {}).get('display_name', ''),
                    year=str(work.get('publication_year', '')),
                    source='OpenAlex'
                )
                articles.append(article)
                
    except Exception as e:
        print(f"OpenAlex search error: {e}")
    
    return articles


def search_sciencedirect_via_scopus(query: str) -> List[Article]:
    """
    ScienceDirect articles are indexed in Scopus (same publisher: Elsevier)
    This uses OpenAlex which indexes Scopus/ScienceDirect content
    """
    articles = []
    
    # Search OpenAlex with filter for Elsevier sources
    try:
        url = "https://api.openalex.org/works"
        params = {
            'search': query,
            'per_page': 25,
            'filter': 'primary_location.source.publisher:Elsevier,has_abstract:true',
            'sort': 'relevance_score:desc'
        }
        resp = requests.get(url, params=params, timeout=15)
        if resp.status_code == 200:
            data = resp.json()
            print(f"  Found {data.get('meta', {}).get('count', 0)} Elsevier papers")
            
            for work in data.get('results', []):
                # Check if it's from ScienceDirect
                url_str = work.get('primary_location', {}).get('landing_page_url', '')
                if not url_str:
                    continue
                    
                # Reconstruct abstract
                abstract = ""
                if work.get('abstract_inverted_index'):
                    inverted = work['abstract_inverted_index']
                    word_positions = []
                    for word, positions in inverted.items():
                        for pos in positions:
                            word_positions.append((pos, word))
                    word_positions.sort()
                    abstract = ' '.join([w for _, w in word_positions])
                
                doi = work.get('doi', '').replace('https://doi.org/', '') if work.get('doi') else None
                authors = ', '.join([a.get('author', {}).get('display_name', '') 
                                    for a in work.get('authorships', [])[:5]])
                
                article = Article(
                    title=work.get('title', 'No title'),
                    url=url_str,
                    doi=doi,
                    abstract=abstract,
                    authors=authors,
                    journal=work.get('primary_location', {}).get('source', {}).get('display_name', ''),
                    year=str(work.get('publication_year', '')),
                    source='ScienceDirect (via OpenAlex)'
                )
                articles.append(article)
                
    except Exception as e:
        print(f"  Error: {e}")
    
    return articles


def try_firecrawl_search(query: str) -> List[Article]:
    """Try using Firecrawl's search feature"""
    articles = []
    
    try:
        # Firecrawl search API
        result = app.search(
            query=f"site:sciencedirect.com {query} abstract",
            limit=10
        )
        
        print(f"  Firecrawl search returned {len(result) if result else 0} results")
        
        if result:
            for item in result:
                # Check if item has the expected attributes
                url = getattr(item, 'url', None) or item.get('url', '') if isinstance(item, dict) else ''
                title = getattr(item, 'title', None) or item.get('title', '') if isinstance(item, dict) else ''
                
                if 'sciencedirect.com' in url:
                    article = Article(
                        title=title,
                        url=url,
                        source='Firecrawl Search'
                    )
                    articles.append(article)
                    
    except Exception as e:
        print(f"  Firecrawl search error: {e}")
    
    return articles


def enrich_article_with_abstract(article: Article) -> Article:
    """Try to get abstract for an article from various sources"""
    
    if article.abstract:
        return article  # Already has abstract
    
    # Try DOI lookup first
    if article.doi:
        print(f"  Trying DOI: {article.doi}")
        abstract = get_abstract_from_openalex(article.doi)
        if abstract:
            article.abstract = abstract
            return article
            
        abstract = get_abstract_from_crossref(article.doi)
        if abstract:
            article.abstract = abstract
            return article
    
    # Try title search on Semantic Scholar
    if article.title and len(article.title) > 10:
        print(f"  Searching by title...")
        result = get_abstract_from_semantic_scholar(article.title)
        if result and result.get('abstract'):
            article.abstract = result['abstract']
            if not article.authors:
                article.authors = result.get('authors', '')
            if not article.year:
                article.year = result.get('year', '')
            if not article.doi:
                article.doi = result.get('doi', '')
    
    return article


def search_sciencedirect_literature(query: str, max_results: int = 30) -> List[Article]:
    """
    Main function to search ScienceDirect-related literature with abstracts
    """
    print(f"\n{'='*70}")
    print(f"SCIENCEDIRECT LITERATURE SEARCH")
    print(f"Query: {query}")
    print(f"{'='*70}\n")
    
    all_articles = []
    
    # Method 1: Try Firecrawl search
    print("1. Trying Firecrawl search...")
    fc_articles = try_firecrawl_search(query)
    all_articles.extend(fc_articles)
    print(f"   Found: {len(fc_articles)} articles")
    
    # Method 2: OpenAlex (ScienceDirect/Elsevier filter)
    print("\n2. Searching OpenAlex (Elsevier/ScienceDirect papers)...")
    sd_articles = search_sciencedirect_via_scopus(query)
    all_articles.extend(sd_articles)
    print(f"   Found: {len(sd_articles)} articles with abstracts")
    
    # Method 3: General OpenAlex search for topic
    print("\n3. Searching OpenAlex (all sources)...")
    oa_articles = search_openalex_for_topic(query, max_results=20)
    all_articles.extend(oa_articles)
    print(f"   Found: {len(oa_articles)} articles")
    
    # Enrich articles without abstracts
    print("\n4. Enriching articles with abstracts...")
    enriched = 0
    for i, article in enumerate(all_articles):
        if not article.abstract:
            all_articles[i] = enrich_article_with_abstract(article)
            if all_articles[i].abstract:
                enriched += 1
            time.sleep(0.5)  # Rate limiting
    print(f"   Enriched {enriched} additional articles")
    
    # Deduplicate by title
    seen_titles = set()
    unique_articles = []
    for article in all_articles:
        title_key = article.title.lower()[:50] if article.title else ''
        if title_key and title_key not in seen_titles:
            seen_titles.add(title_key)
            unique_articles.append(article)
    
    # Sort by whether they have abstracts
    unique_articles.sort(key=lambda x: (not bool(x.abstract), x.title))
    
    return unique_articles[:max_results]


def display_results(articles: List[Article]):
    """Display search results"""
    print(f"\n{'='*70}")
    print(f"SEARCH RESULTS: {len(articles)} articles")
    print(f"{'='*70}")
    
    with_abstracts = sum(1 for a in articles if a.abstract)
    print(f"Articles with abstracts: {with_abstracts}")
    print(f"Articles without abstracts: {len(articles) - with_abstracts}")
    
    for i, article in enumerate(articles, 1):
        print(f"\n{'─'*60}")
        print(f"[{i}] {article.title[:80]}{'...' if len(article.title) > 80 else ''}")
        print(f"    Source: {article.source}")
        print(f"    URL: {article.url[:70]}{'...' if len(article.url) > 70 else ''}")
        if article.doi:
            print(f"    DOI: {article.doi}")
        if article.authors:
            print(f"    Authors: {article.authors[:60]}{'...' if len(article.authors) > 60 else ''}")
        if article.year:
            print(f"    Year: {article.year}")
        if article.journal:
            print(f"    Journal: {article.journal}")
        if article.abstract:
            print(f"    Abstract: {article.abstract[:300]}...")
        else:
            print(f"    Abstract: [Not available]")


def save_results(articles: List[Article], filename: str):
    """Save results to JSON"""
    data = [asdict(a) for a in articles]
    with open(filename, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    print(f"\nResults saved to {filename}")


if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description='Search ScienceDirect literature with abstracts')
    parser.add_argument('query', help='Search query')
    parser.add_argument('--max', type=int, default=30, help='Maximum results')
    parser.add_argument('--output', default='sciencedirect_results.json', help='Output file')
    
    args = parser.parse_args()
    
    articles = search_sciencedirect_literature(args.query, args.max)
    display_results(articles)
    save_results(articles, args.output)
