"""
Academic Literature Search Package
==================================

A modular, extensible toolkit for searching academic literature across multiple databases
including ScienceDirect, Scopus, OpenAlex, CrossRef, and Semantic Scholar.

Features:
- Multi-source academic literature search
- Abstract extraction and enrichment
- Topic/keyword extraction
- Extensible architecture for adding new data sources and analyzers
- Support for LLM-based abstract analysis (pluggable)

Quick Start:
    >>> from academic_search import create_engine
    >>> engine = create_engine()
    >>> results = engine.search("machine learning healthcare")
    >>> engine.export(results, "results.json")

With Elsevier API key:
    >>> from academic_search import create_engine
    >>> engine = create_engine(elsevier_api_key="your-api-key")
    >>> results = engine.search("quantum computing")

With LLM analysis:
    >>> from academic_search import create_engine
    >>> engine = create_engine(
    ...     enable_llm=True,
    ...     llm_provider="openai",
    ...     llm_api_key="sk-..."
    ... )
    >>> results = engine.search("deep learning")
    >>> analysis = engine.analyze(results)
"""

from .models import Article, SearchResult
from .config import Config, APIConfig
from .engine import AcademicSearchEngine, create_engine
from .exporters import JSONExporter, MarkdownExporter, CSVExporter, BibTeXExporter, RISExporter
from .analyzers import TopicExtractor, LLMAnalyzer, CompositeAnalyzer
from .providers import (
    ScienceDirectSearcher, ScopusSearcher, OpenAlexSearcher, SemanticScholarSearcher, ArXivSearcher,
    GoogleScholarSearcher, ClarivateSearcher,
    CrossRefEnricher, SemanticScholarEnricher, ScopusEnricher
)
from .base import BaseSearcher, BaseAbstractEnricher, BaseAnalyzer, BaseExporter

__version__ = "1.0.0"
__author__ = "Academic Search Team"

__all__ = [
    # Main interface
    "AcademicSearchEngine",
    "create_engine",
    
    # Configuration
    "Config",
    "APIConfig",
    
    # Models
    "Article",
    "SearchResult",
    
    # Search providers
    "ScienceDirectSearcher",
    "ScopusSearcher",
    "OpenAlexSearcher",
    "SemanticScholarSearcher",
    "ArXivSearcher",
    "GoogleScholarSearcher",
    "ClarivateSearcher",
    
    # Enrichers
    "CrossRefEnricher",
    "SemanticScholarEnricher",
    "ScopusEnricher",
    
    # Analyzers
    "TopicExtractor",
    "LLMAnalyzer",
    "CompositeAnalyzer",
    
    # Exporters
    "JSONExporter",
    "MarkdownExporter",
    "CSVExporter",
    "BibTeXExporter",
    "RISExporter",
    
    # Base classes for extension
    "BaseSearcher",
    "BaseAbstractEnricher",
    "BaseAnalyzer",
    "BaseExporter",
]
