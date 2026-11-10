"""TÜBİTAK UBYT journal list: name/ISSN search and incentive (payment) lookup.

The list is bundled as CSV (converted from the official Excel release) so the
service needs no spreadsheet dependency at runtime. Convert a new release with::

    python -m academic_search.ubyt_catalog convert ubyt_2027.xlsx data/ubyt_2027.csv

UBYT records are journal-level facts published by TÜBİTAK; they are attached to
provider journals and papers by ISSN first and exact normalized title second.
"""

from __future__ import annotations

import csv
import os
import re
import sys
import unicodedata
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional


DEFAULT_CATALOG_PATH = Path(__file__).resolve().parent / "data" / "ubyt_2026.csv"
CSV_FIELDS = (
    "name", "issn", "eissn", "payment_tl", "mep_score",
    "scie", "ssci", "ahci", "source", "year",
)
# Column headers of the official Excel release, mapped to CSV fields.
EXCEL_HEADERS = {
    "dergi adı": "name",
    "issn": "issn",
    "eissn": "eissn",
    "ödeme (tl)": "payment_tl",
    "dergi mep puanı": "mep_score",
    "scie": "scie",
    "ssci": "ssci",
    "ahci": "ahci",
    "kaynak": "source",
    "yıl": "year",
}
INDEX_CATEGORIES = {
    "scie": "SCIE",
    "ssci": "SSCI",
    "ahci": "AHCI",
    "scopus": "Scopus",
    "tr": "Kaynak: TR",
    "tbtk": "Kaynak: TBTK",
}
_SOURCE_CATEGORIES = {"SCOPUS": "scopus", "TR": "tr", "TBTK": "tbtk"}
SORT_KEYS = {
    "mep": lambda record: -(record["mep_score"] or 0),
    "payment": lambda record: (-(record["payment_tl"] or 0), -(record["mep_score"] or 0)),
    "name": lambda record: record["normalized_name"],
}
_ISSN_RE = re.compile(r"^(\d{4})-?(\d{3}[\dX])$")


def normalize_issn(value: Any) -> Optional[str]:
    match = _ISSN_RE.match(str(value or "").strip().upper())
    return f"{match.group(1)}-{match.group(2)}" if match else None


def normalize_title(value: Any) -> str:
    text = unicodedata.normalize("NFKD", str(value or "")).casefold()
    text = "".join(char for char in text if not unicodedata.combining(char))
    text = text.replace("&", " and ")
    words = re.findall(r"[a-z0-9]+", text)
    if words and words[0] == "the":
        words = words[1:]
    return " ".join(words)


def _truthy(value: str) -> bool:
    return str(value).strip().lower() in {"true", "1", "yes", "x"}


class UbytCatalog:
    """In-memory UBYT list with the journal-catalog adapter interface."""

    source_name = "TÜBİTAK UBYT"

    def __init__(self, path: Optional[os.PathLike] = None) -> None:
        self.path = Path(path or os.getenv("ACADEMIC_UBYT_CATALOG_PATH") or DEFAULT_CATALOG_PATH)
        self.last_failure: Optional[Dict[str, str]] = None
        self.last_total: Optional[int] = None
        self.records: List[Dict[str, Any]] = []
        self._by_issn: Dict[str, Dict[str, Any]] = {}
        self._by_title: Dict[str, Dict[str, Any]] = {}
        self._load()

    @property
    def is_available(self) -> bool:
        return bool(self.records)

    @property
    def year(self) -> Optional[int]:
        return max((record["year"] for record in self.records if record["year"]), default=None)

    @property
    def label(self) -> str:
        return f"TÜBİTAK UBYT {self.year}" if self.year else "TÜBİTAK UBYT"

    def clear_last_failure(self) -> None:
        self.last_failure = None

    def _load(self) -> None:
        if not self.path.is_file():
            return
        with self.path.open(newline="", encoding="utf-8") as handle:
            for row in csv.DictReader(handle):
                record = self._record(row)
                if not record:
                    continue
                self.records.append(record)
                for issn in record["issns"]:
                    # Keep the first (higher-listed) journal when an ISSN is shared.
                    self._by_issn.setdefault(issn, record)
                self._by_title.setdefault(record["normalized_name"], record)

    @staticmethod
    def _record(row: Dict[str, str]) -> Optional[Dict[str, Any]]:
        name = " ".join(str(row.get("name") or "").split())
        issn = normalize_issn(row.get("issn"))
        eissn = normalize_issn(row.get("eissn"))
        issns = list(dict.fromkeys(value for value in (issn, eissn) if value))
        if not name or not issns:
            return None
        indexes = [label for key, label in (("scie", "SCIE"), ("ssci", "SSCI"), ("ahci", "AHCI"))
                   if _truthy(row.get(key, ""))]
        source = str(row.get("source") or "").strip().upper()
        source = source if source and source != "-" else None
        try:
            payment = int(float(row.get("payment_tl") or 0))
        except ValueError:
            payment = None
        try:
            mep = round(float(row.get("mep_score") or 0), 3)
        except ValueError:
            mep = None
        try:
            year = int(row.get("year") or 0) or None
        except ValueError:
            year = None
        return {
            "journal_name": name,
            "normalized_name": normalize_title(name),
            "issn": issn,
            "eissn": eissn,
            "issns": issns,
            "payment_tl": payment,
            "mep_score": mep,
            "indexes": indexes,
            "source": source,
            "year": year,
        }

    def _public(
        self, record: Dict[str, Any], matched_by: str, matched_issn: Optional[str] = None
    ) -> Dict[str, Any]:
        return {
            "journal_name": record["journal_name"],
            "issn": record["issn"],
            "eissn": record["eissn"],
            "payment_tl": record["payment_tl"],
            "mep_score": record["mep_score"],
            "indexes": record["indexes"],
            "source": record["source"],
            "year": record["year"],
            "list": self.label,
            "matched_by": matched_by,
            "matched_issn": matched_issn,
            "provenance": f"list:{self.path.name}",
        }

    def match(self, issns: Iterable[Any] = (), name: Optional[str] = None) -> Optional[Dict[str, Any]]:
        """Find the UBYT entry for a journal: any ISSN match, else exact normalized title."""
        for value in issns or ():
            issn = normalize_issn(value)
            record = self._by_issn.get(issn or "")
            if record:
                return self._public(record, "issn", issn)
        normalized = normalize_title(name)
        record = self._by_title.get(normalized) if normalized else None
        return self._public(record, "name") if record else None

    def search(
        self, query: str = "", category_id: Optional[str] = None, limit: int = 25,
        offset: int = 0, sort: str = "mep",
    ) -> List[Dict[str, Any]]:
        """Search by ISSN or title words; best title matches first, then ``sort`` order.

        ``last_total`` holds the full match count so callers can paginate.
        """
        query = query.strip()
        issn = normalize_issn(query)
        if issn:
            record = self._by_issn.get(issn)
            matches = [record] if record and self._in_category(record, category_id) else []
            self.last_total = len(matches)
            return [self._public(item, "issn", issn) for item in matches[offset:offset + limit]]
        normalized = normalize_title(query)
        words = normalized.split()
        sort_key = SORT_KEYS.get(sort, SORT_KEYS["mep"])
        ranked = []
        for record in self.records:
            if not self._in_category(record, category_id):
                continue
            title = record["normalized_name"]
            if words and not all(word in title for word in words):
                continue
            exact = title == normalized
            prefix = bool(normalized) and title.startswith(normalized)
            ranked.append(((not exact, not prefix, sort_key(record)), record))
        ranked.sort(key=lambda item: item[0])
        self.last_total = len(ranked)
        return [self._public(record, "search") for _, record in ranked[offset:offset + limit]]

    @staticmethod
    def _in_category(record: Dict[str, Any], category_id: Optional[str]) -> bool:
        if not category_id:
            return True
        if category_id in ("scie", "ssci", "ahci"):
            return category_id.upper() in record["indexes"]
        return _SOURCE_CATEGORIES.get(record["source"] or "") == category_id

    # Journal-catalog adapter interface (see JournalCatalogService).
    def journal_categories(self, query: str = "", limit: int = 50) -> List[Dict[str, Any]]:
        needle = query.strip().casefold()
        categories = []
        for category_id, label in INDEX_CATEGORIES.items():
            if needle and needle not in label.casefold():
                continue
            count = sum(1 for record in self.records if self._in_category(record, category_id))
            if count:
                categories.append({
                    "id": category_id, "label": label,
                    "provider": "ubyt", "works_count": count,
                    "description": (
                        f"{count} journals flagged {label} in the {self.label} list "
                        f"({self.path.name}), as published by TÜBİTAK; not live index data."
                    ),
                })
        return categories[:limit]

    def journal_catalog(
        self, query: str = "", category_id: Optional[str] = None, limit: int = 25,
        page: int = 1, sort: str = "mep",
    ) -> List[Dict[str, Any]]:
        entries = self.search(query, category_id, limit, (max(page, 1) - 1) * limit, sort)
        return [self._catalog_journal(entry) for entry in entries]

    def resolve_journal(self, journal_id: str) -> Optional[Dict[str, Any]]:
        entry = self.match([journal_id])
        if not entry:
            self.last_failure = {"code": "not_found", "message": "ISSN is not on the UBYT list"}
            return None
        return self._catalog_journal(entry)

    def _catalog_journal(self, entry: Dict[str, Any]) -> Dict[str, Any]:
        issn_l = entry["issn"] or entry["eissn"]
        issns = [value for value in (entry["issn"], entry["eissn"]) if value]
        categories = [
            {"id": label.lower(), "label": label} for label in entry["indexes"]
        ]
        source_category = _SOURCE_CATEGORIES.get(entry["source"] or "")
        if source_category:
            categories.append({"id": source_category, "label": INDEX_CATEGORIES[source_category]})
        return {
            "id": issn_l,
            "catalog_id": f"ubyt:{issn_l}",
            "catalog_provider": "ubyt",
            "provider_id": issn_l,
            "display_name": entry["journal_name"],
            "issn_l": issn_l,
            "issns": issns,
            "publisher": "",
            "type": "journal",
            "source": self.source_name,
            "categories": categories,
            "identifiers": {"ubyt": issn_l, "issn_l": issn_l, "issns": issns},
            "search_supported": False,
            "ubyt": entry,
        }


def article_issns(raw: Any) -> List[str]:
    """Collect ISSNs from provider raw records (OpenAlex, Scopus, Web of Science, ...)."""
    found: List[str] = []

    def walk(value: Any, key: str, depth: int) -> None:
        if depth > 6:
            return
        if isinstance(value, dict):
            for child_key, child in value.items():
                walk(child, str(child_key).lower(), depth + 1)
        elif isinstance(value, list):
            for child in value:
                walk(child, key, depth + 1)
        elif "issn" in key:
            issn = normalize_issn(value)
            if issn and issn not in found:
                found.append(issn)

    walk(raw, "", 0)
    return found


def convert_excel(source: str, destination: str) -> int:
    """Convert an official UBYT Excel release to the bundled CSV format."""
    import openpyxl  # Only needed when importing a new release.

    sheet = openpyxl.load_workbook(source, read_only=True, data_only=True).active
    rows = sheet.iter_rows(values_only=True)
    headers = [EXCEL_HEADERS.get(str(value or "").strip().casefold()) for value in next(rows)]
    missing = set(CSV_FIELDS) - set(headers)
    if missing:
        raise ValueError(f"UBYT sheet is missing columns: {', '.join(sorted(missing))}")
    count = 0
    Path(destination).parent.mkdir(parents=True, exist_ok=True)
    with open(destination, "w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=CSV_FIELDS)
        writer.writeheader()
        for row in rows:
            values = {field: value for field, value in zip(headers, row) if field}
            if not values.get("name"):
                continue
            writer.writerow({field: "" if values.get(field) is None else values[field] for field in CSV_FIELDS})
            count += 1
    return count


if __name__ == "__main__":
    if len(sys.argv) != 4 or sys.argv[1] != "convert":
        sys.exit("usage: python -m academic_search.ubyt_catalog convert <ubyt.xlsx> <out.csv>")
    print(f"wrote {convert_excel(sys.argv[2], sys.argv[3])} journals to {sys.argv[3]}")
