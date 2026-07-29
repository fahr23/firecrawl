"""
Main search engine orchestrator.

This module provides the AcademicSearchEngine class which coordinates
all search providers, enrichers, analyzers, and exporters.
"""

import logging
import re
from typing import List, Dict, Any, Optional, Type
from concurrent.futures import ThreadPoolExecutor, as_completed

from .base import BaseSearcher, BaseAbstractEnricher, BaseAnalyzer, BaseExporter
from .models import Article, ProviderOutcome, SearchResult
from .config import Config
from .providers import (
    ScienceDirectSearcher, ScopusSearcher, OpenAlexSearcher, SemanticScholarSearcher, ArXivSearcher,
    GoogleScholarSearcher, ClarivateSearcher, FirecrawlResearchSearcher,
    CrossRefEnricher, SemanticScholarEnricher, ScopusEnricher
)
from .exporters import JSONExporter, MarkdownExporter, CSVExporter, BibTeXExporter, RISExporter
from .analyzers import TopicExtractor, LLMAnalyzer


class AcademicSearchEngine:
    """
    Main search engine that orchestrates all components.
    
    This is the primary interface for searching academic literature.
    It coordinates multiple search providers, enriches results with
    abstracts, and can analyze and export results.
    
    Example:
        >>> config = Config()
        >>> engine = AcademicSearchEngine(config)
        >>> results = engine.search("machine learning healthcare")
        >>> engine.export(results, "results.json")
    
    For LLM analysis:
        >>> config = Config(
        ...     enable_llm_analysis=True,
        ...     llm_provider="openai",
        ...     llm_api_key="sk-..."
        ... )
        >>> engine = AcademicSearchEngine(config)
        >>> results = engine.search("deep learning")
        >>> analysis = engine.analyze(results)
    """
    
    def __init__(self, config: Optional[Config] = None):
        """
        Initialize the search engine.
        
        Args:
            config: Configuration object. If None, uses default config.
        """
        self.config = config or Config()
        self.logger = logging.getLogger(__name__)
        
        # Set up logging
        if not self.logger.handlers:
            handler = logging.StreamHandler()
            handler.setFormatter(logging.Formatter(
                '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
            ))
            self.logger.addHandler(handler)
            self.logger.setLevel(
                logging.DEBUG if self.config.debug else logging.INFO
            )
        
        # Initialize components
        self._searchers: List[BaseSearcher] = []
        self._enrichers: List[BaseAbstractEnricher] = []
        self._analyzers: List[BaseAnalyzer] = []
        self._exporters: Dict[str, BaseExporter] = {}
        
        # Set up default components
        self._setup_default_components()
    
    def _setup_default_components(self):
        """Set up default searchers, enrichers, and exporters."""
        # Elsevier searchers (requires API key)
        if self.config.enable_elsevier and self.config.api.elsevier_api_key:
            self._searchers.append(ScienceDirectSearcher(self.config))  # Best for Elsevier content
            self._searchers.append(ScopusSearcher(self.config))         # Broad multi-publisher search
        
        # Clarivate
        if self.config.enable_clarivate and self.config.api.clarivate_api_key:
            self._searchers.append(ClarivateSearcher(self.config))
        
        # Free searchers (no API key needed)
        self._searchers.append(OpenAlexSearcher(self.config))
        self._searchers.append(SemanticScholarSearcher(self.config))
        self._searchers.append(ArXivSearcher(self.config))

        # Optional supplemental discovery. Self-hosted Firecrawl only serves this
        # API when its external RESEARCH_PROXY_URL is configured.
        if self.config.enable_firecrawl_research:
            self._searchers.append(FirecrawlResearchSearcher(self.config))
        
        # Google Scholar is backed by Serper; Firecrawl Research is a separate provider.
        if self.config.enable_serper and self.config.api.serper_api_key:
            self._searchers.append(GoogleScholarSearcher(self.config))
        
        # Enrichers for adding abstracts
        self._enrichers.extend([
            SemanticScholarEnricher(self.config),
            CrossRefEnricher(self.config)
        ])
        
        # Add Scopus enricher if we have the API key
        if self.config.enable_elsevier and self.config.api.elsevier_api_key:
            self._enrichers.append(ScopusEnricher(self.config))
        
        # Analyzers
        self._analyzers.append(TopicExtractor(self.config))
        
        if self.config.enable_llm_analysis:
            self._analyzers.append(LLMAnalyzer(self.config))
        
        # Exporters
        self._exporters = {
            'json': JSONExporter(self.config),
            'markdown': MarkdownExporter(self.config),
            'md': MarkdownExporter(self.config),
            'csv': CSVExporter(self.config),
            'bibtex': BibTeXExporter(self.config),
            'bib': BibTeXExporter(self.config),
            'ris': RISExporter(self.config),
        }
    
    # ========== Search Methods ==========
    
    def search(self, query: str, max_results: int = 25,
               use_all_sources: bool = False,
               year_min: Optional[int] = None,
               year_max: Optional[int] = None,
               providers: Optional[List[str]] = None) -> SearchResult:
        """
        Search for academic papers.
        
        Args:
            query: Search query string.
            max_results: Maximum number of results to return.
            use_all_sources: If True, queries all sources and merges results.
                           If False, uses first available source.
            year_min: Minimum publication year (optional).
            year_max: Maximum publication year (optional).
            providers: List of specific provider names to use (case-insensitive).
                       If None, uses all configured providers.
        
        Returns:
            SearchResult containing found articles.
        """
        self.logger.info(f"Searching for: '{query}'")
        if year_min or year_max:
            year_range = f" ({year_min or 'any'} - {year_max or 'now'})"
            self.logger.info(f"Year filter: {year_range}")
        
        # Determine active searchers. Provider names are retained even when a
        # requested optional provider is not configured, so callers can see that
        # lack of coverage rather than mistaking it for an empty search.
        active_searchers = self._searchers
        requested_names = list(providers or [])
        if providers:
            # Normalize names
            provider_names = [p.lower() for p in providers]
            active_searchers = [
                s for s in self._searchers 
                if any(p in s.source_name.lower() or s.source_name.lower() in p for p in provider_names)
            ]
            
            if not active_searchers:
                self.logger.warning(f"No matching providers found for: {providers}")
                return SearchResult(
                    query=query,
                    requested_providers=requested_names,
                    provider_outcomes=[
                        ProviderOutcome(name, "unavailable", error_code="not_configured",
                                        message="provider is not configured")
                        for name in requested_names
                    ],
                    year_min=year_min,
                    year_max=year_max,
                    limit=max_results,
                )
        
        if use_all_sources or providers: # If specific providers requested, imply use_all_sources behavior usually? 
            # The prompt says "if not given do it all if given use them". 
            # So if providers are given, we iterate them all (implied 'all' behavior for the subset).
            return self._search_all_sources(
                query, max_results, year_min, year_max, active_searchers, requested_names
            )
        else:
            return self._search_primary_source(
                query, max_results, year_min, year_max, active_searchers, requested_names
            )
    
    def _search_primary_source(self, query: str, max_results: int, year_min: Optional[int] = None,
                               year_max: Optional[int] = None, searchers: List[BaseSearcher] = None,
                               requested_names: Optional[List[str]] = None) -> SearchResult:
        """Search using the first available source."""
        searchers = searchers or self._searchers
        outcomes: List[ProviderOutcome] = []
        for searcher in searchers:
            if not searcher.is_available:
                outcomes.append(ProviderOutcome(searcher.source_name, "unavailable", error_code="not_configured",
                                                message="provider is not configured"))
                continue
            try:
                searcher.clear_last_failure()
                self.logger.info(f"Trying {searcher.source_name}...")
                result = searcher.search(query, max_results, year_min, year_max)
                
                if result.articles:
                    self.logger.info(
                        f"Found {result.total_found:,} results from {searcher.source_name}"
                    )
                    result.requested_providers = requested_names or [searcher.source_name]
                    result.provider_outcomes = outcomes + [ProviderOutcome(
                        searcher.source_name, "responded", returned_count=len(result.articles),
                        total_found=result.total_found,
                    )]
                    result.year_min, result.year_max, result.limit = year_min, year_max, max_results
                    result.raw_article_count = result.count
                    result.deduplicated_article_count = result.count
                    return result
                else:
                    self.logger.warning(f"No results from {searcher.source_name}")
                    outcomes.append(self._outcome_from_failure(searcher.source_name, searcher.last_failure))
                    
            except Exception as e:
                self.logger.error(f"Error with {searcher.source_name}: {e}")
                outcomes.append(self._outcome_from_exception(searcher.source_name, e))
                continue
        
        # Return empty result if all sources fail
        return SearchResult(
            query=query,
            articles=[],
            total_found=0,
            sources=[],
            requested_providers=requested_names or [s.source_name for s in searchers],
            provider_outcomes=outcomes,
            year_min=year_min,
            year_max=year_max,
            limit=max_results,
        )
    
    def _search_all_sources(self, query: str, max_results: int, year_min: Optional[int] = None,
                            year_max: Optional[int] = None, searchers: List[BaseSearcher] = None,
                            requested_names: Optional[List[str]] = None) -> SearchResult:
        """Search all sources and merge results."""
        searchers = searchers or self._searchers
        all_articles = []
        total = 0
        raw_article_count = 0
        sources = []
        seen_keys: Dict[str, Article] = {}
        outcomes: List[ProviderOutcome] = []
        
        for searcher in searchers:
            if not searcher.is_available:
                outcomes.append(ProviderOutcome(searcher.source_name, "unavailable", error_code="not_configured",
                                                message="provider is not configured"))
                continue
            try:
                searcher.clear_last_failure()
                self.logger.info(f"Searching {searcher.source_name}...")
                result = searcher.search(query, max_results, year_min, year_max)
                total += result.total_found
                raw_article_count += len(result.articles)
                if result.articles:
                    sources.append(searcher.source_name)
                    outcomes.append(ProviderOutcome(searcher.source_name, "responded", len(result.articles) > 0,
                                                    len(result.articles), result.total_found))
                else:
                    outcomes.append(self._outcome_from_failure(searcher.source_name, searcher.last_failure))

                for article in result.articles:
                    key = self._deduplication_key(article)
                    if key in seen_keys:
                        seen_keys[key].add_provider_record(article)
                        continue
                    seen_keys[key] = article
                    all_articles.append(article)
                    
            except Exception as e:
                self.logger.error(f"Error with {searcher.source_name}: {e}")
                outcomes.append(self._outcome_from_exception(searcher.source_name, e))
        
        # Sort by year (newest first)
        all_articles.sort(key=lambda a: int(a.year) if a.year and str(a.year).isdigit() else 0, reverse=True)
        deduplicated_article_count = len(all_articles)
        all_articles = all_articles[:max_results]
        
        return SearchResult(
            query=query,
            articles=all_articles,
            total_found=total,
            sources=sources,
            requested_providers=requested_names or [s.source_name for s in searchers],
            provider_outcomes=outcomes,
            year_min=year_min,
            year_max=year_max,
            limit=max_results,
            raw_article_count=raw_article_count,
            deduplicated_article_count=deduplicated_article_count,
        )

    @staticmethod
    def _deduplication_key(article: Article) -> str:
        """Prefer DOI; otherwise only merge strong title/year/first-author matches."""
        if article.doi_normalized:
            return f"doi:{article.doi_normalized}"
        title = article.title_normalized
        if len(title) < 20:
            return f"unique:{id(article)}"
        first_author = re.sub(r"[^a-z0-9]", "", (article.authors or "").split(",")[0].lower())
        return f"title:{title}|year:{article.year or ''}|author:{first_author}"

    @staticmethod
    def _outcome_from_failure(provider: str, failure: Optional[Dict[str, str]]) -> ProviderOutcome:
        if not failure:
            return ProviderOutcome(provider, "empty")
        status = "rate_limited" if failure.get("code") == "rate_limited" else "failed"
        return ProviderOutcome(provider, status, error_code=failure.get("code"), message=failure.get("message"))

    @staticmethod
    def _outcome_from_exception(provider: str, exc: Exception) -> ProviderOutcome:
        code = "timeout" if "timeout" in type(exc).__name__.lower() else "provider_error"
        return ProviderOutcome(provider, "failed", error_code=code, message="provider search failed")
    
    # ========== Enrichment Methods ==========
    
    def enrich_abstracts(self, result: SearchResult,
                         parallel: bool = True) -> SearchResult:
        """
        Enrich articles with abstracts from multiple sources.
        
        Args:
            result: SearchResult to enrich.
            parallel: Use parallel processing for faster enrichment.
        
        Returns:
            Enriched SearchResult (modified in place).
        """
        articles_without_abstract = [
            a for a in result.articles if not a.abstract
        ]
        
        if not articles_without_abstract:
            self.logger.info("All articles already have abstracts")
            return result
        
        self.logger.info(
            f"Enriching {len(articles_without_abstract)} articles without abstracts..."
        )
        
        if parallel:
            self._enrich_parallel(articles_without_abstract)
        else:
            self._enrich_sequential(articles_without_abstract)
        
        # Log results
        with_abstract = sum(1 for a in result.articles if a.abstract)
        self.logger.info(f"After enrichment: {with_abstract}/{len(result.articles)} have abstracts")
        
        return result
    
    def _enrich_sequential(self, articles: List[Article]):
        """Enrich articles sequentially."""
        for article in articles:
            if article.abstract:
                continue
            
            for enricher in self._enrichers:
                try:
                    abstract = enricher.get_abstract(article)
                    if abstract:
                        article.set_enriched_abstract(abstract, enricher.source_name)
                        self.logger.debug(
                            f"Got abstract from {enricher.source_name}"
                        )
                        break
                except Exception as e:
                    self.logger.error(
                        f"Enrichment error ({enricher.source_name}): {e}"
                    )
    
    def _enrich_parallel(self, articles: List[Article]):
        """Enrich articles in parallel."""
        with ThreadPoolExecutor(max_workers=5) as executor:
            futures = {
                executor.submit(self._enrich_single, article): article
                for article in articles
            }
            
            for future in as_completed(futures):
                try:
                    future.result()
                except Exception as e:
                    self.logger.error(f"Parallel enrichment error: {e}")
    
    def _enrich_single(self, article: Article):
        """Enrich a single article (for parallel processing)."""
        if article.abstract:
            return
        
        for enricher in self._enrichers:
            try:
                abstract = enricher.get_abstract(article)
                if abstract:
                    article.set_enriched_abstract(abstract, enricher.source_name)
                    return
            except Exception:
                continue
    
    # ========== Analysis Methods ==========
    
    def analyze(self, result: SearchResult,
                analyzer_type: Optional[str] = None) -> Dict[str, Any]:
        """
        Analyze search results.
        
        Args:
            result: SearchResult to analyze.
            analyzer_type: Type of analyzer to use ("topics", "llm").
                          If None, uses all available analyzers.
        
        Returns:
            Dictionary containing analysis results.
        """
        analysis = {}
        
        analyzers = self._get_analyzers(analyzer_type)
        
        for analyzer in analyzers:
            self.logger.info(f"Running {analyzer.analyzer_name}...")
            
            try:
                if isinstance(analyzer, TopicExtractor):
                    analysis["topics"] = analyzer.extract_from_results(result)
                    result.derived_outputs.append({
                        "kind": "topics",
                        "analyzer": analyzer.analyzer_name,
                        "version": "keyword-extractor-v1",
                        "output": analysis["topics"],
                    })
                elif isinstance(analyzer, LLMAnalyzer):
                    if analyzer.is_available:
                        analysis["llm"] = analyzer.analyze_batch(result.articles[:10], result.query)
                        for article, output in zip(result.articles[:10], analysis["llm"]):
                            article.add_derived_output({
                                "kind": "llm_analysis",
                                "analyzer": analyzer.analyzer_name,
                                "provider": self.config.llm_provider,
                                "model": self.config.llm_model,
                                "prompt_version": "llm-analyzer-prompts-v1",
                                "output": output,
                            })
                    else:
                        analysis["llm"] = {"status": "not configured"}
                else:
                    # Generic analyzer
                    analysis[analyzer.analyzer_name] = [
                        analyzer.analyze(a) for a in result.articles
                    ]
            except Exception as e:
                self.logger.error(f"Analysis error ({analyzer.analyzer_name}): {e}")
                analysis[analyzer.analyzer_name] = {"error": str(e)}
        
        return analysis
    
    def _get_analyzers(self, analyzer_type: Optional[str]) -> List[BaseAnalyzer]:
        """Get analyzers based on type."""
        if analyzer_type is None:
            return self._analyzers
        
        type_map = {
            "topics": TopicExtractor,
            "topic": TopicExtractor,
            "llm": LLMAnalyzer,
            "ai": LLMAnalyzer
        }
        
        target_type = type_map.get(analyzer_type.lower())
        if target_type:
            return [a for a in self._analyzers if isinstance(a, target_type)]
        
        return self._analyzers
    
    def extract_topics(self, result: SearchResult, top_n: int = 25) -> List[tuple]:
        """
        Extract top topics from search results.
        
        Convenience method for topic extraction.
        
        Args:
            result: SearchResult to analyze.
            top_n: Number of top topics to return.
        
        Returns:
            List of (topic, score) tuples.
        """
        extractor = TopicExtractor(self.config)
        topics = extractor.extract_from_results(result)
        return topics[:top_n]
    
    # ========== Export Methods ==========
    
    def export(self, result: SearchResult, filepath: str,
               format: Optional[str] = None) -> str:
        """
        Export search results to file.
        
        Args:
            result: SearchResult to export.
            filepath: Output file path.
            format: Export format ('json', 'markdown', 'csv', 'bibtex').
                   If None, infers from file extension.
        
        Returns:
            Path to the created file.
        """
        if format is None:
            # Infer from extension
            ext = filepath.rsplit('.', 1)[-1].lower() if '.' in filepath else 'json'
            format = ext
        
        exporter = self._exporters.get(format.lower())
        if not exporter:
            available = ', '.join(self._exporters.keys())
            raise ValueError(f"Unknown format '{format}'. Available: {available}")
        
        return exporter.export(result, filepath)
    
    def export_to_string(self, result: SearchResult, format: str = 'json') -> str:
        """
        Export search results to string.
        
        Args:
            result: SearchResult to export.
            format: Export format.
        
        Returns:
            Formatted string.
        """
        exporter = self._exporters.get(format.lower())
        if not exporter:
            raise ValueError(f"Unknown format: {format}")
        
        if hasattr(exporter, 'export_to_string'):
            return exporter.export_to_string(result)
        else:
            raise NotImplementedError(f"{format} exporter doesn't support string export")
    
    # ========== Component Management ==========
    
    def add_searcher(self, searcher: BaseSearcher, priority: int = -1):
        """
        Add a custom search provider.
        
        Args:
            searcher: Searcher instance to add.
            priority: Position in searcher list (-1 = end).
        """
        if priority < 0:
            self._searchers.append(searcher)
        else:
            self._searchers.insert(priority, searcher)
        self.logger.info(f"Added searcher: {searcher.source_name}")
    
    def add_enricher(self, enricher: BaseAbstractEnricher):
        """Add a custom abstract enricher."""
        self._enrichers.append(enricher)
        self.logger.info(f"Added enricher: {enricher.source_name}")
    
    def add_analyzer(self, analyzer: BaseAnalyzer):
        """Add a custom analyzer."""
        self._analyzers.append(analyzer)
        self.logger.info(f"Added analyzer: {analyzer.analyzer_name}")
    
    def add_exporter(self, name: str, exporter: BaseExporter):
        """Add a custom exporter."""
        self._exporters[name.lower()] = exporter
        self.logger.info(f"Added exporter: {name}")
    
    @property
    def available_sources(self) -> List[str]:
        """List available search sources."""
        return [s.source_name for s in self._searchers]
    
    @property
    def available_exporters(self) -> List[str]:
        """List available export formats."""
        return list(set(self._exporters.keys()))
    
    # ========== Convenience Methods ==========
    
    def search_and_export(self, query: str, output_path: str,
                          max_results: int = 25,
                          enrich: bool = True,
                          year_min: Optional[int] = None,
                          year_max: Optional[int] = None) -> SearchResult:
        """
        Search, optionally enrich, and export in one call.
        
        Args:
            query: Search query.
            output_path: Output file path.
            max_results: Maximum results.
            enrich: Whether to enrich abstracts.
            year_min: Minimum publication year.
            year_max: Maximum publication year.
        
        Returns:
            SearchResult.
        """
        result = self.search(query, max_results, year_min=year_min, year_max=year_max)
        
        if enrich:
            result = self.enrich_abstracts(result)
        
        self.export(result, output_path)
        
        return result
    
    def quick_search(self, query: str, max_results: int = 10) -> List[Dict]:
        """
        Quick search returning simple dictionary results.
        
        Convenience method for simple use cases.
        
        Args:
            query: Search query.
            max_results: Maximum results.
        
        Returns:
            List of article dictionaries.
        """
        result = self.search(query, max_results)
        return [a.to_dict() for a in result.articles]


def create_engine(elsevier_api_key: Optional[str] = None,
                  clarivate_api_key: Optional[str] = None,
                  enable_llm: bool = False,
                  llm_provider: Optional[str] = None,
                  llm_api_key: Optional[str] = None,
                  debug: bool = False,
                  enable_firecrawl_research: bool = False,
                  firecrawl_api_key: Optional[str] = None,
                  firecrawl_api_url: Optional[str] = None) -> AcademicSearchEngine:
    """
    Factory function to create a configured search engine.
    
    This is a convenience function for quick setup.
    
    Args:
        elsevier_api_key: Elsevier/Scopus API key.
        enable_firecrawl_research: Enable the optional supplemental provider.
        firecrawl_api_key: Firecrawl credential, when required by the endpoint.
        firecrawl_api_url: Firecrawl base URL; Compose uses ``http://api:3002``.
        enable_llm: Enable LLM-based analysis.
        llm_provider: LLM provider ("openai", "anthropic").
        llm_api_key: LLM API key.
        debug: Enable debug logging.
    
    Returns:
        Configured AcademicSearchEngine instance.
    
    Example:
        >>> engine = create_engine(
        ...     elsevier_api_key="your-key",
        ...     enable_llm=True,
        ...     llm_provider="openai",
        ...     llm_api_key="sk-..."
        ... )
        >>> results = engine.search("quantum computing")
    """
    config = Config(
        debug=debug,
        enable_firecrawl_research=enable_firecrawl_research,
        enable_llm_analysis=enable_llm,
        llm_provider=llm_provider,
        llm_api_key=llm_api_key
    )
    
    if elsevier_api_key:
        config.api.elsevier_api_key = elsevier_api_key
        config.enable_elsevier = True
        
    if clarivate_api_key:
        config.api.clarivate_api_key = clarivate_api_key
        config.enable_clarivate = True

    if firecrawl_api_key:
        config.api.firecrawl_api_key = firecrawl_api_key

    if firecrawl_api_url:
        config.api.firecrawl_api_url = firecrawl_api_url
    
    return AcademicSearchEngine(config)
