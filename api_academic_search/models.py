"""
Data models for Academic Search.

This module defines the core data structures used throughout the package.
"""

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
        terms = [t.lower() for t in re.split(r'\s+', query) if len(t) > 2]
        
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
        return self.title.lower().strip()[:50] if self.title else ""
    
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
        )
