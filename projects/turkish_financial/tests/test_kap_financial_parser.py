"""
Unit tests for the KAP financial-statement parser.

Loads the module directly from its file so the test does not pull the heavy
`scrapers` package __init__ (aiohttp / bs4 / LLM providers). Covers Turkish number
coercion, label→canonical mapping across the shapes KAP/callers send, canonical
passthrough, total-debt derivation, and period labelling.
"""
import importlib.util
import io
import os
import zipfile

_PARSER_PATH = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "scrapers", "kap_financial_parser.py")
)

_NS = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"


def _make_xlsx(shared, rows):
    """Build a minimal .xlsx (sharedStrings + one sheet) in memory.

    `shared` is the shared-string table; `rows` is a list of rows, each a list of
    cells where a cell is ("s", idx) for a shared string or ("n", number) for a value.
    """
    si = "".join(f"<si><t>{s}</t></si>" for s in shared)
    shared_xml = (
        f'<?xml version="1.0"?><sst xmlns="{_NS}" count="{len(shared)}" '
        f'uniqueCount="{len(shared)}">{si}</sst>'
    )
    row_xml = ""
    for r, row in enumerate(rows, start=1):
        cells = ""
        for c, cell in enumerate(row):
            ref = f"{chr(ord('A') + c)}{r}"
            kind, val = cell
            if kind == "s":
                cells += f'<c r="{ref}" t="s"><v>{val}</v></c>'
            else:
                cells += f'<c r="{ref}"><v>{val}</v></c>'
        row_xml += f'<row r="{r}">{cells}</row>'
    sheet_xml = (
        f'<?xml version="1.0"?><worksheet xmlns="{_NS}"><sheetData>{row_xml}'
        f"</sheetData></worksheet>"
    )
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("xl/sharedStrings.xml", shared_xml)
        zf.writestr("xl/worksheets/sheet1.xml", sheet_xml)
    return buf.getvalue()


def _load():
    spec = importlib.util.spec_from_file_location("kap_financial_parser_under_test", _PARSER_PATH)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


parser = _load()


class TestCoerceNumber:
    def test_turkish_thousands_and_decimal(self):
        assert parser.coerce_number("1.234.567,89") == 1234567.89

    def test_plain_float(self):
        assert parser.coerce_number(1234.5) == 1234.5

    def test_lone_comma_is_decimal(self):
        assert parser.coerce_number("12,5") == 12.5

    def test_parenthesised_is_negative(self):
        assert parser.coerce_number("(1.000)") == -1000.0

    def test_non_numeric_is_none(self):
        assert parser.coerce_number("n/a") is None
        assert parser.coerce_number("") is None
        assert parser.coerce_number(None) is None
        assert parser.coerce_number(True) is None


class TestNormalizeFacts:
    def test_turkish_labels_dict(self):
        raw = {
            "Hasılat": "1.000",
            "Brüt Kâr (Zarar)": "400",
            "Esas Faaliyet Kârı": "200",
            "Dönem Kârı (Zararı)": "150",
            "Toplam Varlıklar": "2.000",
            "Özkaynaklar": "800",
            "Kısa Vadeli Yükümlülükler": "250",
            "Dönen Varlıklar": "500",
            "Stoklar": "100",
        }
        facts = parser.normalize_facts(raw)
        assert facts["revenue"] == 1000.0
        assert facts["gross_profit"] == 400.0
        assert facts["operating_profit"] == 200.0
        assert facts["net_income"] == 150.0
        assert facts["total_assets"] == 2000.0
        assert facts["total_equity"] == 800.0
        assert facts["current_liabilities"] == 250.0
        assert facts["current_assets"] == 500.0
        assert facts["inventories"] == 100.0

    def test_list_of_label_value_dicts(self):
        raw = [
            {"label": "Hasılat", "value": "500"},
            {"memberName": "Dönem Net Kârı", "value": "75"},
        ]
        facts = parser.normalize_facts(raw)
        assert facts["revenue"] == 500.0
        assert facts["net_income"] == 75.0

    def test_canonical_keys_passthrough(self):
        facts = parser.normalize_facts({"revenue": 1000, "net_income": 150})
        assert facts["revenue"] == 1000.0
        assert facts["net_income"] == 150.0

    def test_total_debt_derived_from_components(self):
        facts = parser.normalize_facts(
            {"Kısa Vadeli Borçlanmalar": "100", "Uzun Vadeli Borçlanmalar": "300"}
        )
        assert facts["short_term_debt"] == 100.0
        assert facts["long_term_debt"] == 300.0
        assert facts["total_debt"] == 400.0

    def test_unmatched_and_nonnumeric_dropped(self):
        facts = parser.normalize_facts({"Bilinmeyen Kalem": "5", "Hasılat": "n/a"})
        assert "revenue" not in facts
        assert facts == {} or all(isinstance(v, float) for v in facts.values())


class TestXlsxParsing:
    SHARED = [
        "Kalem", "Cari Dönem", "Önceki Dönem",   # 0,1,2 (header)
        "Hasılat", "Brüt Kâr (Zarar)", "Dönem Kârı (Zararı)",  # 3,4,5
        "Toplam Varlıklar", "Özkaynaklar",        # 6,7
    ]
    ROWS = [
        [("s", 0), ("s", 1), ("s", 2)],            # header — text values, skipped
        [("s", 3), ("n", 1000), ("n", 800)],       # Hasılat
        [("s", 4), ("n", 400), ("n", 300)],        # Brüt Kâr
        [("s", 5), ("n", 150), ("n", 120)],        # Dönem Kârı
        [("s", 6), ("n", 2000), ("n", 1800)],      # Toplam Varlıklar
        [("s", 7), ("n", 800), ("n", 700)],        # Özkaynaklar
    ]

    def test_read_grid(self):
        grid = parser.read_xlsx_grid(_make_xlsx(self.SHARED, self.ROWS))
        assert grid[1][0] == "Hasılat"
        assert parser.coerce_number(grid[1][1]) == 1000.0

    def test_current_and_prior_split(self):
        current, prior = parser.parse_financial_table_xlsx(_make_xlsx(self.SHARED, self.ROWS))
        assert current["Hasılat"] == 1000.0
        assert prior["Hasılat"] == 800.0
        assert current["Dönem Kârı (Zararı)"] == 150.0
        assert prior["Dönem Kârı (Zararı)"] == 120.0
        # header row (all-text value cells) must be skipped
        assert "Kalem" not in current

    def test_end_to_end_normalize(self):
        current, prior = parser.parse_financial_table_xlsx(_make_xlsx(self.SHARED, self.ROWS))
        cur_facts = parser.normalize_facts(current)
        prior_facts = parser.normalize_facts(prior)
        assert cur_facts["revenue"] == 1000.0
        assert cur_facts["gross_profit"] == 400.0
        assert cur_facts["net_income"] == 150.0
        assert cur_facts["total_assets"] == 2000.0
        assert cur_facts["total_equity"] == 800.0
        assert prior_facts["revenue"] == 800.0

    def test_bad_bytes_returns_empty(self):
        assert parser.read_xlsx_grid(b"not a zip") == []
        assert parser.parse_financial_table_xlsx(b"not a zip") == ({}, {})

    def test_read_all_grids_single_sheet(self):
        grids = parser.read_all_xlsx_grids(_make_xlsx(self.SHARED, self.ROWS))
        assert len(grids) == 1
        assert grids[0][1][0] == "Hasılat"

    def test_read_all_grids_bad_bytes(self):
        assert parser.read_all_xlsx_grids(b"garbage") == []


class TestMultiSheetXlsx:
    """
    KAP workbooks put Balance Sheet / Income Statement / Cash Flow on separate sheets.
    parse_financial_table_xlsx must merge them into a single (current, prior) pair.
    """

    BS_SHARED = [
        "Kalem", "Cari Dönem", "Önceki Dönem",  # 0,1,2
        "Toplam Varlıklar", "Özkaynaklar",       # 3,4
        "Kısa Vadeli Yükümlülükler",             # 5
    ]
    BS_ROWS = [
        [("s", 0), ("s", 1), ("s", 2)],          # header
        [("s", 3), ("n", 5000), ("n", 4000)],    # Toplam Varlıklar
        [("s", 4), ("n", 2000), ("n", 1700)],    # Özkaynaklar
        [("s", 5), ("n", 800), ("n", 700)],      # Kısa Vadeli Yükümlülükler
    ]

    IS_SHARED = [
        "Gelir", "Dönem", "Önceki",              # 0,1,2
        "Hasılat", "Brüt Kâr (Zarar)",           # 3,4
        "Dönem Kârı (Zararı)",                   # 5
    ]
    IS_ROWS = [
        [("s", 0), ("s", 1), ("s", 2)],          # header
        [("s", 3), ("n", 3000), ("n", 2500)],    # Hasılat
        [("s", 4), ("n", 1200), ("n", 900)],     # Brüt Kâr
        [("s", 5), ("n", 600), ("n", 500)],      # Dönem Kârı
    ]

    def _make_multi_sheet_xlsx(self):
        """Build a two-sheet xlsx in memory."""
        _NS = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"

        def build_shared(shared):
            si = "".join(f"<si><t>{s}</t></si>" for s in shared)
            return (
                f'<?xml version="1.0"?><sst xmlns="{_NS}" count="{len(shared)}" '
                f'uniqueCount="{len(shared)}">{si}</sst>'
            )

        def build_sheet(rows):
            row_xml = ""
            for r, row in enumerate(rows, start=1):
                cells = ""
                for c, cell in enumerate(row):
                    ref = f"{chr(ord('A') + c)}{r}"
                    kind, val = cell
                    if kind == "s":
                        cells += f'<c r="{ref}" t="s"><v>{val}</v></c>'
                    else:
                        cells += f'<c r="{ref}"><v>{val}</v></c>'
                row_xml += f'<row r="{r}">{cells}</row>'
            return (
                f'<?xml version="1.0"?><worksheet xmlns="{_NS}">'
                f"<sheetData>{row_xml}</sheetData></worksheet>"
            )

        # Two sheets share separate shared-string tables — in the real xlsx they
        # share ONE table; here we concatenate them for simplicity and adjust indices.
        combined = self.BS_SHARED + self.IS_SHARED
        all_idx_offset = len(self.BS_SHARED)

        # Re-index IS_ROWS to use offsets into the combined shared table.
        is_rows_reindexed = []
        for row in self.IS_ROWS:
            new_row = []
            for kind, val in row:
                if kind == "s":
                    new_row.append(("s", val + all_idx_offset))
                else:
                    new_row.append((kind, val))
            is_rows_reindexed.append(new_row)

        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w") as zf:
            zf.writestr("xl/sharedStrings.xml", build_shared(combined))
            zf.writestr("xl/worksheets/sheet1.xml", build_sheet(self.BS_ROWS))
            zf.writestr("xl/worksheets/sheet2.xml", build_sheet(is_rows_reindexed))
        return buf.getvalue()

    def test_both_sheets_are_loaded(self):
        grids = parser.read_all_xlsx_grids(self._make_multi_sheet_xlsx())
        assert len(grids) == 2

    def test_balance_sheet_and_income_merged(self):
        xlsx = self._make_multi_sheet_xlsx()
        current, prior = parser.parse_financial_table_xlsx(xlsx)
        # Balance sheet items
        assert current["Toplam Varlıklar"] == 5000.0
        assert current["Özkaynaklar"] == 2000.0
        assert prior["Özkaynaklar"] == 1700.0
        # Income statement items from sheet 2
        assert current["Hasılat"] == 3000.0
        assert prior["Hasılat"] == 2500.0
        assert current["Dönem Kârı (Zararı)"] == 600.0

    def test_normalize_merged_facts(self):
        xlsx = self._make_multi_sheet_xlsx()
        current, prior = parser.parse_financial_table_xlsx(xlsx)
        facts = parser.normalize_facts(current)
        assert facts["total_assets"] == 5000.0
        assert facts["total_equity"] == 2000.0
        assert facts["revenue"] == 3000.0
        assert facts["net_income"] == 600.0


class TestDerivePeriod:
    def test_annual(self):
        assert parser.derive_period("2025") == "2025"

    def test_interim_month_term(self):
        assert parser.derive_period("2026", "3") == "2026-Q1"
        assert parser.derive_period("2026", "12") == "2026-Q4"

    def test_interim_quarter_number(self):
        assert parser.derive_period("2026", "2") == "2026-Q2"
