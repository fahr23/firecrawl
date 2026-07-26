"""Offline tests for the optional Firecrawl Research provider."""

from unittest.mock import Mock, patch

from academic_search import (
    APIConfig,
    AcademicSearchEngine,
    Config,
    FirecrawlResearchSearcher,
    create_engine,
)


def _config(enabled=True):
    return Config(
        api=APIConfig(
            elsevier_api_key=None,
            semantic_scholar_api_key=None,
            firecrawl_api_key="test-key",
            firecrawl_api_url="http://firecrawl.test",
            serper_api_key=None,
            clarivate_api_key=None,
        ),
        enable_firecrawl_research=enabled,
    )


def _searcher(response=None, error=None):
    client = Mock()
    if error is not None:
        client.v2.search_papers.side_effect = error
    else:
        client.v2.search_papers.return_value = response
    return FirecrawlResearchSearcher(_config(), client=client), client


def test_normalizes_research_results_and_passes_filters():
    searcher, client = _searcher(
        {
            "success": True,
            "results": [
                {
                    "paperId": "paper-1",
                    "title": "Auditable Retrieval for Scholarly Search",
                    "authors": [{"name": "Ada Researcher"}, "T. Author"],
                    "publishedDate": "2024-05-03",
                    "doi": "https://doi.org/10.1000/example",
                    "url": "https://example.org/paper",
                    "abstract": "Provider supplied abstract.",
                    "venue": "Journal of Retrieval",
                    "categories": ["information retrieval"],
                    "citationCount": "12",
                    "isOpenAccess": True,
                }
            ],
        }
    )

    result = searcher.search("auditable retrieval", 5, 2023, 2025)

    client.v2.search_papers.assert_called_once_with(
        "auditable retrieval",
        k=5,
        from_date="2023-01-01",
        to_date="2025-12-31",
    )
    assert result.total_found == 1
    article = result.articles[0]
    assert article.title == "Auditable Retrieval for Scholarly Search"
    assert article.authors == "Ada Researcher, T. Author"
    assert article.year == "2024"
    assert article.doi == "10.1000/example"
    assert article.source == "Firecrawl Research"
    assert article.citation_count == 12
    assert article.is_open_access is True


def test_filters_out_of_range_and_malformed_records_and_limits_results():
    searcher, _ = _searcher(
        {
            "results": [
                {"title": "Too old", "year": 2019},
                {"paperId": "missing-title"},
                {
                    "title": "Malformed optional fields",
                    "year": 2023,
                    "abstract": {"unexpected": "mapping"},
                    "journal": {"name": "Normalized Journal"},
                    "isOpenAccess": "false",
                    "url": "https://malformed.test",
                },
                {"title": "Accepted one", "year": 2023, "url": "https://one.test"},
                {"title": "Accepted two", "year": 2024, "url": "https://two.test"},
            ]
        }
    )

    result = searcher.search("query", max_results=1, year_min=2022, year_max=2024)

    assert [article.title for article in result.articles] == [
        "Malformed optional fields"
    ]
    assert result.articles[0].abstract is None
    assert result.articles[0].journal == "Normalized Journal"
    assert result.articles[0].is_open_access is False
    assert result.total_found == 1


def test_empty_invalid_and_failed_responses_fail_soft():
    cases = [
        (None, None),
        ({"success": False, "error": "not configured"}, None),
        ({"results": "not-a-list"}, None),
        (None, RuntimeError("service unavailable")),
    ]
    for response, error in cases:
        searcher, _ = _searcher(response=response, error=error)
        result = searcher.search("query")
        assert result.articles == []
        assert result.total_found == 0
        assert result.sources == ["Firecrawl Research"]


def test_provider_is_opt_in_and_google_scholar_does_not_use_firecrawl_key():
    disabled = AcademicSearchEngine(_config(enabled=False))
    assert "Firecrawl Research" not in disabled.available_sources
    assert "Google Scholar" not in disabled.available_sources

    with patch("academic_search.providers.Firecrawl") as client_class:
        enabled = AcademicSearchEngine(_config(enabled=True))

    assert "Firecrawl Research" in enabled.available_sources
    assert "Google Scholar" not in enabled.available_sources
    client_class.assert_called_once()


def test_environment_flag_enables_research(monkeypatch):
    monkeypatch.setenv("ACADEMIC_ENABLE_FIRECRAWL_RESEARCH", "true")
    config = Config(api=APIConfig(firecrawl_api_url="http://firecrawl.test"))
    assert config.enable_firecrawl_research is True


def test_create_engine_exposes_firecrawl_research_options():
    with patch("academic_search.providers.Firecrawl") as client_class:
        engine = create_engine(
            enable_firecrawl_research=True,
            firecrawl_api_key="test-key",
            firecrawl_api_url="http://firecrawl.test",
        )

    assert "Firecrawl Research" in engine.available_sources
    client_class.assert_called_once_with(
        api_key="test-key",
        api_url="http://firecrawl.test",
        timeout=30,
    )
