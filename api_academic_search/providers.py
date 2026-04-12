"""
Search provider implementations.

This module contains concrete implementations of search providers
for various academic databases.
"""

import re
import time
import requests
from typing import List, Optional, Dict, Any

from .base import BaseSearcher, BaseAbstractEnricher
from .models import Article, SearchResult
from .config import Config

try:
    from firecrawl import Firecrawl
except ImportError:
    # Use a dummy class if firecrawl is not installed to prevent ImportErrors
    class Firecrawl:
        def __init__(self, **kwargs): pass
        def scrape_url(self, **kwargs): return {}


class ScienceDirectSearcher(BaseSearcher):
    """
    Search provider for Elsevier ScienceDirect Article Metadata API.
    
    Provides access to 16M+ full-text articles from ScienceDirect.
    Uses the same API key as Scopus but searches Elsevier content specifically.
    Often provides better abstracts and more detailed metadata than Scopus.
    """
    
    SEARCH_URL = "https://api.elsevier.com/content/search/sciencedirect"
    
    def __init__(self, config: Config):
        super().__init__(config)
        self.api_key = config.api.elsevier_api_key if config and config.api else None
        api_key_str = str(self.api_key) if self.api_key else ''
        self.headers = {
            'X-ELS-APIKey': api_key_str,
            'Accept': 'application/json'
        }
    
    @property
    def source_name(self) -> str:
        return "ScienceDirect"
    
    @property
    def is_available(self) -> bool:
        return bool(self.api_key)
    
    def search(self, query: str, max_results: int = 25, year_min: Optional[int] = None, year_max: Optional[int] = None) -> SearchResult:
        """Search ScienceDirect Article Metadata database."""
        if not self.is_available:
            self.logger.warning("ScienceDirect API key not configured")
            return SearchResult(
                query=query,
                articles=[],
                total_found=0,
                sources=[self.source_name]
            )
        
        articles = []
        total_found = 0
        
        try:
            # Build query with year filter using pub-date field
            # ScienceDirect uses different syntax: pub-date AFT YYYYMMDD
            # Update: Don't wrap query in quotes to allow boolean operators/keywords
            search_query = f'title-abs-key({query})'
            
            if year_min:
                year_min_date = f"{year_min}0101"
                search_query += f" AND pub-date AFT {year_min_date}"
            
            if year_max:
                year_max_date = f"{year_max}1231"
                search_query += f" AND pub-date BEF {year_max_date}"
            
            params = {
                'query': search_query,
                'count': min(max_results, 100),  # ScienceDirect allows up to 100
                'sort': 'relevance'
            }
            
            response = requests.get(
                self.SEARCH_URL,
                headers=self.headers,
                params=params,
                timeout=15
            )
            
            if response.status_code == 200:
                data = response.json()
                results = data.get('search-results', {}).get('entry', [])
                total_found = int(data.get('search-results', {}).get('opensearch:totalResults', 0))
                
                self.logger.info(f"ScienceDirect: {total_found} total results, fetched {len(results)}")
                
                for entry in results:
                    article = self._parse_entry(entry)
                    if article:
                        articles.append(article)
                        
            elif response.status_code == 401:
                self.logger.error("ScienceDirect: Authentication failed")
            else:
                self.logger.warning(f"ScienceDirect: Status {response.status_code}")
                
        except Exception as e:
            self.logger.error(f"ScienceDirect search error: {e}")
        
        return SearchResult(
            query=query,
            articles=articles,
            total_found=total_found,
            sources=[self.source_name]
        )
    
    def _parse_entry(self, entry: Dict[str, Any]) -> Optional[Article]:
        """Parse ScienceDirect API entry into Article."""
        try:
            title = entry.get('dc:title', 'Untitled')
            doi = entry.get('prism:doi', '')
            
            # Get abstract (ScienceDirect often includes it)
            abstract = entry.get('dc:description', '')
            
            # Build URL - prefer DOI link
            if doi:
                url = f"https://doi.org/{doi}"
            else:
                # Use ScienceDirect link from entry
                links = entry.get('link', [])
                sd_link = next(
                    (l.get('@href') for l in links if 'sciencedirect' in l.get('@href', '')), 
                    ''
                )
                url = sd_link or f"https://www.sciencedirect.com/science/article/pii/{entry.get('pii', '')}"
            
            # Parse date
            pub_date = entry.get('prism:coverDate', '')
            year = pub_date[:4] if pub_date and len(pub_date) >= 4 else ''
            
            # Get open access status
            is_open_access = entry.get('openaccess', '0') == '1' or entry.get('openaccessFlag', False)
            
            return Article(
                title=title,
                url=url,
                doi=doi if doi else None,
                abstract=abstract,  # ScienceDirect often includes abstracts
                authors=entry.get('dc:creator', ''),
                journal=entry.get('prism:publicationName', ''),
                year=year,
                source=self.source_name,
                is_open_access=is_open_access,
                raw_data=entry
            )
        except Exception as e:
            self.logger.debug(f"Parse error: {e}")
            return None


class ScopusSearcher(BaseSearcher):
    """
    Search provider for Elsevier Scopus API.
    
    Requires an Elsevier API key. Provides access to over 80 million
    records including most ScienceDirect content.
    """
    
    SEARCH_URL = "https://api.elsevier.com/content/search/scopus"
    ABSTRACT_URL = "https://api.elsevier.com/content/abstract"
    
    def __init__(self, config: Config):
        super().__init__(config)
        self.api_key = config.api.elsevier_api_key if config and config.api else None
        api_key_str = str(self.api_key) if self.api_key else ''
        self.headers = {
            'X-ELS-APIKey': api_key_str,
            'Accept': 'application/json'
        }
    
    @property
    def source_name(self) -> str:
        return "Scopus API"
    
    @property
    def is_available(self) -> bool:
        return bool(self.api_key)
    
    def search(self, query: str, max_results: int = 25, year_min: Optional[int] = None, year_max: Optional[int] = None) -> SearchResult:
        """Search Scopus database with pagination."""
        if not self.is_available:
            self.logger.warning("Scopus API key not configured")
            return SearchResult(
                query=query,
                articles=[],
                total_found=0,
                sources=[self.source_name]
            )
        
        articles = []
        total_found = 0
        
        # Build query with year filter
        search_query = query
        if year_min or year_max:
            year_filter = f" AND PUBYEAR > {year_min-1}" if year_min else ""
            year_filter += f" AND PUBYEAR < {year_max+1}" if year_max else ""
            search_query = query + year_filter
        
        start = 0
        batch_size = 25  # Scopus limit per request
        
        while len(articles) < max_results:
            try:
                # Calculate how many more we need
                remaining = max_results - len(articles)
                count = min(remaining, batch_size)
                
                params = {
                    'query': search_query,
                    'start': start,
                    'count': count,
                    'sort': 'relevance'
                }
                
                response = requests.get(
                    self.SEARCH_URL,
                    headers=self.headers,
                    params=params,
                    timeout=15
                )
                
                if response.status_code == 200:
                    data = response.json()
                    results = data.get('search-results', {}).get('entry', [])
                    total_str = data.get('search-results', {}).get('opensearch:totalResults', '0')
                    total_found = int(total_str)
                    
                    if not results:
                        break
                        
                    for entry in results:
                        article = self._parse_entry(entry)
                        if article:
                            articles.append(article)
                    
                    # Log first batch
                    if start == 0:
                        self.logger.info(f"Scopus: {total_found} total results")
                    
                    # Prepare next batch
                    start += len(results)
                    
                    # Check if we've exhausted results
                    if start >= total_found:
                        break
                        
                    # Rate limit kindness
                    time.sleep(0.2)
                            
                elif response.status_code == 401:
                    self.logger.error("Scopus: Authentication failed")
                    break
                else:
                    self.logger.warning(f"Scopus: Status {response.status_code}")
                    break
                    
            except Exception as e:
                self.logger.error(f"Scopus search error: {e}")
                break
        
        self.logger.info(f"Scopus: Fetched {len(articles)} articles")
        
        return SearchResult(
            query=query,
            articles=articles,
            total_found=total_found,
            sources=[self.source_name]
        )
    
    def _parse_entry(self, entry: Dict[str, Any]) -> Optional[Article]:
        """Parse Scopus API entry into Article."""
        try:
            title = entry.get('dc:title', 'Untitled')
            doi = entry.get('prism:doi', '')
            
            # Build URL
            if doi:
                url = f"https://doi.org/{doi}"
            else:
                links = entry.get('link', [])
                scopus_link = next(
                    (l.get('@href') for l in links if l.get('@ref') == 'scopus'), 
                    ''
                )
                url = scopus_link or f"https://www.scopus.com/record/display.uri?eid={entry.get('eid', '')}"
            
            return Article(
                title=title,
                url=url,
                doi=doi if doi else None,
                abstract="",
                authors=entry.get('dc:creator', ''),
                journal=entry.get('prism:publicationName', ''),
                year=entry.get('prism:coverDate', '')[:4] if entry.get('prism:coverDate') else '',
                source=self.source_name,
                is_open_access=entry.get('openaccessFlag', False),
                raw_data=entry
            )
        except Exception as e:
            self.logger.debug(f"Parse error: {e}")
            return None
    
    def get_abstract_by_doi(self, doi: str) -> Optional[str]:
        """Fetch abstract using DOI."""
        try:
            url = f"{self.ABSTRACT_URL}/doi/{doi}"
            response = requests.get(url, headers=self.headers, timeout=10)
            
            if response.status_code == 200:
                data = response.json()
                coredata = data.get('abstracts-retrieval-response', {}).get('coredata', {})
                return coredata.get('dc:description', '')
        except Exception:
            pass
        return None


class OpenAlexSearcher(BaseSearcher):
    """
    Search provider for OpenAlex API.
    
    OpenAlex is a free, open catalog of scholarly works. No API key required.
    Excellent for getting abstracts as they index the inverted abstract format.
    """
    
    BASE_URL = "https://api.openalex.org"
    
    def __init__(self, config: Config):
        super().__init__(config)
        self.email = config.contact_email
    
    @property
    def source_name(self) -> str:
        return "OpenAlex"
    
    def search(self, query: str, max_results: int = 25, year_min: Optional[int] = None, year_max: Optional[int] = None) -> SearchResult:
        """Search OpenAlex for papers with abstracts."""
        filter_str = "has_abstract:true"
        if year_min:
            filter_str += f",publication_year:{year_min}-{year_max or 2030}"
        return self._search_with_filter(query, max_results, filter_str)
    
    def search_elsevier(self, query: str, max_results: int = 25) -> SearchResult:
        """Search specifically for Elsevier/ScienceDirect papers."""
        filter_str = "primary_location.source.publisher_lineage:P4310320595,has_abstract:true"
        return self._search_with_filter(query, max_results, filter_str)
    
    def _search_with_filter(self, query: str, max_results: int, 
                            filter_str: str) -> SearchResult:
        """Execute search with given filter."""
        articles = []
        total_found = 0
        
        try:
            params = {
                'search': query,
                'per_page': min(max_results, 50),
                'filter': filter_str,
                'sort': 'relevance_score:desc',
                'mailto': self.email
            }
            
            response = requests.get(
                f"{self.BASE_URL}/works",
                params=params,
                timeout=15
            )
            
            if response.status_code == 200:
                data = response.json()
                total_found = data.get('meta', {}).get('count', 0)
                self.logger.info(f"OpenAlex: {total_found} total results")
                
                for work in data.get('results', []):
                    article = self._parse_work(work)
                    if article:
                        articles.append(article)
                        
        except Exception as e:
            self.logger.error(f"OpenAlex search error: {e}")
        
        return SearchResult(
            query=query,
            articles=articles,
            total_found=total_found,
            sources=[self.source_name]
        )
    
    def _parse_work(self, work: Dict[str, Any]) -> Optional[Article]:
        """Parse OpenAlex work into Article."""
        try:
            primary_loc = work.get('primary_location') or {}
            source = primary_loc.get('source') or {}
            
            # Get URL
            url = primary_loc.get('landing_page_url', '') or work.get('doi', '')
            
            # Reconstruct abstract from inverted index
            abstract = self._reconstruct_abstract(work.get('abstract_inverted_index'))
            
            # Get DOI
            doi = work.get('doi', '')
            if doi:
                doi = doi.replace('https://doi.org/', '')
            
            # Get authors
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
                source=self.source_name,
                is_open_access=work.get('open_access', {}).get('is_oa', False),
                citation_count=work.get('cited_by_count'),
                raw_data=work
            )
        except Exception as e:
            self.logger.debug(f"Parse error: {e}")
            return None
    
    def _reconstruct_abstract(self, inverted_index: Optional[Dict]) -> str:
        """Reconstruct abstract from OpenAlex inverted index format."""
        if not inverted_index:
            return ""
        
        word_positions = []
        for word, positions in inverted_index.items():
            for pos in positions:
                word_positions.append((pos, word))
        word_positions.sort()
        return ' '.join([w for _, w in word_positions])


class CrossRefEnricher(BaseAbstractEnricher):
    """
    Abstract enricher using CrossRef API.
    
    CrossRef has metadata for many DOIs including abstracts.
    """
    
    BASE_URL = "https://api.crossref.org"
    
    @property
    def source_name(self) -> str:
        return "CrossRef"
    
    def get_abstract(self, article: Article) -> Optional[str]:
        """Fetch abstract from CrossRef by DOI."""
        if not article.doi:
            return None
        
        try:
            url = f"{self.BASE_URL}/works/{article.doi}"
            headers = {
                'User-Agent': f'AcademicSearch/1.0 (mailto:{self.config.contact_email})'
            }
            
            response = requests.get(url, headers=headers, timeout=10)
            
            if response.status_code == 200:
                data = response.json()
                abstract = data.get('message', {}).get('abstract', '')
                if abstract:
                    # Clean HTML tags
                    abstract = re.sub(r'<[^>]+>', '', abstract)
                    return abstract.strip()
                    
        except Exception as e:
            self.logger.debug(f"CrossRef error: {e}")
        
        return None


class SemanticScholarSearcher(BaseSearcher):
    """
    Search provider for Semantic Scholar API.
    
    Free academic search engine with good coverage and abstracts.
    """
    
    BASE_URL = "https://api.semanticscholar.org/graph/v1"
    
    @property
    def source_name(self) -> str:
        return "Semantic Scholar"
    
    def search(self, query: str, max_results: int = 25, year_min: Optional[int] = None, year_max: Optional[int] = None) -> SearchResult:
        """Search Semantic Scholar database."""
        articles = []
        total_found = 0
        
        try:
            url = f"{self.BASE_URL}/paper/search"
            params = {
                'query': query,
                'limit': min(max_results, 100),
                'fields': 'title,abstract,authors,year,citationCount,publicationDate,journal,externalIds,url'
            }
            
            if year_min:
                params['year'] = f"{year_min}-{year_max or 2030}"
            
            response = requests.get(url, params=params, timeout=15)
            
            if response.status_code == 200:
                data = response.json()
                total_found = data.get('total', 0)
                papers = data.get('data', [])
                
                self.logger.info(f"Semantic Scholar: {total_found} total results")
                
                for paper in papers:
                    article = self._parse_paper(paper)
                    if article:
                        articles.append(article)
                        
        except Exception as e:
            self.logger.error(f"Semantic Scholar search error: {e}")
        
        return SearchResult(
            query=query,
            articles=articles,
            total_found=total_found,
            sources=[self.source_name]
        )
    
    def _parse_paper(self, paper: Dict[str, Any]) -> Optional[Article]:
        """Parse Semantic Scholar paper into Article."""
        try:
            # Get DOI
            external_ids = paper.get('externalIds', {})
            doi = external_ids.get('DOI')
            
            # Get URL
            url = paper.get('url', '')
            if not url and doi:
                url = f"https://doi.org/{doi}"
            
            # Get authors
            authors = ', '.join([a.get('name', '') for a in paper.get('authors', [])[:5]])
            
            return Article(
                title=paper.get('title', 'Untitled'),
                url=url,
                doi=doi,
                abstract=paper.get('abstract', ''),
                authors=authors,
                journal=paper.get('journal', {}).get('name', '') if paper.get('journal') else '',
                year=str(paper.get('year', '')),
                source=self.source_name,
                citation_count=paper.get('citationCount'),
                raw_data=paper
            )
        except Exception as e:
            self.logger.debug(f"Parse error: {e}")
            return None


class ArXivSearcher(BaseSearcher):
    """
    Search provider for arXiv.org preprint repository.
    
    Free access to preprints in physics, math, CS, etc.
    """
    
    BASE_URL = "http://export.arxiv.org/api/query"
    
    @property
    def source_name(self) -> str:
        return "arXiv"
    
    def search(self, query: str, max_results: int = 25, year_min: Optional[int] = None, year_max: Optional[int] = None) -> SearchResult:
        """Search arXiv database."""
        articles = []
        total_found = 0
        
        try:
            params = {
                'search_query': f'all:{query}',
                'start': 0,
                'max_results': min(max_results, 100),
                'sortBy': 'relevance'
            }
            
            response = requests.get(self.BASE_URL, params=params, timeout=15)
            
            if response.status_code == 200:
                import xml.etree.ElementTree as ET
                root = ET.fromstring(response.content)
                
                # Parse total results
                ns = {'atom': 'http://www.w3.org/2005/Atom', 'arxiv': 'http://arxiv.org/schemas/atom'}
                total_elem = root.find('.//atom:totalResults', ns)
                if total_elem is not None:
                    total_found = int(total_elem.text)
                
                self.logger.info(f"arXiv: {total_found} total results")
                
                # Parse entries
                for entry in root.findall('.//atom:entry', ns):
                    article = self._parse_entry(entry, ns, year_min, year_max)
                    if article:
                        articles.append(article)
                        
        except Exception as e:
            self.logger.error(f"arXiv search error: {e}")
        
        return SearchResult(
            query=query,
            articles=articles,
            total_found=total_found,
            sources=[self.source_name]
        )
    
    def _parse_entry(self, entry, ns: Dict[str, str], year_min: Optional[int], year_max: Optional[int]) -> Optional[Article]:
        """Parse arXiv entry into Article."""
        try:
            title = entry.find('atom:title', ns).text.strip().replace('\n', ' ')
            abstract = entry.find('atom:summary', ns).text.strip()
            published = entry.find('atom:published', ns).text[:4]
            year = int(published)
            
            # Year filter
            if year_min and year < year_min:
                return None
            if year_max and year > year_max:
                return None
            
            # Get authors
            authors = ', '.join([a.find('atom:name', ns).text for a in entry.findall('atom:author', ns)[:5]])
            
            # Get arxiv ID and DOI
            arxiv_id = entry.find('atom:id', ns).text.split('/abs/')[-1]
            doi_elem = entry.find('arxiv:doi', ns)
            doi = doi_elem.text if doi_elem is not None else None
            
            # Get categories as keywords
            keywords = [cat.get('term') for cat in entry.findall('atom:category', ns)]
            
            return Article(
                title=title,
                url=f"https://arxiv.org/abs/{arxiv_id}",
                doi=doi,
                abstract=abstract,
                authors=authors,
                year=str(year),
                keywords=keywords[:5],
                source=self.source_name,
                raw_data={'arxiv_id': arxiv_id}
            )
        except Exception as e:
            self.logger.debug(f"Parse error: {e}")
            return None


class SemanticScholarEnricher(BaseAbstractEnricher):
    """
    Abstract enricher using Semantic Scholar API.
    
    Searches by title to find matching papers with abstracts.
    """
    
    BASE_URL = "https://api.semanticscholar.org/graph/v1"
    
    @property
    def source_name(self) -> str:
        return "Semantic Scholar"
    
    def get_abstract(self, article: Article) -> Optional[str]:
        """Fetch abstract from Semantic Scholar by title search."""
        if not article.title or len(article.title) < 10:
            return None
        
        try:
            url = f"{self.BASE_URL}/paper/search"
            params = {
                'query': article.title[:200],
                'limit': 1,
                'fields': 'title,abstract'
            }
            
            response = requests.get(url, params=params, timeout=10)
            
            if response.status_code == 200:
                data = response.json()
                papers = data.get('data', [])
                if papers:
                    return papers[0].get('abstract', '')
                    
        except Exception as e:
            self.logger.debug(f"Semantic Scholar error: {e}")
        
        return None


class ScopusEnricher(BaseAbstractEnricher):
    """Abstract enricher using Scopus API."""
    
    def __init__(self, config: Config):
        super().__init__(config)
        self.searcher = ScopusSearcher(config)
    
    @property
    def source_name(self) -> str:
        return "Scopus"
    
    def get_abstract(self, article: Article) -> Optional[str]:
        """Fetch abstract from Scopus by DOI."""
        if not article.doi:
            return None
        return self.searcher.get_abstract_by_doi(article.doi)




class GoogleScholarSearcher(BaseSearcher):
    """
    Search provider for Google Scholar using Serper Dev API.
    
    Uses google.serper.dev to query Google Scholar without browser scraping.
    """
    
    SEARCH_HOST = "google.serper.dev"
    
    def __init__(self, config: Config):
        super().__init__(config)
        self.api_key = config.api.serper_api_key
    
    @property
    def source_name(self) -> str:
        return "Google Scholar"
    
    @property
    def is_available(self) -> bool:
        return bool(self.api_key)
    
    def search(self, query: str, max_results: int = 25, year_min: Optional[int] = None, year_max: Optional[int] = None) -> SearchResult:
        """Search Google Scholar using Serper API."""
        if not self.is_available:
            self.logger.warning("Serper API key not configured")
            return SearchResult(query=query, articles=[], total_found=0, sources=[self.source_name])
            
        articles = []
        total_found = 0
        import http.client
        import json
        
        try:
            conn = http.client.HTTPSConnection(self.SEARCH_HOST)
            
            # Serper Scholar results are usually 10 per page
            # Calculate number of pages needed
            import math
            results_per_page = 10
            num_pages = math.ceil(max_results / results_per_page)
            
            self.logger.info(f"Fetching {max_results} results from Google Scholar (approx {num_pages} pages)")
            
            for page in range(1, num_pages + 1):
                if total_found >= max_results:
                    break
                    
                # Construct payload
                payload_dict = {
                    "q": query,
                    "page": page
                }
                
                if year_min and year_min >= 2025:
                     payload_dict["tbs"] = "qdr:y"
                elif year_min:
                     payload_dict["q"] += f" after:{year_min}"
                
                payload = json.dumps(payload_dict)
                
                headers = {
                  'X-API-KEY': self.api_key,
                  'Content-Type': 'application/json'
                }
                
                self.logger.debug(f"Querying Serper Page {page}: {payload_dict}")
                conn.request("POST", "/scholar", payload, headers)
                res = conn.getresponse()
                data = res.read()
                
                if res.status == 200:
                    response_json = json.loads(data.decode("utf-8"))
                    
                    # Parse results
                    results_list = response_json.get('organic', [])
                    
                    if not results_list:
                        self.logger.info(f"No more results on page {page}")
                        break
                        
                    for item in results_list:
                        if len(articles) >= max_results:
                            break
                            
                        # Parse item
                        title = item.get('title', '')
                        link = item.get('link', '')
                        snippet = item.get('snippet', '')
                        
                        # Publication info
                        pub_info = item.get('publicationInfo', '')
                        authors_text = ""
                        
                        if isinstance(pub_info, dict):
                             authors_list = pub_info.get('authors', [])
                             if isinstance(authors_list, list):
                                authors_text = ", ".join([a.get('name', '') for a in authors_list if isinstance(a, dict)])
                        elif isinstance(pub_info, str):
                            parts = pub_info.split(' - ')
                            if parts:
                                authors_text = parts[0].strip()
                        
                        # Try to extract year
                        import re
                        year = ""
                        year_match = re.search(r'\b(19|20)\d{2}\b', str(pub_info))
                        if year_match:
                            year = year_match.group(0)
                            
                        article = Article(
                            title=title,
                            url=link,
                            abstract=snippet,
                            authors=authors_text,
                            source=self.source_name,
                            year=year
                        )
                        articles.append(article)
                        total_found += 1
                    
                    # Rate limit kindness for API loop
                    time.sleep(0.5)
                else:
                    self.logger.warning(f"Serper request failed on page {page}: {res.status}")
                    break
                    
            self.logger.info(f"Google Scholar (Serper): Found {len(articles)} articles")
                
        except Exception as e:
            self.logger.error(f"Google Scholar search error: {e}")
                

            
        return SearchResult(
            query=query,
            articles=articles,
            total_found=total_found,
            sources=[self.source_name]
        )


class ClarivateSearcher(BaseSearcher):
    """
    Search provider for Clarivate Web of Science Starter API.
    
    Supports advanced features:
    - Field-specific queries (TI, TS, AU, AI, OG, DO, PY, SO)
    - Sorting by citations, publication year, relevance
    - Multiple databases (WOS, BIOABS, MEDLINE)
    - Citation counts and author identifiers
    """
    
    SEARCH_URL = "https://api.clarivate.com/apis/wos-starter/v1/documents"
    DOCUMENT_URL = "https://api.clarivate.com/apis/wos-starter/v1/documents/{uid}"
    
    def __init__(self, config: Config):
        super().__init__(config)
        self.api_key = config.api.clarivate_api_key
        
    @property
    def source_name(self) -> str:
        return "Web of Science"
    
    @property
    def is_available(self) -> bool:
        return bool(self.api_key)
    
    def search(self, query: str, max_results: int = 25, year_min: Optional[int] = None, 
               year_max: Optional[int] = None, sort_by: str = "relevance",
               database: str = "WOS", detail: str = "full") -> SearchResult:
        """
        Search Web of Science Starter API with advanced options.
        
        Args:
            query: Search query. Can use field tags (TI=, TS=, AU=, etc.) or plain text.
            max_results: Maximum number of results to return.
            year_min: Minimum publication year.
            year_max: Maximum publication year.
            sort_by: Sort order. Options: 'relevance', 'citations' (most cited first),
                    'year_desc' (newest first), 'year_asc' (oldest first).
            database: Database to search. Options: 'WOS' (default), 'BIOABS', 'MEDLINE'.
            detail: Detail level. 'full' (default) or 'short'.
        
        Returns:
            SearchResult containing found articles.
        """
        if not self.is_available:
            self.logger.warning("Clarivate API key not configured")
            return SearchResult(
                query=query,
                articles=[],
                total_found=0,
                sources=[self.source_name]
            )
            
        articles = []
        total_found = 0
        
        try:
            page = 1
            limit = 50
            
            # Build search query with field tags if not present
            search_query = self._build_query(query, year_min, year_max)
            
            # Map sort_by to API sortField parameter
            sort_field = self._get_sort_field(sort_by)
            
            while len(articles) < max_results:
                params = {
                    'q': search_query,
                    'limit': min(max_results - len(articles), limit),
                    'page': page,
                    'db': database,
                    'detail': detail
                }
                
                if sort_field:
                    params['sortField'] = sort_field
                
                headers = {
                    'X-ApiKey': self.api_key
                }
                
                response = requests.get(
                    self.SEARCH_URL,
                    headers=headers,
                    params=params,
                    timeout=30
                )
                
                if response.status_code == 200:
                    data = response.json()
                    
                    hits = data.get('hits', [])
                    meta = data.get('metadata', {})
                    total_str = meta.get('total', 0) if isinstance(meta, dict) else 0
                    total_found = int(total_str)

                    if not hits:
                        self.logger.info(f"Clarivate: No results on page {page}")
                        break
                    
                    if page == 1:
                        self.logger.info(f"Clarivate: {total_found} total results found")
                        
                    for hit in hits:
                        if len(articles) >= max_results:
                            break
                        
                        article = self._parse_hit(hit)
                        if article:
                            articles.append(article)
                            
                    if len(articles) >= total_found:
                        break
                    
                    page += 1
                    time.sleep(0.2)  # Rate limiting
                    
                else:
                    self.logger.error(f"Clarivate request failed: {response.status_code} - {response.text}")
                    break
                    
        except Exception as e:
            self.logger.error(f"Clarivate search error: {e}")
            
        return SearchResult(
            query=query,
            articles=articles,
            total_found=total_found,
            sources=[self.source_name]
        )
    
    def _build_query(self, query: str, year_min: Optional[int] = None, 
                     year_max: Optional[int] = None) -> str:
        """
        Build WoS query with field tags and year filters.
        
        Field tags:
        - TS: Topic (title, abstract, keywords)
        - TI: Title
        - AU: Author
        - AI: Author Identifier (ORCID/ResearcherID)
        - OG: Organization
        - DO: DOI
        - PY: Publication Year
        - SO: Source (journal)
        """
        search_query = query
        
        # Add default field tag if not present
        if '=' not in query:
            # Use TS (Topic) for broader search coverage
            search_query = f"TS=({query})"
        
        # Add year filter if specified
        if year_min or year_max:
            if year_min and year_max:
                search_query += f" AND PY=({year_min}-{year_max})"
            elif year_min:
                search_query += f" AND PY=({year_min}-2030)"
            elif year_max:
                search_query += f" AND PY=(1900-{year_max})"
        
        return search_query
    
    def _get_sort_field(self, sort_by: str) -> Optional[str]:
        """
        Map sort_by parameter to WoS sortField value.
        
        Options:
        - RS: Relevance Score (default)
        - TC+D: Times Cited Descending (most cited first)
        - PY+D: Publication Year Descending (newest first)
        - PY+A: Publication Year Ascending (oldest first)
        - LD+D: Load Date Descending
        """
        sort_map = {
            'relevance': 'RS',
            'citations': 'TC+D',
            'year_desc': 'PY+D',
            'year_asc': 'PY+A',
            'newest': 'PY+D',
            'oldest': 'PY+A',
            'most_cited': 'TC+D'
        }
        return sort_map.get(sort_by.lower(), 'RS')
    
    def get_document_by_uid(self, uid: str, detail: str = "full") -> Optional[Article]:
        """
        Retrieve a specific document by its WoS UID (Accession Number).
        
        Args:
            uid: Web of Science Accession Number (e.g., "WOS:000123456789012")
            detail: Detail level ('full' or 'short')
        
        Returns:
            Article object or None if not found.
        """
        if not self.is_available:
            return None
        
        try:
            url = self.DOCUMENT_URL.format(uid=uid)
            params = {'detail': detail}
            headers = {'X-ApiKey': self.api_key}
            
            response = requests.get(url, headers=headers, params=params, timeout=15)
            
            if response.status_code == 200:
                data = response.json()
                # The response should contain the document directly
                return self._parse_hit(data)
            else:
                self.logger.warning(f"Failed to retrieve document {uid}: {response.status_code}")
                return None
                
        except Exception as e:
            self.logger.error(f"Error retrieving document {uid}: {e}")
            return None

    def _parse_hit(self, hit: Dict[str, Any]) -> Optional[Article]:
        """Parse Clarivate API hit with enhanced metadata."""
        try:
            title = hit.get('title', 'Untitled')
            if isinstance(title, list):
                title = title[0] if title else 'Untitled'
            
            # Authors with identifiers
            authors_list = hit.get('names', {}).get('authors', [])
            if not authors_list:
                authors_list = hit.get('authors', [])

            authors = ""
            author_ids = []
            if isinstance(authors_list, list):
                names = []
                for a in authors_list:
                    if isinstance(a, str):
                        names.append(a)
                    elif isinstance(a, dict):
                        display_name = a.get('displayName', a.get('wosStandard', ''))
                        names.append(display_name)
                        
                        # Capture author identifiers (ORCID, ResearcherID)
                        if 'researcherId' in a:
                            author_ids.append(f"RID:{a['researcherId']}")
                        if 'orcid' in a:
                            author_ids.append(f"ORCID:{a['orcid']}")
                
                authors = ", ".join(names)

            # Publication info
            source = hit.get('source', {})
            journal = source.get('sourceTitle', '')
            if isinstance(journal, list):
                journal = journal[0] if journal else ''
            
            year = source.get('publishYear', '')
            volume = source.get('volume', '')
            issue = source.get('issue', '')
            pages = source.get('pages', {})
            
            # Identifiers
            uids = hit.get('identifiers', {})
            doi = uids.get('doi', '')
            if not doi:
                doi = hit.get('doi', '')
            if isinstance(doi, list):
                doi = doi[0] if doi else ''
            
            pmid = uids.get('pmid', '')
            issn = uids.get('issn', '')
            eissn = uids.get('eissn', '')

            # Citation count
            citations_data = hit.get('citations', [])
            citation_count = None
            if citations_data and isinstance(citations_data, list):
                # Usually first element contains the count
                citation_count = citations_data[0].get('count', 0) if citations_data[0] else 0
            
            # Links
            links = hit.get('links', {})
            url = links.get('record', '')
            if not url and doi:
                url = f"https://doi.org/{doi}"
            
            # Keywords (from author keywords if available in full detail)
            keywords = []
            if 'keywords' in hit:
                kw_data = hit.get('keywords', {})
                if isinstance(kw_data, dict) and 'authorKeywords' in kw_data:
                    keywords = kw_data.get('authorKeywords', [])[:10]
            
            # Build citation string
            citation_str = journal
            if volume:
                citation_str += f", {volume}"
            if issue:
                citation_str += f"({issue})"
            if isinstance(pages, dict):
                page_range = pages.get('range', '')
                if page_range:
                    citation_str += f", {page_range}"
            
            return Article(
                title=str(title),
                url=url,
                doi=str(doi) if doi else None,
                abstract="",  # Starter API doesn't include abstracts
                authors=authors,
                journal=str(journal),
                year=str(year),
                keywords=keywords,
                citation_count=citation_count,
                source=self.source_name,
                is_open_access=False,  # Not provided in Starter API
                raw_data=hit
            )
        except Exception as e:
            self.logger.debug(f"Clarivate parse error: {e}")
            return None
    
    def search_by_author(self, author_name: str, max_results: int = 25, 
                         sort_by: str = "citations") -> SearchResult:
        """
        Search for papers by author name.
        
        Args:
            author_name: Author name to search for
            max_results: Maximum results to return
            sort_by: Sort order (default: most cited first)
        
        Returns:
            SearchResult with author's papers
        """
        query = f"AU=({author_name})"
        return self.search(query, max_results=max_results, sort_by=sort_by)
    
    def search_by_organization(self, org_name: str, max_results: int = 25,
                               sort_by: str = "citations") -> SearchResult:
        """
        Search for papers by organization/institution.
        
        Args:
            org_name: Organization name to search for
            max_results: Maximum results to return
            sort_by: Sort order (default: most cited first)
        
        Returns:
            SearchResult with organization's papers
        """
        query = f"OG=({org_name})"
        return self.search(query, max_results=max_results, sort_by=sort_by)
    
    def search_highly_cited(self, topic: str, min_year: Optional[int] = None,
                           max_results: int = 25) -> SearchResult:
        """
        Search for highly cited papers on a topic.
        
        Args:
            topic: Research topic
            min_year: Minimum publication year (optional)
            max_results: Maximum results to return
        
        Returns:
            SearchResult sorted by citation count (descending)
        """
        return self.search(
            query=topic,
            max_results=max_results,
            year_min=min_year,
            sort_by="citations"
        )
