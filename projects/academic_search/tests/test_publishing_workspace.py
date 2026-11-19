from datetime import datetime, timezone
from unittest.mock import Mock

from academic_search import submission_sources
from academic_search.config import APIConfig, Config
from academic_search.engine import AcademicSearchEngine
from academic_search.models import ProviderOutcome, SearchResult
from academic_search.providers import OpenAlexSearcher
from academic_search.service import get_journal_searcher
from academic_search.tests.test_service import make_client


def project(client, name="Energy systems"):
    return client.post("/api/v1/projects", json={"name": name}).json()["id"]


def workspace(project_id, path):
    return f"/api/v1/projects/{project_id}/workspace/{path}"


def save(client, project_id, section, data, entry=None):
    path = workspace(project_id, section)
    if entry:
        return client.put(f"{path}/{entry['id']}", json={"data": data, "revision": entry["revision"]})
    return client.post(path, json={"data": data})


def shortlist(client, project_id, query="electricity forecasting"):
    result = client.get("/api/v1/search", params={"q": query, "project_id": project_id}).json()
    selection = {"kind": "search", "run_id": result["search_run_id"], "paper_url": result["results"][0]["url"]}
    return client.post(workspace(project_id, "reading/from-source"), json=selection).json(), selection


def test_openalex_rate_limit_is_visible_through_parallel_search(monkeypatch):
    engine = AcademicSearchEngine(Config(api=APIConfig(openalex_api_key="fixture-key")))
    client, _, _ = make_client(engine)
    response = Mock(status_code=429)
    get = Mock(return_value=response)
    monkeypatch.setattr("requests.get", get)

    payload = client.get("/api/v1/search", params={"q": "energy data", "providers": "openalex"}).json()

    assert payload["provider_coverage"][0]["status"] == "rate_limited"
    assert payload["results"] == []
    args = get.call_args.kwargs
    assert args["headers"] == {"Authorization": "Bearer fixture-key"}
    assert "fixture-key" not in str(args["params"])


def test_failed_journal_snapshot_remains_in_history_and_is_retried():
    client, _, searcher = make_client()
    pid = project(client)
    failed = SearchResult(query="energy", provider_outcomes=[ProviderOutcome("OpenAlex", "rate_limited")])
    searcher.search_journal = Mock(side_effect=[failed, failed])
    body = {"project_id": pid, "journal": {"id": "S123", "display_name": "Test Journal"}, "topics": ["energy"]}
    first = client.post("/api/v1/journals/search", json=body).json()
    second = client.post("/api/v1/journals/search", json=body).json()
    assert first["id"] != second["id"]
    fit = client.post(f"/api/v1/journal-searches/{first['id']}/fit", json={"project_id": pid, "title": "Energy"})
    assert fit.status_code == 422
    assert searcher.search_journal.call_count == 2


def test_discovery_uses_equal_windows_and_saves_paper_with_source(monkeypatch):
    client, _, _ = make_client()
    pid = project(client)
    other = project(client, "Another project")
    searcher = OpenAlexSearcher(Config())
    client.app.dependency_overrides[get_journal_searcher] = lambda: searcher
    work = {
        "id": "https://openalex.org/W42", "title": "Demand forecasting across regions",
        "publication_date": "2025-10-02", "publication_year": 2025, "type": "preprint",
        "primary_topic": {"id": "https://openalex.org/T10001", "display_name": "Forecasting"},
    }
    requests = []

    def openalex(_, params):
        requests.append(params)
        if "group_by" in params:
            year = int(params["filter"].split("publication_year:")[1])
            recent = year == datetime.now(timezone.utc).year - 1
            return {"meta": {"count": 200 if recent else 100}, "group_by": [
                {"key": "https://openalex.org/T10001", "key_display_name": "Forecasting", "count": 40 if recent else 10}
            ]}
        return {"results": [work]}

    monkeypatch.setattr(searcher, "_make_request", openalex)
    response = client.post(workspace(pid, "discover"), json={"query": "energy demand", "field": "1702", "include_preprints": True})
    assert response.status_code == 201
    entry = response.json()
    assert entry["data"]["trends"][0]["change_pp"] == 10
    assert [period["total"] for period in entry["data"]["periods"]] == [100, 200]
    assert all("primary_topic.field.id:1702" in request["filter"] for request in requests)
    assert requests[-1]["sort"] == "publication_date:desc"
    assert "preprint" in requests[-1]["filter"] and "preprint" not in requests[0]["filter"]
    assert entry["data"]["papers"][0]["work_type"] == "preprint"
    assert client.post(workspace(pid, f"discover/{entry['id']}/topics/T99999")).status_code == 404
    sample = client.post(workspace(pid, f"discover/{entry['id']}/topics/T10001")).json()
    assert "primary_topic.id:T10001" in sample["data"]["filters"]

    selection = {"kind": "discovery", "run_id": entry["id"], "paper_url": work["id"]}
    assert client.post(workspace(other, "reading/from-source"), json=selection).status_code == 404
    shortlisted = client.post(workspace(pid, "reading/from-source"), json=selection).json()
    assert shortlisted["data"]["origin"] == selection
    assert client.post(workspace(pid, "reading/from-source"), json=selection).json()["id"] == shortlisted["id"]
    updated = save(client, pid, "reading", {
        "status": "included", "limitations": "The experiment covers one region.",
        "population": "urban grids", "locator": "Discussion p. 9",
    }, shortlisted)
    assert updated.status_code == 200
    suggestions = client.get(workspace(pid, "discover/gaps")).json()["items"]
    assert suggestions[0]["status"] == "candidate"
    assert suggestions[0]["evidence"] == [shortlisted["id"]]
    assert suggestions[0]["source_url"] == work["id"]
    assert suggestions[0]["locator"] == "Discussion p. 9"


def notice(html):
    value = submission_sources._Notice()
    value.feed(html)
    return value


def test_official_call_search_verification_history_and_deadline(monkeypatch):
    client, _, _ = make_client()
    pid = project(client)
    url = "https://link.springer.com/collections/forecasting"
    searcher = OpenAlexSearcher(Config())
    client.app.dependency_overrides[get_journal_searcher] = lambda: searcher
    metadata = {"id": "https://openalex.org/S123", "display_name": "Energy Forecasting", "type": "journal"}
    monkeypatch.setattr(searcher, "_make_request", Mock(return_value={"results": [{"primary_location": {"source": metadata}}]}))
    monkeypatch.setattr(searcher, "resolve_journal", Mock(return_value={"homepage_url": url}))
    checks = {
        "html": """<h1>Energy Forecasting</h1><p>Open for submissions</p>
            <dt>Submission deadline</dt><dd>31 December 2099</dd>
            <p>Accepted article types: Original research.</p>
            <a href="/journal/123/submission-guidelines">Submission guidelines</a>
            <a href="https://www.editorialmanager.com/test">Submit to this journal</a>"""
    }

    def read(address, params=None):
        assert address == url
        return notice(checks["html"])

    monkeypatch.setattr(submission_sources, "_read", read)
    result = client.get(workspace(pid, "submission-search"), params={"q": "forecasting"}).json()
    assert searcher._make_request.call_args.args[1]["search"] == "forecasting"
    assert len(result["items"]) == 1 and result["items"][0]["status"] == "open"
    assert result["items"][0]["sample_count"] == 1
    assert "query=forecasting" in result["sources"][0]["url"]
    response = save(client, pid, "submissions", {"source_url": url, "title": "Energy Forecasting",
                    "kind": "special_issue", "verify_from_source": True})
    assert response.status_code == 201
    entry = response.json()
    assert entry["data"]["deadline"] == "2099-12-31"
    assert entry["data"]["article_types"] == "Original research"
    assert entry["display_status"] == "open"
    checks["html"] = "<h1>Energy Forecasting</h1><p>Closed for submissions</p>"
    refreshed = client.post(workspace(pid, f"submissions/{entry['id']}/verify")).json()
    assert refreshed["display_status"] == "closed"
    revisions = client.get(workspace(pid, f"submissions/{entry['id']}/history")).json()["items"]
    assert [revision["data"]["status"] for revision in revisions] == ["closed", "open"]
    assert save(client, pid, "submissions", {"title": "Unproven", "source_url": url, "status": "open"}).status_code == 422
    manual = save(client, pid, "submissions", {
        "title": "Conference", "source_url": "https://example.org/call", "kind": "conference",
        "status": "open", "evidence": "Issuer displayed an open call", "deadline": "2020-01-01",
    }).json()
    assert manual["display_status"] == "closed"
    assert client.post(workspace(pid, f"submissions/{manual['id']}/verify")).status_code == 422
    assert not submission_sources.official_page("https://link.springer.com.evil.example/collections/test")


def test_manuscript_review_references_exports_and_version_conflict():
    client, _, _ = make_client()
    pid = project(client)
    other = project(client, "Separate topic")
    source, _ = shortlist(client, pid)
    idea = save(client, pid, "ideas", {
        "question": "Can demand forecasts generalize across regions?", "evidence": [source["id"]],
        "method": "Out-of-region evaluation", "data_source": "Open power consumption records",
    }).json()
    assert save(client, other, "ideas", {"question": "Foreign citation", "evidence": [source["id"]]}).status_code == 422
    draft = save(client, pid, "manuscripts", {"title": "External validity of energy forecasts", "idea_id": idea["id"]}).json()
    data = draft["data"]
    assert data["sections"][1]["text"] == idea["data"]["question"]
    data["sections"][0]["text"] = "Four words in abstract"
    data["claims"] = [
        {"section": "Introduction", "text": "Algorithms improve reliability", "references": [source["id"]],
         "locator": "Abstract", "review": "supported"},
        {"section": "Discussion", "text": "Transfer to rural grids remains uncertain"},
    ]
    data["requirements"] = {"abstract_limit": 2, "abstract_headings": ["Methods"], "declarations_required": ["Funding"]}
    response = save(client, pid, "manuscripts", data, draft)
    assert response.status_code == 200
    assert save(client, pid, "manuscripts", data, draft).status_code == 409
    review = client.get(workspace(pid, f"manuscripts/{draft['id']}/review")).json()
    assert review["abstract_words"] == 4
    assert any("Claim needs linked evidence" in issue["message"] for issue in review["issues"])
    assert any("Missing heading Methods" in issue["message"] for issue in review["issues"])
    path = workspace(pid, f"manuscripts/{draft['id']}/export")
    assert "Funding needs review" in client.get(path).text
    assert "10.1000/example" in client.get(path + "?format=bibtex").text
    assert "TY  - JOUR" in client.get(path + "?format=ris").text
    assert client.get(workspace(other, f"manuscripts/{draft['id']}/review")).status_code == 404
    history = client.get(workspace(pid, f"manuscripts/{draft['id']}/history")).json()["items"]
    assert [version["revision"] for version in history] == [2, 1]


def test_dossier_requires_dated_evidence_and_preserves_target_context():
    client, _, _ = make_client()
    pid = project(client)
    source, _ = shortlist(client, pid)
    target = {"route": "docentlik", "field": "Engineering", "period": "2027 March", "criteria_url": "https://www.uak.gov.tr/example"}
    criterion = {"title": "Indexed original publication", "clause": "Table 1, item A", "official_url": target["criteria_url"]}
    assert save(client, pid, "dossier-rules", criterion).status_code == 422
    profile = save(client, pid, "dossier-profile", target).json()
    assert save(client, pid, "dossier-rules", {**criterion, "status": "reviewed"}).status_code == 422
    activity = save(client, pid, "dossier-activities", {
        "title": "Data systems", "kind": "publication", "reading_id": source["id"], "evidence_date": "2026-04-01",
        "author_role": "First author", "publication_status": "published",
        "index_name": "TR Dizin", "index_year": 2026, "index_url": "https://search.trdizin.gov.tr/record",
    }).json()
    matched = save(client, pid, "dossier-rules", {**criterion, "status": "reviewed", "activity_ids": [activity["id"]]})
    assert matched.status_code == 201
    report = client.get(workspace(pid, "dossier/export")).text
    assert "Table 1, item A" in report and "2026-04-01" in report and "TR Dizin (2026)" in report
    assert save(client, pid, "dossier-activities", {**activity["data"], "author_role": "Coauthor"}, activity).status_code == 200
    rule = client.get(workspace(pid, "dossier-rules")).json()["items"][0]
    assert rule["data"]["status"] == "reviewed" and rule["display_status"] == "in_review"
    assert save(client, pid, "dossier-profile", {**target, "period": "2027 October"}, profile).status_code == 200
    assert "Table 1, item A" not in client.get(workspace(pid, "dossier/export")).text
