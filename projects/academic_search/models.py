"""
Data models for Academic Search.

This module defines the core data structures used throughout the package.
"""

from copy import deepcopy
from dataclasses import dataclass, field, asdict
from typing import List, Optional, Dict, Any
from datetime import datetime
from enum import Enum


class ArticleSource(Enum):
    """Enumeration of supported article sources."""
    SCOPUS = "scopus"
    SCIENCEDIRECT = "sciencedirect"
    OPENALEX = "openalex"
    CROSSREF = "crossref"
    SEMANTIC_SCHOLAR = "semantic_scholar"
    PUBMED = "pubmed"
    ARXIV = "arxiv"
    IEEE = "ieee"
    UNKNOWN = "unknown"


PROVIDER_OUTCOME_STATUSES = {
    "requested", "responded", "empty", "unavailable", "rate_limited", "failed",
}


@dataclass
class ProviderOutcome:
    """A safe, machine-readable account of one provider attempt.

    ``message`` is intentionally a short classification, never a raw exception or
    response body, so result manifests can be shared without leaking credentials or
    provider internals.
    """

    provider: str
    status: str
    requested: bool = True
    returned_count: int = 0
    total_found: int = 0
    error_code: Optional[str] = None
    message: Optional[str] = None

    def __post_init__(self) -> None:
        if self.status not in PROVIDER_OUTCOME_STATUSES:
            raise ValueError(f"Unsupported provider outcome status: {self.status}")

    def to_dict(self) -> Dict[str, Any]:
        return {
            "provider": self.provider,
            "status": self.status,
            "requested": self.requested,
            "returned_count": self.returned_count,
            "total_found": self.total_found,
            "error_code": self.error_code,
            "message": self.message,
        }


@dataclass
class Author:
    """Represents an article author."""
    name: str
    affiliation: Optional[str] = None
    orcid: Optional[str] = None
    
    def __str__(self) -> str:
        return self.name


@dataclass
class Article:
    """
    Represents a single academic article.
    
    This is the core data model for search results. It contains all
    metadata about an article including title, abstract, authors, etc.
    
    Attributes:
        title: Article title
        url: URL to access the article
        doi: Digital Object Identifier (if available)
        abstract: Article abstract text
        authors: List of author names or Author objects
        journal: Journal/publication name
        year: Publication year
        keywords: List of keywords/tags
        source: Source database where article was found
        is_open_access: Whether article is open access
        citation_count: Number of citations (if available)
        references: List of reference DOIs (if available)
        raw_data: Original raw data from the API (for debugging)
        
    Example:
        >>> article = Article(
        ...     title="Renewable Energy Storage",
        ...     url="https://doi.org/10.1000/example",
        ...     doi="10.1000/example",
        ...     abstract="This paper discusses..."
        ... )
    """
    title: str
    url: str
    doi: Optional[str] = None
    abstract: Optional[str] = None
    authors: Optional[str] = None  # Comma-separated string for simplicity
    journal: Optional[str] = None
    year: Optional[str] = None
    keywords: List[str] = field(default_factory=list)
    source: str = "unknown"
    is_open_access: bool = False
    citation_count: Optional[int] = None
    references: List[str] = field(default_factory=list)
    raw_data: Optional[Dict[str, Any]] = field(default=None, repr=False)

    # Provider records are retained independently of mutable display fields.  The
    # original abstract is never overwritten when enrichment supplies a replacement.
    original_abstract: Optional[str] = field(default=None, init=False, repr=False)
    _original_record: Optional[Dict[str, Any]] = field(default=None, init=False, repr=False)
    _provider_records: List[Dict[str, Any]] = field(default_factory=list, init=False, repr=False)
    field_provenance: Dict[str, List[Dict[str, str]]] = field(default_factory=dict)
    derived_outputs: List[Dict[str, Any]] = field(default_factory=list, repr=False)
    
    # Analysis results (populated by analyzers)
    analysis: Optional[Dict[str, Any]] = field(default=None, repr=False)
    
    # Internal flags
    _enriched: bool = field(default=False, repr=False)
    
    def __post_init__(self):
        """Normalize data after initialization."""
        # Ensure year is string
        if self.year and not isinstance(self.year, str):
            self.year = str(self.year)
        
        # Clean abstract whitespace
        if self.abstract:
            self.abstract = ' '.join(self.abstract.split())
        self.original_abstract = self.abstract
        # Never expose the provider response in normal exports; retain a defensive
        # copy for audit/debug use so later normalization/enrichment cannot mutate it.
        self._original_record = deepcopy(self.raw_data) if self.raw_data is not None else None
        self._provider_records.append({"source": self.source, "record": deepcopy(self.raw_data)})
        for name in ("title", "url", "doi", "abstract", "authors", "journal", "year", "keywords",
                     "is_open_access", "citation_count", "references"):
            if getattr(self, name) not in (None, "", []):
                self.field_provenance.setdefault(name, []).append({
                    "source": self.source,
                    "method": "provider_record",
                })

    def set_enriched_abstract(self, abstract: str, source: str) -> None:
        """Attach an enriched abstract without losing the provider-supplied value."""
        normalized = " ".join(abstract.split())
        if not normalized:
            return
        self.abstract = normalized
        self._enriched = True
        self.field_provenance.setdefault("abstract", []).append({
            "source": source,
            "method": "enrichment",
        })

    @property
    def original_record(self) -> Optional[Dict[str, Any]]:
        """Return a copy of the immutable provider snapshot, never a live record."""
        return deepcopy(self._original_record)

    @property
    def provider_records(self) -> List[Dict[str, Any]]:
        """Return independent provider snapshots retained across deduplication."""
        return deepcopy(self._provider_records)

    def add_provider_record(self, article: "Article") -> None:
        """Retain a duplicate provider observation without replacing source fields."""
        self._provider_records.extend(article.provider_records)
        for field_name, entries in article.field_provenance.items():
            current = self.field_provenance.setdefault(field_name, [])
            for entry in entries:
                if entry not in current:
                    current.append(deepcopy(entry))

    def add_derived_output(self, output: Dict[str, Any]) -> None:
        """Store model/topic output separately from provider metadata."""
        self.derived_outputs.append(deepcopy(output))
    
    @property
    def has_abstract(self) -> bool:
        """Check if article has an abstract."""
        return bool(self.abstract and len(self.abstract) > 50)
    
    @property
    def is_sciencedirect(self) -> bool:
        """Check if article is from ScienceDirect."""
        return (
            'sciencedirect' in self.source.lower() or
            'sciencedirect.com' in (self.url or '').lower() or
            'elsevier' in (self.journal or '').lower()
        )
    
    def matches_query(self, query: str) -> bool:
        """
        Check if article matches query terms in Title, Abstract, or Keywords.
        
        Args:
            query: Search query string.
            
        Returns:
            True if all significant query terms are found.
        """
        if not query:
            return True
            
        # Normalize text
        text = f"{self.title} {self.abstract or ''} {' '.join(self.keywords)}".lower()
        
        # Simple term extraction (remove special chars)
        import re
        # Split terms and removing trailing 's' for simple plural matching
        raw_terms = [t.lower() for t in re.split(r'\s+', query) if len(t) > 2]
        terms = []
        for t in raw_terms:
            if t.endswith('s') and len(t) > 3:
                terms.append(t[:-1])
                # Keep original too? No, matching base is safer.
                # Actually, check if base is in text.
            else:
                terms.append(t)
        
        if not terms:
            return True
            
        # Check if ALL terms are present in Title specifically (high relevance)
        title_lower = self.title.lower()
        if all(term in title_lower for term in terms):
            return True

        # Otherwise, check if MOST words are present in combined text (Title + Abstract)
        # We perform a "soft match" where at least 70% of terms must be present
        # This prevents filtering out good results just because 1 word is missing in abstract
        matching_terms = sum(1 for term in terms if term in text)
        match_ratio = matching_terms / len(terms)
        
        return match_ratio >= 0.7
    
    @property
    def title_normalized(self) -> str:
        """Get normalized title for deduplication."""
        import re
        return re.sub(r"[^a-z0-9]+", " ", (self.title or "").lower()).strip()
    
    @property
    def doi_normalized(self) -> str:
        """Get normalized DOI for deduplication."""
        if not self.doi:
            return ""
        return self.doi.lower().replace("https://doi.org/", "").strip()
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert article to dictionary, excluding internal fields."""
        data = asdict(self)
        # Remove internal fields
        data.pop('_enriched', None)
        data.pop('raw_data', None)
        data.pop('_original_record', None)
        data.pop('_provider_records', None)
        return data
    
    def to_bibtex(self) -> str:
        """Export article as BibTeX entry."""
        # Generate citation key
        first_author = self.authors.split(',')[0].split()[-1] if self.authors else "unknown"
        key = f"{first_author.lower()}{self.year or 'nd'}"
        
        lines = [f"@article{{{key},"]
        lines.append(f'  title = {{{self.title}}},')
        if self.authors:
            lines.append(f'  author = {{{self.authors}}},')
        if self.journal:
            lines.append(f'  journal = {{{self.journal}}},')
        if self.year:
            lines.append(f'  year = {{{self.year}}},')
        if self.doi:
            lines.append(f'  doi = {{{self.doi}}},')
        if self.url:
            lines.append(f'  url = {{{self.url}}},')
        if self.abstract:
            # Escape special characters in abstract
            abstract = self.abstract.replace('{', '\\{').replace('}', '\\}')
            lines.append(f'  abstract = {{{abstract[:500]}}},')
        lines.append("}")
        
        return '\n'.join(lines)


@dataclass
class SearchResult:
    """
    Container for search results.
    
    Holds the list of articles along with metadata about the search.
    
    Attributes:
        query: The search query string
        articles: List of Article objects
        total_found: Total number of results (across all sources)
        sources: List of sources that were searched
        search_time: Time taken for the search
        topics: Extracted topics/keywords with scores
    """
    query: str
    articles: List[Article] = field(default_factory=list)
    total_found: int = 0
    sources: List[str] = field(default_factory=list)
    search_time: Optional[float] = None
    topics: List[tuple] = field(default_factory=list)
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())
    requested_providers: List[str] = field(default_factory=list)
    provider_outcomes: List[ProviderOutcome] = field(default_factory=list)
    year_min: Optional[int] = None
    year_max: Optional[int] = None
    limit: Optional[int] = None
    deduplication_version: str = "doi-or-title-author-year-v1"
    raw_article_count: int = 0
    deduplicated_article_count: int = 0
    derived_outputs: List[Dict[str, Any]] = field(default_factory=list)
    
    @property
    def count(self) -> int:
        """Number of articles in results."""
        return len(self.articles)
    
    @property
    def with_abstracts(self) -> int:
        """Number of articles with abstracts."""
        return sum(1 for a in self.articles if a.has_abstract)
    
    @property
    def sciencedirect_count(self) -> int:
        """Number of ScienceDirect articles."""
        return sum(1 for a in self.articles if a.is_sciencedirect)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert search result to dictionary."""
        return {
            "query": self.query,
            "articles": [a.to_dict() for a in self.articles],
            "summary": {
                "total_found": self.total_found,
                "returned": self.count,
                "with_abstracts": self.with_abstracts,
                "sciencedirect_count": self.sciencedirect_count,
                "sources": self.sources,
            },
            "topics": [{"topic": t, "score": s} for t, s in self.topics],
            "timestamp": self.timestamp,
            "search_time": self.search_time,
            "manifest": self.manifest(),
        }

    def manifest(self) -> Dict[str, Any]:
        """Return the reproducibility record shared by exports and the project ledger."""
        return {
            "query": self.query,
            "providers_requested": self.requested_providers or self.sources,
            "provider_outcomes": [outcome.to_dict() for outcome in self.provider_outcomes],
            "year_min": self.year_min,
            "year_max": self.year_max,
            "limit": self.limit,
            "retrieved_at": self.timestamp,
            "search_time": self.search_time,
            "total_provider_matches": self.total_found,
            "returned_count": self.count,
            "raw_article_count": self.raw_article_count or self.count,
            "deduplicated_article_count": self.deduplicated_article_count or self.count,
            "pagination": {"per_provider_limit": self.limit},
            "deduplication_version": self.deduplication_version,
        }
    
    def filter_by_year(self, min_year: int, max_year: Optional[int] = None) -> "SearchResult":
        """Filter results by publication year range."""
        filtered = []
        for article in self.articles:
            if article.year:
                try:
                    year = int(article.year[:4])
                    if year >= min_year:
                        if max_year is None or year <= max_year:
                            filtered.append(article)
                except ValueError:
                    continue
        
        return SearchResult(
            query=self.query,
            articles=filtered,
            total_found=len(filtered),
            sources=self.sources,
            topics=self.topics,
            requested_providers=self.requested_providers,
            provider_outcomes=self.provider_outcomes,
            year_min=min_year,
            year_max=max_year,
            limit=self.limit,
            deduplication_version=self.deduplication_version,
            derived_outputs=self.derived_outputs,
            raw_article_count=self.raw_article_count,
            deduplicated_article_count=self.deduplicated_article_count,
        )
    
    def filter_with_abstracts(self) -> "SearchResult":
        """Filter to only articles with abstracts."""
        filtered = [a for a in self.articles if a.has_abstract]
        return SearchResult(
            query=self.query,
            articles=filtered,
            total_found=len(filtered),
            sources=self.sources,
            topics=self.topics,
            requested_providers=self.requested_providers,
            provider_outcomes=self.provider_outcomes,
            year_min=self.year_min,
            year_max=self.year_max,
            limit=self.limit,
            deduplication_version=self.deduplication_version,
            derived_outputs=self.derived_outputs,
            raw_article_count=self.raw_article_count,
            deduplicated_article_count=self.deduplicated_article_count,
        )
