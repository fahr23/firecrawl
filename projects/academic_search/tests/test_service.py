from fastapi.testclient import TestClient

from academic_search.models import Article, ProviderOutcome, SearchResult
from academic_search.project_store import ProjectStore
from academic_search.service import (
    create_app,
    get_journal_catalog_service,
    get_journal_searcher,
    get_search_engine,
)


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


class ManyArticlesFakeEngine:
    """Fake engine that honors max_results, for pagination tests."""

    def __init__(self, total_available=120):
        self.calls = []
        self.total_available = total_available

    def search(self, query, max_results, use_all_sources, year_min, year_max, providers):
        self.calls.append({"query": query, "max_results": max_results, "providers": providers})
        count = min(max_results, self.total_available)
        articles = [
            Article(
                title=f"Paper {i}",
                url=f"https://example.org/paper-{i}",
                doi=f"10.1000/paper-{i}",
                source="OpenAlex",
                year="2024",
            )
            for i in range(count)
        ]
        return SearchResult(
            query=query,
            articles=articles,
            total_found=self.total_available,
            sources=["OpenAlex"],
            requested_providers=["OpenAlex"],
            provider_outcomes=[ProviderOutcome("OpenAlex", "responded", returned_count=count, total_found=self.total_available)],
        )


class FakeJournalSearcher:
    source_name = "OpenAlex"
    last_failure = None

    def __init__(self):
        self.suggest_calls = []
        self.search_calls = []

    def suggest_journals(self, query, limit=8):
        self.suggest_calls.append({"query": query, "limit": limit})
        return [
            {
                "id": "S123",
                "display_name": "Journal of Computing",
                "issn_l": "1234-5678",
                "issns": ["1234-5678", "8765-4321"],
                "publisher": "Example Academic Press",
                "works_count": 1234,
                "is_oa": True,
                "is_in_doaj": True,
                "type": "journal",
                "source": "OpenAlex",
            }
        ]

    def search_journal(
        self, journal_id, journal_name, query, max_results=25,
        year_min=None, year_max=None,
    ):
        self.search_calls.append({
            "journal_id": journal_id,
            "journal_name": journal_name,
            "query": query,
            "max_results": max_results,
            "year_min": year_min,
            "year_max": year_max,
        })
        return SearchResult(
            query=query,
            articles=[
                Article(
                    title="Machine learning for reliable data systems",
                    url="https://example.org/paper",
                    doi="10.1000/example",
                    abstract=(
                        "A machine learning study of forecasting algorithms and software "
                        "for reliable energy data systems."
                    ),
                    authors="Ada Researcher, Lin Scientist",
                    journal=journal_name,
                    year="2026",
                    keywords=["machine learning", "forecasting", "energy"],
                    source="OpenAlex",
                ),
                Article(
                    title="Statistical forecasting for energy markets",
                    url="https://example.org/forecasting",
                    abstract=(
                        "Statistical forecasting methods are evaluated for electricity "
                        "and energy market decisions."
                    ),
                    journal=journal_name,
                    year="2025",
                    keywords=["forecasting", "energy markets"],
                    source="OpenAlex",
                ),
            ],
            total_found=2,
            sources=["OpenAlex"],
            requested_providers=["OpenAlex"],
            provider_outcomes=[
                ProviderOutcome("OpenAlex", "responded", returned_count=2, total_found=2)
            ],
            year_min=year_min,
            year_max=year_max,
            limit=max_results,
            raw_article_count=2,
            deduplicated_article_count=2,
        )


class FakeJournalCatalog:
    def providers(self):
        return [
            {"id": "openalex", "label": "OpenAlex", "available": True},
            {"id": "web-of-science", "label": "Web of Science Journals", "available": True},
            {"id": "scopus", "label": "Scopus Serial Titles", "available": False},
        ]

    def categories(self, provider, query, limit):
        return {
            "provider": provider,
            "categories": [{"id": "COMP", "label": "Computer Science", "provider": provider}],
            "provider_status": {"status": "responded"},
        }

    def journals(self, provider, query, category_id, limit, page=1, sort=None):
        return {
            "provider": provider,
            "query": query,
            "category_id": category_id,
            "journals": [{
                "id": "PLOS_ONE",
                "catalog_id": "web-of-science:PLOS_ONE",
                "catalog_provider": provider,
                "provider_id": "PLOS_ONE",
                "display_name": "PLoS One",
                "issn_l": None,
                "issns": [],
                "publisher": "Public Library of Science",
                "categories": [{"id": "COMP", "label": "Computer Science"}],
                "identifiers": {"web_of_science": "PLOS_ONE"},
                "search_supported": False,
                "type": "journal",
                "source": "Web of Science Journals API",
            }],
            "provider_status": {"status": "responded"},
            "identifier_note": "ISSN identifies journals; DOI identifies articles.",
        }

    def resolve(self, provider, journal_id):
        return {
            "provider": provider,
            "provider_status": {"status": "responded"},
            "journal": {
                "id": "S123",
                "catalog_id": f"{provider}:{journal_id}",
                "catalog_provider": provider,
                "provider_id": journal_id,
                "display_name": "PLoS One",
                "issn_l": "1932-6203",
                "issns": ["1932-6203"],
                "publisher": "Public Library of Science",
                "categories": [{"id": "COMP", "label": "Computer Science"}],
                "identifiers": {
                    "openalex": "S123", "web_of_science": journal_id,
                    "issn_l": "1932-6203", "issns": ["1932-6203"],
                },
                "provider_records": [
                    {"provider": provider, "id": journal_id},
                    {"provider": "openalex", "id": "S123"},
                ],
                "search_supported": True,
                "type": "journal",
                "source": "OpenAlex",
            },
        }


def make_client(engine=None):
    engine = engine or FakeEngine()
    journal_searcher = FakeJournalSearcher()
    app = create_app(ProjectStore(":memory:"))
    app.dependency_overrides[get_search_engine] = lambda: engine
    app.dependency_overrides[get_journal_searcher] = lambda: journal_searcher
    app.dependency_overrides[get_journal_catalog_service] = lambda: FakeJournalCatalog()
    return TestClient(app), engine, journal_searcher


def test_ui_and_assets_are_served():
    client, _, _ = make_client()

    page = client.get("/ui")
    script = client.get("/assets/app.js")

    assert page.status_code == 200
    assert "Find papers. Keep the trail." in page.text
    assert "Read a local research document" not in page.text
    assert 'id="providers"' in page.text
    assert 'id="sources-unavailable"' in page.text
    assert script.status_code == 200
    assert "Web of Science" in script.text
    assert "/api/v1/search" in script.text
    assert "/api/v1/documents/parse" not in script.text
    assert "/api/v1/health" in script.text
    assert "Journal explorer" in page.text
    assert "/api/v1/journals/search" in script.text
    assert "Journal catalog" in page.text
    assert "/api/v1/journal-catalog/journals" in script.text


def test_search_returns_only_safe_linked_results_with_derived_category():
    client, engine, _ = make_client()

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
    assert engine.calls[0]["max_results"] == 33


def test_search_paginates_beyond_the_single_page_limit():
    client, _, _ = make_client(ManyArticlesFakeEngine(total_available=120))

    page1 = client.get("/api/v1/search", params={"q": "energy", "limit": 50, "page": 1})
    page2 = client.get("/api/v1/search", params={"q": "energy", "limit": 50, "page": 2})
    page3 = client.get("/api/v1/search", params={"q": "energy", "limit": 50, "page": 3})

    assert page1.status_code == page2.status_code == page3.status_code == 200
    body1, body2, body3 = page1.json(), page2.json(), page3.json()

    assert body1["returned"] == 50
    assert body1["page"] == 1
    assert body1["has_more"] is True
    assert body1["results"][0]["url"] == "https://example.org/paper-0"

    assert body2["returned"] == 50
    assert body2["page"] == 2
    assert body2["has_more"] is True
    assert body2["results"][0]["url"] == "https://example.org/paper-50"
    assert {r["url"] for r in body1["results"]}.isdisjoint({r["url"] for r in body2["results"]})

    assert body3["returned"] == 20
    assert body3["page"] == 3
    assert body3["has_more"] is False


def test_search_rejects_a_page_above_the_allowed_maximum():
    client, _, _ = make_client()

    response = client.get("/api/v1/search", params={"q": "energy", "page": 11})

    assert response.status_code == 422


def test_search_queries_several_selected_providers_in_one_request():
    client, engine, _ = make_client()

    response = client.get(
        "/api/v1/search",
        params={"q": "agent based electricity", "providers": "openalex,pubmed,core,clarivate"},
    )
    unknown = client.get(
        "/api/v1/search",
        params={"q": "agent based electricity", "providers": "openalex,not-a-source"},
    )

    assert response.status_code == 200
    assert engine.calls[0]["providers"] == ["OpenAlex", "PubMed", "CORE", "Web of Science"]
    assert response.json()["providers_requested"] == ["OpenAlex", "PubMed", "CORE", "Web of Science"]
    assert unknown.status_code == 422


def test_search_rejects_unknown_category_and_inverted_year_range():
    client, _, _ = make_client()

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
    client, _, _ = make_client()
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


def test_search_beyond_page_one_does_not_duplicate_project_history():
    client, _, _ = make_client(ManyArticlesFakeEngine(total_available=120))
    project = client.post("/api/v1/projects", json={"name": "Pagination essay"}).json()

    client.get("/api/v1/search", params={"q": "energy", "project_id": project["id"], "limit": 50, "page": 1})
    client.get("/api/v1/search", params={"q": "energy", "project_id": project["id"], "limit": 50, "page": 2})

    history = client.get(f"/api/v1/projects/{project['id']}/searches").json()["searches"]
    assert len(history) == 1


def test_project_names_are_unique_ignoring_case_and_spaces():
    client, _, _ = make_client()

    first = client.post("/api/v1/projects", json={"name": "Carbon mitigation study"})
    again = client.post("/api/v1/projects", json={"name": "  carbon MITIGATION study "})
    other = client.post("/api/v1/projects", json={"name": "Carbon pricing study"})
    renamed = client.patch(f"/api/v1/projects/{other.json()['id']}", json={"name": "CARBON mitigation study"})

    assert first.status_code == 201
    assert again.status_code == 409
    assert other.status_code == 201
    assert renamed.status_code == 409
    assert [p["name"] for p in client.get("/api/v1/projects").json()["projects"]].count("Carbon mitigation study") == 1


def test_clearing_the_year_in_a_project_search_clears_the_project_default():
    client, _, _ = make_client()
    project = client.post("/api/v1/projects", json={"name": "Year reset"}).json()

    client.get("/api/v1/search", params={"q": "energy", "project_id": project["id"], "year_min": 2020})
    client.get("/api/v1/search", params={"q": "energy", "project_id": project["id"]})

    assert client.get(f"/api/v1/projects/{project['id']}").json()["default_year_min"] is None


def test_project_search_rejects_an_unknown_project():
    client, _, _ = make_client()
    response = client.get("/api/v1/search", params={"q": "energy", "project_id": "missing"})
    assert response.status_code == 404


def test_categories_expose_derived_provenance():
    client, _, _ = make_client()

    response = client.get("/api/v1/categories")

    assert response.status_code == 200
    payload = response.json()
    assert payload["category_provenance"] == "derived:keyword-rules-v1"
    assert any(item["id"] == "economics-finance" for item in payload["categories"])


def test_health_reports_each_provider_availability():
    client, _, _ = make_client()

    response = client.get("/api/v1/health")

    assert response.status_code == 200
    providers = response.json()["providers"]
    assert set(providers) == {
        "openalex", "semantic-scholar", "arxiv", "pubmed", "core",
        "firecrawl-research", "science-direct", "scopus", "google-scholar",
        "clarivate",
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


def test_journal_suggestions_resolve_stable_identity():
    client, _, journal_searcher = make_client()

    response = client.get("/api/v1/journals/suggest", params={"q": "journal computing"})

    assert response.status_code == 200
    payload = response.json()
    assert payload["journals"][0]["id"] == "S123"
    assert payload["journals"][0]["issn_l"] == "1234-5678"
    assert payload["journals"][0]["publisher"] == "Example Academic Press"
    assert payload["provenance"] == "provider:OpenAlex"
    assert journal_searcher.suggest_calls == [{"query": "journal computing", "limit": 8}]


def test_journal_catalog_browses_provider_categories_and_resolves_issn_crosswalk():
    client, _, _ = make_client()

    providers = client.get("/api/v1/journal-catalog/providers")
    categories = client.get(
        "/api/v1/journal-catalog/categories",
        params={"provider": "web-of-science", "q": "computer"},
    )
    journals = client.get(
        "/api/v1/journal-catalog/journals",
        params={"provider": "web-of-science", "category_id": "COMP", "q": "plos"},
    )
    resolved = client.get(
        "/api/v1/journal-catalog/resolve",
        params={"provider": "web-of-science", "journal_id": "PLOS_ONE"},
    )

    assert providers.status_code == categories.status_code == journals.status_code == resolved.status_code == 200
    assert any(item["id"] == "web-of-science" and item["available"] for item in providers.json()["providers"])
    assert categories.json()["categories"][0]["label"] == "Computer Science"
    assert journals.json()["journals"][0]["identifiers"]["web_of_science"] == "PLOS_ONE"
    assert "DOI identifies articles" in journals.json()["identifier_note"]
    journal = resolved.json()["journal"]
    assert journal["id"] == "S123"
    assert journal["issn_l"] == "1932-6203"
    assert journal["identifiers"]["openalex"] == "S123"
    assert journal["search_supported"] is True


def test_journal_catalog_rejects_unknown_provider():
    client, _, _ = make_client()
    response = client.get(
        "/api/v1/journal-catalog/journals", params={"provider": "made-up"}
    )
    assert response.status_code == 422


def test_saved_journal_search_reuses_snapshot_and_refreshes_on_request():
    client, _, journal_searcher = make_client()
    project = client.post("/api/v1/projects", json={"name": "Target journal"}).json()
    request = {
        "project_id": project["id"],
        "journal": {
            "id": "S123",
            "display_name": "Journal of Computing",
            "issn_l": "1234-5678",
            "publisher": "Example Academic Press",
        },
        "topics": ["machine learning", "energy forecasting"],
        "year_min": 2023,
        "limit": 20,
    }

    first = client.post("/api/v1/journals/search", json=request)
    cached = client.post("/api/v1/journals/search", json=request)
    refreshed = client.post(
        "/api/v1/journals/search", json={**request, "refresh": True}
    )

    assert first.status_code == cached.status_code == refreshed.status_code == 200
    assert first.json()["cache_status"] == "fresh"
    assert cached.json()["cache_status"] == "saved"
    assert cached.json()["id"] == first.json()["id"]
    assert refreshed.json()["cache_status"] == "refreshed"
    assert refreshed.json()["id"] != first.json()["id"]
    assert len(journal_searcher.search_calls) == 2
    assert first.json()["papers"][0]["alignment"]["score"] >= 0
    assert first.json()["profile"]["provenance"] == "derived:journal-profile-token-frequency-v1"
    assert first.json()["retrieved_at"]
    assert first.json()["refresh_recommended"] is False

    saved = client.get(
        f"/api/v1/projects/{project['id']}/journal-searches"
    ).json()["searches"]
    assert len(saved) == 2
    assert saved[0]["journal"]["display_name"] == "Journal of Computing"
    assert saved[0]["topics"] == ["machine learning", "energy forecasting"]


def test_manuscript_fit_uses_and_saves_exact_journal_snapshot():
    client, _, _ = make_client()
    project = client.post("/api/v1/projects", json={"name": "Manuscript fit"}).json()
    searched = client.post(
        "/api/v1/journals/search",
        json={
            "project_id": project["id"],
            "journal": {"id": "S123", "display_name": "Journal of Computing"},
            "topics": ["machine learning", "energy forecasting"],
        },
    ).json()

    response = client.post(
        f"/api/v1/journal-searches/{searched['id']}/fit",
        json={
            "project_id": project["id"],
            "title": "Machine learning forecasts for energy markets",
            "abstract": (
                "We evaluate machine learning and statistical forecasting methods "
                "for reliable electricity market decisions."
            ),
            "keywords": ["machine learning", "forecasting", "energy markets"],
        },
    )

    assert response.status_code == 201
    fit = response.json()
    assert 0 <= fit["overall_score"] <= 100
    assert fit["journal_search_id"] == searched["id"]
    assert fit["provenance"] == "derived:token-cosine-fit-v1"
    assert fit["disclaimer"]
    assert fit["closest_papers"][0]["title"]
    assert fit["matched_terms"]

    saved = client.get(
        f"/api/v1/projects/{project['id']}/journal-fits"
    ).json()["fits"]
    assert saved[0]["id"] == fit["id"]
    assert saved[0]["journal_search_id"] == searched["id"]


def test_journal_search_and_fit_validate_project_and_manuscript():
    client, _, _ = make_client()

    missing_project = client.post(
        "/api/v1/journals/search",
        json={
            "project_id": "missing",
            "journal": {"id": "S123", "display_name": "Journal of Computing"},
            "topics": ["energy"],
        },
    )
    short_suggestion = client.get("/api/v1/journals/suggest", params={"q": "x"})
    project = client.post("/api/v1/projects", json={"name": "Empty manuscript"}).json()
    searched = client.post(
        "/api/v1/journals/search",
        json={
            "project_id": project["id"],
            "journal": {"id": "S123", "display_name": "Journal of Computing"},
            "topics": ["energy"],
        },
    ).json()
    empty_manuscript = client.post(
        f"/api/v1/journal-searches/{searched['id']}/fit",
        json={"project_id": project["id"], "title": "", "abstract": "", "keywords": []},
    )

    assert missing_project.status_code == 404
    assert short_suggestion.status_code == 422
    assert empty_manuscript.status_code == 422


def test_ubyt_list_searches_by_name_or_issn_and_looks_up_payment():
    client, _, _ = make_client()

    by_name = client.get("/api/v1/ubyt/journals", params={"q": "lancet", "limit": 3})
    by_issn = client.get("/api/v1/ubyt/journals", params={"q": "1474547x"})
    by_index = client.get("/api/v1/ubyt/journals", params={"q": "lancet psychiatry", "category": "ssci"})
    lookup = client.get("/api/v1/ubyt/lookup", params={"issn": ["9999-9999", "0140-6736"]})
    title_lookup = client.get("/api/v1/ubyt/lookup", params={"name": "The Lancet"})
    unknown = client.get("/api/v1/ubyt/lookup", params={"issn": "9999-9999"})
    missing = client.get("/api/v1/ubyt/lookup")

    assert by_name.status_code == by_issn.status_code == lookup.status_code == 200
    assert by_name.json()["list"] == "TÜBİTAK UBYT 2026"
    assert by_name.json()["journals"][0]["journal_name"] == "LANCET"
    assert len(by_name.json()["journals"]) == 3
    assert [item["journal_name"] for item in by_issn.json()["journals"]] == ["LANCET"]
    assert [item["journal_name"] for item in by_index.json()["journals"]] == ["Lancet Psychiatry"]
    entry = lookup.json()["ubyt"]
    assert entry["payment_tl"] == 55000
    assert entry["mep_score"] == 38.263
    assert entry["indexes"] == ["SCIE"]
    assert entry["matched_by"] == "issn"
    assert title_lookup.json()["ubyt"]["matched_by"] == "name"
    assert unknown.json()["ubyt"] is None
    assert missing.status_code == 422


def test_paper_results_carry_ubyt_payment_from_provider_issn_or_exact_title():
    class UbytEngine(FakeEngine):
        def search(self, query, max_results, use_all_sources, year_min, year_max, providers):
            return SearchResult(
                query=query,
                articles=[
                    Article(
                        title="Trial by ISSN", url="https://example.org/a", source="OpenAlex",
                        journal="The Lancet (London)",
                        raw_data={"primary_location": {"source": {"issn": ["1474-547X"]}}},
                    ),
                    Article(
                        title="Trial by title", url="https://example.org/b", source="Fixture",
                        journal="Lancet Psychiatry",
                    ),
                    Article(
                        title="Unlisted venue", url="https://example.org/c", source="Fixture",
                        journal="Journal of Computing",
                    ),
                ],
                total_found=3,
                sources=["OpenAlex"],
                requested_providers=["OpenAlex"],
            )

    client, _, _ = make_client()
    client.app.dependency_overrides[get_search_engine] = lambda: UbytEngine()

    results = client.get("/api/v1/search", params={"q": "clinical trial"}).json()["results"]

    by_title = {item["title"]: item["ubyt"] for item in results}
    assert by_title["Trial by ISSN"]["journal_name"] == "LANCET"
    assert by_title["Trial by ISSN"]["matched_by"] == "issn"
    assert by_title["Trial by ISSN"]["matched_issn"] == "1474-547X"
    assert by_title["Trial by ISSN"]["provenance"] == "list:ubyt_2026.csv"
    assert by_title["Trial by title"]["matched_by"] == "name"
    assert by_title["Trial by title"]["indexes"] == ["SCIE", "SSCI"]
    assert by_title["Unlisted venue"] is None


def test_ubyt_catalog_provider_resolves_to_openalex_and_keeps_payment():
    from academic_search.journal_catalog import JournalCatalogService
    from academic_search.service import get_ubyt_catalog

    catalog = JournalCatalogService(ubyt=get_ubyt_catalog())
    catalog.openalex.resolve_journal_by_issn = lambda issn: {
        "id": "S49861241", "display_name": "The Lancet", "issn_l": "0140-6736",
        "issns": ["0140-6736", "1474-547X"], "identifiers": {"openalex": "S49861241"},
        "source": "OpenAlex", "type": "journal",
    }
    client, _, _ = make_client()
    client.app.dependency_overrides[get_journal_catalog_service] = lambda: catalog

    providers = client.get("/api/v1/journal-catalog/providers").json()["providers"]
    categories = client.get("/api/v1/journal-catalog/categories", params={"provider": "ubyt"}).json()
    journals = client.get(
        "/api/v1/journal-catalog/journals",
        params={"provider": "ubyt", "q": "lancet", "category_id": "scie", "limit": 2},
    ).json()
    resolved = client.get(
        "/api/v1/journal-catalog/resolve", params={"provider": "ubyt", "journal_id": "0140-6736"},
    )
    unknown = client.get(
        "/api/v1/journal-catalog/resolve", params={"provider": "ubyt", "journal_id": "9999-9999"},
    )

    assert any(item["id"] == "ubyt" and item["available"] for item in providers)
    assert {item["id"] for item in categories["categories"]} >= {"scie", "ssci", "ahci", "scopus"}
    scie = next(item for item in categories["categories"] if item["id"] == "scie")
    assert "5088 journals flagged SCIE" in scie["description"]
    assert "ubyt_2026.csv" in next(item for item in providers if item["id"] == "ubyt")["access_note"]
    assert journals["journals"][0]["display_name"] == "LANCET"
    assert journals["journals"][0]["ubyt"]["payment_tl"] == 55000
    journal = resolved.json()["journal"]
    assert journal["id"] == "S49861241"
    assert journal["search_supported"] is True
    assert journal["catalog_provider"] == "ubyt"
    assert journal["ubyt"]["journal_name"] == "LANCET"
    assert unknown.status_code == 404


def test_journal_suggestions_and_health_report_ubyt_list():
    client, _, _ = make_client()

    journals = client.get("/api/v1/journals/suggest", params={"q": "journal computing"}).json()["journals"]
    health = client.get("/api/v1/health").json()

    assert journals[0]["ubyt"] is None
    assert health["ubyt"] == {"list": "TÜBİTAK UBYT 2026", "journals": 11639}


def test_ubyt_catalog_normalizes_titles_and_keeps_first_journal_for_shared_issn(tmp_path):
    from academic_search.ubyt_catalog import UbytCatalog

    path = tmp_path / "ubyt.csv"
    path.write_text(
        "name,issn,eissn,payment_tl,mep_score,scie,ssci,ahci,source,year\n"
        "Energy & Environmental Science,1754-5692,1754-5706,55000,9.5,True,False,False,-,2026\n"
        "Global Mental Health,2054-4251,2054-4251,35392,1.295,True,False,False,-,2026\n"
        "Cambridge Prisms-Global Mental Health,2054-4251,2054-4251,28170,1.031,True,False,False,-,2026\n"
        "Missing identifiers,,,5500,0.1,False,False,False,SCOPUS,2026\n",
        encoding="utf-8",
    )
    catalog = UbytCatalog(path)

    assert len(catalog.records) == 3
    assert catalog.match([], "The Energy and Environmental Science")["payment_tl"] == 55000
    assert catalog.match(["20544251"])["journal_name"] == "Global Mental Health"
    assert catalog.match([], "Energy Science") is None


def test_ubyt_journal_list_paginates_through_every_match():
    from academic_search.journal_catalog import JournalCatalogService
    from academic_search.service import get_ubyt_catalog

    catalog = JournalCatalogService(ubyt=get_ubyt_catalog())
    client, _, _ = make_client()
    client.app.dependency_overrides[get_journal_catalog_service] = lambda: catalog

    def page(number):
        return client.get(
            "/api/v1/journal-catalog/journals",
            params={"provider": "ubyt", "category_id": "ahci", "limit": 50, "page": number},
        ).json()

    first, second, last = page(1), page(2), page(35)
    seen = set()
    for number in range(1, 36):
        seen.update(item["issn_l"] for item in page(number)["journals"])

    assert first["total"] == 1750
    assert first["has_more"] is True
    assert len(first["journals"]) == 50
    assert {item["issn_l"] for item in first["journals"]}.isdisjoint(
        item["issn_l"] for item in second["journals"]
    )
    assert len(last["journals"]) == 50
    assert last["has_more"] is False
    assert len(seen) == 1750

    direct = client.get("/api/v1/ubyt/journals", params={"category": "ssci", "limit": 100, "page": 33}).json()
    assert direct["total"] == 3278
    assert len(direct["journals"]) == 78
