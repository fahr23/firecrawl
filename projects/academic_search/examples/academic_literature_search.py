"""
Academic Literature Search Tool
===============================
A comprehensive tool to search academic databases for literature on any topic.

Supported Databases:
- Google Scholar
- Semantic Scholar
- ScienceDirect
- PubMed
- arXiv
- IEEE Xplore
- Scopus (via search engines)
- Web of Science (via search engines)

Usage:
    python academic_literature_search.py "your search topic"
    python academic_literature_search.py --interactive
"""

from firecrawl import Firecrawl
import base64
import os
import re
import json
import time
import argparse
from datetime import datetime
from urllib.parse import quote_plus, urljoin
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, asdict
from typing import List, Dict, Optional, Tuple


@dataclass
class Paper:
    """Represents an academic paper/article"""
    title: str
    url: str
    source: str
    authors: Optional[str] = None
    year: Optional[str] = None
    abstract: Optional[str] = None
    citations: Optional[str] = None
    relevance_score: float = 0.0

    def to_dict(self):
        return asdict(self)


class AcademicSearchEngine:
    """Base class for academic search engines"""
    
    def __init__(self, app: Firecrawl, name: str):
        self.app = app
        self.name = name
        self.results: List[Paper] = []
    
    def get_val(self, obj, key):
        """Helper to get value whether it's dict or object"""
        if isinstance(obj, dict):
            return obj.get(key)
        return getattr(obj, key, None)
    
    def build_search_url(self, query: str) -> str:
        """Build the search URL for this engine"""
        raise NotImplementedError
    
    def get_actions(self) -> List[dict]:
        """Get actions to perform on the page"""
        return [
            {"type": "wait", "milliseconds": 3000},
            {"type": "scroll", "direction": "down"},
            {"type": "wait", "milliseconds": 1000},
            {"type": "scroll", "direction": "down"},
            {"type": "wait", "milliseconds": 1000},
        ]
    
    def parse_results(self, markdown: str, source_url: str) -> List[Paper]:
        """Parse markdown content to extract papers"""
        raise NotImplementedError
    
    def search(self, query: str) -> List[Paper]:
        """Perform the search and return results"""
        url = self.build_search_url(query)
        print(f"  🔍 Searching {self.name}...")
        
        try:
            response = self.app.scrape(
                url=url,
                formats=["markdown"],
                actions=self.get_actions(),
                headers={
                    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                    "Accept-Language": "en-US,en;q=0.9"
                }
            )
            
            markdown = self.get_val(response, "markdown") or ""
            source_url = self.get_val(self.get_val(response, "metadata"), "sourceURL") or url
            
            if markdown:
                self.results = self.parse_results(markdown, source_url)
                print(f"  ✓ {self.name}: Found {len(self.results)} results")
            else:
                print(f"  ⚠ {self.name}: No content returned")
                
        except Exception as e:
            print(f"  ✗ {self.name}: Error - {str(e)[:100]}")
        
        return self.results


class GoogleScholarSearch(AcademicSearchEngine):
    """Google Scholar search engine"""
    
    def __init__(self, app: Firecrawl):
        super().__init__(app, "Google Scholar")
    
    def build_search_url(self, query: str) -> str:
        return f"https://scholar.google.com/scholar?q={quote_plus(query)}&hl=en"
    
    def parse_results(self, markdown: str, source_url: str) -> List[Paper]:
        papers = []
        
        # Extract links with their context
        pattern = r'\[([^\]]+)\]\((https?://[^\)]+)\)'
        matches = re.findall(pattern, markdown)
        
        # Skip list for navigation/UI elements
        skip_urls = ['google.com/scholar?', 'javascript:', '#', 'accounts.google', 
                     'support.google', 'scholar.google.com/scholar_settings',
                     'scholar.google.com/intl', 'scholar.google.com/scholar_alerts']
        skip_titles = ['cited by', 'related articles', 'all versions', 'sign in', 
                       'settings', 'my profile', 'create alert', 'my library',
                       'help', 'privacy', 'terms', 'about']
        
        for title, url in matches:
            # Skip navigation/UI links
            if any(skip in url.lower() for skip in skip_urls):
                continue
            if any(skip in title.lower() for skip in skip_titles):
                continue
            if len(title) < 15:  # Academic titles are usually longer
                continue
            # Skip if title is mostly numbers or special chars
            if sum(c.isalpha() for c in title) < len(title) * 0.5:
                continue
                
            # Clean title
            title = title.replace('\n', ' ').replace('  ', ' ').strip()
            
            # Try to extract year from context
            year_match = re.search(r'\b(19|20)\d{2}\b', title)
            year = year_match.group(0) if year_match else None
            
            papers.append(Paper(
                title=title,
                url=url,
                source="Google Scholar",
                year=year
            ))
        
        return papers[:20]  # Limit results


class SemanticScholarSearch(AcademicSearchEngine):
    """Semantic Scholar search engine"""
    
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
    
    def parse_results(self, markdown: str, source_url: str) -> List[Paper]:
        papers = []
        
        pattern = r'\[([^\]]+)\]\((https?://[^\)]+)\)'
        matches = re.findall(pattern, markdown)
        
        for title, url in matches:
            # Only keep semantic scholar paper links
            if 'semanticscholar.org/paper/' not in url:
                continue
            if len(title) < 10:
                continue
                
            title = title.replace('\n', ' ').strip()
            
            # Extract year if present
            year_match = re.search(r'\b(19|20)\d{2}\b', title)
            year = year_match.group(0) if year_match else None
            
            papers.append(Paper(
                title=title,
                url=url,
                source="Semantic Scholar",
                year=year
            ))
        
        return papers[:20]


class ScienceDirectSearch(AcademicSearchEngine):
    """ScienceDirect search engine"""
    
    def __init__(self, app: Firecrawl):
        super().__init__(app, "ScienceDirect")
    
    def build_search_url(self, query: str) -> str:
        # Use the show=100 parameter to get more results
        return f"https://www.sciencedirect.com/search?qs={quote_plus(query)}&show=25"
    
    def get_actions(self) -> List[dict]:
        return [
            {"type": "wait", "milliseconds": 6000},  # ScienceDirect is slow to load
            {"type": "scroll", "direction": "down"},
            {"type": "wait", "milliseconds": 2000},
            {"type": "scroll", "direction": "down"},
            {"type": "wait", "milliseconds": 2000},
            {"type": "scroll", "direction": "down"},
            {"type": "wait", "milliseconds": 1000},
        ]
    
    def parse_results(self, markdown: str, source_url: str) -> List[Paper]:
        papers = []
        
        # ScienceDirect article URLs contain /pii/ (Publisher Item Identifier)
        pattern = r'\[([^\]]+)\]\((https?://[^\)]+)\)'
        matches = re.findall(pattern, markdown)
        
        skip_titles = ['search', 'filter', 'sort', 'sign in', 'register',
                       'journals', 'books', 'about', 'help', 'open access']
        
        for title, url in matches:
            # Only keep article links (contain /pii/ or /article/)
            if not any(x in url for x in ['/pii/', '/article/pii/', 'sciencedirect.com/science/article']):
                continue
            if any(skip in title.lower() for skip in skip_titles):
                continue
            if len(title) < 15:
                continue
                
            title = title.replace('\n', ' ').replace('  ', ' ').strip()
            
            # Extract year if present
            year_match = re.search(r'\b(19|20)\d{2}\b', title)
            year = year_match.group(0) if year_match else None
            
            papers.append(Paper(
                title=title,
                url=url,
                source="ScienceDirect",
                year=year
            ))
        
        return papers[:20]


class PubMedSearch(AcademicSearchEngine):
    """PubMed search engine"""
    
    def __init__(self, app: Firecrawl):
        super().__init__(app, "PubMed")
    
    def build_search_url(self, query: str) -> str:
        return f"https://pubmed.ncbi.nlm.nih.gov/?term={quote_plus(query)}"
    
    def get_actions(self) -> List[dict]:
        return [
            {"type": "wait", "milliseconds": 4000},
            {"type": "scroll", "direction": "down"},
            {"type": "wait", "milliseconds": 2000},
            {"type": "scroll", "direction": "down"},
            {"type": "wait", "milliseconds": 1000},
        ]
    
    def parse_results(self, markdown: str, source_url: str) -> List[Paper]:
        papers = []
        
        # Skip list for PubMed UI elements
        skip_titles = ['learn about', 'filters', 'page navigation', 'display options',
                       'save', 'email', 'send to', 'create', 'sign in', 'nih.gov',
                       'results by year', 'advanced', 'clipboard', 'collections']
        
        pattern = r'\[([^\]]+)\]\((https?://[^\)]+)\)'
        matches = re.findall(pattern, markdown)
        
        for title, url in matches:
            # Only keep PubMed article links (they have numeric IDs)
            if 'pubmed.ncbi.nlm.nih.gov/' not in url:
                continue
            # Extract PMID from URL
            pmid_match = re.search(r'pubmed\.ncbi\.nlm\.nih\.gov/(\d+)', url)
            if not pmid_match:
                continue
            if any(skip in title.lower() for skip in skip_titles):
                continue
            if len(title) < 15:
                continue
                
            title = title.replace('\n', ' ').replace('  ', ' ').strip()
            
            # Extract year if in title
            year_match = re.search(r'\b(19|20)\d{2}\b', title)
            year = year_match.group(0) if year_match else None
            
            papers.append(Paper(
                title=title,
                url=url,
                source="PubMed",
                year=year
            ))
        
        return papers[:20]


class ArXivSearch(AcademicSearchEngine):
    """arXiv search engine"""
    
    def __init__(self, app: Firecrawl):
        super().__init__(app, "arXiv")
    
    def build_search_url(self, query: str) -> str:
        return f"https://arxiv.org/search/?query={quote_plus(query)}&searchtype=all"
    
    def get_actions(self) -> List[dict]:
        return [
            {"type": "wait", "milliseconds": 3000},
            {"type": "scroll", "direction": "down"},
            {"type": "wait", "milliseconds": 1500},
            {"type": "scroll", "direction": "down"},
            {"type": "wait", "milliseconds": 1000},
        ]
    
    def parse_results(self, markdown: str, source_url: str) -> List[Paper]:
        papers = []
        
        # arXiv has specific patterns - look for paper titles and their abs/pdf links
        # Pattern 1: Direct title links
        pattern = r'\[([^\]]+)\]\((https?://arxiv\.org/(?:abs|pdf)/[^\)]+)\)'
        matches = re.findall(pattern, markdown)
        
        seen_ids = set()
        
        for title, url in matches:
            # Extract arXiv ID
            arxiv_id_match = re.search(r'(\d{4}\.\d{4,5})', url)
            if not arxiv_id_match:
                continue
            
            arxiv_id = arxiv_id_match.group(1)
            if arxiv_id in seen_ids:
                continue
            seen_ids.add(arxiv_id)
            
            # Skip if title is just the arXiv ID
            if re.match(r'^arXiv:\d{4}\.\d+', title):
                # Try to find the actual title in nearby context
                continue
            
            if len(title) < 15:
                continue
                
            title = title.replace('\n', ' ').replace('  ', ' ').strip()
            
            # Normalize URL to abs format
            url = f"https://arxiv.org/abs/{arxiv_id}"
            
            papers.append(Paper(
                title=title,
                url=url,
                source="arXiv"
            ))
        
        # Also try to extract from text patterns like "Title\narXiv:XXXX.XXXXX"
        title_pattern = r'(?:^|\n)([A-Z][^:\n]{20,200})\n.*?arXiv:(\d{4}\.\d{4,5})'
        title_matches = re.findall(title_pattern, markdown, re.MULTILINE)
        
        for title, arxiv_id in title_matches:
            if arxiv_id in seen_ids:
                continue
            seen_ids.add(arxiv_id)
            
            title = title.replace('\n', ' ').replace('  ', ' ').strip()
            url = f"https://arxiv.org/abs/{arxiv_id}"
            
            papers.append(Paper(
                title=title,
                url=url,
                source="arXiv"
            ))
        
        return papers[:20]


class IEEESearch(AcademicSearchEngine):
    """IEEE Xplore search engine"""
    
    def __init__(self, app: Firecrawl):
        super().__init__(app, "IEEE Xplore")
    
    def build_search_url(self, query: str) -> str:
        return f"https://ieeexplore.ieee.org/search/searchresult.jsp?queryText={quote_plus(query)}"
    
    def get_actions(self) -> List[dict]:
        return [
            {"type": "wait", "milliseconds": 5000},
            {"type": "scroll", "direction": "down"},
            {"type": "wait", "milliseconds": 2000},
            {"type": "scroll", "direction": "down"},
            {"type": "wait", "milliseconds": 1000},
        ]
    
    def parse_results(self, markdown: str, source_url: str) -> List[Paper]:
        papers = []
        
        # Skip common UI elements
        skip_titles = ['papers', 'conferences', 'journals', 'standards', 
                       'courses', 'books', 'early access', 'filter', 
                       'sort by', 'refine', 'ieee', 'xplore']
        
        pattern = r'\[([^\]]+)\]\((https?://[^\)]+)\)'
        matches = re.findall(pattern, markdown)
        
        for title, url in matches:
            # Only keep IEEE document links
            if 'ieeexplore.ieee.org/document/' not in url:
                continue
            if any(skip == title.lower().strip() for skip in skip_titles):
                continue
            if len(title) < 15:
                continue
            # Skip if mostly numbers
            if sum(c.isalpha() for c in title) < len(title) * 0.4:
                continue
                
            title = title.replace('\n', ' ').replace('  ', ' ').strip()
            
            # Extract year if present
            year_match = re.search(r'\b(19|20)\d{2}\b', title)
            year = year_match.group(0) if year_match else None
            
            papers.append(Paper(
                title=title,
                url=url,
                source="IEEE Xplore",
                year=year
            ))
        
        return papers[:20]


class ScopusViaGoogleSearch(AcademicSearchEngine):
    """Search Scopus via Google (since direct access requires login)"""
    
    def __init__(self, app: Firecrawl):
        super().__init__(app, "Scopus")
    
    def build_search_url(self, query: str) -> str:
        return f"https://www.google.com/search?q=site:scopus.com+{quote_plus(query)}"
    
    def parse_results(self, markdown: str, source_url: str) -> List[Paper]:
        papers = []
        
        pattern = r'\[([^\]]+)\]\((https?://[^\)]+)\)'
        matches = re.findall(pattern, markdown)
        
        for title, url in matches:
            if 'scopus.com' not in url:
                continue
            if len(title) < 10:
                continue
                
            title = title.replace('\n', ' ').strip()
            
            papers.append(Paper(
                title=title,
                url=url,
                source="Scopus"
            ))
        
        return papers[:20]


class WebOfScienceViaGoogleSearch(AcademicSearchEngine):
    """Search Web of Science via Google (since direct access requires login)"""
    
    def __init__(self, app: Firecrawl):
        super().__init__(app, "Web of Science")
    
    def build_search_url(self, query: str) -> str:
        return f"https://www.google.com/search?q=site:webofscience.com+{quote_plus(query)}"
    
    def parse_results(self, markdown: str, source_url: str) -> List[Paper]:
        papers = []
        
        pattern = r'\[([^\]]+)\]\((https?://[^\)]+)\)'
        matches = re.findall(pattern, markdown)
        
        for title, url in matches:
            if 'webofscience.com' not in url:
                continue
            if len(title) < 10:
                continue
                
            title = title.replace('\n', ' ').strip()
            
            papers.append(Paper(
                title=title,
                url=url,
                source="Web of Science"
            ))
        
        return papers[:20]


class AcademicLiteratureSearch:
    """Main class for comprehensive academic literature search"""
    
    def __init__(self, api_url: str = "http://localhost:3002", api_key: str = None):
        self.api_url = api_url
        self.api_key = api_key or os.getenv("FIRECRAWL_API_KEY", "fc-USER_API_KEY")
        self.app = Firecrawl(api_url=api_url, api_key=self.api_key)
        self.all_results: List[Paper] = []
        
        # Initialize search engines
        self.engines = [
            GoogleScholarSearch(self.app),
            SemanticScholarSearch(self.app),
            ScienceDirectSearch(self.app),
            PubMedSearch(self.app),
            ArXivSearch(self.app),
            IEEESearch(self.app),
            # ScopusViaGoogleSearch(self.app),
            # WebOfScienceViaGoogleSearch(self.app),
        ]
    
    def refine_query(self, topic: str) -> str:
        """
        Refine the search query for better academic results.
        Adds common academic search modifiers.
        """
        # Remove common words that don't add value
        stopwords = ['the', 'a', 'an', 'and', 'or', 'but', 'in', 'on', 'at', 'to', 'for']
        words = topic.lower().split()
        refined_words = [w for w in words if w not in stopwords]
        
        return ' '.join(refined_words) if refined_words else topic
    
    def analyze_topic(self, topic: str) -> Dict[str, any]:
        """
        Analyze the topic to understand what kind of search to perform.
        Returns metadata about the topic.
        """
        topic_lower = topic.lower()
        
        analysis = {
            "original_topic": topic,
            "refined_query": self.refine_query(topic),
            "is_medical": any(w in topic_lower for w in ['health', 'medical', 'disease', 'treatment', 'clinical', 'patient', 'drug', 'therapy']),
            "is_cs": any(w in topic_lower for w in ['algorithm', 'machine learning', 'deep learning', 'neural', 'ai', 'artificial intelligence', 'computer', 'software', 'programming']),
            "is_physics": any(w in topic_lower for w in ['quantum', 'physics', 'particle', 'energy', 'relativity', 'mechanics']),
            "is_engineering": any(w in topic_lower for w in ['engineering', 'design', 'system', 'control', 'optimization', 'manufacturing']),
            "is_biology": any(w in topic_lower for w in ['biology', 'gene', 'protein', 'cell', 'organism', 'evolution', 'ecology']),
            "suggested_databases": []
        }
        
        # Suggest databases based on topic
        if analysis["is_medical"]:
            analysis["suggested_databases"].extend(["PubMed", "Google Scholar"])
        if analysis["is_cs"]:
            analysis["suggested_databases"].extend(["arXiv", "Semantic Scholar", "IEEE Xplore"])
        if analysis["is_physics"]:
            analysis["suggested_databases"].extend(["arXiv", "Google Scholar"])
        if analysis["is_engineering"]:
            analysis["suggested_databases"].extend(["IEEE Xplore", "ScienceDirect"])
        if analysis["is_biology"]:
            analysis["suggested_databases"].extend(["PubMed", "ScienceDirect"])
        
        if not analysis["suggested_databases"]:
            analysis["suggested_databases"] = ["Google Scholar", "Semantic Scholar", "ScienceDirect"]
        
        return analysis
    
    def search(self, topic: str, databases: List[str] = None, max_results_per_db: int = 20) -> List[Paper]:
        """
        Perform search across all or selected databases.
        
        Args:
            topic: The search topic/keywords
            databases: List of database names to search (None = all)
            max_results_per_db: Maximum results per database
        
        Returns:
            List of Paper objects
        """
        print("\n" + "="*70)
        print("🎓 ACADEMIC LITERATURE SEARCH")
        print("="*70)
        
        # Analyze topic
        analysis = self.analyze_topic(topic)
        print(f"\n📚 Topic: {topic}")
        print(f"🔧 Refined Query: {analysis['refined_query']}")
        print(f"💡 Suggested Databases: {', '.join(analysis['suggested_databases'])}")
        
        # Select engines to use
        if databases:
            engines_to_use = [e for e in self.engines if e.name in databases]
        else:
            engines_to_use = self.engines
        
        print(f"\n🔍 Searching {len(engines_to_use)} databases...")
        print("-"*70)
        
        self.all_results = []
        
        # Search each database sequentially (to avoid overwhelming the API)
        for engine in engines_to_use:
            try:
                results = engine.search(analysis['refined_query'])
                self.all_results.extend(results)
            except Exception as e:
                print(f"  ✗ {engine.name}: Error - {str(e)[:50]}")
            
            # Small delay between searches
            time.sleep(1)
        
        # Deduplicate results by URL
        seen_urls = set()
        unique_results = []
        for paper in self.all_results:
            if paper.url not in seen_urls:
                seen_urls.add(paper.url)
                unique_results.append(paper)
        
        self.all_results = unique_results
        
        print("-"*70)
        print(f"✅ Total unique results: {len(self.all_results)}")
        
        return self.all_results
    
    def save_results(self, filename: str = None, format: str = "all"):
        """
        Save results to file(s).
        
        Args:
            filename: Base filename (without extension)
            format: 'json', 'txt', 'csv', 'markdown', or 'all'
        """
        if not self.all_results:
            print("No results to save.")
            return
        
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        base_filename = filename or f"literature_search_{timestamp}"
        
        formats_to_save = ['json', 'txt', 'csv', 'markdown'] if format == 'all' else [format]
        
        for fmt in formats_to_save:
            if fmt == 'json':
                self._save_json(f"{base_filename}.json")
            elif fmt == 'txt':
                self._save_txt(f"{base_filename}.txt")
            elif fmt == 'csv':
                self._save_csv(f"{base_filename}.csv")
            elif fmt == 'markdown':
                self._save_markdown(f"{base_filename}.md")
    
    def _save_json(self, filename: str):
        """Save results as JSON"""
        data = {
            "search_timestamp": datetime.now().isoformat(),
            "total_results": len(self.all_results),
            "results": [p.to_dict() for p in self.all_results]
        }
        with open(filename, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        print(f"  📄 Saved JSON: {filename}")
    
    def _save_txt(self, filename: str):
        """Save results as plain text"""
        with open(filename, 'w', encoding='utf-8') as f:
            f.write(f"Academic Literature Search Results\n")
            f.write(f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
            f.write(f"Total Results: {len(self.all_results)}\n")
            f.write("="*70 + "\n\n")
            
            # Group by source
            by_source = {}
            for paper in self.all_results:
                if paper.source not in by_source:
                    by_source[paper.source] = []
                by_source[paper.source].append(paper)
            
            for source, papers in by_source.items():
                f.write(f"\n--- {source} ({len(papers)} results) ---\n\n")
                for i, paper in enumerate(papers, 1):
                    f.write(f"{i}. {paper.title}\n")
                    f.write(f"   URL: {paper.url}\n")
                    if paper.year:
                        f.write(f"   Year: {paper.year}\n")
                    f.write("\n")
        
        print(f"  📄 Saved TXT: {filename}")
    
    def _save_csv(self, filename: str):
        """Save results as CSV"""
        import csv
        with open(filename, 'w', newline='', encoding='utf-8') as f:
            writer = csv.writer(f)
            writer.writerow(['Title', 'URL', 'Source', 'Year', 'Authors'])
            for paper in self.all_results:
                writer.writerow([paper.title, paper.url, paper.source, paper.year or '', paper.authors or ''])
        print(f"  📄 Saved CSV: {filename}")
    
    def _save_markdown(self, filename: str):
        """Save results as Markdown"""
        with open(filename, 'w', encoding='utf-8') as f:
            f.write(f"# Academic Literature Search Results\n\n")
            f.write(f"**Generated:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n")
            f.write(f"**Total Results:** {len(self.all_results)}\n\n")
            f.write("---\n\n")
            
            # Group by source
            by_source = {}
            for paper in self.all_results:
                if paper.source not in by_source:
                    by_source[paper.source] = []
                by_source[paper.source].append(paper)
            
            for source, papers in by_source.items():
                f.write(f"## {source} ({len(papers)} results)\n\n")
                for i, paper in enumerate(papers, 1):
                    f.write(f"{i}. [{paper.title}]({paper.url})")
                    if paper.year:
                        f.write(f" ({paper.year})")
                    f.write("\n")
                f.write("\n")
        
        print(f"  📄 Saved Markdown: {filename}")
    
    def print_summary(self):
        """Print a summary of results"""
        if not self.all_results:
            print("\nNo results found.")
            return
        
        print("\n" + "="*70)
        print("📊 RESULTS SUMMARY")
        print("="*70)
        
        # Group by source
        by_source = {}
        for paper in self.all_results:
            if paper.source not in by_source:
                by_source[paper.source] = []
            by_source[paper.source].append(paper)
        
        for source, papers in sorted(by_source.items()):
            print(f"\n📚 {source}: {len(papers)} papers")
            for i, paper in enumerate(papers[:5], 1):  # Show first 5
                title_short = paper.title[:60] + "..." if len(paper.title) > 60 else paper.title
                print(f"   {i}. {title_short}")
            if len(papers) > 5:
                print(f"   ... and {len(papers) - 5} more")
        
        print("\n" + "="*70)


def interactive_search():
    """Interactive search mode"""
    print("\n" + "="*70)
    print("🎓 INTERACTIVE ACADEMIC LITERATURE SEARCH")
    print("="*70)
    
    searcher = AcademicLiteratureSearch()
    
    print("\nAvailable databases:")
    for i, engine in enumerate(searcher.engines, 1):
        print(f"  {i}. {engine.name}")
    
    print("\n" + "-"*70)
    topic = input("\n📝 Enter your search topic/keywords: ").strip()
    
    if not topic:
        print("No topic entered. Exiting.")
        return
    
    # Ask which databases to search
    print("\n🔧 Database selection:")
    print("  1. Search ALL databases (recommended)")
    print("  2. Let me suggest based on topic")
    print("  3. Select specific databases")
    
    choice = input("\nYour choice (1/2/3): ").strip()
    
    databases = None
    if choice == "2":
        analysis = searcher.analyze_topic(topic)
        databases = analysis["suggested_databases"]
        print(f"Suggested databases: {', '.join(databases)}")
    elif choice == "3":
        print("\nEnter database numbers (comma-separated), e.g., 1,2,4:")
        db_choices = input("Your selection: ").strip()
        try:
            indices = [int(x.strip()) - 1 for x in db_choices.split(",")]
            databases = [searcher.engines[i].name for i in indices if 0 <= i < len(searcher.engines)]
        except:
            print("Invalid selection. Searching all databases.")
    
    # Perform search
    results = searcher.search(topic, databases=databases)
    
    # Print summary
    searcher.print_summary()
    
    # Save results
    print("\n💾 Save options:")
    print("  1. Save all formats (JSON, TXT, CSV, Markdown)")
    print("  2. Save as JSON only")
    print("  3. Save as Markdown only")
    print("  4. Don't save")
    
    save_choice = input("\nYour choice (1/2/3/4): ").strip()
    
    if save_choice == "1":
        searcher.save_results(format="all")
    elif save_choice == "2":
        searcher.save_results(format="json")
    elif save_choice == "3":
        searcher.save_results(format="markdown")
    
    print("\n✅ Search complete!")


def main():
    parser = argparse.ArgumentParser(
        description="Academic Literature Search Tool",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python academic_literature_search.py "machine learning in healthcare"
  python academic_literature_search.py "renewable energy" --databases "Google Scholar,arXiv"
  python academic_literature_search.py --interactive
        """
    )
    
    parser.add_argument("topic", nargs="?", help="Search topic or keywords")
    parser.add_argument("--interactive", "-i", action="store_true", help="Interactive mode")
    parser.add_argument("--databases", "-d", help="Comma-separated list of databases to search")
    parser.add_argument("--output", "-o", help="Output filename (without extension)")
    parser.add_argument("--format", "-f", choices=['json', 'txt', 'csv', 'markdown', 'all'], 
                        default='all', help="Output format")
    parser.add_argument("--api-url", default="http://localhost:3002", help="Firecrawl API URL")
    
    args = parser.parse_args()
    
    if args.interactive or not args.topic:
        interactive_search()
        return
    
    # Direct search mode
    searcher = AcademicLiteratureSearch(api_url=args.api_url)
    
    databases = None
    if args.databases:
        databases = [d.strip() for d in args.databases.split(",")]
    
    results = searcher.search(args.topic, databases=databases)
    searcher.print_summary()
    searcher.save_results(filename=args.output, format=args.format)
    
    print("\n✅ Search complete!")


if __name__ == "__main__":
    main()
