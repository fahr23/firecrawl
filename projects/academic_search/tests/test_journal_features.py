"""Offline provider and analysis tests for journal exploration."""

from unittest.mock import Mock

from academic_search.config import APIConfig, Config
from academic_search.journal_catalog import JournalCatalogService
from academic_search.journal_analysis import build_journal_profile, manuscript_fit
from academic_search.providers import ClarivateSearcher, OpenAlexSearcher, ScopusSearcher


def test_openalex_journal_suggestions_normalize_identity_and_ignore_non_journals():
    searcher = OpenAlexSearcher(Config())
    searcher._make_request = Mock(return_value={
        "results": [
            {
                "id": "https://openalex.org/S123",
                "display_name": "Journal of Testing",
                "type": "journal",
                "issn_l": "1234-5678",
                "issn": ["1234-5678"],
                "host_organization_name": "Testing Press",
                "works_count": 42,
                "is_oa": True,
                "is_in_doaj": True,
            },
            {"id": "https://openalex.org/S999", "display_name": "Repository", "type": "repository"},
            {"type": "journal", "display_name": "Malformed journal"},
        ]
    })

    journals = searcher.suggest_journals("journal testing", 5)

    assert len(journals) == 1
    assert journals[0]["id"] == "S123"
    assert journals[0]["display_name"] == "Journal of Testing"
    assert journals[0]["issn_l"] == "1234-5678"
    assert journals[0]["publisher"] == "Testing Press"
    assert journals[0]["identifiers"]["openalex"] == "S123"
    assert journals[0]["search_supported"] is True
    params = searcher._make_request.call_args.args[1]
    assert params["filter"] == "type:journal"


def test_openalex_journal_search_scopes_by_source_and_year():
    searcher = OpenAlexSearcher(Config())
    searcher._make_request = Mock(return_value={
        "meta": {"count": 1},
        "results": [{
            "id": "https://openalex.org/W1",
            "title": "Energy forecasting",
            "doi": "https://doi.org/10.1000/test",
            "publication_year": 2025,
            "primary_location": {
                "landing_page_url": "https://example.org/paper",
                "source": {"display_name": "Journal of Testing"},
            },
            "abstract_inverted_index": {"Energy": [0], "forecasting": [1]},
            "authorships": [],
            "concepts": [],
            "open_access": {"is_oa": True},
        }],
    })

    result = searcher.search_journal(
        "S123", "Journal of Testing", "energy forecasting", 20, 2022, 2026
    )

    assert result.count == 1
    assert result.articles[0].journal == "Journal of Testing"
    assert result.provider_outcomes[0].status == "responded"
    params = searcher._make_request.call_args.args[1]
    assert "primary_location.source.id:S123" in params["filter"]
    assert "publication_year:2022-2026" in params["filter"]


def test_openalex_journal_search_preserves_provider_failure():
    searcher = OpenAlexSearcher(Config())

    def fail(*_args, **_kwargs):
        searcher.last_failure = {"code": "rate_limited", "message": "provider rate limit reached"}
        return None

    searcher._make_request = Mock(side_effect=fail)

    result = searcher.search_journal("S123", "Journal", "energy", 10)

    assert result.articles == []
    assert result.provider_outcomes[0].status == "rate_limited"
    assert result.provider_outcomes[0].error_code == "rate_limited"


def test_openalex_catalog_filters_journals_by_field_category():
    searcher = OpenAlexSearcher(Config())
    searcher._make_request = Mock(return_value={
        "results": [{
            "id": "https://openalex.org/S123",
            "display_name": "Journal of Computing",
            "type": "journal",
            "issn_l": "1234-5678",
            "issn": ["1234-5678"],
            "host_organization_name": "Computing Press",
            "works_count": 500,
            "topics": [{"field": {"id": "https://openalex.org/fields/17", "display_name": "Computer Science"}}],
        }]
    })

    journals = searcher.journal_catalog("computing", "17", 20)

    assert journals[0]["identifiers"]["openalex"] == "S123"
    assert journals[0]["issn_l"] == "1234-5678"
    assert journals[0]["categories"] == [{"id": "17", "label": "Computer Science"}]
    params = searcher._make_request.call_args.args[1]
    assert params["search"] == "computing"
    assert "topics.field.id:17" in params["filter"]


def test_scopus_serial_catalog_normalizes_issn_and_subjects():
    searcher = ScopusSearcher(Config(api=APIConfig(elsevier_api_key="test-key")))
    searcher._make_request = Mock(return_value={
        "serial-metadata-response": {
            "entry": [{
                "dc:title": "Journal of Data Systems",
                "prism:issn": "1234-5678",
                "prism:eIssn": "8765-4321",
                "source-id": "21100123456",
                "dc:publisher": "Example Press",
                "subject-area": [{"@abbrev": "COMP", "$": "Computer Science"}],
                "prism:url": "https://api.elsevier.com/content/serial/title/issn/1234-5678",
            }]
        }
    })

    journals = searcher.journal_catalog("data", "COMP", 10)

    assert journals[0]["issns"] == ["1234-5678", "8765-4321"]
    assert journals[0]["identifiers"]["scopus"] == "21100123456"
    assert journals[0]["categories"][0]["id"] == "COMP"
    params = searcher._make_request.call_args.args[1]
    assert params["content"] == "journal"
    assert params["subj"] == "COMP"


def test_web_of_science_journals_catalog_and_detail_are_separate_from_article_api():
    config = Config(api=APIConfig(
        clarivate_api_key="starter-key",
        clarivate_journals_api_key="journals-key",
    ))
    searcher = ClarivateSearcher(config)

    def response(url, _params, headers=None):
        assert headers == {"X-ApiKey": "journals-key"}
        if url.endswith("/categories"):
            return {"hits": [{"id": "COMP", "name": "COMPUTER SCIENCE", "edition": "SCIE"}]}
        if url.endswith("/journals/PLOS_ONE"):
            return {
                "id": "PLOS_ONE", "name": "PLoS One", "issn": "1932-6203",
                "eIssn": "1932-6203", "publisher": {"name": "PUBLIC LIBRARY SCIENCE"},
                "categories": [{"url": "/categories/ROC", "name": "MULTIDISCIPLINARY SCIENCES", "edition": "SCIE"}],
                "openAccess": {"startYear": 2006},
            }
        return {"hits": [{"id": "PLOS_ONE", "name": "PLoS One"}]}

    searcher._make_request = Mock(side_effect=response)

    categories = searcher.journal_categories("computer", 20)
    journals = searcher.journal_catalog("plos", "COMP", 10)
    detail = searcher.resolve_journal("PLOS_ONE")

    assert categories[0]["edition"] == "SCIE"
    assert journals[0]["identifiers"]["web_of_science"] == "PLOS_ONE"
    assert journals[0]["search_supported"] is False
    assert detail["issn_l"] == "1932-6203"
    assert detail["publisher"] == "PUBLIC LIBRARY SCIENCE"
    assert detail["categories"][0]["id"] == "ROC"


def test_catalog_crosswalks_paid_provider_issn_to_openalex_for_paper_search():
    catalog = JournalCatalogService(Config())
    catalog.web_of_science.resolve_journal = Mock(return_value={
        "id": "PLOS_ONE", "catalog_id": "web-of-science:PLOS_ONE",
        "catalog_provider": "web-of-science", "provider_id": "PLOS_ONE",
        "display_name": "PLoS One", "issns": ["1932-6203"],
        "identifiers": {"web_of_science": "PLOS_ONE", "issns": ["1932-6203"]},
        "source": "Web of Science Journals API", "search_supported": False,
    })
    catalog.openalex.resolve_journal_by_issn = Mock(return_value={
        "id": "S202381698", "display_name": "PLoS ONE", "issn_l": "1932-6203",
        "issns": ["1932-6203"], "identifiers": {"openalex": "S202381698"},
        "catalog_id": "openalex:S202381698", "catalog_provider": "openalex",
        "provider_id": "S202381698", "source": "OpenAlex", "search_supported": True,
    })

    resolved = catalog.resolve("web-of-science", "PLOS_ONE")["journal"]

    assert resolved["id"] == "S202381698"
    assert resolved["identifiers"]["web_of_science"] == "PLOS_ONE"
    assert resolved["identifiers"]["openalex"] == "S202381698"
    assert resolved["search_supported"] is True


def test_profile_and_fit_are_derived_from_the_exact_snapshot():
    papers = [
        {
            "title": "Machine learning for energy forecasting",
            "abstract": "Forecasting electricity markets with machine learning models.",
            "keywords": ["machine learning", "energy forecasting"],
            "url": "https://example.org/one",
            "doi": "10.1/one",
            "year": "2025",
        },
        {
            "title": "Policy instruments for emissions",
            "abstract": "A qualitative comparison of climate policy instruments.",
            "keywords": ["climate policy"],
            "url": "https://example.org/two",
            "year": "2024",
        },
    ]

    profile = build_journal_profile(papers)
    fit = manuscript_fit(
        "Energy market forecasting",
        "Machine learning methods forecast electricity markets.",
        ["machine learning", "energy forecasting"],
        papers,
    )

    assert profile["paper_count"] == 2
    assert profile["provenance"].startswith("derived:")
    assert fit["closest_papers"][0]["title"] == papers[0]["title"]
    assert fit["overall_score"] > 0
    assert "acceptance" in fit["disclaimer"]
