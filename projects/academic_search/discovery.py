"""OpenAlex discovery within a reproducible, query-defined publication corpus."""

from datetime import datetime, timedelta, timezone
from typing import Any, Callable, Dict, Optional

from .models import Article
from .providers import OpenAlexSearcher

GROUP_PAGE_SIZE = OpenAlexSearcher.PAGE_SIZE


def _works(searcher: OpenAlexSearcher, params: Dict[str, Any], key: str):
    searcher.clear_last_failure()
    payload = searcher._make_request(
        f"{searcher.BASE_URL}/works", {**params, "mailto": searcher.email}
    )
    if not isinstance(payload, dict) or not isinstance(payload.get(key), list):
        failure = searcher.last_failure or {"code": "invalid_response", "message": "Invalid OpenAlex response"}
        return None, failure
    if key == "group_by":
        meta = payload.get("meta")
        if not isinstance(meta, dict) or not isinstance(meta.get("count"), int) or meta["count"] < 0:
            return None, {"code": "invalid_response", "message": "OpenAlex did not return a valid publication count"}
    return payload, None


def _group(data):
    return {
        str(item["key"]).rsplit("/", 1)[-1]: (item.get("key_display_name") or item["key"], item["count"])
        for item in data.get("group_by", [])
        if isinstance(item, dict) and item.get("key") and isinstance(item.get("count"), int)
        and str(item["key"]).rsplit("/", 1)[-1].startswith("T")
    }


def _trends(prior, recent):
    if not prior or not recent:
        return []
    old_total = (prior.get("meta") or {}).get("count")
    new_total = (recent.get("meta") or {}).get("count")
    if not isinstance(old_total, int) or not isinstance(new_total, int) or min(old_total, new_total) <= 0:
        return []
    old = _group(prior)
    new = _group(recent)
    results = []
    for key, (label, count) in new.items():
        if key not in old and len(prior["group_by"]) >= GROUP_PAGE_SIZE:
            continue
        old_count = old.get(key, ("", 0))[1]
        prior_share, recent_share = 100 * old_count / old_total, 100 * count / new_total
        results.append({
            "id": key, "name": label, "baseline_count": old_count, "recent_count": count,
            "baseline_share": round(prior_share, 3), "recent_share": round(recent_share, 3),
            "change_pp": round(recent_share - prior_share, 3),
            "sparse": min(old_total, new_total) < 30 or count < 5,
        })
    return sorted(results, key=lambda row: (row["sparse"], -row["change_pp"], -row["recent_count"], row["name"]))[:12]


def _compare_periods(searcher, query, corpus_filter, windows):
    periods, errors = [], {}
    trend_data = []
    for label, start, end, date_filter in windows:
        payload, error = _works(searcher, {
            "search": query, "filter": f"{corpus_filter},{date_filter}",
            "group_by": "primary_topic.id", "per_page": GROUP_PAGE_SIZE,
        }, "group_by")
        trend_data.append(payload)
        if error:
            errors[label] = error
        periods.append({
            "label": label, "from": start, "to": end,
            "total": ((payload or {}).get("meta") or {}).get("count"),
            "truncated": bool(payload and len(payload["group_by"]) >= GROUP_PAGE_SIZE),
        })
    return periods, _trends(*trend_data), errors


def daily_trends(searcher, query, day):
    """Compare two complete 30-day windows ending before the edition date."""
    windows = []
    for label, start_offset in (("baseline", 60), ("recent", 30)):
        start = day - timedelta(days=start_offset)
        end = start + timedelta(days=29)
        windows.append((label, start.isoformat(), end.isoformat(),
                        f"from_publication_date:{start},to_publication_date:{end}"))
    periods, trends, errors = _compare_periods(searcher, query, "is_retracted:false,type:article|review", windows)
    return {"provider": "OpenAlex", "periods": periods, "errors": errors,
            "topics": [topic for topic in trends if topic["change_pp"] > 0][:5],
            "retrieved_at": datetime.now(timezone.utc).isoformat()}


def discover(
    searcher: OpenAlexSearcher, query: str, field: str, include_preprints: bool,
    serialize: Callable[[Article], Optional[Dict[str, Any]]],
) -> Dict[str, Any]:
    now = datetime.now(timezone.utc)
    field_filter = f",primary_topic.field.id:{field}" if field else ""
    corpus_filter = "is_retracted:false,type:article|review" + field_filter
    windows = [(label, f"{year}-01-01", f"{year}-12-31", f"publication_year:{year}")
               for label, year in (("baseline", now.year - 2), ("recent", now.year - 1))]
    periods, trends, errors = _compare_periods(searcher, query, corpus_filter, windows)
    work_type = "article|review|preprint" if include_preprints else "article|review"
    latest_filter = f"is_retracted:false,type:{work_type}{field_filter},to_publication_date:{now.date().isoformat()}"
    latest, error = _works(searcher, {
        "search": query, "filter": latest_filter, "sort": "publication_date:desc", "per_page": 20,
    }, "results")
    if error:
        errors["latest"] = error
    return {
        "query": query, "field": field, "include_preprints": include_preprints, "periods": periods,
        "trends": trends, "papers": _papers(searcher, latest, serialize),
        "errors": errors, "retrieved_at": now.isoformat(), "provider": "OpenAlex",
        "method": "Primary topic share of matching articles and reviews in two completed calendar years",
        "filters": {"trends": corpus_filter, "latest": latest_filter},
        "coverage": "OpenAlex classifications and indexing can change. Sparse comparisons are flagged.",
    }


def _papers(searcher, payload, serialize):
    papers = []
    for work in (payload or {}).get("results", []):
        article = searcher._parse_work(work)
        paper = serialize(article) if article else None
        if paper:
            papers.append({
                **paper, "publication_date": work.get("publication_date"), "work_type": work.get("type"),
                "primary_topic": work.get("primary_topic") or {},
            })
    return papers


def representative_papers(searcher, snapshot, topic_id, serialize):
    end = snapshot["periods"][1]["to"]
    start = snapshot["periods"][1]["from"]
    filters = f'{snapshot["filters"]["trends"]},primary_topic.id:{topic_id},from_publication_date:{start},to_publication_date:{end}'
    payload, error = _works(searcher, {
        "search": snapshot["query"], "filter": filters, "sort": "publication_date:desc", "per_page": 8,
    }, "results")
    return {
        "papers": _papers(searcher, payload, serialize), "error": error, "filters": filters,
        "retrieved_at": datetime.now(timezone.utc).isoformat(), "topic_id": topic_id,
    }
