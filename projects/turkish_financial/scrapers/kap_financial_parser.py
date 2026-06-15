"""
KAP "Finansal Tablolar" parser — raw KAP statement data → canonical facts.

KAP publishes financial statements inside financial-report (FR) disclosures. The
structured payload is a set of statement rows, each carrying a Turkish concept
label (e.g. "Hasılat", "Dönem Kârı (Zararı)") and a numeric value for one or more
periods. The exact JSON envelope KAP returns is not stable across report templates
(TMS/TFRS banking vs. industrial), so this module deliberately works off a *flat
label → value* mapping and is tolerant of missing / unexpected rows.

`normalize_facts()` maps those Turkish labels onto the canonical English fact keys
consumed by `domain.services.fundamental_analyzer_service`. Callers that already
hold canonical keys (e.g. tests, replays from `kap_financial_statements.facts`) can
pass them straight through — canonical keys are recognised as-is.

Everything here is pure (no I/O), so it is cheap to unit-test against fixtures.

KAP xlsx workbooks contain **multiple sheets** — one per statement type:
  Sheet 1: Finansal Durum Tablosu (Balance Sheet)
  Sheet 2: Kâr veya Zarar Tablosu (Income Statement)
  Sheet 3: Nakit Akış Tablosu (Cash Flow)
  Sheet 4+: possibly equity changes, etc.
`parse_financial_table_xlsx` reads ALL sheets and merges facts (first value wins).
"""
from __future__ import annotations

import io
import re
import unicodedata
import zipfile
from typing import Any, Dict, Iterable, List, Optional, Tuple
from xml.etree import ElementTree as ET

# Canonical fact keys. The analyzer derives every ratio from this vocabulary.
CANONICAL_KEYS: tuple[str, ...] = (
    # income statement
    "revenue",
    "cost_of_sales",
    "gross_profit",
    "operating_profit",
    "ebit",
    "depreciation_amortization",
    "interest_expense",
    "tax_expense",
    "pretax_profit",
    "net_income",
    # balance sheet
    "total_assets",
    "current_assets",
    "inventories",
    "current_liabilities",
    "total_liabilities",
    "total_equity",
    "equity_parent",
    "cash_and_equivalents",
    "short_term_debt",
    "long_term_debt",
    # cash flow
    "operating_cash_flow",
    "capex",
    "dividends_paid",
    # share / market data (usually supplied out-of-band, kept here for completeness)
    "shares_outstanding",
)

# Ordered (canonical_key, [label patterns]) — first matching pattern wins, and more
# specific keys are listed before the broader ones they could be confused with
# (e.g. "operating_profit" before "gross_profit"). Patterns are matched against an
# accent-folded, lowercased label using substring containment.
_LABEL_PATTERNS: List[tuple[str, List[str]]] = [
    ("cost_of_sales", ["satislarin maliyeti", "satislar maliyeti"]),
    ("gross_profit", ["brut kar", "brut esas faaliyet kari", "brut kar (zarar)"]),
    ("operating_profit", ["esas faaliyet kari", "faaliyet kari", "esas faaliyet kar"]),
    ("revenue", ["hasilat", "satis gelirleri", "faiz, ucret, prim"]),
    ("depreciation_amortization", ["amortisman", "itfa ve tukenme", "amortisman ve itfa"]),
    ("interest_expense", ["finansman gideri", "faiz gideri", "esas faaliyetlerden finansman gideri"]),
    ("tax_expense", ["vergi gideri", "donem vergi gideri", "surdurulen faaliyetler vergi"]),
    ("pretax_profit", ["surdurulen faaliyetler vergi oncesi kar", "vergi oncesi kar"]),
    ("net_income", [
        "donem kari (zarari)", "donem net kar", "donem kari", "net donem kari",
        "ana ortakliga ait", "donem kar zarari", "net kar",
    ]),
    ("current_assets", ["donen varliklar"]),
    ("inventories", ["stoklar"]),
    ("cash_and_equivalents", ["nakit ve nakit benzerleri", "nakit ve nakit benzeri"]),
    ("total_assets", ["toplam varliklar", "varliklar toplami", "aktif toplami"]),
    ("current_liabilities", ["kisa vadeli yukumlulukler"]),
    ("short_term_debt", ["kisa vadeli borclanmalar", "kisa vadeli finansal borclar"]),
    ("long_term_debt", ["uzun vadeli borclanmalar", "uzun vadeli finansal borclar"]),
    ("total_liabilities", ["toplam yukumlulukler", "yukumlulukler toplami"]),
    ("equity_parent", ["ana ortakliga ait ozkaynaklar"]),
    ("total_equity", ["ozkaynaklar", "toplam ozkaynaklar", "ozkaynaklar toplami"]),
    ("operating_cash_flow", [
        "isletme faaliyetlerinden", "esas faaliyetlerden kaynaklanan nakit",
        "isletme faaliyetlerine iliskin nakit",
    ]),
    ("capex", ["maddi duran varlik alimlari", "yatirim harcamalari", "maddi ve maddi olmayan duran varlik alimlari"]),
    ("dividends_paid", ["odenen temettu", "odenen kar paylari", "temettu odemeleri"]),
    ("shares_outstanding", ["odenmis sermaye", "cikarilmis sermaye", "pay adedi"]),
]

_NUMERIC_CLEAN_RE = re.compile(r"[^\d,.\-]")


def _fold(text: str) -> str:
    """Lowercase + strip Turkish diacritics so label matching is accent-insensitive."""
    text = (text or "").strip().lower()
    # Turkish-specific folds before NFKD (ı/İ don't fold cleanly via NFKD alone).
    text = text.replace("ı", "i").replace("İ", "i").replace("ş", "s").replace(
        "ğ", "g"
    ).replace("ü", "u").replace("ö", "o").replace("ç", "c")
    text = unicodedata.normalize("NFKD", text)
    text = "".join(c for c in text if not unicodedata.combining(c))
    return re.sub(r"\s+", " ", text).strip()


def coerce_number(value: Any) -> Optional[float]:
    """
    Parse a KAP-formatted number into a float, or None when not numeric.

    Handles Turkish thousands/decimal separators ("1.234.567,89"), plain floats,
    parenthesised negatives ("(1.234)"), and already-numeric values.
    """
    if value is None:
        return None
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)

    text = str(value).strip()
    if not text:
        return None

    negative = text.startswith("(") and text.endswith(")")
    text = _NUMERIC_CLEAN_RE.sub("", text)
    if not text or text in {"-", ".", ","}:
        return None

    # Decide separators: if both present, the last one is the decimal separator.
    if "," in text and "." in text:
        if text.rfind(",") > text.rfind("."):
            text = text.replace(".", "").replace(",", ".")
        else:
            text = text.replace(",", "")
    elif "," in text:
        # Lone comma → decimal separator (Turkish convention).
        text = text.replace(".", "").replace(",", ".")
    elif "." in text:
        # Lone dot(s): Turkish uses "." as the thousands separator. Treat it as such
        # when every group after the first is exactly 3 digits ("1.000", "1.234.567");
        # otherwise it's a genuine decimal point ("12.5").
        groups = text.lstrip("-").split(".")
        if len(groups) > 1 and all(len(g) == 3 for g in groups[1:]):
            text = text.replace(".", "")
        # else: leave as a decimal.

    try:
        number = float(text)
    except ValueError:
        return None
    return -number if negative else number


def _match_key(folded_label: str) -> Optional[str]:
    for key, patterns in _LABEL_PATTERNS:
        for pat in patterns:
            if pat in folded_label:
                return key
    return None


def _iter_label_value(raw: Any) -> Iterable[tuple[str, Any]]:
    """
    Yield (label, value) pairs from the several shapes KAP / callers may provide:
      - {label: value}
      - [{"label": .., "value": ..}, ...]  (also accepts memberName/itemName/value/amount)
      - [["label", value], ...]
    """
    if isinstance(raw, dict):
        for label, value in raw.items():
            yield str(label), value
        return
    if isinstance(raw, list):
        for item in raw:
            if isinstance(item, dict):
                label = (
                    item.get("label")
                    or item.get("memberName")
                    or item.get("itemName")
                    or item.get("name")
                    or item.get("concept")
                )
                value = item.get("value")
                if value is None:
                    value = item.get("amount")
                if label is not None:
                    yield str(label), value
            elif isinstance(item, (list, tuple)) and len(item) >= 2:
                yield str(item[0]), item[1]


def normalize_facts(raw: Any) -> Dict[str, float]:
    """
    Map a raw KAP statement into canonical numeric facts.

    Recognises canonical keys passed through directly, otherwise matches Turkish
    concept labels. When several rows map to the same canonical key (KAP repeats
    concepts across statement sections), the first numeric value wins. Non-numeric
    or unmatched rows are dropped.
    """
    canonical_set = set(CANONICAL_KEYS)
    facts: Dict[str, float] = {}

    for label, value in _iter_label_value(raw):
        number = coerce_number(value)
        if number is None:
            continue

        # Pass canonical keys straight through.
        if label in canonical_set:
            facts.setdefault(label, number)
            continue

        key = _match_key(_fold(label))
        if key is not None:
            facts.setdefault(key, number)

    # Derive total financial debt if its components are present but the total isn't.
    if "short_term_debt" in facts or "long_term_debt" in facts:
        facts.setdefault(
            "total_debt",
            facts.get("short_term_debt", 0.0) + facts.get("long_term_debt", 0.0),
        )
    return facts


def _local(tag: str) -> str:
    """Strip an XML namespace, returning the local element name."""
    return tag.rsplit("}", 1)[-1]


def _col_index(cell_ref: str) -> int:
    """Convert an A1-style cell reference to a 0-based column index ("C7" -> 2)."""
    letters = "".join(c for c in cell_ref if c.isalpha())
    idx = 0
    for ch in letters:
        idx = idx * 26 + (ord(ch.upper()) - ord("A") + 1)
    return idx - 1


def _parse_sheet_xml(sheet_root, shared: List[str]) -> List[List[Any]]:
    """Parse one SpreadsheetML worksheet root into a row-major grid of cell values."""
    grid: List[List[Any]] = []
    for elem in sheet_root.iter():
        if _local(elem.tag) != "row":
            continue
        cells: Dict[int, Any] = {}
        for c in elem:
            if _local(c.tag) != "c":
                continue
            ref = c.get("r", "")
            col = _col_index(ref) if ref else len(cells)
            ctype = c.get("t")
            value: Any = None
            for child in c:
                local = _local(child.tag)
                if local == "v":
                    value = child.text
                elif local == "is":  # inline string
                    value = "".join(
                        (t.text or "") for t in child.iter() if _local(t.tag) == "t"
                    )
            if ctype == "s" and value is not None:
                try:
                    value = shared[int(value)]
                except (ValueError, IndexError):
                    value = None
            cells[col] = value
        width = (max(cells) + 1) if cells else 0
        grid.append([cells.get(i) for i in range(width)])
    return grid


def _load_xlsx(content: bytes) -> Tuple[zipfile.ZipFile, List[str], List[str]]:
    """
    Open an xlsx zip, load the shared strings table, and return the sorted sheet
    file paths. Returns (zf, shared_strings, sheet_files) or raises on bad input.
    """
    zf = zipfile.ZipFile(io.BytesIO(content))
    names = set(zf.namelist())

    shared: List[str] = []
    if "xl/sharedStrings.xml" in names:
        root = ET.fromstring(zf.read("xl/sharedStrings.xml"))
        for si in root:
            if _local(si.tag) != "si":
                continue
            text = "".join(
                (t.text or "") for t in si.iter() if _local(t.tag) == "t"
            )
            shared.append(text)

    sheet_files = sorted(n for n in names if re.match(r"xl/worksheets/sheet\d+\.xml$", n))
    return zf, shared, sheet_files


def read_xlsx_grid(content: bytes) -> List[List[Any]]:
    """
    Read the FIRST worksheet of an .xlsx file into a row-major grid (no deps).

    Provided for backward compatibility. Use `read_all_xlsx_grids` when you need
    data from all sheets (e.g. KAP workbooks with Balance Sheet / Income Statement
    / Cash Flow on separate tabs).

    Returns [] on anything unparseable.
    """
    grids = read_all_xlsx_grids(content)
    return grids[0] if grids else []


def read_all_xlsx_grids(content: bytes) -> List[List[List[Any]]]:
    """
    Read ALL worksheets from an .xlsx file into a list of row-major grids (no deps).

    KAP financial-statement workbooks place different statement types on separate
    sheets (Balance Sheet, Income Statement, Cash Flow…). This function returns one
    grid per sheet so callers can merge facts across all statement types.

    Returns [] on anything unparseable.
    """
    try:
        zf, shared, sheet_files = _load_xlsx(content)
    except (zipfile.BadZipFile, TypeError, Exception):
        return []

    if not sheet_files:
        return []

    grids: List[List[List[Any]]] = []
    for sf in sheet_files:
        try:
            sheet_root = ET.fromstring(zf.read(sf))
            grids.append(_parse_sheet_xml(sheet_root, shared))
        except Exception:
            grids.append([])
    return grids


def _extract_facts_from_grid(
    grid: List[List[Any]],
) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    """
    Extract (current_period, prior_period) label→raw-value dicts from one grid.

    KAP statement sheets lay out:  label | current-period value | prior-period value
    For each data row we take the first numeric column as current and the next as prior.
    Header rows (all cells are text) are skipped naturally because they produce no
    numeric values.
    """
    current: Dict[str, Any] = {}
    prior: Dict[str, Any] = {}

    for row in grid:
        if not row:
            continue
        label: Optional[str] = None
        label_col = -1
        for i, cell in enumerate(row):
            if isinstance(cell, str) and cell.strip() and coerce_number(cell) is None:
                label = cell.strip()
                label_col = i
                break
        if label is None:
            continue

        numbers = [coerce_number(c) for c in row[label_col + 1:]]
        numbers = [n for n in numbers if n is not None]
        if not numbers:
            continue

        current.setdefault(label, numbers[0])
        if len(numbers) > 1:
            prior.setdefault(label, numbers[1])

    return current, prior


def parse_financial_table_xlsx(content: bytes) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    """
    Parse a KAP "Finansal Tablolar" Excel into (current_period, prior_period) facts.

    KAP statement workbooks contain multiple sheets (Balance Sheet, Income Statement,
    Cash Flow, …). This function reads ALL sheets and merges them into a single pair
    of label→raw-value dicts — the first occurrence of each label wins so that the
    same line item appearing in multiple sheets is not double-counted.

    Returns two ``{label: raw_value}`` dicts ready for :func:`normalize_facts`. Either
    may be empty (e.g. a workbook that could not be opened or had no numeric data).
    """
    grids = read_all_xlsx_grids(content)
    current: Dict[str, Any] = {}
    prior: Dict[str, Any] = {}

    for grid in grids:
        c, p = _extract_facts_from_grid(grid)
        for k, v in c.items():
            current.setdefault(k, v)
        for k, v in p.items():
            prior.setdefault(k, v)

    return current, prior


# ── KAP disclosure-page (HTML/markdown) statement parsing ─────────────────────
# KAP killed the public financialTable .xlsx download (the endpoint now 404s even
# through a real browser), but the financial-report *disclosure page*
# (`/tr/Bildirim/{disclosureIndex}`) renders the full statements as HTML tables that
# Firecrawl can scrape as markdown. Each data row is laid out as:
#   |  |  | <Turkish label> | <English XBRL label> |  |  | | <note?> | <current> | <prior> |
# The English XBRL label is standardised and unambiguous, so we key on it (the Turkish
# substring matching used for .xlsx is too loose here — e.g. "Diğer Dönen Varlıklar"
# would shadow "Toplam Dönen Varlıklar"). Falls back to Turkish matching when no English
# label maps. Trailing two numeric columns are the current / prior period values.
_ENGLISH_LABEL_MAP: dict[str, str] = {
    "revenue": "revenue",
    "cost of sales": "cost_of_sales",
    "gross profit (loss)": "gross_profit",
    "profit (loss) from operating activities": "operating_profit",
    "profit (loss)": "net_income",
    "finance costs": "interest_expense",
    "total assets": "total_assets",
    "total current assets": "current_assets",
    "total current liabilities": "current_liabilities",
    "total equity": "total_equity",
    "equity attributable to owners of parent": "equity_parent",
    "cash and cash equivalents": "cash_and_equivalents",
    "inventories": "inventories",
    "current borrowings": "short_term_debt",
    "long term borrowings": "long_term_debt",
    "cash flows from (used in) operating activities": "operating_cash_flow",
    "adjustments for depreciation and amortisation expense": "depreciation_amortization",
    "purchase of property, plant and equipment": "capex",
    "issued capital": "shares_outstanding",
    "total liabilities": "total_liabilities",
    "dividends paid": "dividends_paid",
    "long-term borrowings": "long_term_debt",
    "non-current borrowings": "long_term_debt",
}

_MD_CLEAN_RE = re.compile(r"<br>.*$|[*_`]")


def _clean_md_cell(cell: str) -> str:
    """Strip markdown emphasis and trailing <br>-joined sub-text from a table cell."""
    return re.sub(r"\s+", " ", _MD_CLEAN_RE.sub("", cell)).strip()


def parse_financial_table_markdown(markdown: str) -> Tuple[Dict[str, float], Dict[str, float]]:
    """
    Parse a KAP financial-report disclosure page (scraped to markdown) into
    (current_period, prior_period) canonical facts.

    Matches each statement row primarily on its English XBRL label, falling back to
    the Turkish label patterns. The first value found for a canonical key wins (the
    main statement line appears before equity-movement sub-rows that reuse the label).
    Returns two ``{canonical_key: value}`` dicts ready to pass straight to the analyzer.
    """
    current: Dict[str, float] = {}
    prior: Dict[str, float] = {}
    if not markdown:
        return current, prior

    for line in markdown.splitlines():
        stripped = line.strip()
        if not stripped.startswith("|"):
            continue
        cells = [_clean_md_cell(c) for c in stripped.strip("|").split("|")]

        # The two text cells are the Turkish label then the English XBRL label.
        text_cells = [
            c for c in cells
            if c and coerce_number(c) is None and re.search(r"[A-Za-zÇĞİÖŞÜçğıöşü]", c)
        ]
        if not text_cells:
            continue
        turkish_label = text_cells[0]
        english_label = text_cells[1] if len(text_cells) > 1 else ""

        # English XBRL labels are authoritative: if a row carries one, key strictly on
        # it (an unmapped English label means "not a concept we track" — skip it). Only
        # rows with no English label fall back to loose Turkish substring matching. This
        # stops sub-items like "Current tax liabilities" from shadowing "Profit (Loss)".
        if english_label:
            key = _ENGLISH_LABEL_MAP.get(_fold(english_label))
        else:
            key = _match_key(_fold(turkish_label))
        if key is None:
            continue

        numbers = [coerce_number(c) for c in cells]
        numbers = [n for n in numbers if n is not None]
        if not numbers:
            continue
        # Trailing columns are current | prior; a lone trailing number is current-only.
        current.setdefault(key, numbers[-2] if len(numbers) >= 2 else numbers[-1])
        if len(numbers) >= 2:
            prior.setdefault(key, numbers[-1])

    # Derive total financial debt from the maturity split when not given directly.
    for facts in (current, prior):
        if "short_term_debt" in facts or "long_term_debt" in facts:
            facts.setdefault(
                "total_debt",
                facts.get("short_term_debt", 0.0) + facts.get("long_term_debt", 0.0),
            )
    return current, prior


def derive_period(year: Any, quarter: Any = None) -> str:
    """
    Build the canonical period label used as the storage key.

    Annual reports → "YYYY"; interim reports → "YYYY-Qn". Quarter may be given as a
    KAP term code (3/6/9/12 cumulative months) or a 1-4 quarter number.
    """
    year_str = str(year).strip()
    if not quarter:
        return year_str
    q = str(quarter).strip()
    month_to_q = {"3": "Q1", "6": "Q2", "9": "Q3", "12": "Q4"}
    if q in month_to_q:
        return f"{year_str}-{month_to_q[q]}"
    if q in {"1", "2", "3", "4"}:
        return f"{year_str}-Q{q}"
    return year_str
