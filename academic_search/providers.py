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
        """Search Scopus database."""
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
        
        try:
            # Build query with year filter
            search_query = query
            if year_min or year_max:
                year_filter = f" AND PUBYEAR > {year_min-1}" if year_min else ""
                year_filter += f" AND PUBYEAR < {year_max+1}" if year_max else ""
                search_query = query + year_filter
            
            params = {
                'query': search_query,
                'count': min(max_results, 25),
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
                
                self.logger.info(f"Scopus: {total_found} total results, fetched {len(results)}")
                
                for entry in results:
                    article = self._parse_entry(entry)
                    if article:
                        articles.append(article)
                        
            elif response.status_code == 401:
                self.logger.error("Scopus: Authentication failed")
            else:
                self.logger.warning(f"Scopus: Status {response.status_code}")
                
        except Exception as e:
            self.logger.error(f"Scopus search error: {e}")
        
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
