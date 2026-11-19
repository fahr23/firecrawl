"""
Abstract base classes for data sources.

This module defines the interfaces that all data source providers must implement.
This allows for easy extension with new sources.
"""

from abc import ABC, abstractmethod
from typing import List, Optional, Dict, Any
import logging
from threading import local

import requests

from .models import Article, SearchResult
from .config import Config


class ProviderRequestState:
    """Keep diagnostics for cached adapters local to the request's worker thread."""

    def __init__(self) -> None:
        self._request_state = local()

    @property
    def last_failure(self) -> Optional[Dict[str, str]]:
        return getattr(self._request_state, "failure", None)

    @last_failure.setter
    def last_failure(self, value: Optional[Dict[str, str]]) -> None:
        self._request_state.failure = value

    @property
    def last_total(self) -> Optional[int]:
        return getattr(self._request_state, "total", None)

    @last_total.setter
    def last_total(self, value: Optional[int]) -> None:
        self._request_state.total = value

    def clear_last_failure(self) -> None:
        self.last_failure = None


class BaseSearcher(ProviderRequestState, ABC):
    """
    Abstract base class for all search providers.
    
    To add a new search source:
    1. Create a new class that inherits from BaseSearcher
    2. Implement the required abstract methods
    3. Register it with the AcademicSearchEngine
    
    Example:
        >>> class MyNewSearcher(BaseSearcher):
        ...     def search(self, query: str, max_results: int = 25) -> SearchResult:
        ...         # Implementation here
        ...         pass
        ...     
        ...     @property
        ...     def source_name(self) -> str:
        ...         return "my_source"
    """
    
    def __init__(self, config: Config):
        """
        Initialize the searcher with configuration.
        
        Args:
            config: Configuration object with API keys and settings.
        """
        super().__init__()
        self.config = config
        self.logger = logging.getLogger(self.__class__.__name__)

    @staticmethod
    def _failure_from_exception(exc: Exception) -> Dict[str, str]:
        """Classify a provider exception so it is not reported as an empty result."""
        status = getattr(getattr(exc, "response", None), "status_code", None)
        if status == 429:
            return {"code": "rate_limited", "message": "provider rate limit reached"}
        if status in (401, 403):
            return {"code": "authentication", "message": "authentication failed"}
        if isinstance(exc, requests.exceptions.Timeout):
            return {"code": "timeout", "message": "provider request timed out"}
        return {"code": "request_error", "message": "provider request failed"}
    
    @abstractmethod
    def search(self, query: str, max_results: int = 25, year_min: Optional[int] = None, year_max: Optional[int] = None) -> SearchResult:
        """
        Search for articles matching the query.
        
        Args:
            query: Search query string.
            max_results: Maximum number of results to return.
            year_min: Minimum publication year (optional).
            year_max: Maximum publication year (optional).
            
        Returns:
            SearchResult object containing matching articles.
        """
        pass
    
    @property
    @abstractmethod
    def source_name(self) -> str:
        """Return the name of this search source."""
        pass
    
    @property
    def is_available(self) -> bool:
        """
        Check if this searcher is available (has required credentials, etc.).
        
        Override this method if your searcher requires specific setup.
        """
        return True
    
    def _make_request(self, url: str, params: Dict[str, Any], 
                      headers: Optional[Dict[str, str]] = None, *, post: bool = False) -> Optional[Dict]:
        """
        Make an HTTP request with error handling.
        
        Args:
            url: Request URL
            params: Query parameters
            headers: Optional headers
            
        Returns:
            JSON response data or None if request failed.
        """
        try:
            if post:
                response = requests.post(url, data=params, headers=headers, timeout=self.config.timeout)
            else:
                response = requests.get(url, params=params, headers=headers, timeout=self.config.timeout)
        except requests.exceptions.RequestException as exc:
            self.last_failure = self._failure_from_exception(exc)
            return None
        if response.status_code != 200:
            self.last_failure = self._failure_from_exception(requests.HTTPError(response=response))
            if self.last_failure["code"] == "request_error":
                self.last_failure["code"] = "http_error"
            self.logger.warning("%s: HTTP %s", self.source_name, response.status_code)
            return None
        try:
            data = response.json()
        except ValueError:
            data = None
        if not isinstance(data, dict):
            self._invalid_response()
            return None
        return data

    def _invalid_response(self) -> None:
        self.last_failure = {"code": "invalid_response", "message": "invalid provider response"}


class BaseAbstractEnricher(ABC):
    """
    Abstract base class for abstract enrichment providers.
    
    Enrichers fetch abstracts for articles that don't have them.
    """
    
    def __init__(self, config: Config):
        self.config = config
        self.logger = logging.getLogger(self.__class__.__name__)
    
    @abstractmethod
    def get_abstract(self, article: Article) -> Optional[str]:
        """
        Try to fetch the abstract for an article.
        
        Args:
            article: Article object to enrich.
            
        Returns:
            Abstract text if found, None otherwise.
        """
        pass
    
    @property
    @abstractmethod
    def source_name(self) -> str:
        """Return the name of this enricher source."""
        pass


class BaseAnalyzer(ABC):
    """
    Abstract base class for article analyzers.
    
    Analyzers process articles to extract insights, summaries, or other
    derived information. This is the extension point for LLM-based analysis.
    
    Example implementation for LLM analysis:
        >>> class LLMAbstractAnalyzer(BaseAnalyzer):
        ...     def analyze(self, article: Article) -> Dict[str, Any]:
        ...         prompt = f"Analyze this abstract: {article.abstract}"
        ...         result = self.llm_client.complete(prompt)
        ...         return {"summary": result, "key_findings": [...]}
    """
    
    def __init__(self, config: Config):
        self.config = config
        self.logger = logging.getLogger(self.__class__.__name__)
    
    @abstractmethod
    def analyze(self, article: Article) -> Dict[str, Any]:
        """
        Analyze a single article.
        
        Args:
            article: Article to analyze.
            
        Returns:
            Dictionary containing analysis results.
        """
        pass
    
    def analyze_batch(self, articles: List[Article]) -> List[Dict[str, Any]]:
        """
        Analyze multiple articles.
        
        Override this method for more efficient batch processing.
        
        Args:
            articles: List of articles to analyze.
            
        Returns:
            List of analysis results.
        """
        return [self.analyze(article) for article in articles]
    
    @property
    @abstractmethod
    def analyzer_name(self) -> str:
        """Return the name of this analyzer."""
        pass


class BaseExporter(ABC):
    """
    Abstract base class for result exporters.
    
    Exporters convert SearchResult objects to various output formats.
    """
    
    def __init__(self, config: Config):
        self.config = config
        self.logger = logging.getLogger(self.__class__.__name__)
    
    @abstractmethod
    def export(self, result: "SearchResult", filepath: str) -> str:
        """
        Export search results to a file.
        
        Args:
            result: SearchResult object to export.
            filepath: Output file path.
            
        Returns:
            Path to the created file.
        """
        pass
    
    @property
    @abstractmethod
    def format_name(self) -> str:
        """Return the format name (e.g., 'json', 'markdown')."""
        pass
    
    @property
    @abstractmethod
    def file_extension(self) -> str:
        """Return the file extension for this format."""
        pass
    
    def _ensure_extension(self, filepath: str) -> str:
        """Ensure the filepath has the correct extension."""
        if not filepath.endswith(f'.{self.file_extension}'):
            filepath = f'{filepath}.{self.file_extension}'
        return filepath
