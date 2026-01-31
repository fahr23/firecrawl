"""
Advanced Academic Literature Search Tool v2
============================================
Searches multiple academic databases, extracts abstracts via OpenAlex API,
and identifies related topics.

Features:
- Multi-source search: Google Scholar, Semantic Scholar, PubMed, arXiv, IEEE Xplore
- Uses OpenAlex API for metadata and abstracts (free, open API)
- Topic extraction and keyword analysis
- Multiple output formats (JSON, CSV, Markdown)

Usage:
    python academic_literature_search_v2.py "your research topic"
    python academic_literature_search_v2.py "renewable energy" --fetch-abstracts
"""

from firecrawl import Firecrawl
import os
import re
import json
import time
import argparse
import requests
from datetime import datetime
from urllib.parse import quote_plus
from dataclasses import dataclass, asdict, field
from typing import List, Dict, Optional
from collections import Counter


@dataclass
class Paper:
    """Represents an academic paper"""
    title: str
    url: str
    source: str
    authors: Optional[str] = None
    year: Optional[str] = None
    abstract: Optional[str] = None
    keywords: List[str] = field(default_factory=list)
    journal: Optional[str] = None
    doi: Optional[str] = None
    citations: Optional[int] = None
    open_access: bool = False
    
    def to_dict(self):
        return asdict(self)


class OpenAlexAPI:
    """OpenAlex API client for fetching paper metadata"""
    
    BASE_URL = "https://api.openalex.org"
    
    @classmethod
    def search_works(cls, query: str, per_page: int = 25) -> List[Paper]:
        """Search for works/papers via OpenAlex API"""
        papers = []
        
        try:
            url = f"{cls.BASE_URL}/works"
            params = {
                "search": query,
                "per_page": per_page,
                "sort": "relevance_score:desc",
                "mailto": "academic_search@example.com"  # Polite pool
            }
            
            response = requests.get(url, params=params, timeout=30)
            
            if response.status_code == 200:
                data = response.json()
                
                for work in data.get("results", []):
                    # Extract authors
                    authors = []
                    for authorship in work.get("authorships", [])[:5]:
                        author = authorship.get("author", {})
                        if author.get("display_name"):
                            authors.append(author["display_name"])
                    
                    # Extract abstract
                    abstract_inverted = work.get("abstract_inverted_index", {})
                    abstract = cls._reconstruct_abstract(abstract_inverted) if abstract_inverted else None
                    
                    # Extract keywords/concepts
                    keywords = []
                    for concept in work.get("concepts", [])[:10]:
                        if concept.get("display_name"):
                            keywords.append(concept["display_name"])
                    
                    # Get journal/venue
                    primary_location = work.get("primary_location", {})
                    source = primary_location.get("source", {})
                    journal = source.get("display_name") if source else None
                    
                    papers.append(Paper(
                        title=work.get("title", "Unknown"),
                        url=work.get("id", "").replace("https://openalex.org/", "https://openalex.org/works/"),
                        source="OpenAlex",
                        authors=", ".join(authors) if authors else None,
                        year=str(work.get("publication_year")) if work.get("publication_year") else None,
                        abstract=abstract,
                        keywords=keywords,
                        journal=journal,
                        doi=work.get("doi"),
                        citations=work.get("cited_by_count"),
                        open_access=work.get("open_access", {}).get("is_oa", False)
                    ))
        
        except Exception as e:
            print(f"  ⚠ OpenAlex API error: {str(e)[:60]}")
        
        return papers
    
    @classmethod
    def _reconstruct_abstract(cls, inverted_index: Dict) -> str:
        """Reconstruct abstract from inverted index format"""
        if not inverted_index:
            return None
        
        # Find max position
        max_pos = 0
        for positions in inverted_index.values():
            if positions:
                max_pos = max(max_pos, max(positions))
        
        # Reconstruct
        words = [""] * (max_pos + 1)
        for word, positions in inverted_index.items():
            for pos in positions:
                words[pos] = word
        
        return " ".join(words)
    
    @classmethod
    def get_abstract_by_doi(cls, doi: str) -> Optional[str]:
        """Fetch abstract for a paper by DOI"""
        try:
            url = f"{cls.BASE_URL}/works/https://doi.org/{doi}"
            response = requests.get(url, params={"mailto": "academic_search@example.com"}, timeout=15)
            
            if response.status_code == 200:
                work = response.json()
                abstract_inverted = work.get("abstract_inverted_index", {})
                return cls._reconstruct_abstract(abstract_inverted)
        except:
            pass
        return None


class AcademicSearchEngine:
    """Base class for web-based academic search"""
    
    def __init__(self, app: Firecrawl, name: str):
        self.app = app
        self.name = name
        self.results: List[Paper] = []
    
    def get_val(self, obj, key):
        if isinstance(obj, dict):
            return obj.get(key)
        return getattr(obj, key, None)
    
    def build_search_url(self, query: str) -> str:
        raise NotImplementedError
    
    def get_actions(self) -> List[dict]:
        return [
            {"type": "wait", "milliseconds": 3000},
            {"type": "scroll", "direction": "down"},
            {"type": "wait", "milliseconds": 1500},
            {"type": "scroll", "direction": "down"},
            {"type": "wait", "milliseconds": 1000},
        ]
    
    def parse_results(self, markdown: str) -> List[Paper]:
        raise NotImplementedError
    
    def search(self, query: str) -> List[Paper]:
        url = self.build_search_url(query)
        print(f"  🔍 Searching {self.name}...")
        
        try:
            response = self.app.scrape(
                url=url,
                formats=["markdown"],
                actions=self.get_actions(),
                headers={
                    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
                    "Accept-Language": "en-US,en;q=0.9"
                },
                timeout=60000
            )
            
            markdown = self.get_val(response, "markdown") or ""
            
            if markdown:
                self.results = self.parse_results(markdown)
                print(f"  ✓ {self.name}: Found {len(self.results)} results")
            else:
                print(f"  ⚠ {self.name}: No content returned")
                
        except Exception as e:
            print(f"  ✗ {self.name}: Error - {str(e)[:60]}")
        
        return self.results


class GoogleScholarSearch(AcademicSearchEngine):
    """Google Scholar search"""
    
    def __init__(self, app: Firecrawl):
        super().__init__(app, "Google Scholar")
    
    def build_search_url(self, query: str) -> str:
        return f"https://scholar.google.com/scholar?q={quote_plus(query)}&hl=en&as_sdt=0,5"
    
    def parse_results(self, markdown: str) -> List[Paper]:
        papers = []
        pattern = r'\[([^\]]+)\]\((https?://[^\)]+)\)'
        matches = re.findall(pattern, markdown)
        
        skip_urls = ['google.com/scholar?', 'javascript:', '#', 'accounts.google', 
                     'support.google', 'scholar.google.com/scholar_settings']
        skip_titles = ['cited by', 'related articles', 'all versions', 'sign in', 
                       'settings', 'my profile', 'create alert', 'my library', 'pdf', 'html']
        
        seen = set()
        for title, url in matches:
            if any(s in url.lower() for s in skip_urls):
                continue
            if any(s in title.lower() for s in skip_titles):
                continue
            if url in seen or len(title) < 20:
                continue
            if sum(c.isalpha() for c in title) < len(title) * 0.5:
                continue
            
            seen.add(url)
            title = title.replace('\n', ' ').replace('  ', ' ').strip()
            
            year = None
            year_match = re.search(r'\b(19|20)\d{2}\b', title)
            if year_match:
                year = year_match.group(0)
            
            papers.append(Paper(title=title, url=url, source="Google Scholar", year=year))
        
        return papers[:20]


class SemanticScholarSearch(AcademicSearchEngine):
    """Semantic Scholar search"""
    
    def __init__(self, app: Firecrawl):
        super().__init__(app, "Semantic Scholar")
    
    def build_search_url(self, query: str) -> str:
        return f"https://www.semanticscholar.org/search?q={quote_plus(query)}&sort=relevance"
    
    def get_actions(self) -> List[dict]:
        return [
            {"type": "wait", "milliseconds": 4000},
            {"type": "scroll", "direction": "down"},
            {"type": "wait", "milliseconds": 2000},
            {"type": "scroll", "direction": "down"},
            {"type": "wait", "milliseconds": 1000},
        ]
    
    def parse_results(self, markdown: str) -> List[Paper]:
        papers = []
        pattern = r'\[([^\]]+)\]\((https?://www\.semanticscholar\.org/paper/[^\)]+)\)'
        matches = re.findall(pattern, markdown)
        
        seen = set()
        for title, url in matches:
            if url in seen or len(title) < 20:
                continue
            seen.add(url)
            
            title = title.replace('\n', ' ').replace('  ', ' ').strip()
            title = re.sub(r'\*+', '', title)
            title = re.sub(r'_+', ' ', title)
            
            papers.append(Paper(title=title, url=url, source="Semantic Scholar"))
        
        return papers[:20]


class PubMedSearch(AcademicSearchEngine):
    """PubMed search"""
    
    def __init__(self, app: Firecrawl):
        super().__init__(app, "PubMed")
    
    def build_search_url(self, query: str) -> str:
        return f"https://pubmed.ncbi.nlm.nih.gov/?term={quote_plus(query)}&sort=relevance"
    
    def parse_results(self, markdown: str) -> List[Paper]:
        papers = []
        pattern = r'\[([^\]]+)\]\((https?://pubmed\.ncbi\.nlm\.nih\.gov/\d+[^\)]*)\)'
        matches = re.findall(pattern, markdown)
        
        skip = ['learn about', 'filters', 'page navigation', 'display', 'save', 'email']
        seen = set()
        
        for title, url in matches:
            pmid = re.search(r'/(\d+)', url)
            if not pmid:
                continue
            pid = pmid.group(1)
            
            if pid in seen or any(s in title.lower() for s in skip):
                continue
            if len(title) < 20:
                continue
            
            seen.add(pid)
            title = title.replace('\n', ' ').replace('  ', ' ').strip()
            url = f"https://pubmed.ncbi.nlm.nih.gov/{pid}/"
            
            papers.append(Paper(title=title, url=url, source="PubMed"))
        
        return papers[:20]


class ArXivSearch(AcademicSearchEngine):
    """arXiv search"""
    
    def __init__(self, app: Firecrawl):
        super().__init__(app, "arXiv")
    
    def build_search_url(self, query: str) -> str:
        return f"https://arxiv.org/search/?query={quote_plus(query)}&searchtype=all"
    
    def parse_results(self, markdown: str) -> List[Paper]:
        papers = []
        
        # Look for paper links
        pattern = r'\[([^\]]+)\]\((https?://arxiv\.org/abs/[\d\.v]+[^\)]*)\)'
        matches = re.findall(pattern, markdown)
        
        seen = set()
        for title, url in matches:
            aid = re.search(r'(\d{4}\.\d{4,5})', url)
            if not aid:
                continue
            arxiv_id = aid.group(1)
            
            if arxiv_id in seen or len(title) < 15:
                continue
            seen.add(arxiv_id)
            
            title = title.replace('\n', ' ').replace('  ', ' ').strip()
            url = f"https://arxiv.org/abs/{arxiv_id}"
            
            papers.append(Paper(title=title, url=url, source="arXiv"))
        
        return papers[:20]


class IEEESearch(AcademicSearchEngine):
    """IEEE Xplore search"""
    
    def __init__(self, app: Firecrawl):
        super().__init__(app, "IEEE Xplore")
    
    def build_search_url(self, query: str) -> str:
        return f"https://ieeexplore.ieee.org/search/searchresult.jsp?queryText={quote_plus(query)}"
    
    def get_actions(self) -> List[dict]:
        return [
            {"type": "wait", "milliseconds": 5000},
            {"type": "scroll", "direction": "down"},
            {"type": "wait", "milliseconds": 2000},
        ]
    
    def parse_results(self, markdown: str) -> List[Paper]:
        papers = []
        pattern = r'\[([^\]]+)\]\((https?://ieeexplore\.ieee\.org/document/\d+[^\)]*)\)'
        matches = re.findall(pattern, markdown)
        
        skip = ['papers', 'conferences', 'journals', 'standards', 'courses', 'ieee', 'filter']
        seen = set()
        
        for title, url in matches:
            if url in seen or any(s == title.lower().strip() for s in skip):
                continue
            if len(title) < 20:
                continue
            
            seen.add(url)
            title = title.replace('\n', ' ').replace('  ', ' ').strip()
            
            papers.append(Paper(title=title, url=url, source="IEEE Xplore"))
        
        return papers[:20]


class TopicExtractor:
    """Extract related topics from papers"""
    
    STOPWORDS = {
        'the', 'a', 'an', 'and', 'or', 'but', 'in', 'on', 'at', 'to', 'for', 'of', 'with',
        'by', 'from', 'as', 'is', 'was', 'are', 'were', 'been', 'be', 'have', 'has', 'had',
        'that', 'which', 'who', 'this', 'these', 'those', 'it', 'its', 'their', 'there',
        'when', 'where', 'why', 'how', 'what', 'all', 'each', 'both', 'few', 'more', 'most',
        'other', 'some', 'such', 'no', 'not', 'only', 'same', 'so', 'than', 'too', 'very',
        'can', 'will', 'just', 'should', 'now', 'also', 'into', 'over', 'after', 'before',
        'paper', 'study', 'research', 'work', 'article', 'results', 'show', 'shows', 'based',
        'using', 'used', 'use', 'proposed', 'present', 'method', 'approach', 'model',
        'data', 'analysis', 'experimental', 'performance', 'new', 'novel', 'different'
    }
    
    @classmethod
    def extract_topics(cls, papers: List[Paper], top_n: int = 25) -> List[tuple]:
        """Extract topics from papers"""
        counter = Counter()
        
        for paper in papers:
            # Weight keywords highly
            for kw in paper.keywords:
                counter[kw.lower()] += 3
            
            # Process abstract
            if paper.abstract:
                words = re.findall(r'\b[a-z]{4,}\b', paper.abstract.lower())
                for w in words:
                    if w not in cls.STOPWORDS:
                        counter[w] += 1
                
                # Bigrams from abstract
                for i in range(len(words) - 1):
                    if words[i] not in cls.STOPWORDS and words[i+1] not in cls.STOPWORDS:
                        counter[f"{words[i]} {words[i+1]}"] += 1.5
            
            # Process title
            title_words = re.findall(r'\b[a-z]{4,}\b', paper.title.lower())
            for w in title_words:
                if w not in cls.STOPWORDS:
                    counter[w] += 2
        
        return counter.most_common(top_n)


class AcademicLiteratureSearchV2:
    """Main search orchestrator"""
    
    def __init__(self, api_url: str = "http://localhost:3002", api_key: str = None):
        self.api_url = api_url
        self.api_key = api_key or os.getenv("FIRECRAWL_API_KEY", "fc-USER_API_KEY")
        self.app = Firecrawl(api_url=api_url, api_key=self.api_key)
        self.papers: List[Paper] = []
        self.topics: List[tuple] = []
        
        self.engines = [
            GoogleScholarSearch(self.app),
            SemanticScholarSearch(self.app),
            PubMedSearch(self.app),
            ArXivSearch(self.app),
            IEEESearch(self.app),
        ]
    
    def search(self, topic: str, use_openalex: bool = True) -> List[Paper]:
        """Search for papers on a topic"""
        print("\n" + "="*70)
        print("🎓 ACADEMIC LITERATURE SEARCH v2")
        print("="*70)
        print(f"\n📚 Topic: {topic}")
        print(f"🔍 Searching {len(self.engines)} databases + OpenAlex API...")
        print("-"*70)
        
        self.papers = []
        
        # Search via web scraping
        for engine in self.engines:
            try:
                results = engine.search(topic)
                self.papers.extend(results)
            except Exception as e:
                print(f"  ✗ {engine.name}: {str(e)[:50]}")
            time.sleep(1)
        
        # Search via OpenAlex API (includes abstracts!)
        if use_openalex:
            print(f"  🔍 Searching OpenAlex API...")
            try:
                openalex_results = OpenAlexAPI.search_works(topic, per_page=30)
                print(f"  ✓ OpenAlex: Found {len(openalex_results)} results (with abstracts)")
                self.papers.extend(openalex_results)
            except Exception as e:
                print(f"  ✗ OpenAlex: {str(e)[:50]}")
        
        # Deduplicate by title similarity
        seen_titles = set()
        unique = []
        for p in self.papers:
            # Normalize title for comparison
            norm_title = re.sub(r'[^a-z0-9]', '', p.title.lower())[:50]
            if norm_title not in seen_titles:
                seen_titles.add(norm_title)
                unique.append(p)
        
        self.papers = unique
        
        print("-"*70)
        print(f"✅ Total unique papers: {len(self.papers)}")
        abstracts_count = sum(1 for p in self.papers if p.abstract)
        print(f"📝 Papers with abstracts: {abstracts_count}")
        
        return self.papers
    
    def extract_topics(self) -> List[tuple]:
        """Extract related topics from all papers"""
        print("\n🔬 Extracting related topics...")
        self.topics = TopicExtractor.extract_topics(self.papers)
        print(f"✅ Found {len(self.topics)} related topics")
        return self.topics
    
    def print_summary(self):
        """Print results summary"""
        print("\n" + "="*70)
        print("📊 SEARCH RESULTS SUMMARY")
        print("="*70)
        
        # Group by source
        by_source = {}
        for p in self.papers:
            by_source.setdefault(p.source, []).append(p)
        
        for source, papers in sorted(by_source.items()):
            print(f"\n📚 {source}: {len(papers)} papers")
            for i, p in enumerate(papers[:5], 1):
                title = p.title[:50] + "..." if len(p.title) > 50 else p.title
                year = f" ({p.year})" if p.year else ""
                cite = f" [{p.citations} cit.]" if p.citations else ""
                print(f"   {i}. {title}{year}{cite}")
            if len(papers) > 5:
                print(f"   ... and {len(papers)-5} more")
        
        # Print topics
        if self.topics:
            print("\n" + "="*70)
            print("🔬 RELATED TOPICS & KEYWORDS")
            print("="*70)
            
            print("\nTop keywords (by relevance):")
            for i, (topic, score) in enumerate(self.topics[:15], 1):
                print(f"   {i:2}. {topic} ({score:.1f})")
        
        # Papers with abstracts
        with_abstracts = [p for p in self.papers if p.abstract]
        if with_abstracts:
            print("\n" + "="*70)
            print("📝 SAMPLE PAPERS WITH ABSTRACTS")
            print("="*70)
            
            for i, p in enumerate(with_abstracts[:3], 1):
                print(f"\n{i}. {p.title}")
                print(f"   Source: {p.source} | Year: {p.year or 'N/A'}")
                if p.authors:
                    print(f"   Authors: {p.authors[:80]}...")
                if p.keywords:
                    print(f"   Keywords: {', '.join(p.keywords[:5])}")
                print(f"   Abstract: {p.abstract[:300]}...")
    
    def save_results(self, filename: str = None):
        """Save results to files"""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        base = filename or f"literature_search_{timestamp}"
        
        # JSON
        data = {
            "timestamp": datetime.now().isoformat(),
            "total_papers": len(self.papers),
            "papers_with_abstracts": sum(1 for p in self.papers if p.abstract),
            "related_topics": [{"topic": t, "score": s} for t, s in self.topics],
            "papers": [p.to_dict() for p in self.papers]
        }
        with open(f"{base}.json", 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        print(f"  📄 {base}.json")
        
        # Markdown
        with open(f"{base}.md", 'w', encoding='utf-8') as f:
            f.write(f"# Academic Literature Search Results\n\n")
            f.write(f"**Generated:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n")
            f.write(f"**Total Papers:** {len(self.papers)} | **With Abstracts:** {sum(1 for p in self.papers if p.abstract)}\n\n")
            
            # Topics
            if self.topics:
                f.write("## 🔬 Related Topics\n\n")
                for topic, score in self.topics[:20]:
                    f.write(f"- **{topic}** (score: {score:.1f})\n")
                f.write("\n---\n\n")
            
            # Papers by source
            f.write("## 📚 Papers\n\n")
            by_source = {}
            for p in self.papers:
                by_source.setdefault(p.source, []).append(p)
            
            for source, papers in sorted(by_source.items()):
                f.write(f"### {source} ({len(papers)})\n\n")
                for i, p in enumerate(papers, 1):
                    year = f" ({p.year})" if p.year else ""
                    f.write(f"{i}. [{p.title}]({p.url}){year}\n")
                    if p.authors:
                        f.write(f"   - Authors: {p.authors[:100]}\n")
                    if p.keywords:
                        f.write(f"   - Keywords: {', '.join(p.keywords[:5])}\n")
                    if p.abstract:
                        f.write(f"   > {p.abstract[:200]}...\n")
                    f.write("\n")
        print(f"  📄 {base}.md")
        
        # CSV
        import csv
        with open(f"{base}.csv", 'w', newline='', encoding='utf-8') as f:
            writer = csv.writer(f)
            writer.writerow(['Title', 'Authors', 'Year', 'Source', 'URL', 'DOI', 'Citations', 'Keywords', 'Abstract'])
            for p in self.papers:
                writer.writerow([
                    p.title,
                    p.authors or '',
                    p.year or '',
                    p.source,
                    p.url,
                    p.doi or '',
                    p.citations or '',
                    '; '.join(p.keywords[:5]),
                    (p.abstract or '')[:500]
                ])
        print(f"  📄 {base}.csv")


def main():
    parser = argparse.ArgumentParser(description="Academic Literature Search v2")
    parser.add_argument("topic", nargs="?", help="Search topic")
    parser.add_argument("--output", "-o", help="Output filename")
    parser.add_argument("--no-openalex", action="store_true", help="Skip OpenAlex API")
    
    args = parser.parse_args()
    
    if not args.topic:
        args.topic = input("📝 Enter search topic: ").strip()
        if not args.topic:
            print("No topic. Exiting.")
            return
    
    searcher = AcademicLiteratureSearchV2()
    searcher.search(args.topic, use_openalex=not args.no_openalex)
    searcher.extract_topics()
    searcher.print_summary()
    
    print("\n💾 Saving results...")
    searcher.save_results(args.output)
    print("\n✅ Done!")


if __name__ == "__main__":
    main()
