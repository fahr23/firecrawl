"""Persistent HTTP service and UI for the academic-search package."""

from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional
from urllib.parse import urlparse

from fastapi import Depends, FastAPI, HTTPException, Query, Request
from fastapi.concurrency import run_in_threadpool
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from .engine import AcademicSearchEngine
from .models import Article
from .project_store import ProjectStore


SERVICE_VERSION = "1.0"
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


def _cors_origins() -> List[str]:
    value = os.getenv("ACADEMIC_CORS_ORIGINS", "*")
    origins = [item.strip() for item in value.split(",") if item.strip()]
    return origins or ["*"]


def _safe_url(article: Article) -> Optional[str]:
    candidates = [article.url]
    if article.doi:
        candidates.append(f"https://doi.org/{article.doi_normalized}")
    for candidate in candidates:
        if not candidate:
            continue
        parsed = urlparse(candidate)
        if parsed.scheme in {"http", "https"} and parsed.netloc:
            return candidate
    return None


def _article_text(article: Article) -> str:
    return " ".join(
        [
            article.title or "",
            article.abstract or "",
            article.journal or "",
            " ".join(article.keywords or []),
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
    return "\n".join(lines) + "\n"


def _serialize_article(article: Article) -> Optional[Dict[str, Any]]:
    url = _safe_url(article)
    if not url:
        return None
    category = derive_category(article)
    return {
        "title": article.title,
        "url": url,
        "doi": article.doi,
        "authors": article.authors,
        "journal": article.journal,
        "year": article.year,
        "abstract": article.abstract,
        "source": article.source,
        "is_open_access": article.is_open_access,
        "citation_count": article.citation_count,
        "keywords": article.keywords,
        "category": category,
        "category_label": CATEGORIES[category]["label"],
        "category_provenance": "derived:keyword-rules-v1",
        "field_provenance": article.field_provenance,
        "derived_outputs": article.derived_outputs,
    }


def _provider_availability(engine: AcademicSearchEngine) -> Dict[str, bool]:
    configured = {
        searcher.source_name.lower()
        for searcher in getattr(engine, "_searchers", [])
        if searcher.is_available
    }
    return {
        slug: PROVIDER_SOURCE_NAMES[slug] in configured
        for slug in PROVIDERS
    }


@lru_cache(maxsize=1)
def get_search_engine() -> AcademicSearchEngine:
    return AcademicSearchEngine()


def create_app(project_store: Optional[ProjectStore] = None) -> FastAPI:
    app = FastAPI(
        title="Academic Search Service",
        description=(
            "Search scholarly providers and return linked, normalized records. "
            "UI categories are explicitly derived keyword labels."
        ),
        version=SERVICE_VERSION,
        docs_url="/docs",
        redoc_url="/redoc",
    )

    origins = _cors_origins()
    app.add_middleware(
        CORSMiddleware,
        allow_origins=origins,
        allow_credentials="*" not in origins,
        allow_methods=["GET", "POST", "PATCH"],
        allow_headers=["*"],
    )
    app.state.project_store = project_store or ProjectStore(_project_store_path())

    app.mount("/assets", StaticFiles(directory=WEB_DIR), name="assets")

    @app.get("/", include_in_schema=False)
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
        return store.create_project(payload.model_dump())

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
        project = store.update_project(project_id, changes)
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

    @app.get("/api/v1/search")
    async def search(
        q: str = Query(min_length=2, max_length=300),
        category: str = Query(default="all"),
        providers: Optional[str] = Query(default=None),
        limit: int = Query(default=20, ge=1, le=50),
        year_min: Optional[int] = Query(default=None, ge=1800, le=2200),
        year_max: Optional[int] = Query(default=None, ge=1800, le=2200),
        project_id: Optional[str] = Query(default=None),
        engine: AcademicSearchEngine = Depends(get_search_engine),
        store: ProjectStore = Depends(get_project_store),
    ) -> Dict[str, Any]:
        query = q.strip()
        if len(query) < 2:
            raise HTTPException(status_code=422, detail="Query is too short")
        if category != "all" and category not in CATEGORIES:
            raise HTTPException(status_code=422, detail="Unknown category")
        if year_min is not None and year_max is not None and year_min > year_max:
            raise HTTPException(
                status_code=422,
                detail="year_min must be less than or equal to year_max",
            )

        provider_names = _parse_providers(providers)
        if project_id and not store.get_project(project_id):
            raise HTTPException(status_code=404, detail="Research project not found")
        candidate_limit = min(limit * 3 if category != "all" else limit, 100)
        result = await run_in_threadpool(
            engine.search,
            query,
            candidate_limit,
            False,
            year_min,
            year_max,
            provider_names,
        )

        serialized = [
            item
            for item in (_serialize_article(article) for article in result.articles)
            if item is not None
        ]
        if category != "all":
            serialized = [
                item for item in serialized if item["category"] == category
            ]
        serialized = serialized[:limit]

        payload = {
            "query": query,
            "category": category,
            "category_provenance": "derived:keyword-rules-v1",
            "providers_requested": provider_names,
            "sources_responded": result.sources,
            "provider_outcomes": [outcome.to_dict() for outcome in result.provider_outcomes],
            "retrieved_at": result.timestamp,
            "search_time": result.search_time,
            "total_provider_matches": result.total_found,
            "returned": len(serialized),
            "results": serialized,
            "year_min": year_min,
            "year_max": year_max,
            "limit": limit,
            "provider_coverage": _provider_coverage(
                provider_names, result.sources,
                [outcome.to_dict() for outcome in result.provider_outcomes],
            ),
            "manifest": result.manifest(),
        }
        if project_id:
            store.update_project(project_id, {
                "default_category": category,
                "default_providers": providers or ",".join(DEFAULT_PROVIDERS),
                "default_year_min": year_min,
                "default_year_max": year_max,
            })
            run = store.record_search(project_id, payload)
            payload["project_id"] = project_id
            payload["search_run_id"] = run["id"]
        return payload

    return app


app = create_app()
