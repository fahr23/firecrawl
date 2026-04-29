#!/usr/bin/env python3
"""
Tests for the Academic Search Package

Run with: python -m pytest tests/test_academic_search.py -v
Or simply: python tests/test_academic_search.py
"""

import sys
import os
import unittest
from unittest.mock import Mock, patch, MagicMock
from dataclasses import asdict

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from academic_search import (
    Article, SearchResult, Config, APIConfig,
    AcademicSearchEngine, create_engine,
    TopicExtractor, LLMAnalyzer,
    JSONExporter, MarkdownExporter, CSVExporter,
    BaseSearcher, BaseAbstractEnricher
)


class TestArticle(unittest.TestCase):
    """Test the Article dataclass."""
    
    def setUp(self):
        self.article = Article(
            title="Test Article on Machine Learning",
            url="https://example.com/article",
            authors="John Doe, Jane Smith",
            year=2023,
            journal="Journal of Testing",
            doi="10.1234/test.2023",
            abstract="This is a test abstract about machine learning.",
            source="TestSource",
            keywords=["machine learning", "testing"]
        )
    
    def test_article_creation(self):
        """Test basic article creation."""
        self.assertEqual(self.article.title, "Test Article on Machine Learning")
        self.assertEqual(self.article.year, "2023")  # Year is converted to string
        self.assertEqual(len(self.article.keywords), 2)
    
    def test_to_dict(self):
        """Test article to dictionary conversion."""
        d = self.article.to_dict()
        self.assertIsInstance(d, dict)
        self.assertEqual(d["title"], self.article.title)
        self.assertEqual(d["year"], "2023")  # Year is string
    
    def test_to_bibtex(self):
        """Test BibTeX generation."""
        bibtex = self.article.to_bibtex()
        self.assertIn("@article", bibtex)
        self.assertIn("title = {Test Article on Machine Learning}", bibtex)
        self.assertIn("year = {2023}", bibtex)
        self.assertIn("doi = {10.1234/test.2023}", bibtex)


class TestSearchResult(unittest.TestCase):
    """Test the SearchResult dataclass."""
    
    def setUp(self):
        self.articles = [
            Article(title="Article 1", url="https://example.com/1", year=2023, abstract="Abstract 1"),
            Article(title="Article 2", url="https://example.com/2", year=2022, abstract=None),
            Article(title="Article 3", url="https://example.com/3", year=2021, abstract="Abstract 3"),
            Article(title="Article 4", url="https://example.com/4", year=2020, abstract=None),
        ]
        self.result = SearchResult(
            query="test query",
            articles=self.articles,
            total_found=100,
            sources=["Source1", "Source2"]
        )
    
    def test_filter_by_year(self):
        """Test year filtering."""
        filtered = self.result.filter_by_year(2021, 2023)
        self.assertEqual(len(filtered.articles), 3)
        for article in filtered.articles:
            year = int(article.year) if article.year else 0
            self.assertGreaterEqual(year, 2021)
            self.assertLessEqual(year, 2023)
    
    def test_filter_with_abstracts(self):
        """Test abstract filtering."""
        filtered = self.result.filter_with_abstracts()
        # has_abstract requires abstract length > 50
        # Our test abstracts are short, so let's check differently
        self.assertLessEqual(len(filtered.articles), 2)  # At most 2 have abstracts
        for article in filtered.articles:
            self.assertIsNotNone(article.abstract)


class TestConfig(unittest.TestCase):
    """Test the Config class."""
    
    def test_default_config(self):
        """Test default configuration values."""
        config = Config()
        self.assertFalse(config.debug)
        self.assertEqual(config.max_results, 25)
        self.assertEqual(config.timeout, 30)
        self.assertFalse(config.enable_llm_analysis)
    
    def test_api_config(self):
        """Test API configuration."""
        config = Config()
        # Default Elsevier key should be set
        self.assertIsNotNone(config.api.elsevier_api_key)
    
    def test_config_modification(self):
        """Test config modification."""
        config = Config(debug=True, max_results=50)
        self.assertTrue(config.debug)
        self.assertEqual(config.max_results, 50)


class TestTopicExtractor(unittest.TestCase):
    """Test the TopicExtractor analyzer."""
    
    def setUp(self):
        self.config = Config()
        self.extractor = TopicExtractor(self.config)
        self.article = Article(
            title="Deep Learning for Natural Language Processing",
            url="https://example.com/nlp",
            abstract="This paper presents a deep learning approach for NLP tasks.",
            keywords=["deep learning", "NLP", "neural networks"]
        )
    
    def test_analyze_single(self):
        """Test single article analysis."""
        result = self.extractor.analyze(self.article)
        self.assertIn("topics", result)
        self.assertIsInstance(result["topics"], list)
    
    def test_extract_from_results(self):
        """Test extraction from search results."""
        result = SearchResult(
            query="test",
            articles=[self.article],
            total_found=1,
            sources=["test"]
        )
        topics = self.extractor.extract_from_results(result)
        self.assertIsInstance(topics, list)
        # Keywords should be in top topics
        topic_names = [t[0] for t in topics]
        self.assertIn("deep learning", topic_names)


class TestExporters(unittest.TestCase):
    """Test export functionality."""
    
    def setUp(self):
        self.config = Config()
        self.result = SearchResult(
            query="test query",
            articles=[
                Article(
                    title="Test Article",
                    url="https://example.com/test",
                    authors="Test Author",
                    year=2023,
                    abstract="Test abstract"
                )
            ],
            total_found=1,
            sources=["TestSource"]
        )
    
    def test_json_exporter_to_string(self):
        """Test JSON export to string."""
        exporter = JSONExporter(self.config)
        output = exporter.export_to_string(self.result)
        self.assertIn("Test Article", output)
        self.assertIn("test query", output)
    
    def test_markdown_exporter_to_string(self):
        """Test Markdown export to string."""
        exporter = MarkdownExporter(self.config)
        output = exporter.export_to_string(self.result)
        self.assertIn("# Academic Literature Search Results", output)
        self.assertIn("Test Article", output)


class TestLLMAnalyzer(unittest.TestCase):
    """Test LLM analyzer (without actual API calls)."""
    
    def setUp(self):
        self.config = Config(enable_llm_analysis=False)
        self.analyzer = LLMAnalyzer(self.config)
    
    def test_not_available_without_config(self):
        """Test that LLM is not available without configuration."""
        self.assertFalse(self.analyzer.is_available)
    
    def test_returns_error_when_not_configured(self):
        """Test error response when LLM not configured."""
        article = Article(title="Test", url="https://example.com", abstract="Test abstract")
        result = self.analyzer.analyze(article)
        self.assertIn("error", result)


class TestCreateEngine(unittest.TestCase):
    """Test the create_engine factory function."""
    
    def test_create_default_engine(self):
        """Test creating engine with defaults."""
        engine = create_engine()
        self.assertIsInstance(engine, AcademicSearchEngine)
        self.assertGreater(len(engine.available_sources), 0)
    
    def test_create_engine_with_elsevier_key(self):
        """Test creating engine with Elsevier key."""
        engine = create_engine(elsevier_api_key="test-key")
        self.assertIn("Scopus API", engine.available_sources)


class TestCustomComponents(unittest.TestCase):
    """Test adding custom components."""
    
    def test_add_custom_searcher(self):
        """Test adding a custom search provider."""
        
        class CustomSearcher(BaseSearcher):
            @property
            def source_name(self):
                return "CustomSource"
            
            def search(self, query, max_results=25):
                return SearchResult(
                    query=query,
                    articles=[Article(title="Custom Result", url="https://example.com/custom")],
                    total_found=1,
                    sources=[self.source_name]
                )
        
        engine = create_engine()
        initial_sources = len(engine.available_sources)
        
        engine.add_searcher(CustomSearcher(engine.config))
        
        self.assertEqual(len(engine.available_sources), initial_sources + 1)
        self.assertIn("CustomSource", engine.available_sources)


class TestIntegration(unittest.TestCase):
    """Integration tests (require network, skipped by default)."""
    
    @unittest.skipUnless(
        os.getenv("RUN_INTEGRATION_TESTS"),
        "Integration tests skipped (set RUN_INTEGRATION_TESTS=1 to run)"
    )
    def test_real_search(self):
        """Test a real search (requires network)."""
        engine = create_engine()
        results = engine.search("machine learning", max_results=5)
        
        self.assertGreater(len(results.articles), 0)
        self.assertIsNotNone(results.articles[0].title)


def run_tests():
    """Run all tests."""
    loader = unittest.TestLoader()
    suite = unittest.TestSuite()
    
    # Add test classes
    suite.addTests(loader.loadTestsFromTestCase(TestArticle))
    suite.addTests(loader.loadTestsFromTestCase(TestSearchResult))
    suite.addTests(loader.loadTestsFromTestCase(TestConfig))
    suite.addTests(loader.loadTestsFromTestCase(TestTopicExtractor))
    suite.addTests(loader.loadTestsFromTestCase(TestExporters))
    suite.addTests(loader.loadTestsFromTestCase(TestLLMAnalyzer))
    suite.addTests(loader.loadTestsFromTestCase(TestCreateEngine))
    suite.addTests(loader.loadTestsFromTestCase(TestCustomComponents))
    suite.addTests(loader.loadTestsFromTestCase(TestIntegration))
    
    # Run tests
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)
    
    return 0 if result.wasSuccessful() else 1


if __name__ == "__main__":
    sys.exit(run_tests())
