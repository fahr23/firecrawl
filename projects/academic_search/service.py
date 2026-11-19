"""Persistent HTTP service and UI for the academic-search package."""

from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager, suppress
import os
from datetime import date, datetime, timezone
from functools import lru_cache
from itertools import chain
from pathlib import Path
from typing import Any, Dict, Iterable, List, Literal, Optional
from urllib.parse import urlparse

from fastapi import Depends, FastAPI, HTTPException, Query, Request
from fastapi.concurrency import run_in_threadpool
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from requests import RequestException

from .engine import AcademicSearchEngine
from .config import Config
from .daily_api import daily_router, daily_scheduler
from .journal_analysis import (
    ARTICLE_ALIGNMENT_VERSION,
    FIT_VERSION,
    PROFILE_VERSION,
    annotate_topic_alignment,
    build_journal_profile,
    manuscript_fit,
)
from .journal_catalog import CATALOG_PROVIDERS, JournalCatalogService
from .journal_favorites import journal_favorites_router, scheduler as journal_favorites_scheduler
from .models import Article, ProviderOutcome, SearchResult
from .project_store import DuplicateProjectName, ProjectStore
from .providers import OpenAlexSearcher
from .publishing_api import router_for_publishing
from .research_workspace import account_router, workspace_router
from .special_issues import scheduler as special_issue_scheduler
from .ubyt_catalog import UbytCatalog, article_issns
from .workflow_api import watch_scheduler, workflow_router


SERVICE_VERSION = "2.1.1"
MAX_SEARCH_PAGE = 10
MAX_SEARCH_SIZE = 50
WEB_DIR = Path(__file__).resolve().parent / "web"

# Categories are derived labels, not provider-supplied scholarly classifications.
CATEGORIES: Dict[str, Dict[str, Any]] = {
    "computer-science": {
        "label": "Computer science",
        "description": "AI, software, data, algorithms, and computing systems.",
        "keywords": (
            "algorithm", "artificial intelligence", "computer", "computing",
            "data science", "deep learning", "machine learning", "neural",
            "software", "information system",
        ),
    },
    "engineering": {
        "label": "Engineering",
        "description": "Applied engineering, manufacturing, control, and materials.",
        "keywords": (
            "engineering", "manufacturing", "control system", "robot",
            "materials", "mechanical", "electrical", "civil engineering",
        ),
    },
    "medicine-health": {
        "label": "Medicine & health",
        "description": "Clinical research, public health, biology, and care.",
        "keywords": (
            "clinical", "disease", "health", "medical", "medicine", "patient",
            "therapy", "biomedical", "epidemiology", "diagnosis",
        ),
    },
    "economics-finance": {
        "label": "Economics & finance",
        "description": "Markets, organizations, policy, accounting, and economics.",
        "keywords": (
            "accounting", "bank", "business", "economic", "economy", "finance",
            "financial", "market", "monetary", "investment",
        ),
    },
    "environment-energy": {
        "label": "Environment & energy",
        "description": "Climate, emissions, energy systems, and sustainability.",
        "keywords": (
            "climate", "carbon", "emission", "energy", "environment",
            "renewable", "sustainability", "solar", "wind power",
        ),
    },
    "social-sciences": {
        "label": "Social sciences",
        "description": "Society, education, behavior, institutions, and culture.",
        "keywords": (
            "behavior", "education", "policy", "political", "psychology",
            "social", "society", "sociology", "culture", "institution",
        ),
    },
    "multidisciplinary": {
        "label": "Multidisciplinary",
        "description": "Results without a strong match to one listed field.",
        "keywords": (),
    },
}

PROVIDERS = {
    "openalex": "OpenAlex",
    "semantic-scholar": "Semantic Scholar",
    "arxiv": "arXiv",
    "pubmed": "PubMed",
    "core": "CORE",
    "firecrawl-research": "Firecrawl Research",
    "science-direct": "ScienceDirect",
    "scopus": "Scopus",
    "google-scholar": "Google Scholar",
    "clarivate": "Web of Science",
}
PROVIDER_SOURCE_NAMES = {
    "openalex": "openalex",
    "semantic-scholar": "semantic scholar",
    "arxiv": "arxiv",
    "pubmed": "pubmed",
    "core": "core",
    "firecrawl-research": "firecrawl research",
    "science-direct": "sciencedirect",
    "scopus": "scopus",
    "google-scholar": "google scholar",
    "clarivate": "web of science",
}
DEFAULT_PROVIDERS = ("openalex",)


class ProjectCreate(BaseModel):
    name: str = Field(min_length=1, max_length=160)
    research_question: Optional[str] = Field(default=None, max_length=1000)
    default_category: str = "all"
    default_providers: str = "openalex"
    default_year_min: Optional[int] = Field(default=None, ge=1800, le=2200)
    default_year_max: Optional[int] = Field(default=None, ge=1800, le=2200)


class ProjectUpdate(BaseModel):
    name: Optional[str] = Field(default=None, min_length=1, max_length=160)
    research_question: Optional[str] = Field(default=None, max_length=1000)
    default_category: Optional[str] = None
    default_providers: Optional[str] = None
    default_year_min: Optional[int] = Field(default=None, ge=1800, le=2200)
    default_year_max: Optional[int] = Field(default=None, ge=1800, le=2200)


class JournalIdentity(BaseModel):
    id: str = Field(min_length=2, max_length=80)
    display_name: str = Field(min_length=1, max_length=300)
    issn_l: Optional[str] = Field(default=None, max_length=20)
    issns: List[str] = Field(default_factory=list, max_length=20)
    publisher: Optional[str] = Field(default=None, max_length=300)
    works_count: Optional[int] = Field(default=None, ge=0)
    is_oa: Optional[bool] = None
    is_in_doaj: Optional[bool] = None
    type: str = "journal"
    source: str = "OpenAlex"
    catalog_id: Optional[str] = None
    catalog_provider: str = "openalex"
    provider_id: Optional[str] = None
    categories: List[Dict[str, Any]] = Field(default_factory=list, max_length=50)
    identifiers: Dict[str, Any] = Field(default_factory=dict)
    provider_records: List[Dict[str, Any]] = Field(default_factory=list, max_length=10)
    search_supported: bool = True
    source_url: Optional[str] = None
    ubyt: Optional[Dict[str, Any]] = None


class JournalSearchRequest(BaseModel):
    project_id: Optional[str] = None
    journal: JournalIdentity
    topics: List[str] = Field(min_length=1, max_length=12)
    year_min: Optional[int] = Field(default=None, ge=1800, le=2200)
    year_max: Optional[int] = Field(default=None, ge=1800, le=2200)
    limit: int = Field(default=20, ge=1, le=50)
    refresh: bool = False


class ManuscriptFitRequest(BaseModel):
    project_id: str
    title: str = Field(default="", max_length=500)
    abstract: str = Field(default="", max_length=20000)
    keywords: List[str] = Field(default_factory=list, max_length=30)


def _cors_origins() -> List[str]:
    value = os.getenv("ACADEMIC_CORS_ORIGINS", "*")
    origins = [item.strip() for item in value.split(",") if item.strip()]
    return origins or ["*"]


def _safe_url(article: Article) -> Optional[str]:
    candidates = [article.url]
    if isinstance(article.doi, str) and article.doi_normalized:
        candidates.append(f"https://doi.org/{article.doi_normalized}")
    for candidate in candidates:
        if not isinstance(candidate, str) or not candidate.strip():
            continue
        candidate = candidate.strip()
        try:
            parsed = urlparse(candidate)
            if parsed.scheme in {"http", "https"} and parsed.hostname and not parsed.username and not parsed.password:
                return candidate
        except ValueError:
            continue
    return None


def _article_text(article: Article) -> str:
    return " ".join(
        [
            article.title or "",
            article.abstract or "",
            article.journal or "",
            " ".join(keyword for keyword in (article.keywords or []) if isinstance(keyword, str)),
        ]
    ).lower()


def derive_category(article: Article) -> str:
    """Assign a transparent keyword-derived category to an article."""
    text = _article_text(article)
    scores = {
        slug: sum(1 for keyword in data["keywords"] if keyword in text)
        for slug, data in CATEGORIES.items()
        if slug != "multidisciplinary"
    }
    best = max(scores, key=scores.get)
    return best if scores[best] else "multidisciplinary"


def _parse_providers(value: Optional[str]) -> List[str]:
    requested = [
        item.strip().lower()
        for item in (value or ",".join(DEFAULT_PROVIDERS)).split(",")
        if item.strip()
    ]
    unknown = sorted(set(requested) - set(PROVIDERS))
    if unknown:
        raise HTTPException(
            status_code=422,
            detail=f"Unknown provider(s): {', '.join(unknown)}",
        )
    return [PROVIDERS[item] for item in requested]


def _provider_coverage(provider_names: List[str], sources_responded: Iterable[str],
                       outcomes: Optional[Iterable[Dict[str, Any]]] = None) -> List[Dict[str, str]]:
    """Return explicit provider outcomes without collapsing failures into empties."""
    responded = {source.lower() for source in sources_responded}
    by_provider = {
        str(item.get("provider", "")).lower(): item
        for item in (outcomes or [])
    }
    coverage = []
    for provider in provider_names:
        outcome = by_provider.get(provider.lower(), {})
        item = {
            "provider": provider,
            "status": str(outcome.get("status", "responded" if provider.lower() in responded else "unavailable")),
        }
        if outcome.get("error_code"):
            item["error_code"] = outcome["error_code"]
        coverage.append(item)
    return coverage


def _project_store_path() -> str:
    return os.getenv("ACADEMIC_PROJECT_DB_PATH", "/tmp/academic-search-projects.db")


def get_project_store(request: Request) -> ProjectStore:
    return request.app.state.project_store


def _markdown_evidence(evidence: Dict[str, Any]) -> str:
    project = evidence["project"]
    lines = [f"# {project['name']} — search evidence", ""]
    if project.get("research_question"):
        lines.extend([f"Research question: {project['research_question']}", ""])
    lines.extend([
        "This export is a search-run ledger, not a curated reference library.",
        "Categories are derived keyword labels; source records remain provider-supplied.",
    ])
    for run in evidence["search_runs"]:
        lines.extend([
            "", f"## Query: {run['query']}",
            f"Retrieved: {run['retrieved_at']}",
            f"Filters: category={run['category']}; years={run['year_min'] or 'any'}–{run['year_max'] or 'any'}; limit={run['limit_value']}",
            f"Requested providers: {', '.join(run['providers_requested'])}",
            f"Responding sources: {', '.join(run['sources_responded']) or 'none recorded'}",
            f"Deduplication: {run.get('manifest', {}).get('deduplication_version', 'not recorded')}",
            "Provider outcomes: " + ", ".join(
                f"{item.get('provider')}: {item.get('status')}"
                for item in run.get("manifest", {}).get("provider_outcomes", [])
            ),
            "", "### Linked results",
        ])
        for paper in run["results"]:
            title = paper.get("title") or "Untitled paper"
            url = paper.get("url") or ""
            source = paper.get("source") or "Unknown source"
            journal = paper.get("journal") or "Journal not supplied"
            year = paper.get("year") or "Year not supplied"
            lines.append(f"- [{title}]({url}) — {source}; {journal}; {year}")
        if not run["results"]:
            lines.append("- No linked results were saved for this run.")
    for run in evidence.get("journal_search_runs", []):
        journal = run["journal"]
        lines.extend([
            "", f"## Journal snapshot: {journal.get('display_name', 'Unknown journal')}",
            f"Journal ID: {journal.get('id')}; ISSN-L: {journal.get('issn_l') or 'not supplied'}",
            _markdown_ubyt(journal.get("ubyt")),
            f"Topics: {', '.join(run['topics'])}",
            f"Retrieved: {run['retrieved_at']}",
            f"Profile provenance: {run['profile'].get('provenance')}",
            "", "### Matching papers",
        ])
        for paper in run["papers"]:
            lines.append(
                f"- [{paper.get('title') or 'Untitled paper'}]({paper.get('url') or ''}) "
                f"— {paper.get('year') or 'year not supplied'}; "
                f"topic alignment {paper.get('alignment', {}).get('score', 0)}/100"
            )
        if not run["papers"]:
            lines.append("- No linked results were saved for this journal snapshot.")
    for fit in evidence.get("journal_fit_runs", []):
        lines.extend([
            "", f"## Manuscript fit: {fit.get('manuscript', {}).get('title') or 'Untitled manuscript'}",
            f"Created: {fit.get('created_at')}",
            f"Journal snapshot: {fit.get('journal_search_id')}",
            f"Scope overlap: {fit.get('overall_score', 0)}/100",
            f"Analysis provenance: {fit.get('provenance')}",
            fit.get("disclaimer") or "",
        ])
    return "\n".join(lines) + "\n"


def _markdown_ubyt(entry: Optional[Dict[str, Any]]) -> str:
    if not entry:
        return "UBYT: journal not found on the bundled UBYT list"
    indexes = ", ".join(entry.get("indexes") or []) or "no WoS index"
    return (
        f"{entry.get('list')}: payment {entry.get('payment_tl')} TL; "
        f"MEP score {entry.get('mep_score')}; {indexes}; matched by {entry.get('matched_by')}"
    )


def _serialize_article(article: Article) -> Optional[Dict[str, Any]]:
    url = _safe_url(article)
    if not url:
        return None
    category = derive_category(article)
    snippet = (article.raw_data or {}).get("search_snippet") if article.source == "Google Scholar" else None
    raw = article.raw_data or {}
    date_keys = ("publication_date", "publicationDate", "publishedDate", "published_date", "prism:coverDate")
    publication_date = None
    for key in date_keys:
        value = raw.get(key)
        if isinstance(value, str) and len(value) >= 10 and value[4:5] == "-" and value[7:8] == "-":
            try:
                publication_date = date.fromisoformat(value[:10]).isoformat()
                break
            except ValueError:
                continue
    if not publication_date and article.source == "PubMed":
        for key in ("epubdate", "pubdate"):
            value = raw.get(key)
            if not isinstance(value, str):
                continue
            try:
                publication_date = datetime.strptime(value, "%Y %b %d").date().isoformat()
                break
            except ValueError:
                continue
    return {
        "title": article.title,
        "url": url,
        "doi": article.doi,
        "authors": article.authors,
        "journal": article.journal,
        "year": article.year,
        "publication_date": publication_date,
        **({"is_retracted": True} if raw.get("is_retracted") is True else {}),
        "abstract": article.abstract,
        **({"search_snippet": snippet} if snippet else {}),
        "source": article.source,
        "is_open_access": article.is_open_access,
        "citation_count": article.citation_count,
        "keywords": [keyword for keyword in (article.keywords or []) if isinstance(keyword, str)],
        "category": category,
        "category_label": CATEGORIES[category]["label"],
        "category_provenance": "derived:keyword-rules-v1",
        "field_provenance": article.field_provenance,
        "derived_outputs": article.derived_outputs,
        "ubyt": get_ubyt_catalog().match(article_issns(article.raw_data), article.journal),
    }


def _provider_availability(engine: AcademicSearchEngine) -> Dict[str, bool]:
    configured = {
        searcher.source_name.lower()
        for searcher in getattr(engine, "_searchers", [])
        if searcher.is_available
    }
    return {
        slug: any(PROVIDER_SOURCE_NAMES[slug] in name for name in configured)
        for slug in PROVIDERS
    }


@lru_cache(maxsize=1)
def get_search_engine() -> AcademicSearchEngine:
    return AcademicSearchEngine()


@lru_cache(maxsize=1)
def get_journal_searcher() -> OpenAlexSearcher:
    return OpenAlexSearcher(Config())


@lru_cache(maxsize=1)
def get_ubyt_catalog() -> UbytCatalog:
    return UbytCatalog()


@lru_cache(maxsize=1)
def get_journal_catalog_service() -> JournalCatalogService:
    return JournalCatalogService(Config(), get_ubyt_catalog())


def _refresh_recommended(retrieved_at: str) -> bool:
    try:
        value = retrieved_at.replace("Z", "+00:00")
        retrieved = datetime.fromisoformat(value)
        if retrieved.tzinfo is None:
            retrieved = retrieved.replace(tzinfo=timezone.utc)
        age_days = (datetime.now(timezone.utc) - retrieved).total_seconds() / 86400
        return age_days >= max(1, int(os.getenv("ACADEMIC_JOURNAL_REFRESH_DAYS", "7")))
    except (TypeError, ValueError):
        return True


def _journal_response(payload: Dict[str, Any], cache_status: str) -> Dict[str, Any]:
    return {
        **payload,
        "cache_status": cache_status,
        "refresh_recommended": _refresh_recommended(payload["retrieved_at"]),
    }


def _saved_response(library, query, category, provider_names, year_min, year_max, page, limit,
                    *, cached=None):
    if cached is not None:
        papers = cached["results"]
        source = "query_cache"
        fetched_at = cached["cache_fetched_at"]
        extra = cached.get("has_more", False)
    else:
        papers = library.search(query, category, provider_names, year_min, year_max, limit + 1, (page - 1) * limit)
        source = "library"
        fetched_at = max((paper["library_observed_at"] for paper in papers[:limit]), default=None)
        extra = len(papers) > limit
    results = [{**paper, "retrieval_kind": "saved"} for paper in papers[:limit]]
    return {
        "query": query, "category": category, "category_provenance": "derived:keyword-rules-v1",
        "providers_requested": provider_names, "sources_responded": [], "provider_outcomes": [],
        "provider_coverage": [], "retrieved_at": fetched_at, "search_time": None,
        "total_provider_matches": None, "results": results, "returned": len(results),
        "year_min": year_min, "year_max": year_max, "page": page, "limit": limit,
        "has_more": page < MAX_SEARCH_PAGE and extra,
        "pagination": {"max_page": MAX_SEARCH_PAGE, "partial": False, "window_limited": page == MAX_SEARCH_PAGE and extra},
        "cache": {"kind": "local", "source": source, "fetched_at": fetched_at,
                  "checked_at": None, "live_count": 0, "saved_count": len(results)},
        "manifest": {"query": query, "source": source, "retrieved_at": fetched_at,
                     "provider_attempt": False, "cached_manifest": cached.get("manifest") if cached is not None else None},
    }


def _add_saved_fallback(library, payload, signature, failed_providers):
    if not failed_providers or len(payload["results"]) >= payload["limit"]:
        return
    query, category = payload["query"], payload["category"]
    year_min, year_max = payload["year_min"], payload["year_max"]
    page, limit = payload["page"], payload["limit"]
    exact = library.cached_page(signature, page, limit)
    failed = {provider.casefold() for provider in failed_providers}
    cached_rows = [paper for paper in (exact or {}).get("results", [])
                   if str(paper.get("source") or "").casefold() in failed]
    seen = {paper.get("library_id") or paper["url"] for paper in payload["results"]}
    candidates = [paper for paper in cached_rows if (paper.get("library_id") or paper["url"]) not in seen]
    source = "query_cache"
    fetched_at = exact["cache_fetched_at"] if exact else None
    fallback_has_more = exact.get("has_more", False) if exact else False
    if not candidates:
        saved = _saved_response(library, query, category, failed_providers, year_min, year_max, page, limit)
        candidates = saved["results"]
        source = "library"
        fetched_at = saved["cache"]["fetched_at"]
        fallback_has_more = saved["has_more"]
    live_count = len(payload["results"])
    for paper in candidates:
        key = paper.get("library_id") or paper["url"]
        if key in seen:
            continue
        if len(payload["results"]) >= limit:
            break
        seen.add(key)
        payload["results"].append({**paper, "retrieval_kind": "saved"})
    saved_count = len(payload["results"]) - live_count
    if saved_count:
        payload["returned"] = len(payload["results"])
        payload["has_more"] = page < MAX_SEARCH_PAGE and (payload["has_more"] or fallback_has_more)
        payload["cache"].update(kind="mixed" if live_count else "fallback", source=source,
                                fetched_at=fetched_at, saved_count=saved_count)


def _search_filters(q, category, providers, year_min, year_max):
    query = q.strip()
    if len(query) < 2:
        raise HTTPException(422, "Query is too short")
    if category != "all" and category not in CATEGORIES:
        raise HTTPException(422, "Unknown category")
    if year_min is not None and year_max is not None and year_min > year_max:
        raise HTTPException(422, "year_min must be less than or equal to year_max")
    return query, _parse_providers(providers)


async def fetch_literature(
    store, engine, query, category, provider_names, year_min, year_max, page, limit, *, for_watch=False,
):
    library = store.literature
    signature = library.signature(query, category, provider_names, year_min, year_max)
    # Providers don't support an offset, so each page re-fetches candidates from
    # the start and slices the window locally. One extra candidate is requested
    # past the window edge so `has_more` can be determined without a separate
    # count call; cap total candidates fetched.
    window_end = page * limit
    fetch_target = window_end + 1
    max_candidates = MAX_SEARCH_PAGE * MAX_SEARCH_SIZE + 1
    candidate_limit = min(fetch_target * 3 if category != "all" else fetch_target, max_candidates)
    extra = {"prefer_recent": True} if for_watch and isinstance(engine, AcademicSearchEngine) else {}
    try:
        result = await run_in_threadpool(
            engine.search, query, candidate_limit, False, year_min, year_max, provider_names, **extra,
        )
    except (RequestException, OSError):
        result = SearchResult(
            query=query, requested_providers=provider_names,
            provider_outcomes=[ProviderOutcome(name, "failed", error_code="transport_error",
                                               message="provider transport unavailable") for name in provider_names],
        )

    candidates = [
        item
        for item in (_serialize_article(article) for article in result.articles)
        if item is not None
    ]
    serialized = candidates if category == "all" else [item for item in candidates if item["category"] == category]
    window_start = (page - 1) * limit
    extra_result = len(serialized) > window_end
    has_more = page < MAX_SEARCH_PAGE and extra_result
    serialized = serialized[window_start:window_end]
    outcomes = [outcome.to_dict() for outcome in result.provider_outcomes]
    coverage = _provider_coverage(provider_names, result.sources, outcomes)
    failed_providers = [entry["provider"] for entry in coverage
                        if entry["status"] in {"failed", "rate_limited", "unavailable"}]
    payload = {
        "query": query,
        "category": category,
        "category_provenance": "derived:keyword-rules-v1",
        "providers_requested": provider_names,
        "sources_responded": result.sources,
        "provider_outcomes": outcomes,
        "retrieved_at": result.timestamp,
        "search_time": result.search_time,
        "total_provider_matches": result.total_found,
        "returned": len(serialized),
        "results": serialized,
        "year_min": year_min,
        "year_max": year_max,
        "limit": limit,
        "page": page,
        "has_more": has_more,
        "pagination": {
            "max_page": MAX_SEARCH_PAGE,
            "candidate_limit": candidate_limit,
            "window_limited": (page == MAX_SEARCH_PAGE and extra_result) or (
                category != "all" and not extra_result and len(result.articles) >= max_candidates
            ),
            "partial": bool(failed_providers),
        },
        "provider_coverage": coverage,
        "manifest": result.manifest(),
        "cache": {"kind": "live", "source": "api", "fetched_at": None,
                  "checked_at": result.timestamp, "live_count": len(serialized), "saved_count": 0},
    }
    additional_articles = result.provider_articles
    if additional_articles:
        # Keep the observations from each provider even when the online list
        # merges a duplicate into a single ranked result.
        shown = {id(article) for article in result.articles}
        additional = (
            paper for paper in (
                _serialize_article(article) for article in additional_articles if id(article) not in shown
            ) if paper is not None
        )
        observed = chain(additional, candidates)
    else:
        observed = candidates
    new_work_ids = await run_in_threadpool(
        library.save_search, signature, payload, observed, not failed_providers and not for_watch,
    )
    if for_watch:
        payload["new_work_ids"] = new_work_ids
    else:
        await run_in_threadpool(_add_saved_fallback, library, payload, signature, failed_providers)
    payload["manifest"]["delivery"] = dict(payload["cache"])
    return payload


def create_app(project_store: Optional[ProjectStore] = None) -> FastAPI:
    @asynccontextmanager
    async def lifespan(app):
        def engine():
            return app.dependency_overrides.get(get_search_engine, get_search_engine)()

        def openalex():
            return app.dependency_overrides.get(get_journal_searcher, get_journal_searcher)()

        store = app.state.project_store
        tasks = [
            asyncio.create_task(watch_scheduler(store, engine, fetch_literature)),
            asyncio.create_task(daily_scheduler(store, engine, openalex, fetch_literature)),
            asyncio.create_task(special_issue_scheduler(store)),
            asyncio.create_task(journal_favorites_scheduler(store, openalex, _serialize_article)),
        ]
        try:
            yield
        finally:
            for task in tasks:
                task.cancel()
            for task in tasks:
                with suppress(asyncio.CancelledError):
                    await task

    app = FastAPI(
        title="Academic Search Service",
        description=(
            "Search scholarly providers and return linked, normalized records. "
            "UI categories are explicitly derived keyword labels."
        ),
        version=SERVICE_VERSION,
        docs_url="/docs",
        redoc_url="/redoc",
        lifespan=lifespan,
    )

    origins = _cors_origins()
    app.add_middleware(
        CORSMiddleware,
        allow_origins=origins,
        allow_credentials="*" not in origins,
        allow_methods=["GET", "POST", "PATCH", "PUT", "DELETE"],
        allow_headers=["*"],
    )
    app.state.project_store = project_store or ProjectStore(_project_store_path())

    app.mount("/assets", StaticFiles(directory=WEB_DIR), name="assets")
    app.include_router(workspace_router(get_project_store, get_journal_searcher, _serialize_article))
    app.include_router(account_router(get_project_store))
    app.include_router(workflow_router(get_project_store, get_search_engine, _search_filters, fetch_literature))
    app.include_router(daily_router(get_project_store, get_search_engine, get_journal_searcher, _search_filters, fetch_literature))
    app.include_router(router_for_publishing(get_project_store, get_journal_searcher))
    app.include_router(journal_favorites_router(get_project_store, get_journal_catalog_service, get_journal_searcher,
                                                _serialize_article))

    @app.get("/", include_in_schema=False)
    @app.get("/ui", include_in_schema=False)
    async def index() -> FileResponse:
        return FileResponse(WEB_DIR / "index.html")

    @app.get("/api/v1/health")
    async def health() -> Dict[str, Any]:
        engine = get_search_engine()
        return {
            "status": "ok",
            "service": "academic-search",
            "version": SERVICE_VERSION,
            "providers": _provider_availability(engine),
            "ubyt": {
                "list": get_ubyt_catalog().label,
                "journals": len(get_ubyt_catalog().records),
            },
        }

    @app.get("/api/v1/categories")
    async def categories() -> Dict[str, Any]:
        return {
            "category_provenance": "derived:keyword-rules-v1",
            "categories": [
                {
                    "id": slug,
                    "label": data["label"],
                    "description": data["description"],
                }
                for slug, data in CATEGORIES.items()
            ],
        }

    @app.get("/api/v1/projects")
    async def list_projects(store: ProjectStore = Depends(get_project_store)) -> Dict[str, Any]:
        return {"projects": store.list_projects()}

    @app.post("/api/v1/projects", status_code=201)
    async def create_project(
        payload: ProjectCreate,
        store: ProjectStore = Depends(get_project_store),
    ) -> Dict[str, Any]:
        if payload.default_category != "all" and payload.default_category not in CATEGORIES:
            raise HTTPException(status_code=422, detail="Unknown default category")
        _parse_providers(payload.default_providers)
        if (payload.default_year_min is not None and payload.default_year_max is not None
                and payload.default_year_min > payload.default_year_max):
            raise HTTPException(status_code=422, detail="default_year_min must be less than or equal to default_year_max")
        try:
            return store.create_project(payload.model_dump())
        except DuplicateProjectName as exc:
            raise HTTPException(status_code=409, detail=f'A project named "{exc}" already exists') from exc

    @app.get("/api/v1/projects/{project_id}")
    async def get_project(
        project_id: str, store: ProjectStore = Depends(get_project_store)
    ) -> Dict[str, Any]:
        project = store.get_project(project_id)
        if not project:
            raise HTTPException(status_code=404, detail="Research project not found")
        return project

    @app.patch("/api/v1/projects/{project_id}")
    async def update_project(
        project_id: str, payload: ProjectUpdate, store: ProjectStore = Depends(get_project_store)
    ) -> Dict[str, Any]:
        changes = payload.model_dump(exclude_unset=True)
        if "default_category" in changes and changes["default_category"] not in {*CATEGORIES, "all"}:
            raise HTTPException(status_code=422, detail="Unknown default category")
        if changes.get("default_providers"):
            _parse_providers(changes["default_providers"])
        year_min = changes.get("default_year_min")
        year_max = changes.get("default_year_max")
        if year_min is not None and year_max is not None and year_min > year_max:
            raise HTTPException(status_code=422, detail="default_year_min must be less than or equal to default_year_max")
        try:
            project = store.update_project(project_id, changes)
        except DuplicateProjectName as exc:
            raise HTTPException(status_code=409, detail=f'A project named "{exc}" already exists') from exc
        if not project:
            raise HTTPException(status_code=404, detail="Research project not found")
        return project

    @app.get("/api/v1/projects/{project_id}/searches")
    async def project_searches(
        project_id: str, limit: int = Query(default=20, ge=1, le=100),
        store: ProjectStore = Depends(get_project_store),
    ) -> Dict[str, Any]:
        if not store.get_project(project_id):
            raise HTTPException(status_code=404, detail="Research project not found")
        return {"searches": store.list_searches(project_id, limit)}

    @app.get("/api/v1/projects/{project_id}/searches/{run_id}")
    async def saved_paper_search(
        project_id: str, run_id: str, store: ProjectStore = Depends(get_project_store),
    ) -> Dict[str, Any]:
        saved = store.get_search(project_id, run_id)
        if not saved:
            raise HTTPException(status_code=404, detail="Saved paper search not found")
        return saved

    @app.get("/api/v1/projects/{project_id}/journal-searches")
    async def project_journal_searches(
        project_id: str, limit: int = Query(default=20, ge=1, le=100),
        store: ProjectStore = Depends(get_project_store),
    ) -> Dict[str, Any]:
        if not store.get_project(project_id):
            raise HTTPException(status_code=404, detail="Research project not found")
        return {"searches": store.list_journal_searches(project_id, limit)}

    @app.get("/api/v1/projects/{project_id}/journal-searches/{run_id}")
    async def saved_journal_search(
        project_id: str, run_id: str, store: ProjectStore = Depends(get_project_store),
    ) -> Dict[str, Any]:
        saved = store.get_journal_search(run_id)
        if not saved or saved["project_id"] != project_id:
            raise HTTPException(status_code=404, detail="Saved journal search not found")
        fits = store.list_journal_fits(project_id, limit=1, journal_search_id=run_id)
        return {**_journal_response(saved, "saved"), "latest_fit": next(iter(fits), None)}

    @app.get("/api/v1/projects/{project_id}/journal-fits")
    async def project_journal_fits(
        project_id: str, limit: int = Query(default=20, ge=1, le=100),
        store: ProjectStore = Depends(get_project_store),
    ) -> Dict[str, Any]:
        if not store.get_project(project_id):
            raise HTTPException(status_code=404, detail="Research project not found")
        return {"fits": store.list_journal_fits(project_id, limit)}

    @app.get("/api/v1/projects/{project_id}/evidence")
    async def project_evidence(
        project_id: str, format: str = Query(default="json", pattern="^(json|markdown)$"),
        store: ProjectStore = Depends(get_project_store),
    ) -> Any:
        evidence = store.evidence(project_id)
        if not evidence:
            raise HTTPException(status_code=404, detail="Research project not found")
        if format == "markdown":
            return Response(
                _markdown_evidence(evidence), media_type="text/markdown",
                headers={"Content-Disposition": f'attachment; filename="{project_id}-search-evidence.md"'},
            )
        return evidence

    @app.get("/api/v1/journals/suggest")
    async def suggest_journals(
        q: str = Query(min_length=2, max_length=200),
        limit: int = Query(default=8, ge=1, le=20),
        searcher: OpenAlexSearcher = Depends(get_journal_searcher),
        ubyt: UbytCatalog = Depends(get_ubyt_catalog),
    ) -> Dict[str, Any]:
        def fetch_suggestions():
            journals = searcher.suggest_journals(q.strip(), limit)
            return journals, getattr(searcher, "last_failure", None)

        journals, failure = await run_in_threadpool(fetch_suggestions)
        for journal in journals:
            journal["ubyt"] = ubyt.match(journal.get("issns") or [], journal.get("display_name"))
        return {
            "query": q.strip(),
            "journals": journals,
            "provenance": "provider:OpenAlex",
            "provider_status": (
                {"status": failure["code"], "message": failure["message"]}
                if failure else {"status": "responded" if journals else "empty"}
            ),
        }

    @app.get("/api/v1/ubyt/journals")
    async def ubyt_journals(
        q: str = Query(default="", max_length=200),
        category: Optional[str] = Query(default=None, max_length=20),
        limit: int = Query(default=25, ge=1, le=100),
        page: int = Query(default=1, ge=1, le=10000),
        sort: str = Query(default="mep", pattern="^(mep|payment|name)$"),
        ubyt: UbytCatalog = Depends(get_ubyt_catalog),
    ) -> Dict[str, Any]:
        def find_journals():
            journals = ubyt.search(q, category, limit, (page - 1) * limit, sort)
            return journals, ubyt.last_total

        journals, total = await run_in_threadpool(find_journals)
        return {
            "list": ubyt.label,
            "query": q.strip(),
            "category": category,
            "page": page,
            "limit": limit,
            "sort": sort,
            "total": total,
            "journals": journals,
        }

    @app.get("/api/v1/ubyt/lookup")
    async def ubyt_lookup(
        issn: List[str] = Query(default=[], max_length=10),
        name: Optional[str] = Query(default=None, max_length=300),
        ubyt: UbytCatalog = Depends(get_ubyt_catalog),
    ) -> Dict[str, Any]:
        if not issn and not (name or "").strip():
            raise HTTPException(status_code=422, detail="Provide an ISSN or a journal name")
        return {"list": ubyt.label, "ubyt": ubyt.match(issn, name)}

    @app.get("/api/v1/journal-catalog/providers")
    async def journal_catalog_providers(
        catalog: JournalCatalogService = Depends(get_journal_catalog_service),
    ) -> Dict[str, Any]:
        return {
            "providers": catalog.providers(),
            "identifier_note": (
                "Journals use ISSN/ISSN-L and provider source IDs. DOI identifies an "
                "article and appears in paper results."
            ),
        }

    @app.get("/api/v1/journal-catalog/categories")
    async def journal_catalog_categories(
        provider: str = Query(default="openalex"),
        q: str = Query(default="", max_length=200),
        limit: int = Query(default=50, ge=1, le=100),
        catalog: JournalCatalogService = Depends(get_journal_catalog_service),
    ) -> Dict[str, Any]:
        if provider not in CATALOG_PROVIDERS:
            raise HTTPException(status_code=422, detail="Unknown journal catalog provider")
        return await run_in_threadpool(catalog.categories, provider, q.strip(), limit)

    @app.get("/api/v1/journal-catalog/journals")
    async def journal_catalog_journals(
        provider: str = Query(default="openalex"),
        q: str = Query(default="", max_length=200),
        category_id: Optional[str] = Query(default=None, max_length=100),
        limit: int = Query(default=25, ge=1, le=100),
        page: int = Query(default=1, ge=1, le=10000),
        sort: Optional[str] = Query(default=None, pattern="^(mep|payment|name)$"),
        catalog: JournalCatalogService = Depends(get_journal_catalog_service),
    ) -> Dict[str, Any]:
        if provider not in CATALOG_PROVIDERS:
            raise HTTPException(status_code=422, detail="Unknown journal catalog provider")
        return await run_in_threadpool(
            catalog.journals, provider, q.strip(), category_id, limit, page, sort
        )

    @app.get("/api/v1/journal-catalog/resolve")
    async def resolve_catalog_journal(
        provider: str = Query(default="openalex"),
        journal_id: str = Query(min_length=1, max_length=160),
        catalog: JournalCatalogService = Depends(get_journal_catalog_service),
    ) -> Dict[str, Any]:
        if provider not in CATALOG_PROVIDERS:
            raise HTTPException(status_code=422, detail="Unknown journal catalog provider")
        payload = await run_in_threadpool(catalog.resolve, provider, journal_id)
        if not payload.get("journal"):
            status = payload.get("provider_status", {}).get("status")
            raise HTTPException(
                status_code=503 if status not in {"empty", "not_found"} else 404,
                detail=payload.get("provider_status", {}).get("message") or "Journal could not be resolved",
            )
        return payload

    @app.post("/api/v1/journals/search")
    async def search_journal(
        request: JournalSearchRequest,
        searcher: OpenAlexSearcher = Depends(get_journal_searcher),
        store: ProjectStore = Depends(get_project_store),
    ) -> Dict[str, Any]:
        if request.project_id and not store.get_project(request.project_id):
            raise HTTPException(status_code=404, detail="Research project not found")
        if request.year_min and request.year_max and request.year_min > request.year_max:
            raise HTTPException(
                status_code=422,
                detail="year_min must be less than or equal to year_max",
            )
        if request.journal.type != "journal":
            raise HTTPException(status_code=422, detail="Selected source is not a journal")
        if not request.journal.search_supported:
            raise HTTPException(
                status_code=422,
                detail="This catalog journal has no OpenAlex ISSN crosswalk for paper search",
            )
        stable_id = request.journal.id.rsplit("/", 1)[-1]
        if not stable_id.startswith("S") or not stable_id[1:].isdigit():
            raise HTTPException(status_code=422, detail="Invalid OpenAlex journal identifier")

        topics: List[str] = []
        seen_topics = set()
        for topic in request.topics:
            cleaned = " ".join(topic.split()).casefold()
            if cleaned and cleaned not in seen_topics:
                topics.append(cleaned)
                seen_topics.add(cleaned)
        if not topics:
            raise HTTPException(status_code=422, detail="At least one topic is required")

        if request.project_id and not request.refresh:
            saved = store.find_journal_search(
                request.project_id, stable_id, topics,
                request.year_min, request.year_max, request.limit,
            )
            if saved:
                return _journal_response(saved, "saved")

        query = " ".join(topics)
        result = await run_in_threadpool(
            searcher.search_journal,
            stable_id,
            request.journal.display_name,
            query,
            request.limit,
            request.year_min,
            request.year_max,
        )
        serialized = [
            item
            for item in (_serialize_article(article) for article in result.articles)
            if item is not None
        ]
        papers = annotate_topic_alignment(serialized, topics)
        profile = build_journal_profile(papers)
        journal = request.journal.model_dump()
        journal["id"] = stable_id
        retrieved_at = datetime.now(timezone.utc).isoformat()
        provider_outcomes = [item.to_dict() for item in result.provider_outcomes]
        manifest = {
            **result.manifest(),
            "retrieved_at": retrieved_at,
            "journal": journal,
            "topics": topics,
            "article_alignment_version": ARTICLE_ALIGNMENT_VERSION,
            "profile_version": PROFILE_VERSION,
        }
        payload = {
            "id": None,
            "project_id": request.project_id,
            "journal": journal,
            "topics": topics,
            "query": query,
            "year_min": request.year_min,
            "year_max": request.year_max,
            "limit": request.limit,
            "retrieved_at": retrieved_at,
            "total_provider_matches": result.total_found,
            "provider_outcomes": provider_outcomes,
            "papers": papers,
            "profile": profile,
            "manifest": manifest,
        }
        await run_in_threadpool(store.literature.observe, serialized, retrieved_at)
        if request.project_id:
            payload = store.record_journal_search(request.project_id, payload)
        return _journal_response(payload, "refreshed" if request.refresh else "fresh")

    @app.post("/api/v1/journal-searches/{journal_search_id}/fit", status_code=201)
    async def fit_manuscript_to_journal(
        journal_search_id: str,
        request: ManuscriptFitRequest,
        store: ProjectStore = Depends(get_project_store),
    ) -> Dict[str, Any]:
        project = store.get_project(request.project_id)
        if not project:
            raise HTTPException(status_code=404, detail="Research project not found")
        saved = store.get_journal_search(journal_search_id)
        if not saved or saved["project_id"] != request.project_id:
            raise HTTPException(status_code=404, detail="Saved journal search not found")
        if not saved["papers"]:
            raise HTTPException(status_code=422, detail="A saved journal sample with linked papers is required")
        title = " ".join(request.title.split())
        abstract = " ".join(request.abstract.split())
        keywords = [" ".join(item.split()) for item in request.keywords if item.strip()]
        if not title and not abstract and not keywords:
            raise HTTPException(status_code=422, detail="Manuscript text is required")
        report = manuscript_fit(title, abstract, keywords, saved["papers"])
        report["journal"] = saved["journal"]
        report["journal_snapshot_retrieved_at"] = saved["retrieved_at"]
        report["analysis_version"] = FIT_VERSION
        return store.record_journal_fit(
            request.project_id,
            journal_search_id,
            {"title": title, "abstract": abstract, "keywords": keywords},
            report,
        )

    @app.get("/api/v1/library/status")
    async def library_status(store: ProjectStore = Depends(get_project_store)) -> Dict[str, Any]:
        return await run_in_threadpool(store.literature.status)

    @app.get("/api/v1/search")
    async def search(
        response: Response,
        q: str = Query(min_length=2, max_length=300),
        category: str = Query(default="all"),
        providers: Optional[str] = Query(default=None),
        limit: int = Query(default=20, ge=1, le=MAX_SEARCH_SIZE),
        page: int = Query(default=1, ge=1, le=MAX_SEARCH_PAGE),
        year_min: Optional[int] = Query(default=None, ge=1800, le=2200),
        year_max: Optional[int] = Query(default=None, ge=1800, le=2200),
        project_id: Optional[str] = Query(default=None),
        mode: Literal["online", "local", "cache"] = Query(default="online"),
        engine: AcademicSearchEngine = Depends(get_search_engine),
        store: ProjectStore = Depends(get_project_store),
    ) -> Dict[str, Any]:
        response.headers["Cache-Control"] = "no-store"
        query, provider_names = _search_filters(q, category, providers, year_min, year_max)
        if mode == "local" and providers is None:
            provider_names = []
        if project_id and not store.get_project(project_id):
            raise HTTPException(status_code=404, detail="Research project not found")
        library = store.literature
        signature = library.signature(query, category, provider_names, year_min, year_max)
        if mode != "online":
            cached = await run_in_threadpool(library.cached_page, signature, page, limit) if mode == "cache" else None
            return await run_in_threadpool(
                _saved_response, library, query, category, provider_names, year_min, year_max, page, limit, cached=cached,
            )
        payload = await fetch_literature(
            store, engine, query, category, provider_names, year_min, year_max, page, limit,
        )
        if project_id and page == 1:
            store.update_project(project_id, {
                "default_category": category,
                "default_providers": providers or ",".join(DEFAULT_PROVIDERS),
                "default_year_min": year_min,
                "default_year_max": year_max,
            })
            run = store.record_search(project_id, payload)
            payload["project_id"] = project_id
            payload["search_run_id"] = run["id"]
        elif project_id and payload["results"]:
            run = store.put_workspace_item(project_id, "search-page", {
                "results": payload["results"], "query": query, "page": page,
                "retrieved_at": payload["retrieved_at"],
            })
            payload["reading_source_id"] = run["id"]
        return payload

    return app


app = create_app()
