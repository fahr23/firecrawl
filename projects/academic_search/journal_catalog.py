"""Provider-aware journal catalog browsing and ISSN crosswalking."""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from .config import Config
from .providers import ClarivateSearcher, OpenAlexSearcher, ScopusSearcher
from .ubyt_catalog import UbytCatalog


CATALOG_PROVIDERS = {
    "openalex": "OpenAlex",
    "web-of-science": "Web of Science Journals",
    "scopus": "Scopus Serial Titles",
    "ubyt": "TÜBİTAK UBYT",
}
# Largest page each catalog API returns; paging maths must use the real page size.
CATALOG_PAGE_LIMITS = {"web-of-science": 50}


class JournalCatalogService:
    """Coordinate journal-level APIs while keeping their provenance separate."""

    def __init__(self, config: Optional[Config] = None, ubyt: Optional[UbytCatalog] = None) -> None:
        config = config or Config()
        self.openalex = OpenAlexSearcher(config)
        self.scopus = ScopusSearcher(config)
        self.web_of_science = ClarivateSearcher(config)
        self.ubyt = ubyt or UbytCatalog()

    def providers(self) -> List[Dict[str, Any]]:
        return [
            {
                "id": "openalex",
                "label": CATALOG_PROVIDERS["openalex"],
                "available": True,
                "category_catalog": True,
                "journal_search": True,
                "article_search": True,
            },
            {
                "id": "web-of-science",
                "label": CATALOG_PROVIDERS["web-of-science"],
                "available": self.web_of_science.is_journal_catalog_available,
                "category_catalog": True,
                "journal_search": True,
                "article_search": self.web_of_science.is_available,
                "access_note": "Requires a Web of Science Journals API/JCR entitlement.",
            },
            {
                "id": "scopus",
                "label": CATALOG_PROVIDERS["scopus"],
                "available": self.scopus.is_available,
                "category_catalog": True,
                "journal_search": True,
                "article_search": self.scopus.is_available,
                "access_note": "Requires an Elsevier Serial Title API entitlement.",
            },
            {
                "id": "ubyt",
                "label": self.ubyt.label,
                "available": self.ubyt.is_available,
                "category_catalog": True,
                "journal_search": True,
                "article_search": False,
                "access_note": (
                    f"Bundled {self.ubyt.label} list ({self.ubyt.path.name}, "
                    f"{len(self.ubyt.records)} journals): search by name or ISSN; "
                    "selections are linked to OpenAlex by ISSN for paper search."
                ),
            },
        ]

    def annotate(self, journal: Dict[str, Any]) -> Dict[str, Any]:
        """Attach the UBYT payment/MEP entry for a journal (or None when not listed)."""
        if "ubyt" not in journal or journal["ubyt"] is None:
            journal["ubyt"] = self.ubyt.match(journal.get("issns") or [], journal.get("display_name"))
        return journal

    def categories(self, provider: str, query: str, limit: int) -> Dict[str, Any]:
        adapter = self._adapter(provider)
        adapter.clear_last_failure()
        categories = adapter.journal_categories(query, limit)
        return {
            "provider": provider,
            "categories": categories,
            "provider_status": self._status(adapter, bool(categories)),
        }

    def journals(
        self, provider: str, query: str, category_id: Optional[str], limit: int,
        page: int = 1, sort: Optional[str] = None,
    ) -> Dict[str, Any]:
        adapter = self._adapter(provider)
        adapter.clear_last_failure()
        limit = min(limit, CATALOG_PAGE_LIMITS.get(provider, limit))
        if provider == "ubyt":
            sort = sort or "mep"
            items = adapter.journal_catalog(query, category_id, limit, page, sort)
        else:
            sort = None
            items = adapter.journal_catalog(query, category_id, limit, page)
        journals = [self.annotate(item) for item in items]
        total = getattr(adapter, "last_total", None)
        return {
            "provider": provider,
            "query": query,
            "category_id": category_id,
            "journals": journals,
            "page": page,
            "limit": limit,
            "sort": sort,
            "total": total,
            "has_more": page * limit < total if total is not None else len(journals) == limit,
            "provider_status": self._status(adapter, bool(journals)),
            "identifier_note": (
                "ISSN/ISSN-L identify journals. DOI identifies an article and is returned "
                "with paper search results, not as a journal identifier."
            ),
        }

    def resolve(self, provider: str, journal_id: str) -> Dict[str, Any]:
        adapter = self._adapter(provider)
        adapter.clear_last_failure()
        journal = adapter.resolve_journal(journal_id)
        if not journal:
            return {
                "provider": provider,
                "journal": None,
                "provider_status": self._status(adapter, False),
            }
        if provider == "openalex":
            return {
                "provider": provider,
                "journal": self.annotate(journal),
                "provider_status": {"status": "responded"},
            }

        crosswalk = None
        for issn in journal.get("issns") or []:
            crosswalk = self.openalex.resolve_journal_by_issn(issn)
            if crosswalk:
                break
        if crosswalk:
            original_identifiers = journal.get("identifiers") or {}
            crosswalk["catalog_id"] = journal.get("catalog_id")
            crosswalk["catalog_provider"] = provider
            crosswalk["provider_id"] = journal.get("provider_id")
            crosswalk["identifiers"] = {
                **(crosswalk.get("identifiers") or {}),
                **original_identifiers,
            }
            crosswalk["provider_records"] = [
                {
                    "provider": provider,
                    "id": journal.get("provider_id"),
                    "source": journal.get("source"),
                },
                {
                    "provider": "openalex",
                    "id": crosswalk.get("id"),
                    "source": crosswalk.get("source"),
                },
            ]
            crosswalk["search_supported"] = True
            crosswalk["ubyt"] = journal.get("ubyt")
            journal = crosswalk
        else:
            journal["search_supported"] = False
            journal["resolution_note"] = (
                "No OpenAlex journal crosswalk was found from the provider ISSN; "
                "catalog metadata is available but journal-scoped paper search is disabled."
            )
        return {
            "provider": provider,
            "journal": self.annotate(journal),
            "provider_status": {"status": "responded"},
        }

    def _adapter(self, provider: str) -> Any:
        if provider == "openalex":
            return self.openalex
        if provider == "web-of-science":
            return self.web_of_science
        if provider == "scopus":
            return self.scopus
        if provider == "ubyt":
            return self.ubyt
        raise ValueError(f"Unknown journal catalog provider: {provider}")

    @staticmethod
    def _status(adapter: Any, has_results: bool) -> Dict[str, str]:
        failure = getattr(adapter, "last_failure", None)
        if failure:
            return {"status": failure.get("code", "failed"), "message": failure.get("message", "provider failed")}
        return {"status": "responded" if has_results else "empty"}
