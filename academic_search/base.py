"""
Abstract base classes for data sources.

This module defines the interfaces that all data source providers must implement.
This allows for easy extension with new sources.
"""

from abc import ABC, abstractmethod
from typing import List, Optional, Dict, Any
import logging

from .models import Article, SearchResult
from .config import Config


class BaseSearcher(ABC):
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
        self.config = config
        self.logger = logging.getLogger(self.__class__.__name__)
    
    @abstractmethod
    def search(self, query: str, max_results: int = 25) -> SearchResult:
        """
        Search for articles matching the query.
        
        Args:
            query: Search query string.
            max_results: Maximum number of results to return.
            
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
                      headers: Optional[Dict[str, str]] = None) -> Optional[Dict]:
        """
        Make an HTTP request with error handling.
        
        Args:
            url: Request URL
            params: Query parameters
            headers: Optional headers
            
        Returns:
            JSON response data or None if request failed.
        """
        import requests
        
        try:
            response = requests.get(
                url, 
                params=params, 
                headers=headers,
                timeout=self.config.timeout
            )
            
            if response.status_code == 200:
                return response.json()
            elif response.status_code == 401:
                self.logger.warning(f"{self.source_name}: Authentication failed")
            elif response.status_code == 429:
                self.logger.warning(f"{self.source_name}: Rate limited")
            else:
                self.logger.warning(
                    f"{self.source_name}: Request failed with status {response.status_code}"
                )
                
        except requests.exceptions.Timeout:
            self.logger.warning(f"{self.source_name}: Request timeout")
        except requests.exceptions.RequestException as e:
            self.logger.warning(f"{self.source_name}: Request error - {e}")
        
        return None


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
