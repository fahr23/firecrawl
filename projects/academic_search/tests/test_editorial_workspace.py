"""End-to-end coverage for direct calls, manuscript recovery, and model help."""

from datetime import date, timedelta
from io import BytesIO
import json
from unittest.mock import Mock
from zipfile import ZipFile

from docx import Document
import pytest

from academic_search import special_issues, submission_sources, workspace_assistant
from academic_search.service import get_journal_searcher
from academic_search.tests.test_research_workflow import topic, workspace
from academic_search.tests.test_service import make_client


def manuscript(client, project, title="Evidence synthesis"):
    response = workspace(client, project, "manuscripts", {"title": title, "article_type": "original"})
    assert response.status_code == 201
    return response.json()


def reading(client, project):
    papers = client.get("/api/v1/search", params={"q": "machine learning", "project_id": project}).json()
    response = client.post(f"/api/v1/projects/{project}/workspace/reading/from-source", json={
        "kind": "search", "run_id": papers["search_run_id"], "paper_url": papers["results"][0]["url"],
    })
    assert response.status_code == 201
    return response.json()


def notice(html):
    result = submission_sources._Notice()
    result.feed(html)
    return result


def test_sage_index_can_filter_verified_calls_and_alert_on_a_deadline_change(monkeypatch):
    client, _, _ = make_client()
    pid = topic(client, "Energy forecasting")
    draft = manuscript(client, pid)
    due = date.today() + timedelta(days=10)
    abstract_due = (date.today() + timedelta(days=4)).isoformat()
    first = due.isoformat()
    read = Mock()

    def publisher(url, params=None):
        assert url == special_issues.PUBLISHERS["sage"][1]
        return notice(f"""
        <h1>Open Call for Papers</h1>
        <p><a href="/home/forecast">Journal of Forecasting</a></p>
        <a href="/pb-assets/cmscontent/forecast/special-paper.pdf">Special issue on energy forecasting</a>
        <p>Abstract proposal due {abstract_due}.</p><p>Submission deadline: {due.isoformat()}</p>
        <p><a href="/home/wind">Other Journal</a></p>
        <a href="/pb-assets/cmscontent/wind/general.pdf">General Call for Papers</a><p>Submission deadline: Ongoing</p>""")

    read.side_effect = publisher
    monkeypatch.setattr(submission_sources, "_read", read)
    filters = {"q": "energy forecasting", "journal": "journal of forecasting", "publisher": "sage",
               "open_only": True, "deadline_to": (due + timedelta(days=2)).isoformat()}
    found = client.get("/api/v1/special-issues", params=filters).json()
    [call] = found["items"]
    assert call["deadline"] == first and call["abstract_deadline"] == abstract_due
    assert call["status"] == "open"
    assert found["sources"][0]["status"] == "checked"
    assert client.get("/api/v1/special-issues", params={**filters, "deadline_to": date.today().isoformat()}).json()["items"] == []
    assert read.call_count == 1

    save_route = f"/api/v1/special-issues/{call['id']}/save"
    attached = client.post(save_route, json={"project_id": pid, "draft_id": draft["id"]})
    assert attached.status_code == 201, attached.text
    opportunity = attached.json()
    assert client.post(save_route, json={"project_id": pid, "draft_id": draft["id"]}).json()["id"] == opportunity["id"]
    target = client.get(f"/api/v1/projects/{pid}/workspace/manuscripts").json()["items"][0]
    assert target["revision"] == 2 and target["data"]["submission_id"] == opportunity["id"]

    due += timedelta(days=5)
    assert client.get("/api/v1/special-issues", params={**filters, "refresh": True}).json()["items"] == []
    home = client.get("/api/v1/today").json()
    assert home["deadlines"][0]["date"] == due.isoformat()
    assert home["alerts"][0]["changes"]["deadline"] == {"before": first, "after": due.isoformat()}
    alert = home["alerts"][0]["id"]
    assert client.post(f"/api/v1/special-issue-alerts/{alert}/dismiss").status_code == 200
    assert client.get("/api/v1/today").json()["alerts"] == []


def test_direct_official_call_uses_manuscript_deadline_and_rejects_unapproved_urls(monkeypatch):
    client, _, _ = make_client()
    future = (date.today() + timedelta(days=100)).isoformat()
    proposal = (date.today() + timedelta(days=10)).isoformat()
    url = "https://think.taylorandfrancis.com/special_issues/forecasting/"
    read = Mock(return_value=notice(f"""
    <h1>Forecasting Research</h1>
    <h2>Forecasting for resilience</h2>
    <h3>Abstract deadline</h3><p>{proposal}</p>
    <h3>Manuscript deadline</h3><p>{future}</p>
    <a href="https://www.tandfonline.com/forecast">Submit an article to Forecasting Research</a>
    """))
    monkeypatch.setattr(submission_sources, "_read", read)
    reply = client.post("/api/v1/special-issues/verify", json={"url": url})
    assert reply.status_code == 200
    assert reply.json()["venue"] == "Forecasting Research"
    assert reply.json()["deadline"] == future and reply.json()["status"] == "open"
    assert reply.json()["source_url"].startswith("https://callforpapers.taylorandfrancis.com/")
    assert client.post("/api/v1/special-issues/verify", json={"url": "https://example.com/call"}).status_code == 422
    assert read.call_count == 1


def test_dergipark_search_and_issn_resolution_use_public_journal_notices(monkeypatch):
    client, _, _ = make_client()
    root = "https://dergipark.org.tr/en/pub/forecast-research"
    call = root + "/announcements/725"
    alex = Mock()
    alex.resolve_journal_by_issn.return_value = {"display_name": "Forecast Research"}
    alex.suggest_journals.return_value = [{"homepage_url": root}, {"homepage_url": "https://example.com/journal"}]
    client.app.dependency_overrides[get_journal_searcher] = lambda: alex
    deadline = (date.today() + timedelta(days=100)).isoformat()
    saved = {
        root + "/announcements": notice('<a href="/en/pub/forecast-research/announcements/725">Energy special issue</a>'),
        call: notice(f"<h1>Forecast Research</h1><h1>Energy special issue</h1>"
                     f"<p>Our journal invites original research papers.</p><p>Submission Deadline: {deadline}</p>"),
    }
    monkeypatch.setattr(submission_sources, "_read", lambda url, params=None: saved[url])
    result = client.get("/api/v1/special-issues", params={
        "q": "energy", "journal": "2049-3630", "publisher": "dergipark", "open_only": True,
    }).json()
    assert result["sources"][0]["status"] == "checked"
    assert result["items"][0]["source_url"] == call and result["items"][0]["deadline"] == deadline
    alex.resolve_journal_by_issn.assert_called_once_with("2049-3630")
    alex.suggest_journals.assert_called_once_with("Forecast Research", 8)


def test_parallel_drafts_autosave_today_and_word_export_with_inline_references():
    client, _, _ = make_client()
    pid = topic(client, "Research methods")
    other = topic(client, "Another subject")
    ref = reading(client, pid)
    brief = workspace(client, pid, "ideas", {
        "question": "How far do the results generalize?", "data_access": "to_check",
        "constraints": "Access to historical metadata is needed.",
        "next_step": "Compare sampling frames.", "evidence": [ref["id"]],
    }).json()
    original = manuscript(client, pid, "First draft")
    independent = manuscript(client, pid, "Second draft")
    foreign = manuscript(client, other, "Different topic")
    base = f"/api/v1/projects/{pid}/workspace/manuscripts"
    url = f"{base}/{original['id']}"
    first_doc = {**original["data"], "stage": "drafting", "next_action": "Verify the evidence",
                 "idea_id": brief["id"], "action_due": date.today().isoformat(),
                 "sections": [{"heading": "Introduction", "text": "Earlier work used linked data [@ref1]."}],
                 "inline_citations": {"ref1": ref["id"]}}
    request = {"revision": 1, "autosave_version": 0, "data": first_doc}
    buffer = client.put(f"{url}/autosave", json=request)
    assert buffer.status_code == 200, buffer.text
    assert client.put(f"{url}/autosave", json=request).status_code == 409
    assert client.get(f"{base}/{independent['id']}/autosave").json() == {"item": None}
    assert client.get(f"{base}/{foreign['id']}/autosave").status_code == 404
    assert client.get(f"{url}/autosave").json()["item"]["data"] == first_doc
    today = client.get("/api/v1/today").json()
    assert today["manuscripts"][0]["next_action"] == "Verify the evidence"

    exported = client.get(f"{url}/export", params={"format": "docx"})
    assert exported.status_code == 200
    archive = ZipFile(BytesIO(exported.content))
    assert archive.testzip() is None
    document = Document(BytesIO(exported.content))
    text = "\n".join(p.text for p in document.paragraphs)
    assert "Earlier work used linked data [1]." in text
    assert ref["data"]["paper"]["title"] in text and "[@ref1]" not in text
    assert client.put(url, json=request).status_code == 409
    manual = client.put(url, json={**request, "autosave_version": 1})
    assert manual.json()["revision"] == 2
    assert client.get(f"{url}/autosave").json()["item"] is None
    assert len(client.get(f"{url}/history").json()["items"]) == 2


@pytest.mark.parametrize("provider,variable,model_variable", [
    ("openai", "OPENAI_API_KEY", "ACADEMIC_OPENAI_MODEL"),
    ("anthropic", "ANTHROPIC_API_KEY", "ACADEMIC_ANTHROPIC_MODEL"),
])
def test_llm_actions_are_opt_in_and_limit_citations_to_existing_evidence(monkeypatch, provider, variable, model_variable):
    client, _, _ = make_client()
    pid = topic(client, "Estimation")
    ref = reading(client, pid)
    monkeypatch.delenv(variable, raising=False)
    monkeypatch.setenv(model_variable, "fixture-model")
    url = f"/api/v1/projects/{pid}/assistant"
    request = {"action": "evidence", "provider": provider, "reading_ids": [ref["id"]]}
    assert client.post(url, json=request).status_code == 503
    monkeypatch.setenv(variable, "fixture-key")
    answer = {"suggestions": [{"text": "Check the sampling frame.", "source_ids": ["P1"]}], "gaps": ["No second study."]}

    def response(value):
        text = json.dumps(value)
        if provider == "openai":
            body = {"output": [{"type": "message", "content": [{"type": "output_text", "text": text}]}]}
        else:
            body = {"content": [{"type": "text", "text": text}]}
        return Mock(status_code=200, json=Mock(return_value=body))

    post = Mock(side_effect=[response(answer), response({
        **answer, "suggestions": [{"text": "Unsupported citation", "source_ids": ["invented"]}],
    })])
    monkeypatch.setattr(workspace_assistant.requests, "post", post)
    status = client.get("/api/v1/assistant/providers")
    assert "fixture-key" not in status.text
    assert post.call_count == 0
    accepted = client.post(url, json=request)
    assert accepted.status_code == 200
    assert accepted.json()["sources"][0]["url"] == ref["data"]["paper"]["url"]
    headers = post.call_args.kwargs["headers"]
    assert headers["Authorization"] == "Bearer fixture-key"
    assert "fixture-key" not in json.dumps(post.call_args.kwargs["json"])
    assert client.post(url, json=request).status_code == 502
