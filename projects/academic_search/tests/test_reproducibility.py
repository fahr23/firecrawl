"""Offline conformance tests for search outcomes, evidence, and exports."""

from unittest.mock import Mock, patch

import requests

from academic_search import Article, Config, SearchResult
from academic_search.base import BaseSearcher
from academic_search.engine import AcademicSearchEngine
from academic_search.exporters import BibTeXExporter, CSVExporter, JSONExporter, RISExporter


class FixtureSearcher(BaseSearcher):
    def __init__(self, config, name, behavior):
        super().__init__(config)
        self._name = name
        self.behavior = behavior

    @property
    def source_name(self):
        return self._name

    def search(self, query, max_results=25, year_min=None, year_max=None):
        if isinstance(self.behavior, Exception):
            raise self.behavior
        if isinstance(self.behavior, dict):
            self.last_failure = self.behavior
            return SearchResult(query=query, sources=[self.source_name])
        return SearchResult(query=query, articles=self.behavior, total_found=len(self.behavior), sources=[self.source_name])


def fixture_engine(*searchers):
    engine = AcademicSearchEngine(Config())
    engine._searchers = list(searchers)
    return engine


def test_provider_conformance_outcomes_cover_success_empty_and_failures():
    config = Config()
    cases = [
        ("Success", [Article("One reliable paper", "https://example.org/one")], "responded"),
        ("Empty", [], "empty"),
        ("Auth", {"code": "authentication", "message": "authentication failed"}, "failed"),
        ("Rate", {"code": "rate_limited", "message": "provider rate limit reached"}, "rate_limited"),
        ("Timeout", requests.exceptions.Timeout(), "failed"),
        ("Malformed", ValueError("malformed provider response"), "failed"),
    ]
    engine = fixture_engine(*(FixtureSearcher(config, name, behavior) for name, behavior, _ in cases))

    result = engine.search("reliable paper", max_results=10, use_all_sources=True)

    assert [outcome.status for outcome in result.provider_outcomes] == [expected for _, _, expected in cases]
    assert result.provider_outcomes[3].error_code == "rate_limited"
    assert result.provider_outcomes[4].error_code == "timeout"
    assert result.manifest()["deduplication_version"] == "doi-or-title-author-year-v1"


def test_global_limit_and_conservative_deduplication_preserve_distinct_short_titles():
    config = Config()
    first = FixtureSearcher(config, "First", [
        Article("A sufficiently long shared research title", "https://one", authors="Ada Smith", year="2024"),
        Article("AI", "https://short-one", year="2024"),
        Article("Unique study one", "https://unique-one", year="2022"),
    ])
    second = FixtureSearcher(config, "Second", [
        Article("A sufficiently long shared research title", "https://two", authors="Ada Smith", year="2024"),
        Article("AI", "https://short-two", year="2024"),
        Article("Unique study two", "https://unique-two", year="2023"),
    ])

    result = fixture_engine(first, second).search("research", max_results=3, use_all_sources=True)

    assert result.count == 3
    assert [article.title for article in result.articles].count("A sufficiently long shared research title") == 1
    assert [article.title for article in result.articles].count("AI") == 2


def test_abstract_enrichment_preserves_original_record_and_provenance():
    article = Article("Paper", "https://example.org", source="OpenAlex", raw_data={"abstract": None})
    article.set_enriched_abstract("A newly retrieved abstract.", "Crossref")

    assert article.original_abstract is None
    assert article.original_record == {"abstract": None}
    assert article.abstract == "A newly retrieved abstract."
    assert article.field_provenance["abstract"][-1] == {"source": "Crossref", "method": "enrichment"}


def test_base_searcher_records_safe_http_failure_classifications():
    searcher = FixtureSearcher(Config(), "Fixture", [])
    response = Mock(status_code=429)
    with patch("requests.get", return_value=response):
        assert searcher._make_request("https://provider.test", {}) is None
    assert searcher.last_failure == {"code": "rate_limited", "message": "provider rate limit reached"}


def test_exports_are_deterministic_and_bibtex_keys_do_not_collide():
    result = SearchResult(
        query="determinism", timestamp="2026-01-02T03:04:05+00:00",
        articles=[
            Article("One", "https://one", authors="Ada Smith", year="2024"),
            Article("Two", "https://two", authors="Ada Smith", year="2024"),
        ],
        sources=["Fixture"], requested_providers=["Fixture"], limit=2,
    )
    config = Config()

    json_export = JSONExporter(config).export_to_string(result)
    assert json_export == JSONExporter(config).export_to_string(result)
    assert '"manifest"' in json_export
    assert CSVExporter(config).export_to_string(result).startswith("title,authors,year")
    bibtex = BibTeXExporter(config).export_to_string(result)
    assert "@article{smith2024," in bibtex
    assert "@article{smith2024b," in bibtex
    assert RISExporter(config).export_to_string(result).count("ER  -") == 2
