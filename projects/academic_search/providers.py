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
from .models import Article, ProviderOutcome, SearchResult
from .config import Config

try:
    from firecrawl import Firecrawl
except ImportError:
    Firecrawl = None


class FirecrawlResearchSearcher(BaseSearcher):
    """
    Supplemental scholarly discovery through Firecrawl Research.

    The Research API is optional and may not be configured by a self-hosted
    Firecrawl deployment. Failures therefore produce an empty provider result
    while the engine continues with its official scholarly API providers.
    """

    def __init__(self, config: Config, client: Any = None):
        super().__init__(config)
        self.client = client
        if (
            self.client is None
            and config.enable_firecrawl_research
            and config.api.firecrawl_api_url
            and Firecrawl is not None
        ):
            self.client = Firecrawl(
                api_key=config.api.firecrawl_api_key,
                api_url=config.api.firecrawl_api_url,
                timeout=config.timeout,
            )

    @property
    def source_name(self) -> str:
        return "Firecrawl Research"

    @property
    def is_available(self) -> bool:
        return bool(self.config.enable_firecrawl_research and self.client is not None)

    def search(
        self,
        query: str,
        max_results: int = 25,
        year_min: Optional[int] = None,
        year_max: Optional[int] = None,
    ) -> SearchResult:
        if not self.is_available or not query.strip() or max_results <= 0:
            return self._empty_result(query)

        if year_min is not None and year_max is not None and year_min > year_max:
            self.logger.warning("Firecrawl Research: invalid year range")
            return self._empty_result(query)

        try:
            response = self.client.v2.search_papers(
                query,
                k=min(max_results, 500),
                from_date=f"{year_min}-01-01" if year_min is not None else None,
                to_date=f"{year_max}-12-31" if year_max is not None else None,
            )
        except Exception as exc:
            self.logger.warning("Firecrawl Research request failed: %s", exc)
            return self._empty_result(query)

        if not isinstance(response, dict) or response.get("success") is False:
            self.logger.warning("Firecrawl Research returned an invalid response")
            return self._empty_result(query)

        records = response.get("results")
        if not isinstance(records, list):
            self.logger.warning("Firecrawl Research response did not contain results")
            return self._empty_result(query)

        articles: List[Article] = []
        for record in records:
            try:
                article = self._parse_paper(record, year_min, year_max)
            except (TypeError, ValueError) as exc:
                self.logger.debug("Skipping malformed Firecrawl paper: %s", exc)
                continue
            if article is not None:
                articles.append(article)
            if len(articles) >= max_results:
                break

        return SearchResult(
            query=query,
            articles=articles,
            total_found=len(articles),
            sources=[self.source_name],
        )

    def _empty_result(self, query: str) -> SearchResult:
        return SearchResult(
            query=query,
            articles=[],
            total_found=0,
            sources=[self.source_name],
        )

    @staticmethod
    def _first(record: Dict[str, Any], *keys: str) -> Any:
        for key in keys:
            value = record.get(key)
            if value not in (None, "", []):
                return value
        return None

    @staticmethod
    def _year(value: Any) -> Optional[str]:
        if value is None:
            return None
        match = re.search(r"\b(18|19|20|21)\d{2}\b", str(value))
        return match.group(0) if match else None

    @staticmethod
    def _authors(value: Any) -> Optional[str]:
        if isinstance(value, str):
            return value.strip() or None
        if not isinstance(value, list):
            return None

        names: List[str] = []
        for author in value:
            if isinstance(author, str) and author.strip():
                names.append(author.strip())
            elif isinstance(author, dict):
                name = (
                    author.get("name")
                    or author.get("displayName")
                    or author.get("display_name")
                )
                if isinstance(name, str) and name.strip():
                    names.append(name.strip())
        return ", ".join(names) or None

    @staticmethod
    def _text(value: Any) -> Optional[str]:
        if isinstance(value, str):
            return value.strip() or None
        if isinstance(value, dict):
            for key in ("name", "displayName", "display_name", "title"):
                text = value.get(key)
                if isinstance(text, str) and text.strip():
                    return text.strip()
        return None

    @staticmethod
    def _boolean(value: Any) -> bool:
        if isinstance(value, bool):
            return value
        if isinstance(value, str):
            return value.strip().lower() in ("true", "1", "yes")
        if isinstance(value, (int, float)):
            return value == 1
        return False

    def _parse_paper(
        self,
        record: Any,
        year_min: Optional[int],
        year_max: Optional[int],
    ) -> Optional[Article]:
        if not isinstance(record, dict):
            return None

        title = self._first(record, "title", "name")
        if not isinstance(title, str) or not title.strip():
            return None

        year = self._year(
            self._first(
                record,
                "year",
                "publishedDate",
                "published_date",
                "publicationDate",
                "publication_date",
                "date",
            )
        )
        if year is not None:
            numeric_year = int(year)
            if year_min is not None and numeric_year < year_min:
                return None
            if year_max is not None and numeric_year > year_max:
                return None

        doi = self._first(record, "doi", "DOI")
        if isinstance(doi, str):
            doi = re.sub(r"^https?://(?:dx\.)?doi\.org/", "", doi.strip(), flags=re.I)
            doi = doi or None
        else:
            doi = None

        url = self._text(
            self._first(
                record,
                "url",
                "paperUrl",
                "paper_url",
                "landingPageUrl",
                "landing_page_url",
            )
        )
        if url is None:
            url = f"https://doi.org/{doi}" if doi else ""

        keywords_value = self._first(record, "keywords", "categories")
        if isinstance(keywords_value, list):
            keywords = [str(value) for value in keywords_value if value]
        else:
            keywords = []

        citation_count = self._first(
            record, "citationCount", "citation_count", "citedByCount"
        )
        try:
            citation_count = int(citation_count) if citation_count is not None else None
        except (TypeError, ValueError):
            citation_count = None

        return Article(
            title=title.strip(),
            url=url,
            doi=doi,
            abstract=self._text(self._first(record, "abstract", "summary")),
            authors=self._authors(self._first(record, "authors", "author")),
            journal=self._text(
                self._first(
                    record,
                    "journal",
                    "venue",
                    "publicationName",
                    "publication_name",
                )
            ),
            year=year,
            keywords=keywords,
            source=self.source_name,
            is_open_access=self._boolean(
                self._first(record, "isOpenAccess", "is_open_access", "openAccess")
            ),
            citation_count=citation_count,
            raw_data=record,
        )


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
        
        self.clear_last_failure()
        articles = []
        total_found = 0
        
        try:
            # Build query with year filter using pub-date field
            # ScienceDirect uses different syntax: pub-date AFT YYYYMMDD
            # Update: Don't wrap query in quotes to allow boolean operators/keywords
            search_query = f'title-abs-key({query})'
            
            if year_min:
                year_min_date = f"{year_min - 1}1231"
                search_query += f" AND pub-date AFT {year_min_date}"
            
            if year_max:
                year_max_date = f"{year_max + 1}0101"
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
                        
            elif response.status_code in (401, 403):
                self.logger.error("ScienceDirect: Authentication failed")
                self.last_failure = {"code": "authentication", "message": "authentication failed"}
            elif response.status_code == 429:
                self.last_failure = {"code": "rate_limited", "message": "provider rate limit reached"}
            else:
                self.logger.warning(f"ScienceDirect: Status {response.status_code}")
                self.last_failure = {"code": "http_error", "message": "provider request failed"}
                
        except Exception as e:
            self.last_failure = self._failure_from_exception(e)
        
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
    SERIAL_URL = "https://api.elsevier.com/content/serial/title"
    SUBJECT_AREAS = {
        "AGRI": "Agricultural and Biological Sciences", "ARTS": "Arts and Humanities",
        "BIOC": "Biochemistry, Genetics and Molecular Biology", "BUSI": "Business, Management and Accounting",
        "CENG": "Chemical Engineering", "CHEM": "Chemistry", "COMP": "Computer Science",
        "DECI": "Decision Sciences", "DENT": "Dentistry", "EART": "Earth and Planetary Sciences",
        "ECON": "Economics, Econometrics and Finance", "ENER": "Energy", "ENGI": "Engineering",
        "ENVI": "Environmental Science", "HEAL": "Health Professions", "IMMU": "Immunology and Microbiology",
        "MATE": "Materials Science", "MATH": "Mathematics", "MEDI": "Medicine",
        "NEUR": "Neuroscience", "NURS": "Nursing", "PHAR": "Pharmacology, Toxicology and Pharmaceutics",
        "PHYS": "Physics and Astronomy", "PSYC": "Psychology", "SOCI": "Social Sciences",
        "VETE": "Veterinary", "MULT": "Multidisciplinary",
    }
    
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
        return "Scopus"
    
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
        
        self.clear_last_failure()
        articles = []
        total_found = 0
        
        # Build query with year filter
        search_query = query
        if year_min or year_max:
            year_filter = f" AND PUBYEAR > {year_min-1}" if year_min else ""
            year_filter += f" AND PUBYEAR < {year_max+1}" if year_max else ""
            search_query = f"({query})" + year_filter
        
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
                            
                elif response.status_code in (401, 403):
                    self.logger.error("Scopus: Authentication failed")
                    self.last_failure = {"code": "authentication", "message": "authentication failed"}
                    break
                elif response.status_code == 429:
                    self.last_failure = {"code": "rate_limited", "message": "provider rate limit reached"}
                    break
                else:
                    self.logger.warning(f"Scopus: Status {response.status_code}")
                    self.last_failure = {"code": "http_error", "message": "provider request failed"}
                    break
                    
            except Exception as e:
                self.last_failure = self._failure_from_exception(e)
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

    def journal_categories(self, query: str = "", limit: int = 50) -> List[Dict[str, Any]]:
        wanted = query.strip().casefold()
        categories = [
            {"id": code, "label": label, "provider": "scopus"}
            for code, label in self.SUBJECT_AREAS.items()
            if not wanted or wanted in label.casefold() or wanted in code.casefold()
        ]
        return categories[:limit]

    def journal_catalog(
        self, query: str = "", category_id: Optional[str] = None, limit: int = 25, page: int = 1
    ) -> List[Dict[str, Any]]:
        self.last_total = None
        if not self.is_available:
            self.last_failure = {"code": "not_configured", "message": "Elsevier API key not configured"}
            return []
        count = min(max(limit, 1), 200)
        params: Dict[str, Any] = {
            "content": "journal",
            "count": count,
            "start": (max(page, 1) - 1) * count,
            "view": "STANDARD",
        }
        if query.strip():
            params["title"] = query.strip()
        if category_id:
            params["subj"] = category_id
        data = self._make_request(self.SERIAL_URL, params, headers=self.headers)
        response = (data or {}).get("serial-metadata-response", {})
        entries = response.get("entry", [])
        try:
            self.last_total = int(response["opensearch:totalResults"])
        except (KeyError, TypeError, ValueError):
            self.last_total = None
        return [
            normalized
            for normalized in (self._catalog_serial(entry) for entry in entries)
            if normalized is not None
        ]

    def resolve_journal(self, journal_id: str) -> Optional[Dict[str, Any]]:
        """Resolve a Scopus serial by ISSN (used as its portable catalog ID)."""
        if not self.is_available:
            self.last_failure = {"code": "not_configured", "message": "Elsevier API key not configured"}
            return None
        data = self._make_request(
            self.SERIAL_URL,
            {"issn": journal_id, "count": 1, "view": "STANDARD"},
            headers=self.headers,
        )
        entries = (data or {}).get("serial-metadata-response", {}).get("entry", [])
        return self._catalog_serial(entries[0]) if entries else None

    def _catalog_serial(self, entry: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        if not isinstance(entry, dict):
            return None
        title = entry.get("dc:title") or entry.get("prism:publicationName")
        issn = entry.get("prism:issn") or entry.get("prism:eIssn")
        if not title or not issn:
            return None
        e_issn = entry.get("prism:eIssn")
        issns = list(dict.fromkeys(str(value) for value in (issn, e_issn) if value))
        source_id = str(entry.get("source-id") or entry.get("dc:identifier") or "")
        subject_value = entry.get("subject-area") or entry.get("subject-areas") or []
        if isinstance(subject_value, dict):
            subject_value = subject_value.get("subject-area") or []
        if isinstance(subject_value, dict):
            subject_value = [subject_value]
        categories = []
        for subject in subject_value if isinstance(subject_value, list) else []:
            if not isinstance(subject, dict):
                continue
            code = subject.get("@abbrev") or subject.get("@code") or ""
            label = subject.get("$") or subject.get("name") or self.SUBJECT_AREAS.get(code, code)
            if code or label:
                categories.append({"id": str(code), "label": str(label)})
        return {
            "id": str(issn),
            "catalog_id": f"scopus:{issn}",
            "catalog_provider": "scopus",
            "provider_id": source_id or str(issn),
            "display_name": str(title),
            "issn_l": str(issn),
            "issns": issns,
            "publisher": entry.get("dc:publisher") or entry.get("publisher") or "",
            "works_count": 0,
            "is_oa": str(entry.get("openaccess") or "").lower() in {"1", "true", "yes"},
            "is_in_doaj": False,
            "type": "journal",
            "source": self.source_name,
            "categories": categories,
            "identifiers": {"scopus": source_id or None, "issn_l": str(issn), "issns": issns},
            "search_supported": False,
            "source_url": entry.get("prism:url") or "",
        }


class OpenAlexSearcher(BaseSearcher):
    """
    Search provider for OpenAlex API.
    
    OpenAlex is a free, open catalog of scholarly works. An optional API key increases the request budget.
    Excellent for getting abstracts as they index the inverted abstract format.
    """
    
    BASE_URL = "https://api.openalex.org"
    
    PAGE_SIZE = 100
    BASIC_RESULT_LIMIT = 10_000

    def __init__(self, config: Config):
        super().__init__(config)
        self.email = config.contact_email

    def _make_request(self, url, params, headers=None):
        key = self.config.api.openalex_api_key
        if key:
            headers = {**(headers or {}), "Authorization": f"Bearer {key}"}
        return super()._make_request(url, params, headers)

    @property
    def source_name(self) -> str:
        return "OpenAlex"
    
    def search(self, query: str, max_results: int = 25, year_min: Optional[int] = None, year_max: Optional[int] = None,
               *, sort_by: str = "relevance_score:desc") -> SearchResult:
        """Search OpenAlex for papers with abstracts."""
        filter_str = "has_abstract:true"
        if year_min or year_max:
            filter_str += f",publication_year:{year_min or 1800}-{year_max or 2200}"
        return self._search_with_filter(query, max_results, filter_str, sort_by=sort_by)

    def search_recent(self, query, max_results, year_min, year_max):
        return self.search(query, max_results, year_min, year_max, sort_by="publication_date:desc")
    
    def search_elsevier(self, query: str, max_results: int = 25) -> SearchResult:
        """Search specifically for Elsevier/ScienceDirect papers."""
        filter_str = "primary_location.source.publisher_lineage:P4310320595,has_abstract:true"
        return self._search_with_filter(query, max_results, filter_str)

    def suggest_journals(self, query: str, limit: int = 8) -> List[Dict[str, Any]]:
        """Resolve a user-entered journal name to stable OpenAlex/ISSN identity."""
        self.clear_last_failure()
        data = self._make_request(
            f"{self.BASE_URL}/sources",
            {
                "search": query.strip(),
                "filter": "type:journal",
                "per_page": min(max(limit, 1), 20),
                "mailto": self.email,
            },
        )
        journals = []
        for source in self._list_records(data):
            if source.get("type") != "journal":
                continue
            normalized = self._catalog_source(source)
            if normalized:
                journals.append(normalized)
        return journals

    def journal_categories(self, query: str = "", limit: int = 50) -> List[Dict[str, Any]]:
        """Return OpenAlex Fields used to categorize journal Sources."""
        self.clear_last_failure()
        params: Dict[str, Any] = {
            "per_page": min(max(limit, 1), 100),
            "sort": "works_count:desc",
            "mailto": self.email,
        }
        if query.strip():
            params["search"] = query.strip()
        data = self._make_request(f"{self.BASE_URL}/fields", params)
        return [
            {
                "id": str(item.get("id") or "").rsplit("/", 1)[-1],
                "label": item.get("display_name") or "Unknown field",
                "provider": "openalex",
                "works_count": item.get("works_count") or 0,
            }
            for item in self._list_records(data)
            if item.get("id")
        ]

    def journal_catalog(
        self, query: str = "", category_id: Optional[str] = None, limit: int = 25, page: int = 1
    ) -> List[Dict[str, Any]]:
        """Browse or search journal Sources, optionally scoped to an OpenAlex Field."""
        self.clear_last_failure()
        self.last_total = None
        filters = ["type:journal"]
        if category_id:
            stable_category = str(category_id).rsplit("/", 1)[-1]
            filters.append(f"topics.field.id:{stable_category}")
        params: Dict[str, Any] = {
            "filter": ",".join(filters),
            "per_page": min(max(limit, 1), self.PAGE_SIZE),
            "page": max(page, 1),
            "sort": "works_count:desc",
            "mailto": self.email,
        }
        if query.strip():
            params["search"] = query.strip()
        data = self._make_request(f"{self.BASE_URL}/sources", params)
        records = self._list_records(data)
        meta = (data or {}).get("meta")
        if isinstance(meta, dict) and isinstance(meta.get("count"), int):
            self.last_total = meta["count"]
        return [
            normalized
            for normalized in (self._catalog_source(item) for item in records)
            if normalized is not None
        ]

    def resolve_journal(self, journal_id: str) -> Optional[Dict[str, Any]]:
        """Resolve one OpenAlex Source ID to complete journal metadata."""
        stable_id = str(journal_id).rsplit("/", 1)[-1]
        if not re.fullmatch(r"S\d+", stable_id):
            self.last_failure = {"code": "invalid_journal_id", "message": "invalid OpenAlex source"}
            return None
        data = self._make_request(
            f"{self.BASE_URL}/sources/{stable_id}", {"mailto": self.email}
        )
        return self._catalog_source(data) if data else None

    def resolve_journal_by_issn(self, issn: str) -> Optional[Dict[str, Any]]:
        """Crosswalk an ISSN from another catalog to an OpenAlex Source."""
        self.clear_last_failure()
        normalized_issn = str(issn or "").strip().upper().replace("-", "")
        if not re.fullmatch(r"\d{7}[0-9X]", normalized_issn):
            return None
        normalized_issn = f"{normalized_issn[:4]}-{normalized_issn[4:]}"
        data = self._make_request(
            f"{self.BASE_URL}/sources",
            {"filter": f"issn:{normalized_issn}", "per_page": 1, "mailto": self.email},
        )
        results = self._list_records(data)
        return self._catalog_source(results[0]) if results else None

    def _list_records(self, data):
        if data is None:
            return []
        records = data.get("results")
        if not isinstance(records, list):
            self._invalid_response()
            return []
        parsed = [record for record in records if isinstance(record, dict)]
        if records and not parsed:
            self._invalid_response()
        return parsed

    def _catalog_source(self, source: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        if not isinstance(source, dict) or source.get("type") not in (None, "journal"):
            return None
        source_id = str(source.get("id") or "").rsplit("/", 1)[-1]
        if not re.fullmatch(r"S\d+", source_id):
            return None
        categories = []
        seen = set()
        for topic in source.get("topics") or []:
            field = topic.get("field") or {}
            field_id = str(field.get("id") or "").rsplit("/", 1)[-1]
            if field_id and field_id not in seen:
                categories.append({"id": field_id, "label": field.get("display_name") or field_id})
                seen.add(field_id)
        issns = [str(value) for value in (source.get("issn") or []) if value]
        issn_l = source.get("issn_l")
        identifiers = {
            "openalex": source_id,
            "issn_l": issn_l,
            "issns": issns,
        }
        return {
            "id": source_id,
            "catalog_id": f"openalex:{source_id}",
            "catalog_provider": "openalex",
            "provider_id": source_id,
            "display_name": source.get("display_name") or "Unknown journal",
            "issn_l": issn_l,
            "issns": issns,
            "publisher": source.get("host_organization_name") or "",
            "works_count": source.get("works_count") or 0,
            "is_oa": bool(source.get("is_oa")),
            "is_in_doaj": bool(source.get("is_in_doaj")),
            "type": "journal",
            "source": self.source_name,
            "categories": categories,
            "identifiers": identifiers,
            "search_supported": True,
            "homepage_url": source.get("homepage_url") or "",
            "source_url": f"https://openalex.org/{source_id}",
        }

    def search_journal(
        self,
        journal_id: str,
        journal_name: str,
        query: str,
        max_results: int = 25,
        year_min: Optional[int] = None,
        year_max: Optional[int] = None,
        *,
        published_through: Optional[str] = None,
    ) -> SearchResult:
        """Search works scoped to one resolved OpenAlex journal source."""
        self.clear_last_failure()
        stable_id = str(journal_id).rsplit("/", 1)[-1]
        if not re.fullmatch(r"S\d+", stable_id):
            self.last_failure = {
                "code": "invalid_journal_id",
                "message": "journal identifier is not a valid OpenAlex source",
            }
            return SearchResult(
                query=query,
                requested_providers=[self.source_name],
                provider_outcomes=[ProviderOutcome(
                    self.source_name, "failed",
                    error_code="invalid_journal_id",
                    message="journal identifier is not a valid OpenAlex source",
                )],
                year_min=year_min,
                year_max=year_max,
                limit=max_results,
            )

        filters = [f"primary_location.source.id:{stable_id}"]
        if published_through:
            filters.append(f"to_publication_date:{published_through}")
        else:
            filters.append("has_abstract:true")
        if year_min or year_max:
            filters.append(
                f"publication_year:{year_min or 1800}-{year_max or 2200}"
            )
        data = self._make_request(
            f"{self.BASE_URL}/works",
            {
                **({"search": query.strip()} if not published_through or query.strip() else {}),
                "filter": ",".join(filters),
                "per_page": min(max(max_results, 1), 50),
                "sort": "publication_date:desc" if published_through else "relevance_score:desc",
                "mailto": self.email,
            },
        )
        records = self._list_records(data)
        if data is None or self.last_failure:
            failure = self.last_failure or {
                "code": "provider_error", "message": "journal search failed"
            }
            return SearchResult(
                query=query,
                requested_providers=[self.source_name],
                provider_outcomes=[ProviderOutcome(
                    self.source_name,
                    "rate_limited" if failure["code"] == "rate_limited" else "failed",
                    error_code=failure["code"],
                    message=failure["message"],
                )],
                year_min=year_min,
                year_max=year_max,
                limit=max_results,
            )

        articles = [
            article
            for article in (self._parse_work(work) for work in records)
            if article is not None
        ]
        meta = data.get("meta") or {}
        total = meta.get("count") if isinstance(meta, dict) else None
        if not isinstance(total, int):
            total = len(articles)
        return SearchResult(
            query=query,
            articles=articles,
            total_found=total,
            sources=[self.source_name],
            requested_providers=[self.source_name],
            provider_outcomes=[ProviderOutcome(
                self.source_name, "empty" if published_through and not articles else "responded", returned_count=len(articles),
                total_found=total,
            )],
            year_min=year_min,
            year_max=year_max,
            limit=max_results,
            raw_article_count=len(articles),
            deduplicated_article_count=len(articles),
        )
    
    def _search_with_filter(self, query: str, max_results: int, filter_str: str, *,
                            sort_by: str = "relevance_score:desc") -> SearchResult:
        self.clear_last_failure()
        if max_results <= 0:
            return SearchResult(query=query)
        page_size = min(max_results, self.PAGE_SIZE)
        params = {
            "search": query, "per_page": page_size, "filter": filter_str,
            "sort": sort_by, "mailto": self.email,
        }
        use_cursor = max_results > self.BASIC_RESULT_LIMIT and bool(self.config.api.openalex_api_key)
        target = max_results if use_cursor else min(max_results, self.BASIC_RESULT_LIMIT)
        page_limit = (target + page_size - 1) // page_size
        cursor = "*"
        seen_cursors = set()
        articles = []
        total = 0
        seen_records = set()
        for page in range(1, page_limit + 1):
            paging = {"cursor": cursor} if use_cursor else {"page": page}
            data = self._make_request(f"{self.BASE_URL}/works", {**params, **paging})
            if data is None:
                break
            rows, meta = data.get("results"), data.get("meta")
            if not isinstance(rows, list) or not isinstance(meta, dict) or not isinstance(meta.get("count"), int):
                self._invalid_response()
                break
            total = meta["count"]
            for work in rows:
                if not isinstance(work, dict):
                    continue
                identifier = work.get("id")
                if identifier and identifier in seen_records:
                    continue
                article = self._parse_work(work)
                if article:
                    articles.append(article)
                    if identifier:
                        seen_records.add(identifier)
            if not rows or len(articles) >= target or (not use_cursor and page * page_size >= total):
                break
            if use_cursor:
                seen_cursors.add(cursor)
                cursor = meta.get("next_cursor")
                if not cursor or cursor in seen_cursors:
                    break
        return SearchResult(
            query=query, articles=articles[:target], total_found=total,
            sources=[self.source_name] if articles else [],
        )

    def _parse_work(self, work: Dict[str, Any]) -> Optional[Article]:
        """Parse OpenAlex work into Article."""
        try:
            primary_loc = work.get('primary_location') or {}
            source = primary_loc.get('source') or {}
            
            # Get URL
            url = primary_loc.get('landing_page_url') or work.get('doi') or work.get('id') or ''
            
            # Reconstruct abstract from inverted index
            abstract = self._reconstruct_abstract(work.get('abstract_inverted_index'))
            
            # Get DOI
            doi = work.get('doi', '')
            if doi:
                doi = doi.replace('https://doi.org/', '')
            
            # Get authors
            authors = ', '.join([
                (a.get('author') or {}).get('display_name') or ''
                for a in (work.get('authorships') or [])[:5] if isinstance(a, dict)
            ])
            
            # Get keywords from concepts
            keywords = [
                c.get('display_name', '')
                for c in (work.get('concepts') or [])[:10] if isinstance(c, dict)
                if c.get('display_name') and (c.get('score') or 0) > 0.3
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
        """Return relevance-ranked results from the documented offset API."""
        self.clear_last_failure()
        target = min(max_results, 1000)
        articles: List[Article] = []
        total = 0
        offset = 0
        api_key = self.config.api.semantic_scholar_api_key
        headers = {"x-api-key": api_key} if api_key else None
        while offset < target:
            params = {
                "query": query, "offset": offset, "limit": min(target - offset, 100),
                "fields": "title,abstract,authors,year,citationCount,publicationDate,journal,externalIds,url",
            }
            if year_min or year_max:
                params["year"] = f"{year_min or ''}-{year_max or ''}"
            data = self._make_request(f"{self.BASE_URL}/paper/search", params, headers)
            if data is None:
                break
            rows = data.get("data")
            if not isinstance(rows, list) or not isinstance(data.get("total"), int):
                self._invalid_response()
                break
            total = data["total"]
            articles.extend(article for paper in rows if (article := self._parse_paper(paper)))
            next_offset = data.get("next")
            if not rows or not isinstance(next_offset, int) or next_offset <= offset:
                break
            offset = next_offset
        return SearchResult(query=query, articles=articles[:target], total_found=total,
                            sources=[self.source_name] if articles else [])

    def _parse_paper(self, paper: Dict[str, Any]) -> Optional[Article]:
        """Parse Semantic Scholar paper into Article."""
        try:
            # Get DOI
            external_ids = paper.get('externalIds') or {}
            doi = external_ids.get('DOI')
            
            # Get URL
            url = paper.get('url', '')
            if not url and doi:
                url = f"https://doi.org/{doi}"
            if not url and paper.get("paperId"):
                url = f"https://www.semanticscholar.org/paper/{paper['paperId']}"
            
            # Get authors
            authors = ', '.join([a.get('name') or '' for a in (paper.get('authors') or [])[:5] if isinstance(a, dict)])
            
            return Article(
                title=paper.get('title') or 'Untitled',
                url=url,
                doi=doi,
                abstract=paper.get('abstract', ''),
                authors=authors,
                journal=paper.get('journal', {}).get('name', '') if paper.get('journal') else '',
                year=str(paper['year']) if paper.get('year') else None,
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
    
    BASE_URL = "https://export.arxiv.org/api/query"
    
    @property
    def source_name(self) -> str:
        return "arXiv"

    @staticmethod
    def _build_query(query: str) -> str:
        """Require every term; arXiv ORs bare terms after the first field prefix."""
        if re.search(r"\b(AND|OR|ANDNOT)\b|\w+:", query):
            return query
        terms = [term for term in re.findall(r"[\w-]+", query) if term]
        return " AND ".join(f"all:{term}" for term in terms) or f"all:{query}"

    def search(self, query: str, max_results: int = 25, year_min: Optional[int] = None, year_max: Optional[int] = None,
               *, sort_by: str = "relevance") -> SearchResult:
        """Submit year limits with the query so the provider applies them before sorting."""
        import xml.etree.ElementTree as ET

        self.clear_last_failure()
        search_query = self._build_query(query)
        if year_min or year_max:
            search_query = f"({search_query}) AND submittedDate:[{year_min or 1800}01010000 TO {year_max or 2200}12312359]"
        params = {"search_query": search_query, "start": 0,
                  "max_results": min(max_results, 2000), "sortBy": sort_by, "sortOrder": "descending"}
        ns = {"atom": "http://www.w3.org/2005/Atom", "arxiv": "http://arxiv.org/schemas/atom",
              "opensearch": "http://a9.com/-/spec/opensearch/1.1/"}
        try:
            response = requests.get(self.BASE_URL, params=params, timeout=self.config.timeout)
            if response.status_code != 200:
                raise requests.HTTPError(response=response)
            root = ET.fromstring(response.content)
            if root.tag != f'{{{ns["atom"]}}}feed':
                raise ValueError("missing Atom feed")
            entries = root.findall("atom:entry", ns)
            if any("/api/errors" in (entry.findtext("atom:id", default="", namespaces=ns)) for entry in entries):
                raise ValueError("arXiv error feed")
            articles = [article for entry in entries if (article := self._parse_entry(entry, ns, year_min, year_max))]
            total = root.findtext("opensearch:totalResults", namespaces=ns)
            return SearchResult(query=query, articles=articles, total_found=int(total) if total else len(articles),
                                sources=[self.source_name] if articles else [])
        except requests.RequestException as exc:
            self.last_failure = self._failure_from_exception(exc)
        except (ET.ParseError, ValueError):
            self._invalid_response()
        return SearchResult(query=query)

    def search_recent(self, query, max_results, year_min, year_max):
        return self.search(query, max_results, year_min, year_max, sort_by="submittedDate")

    def _parse_entry(self, entry, ns: Dict[str, str], year_min: Optional[int], year_max: Optional[int]) -> Optional[Article]:
        """Parse arXiv entry into Article."""
        try:
            title = entry.find('atom:title', ns).text.strip().replace('\n', ' ')
            abstract = entry.find('atom:summary', ns).text.strip()
            published = entry.find('atom:published', ns).text
            year = int(published[:4])
            
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
            keywords = [term for cat in entry.findall('atom:category', ns) if (term := cat.get('term'))]
            
            return Article(
                title=title,
                url=f"https://arxiv.org/abs/{arxiv_id}",
                doi=doi,
                abstract=abstract,
                authors=authors,
                year=str(year),
                keywords=keywords[:5],
                source=self.source_name,
                raw_data={'arxiv_id': arxiv_id, 'publication_date': published}
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
            
        self.clear_last_failure()
        articles = []
        total_found = 0
        import http.client
        import json
        
        conn = http.client.HTTPSConnection(self.SEARCH_HOST, timeout=self.config.timeout)
        try:
            
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
                
                if year_min:
                    payload_dict["q"] += f" after:{year_min - 1}-12-31"
                if year_max:
                    payload_dict["q"] += f" before:{year_max + 1}-01-01"
                
                payload = json.dumps(payload_dict)
                
                headers = {
                  'X-API-KEY': self.api_key,
                  'Content-Type': 'application/json'
                }
                
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
                        if year and ((year_min and int(year) < year_min) or (year_max and int(year) > year_max)):
                            continue
                            
                        article = Article(
                            title=title,
                            url=link,
                            raw_data={"search_snippet": snippet},
                            authors=authors_text,
                            source=self.source_name,
                            year=year
                        )
                        articles.append(article)
                        total_found += 1
                    
                    # Rate limit kindness for API loop
                    time.sleep(0.5)
                else:
                    if res.status == 429:
                        self.last_failure = {"code": "rate_limited", "message": "provider rate limit reached"}
                    elif res.status in (401, 403):
                        self.last_failure = {"code": "authentication", "message": "authentication failed"}
                    else:
                        self.last_failure = {"code": "http_error", "message": "provider request failed"}
                    break
                    
            self.logger.info(f"Google Scholar (Serper): Found {len(articles)} articles")
                
        except Exception as e:
            self.last_failure = self._failure_from_exception(e)
        finally:
            conn.close()
                

            
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
    JOURNALS_URL = "https://api.clarivate.com/apis/wos-journals/v1"
    
    def __init__(self, config: Config):
        super().__init__(config)
        self.api_key = config.api.clarivate_api_key
        self.journal_api_key = config.api.clarivate_journals_api_key or self.api_key
        
    @property
    def source_name(self) -> str:
        return "Web of Science"
    
    @property
    def is_available(self) -> bool:
        return bool(self.api_key)

    @property
    def is_journal_catalog_available(self) -> bool:
        return bool(self.journal_api_key)

    def journal_categories(self, query: str = "", limit: int = 50) -> List[Dict[str, Any]]:
        if not self.is_journal_catalog_available:
            self.last_failure = {"code": "not_configured", "message": "Clarivate Journals API key not configured"}
            return []
        params: Dict[str, Any] = {"limit": min(max(limit, 1), 50), "page": 1}
        if query.strip():
            params["q"] = query.strip()
        data = self._make_request(
            f"{self.JOURNALS_URL}/categories",
            params,
            headers={"X-ApiKey": str(self.journal_api_key)},
        )
        return [
            {
                "id": str(item.get("id")),
                "label": item.get("name") or str(item.get("id")),
                "provider": "web-of-science",
                "edition": item.get("edition"),
            }
            for item in (data or {}).get("hits", [])
            if item.get("id")
        ]

    def journal_catalog(
        self, query: str = "", category_id: Optional[str] = None, limit: int = 25, page: int = 1
    ) -> List[Dict[str, Any]]:
        self.last_total = None
        if not self.is_journal_catalog_available:
            self.last_failure = {"code": "not_configured", "message": "Clarivate Journals API key not configured"}
            return []
        params: Dict[str, Any] = {"limit": min(max(limit, 1), 50), "page": max(page, 1)}
        if query.strip():
            params["q"] = query.strip()
        if category_id:
            params["categoryCode"] = category_id
        data = self._make_request(
            f"{self.JOURNALS_URL}/journals",
            params,
            headers={"X-ApiKey": str(self.journal_api_key)},
        )
        self.last_total = ((data or {}).get("metadata") or {}).get("total")
        return [
            self._catalog_journal(item, detailed=False)
            for item in (data or {}).get("hits", [])
            if item.get("id") and item.get("name")
        ]

    def resolve_journal(self, journal_id: str) -> Optional[Dict[str, Any]]:
        if not self.is_journal_catalog_available:
            self.last_failure = {"code": "not_configured", "message": "Clarivate Journals API key not configured"}
            return None
        safe_id = str(journal_id).strip()
        if not re.fullmatch(r"[A-Za-z0-9_-]+", safe_id):
            self.last_failure = {"code": "invalid_journal_id", "message": "invalid Clarivate journal identifier"}
            return None
        data = self._make_request(
            f"{self.JOURNALS_URL}/journals/{safe_id}",
            {},
            headers={"X-ApiKey": str(self.journal_api_key)},
        )
        return self._catalog_journal(data, detailed=True) if data else None

    def _catalog_journal(self, item: Dict[str, Any], detailed: bool) -> Dict[str, Any]:
        journal_id = str(item.get("id"))
        issn = item.get("issn")
        e_issn = item.get("eIssn")
        issns = list(dict.fromkeys(str(value) for value in (issn, e_issn) if value))
        publisher = item.get("publisher") or {}
        if not isinstance(publisher, dict):
            publisher = {"name": str(publisher)}
        category_value = item.get("categories") or []
        if isinstance(category_value, dict):
            category_value = [category_value]
        categories = [
            {
                "id": str(category.get("url") or category.get("id") or "").rsplit("/", 1)[-1],
                "label": category.get("name") or "Unknown category",
                "edition": category.get("edition"),
            }
            for category in category_value
            if isinstance(category, dict)
        ]
        return {
            "id": journal_id,
            "catalog_id": f"web-of-science:{journal_id}",
            "catalog_provider": "web-of-science",
            "provider_id": journal_id,
            "display_name": item.get("name") or journal_id,
            "issn_l": str(issn or e_issn or "") or None,
            "issns": issns,
            "publisher": publisher.get("name") or "",
            "works_count": 0,
            "is_oa": bool(item.get("openAccess")),
            "is_in_doaj": False,
            "type": "journal",
            "source": "Web of Science Journals API",
            "categories": categories,
            "identifiers": {
                "web_of_science": journal_id,
                "issn_l": str(issn or e_issn or "") or None,
                "issns": issns,
            },
            "search_supported": False,
            "source_url": "",
            "details_loaded": detailed,
        }
    
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
            
        self.clear_last_failure()
        if max_results <= 0:
            return SearchResult(query=query)
        articles = []
        total = 0
        page_size = min(max_results, 50)
        headers = {"X-ApiKey": self.api_key}
        params = {
            "q": self._build_query(query, year_min, year_max),
            "limit": page_size, "db": database, "detail": detail, "sortField": self._get_sort_field(sort_by),
        }
        for page in range(1, (max_results + page_size - 1) // page_size + 1):
            data = self._make_request(self.SEARCH_URL, {**params, "page": page}, headers)
            if data is None:
                break
            hits, meta = data.get("hits"), data.get("metadata")
            if not isinstance(hits, list) or not isinstance(meta, dict):
                self._invalid_response()
                break
            try:
                total = int(meta["total"])
            except (KeyError, TypeError, ValueError):
                self._invalid_response()
                break
            articles.extend(article for hit in hits if (article := self._parse_hit(hit)))
            if not hits or page * page_size >= total or len(articles) >= max_results:
                break
        return SearchResult(query=query, articles=articles[:max_results], total_found=total,
                            sources=[self.source_name] if articles else [])

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
        The Starter API expects ``TAG DIRECTION`` (for example ``PY D``),
        not the older ``TAG+D`` notation.
        """
        sort_map = {
            'relevance': 'RS D',
            'citations': 'TC D',
            'year_desc': 'PY D',
            'year_asc': 'PY A',
            'newest': 'PY D',
            'oldest': 'PY A',
            'most_cited': 'TC D'
        }
        return sort_map.get(sort_by.lower(), 'RS D')
    
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


class PubMedSearcher(BaseSearcher):
    """
    Search provider for PubMed (NCBI E-utilities API).
    Provides medical and life sciences literature.
    """
    
    @property
    def source_name(self) -> str:
        return "PubMed"
        
    @property
    def is_available(self) -> bool:
        return True

    def search_recent(self, query, max_results, year_min, year_max):
        return self.search(query, max_results, year_min, year_max, sort_by="pub_date")
        
    def search(
        self, query: str, max_results: int = 25, year_min: Optional[int] = None,
        year_max: Optional[int] = None, sort_by: str = "relevance",
    ) -> SearchResult:
        self.clear_last_failure()
        if not query.strip() or max_results <= 0:
            return SearchResult(query=query)
        started = time.monotonic()
        base = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils"
        requested = min(max_results, 10_000)
        params = {"db": "pubmed", "term": query, "retmax": requested, "retmode": "json", "sort": sort_by}
        if year_min or year_max:
            params.update(datetype="pdat", mindate=f"{year_min or 1800}/01/01", maxdate=f"{year_max or 2200}/12/31")
        data = self._make_request(f"{base}/esearch.fcgi", params)
        if data is None:
            return SearchResult(query=query)
        result = data.get("esearchresult")
        if not isinstance(result, dict) or not isinstance(result.get("idlist"), list):
            self._invalid_response()
            return SearchResult(query=query)
        ids = list(dict.fromkeys(uid for uid in result["idlist"] if isinstance(uid, str) and uid.isascii() and uid.isdigit()))
        try:
            total = int(result["count"])
        except (TypeError, KeyError, ValueError):
            self._invalid_response()
            return SearchResult(query=query)
        if not ids:
            if total != 0 or result["idlist"]:
                self._invalid_response()
            return SearchResult(query=query, total_found=total, search_time=time.monotonic() - started)

        summary = self._make_request(
            f"{base}/esummary.fcgi", {"db": "pubmed", "id": ",".join(ids), "retmode": "json"}, post=len(ids) > 200,
        )
        if summary is None:
            return SearchResult(query=query, total_found=total)
        records = summary.get("result")
        if not isinstance(records, dict):
            self._invalid_response()
            return SearchResult(query=query, total_found=total)
        articles = []
        # The ESummary response may return the IDs in a different order than ESearch.
        for uid in ids:
            item = records.get(uid)
            if not isinstance(item, dict) or not item.get("title"):
                continue
            authors = ", ".join(a["name"] for a in (item.get("authors") or []) if isinstance(a, dict) and a.get("name"))
            year = str(item.get("pubdate") or "")[:4]
            doi = next((a.get("value") for a in (item.get("articleids") or [])
                        if isinstance(a, dict) and a.get("idtype") == "doi"), None)
            articles.append(Article(
                title=item["title"], authors=authors or None, year=year if year.isdigit() else None,
                journal=item.get("fulljournalname") or item.get("source"), url=f"https://pubmed.ncbi.nlm.nih.gov/{uid}/",
                doi=doi, source=self.source_name, raw_data=item,
            ))
        if len(articles) < len(ids):
            self.last_failure = {"code": "incomplete_response", "message": "some PubMed summaries were missing"}
        return SearchResult(query=query, articles=articles, total_found=total,
                            sources=[self.source_name] if articles else [], search_time=time.monotonic() - started)


class CoreSearcher(BaseSearcher):
    """
    Search provider for CORE (core.ac.uk) API.
    Provides access to millions of open access research papers.
    """
    
    @property
    def source_name(self) -> str:
        return "CORE"
        
    @property
    def is_available(self) -> bool:
        return True
        
    def search(
        self, query: str, max_results: int = 25, year_min: Optional[int] = None,
        year_max: Optional[int] = None, sort_by: str = "relevance",
    ) -> SearchResult:
        self.clear_last_failure()
        if not query.strip() or max_results <= 0:
            return SearchResult(query=query)
        started = time.monotonic()
        terms = [f"({query})"]
        if year_min is not None:
            terms.append(f"yearPublished>={year_min}")
        if year_max is not None:
            terms.append(f"yearPublished<={year_max}")
        core_query = " AND ".join(terms) if len(terms) > 1 else query
        key = self.config.api.core_api_key
        headers = {"Authorization": f"Bearer {key}"} if key else None
        offset, total = 0, 0
        articles = []
        while offset < max_results:
            data = self._make_request("https://api.core.ac.uk/v3/search/works", {
                "q": core_query, "limit": min(max_results - offset, 100), "offset": offset,
            }, headers)
            if data is None:
                break
            rows, total_hits = data.get("results"), data.get("totalHits")
            if not isinstance(rows, list) or not isinstance(total_hits, int):
                self._invalid_response()
                break
            total = total_hits
            for item in rows:
                if not isinstance(item, dict) or not item.get("title"):
                    continue
                authors = ", ".join(a["name"] for a in (item.get("authors") or []) if isinstance(a, dict) and a.get("name"))
                links = item.get("sourceFulltextUrls") or []
                source_url = next((link for link in links if isinstance(link, str) and link), "")
                download = item.get("downloadUrl")
                identifier = item.get("id")
                articles.append(Article(
                    title=item["title"], abstract=item.get("abstract"), authors=authors or None,
                    year=str(item["yearPublished"]) if item.get("yearPublished") else None,
                    url=download or source_url or (f"https://core.ac.uk/works/{identifier}" if identifier else ""),
                    doi=item.get("doi"), source=self.source_name, is_open_access=bool(download or source_url), raw_data=item,
                ))
            offset += len(rows)
            if not rows or offset >= total:
                break
        return SearchResult(query=query, articles=articles[:max_results], total_found=total,
                            sources=[self.source_name] if articles else [], search_time=time.monotonic() - started)
