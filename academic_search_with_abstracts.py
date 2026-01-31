"""
Advanced Academic Literature Search Tool
=========================================
Searches multiple academic databases, extracts abstracts, and identifies related topics.

Features:
- Searches: Google Scholar, Semantic Scholar, ScienceDirect, PubMed, arXiv, IEEE Xplore
- Fetches abstracts from individual paper pages
- Extracts related topics/keywords from abstracts
- Generates comprehensive reports

Usage:
    python academic_search_with_abstracts.py "your research topic"
    python academic_search_with_abstracts.py "renewable energy" --fetch-abstracts --max-papers 10
"""

from firecrawl import Firecrawl
import base64
import os
import re
import json
import time
import argparse
from datetime import datetime
from urllib.parse import quote_plus, urlparse
from dataclasses import dataclass, asdict, field
from typing import List, Dict, Optional, Set
from collections import Counter
import concurrent.futures


@dataclass
class Paper:
    """Represents an academic paper with abstract"""
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
    
    def to_dict(self):
        return asdict(self)


class AcademicSearchEngine:
    """Base class for academic search engines"""
    
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
            {"type": "wait", "milliseconds": 4000},
            {"type": "scroll", "direction": "down"},
            {"type": "wait", "milliseconds": 2000},
            {"type": "scroll", "direction": "down"},
            {"type": "wait", "milliseconds": 1500},
        ]
    
    def parse_results(self, markdown: str, source_url: str) -> List[Paper]:
        raise NotImplementedError
    
    def fetch_abstract(self, paper: Paper) -> Paper:
        """Fetch abstract from the paper's page"""
        return paper  # Override in subclass
    
    def search(self, query: str) -> List[Paper]:
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
                },
                timeout=60000
            )
            
            markdown = self.get_val(response, "markdown") or ""
            
            if markdown:
                self.results = self.parse_results(markdown, url)
                print(f"  ✓ {self.name}: Found {len(self.results)} results")
            else:
                print(f"  ⚠ {self.name}: No content returned")
                
        except Exception as e:
            print(f"  ✗ {self.name}: Error - {str(e)[:80]}")
        
        return self.results


class ScienceDirectViaGoogleSearch(AcademicSearchEngine):
    """ScienceDirect search via Google (bypass direct blocking)"""
    
    def __init__(self, app: Firecrawl):
        super().__init__(app, "ScienceDirect")
    
    def build_search_url(self, query: str) -> str:
        # Search ScienceDirect via Google to bypass bot protection
        return f"https://www.google.com/search?q=site:sciencedirect.com+{quote_plus(query)}&num=20"
    
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
        
        # Look for ScienceDirect article links from Google results
        pattern = r'\[([^\]]+)\]\((https?://www\.sciencedirect\.com/science/article[^\)]+)\)'
        matches = re.findall(pattern, markdown)
        
        seen_urls = set()
        skip_titles = ['search', 'filter', 'sort', 'sign in', 'register', 'export', 
                       'journals', 'books', 'about', 'help', 'open access', 'volume', 
                       'issue', 'elsevier', 'sciencedirect']
        
        for title, url in matches:
            # Normalize URL
            url = url.split('?')[0]
            if url in seen_urls:
                continue
            seen_urls.add(url)
            
            if any(skip == title.lower().strip() for skip in skip_titles):
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
        
        return papers[:25]
    
    def fetch_abstract(self, paper: Paper) -> Paper:
        """Fetch abstract from ScienceDirect article page"""
        try:
            response = self.app.scrape(
                url=paper.url,
                formats=["markdown"],
                actions=[
                    {"type": "wait", "milliseconds": 4000},
                    {"type": "scroll", "direction": "down"},
                    {"type": "wait", "milliseconds": 1000},
                ],
                timeout=45000
            )
            
            markdown = self.get_val(response, "markdown") or ""
            
            # Extract abstract - ScienceDirect has "Abstract" section
            abstract_patterns = [
                r'(?:^|\n)#+\s*Abstract\s*\n+([\s\S]+?)(?=\n#+|\n\*\*[A-Z]|\nKeywords|\nIntroduction|$)',
                r'(?:Abstract|ABSTRACT)[:\s]*([\s\S]{100,2000}?)(?=\n\n|\nKeywords|\n#+|Introduction)',
                r'Highlights[\s\S]*?Abstract\s*([\s\S]+?)(?=Keywords|Introduction|\n##)',
            ]
            
            for pattern in abstract_patterns:
                match = re.search(pattern, markdown, re.IGNORECASE)
                if match:
                    abstract = match.group(1).strip()
                    # Clean up
                    abstract = re.sub(r'\[.*?\]\(.*?\)', '', abstract)  # Remove links
                    abstract = re.sub(r'\s+', ' ', abstract)
                    if len(abstract) > 50:
                        paper.abstract = abstract[:2000]
                        break
            
            # Extract keywords
            kw_match = re.search(r'Keywords?[:\s]*([\s\S]+?)(?=\n\n|\n##|Introduction)', markdown, re.IGNORECASE)
            if kw_match:
                kw_text = kw_match.group(1)
                keywords = re.split(r'[,;•·\n]', kw_text)
                paper.keywords = [k.strip() for k in keywords if k.strip() and len(k.strip()) > 2][:10]
            
            # Extract authors
            author_match = re.search(r'(?:Authors?|By)[:\s]*([\s\S]+?)(?=\n\n|\n##|Abstract)', markdown, re.IGNORECASE)
            if author_match:
                paper.authors = author_match.group(1).strip()[:200]
            
        except Exception as e:
            pass  # Silent fail for individual abstracts
        
        return paper


class GoogleScholarSearch(AcademicSearchEngine):
    """Google Scholar search"""
    
    def __init__(self, app: Firecrawl):
        super().__init__(app, "Google Scholar")
    
    def build_search_url(self, query: str) -> str:
        return f"https://scholar.google.com/scholar?q={quote_plus(query)}&hl=en&as_sdt=0,5"
    
    def parse_results(self, markdown: str, source_url: str) -> List[Paper]:
        papers = []
        pattern = r'\[([^\]]+)\]\((https?://[^\)]+)\)'
        matches = re.findall(pattern, markdown)
        
        skip_urls = ['google.com/scholar?', 'javascript:', '#', 'accounts.google', 
                     'support.google', 'scholar.google.com/scholar_settings']
        skip_titles = ['cited by', 'related articles', 'all versions', 'sign in', 
                       'settings', 'my profile', 'create alert', 'my library', 'pdf', 'html']
        
        seen_urls = set()
        
        for title, url in matches:
            if any(skip in url.lower() for skip in skip_urls):
                continue
            if any(skip in title.lower() for skip in skip_titles):
                continue
            if url in seen_urls:
                continue
            if len(title) < 20 or sum(c.isalpha() for c in title) < len(title) * 0.5:
                continue
            
            seen_urls.add(url)
            title = title.replace('\n', ' ').replace('  ', ' ').strip()
            
            year_match = re.search(r'\b(19|20)\d{2}\b', title)
            year = year_match.group(0) if year_match else None
            
            papers.append(Paper(title=title, url=url, source="Google Scholar", year=year))
        
        return papers[:20]


class SemanticScholarSearch(AcademicSearchEngine):
    """Semantic Scholar search with abstract extraction"""
    
    def __init__(self, app: Firecrawl):
        super().__init__(app, "Semantic Scholar")
    
    def build_search_url(self, query: str) -> str:
        return f"https://www.semanticscholar.org/search?q={quote_plus(query)}&sort=relevance"
    
    def get_actions(self) -> List[dict]:
        return [
            {"type": "wait", "milliseconds": 5000},
            {"type": "scroll", "direction": "down"},
            {"type": "wait", "milliseconds": 2000},
            {"type": "scroll", "direction": "down"},
            {"type": "wait", "milliseconds": 1500},
        ]
    
    def parse_results(self, markdown: str, source_url: str) -> List[Paper]:
        papers = []
        pattern = r'\[([^\]]+)\]\((https?://www\.semanticscholar\.org/paper/[^\)]+)\)'
        matches = re.findall(pattern, markdown)
        
        seen_urls = set()
        
        for title, url in matches:
            if url in seen_urls or len(title) < 20:
                continue
            seen_urls.add(url)
            
            title = title.replace('\n', ' ').replace('  ', ' ').strip()
            # Remove markdown formatting
            title = re.sub(r'\*+', '', title)
            title = re.sub(r'_+', ' ', title)
            
            papers.append(Paper(title=title, url=url, source="Semantic Scholar"))
        
        return papers[:20]
    
    def fetch_abstract(self, paper: Paper) -> Paper:
        """Fetch abstract from Semantic Scholar paper page"""
        try:
            response = self.app.scrape(
                url=paper.url,
                formats=["markdown"],
                actions=[
                    {"type": "wait", "milliseconds": 4000},
                    {"type": "click", "selector": "button[data-test-id='text-truncator-toggle']"},
                    {"type": "wait", "milliseconds": 1000},
                ],
                timeout=45000
            )
            
            markdown = self.get_val(response, "markdown") or ""
            
            # Abstract extraction
            abstract_match = re.search(
                r'(?:Abstract|TLDR)[:\s]*([\s\S]{50,2000}?)(?=\n\n|\n##|Keywords|Figures|Citations)',
                markdown, re.IGNORECASE
            )
            if abstract_match:
                paper.abstract = abstract_match.group(1).strip()
            
            # Extract year
            year_match = re.search(r'Published\s+(\d{4})', markdown)
            if year_match:
                paper.year = year_match.group(1)
            
            # Extract citations count
            cite_match = re.search(r'(\d+)\s+Citations?', markdown, re.IGNORECASE)
            if cite_match:
                paper.citations = int(cite_match.group(1))
            
        except Exception:
            pass
        
        return paper


class PubMedSearch(AcademicSearchEngine):
    """PubMed search with abstract extraction"""
    
    def __init__(self, app: Firecrawl):
        super().__init__(app, "PubMed")
    
    def build_search_url(self, query: str) -> str:
        return f"https://pubmed.ncbi.nlm.nih.gov/?term={quote_plus(query)}&sort=relevance"
    
    def get_actions(self) -> List[dict]:
        return [
            {"type": "wait", "milliseconds": 4000},
            {"type": "scroll", "direction": "down"},
            {"type": "wait", "milliseconds": 2000},
            {"type": "scroll", "direction": "down"},
            {"type": "wait", "milliseconds": 1500},
        ]
    
    def parse_results(self, markdown: str, source_url: str) -> List[Paper]:
        papers = []
        pattern = r'\[([^\]]+)\]\((https?://pubmed\.ncbi\.nlm\.nih\.gov/\d+[^\)]*)\)'
        matches = re.findall(pattern, markdown)
        
        skip_titles = ['learn about', 'filters', 'page navigation', 'display options',
                       'save', 'email', 'send to', 'create', 'sign in']
        seen_pmids = set()
        
        for title, url in matches:
            pmid_match = re.search(r'/(\d+)', url)
            if not pmid_match:
                continue
            pmid = pmid_match.group(1)
            
            if pmid in seen_pmids:
                continue
            seen_pmids.add(pmid)
            
            if any(skip in title.lower() for skip in skip_titles):
                continue
            if len(title) < 20:
                continue
            
            title = title.replace('\n', ' ').replace('  ', ' ').strip()
            url = f"https://pubmed.ncbi.nlm.nih.gov/{pmid}/"
            
            papers.append(Paper(title=title, url=url, source="PubMed"))
        
        return papers[:20]
    
    def fetch_abstract(self, paper: Paper) -> Paper:
        """Fetch abstract from PubMed article page"""
        try:
            response = self.app.scrape(
                url=paper.url,
                formats=["markdown"],
                actions=[{"type": "wait", "milliseconds": 3000}],
                timeout=45000
            )
            
            markdown = self.get_val(response, "markdown") or ""
            
            # Extract abstract
            abstract_match = re.search(
                r'(?:^|\n)(?:#+\s*)?Abstract\s*\n+([\s\S]+?)(?=\n#+|\nKeywords|\nMeSH|PMID|\nCopyright)',
                markdown, re.IGNORECASE
            )
            if abstract_match:
                paper.abstract = abstract_match.group(1).strip()[:2000]
            
            # Extract keywords/MeSH terms
            mesh_match = re.search(r'MeSH terms[:\s]*([\s\S]+?)(?=\n\n|\nSubstances|\nPMID)', markdown)
            if mesh_match:
                terms = re.findall(r'([A-Za-z][A-Za-z\s]+)', mesh_match.group(1))
                paper.keywords = [t.strip() for t in terms if len(t.strip()) > 3][:10]
            
            # Extract year
            year_match = re.search(r'(\d{4})\s*(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)', markdown)
            if year_match:
                paper.year = year_match.group(1)
            
        except Exception:
            pass
        
        return paper


class ArXivSearch(AcademicSearchEngine):
    """arXiv search with abstract extraction"""
    
    def __init__(self, app: Firecrawl):
        super().__init__(app, "arXiv")
    
    def build_search_url(self, query: str) -> str:
        return f"https://arxiv.org/search/?query={quote_plus(query)}&searchtype=all&source=header"
    
    def parse_results(self, markdown: str, source_url: str) -> List[Paper]:
        papers = []
        
        # Look for arXiv paper links
        pattern = r'\[([^\]]+)\]\((https?://arxiv\.org/abs/[\d\.]+[^\)]*)\)'
        matches = re.findall(pattern, markdown)
        
        seen_ids = set()
        
        for title, url in matches:
            arxiv_id = re.search(r'(\d{4}\.\d{4,5})', url)
            if not arxiv_id:
                continue
            
            aid = arxiv_id.group(1)
            if aid in seen_ids:
                continue
            seen_ids.add(aid)
            
            if len(title) < 15:
                continue
            
            title = title.replace('\n', ' ').replace('  ', ' ').strip()
            url = f"https://arxiv.org/abs/{aid}"
            
            papers.append(Paper(title=title, url=url, source="arXiv"))
        
        # Also try to extract from search result patterns
        # arXiv shows titles followed by arXiv:XXXX.XXXXX
        alt_pattern = r'([A-Z][^\n]{20,200}?)\n[^\n]*arXiv:(\d{4}\.\d{4,5})'
        alt_matches = re.findall(alt_pattern, markdown)
        
        for title, aid in alt_matches:
            if aid in seen_ids:
                continue
            seen_ids.add(aid)
            
            title = title.strip()
            url = f"https://arxiv.org/abs/{aid}"
            papers.append(Paper(title=title, url=url, source="arXiv"))
        
        return papers[:20]
    
    def fetch_abstract(self, paper: Paper) -> Paper:
        """Fetch abstract from arXiv paper page"""
        try:
            response = self.app.scrape(
                url=paper.url,
                formats=["markdown"],
                actions=[{"type": "wait", "milliseconds": 3000}],
                timeout=45000
            )
            
            markdown = self.get_val(response, "markdown") or ""
            
            # arXiv abstracts are usually in a specific format
            abstract_match = re.search(
                r'(?:Abstract|^>)\s*[:\n]*([\s\S]{100,3000}?)(?=\nComments|\nSubjects|\nCite as|\nSubmission)',
                markdown, re.IGNORECASE | re.MULTILINE
            )
            if abstract_match:
                paper.abstract = abstract_match.group(1).strip()
            
            # Extract subjects as keywords
            subj_match = re.search(r'Subjects?[:\s]*([^\n]+)', markdown)
            if subj_match:
                subjects = re.split(r'[;,]', subj_match.group(1))
                paper.keywords = [s.strip() for s in subjects if s.strip()][:10]
            
            # Extract authors
            auth_match = re.search(r'Authors?[:\s]*([^\n]+)', markdown)
            if auth_match:
                paper.authors = auth_match.group(1).strip()[:300]
            
        except Exception:
            pass
        
        return paper


class IEEESearch(AcademicSearchEngine):
    """IEEE Xplore search"""
    
    def __init__(self, app: Firecrawl):
        super().__init__(app, "IEEE Xplore")
    
    def build_search_url(self, query: str) -> str:
        return f"https://ieeexplore.ieee.org/search/searchresult.jsp?queryText={quote_plus(query)}&sortType=desc_p_Publication_Year"
    
    def get_actions(self) -> List[dict]:
        return [
            {"type": "wait", "milliseconds": 6000},
            {"type": "scroll", "direction": "down"},
            {"type": "wait", "milliseconds": 2000},
            {"type": "scroll", "direction": "down"},
            {"type": "wait", "milliseconds": 1500},
        ]
    
    def parse_results(self, markdown: str, source_url: str) -> List[Paper]:
        papers = []
        pattern = r'\[([^\]]+)\]\((https?://ieeexplore\.ieee\.org/document/\d+[^\)]*)\)'
        matches = re.findall(pattern, markdown)
        
        skip_titles = ['papers', 'conferences', 'journals', 'standards', 
                       'courses', 'books', 'early access', 'filter', 'ieee']
        seen_urls = set()
        
        for title, url in matches:
            if url in seen_urls:
                continue
            seen_urls.add(url)
            
            if any(skip == title.lower().strip() for skip in skip_titles):
                continue
            if len(title) < 20:
                continue
            
            title = title.replace('\n', ' ').replace('  ', ' ').strip()
            
            papers.append(Paper(title=title, url=url, source="IEEE Xplore"))
        
        return papers[:20]


class TopicExtractor:
    """Extract related topics from abstracts"""
    
    # Common academic stopwords
    STOPWORDS = {
        'the', 'a', 'an', 'and', 'or', 'but', 'in', 'on', 'at', 'to', 'for', 'of', 'with',
        'by', 'from', 'as', 'is', 'was', 'are', 'were', 'been', 'be', 'have', 'has', 'had',
        'do', 'does', 'did', 'will', 'would', 'could', 'should', 'may', 'might', 'must',
        'that', 'which', 'who', 'whom', 'this', 'these', 'those', 'it', 'its', 'their',
        'there', 'here', 'when', 'where', 'why', 'how', 'what', 'all', 'each', 'every',
        'both', 'few', 'more', 'most', 'other', 'some', 'such', 'no', 'nor', 'not', 'only',
        'own', 'same', 'so', 'than', 'too', 'very', 'can', 'just', 'should', 'now',
        'also', 'into', 'over', 'after', 'before', 'between', 'under', 'again', 'further',
        'then', 'once', 'during', 'while', 'about', 'against', 'through', 'however',
        'although', 'though', 'because', 'since', 'therefore', 'thus', 'hence',
        'paper', 'study', 'research', 'work', 'article', 'results', 'show', 'shows',
        'shown', 'based', 'using', 'used', 'use', 'proposed', 'present', 'presents',
        'presented', 'method', 'methods', 'approach', 'approaches', 'model', 'models',
        'data', 'analysis', 'evaluated', 'experimental', 'experiments', 'performance',
        'high', 'low', 'new', 'novel', 'different', 'various', 'several', 'many', 'first',
        'second', 'one', 'two', 'three'
    }
    
    @classmethod
    def extract_topics(cls, papers: List[Paper], top_n: int = 20) -> List[tuple]:
        """Extract common topics/keywords from paper abstracts and keywords"""
        
        all_text = []
        keyword_counter = Counter()
        
        for paper in papers:
            # Add keywords directly
            for kw in paper.keywords:
                keyword_counter[kw.lower()] += 2  # Weight keywords higher
            
            # Process abstract
            if paper.abstract:
                all_text.append(paper.abstract)
            
            # Also add title
            all_text.append(paper.title)
        
        # Extract n-grams from text
        combined_text = ' '.join(all_text).lower()
        
        # Extract bigrams and trigrams
        words = re.findall(r'\b[a-z]{3,}\b', combined_text)
        
        # Unigrams (filtered)
        for word in words:
            if word not in cls.STOPWORDS and len(word) > 3:
                keyword_counter[word] += 1
        
        # Bigrams
        for i in range(len(words) - 1):
            if words[i] not in cls.STOPWORDS and words[i+1] not in cls.STOPWORDS:
                bigram = f"{words[i]} {words[i+1]}"
                keyword_counter[bigram] += 1.5
        
        # Trigrams
        for i in range(len(words) - 2):
            if (words[i] not in cls.STOPWORDS and 
                words[i+2] not in cls.STOPWORDS):
                trigram = f"{words[i]} {words[i+1]} {words[i+2]}"
                keyword_counter[trigram] += 1.2
        
        # Get top topics
        return keyword_counter.most_common(top_n)
    
    @classmethod
    def categorize_topics(cls, topics: List[tuple]) -> Dict[str, List[str]]:
        """Categorize topics into groups"""
        categories = {
            "Technical Terms": [],
            "Methodologies": [],
            "Applications": [],
            "General Concepts": []
        }
        
        method_keywords = ['algorithm', 'method', 'approach', 'technique', 'framework', 
                          'model', 'network', 'learning', 'optimization', 'analysis']
        app_keywords = ['application', 'system', 'device', 'implementation', 'design',
                       'development', 'production', 'industry', 'practical']
        
        for topic, score in topics:
            if any(m in topic for m in method_keywords):
                categories["Methodologies"].append(topic)
            elif any(a in topic for a in app_keywords):
                categories["Applications"].append(topic)
            elif len(topic.split()) >= 2:
                categories["Technical Terms"].append(topic)
            else:
                categories["General Concepts"].append(topic)
        
        return categories


class AdvancedAcademicSearch:
    """Main class for comprehensive academic literature search"""
    
    def __init__(self, api_url: str = "http://localhost:3002", api_key: str = None):
        self.api_url = api_url
        self.api_key = api_key or os.getenv("FIRECRAWL_API_KEY", "fc-USER_API_KEY")
        self.app = Firecrawl(api_url=api_url, api_key=self.api_key)
        self.papers: List[Paper] = []
        self.topics: List[tuple] = []
        
        self.engines = [
            GoogleScholarSearch(self.app),
            SemanticScholarSearch(self.app),
            ScienceDirectViaGoogleSearch(self.app),
            PubMedSearch(self.app),
            ArXivSearch(self.app),
            IEEESearch(self.app),
        ]
    
    def search(self, topic: str, databases: List[str] = None) -> List[Paper]:
        """Search all databases for papers"""
        print("\n" + "="*70)
        print("🎓 ADVANCED ACADEMIC LITERATURE SEARCH")
        print("="*70)
        print(f"\n📚 Search Topic: {topic}")
        
        engines_to_use = self.engines
        if databases:
            engines_to_use = [e for e in self.engines if e.name in databases]
        
        print(f"🔍 Searching {len(engines_to_use)} databases...")
        print("-"*70)
        
        self.papers = []
        
        for engine in engines_to_use:
            try:
                results = engine.search(topic)
                self.papers.extend(results)
            except Exception as e:
                print(f"  ✗ {engine.name}: {str(e)[:60]}")
            time.sleep(1)
        
        # Deduplicate
        seen = set()
        unique = []
        for p in self.papers:
            key = p.url.lower().rstrip('/')
            if key not in seen:
                seen.add(key)
                unique.append(p)
        self.papers = unique
        
        print("-"*70)
        print(f"✅ Total unique papers: {len(self.papers)}")
        
        return self.papers
    
    def fetch_abstracts(self, max_papers: int = 10):
        """Fetch abstracts for top papers"""
        print(f"\n📖 Fetching abstracts for top {max_papers} papers...")
        print("-"*70)
        
        papers_to_fetch = self.papers[:max_papers]
        
        for i, paper in enumerate(papers_to_fetch, 1):
            print(f"  [{i}/{len(papers_to_fetch)}] {paper.title[:50]}...")
            
            # Find the appropriate engine to fetch abstract
            for engine in self.engines:
                if engine.name == paper.source:
                    paper = engine.fetch_abstract(paper)
                    if paper.abstract:
                        print(f"       ✓ Abstract found ({len(paper.abstract)} chars)")
                    break
            
            time.sleep(0.5)
        
        print("-"*70)
        abstracts_found = sum(1 for p in papers_to_fetch if p.abstract)
        print(f"✅ Abstracts retrieved: {abstracts_found}/{len(papers_to_fetch)}")
    
    def extract_related_topics(self) -> List[tuple]:
        """Extract related topics from papers"""
        print("\n🔬 Extracting related topics...")
        
        self.topics = TopicExtractor.extract_topics(self.papers)
        
        print(f"✅ Found {len(self.topics)} related topics/keywords")
        return self.topics
    
    def print_summary(self):
        """Print search results summary"""
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
                title = p.title[:55] + "..." if len(p.title) > 55 else p.title
                year_str = f" ({p.year})" if p.year else ""
                print(f"   {i}. {title}{year_str}")
            if len(papers) > 5:
                print(f"   ... and {len(papers)-5} more")
        
        # Print related topics
        if self.topics:
            print("\n" + "="*70)
            print("🔬 RELATED TOPICS & KEYWORDS")
            print("="*70)
            
            categories = TopicExtractor.categorize_topics(self.topics[:30])
            
            for category, terms in categories.items():
                if terms:
                    print(f"\n📌 {category}:")
                    for term in terms[:10]:
                        print(f"   • {term}")
        
        # Print papers with abstracts
        papers_with_abstracts = [p for p in self.papers if p.abstract]
        if papers_with_abstracts:
            print("\n" + "="*70)
            print("📝 PAPERS WITH ABSTRACTS")
            print("="*70)
            
            for i, p in enumerate(papers_with_abstracts[:5], 1):
                print(f"\n{i}. {p.title}")
                print(f"   Source: {p.source} | Year: {p.year or 'N/A'}")
                print(f"   URL: {p.url}")
                if p.keywords:
                    print(f"   Keywords: {', '.join(p.keywords[:5])}")
                print(f"   Abstract: {p.abstract[:300]}...")
    
    def save_results(self, filename: str = None):
        """Save results to files"""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        base = filename or f"academic_search_{timestamp}"
        
        # Save JSON
        data = {
            "search_timestamp": datetime.now().isoformat(),
            "total_papers": len(self.papers),
            "related_topics": [{"topic": t, "score": s} for t, s in self.topics],
            "papers": [p.to_dict() for p in self.papers]
        }
        with open(f"{base}.json", 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        print(f"  📄 Saved: {base}.json")
        
        # Save Markdown
        with open(f"{base}.md", 'w', encoding='utf-8') as f:
            f.write(f"# Academic Literature Search Results\n\n")
            f.write(f"**Generated:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n")
            f.write(f"**Total Papers:** {len(self.papers)}\n\n")
            
            # Related topics
            if self.topics:
                f.write("## 🔬 Related Topics & Keywords\n\n")
                for topic, score in self.topics[:20]:
                    f.write(f"- **{topic}** (relevance: {score:.1f})\n")
                f.write("\n")
            
            # Papers by source
            f.write("---\n\n## 📚 Papers by Source\n\n")
            
            by_source = {}
            for p in self.papers:
                by_source.setdefault(p.source, []).append(p)
            
            for source, papers in sorted(by_source.items()):
                f.write(f"### {source} ({len(papers)} papers)\n\n")
                for i, p in enumerate(papers, 1):
                    year_str = f" ({p.year})" if p.year else ""
                    f.write(f"{i}. [{p.title}]({p.url}){year_str}\n")
                    if p.abstract:
                        f.write(f"   > {p.abstract[:200]}...\n")
                    if p.keywords:
                        f.write(f"   - Keywords: {', '.join(p.keywords[:5])}\n")
                    f.write("\n")
        
        print(f"  📄 Saved: {base}.md")
        
        # Save CSV
        import csv
        with open(f"{base}.csv", 'w', newline='', encoding='utf-8') as f:
            writer = csv.writer(f)
            writer.writerow(['Title', 'URL', 'Source', 'Year', 'Keywords', 'Abstract'])
            for p in self.papers:
                writer.writerow([
                    p.title, p.url, p.source, p.year or '',
                    '; '.join(p.keywords[:5]), (p.abstract or '')[:500]
                ])
        print(f"  📄 Saved: {base}.csv")


def main():
    parser = argparse.ArgumentParser(description="Advanced Academic Literature Search")
    parser.add_argument("topic", nargs="?", help="Search topic or keywords")
    parser.add_argument("--fetch-abstracts", "-a", action="store_true", 
                        help="Fetch abstracts from paper pages")
    parser.add_argument("--max-papers", "-m", type=int, default=10,
                        help="Max papers to fetch abstracts for")
    parser.add_argument("--output", "-o", help="Output filename (without extension)")
    parser.add_argument("--databases", "-d", help="Comma-separated list of databases")
    
    args = parser.parse_args()
    
    if not args.topic:
        args.topic = input("📝 Enter your search topic: ").strip()
        if not args.topic:
            print("No topic provided. Exiting.")
            return
    
    searcher = AdvancedAcademicSearch()
    
    databases = None
    if args.databases:
        databases = [d.strip() for d in args.databases.split(",")]
    
    # Search
    searcher.search(args.topic, databases=databases)
    
    # Fetch abstracts if requested
    if args.fetch_abstracts:
        searcher.fetch_abstracts(max_papers=args.max_papers)
    
    # Extract topics
    searcher.extract_related_topics()
    
    # Print summary
    searcher.print_summary()
    
    # Save results
    print("\n💾 Saving results...")
    searcher.save_results(filename=args.output)
    
    print("\n✅ Search complete!")


if __name__ == "__main__":
    main()
