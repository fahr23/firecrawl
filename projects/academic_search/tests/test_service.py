from unittest.mock import Mock, patch

import requests
from fastapi.testclient import TestClient

from academic_search.models import Article, ProviderOutcome, SearchResult
from academic_search.project_store import ProjectStore
from academic_search.service import create_app, get_search_engine


class FakeEngine:
    def __init__(self):
        self.calls = []

    def search(
        self,
        query,
        max_results,
        use_all_sources,
        year_min,
        year_max,
        providers,
    ):
        self.calls.append(
            {
                "query": query,
                "max_results": max_results,
                "use_all_sources": use_all_sources,
                "year_min": year_min,
                "year_max": year_max,
                "providers": providers,
            }
        )
        return SearchResult(
            query=query,
            articles=[
                Article(
                    title="Machine learning for reliable data systems",
                    url="https://example.org/paper",
                    doi="10.1000/example",
                    abstract=(
                        "A machine learning study of algorithms and software "
                        "for reliable computing systems."
                    ),
                    authors="Ada Researcher, Lin Scientist",
                    journal="Journal of Computing",
                    year="2026",
                    source="OpenAlex",
                ),
                Article(
                    title="Unsafe link is not exposed",
                    url="javascript:alert(1)",
                    source="Fixture",
                ),
            ],
            total_found=2,
            sources=["OpenAlex"],
            requested_providers=["OpenAlex"],
            provider_outcomes=[ProviderOutcome("OpenAlex", "responded", returned_count=2, total_found=2)],
        )


def make_client():
    engine = FakeEngine()
    app = create_app(ProjectStore(":memory:"))
    app.dependency_overrides[get_search_engine] = lambda: engine
    return TestClient(app), engine


def test_ui_and_assets_are_served():
    client, _ = make_client()

    page = client.get("/")
    script = client.get("/assets/app.js")

    assert page.status_code == 200
    assert "Find papers. Keep the trail." in page.text
    assert "Parse document" in page.text
    assert "Web of Science" in page.text
    assert script.status_code == 200
    assert "/api/v1/search" in script.text
    assert "/api/v1/documents/parse" in script.text
    assert "/api/v1/health" in script.text


def test_search_returns_only_safe_linked_results_with_derived_category():
    client, engine = make_client()

    response = client.get(
        "/api/v1/search",
        params={
            "q": "machine learning",
            "category": "computer-science",
            "providers": "openalex",
            "limit": 10,
            "year_min": 2024,
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["returned"] == 1
    assert payload["results"][0]["url"] == "https://example.org/paper"
    assert payload["results"][0]["category"] == "computer-science"
    assert payload["results"][0]["category_provenance"] == "derived:keyword-rules-v1"
    assert payload["manifest"]["providers_requested"] == ["OpenAlex"]
    assert engine.calls[0]["providers"] == ["OpenAlex"]
    assert engine.calls[0]["max_results"] == 30


def test_search_rejects_unknown_category_and_inverted_year_range():
    client, _ = make_client()

    bad_category = client.get(
        "/api/v1/search",
        params={"q": "energy", "category": "astrology"},
    )
    bad_years = client.get(
        "/api/v1/search",
        params={"q": "energy", "year_min": 2026, "year_max": 2024},
    )

    assert bad_category.status_code == 422
    assert bad_years.status_code == 422


def test_project_keeps_search_defaults_history_and_exportable_evidence():
    client, _ = make_client()
    created = client.post(
        "/api/v1/projects",
        json={
            "name": "Carbon essay",
            "research_question": "Which interventions reduce emissions?",
            "default_providers": "openalex",
        },
    )
    assert created.status_code == 201
    project = created.json()

    searched = client.get(
        "/api/v1/search",
        params={
            "q": "machine learning", "project_id": project["id"],
            "category": "computer-science", "providers": "openalex", "year_min": 2024,
        },
    )
    assert searched.status_code == 200
    payload = searched.json()
    assert payload["project_id"] == project["id"]
    assert payload["provider_coverage"] == [{"provider": "OpenAlex", "status": "responded"}]

    history = client.get(f"/api/v1/projects/{project['id']}/searches").json()["searches"]
    assert history[0]["query"] == "machine learning"
    assert history[0]["year_min"] == 2024
    assert client.get(f"/api/v1/projects/{project['id']}").json()["default_category"] == "computer-science"

    evidence = client.get(f"/api/v1/projects/{project['id']}/evidence?format=markdown")
    assert evidence.status_code == 200
    assert "Which interventions reduce emissions?" in evidence.text
    assert "https://example.org/paper" in evidence.text
    assert "Deduplication:" in evidence.text
    assert history[0]["manifest"]["deduplication_version"] == "doi-or-title-author-year-v1"


def test_project_search_rejects_an_unknown_project():
    client, _ = make_client()
    response = client.get("/api/v1/search", params={"q": "energy", "project_id": "missing"})
    assert response.status_code == 404


def test_categories_expose_derived_provenance():
    client, _ = make_client()

    response = client.get("/api/v1/categories")

    assert response.status_code == 200
    payload = response.json()
    assert payload["category_provenance"] == "derived:keyword-rules-v1"
    assert any(item["id"] == "economics-finance" for item in payload["categories"])


def test_health_reports_each_provider_availability():
    client, _ = make_client()

    response = client.get("/api/v1/health")

    assert response.status_code == 200
    providers = response.json()["providers"]
    assert set(providers) == {
        "openalex", "semantic-scholar", "arxiv", "firecrawl-research",
        "science-direct", "scopus", "google-scholar", "clarivate",
    }
    assert providers["openalex"] is True
    assert providers["semantic-scholar"] is True
    assert providers["arxiv"] is True
    assert all(isinstance(value, bool) for value in providers.values())


def test_provider_availability_matches_web_of_science_to_clarivate():
    class WebOfScienceEngine:
        _searchers = [
            type("WebOfScience", (), {"source_name": "Web of Science", "is_available": True})()
        ]

    from academic_search.service import _provider_availability

    assert _provider_availability(WebOfScienceEngine())["clarivate"] is True


def test_provider_coverage_keeps_rate_limit_distinct_from_empty_results():
    from academic_search.service import _provider_coverage

    coverage = _provider_coverage(
        ["OpenAlex"], [],
        [{"provider": "OpenAlex", "status": "rate_limited", "error_code": "rate_limited"}],
    )

    assert coverage == [{
        "provider": "OpenAlex", "status": "rate_limited", "error_code": "rate_limited",
    }]


def test_document_parse_forwards_supported_upload_without_persisting_it():
    client, _ = make_client()
    firecrawl_response = Mock()
    firecrawl_response.status_code = 200
    firecrawl_response.json.return_value = {
        "success": True,
        "data": {
            "markdown": "# Findings\n\nA reproducible result.",
            "links": ["https://doi.org/10.1000/example"],
            "metadata": {"contentType": "application/pdf", "title": "Fixture"},
        },
    }

    with patch("academic_search.service.requests.post", return_value=firecrawl_response) as post:
        response = client.post(
            "/api/v1/documents/parse?filename=paper.pdf",
            content=b"%PDF-fixture",
            headers={"content-type": "application/pdf"},
        )

    assert response.status_code == 200
    body = response.json()
    assert body["filename"] == "paper.pdf"
    assert body["retrieval"] == "user-upload"
    assert body["markdown"].startswith("# Findings")
    assert body["metadata"]["contentType"] == "application/pdf"
    assert post.call_args.kwargs["files"]["file"][0] == "paper.pdf"


def test_document_parse_rejects_empty_or_unsupported_uploads():
    client, _ = make_client()

    unsupported = client.post("/api/v1/documents/parse?filename=notes.txt", content=b"text")
    empty = client.post("/api/v1/documents/parse?filename=paper.pdf", content=b"")

    assert unsupported.status_code == 422
    assert empty.status_code == 422


def test_document_parse_reports_an_unavailable_firecrawl_dependency():
    client, _ = make_client()

    with patch(
        "academic_search.service.requests.post",
        side_effect=requests.RequestException("offline"),
    ):
        response = client.post(
            "/api/v1/documents/parse?filename=paper.html",
            content=b"<h1>fixture</h1>",
        )

    assert response.status_code == 503
    assert response.json()["detail"] == "Firecrawl document parser is unavailable"
