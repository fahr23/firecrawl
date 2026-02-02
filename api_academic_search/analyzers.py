"""
Article analyzers for extracting insights.

This module contains analyzers that process articles to extract
topics, summaries, and other derived information.

The LLMAnalyzer class provides the extension point for adding
LLM-based abstract analysis.
"""

import re
from typing import List, Dict, Any, Optional, Callable
from collections import Counter
from abc import ABC

from .base import BaseAnalyzer
from .models import Article, SearchResult
from .config import Config


class TopicExtractor(BaseAnalyzer):
    """
    Extract common topics and keywords from articles.
    
    Uses keyword extraction from titles, abstracts, and existing keywords.
    """
    
    # Common stop words to exclude
    STOP_WORDS = {
        'with', 'from', 'that', 'this', 'have', 'been', 'were', 'their',
        'which', 'these', 'would', 'could', 'should', 'about', 'after',
        'before', 'through', 'during', 'between', 'under', 'over', 'into',
        'such', 'than', 'also', 'more', 'most', 'other', 'some', 'only',
        'both', 'each', 'being', 'based', 'using', 'paper', 'study',
        'results', 'shows', 'shown', 'found', 'used', 'article', 'research'
    }
    
    def __init__(self, config: Config):
        super().__init__(config)
        self.min_word_length = 4
    
    @property
    def analyzer_name(self) -> str:
        return "TopicExtractor"
    
    def analyze(self, article: Article) -> Dict[str, Any]:
        """Extract topics from a single article."""
        topics = Counter()
        
        # From keywords
        for kw in article.keywords:
            topics[kw.lower()] += 2.0
        
        # From title
        if article.title:
            words = self._extract_words(article.title)
            for word in words:
                topics[word] += 1.0
        
        # From abstract
        if article.abstract:
            words = self._extract_words(article.abstract)
            for word in words:
                topics[word] += 0.3
        
        return {"topics": topics.most_common(10)}
    
    def extract_from_results(self, result: SearchResult) -> List[tuple]:
        """
        Extract topics from all articles in a search result.
        
        Args:
            result: SearchResult object containing articles.
            
        Returns:
            List of (topic, score) tuples sorted by score.
        """
        combined = Counter()
        
        for article in result.articles:
            analysis = self.analyze(article)
            for topic, score in analysis["topics"]:
                combined[topic] += score
        
        return combined.most_common(25)
    
    def _extract_words(self, text: str) -> List[str]:
        """Extract meaningful words from text."""
        words = re.findall(r'\b[a-zA-Z]{%d,}\b' % self.min_word_length, text.lower())
        return [w for w in words if w not in self.STOP_WORDS]


class LLMAnalyzer(BaseAnalyzer):
    """
    LLM-based article analyzer.
    
    This is the extension point for adding AI-powered abstract analysis.
    Supports multiple LLM providers (OpenAI, Anthropic, local models).
    
    Example usage:
        >>> config = Config(
        ...     llm_provider="openai",
        ...     llm_api_key="sk-...",
        ...     enable_llm_analysis=True
        ... )
        >>> analyzer = LLMAnalyzer(config)
        >>> result = analyzer.analyze(article)
        >>> print(result["summary"])
    
    To implement a custom LLM provider:
        >>> class MyLLMAnalyzer(LLMAnalyzer):
        ...     def _get_completion(self, prompt: str) -> str:
        ...         return my_llm_client.complete(prompt)
    """
    
    # Default prompts for different analysis types
    PROMPTS = {
        "summary": """Summarize the following academic abstract in 2-3 sentences, 
focusing on the main findings and contributions:

Abstract: {abstract}

Summary:""",
        
        "key_findings": """Extract the key findings from this academic abstract as a bullet list:

Abstract: {abstract}

Key Findings:""",
        
        "methodology": """Identify the methodology or approach used in this research:

Abstract: {abstract}

Methodology:""",
        
        "relevance": """Rate the relevance of this paper to the topic "{query}" on a scale of 1-10 
and explain briefly:

Title: {title}
Abstract: {abstract}

Relevance (1-10):""",
        
        "research_gaps": """Identify potential research gaps or future work suggested by this abstract:

Abstract: {abstract}

Research Gaps:"""
    }
    
    def __init__(self, config: Config, analysis_types: Optional[List[str]] = None):
        """
        Initialize the LLM analyzer.
        
        Args:
            config: Configuration with LLM settings.
            analysis_types: List of analysis types to perform. 
                           Options: "summary", "key_findings", "methodology", 
                                    "relevance", "research_gaps"
        """
        super().__init__(config)
        self.analysis_types = analysis_types or ["summary", "key_findings"]
        self._client = None
    
    @property
    def analyzer_name(self) -> str:
        return f"LLM ({self.config.llm_provider or 'not configured'})"
    
    @property
    def is_available(self) -> bool:
        """Check if LLM analysis is available."""
        return (
            self.config.enable_llm_analysis and
            self.config.llm_provider is not None and
            self.config.llm_api_key is not None
        )
    
    def analyze(self, article: Article, query: Optional[str] = None) -> Dict[str, Any]:
        """
        Analyze an article using LLM.
        
        Args:
            article: Article to analyze.
            query: Optional search query for relevance analysis.
            
        Returns:
            Dictionary containing analysis results for each type.
        """
        if not self.is_available:
            return {"error": "LLM analysis not configured"}
        
        if not article.abstract:
            return {"error": "No abstract available for analysis"}
        
        results = {}
        
        for analysis_type in self.analysis_types:
            if analysis_type in self.PROMPTS:
                prompt = self.PROMPTS[analysis_type].format(
                    abstract=article.abstract,
                    title=article.title,
                    query=query or ""
                )
                
                try:
                    response = self._get_completion(prompt)
                    results[analysis_type] = response.strip()
                except Exception as e:
                    self.logger.error(f"LLM error for {analysis_type}: {e}")
                    results[analysis_type] = f"Error: {e}"
        
        return results
    
    def _get_completion(self, prompt: str) -> str:
        """
        Get completion from the configured LLM provider.
        
        Override this method to implement custom LLM providers.
        
        Args:
            prompt: The prompt to send to the LLM.
            
        Returns:
            The LLM's response text.
        """
        provider = self.config.llm_provider
        
        if provider == "openai":
            return self._openai_completion(prompt)
        elif provider == "anthropic":
            return self._anthropic_completion(prompt)
        elif provider == "local":
            return self._local_completion(prompt)
        else:
            raise ValueError(f"Unknown LLM provider: {provider}")
    
    def _openai_completion(self, prompt: str) -> str:
        """Get completion from OpenAI API."""
        try:
            import openai
            
            if self._client is None:
                self._client = openai.OpenAI(api_key=self.config.llm_api_key)
            
            response = self._client.chat.completions.create(
                model=self.config.llm_model,
                messages=[
                    {"role": "system", "content": "You are a helpful research assistant."},
                    {"role": "user", "content": prompt}
                ],
                max_tokens=500,
                temperature=0.3
            )
            
            return response.choices[0].message.content
            
        except ImportError:
            raise ImportError("openai package not installed. Run: pip install openai")
    
    def _anthropic_completion(self, prompt: str) -> str:
        """Get completion from Anthropic API."""
        try:
            import anthropic
            
            if self._client is None:
                self._client = anthropic.Anthropic(api_key=self.config.llm_api_key)
            
            response = self._client.messages.create(
                model=self.config.llm_model or "claude-3-sonnet-20240229",
                max_tokens=500,
                messages=[
                    {"role": "user", "content": prompt}
                ]
            )
            
            return response.content[0].text
            
        except ImportError:
            raise ImportError("anthropic package not installed. Run: pip install anthropic")
    
    def _local_completion(self, prompt: str) -> str:
        """
        Get completion from a local LLM.
        
        This is a placeholder for local model integration.
        Override this method to implement your local LLM.
        """
        raise NotImplementedError(
            "Local LLM not implemented. Override _local_completion() method."
        )
    
    def analyze_batch(self, articles: List[Article], 
                      query: Optional[str] = None) -> List[Dict[str, Any]]:
        """
        Analyze multiple articles.
        
        Args:
            articles: List of articles to analyze.
            query: Optional search query for relevance analysis.
            
        Returns:
            List of analysis results.
        """
        results = []
        for i, article in enumerate(articles):
            self.logger.info(f"Analyzing article {i+1}/{len(articles)}")
            result = self.analyze(article, query)
            results.append(result)
        return results


class CompositeAnalyzer(BaseAnalyzer):
    """
    Combines multiple analyzers into one.
    
    Useful for running multiple analysis types on each article.
    
    Example:
        >>> analyzer = CompositeAnalyzer(config, [
        ...     TopicExtractor(config),
        ...     LLMAnalyzer(config)
        ... ])
        >>> results = analyzer.analyze(article)
    """
    
    def __init__(self, config: Config, analyzers: List[BaseAnalyzer]):
        super().__init__(config)
        self.analyzers = analyzers
    
    @property
    def analyzer_name(self) -> str:
        names = [a.analyzer_name for a in self.analyzers]
        return f"Composite({', '.join(names)})"
    
    def analyze(self, article: Article) -> Dict[str, Any]:
        """Run all analyzers on the article."""
        combined = {}
        for analyzer in self.analyzers:
            try:
                result = analyzer.analyze(article)
                combined[analyzer.analyzer_name] = result
            except Exception as e:
                self.logger.error(f"{analyzer.analyzer_name} failed: {e}")
                combined[analyzer.analyzer_name] = {"error": str(e)}
        return combined
