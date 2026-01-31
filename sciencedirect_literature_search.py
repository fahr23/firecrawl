#!/usr/bin/env python3
"""
ScienceDirect Literature Search with Full Abstracts
=================================================

Since ScienceDirect has Cloudflare bot protection, this tool:
1. Uses OpenAlex API (indexes Elsevier/ScienceDirect content with abstracts)
2. Uses CrossRef API for additional abstracts
3. Uses Semantic Scholar API for backup
4. Fetches papers from ScienceDirect-owned journals
"""

import requests
import json
import re
import time
from dataclasses import dataclass, asdict, field
from typing import List, Optional, Dict
from collections import Counter
import argparse


@dataclass
class Article:
    title: str
    url: str
    doi: Optional[str] = None
    abstract: Optional[str] = None
    authors: Optional[str] = None
    journal: Optional[str] = None
    year: Optional[str] = None
    keywords: List[str] = field(default_factory=list)
    source: str = "unknown"
    is_sciencedirect: bool = False


class OpenAlexSearcher:
    """Search OpenAlex API - has most ScienceDirect content indexed with abstracts"""
    
    BASE_URL = "https://api.openalex.org"
    
    def __init__(self, email: str = "research@example.com"):
        self.email = email
    
    def _reconstruct_abstract(self, inverted_index: Dict) -> str:
        """Reconstruct abstract from OpenAlex inverted index format"""
        if not inverted_index:
            return ""
        
        word_positions = []
        for word, positions in inverted_index.items():
            for pos in positions:
                word_positions.append((pos, word))
        word_positions.sort()
        return ' '.join([w for _, w in word_positions])
    
    def search_sciencedirect(self, query: str, max_results: int = 25) -> List[Article]:
        """Search for ScienceDirect papers specifically"""
        articles = []
        
        try:
            # Filter for Elsevier publisher (owns ScienceDirect)
            url = f"{self.BASE_URL}/works"
            params = {
                'search': query,
                'per_page': min(max_results, 50),
                'filter': 'primary_location.source.publisher_lineage:P4310320595,has_abstract:true',  # Elsevier
                'sort': 'relevance_score:desc',
                'mailto': self.email
            }
            
            resp = requests.get(url, params=params, timeout=15)
            if resp.status_code == 200:
                data = resp.json()
                print(f"    Found {data.get('meta', {}).get('count', 0)} total Elsevier papers")
                
                for work in data.get('results', []):
                    article = self._parse_work(work, is_sciencedirect=True)
                    if article:
                        articles.append(article)
                        
        except Exception as e:
            print(f"    Error searching Elsevier papers: {e}")
        
        return articles
    
    def search_all(self, query: str, max_results: int = 25) -> List[Article]:
        """Search all sources with abstracts"""
        articles = []
        
        try:
            url = f"{self.BASE_URL}/works"
            params = {
                'search': query,
                'per_page': min(max_results, 50),
                'filter': 'has_abstract:true',
                'sort': 'relevance_score:desc',
                'mailto': self.email
            }
            
            resp = requests.get(url, params=params, timeout=15)
            if resp.status_code == 200:
                data = resp.json()
                
                for work in data.get('results', []):
                    article = self._parse_work(work)
                    if article:
                        articles.append(article)
                        
        except Exception as e:
            print(f"    Error: {e}")
        
        return articles
    
    def _parse_work(self, work: dict, is_sciencedirect: bool = False) -> Optional[Article]:
        """Parse OpenAlex work into Article"""
        try:
            # Get primary location
            primary_loc = work.get('primary_location') or {}
            source = primary_loc.get('source') or {}
            
            # Determine URL
            url = primary_loc.get('landing_page_url', '')
            if not url:
                url = work.get('doi', '')
            
            # Check if it's actually ScienceDirect
            is_sd = 'sciencedirect.com' in url if url else False
            if is_sciencedirect:
                is_sd = True
            
            # Reconstruct abstract
            abstract = self._reconstruct_abstract(work.get('abstract_inverted_index'))
            
            # Get DOI
            doi = work.get('doi', '')
            if doi:
                doi = doi.replace('https://doi.org/', '')
            
            # Get authors (first 5)
            authors = ', '.join([
                a.get('author', {}).get('display_name', '') 
                for a in work.get('authorships', [])[:5]
            ])
            
            # Get keywords from concepts
            keywords = [
                c.get('display_name', '') 
                for c in work.get('concepts', [])[:10]
                if c.get('score', 0) > 0.3
            ]
            
            return Article(
                title=work.get('title', 'Untitled'),
                url=url,
                doi=doi if doi else None,
                abstract=abstract,
                authors=authors,
                journal=source.get('display_name', ''),
                year=str(work.get('publication_year', '')),
                keywords=keywords,
                source='OpenAlex' + (' (ScienceDirect)' if is_sd else ''),
                is_sciencedirect=is_sd
            )
        except Exception as e:
            print(f"      Parse error: {e}")
            return None


class CrossRefSearcher:
    """Search CrossRef API for additional abstracts"""
    
    BASE_URL = "https://api.crossref.org"
    
    def get_abstract_by_doi(self, doi: str) -> Optional[str]:
        """Get abstract for a specific DOI"""
        try:
            url = f"{self.BASE_URL}/works/{doi}"
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
        except Exception:
            pass
        return None


class SemanticScholarSearcher:
    """Search Semantic Scholar API"""
    
    BASE_URL = "https://api.semanticscholar.org/graph/v1"
    
    def search_by_title(self, title: str) -> Optional[dict]:
        """Search by title and get details"""
        try:
            url = f"{self.BASE_URL}/paper/search"
            params = {
                'query': title[:200],  # Limit title length
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
                        'year': paper.get('year'),
                        'doi': paper.get('externalIds', {}).get('DOI')
                    }
        except Exception:
            pass
        return None


class ScienceDirectLiteratureSearch:
    """Main class for ScienceDirect literature search"""
    
    def __init__(self):
        self.openalex = OpenAlexSearcher()
        self.crossref = CrossRefSearcher()
        self.semantic = SemanticScholarSearcher()
    
    def search(self, query: str, max_results: int = 30) -> List[Article]:
        """
        Search for ScienceDirect literature with abstracts
        """
        print(f"\n{'='*70}")
        print(f"SCIENCEDIRECT LITERATURE SEARCH")
        print(f"Query: {query}")
        print(f"{'='*70}")
        
        all_articles = []
        seen_dois = set()
        seen_titles = set()
        
        # Step 1: Search ScienceDirect (Elsevier) papers via OpenAlex
        print(f"\n📚 Step 1: Searching ScienceDirect/Elsevier papers...")
        sd_articles = self.openalex.search_sciencedirect(query, max_results)
        for article in sd_articles:
            title_key = article.title.lower()[:50] if article.title else ''
            doi_key = article.doi.lower() if article.doi else ''
            
            if title_key and title_key not in seen_titles:
                if not doi_key or doi_key not in seen_dois:
                    seen_titles.add(title_key)
                    if doi_key:
                        seen_dois.add(doi_key)
                    all_articles.append(article)
        
        print(f"    ✓ Found {len(sd_articles)} ScienceDirect papers")
        
        # Step 2: Search all OpenAlex for additional results
        print(f"\n📖 Step 2: Searching all academic databases...")
        all_search = self.openalex.search_all(query, max_results)
        added = 0
        for article in all_search:
            title_key = article.title.lower()[:50] if article.title else ''
            doi_key = article.doi.lower() if article.doi else ''
            
            if title_key and title_key not in seen_titles:
                if not doi_key or doi_key not in seen_dois:
                    seen_titles.add(title_key)
                    if doi_key:
                        seen_dois.add(doi_key)
                    all_articles.append(article)
                    added += 1
        
        print(f"    ✓ Added {added} additional papers")
        
        # Step 3: Enrich articles without abstracts
        print(f"\n🔍 Step 3: Enriching papers without abstracts...")
        enriched = 0
        for i, article in enumerate(all_articles):
            if not article.abstract:
                # Try CrossRef
                if article.doi:
                    abstract = self.crossref.get_abstract_by_doi(article.doi)
                    if abstract:
                        all_articles[i].abstract = abstract
                        enriched += 1
                        continue
                
                # Try Semantic Scholar
                result = self.semantic.search_by_title(article.title)
                if result and result.get('abstract'):
                    all_articles[i].abstract = result['abstract']
                    enriched += 1
                
                time.sleep(0.3)  # Rate limiting
        
        print(f"    ✓ Enriched {enriched} papers with abstracts")
        
        # Sort: ScienceDirect papers first, then by whether they have abstracts
        all_articles.sort(key=lambda x: (
            not x.is_sciencedirect,
            not bool(x.abstract),
            x.title.lower()
        ))
        
        return all_articles[:max_results]
    
    def extract_topics(self, articles: List[Article]) -> List[tuple]:
        """Extract common topics/keywords from articles"""
        topic_counter = Counter()
        
        for article in articles:
            # From keywords
            for kw in article.keywords:
                topic_counter[kw.lower()] += 1
            
            # From title
            if article.title:
                words = re.findall(r'\b[a-zA-Z]{4,}\b', article.title.lower())
                for word in words:
                    if word not in ['with', 'from', 'that', 'this', 'have', 'been', 'were', 'their']:
                        topic_counter[word] += 0.5
            
            # From abstract
            if article.abstract:
                words = re.findall(r'\b[a-zA-Z]{4,}\b', article.abstract.lower())
                for word in words:
                    if word not in ['with', 'from', 'that', 'this', 'have', 'been', 'were', 'their', 'which', 'these']:
                        topic_counter[word] += 0.2
        
        return topic_counter.most_common(20)


def display_results(articles: List[Article], topics: List[tuple]):
    """Display search results in a nice format"""
    
    print(f"\n{'='*70}")
    print(f"📊 RESULTS SUMMARY")
    print(f"{'='*70}")
    
    total = len(articles)
    with_abstracts = sum(1 for a in articles if a.abstract)
    sd_count = sum(1 for a in articles if a.is_sciencedirect)
    
    print(f"Total papers found: {total}")
    print(f"Papers with abstracts: {with_abstracts}")
    print(f"ScienceDirect papers: {sd_count}")
    
    print(f"\n🏷️ Top Related Topics:")
    for topic, score in topics[:10]:
        print(f"    • {topic}: {score:.1f}")
    
    print(f"\n{'='*70}")
    print(f"📄 ARTICLES")
    print(f"{'='*70}")
    
    for i, article in enumerate(articles, 1):
        sd_badge = "🔵 SD" if article.is_sciencedirect else "   "
        abs_badge = "✓" if article.abstract else "✗"
        
        print(f"\n{'-'*60}")
        print(f"[{i:2d}] {sd_badge} [{abs_badge}] {article.title[:70]}{'...' if len(article.title) > 70 else ''}")
        print(f"      📍 {article.source}")
        
        if article.url:
            print(f"      🔗 {article.url[:65]}{'...' if len(article.url) > 65 else ''}")
        if article.doi:
            print(f"      📑 DOI: {article.doi}")
        if article.authors:
            print(f"      👤 {article.authors[:55]}{'...' if len(article.authors) > 55 else ''}")
        if article.year:
            print(f"      📅 {article.year}")
        if article.journal:
            print(f"      📰 {article.journal}")
        
        if article.abstract:
            # Show first 250 characters of abstract
            abstract_preview = article.abstract[:250].replace('\n', ' ')
            print(f"      📝 {abstract_preview}...")
        
        if article.keywords:
            print(f"      🏷️ Keywords: {', '.join(article.keywords[:5])}")


def save_results(articles: List[Article], topics: List[tuple], base_filename: str):
    """Save results to multiple formats"""
    
    # JSON
    json_data = {
        'articles': [asdict(a) for a in articles],
        'topics': [{'topic': t, 'score': s} for t, s in topics],
        'summary': {
            'total': len(articles),
            'with_abstracts': sum(1 for a in articles if a.abstract),
            'sciencedirect_papers': sum(1 for a in articles if a.is_sciencedirect)
        }
    }
    
    with open(f"{base_filename}.json", 'w', encoding='utf-8') as f:
        json.dump(json_data, f, indent=2, ensure_ascii=False)
    
    # Markdown
    with open(f"{base_filename}.md", 'w', encoding='utf-8') as f:
        f.write(f"# ScienceDirect Literature Search Results\n\n")
        f.write(f"**Total papers:** {len(articles)}\n")
        f.write(f"**With abstracts:** {sum(1 for a in articles if a.abstract)}\n")
        f.write(f"**ScienceDirect papers:** {sum(1 for a in articles if a.is_sciencedirect)}\n\n")
        
        f.write(f"## Related Topics\n\n")
        for topic, score in topics[:15]:
            f.write(f"- {topic} ({score:.1f})\n")
        
        f.write(f"\n## Articles\n\n")
        for i, article in enumerate(articles, 1):
            sd_badge = "🔵" if article.is_sciencedirect else ""
            f.write(f"### {i}. {article.title} {sd_badge}\n\n")
            
            if article.url:
                f.write(f"**URL:** [{article.url}]({article.url})\n\n")
            if article.doi:
                f.write(f"**DOI:** {article.doi}\n\n")
            if article.authors:
                f.write(f"**Authors:** {article.authors}\n\n")
            if article.year:
                f.write(f"**Year:** {article.year}\n\n")
            if article.journal:
                f.write(f"**Journal:** {article.journal}\n\n")
            if article.abstract:
                f.write(f"**Abstract:**\n> {article.abstract}\n\n")
            if article.keywords:
                f.write(f"**Keywords:** {', '.join(article.keywords)}\n\n")
            
            f.write("---\n\n")
    
    print(f"\n✅ Results saved to:")
    print(f"    📄 {base_filename}.json")
    print(f"    📝 {base_filename}.md")


def main():
    parser = argparse.ArgumentParser(
        description='Search ScienceDirect and academic literature with abstracts',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s "renewable energy storage"
  %(prog)s "machine learning healthcare" --max 50 --output ml_health
  %(prog)s "climate change adaptation" --max 30
        """
    )
    parser.add_argument('query', help='Search query (topic or keywords)')
    parser.add_argument('--max', type=int, default=30, help='Maximum number of results (default: 30)')
    parser.add_argument('--output', default='sciencedirect_search', help='Output filename base (default: sciencedirect_search)')
    
    args = parser.parse_args()
    
    # Run search
    searcher = ScienceDirectLiteratureSearch()
    articles = searcher.search(args.query, args.max)
    topics = searcher.extract_topics(articles)
    
    # Display results
    display_results(articles, topics)
    
    # Save results
    save_results(articles, topics, args.output)


if __name__ == "__main__":
    main()
