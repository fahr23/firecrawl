"""Regression tests for provider requests and fetches through the HTTP service."""

from concurrent.futures import ThreadPoolExecutor
import json
from threading import Barrier
from unittest.mock import Mock

import pytest
import requests

from academic_search import discovery, submission_sources
from academic_search.base import BaseSearcher
from academic_search.config import APIConfig, Config
from academic_search.journal_catalog import JournalCatalogService
from academic_search.models import Article, SearchResult
from academic_search.providers import (
    ArXivSearcher, ClarivateSearcher, CoreSearcher, GoogleScholarSearcher, OpenAlexSearcher,
    PubMedSearcher, ScienceDirectSearcher, ScopusSearcher, SemanticScholarSearcher,
)
from academic_search.service import get_journal_searcher
from academic_search.tests.test_reproducibility import FixtureSearcher, fixture_engine
from academic_search.tests.test_service import ManyArticlesFakeEngine, make_client


def json_response(payload, status=200):
    response = Mock(status_code=status)
    response.json.return_value = payload
    return response


def test_concurrent_queries_keep_provider_failure_on_the_correct_request():
    barrier = Barrier(2, timeout=5)

    class ConcurrentSearcher(BaseSearcher):
        @property
        def source_name(self):
            return "Concurrent fixture"

        def search(self, query, *args):
            if query == "throttled":
                self.last_failure = {"code": "rate_limited", "message": "rate limited"}
            barrier.wait()
            return SearchResult(query=query)

    engine = fixture_engine(ConcurrentSearcher(Config()))
    with ThreadPoolExecutor(max_workers=2) as pool:
        throttled = pool.submit(engine.search, "throttled", use_all_sources=True)
        empty = pool.submit(engine.search, "empty", use_all_sources=True)
        assert throttled.result().provider_outcomes[0].status == "rate_limited"
        assert empty.result().provider_outcomes[0].status == "empty"


def test_concurrent_catalog_queries_keep_their_totals():
    barrier = Barrier(2, timeout=5)
    catalog = JournalCatalogService()

    def fetch(query, category, limit, page):
        catalog.openalex.last_total = int(query)
        barrier.wait()
        return []

    catalog.openalex.journal_catalog = fetch
    with ThreadPoolExecutor(max_workers=2) as pool:
        a = pool.submit(catalog.journals, "openalex", "53", None, 20)
        b = pool.submit(catalog.journals, "openalex", "4", None, 20)
        assert a.result()["total"] == 53 and a.result()["has_more"]
        assert b.result()["total"] == 4 and not b.result()["has_more"]


def test_public_search_supports_the_tenth_page_without_advertising_page_eleven():
    client, engine, _ = make_client(ManyArticlesFakeEngine(total_available=530))

    result = client.get("/api/v1/search", params={"q": "energy", "limit": 50, "page": 10}).json()

    assert result["page"] == 10
    assert result["returned"] == 50
    assert result["results"][0]["title"] == "Paper 450"
    assert result["has_more"] is False
    assert result["pagination"]["max_page"] == 10
    assert result["pagination"]["window_limited"] is True
    assert engine.calls[0]["max_results"] >= 501


def test_openalex_public_paging_keeps_a_fixed_page_size_and_partial_errors(monkeypatch):
    monkeypatch.delenv("OPENALEX_API_KEY", raising=False)
    searcher = OpenAlexSearcher(Config())
    requested = []

    def get(url, *, params, **kwargs):
        requested.append(dict(params))
        if len(requested) > 1:
            return json_response({}, 429)
        works = [{"id": f"https://openalex.org/W{index + 1}", "title": f"Forecast {index}"}
                 for index in range(params["per_page"])]
        return json_response({"meta": {"count": 320}, "results": works})

    monkeypatch.setattr(requests, "get", get)
    client, _, _ = make_client(fixture_engine(searcher))
    body = client.get("/api/v1/search", params={"q": "energy", "page": 2, "limit": 50}).json()

    assert [params["per_page"] for params in requested] == [100, 100]
    assert [params["page"] for params in requested] == [1, 2]
    assert body["returned"] == 50
    assert not body["has_more"]
    assert body["provider_coverage"][0]["status"] == "rate_limited"
    assert body["provider_outcomes"][0]["returned_count"] == 100
    assert body["pagination"]["partial"] is True


def test_web_of_science_final_page_does_not_change_page_size(monkeypatch):
    requested = []

    def get(url, *, params, **kwargs):
        requested.append(dict(params))
        start = (params["page"] - 1) * params["limit"]
        hits = [{"id": index} for index in range(start, min(start + params["limit"], 130))]
        return json_response({"hits": hits, "metadata": {"total": 130}})

    monkeypatch.setattr(requests, "get", get)
    searcher = ClarivateSearcher(Config(api=APIConfig(clarivate_api_key="fixture-key")))
    searcher._parse_hit = lambda hit: Article(f"Paper {hit['id']}", f"https://example.org/{hit['id']}")

    result = searcher.search("forecasting", max_results=51)

    assert result.count == 51
    assert result.articles[-1].title == "Paper 50"
    assert [params["limit"] for params in requested] == [50, 50]


def test_arxiv_applies_dates_upstream_and_reads_opensearch_total(monkeypatch):
    get = Mock(return_value=Mock(status_code=200, content=b"""
        <feed xmlns="http://www.w3.org/2005/Atom" xmlns:o="http://a9.com/-/spec/opensearch/1.1/">
          <o:totalResults>25</o:totalResults>
          <entry><id>https://arxiv.org/abs/2501.12345v1</id><title>Arxiv fixture</title>
            <summary>Forecasting</summary><published>2025-01-02T00:00:00Z</published></entry>
        </feed>"""))
    monkeypatch.setattr(requests, "get", get)
    searcher = ArXivSearcher(Config())
    result = searcher.search("ti:power OR ti:energy", max_results=5, year_min=2024, year_max=2025)

    assert get.call_args.args[0].startswith("https://")
    assert get.call_args.kwargs["params"]["search_query"] == (
        "(ti:power OR ti:energy) AND submittedDate:[202401010000 TO 202512312359]"
    )
    assert result.total_found == 25 and result.articles[0].year == "2025"
    get.return_value = Mock(status_code=429)
    result = fixture_engine(searcher).search("forecasting", use_all_sources=True)
    assert result.provider_outcomes[0].status == "rate_limited"


@pytest.mark.parametrize("body", [{"error": "upstream"}, {"esearchresult": {"idlist": [], "count": "3"}}, ["invalid"]])
def test_pubmed_invalid_esearch_payload_is_not_an_empty_result(monkeypatch, body):
    monkeypatch.setattr(requests, "get", Mock(return_value=json_response(body)))
    client, _, _ = make_client(fixture_engine(PubMedSearcher(Config())))
    result = client.get("/api/v1/search", params={"q": "asthma", "providers": "pubmed"}).json()

    assert result["provider_coverage"][0]["error_code"] == "invalid_response"


def test_pubmed_preserves_esearch_rank_and_uses_publication_date_parameters(monkeypatch):
    get = Mock(side_effect=[
        json_response({"esearchresult": {"count": "30", "idlist": ["12", "14"]}}),
        json_response({"result": {"uids": ["14", "12"], "12": {"title": "First", "pubdate": "2024 Aug", "authors": [{}]},
                                 "14": {"title": "Second", "pubdate": "2022 Sep"}}}),
    ])
    monkeypatch.setattr(requests, "get", get)
    result = PubMedSearcher(Config()).search("asthma OR rhinitis", max_results=2, year_max=2024, sort_by="pub_date")

    search = get.call_args_list[0].kwargs["params"]
    assert search["term"] == "asthma OR rhinitis"
    assert search["datetype"] == "pdat" and search["maxdate"] == "2024/12/31"
    assert search["sort"] == "pub_date"
    assert result.total_found == 30
    assert [item.title for item in result.articles] == ["First", "Second"]


def test_semantic_scholar_follows_next_offset_and_honors_upper_year(monkeypatch):
    get = Mock(side_effect=[
        json_response({"total": 300, "next": 100, "data": [
            {"paperId": f"p{n}", "title": f"Paper {n}", "year": 2024} for n in range(100)
        ]}),
        json_response({"total": 300, "data": [{"paperId": "p100", "title": "Paper 100", "year": 2024}]}),
    ])
    monkeypatch.setattr(requests, "get", get)
    result = SemanticScholarSearcher(Config()).search("solar", max_results=101, year_max=2024)
    assert result.count == 101
    assert [call.kwargs["params"]["offset"] for call in get.call_args_list] == [0, 100]
    assert all(call.kwargs["params"]["year"] == "-2024" for call in get.call_args_list)
    assert result.articles[-1].url == "https://www.semanticscholar.org/paper/p100"


def test_verified_notices_use_current_status_without_history_or_negation(monkeypatch):
    def read(url):
        page = submission_sources._Notice()
        page.feed('''
            <h1>Journal</h1><p>The journal is not accepting submissions this month.</p>
            <h2>Submission history</h2><p>Open for submissions last year</p>
        ''')
        return page

    monkeypatch.setattr(submission_sources, "_read", read)
    result = submission_sources.verify_notice("https://dergipark.org.tr/en/pub/test")
    assert result["status"] == "closed"
    assert "not accepting submissions" in result["evidence"].lower()


def test_core_uses_the_configured_key_and_retains_a_metadata_only_record(monkeypatch):
    get = Mock(return_value=json_response({"totalHits": 1, "results": [{
        "id": 42, "title": "A forecast study", "yearPublished": 2024,
    }]}))
    monkeypatch.setattr(requests, "get", get)
    searcher = CoreSearcher(Config(api=APIConfig(core_api_key="core-fixture-key")))

    result = searcher.search("solar forecasting", max_results=5, year_min=2024)

    assert get.call_args.kwargs["headers"] == {"Authorization": "Bearer core-fixture-key"}
    assert result.articles[0].url == "https://core.ac.uk/works/42"
    assert result.articles[0].is_open_access is False


def test_journal_suggestions_report_thread_local_rate_limit(monkeypatch):
    monkeypatch.setattr(requests, "get", Mock(return_value=json_response({}, 429)))
    client, _, _ = make_client()
    client.app.dependency_overrides[get_journal_searcher] = lambda: OpenAlexSearcher(Config())

    body = client.get("/api/v1/journals/suggest", params={"q": "solar research"}).json()

    assert body["journals"] == []
    assert body["provider_status"]["status"] == "rate_limited"


def test_malformed_paper_url_falls_back_to_doi_without_losing_other_results():
    provider = FixtureSearcher(Config(), "OpenAlex", [
        Article("Malformed landing page", "https://[broken", doi="10.1000/solar", keywords=[None]),
        Article("Valid landing page", "https://example.org/solar"),
    ])
    client, _, _ = make_client(fixture_engine(provider))
    response = client.get("/api/v1/search", params={"q": "solar", "providers": "openalex"})

    assert response.status_code == 200
    assert [paper["url"] for paper in response.json()["results"]] == [
        "https://doi.org/10.1000/solar", "https://example.org/solar",
    ]


def test_trends_do_not_assume_a_topic_was_absent_from_a_truncated_baseline():
    baseline = {"meta": {"count": 1000}, "group_by": [
        {"key": f"T{n}", "count": 10} for n in range(discovery.GROUP_PAGE_SIZE)
    ]}
    recent = {"meta": {"count": 1000}, "group_by": [
        {"key": "T101", "count": 40}, {"key": "T1", "count": 15},
    ]}

    assert [item["id"] for item in discovery._trends(baseline, recent)] == ["T1"]


def test_large_pubmed_requests_use_post_for_document_summaries(monkeypatch):
    ids = [str(index) for index in range(1, 202)]
    get = Mock(return_value=json_response({"esearchresult": {"count": "201", "idlist": ids}}))
    post = Mock(return_value=json_response({"result": {uid: {"title": f"Article {uid}"} for uid in ids}}))
    monkeypatch.setattr(requests, "get", get)
    monkeypatch.setattr(requests, "post", post)

    result = PubMedSearcher(Config()).search("solar", max_results=201)

    assert result.count == 201
    assert post.call_args.kwargs["data"]["id"] == ",".join(ids)
    assert get.call_count == post.call_count == 1


def test_scopus_preserves_first_batch_when_second_request_is_rate_limited(monkeypatch):
    get = Mock(side_effect=[
        json_response({"search-results": {"opensearch:totalResults": "500", "entry": [{"id": n} for n in range(25)]}}),
        json_response({}, 429),
    ])
    monkeypatch.setattr(requests, "get", get)
    monkeypatch.setattr("academic_search.providers.time.sleep", Mock())
    searcher = ScopusSearcher(Config(api=APIConfig(elsevier_api_key="fixture-key")))
    searcher._parse_entry = lambda hit: Article(f"Paper {hit['id']}", f"https://example.org/{hit['id']}")

    result = fixture_engine(searcher).search("solar OR wind", max_results=26, year_min=2024, use_all_sources=True)

    assert result.count == 25
    assert result.provider_outcomes[0].status == "rate_limited"
    assert get.call_args_list[0].kwargs["params"]["query"] == "(solar OR wind) AND PUBYEAR > 2023"


def test_sciencedirect_keeps_full_year_and_reports_timeout(monkeypatch):
    get = Mock(side_effect=requests.Timeout)
    monkeypatch.setattr(requests, "get", get)
    searcher = ScienceDirectSearcher(Config(api=APIConfig(elsevier_api_key="fixture-key")))

    result = fixture_engine(searcher).search("solar", max_results=3, year_min=2024, year_max=2024, use_all_sources=True)

    assert result.provider_outcomes[0].error_code == "timeout"
    assert "pub-date AFT 20231231" in get.call_args.kwargs["params"]["query"]
    assert "pub-date BEF 20250101" in get.call_args.kwargs["params"]["query"]


def test_google_scholar_exposes_search_snippets_separately_from_abstracts(monkeypatch):
    response = Mock(status=200)
    response.read.return_value = json.dumps({"organic": [{
        "title": "Energy forecasting", "link": "https://example.org/solar", "snippet": "A result snippet.",
        "publicationInfo": "Researcher - 2024 - Journal",
    }]}).encode()
    connection = Mock()
    connection.getresponse.return_value = response
    monkeypatch.setattr("http.client.HTTPSConnection", Mock(return_value=connection))
    monkeypatch.setattr("academic_search.providers.time.sleep", Mock())
    searcher = GoogleScholarSearcher(Config(api=APIConfig(serper_api_key="fixture-key")))
    client, _, _ = make_client(fixture_engine(searcher))

    body = client.get("/api/v1/search", params={
        "q": "solar forecasting", "providers": "google-scholar", "limit": 1, "year_max": 2024,
    }).json()

    assert body["results"][0]["abstract"] is None
    assert body["results"][0]["search_snippet"] == "A result snippet."
    assert "before:2025-01-01" in json.loads(connection.request.call_args.args[2])["q"]
    connection.close.assert_called_once()
