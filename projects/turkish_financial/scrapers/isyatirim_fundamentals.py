"""Adapter for public fundamental indicators on İş Yatırım company cards."""
from __future__ import annotations

import re
from typing import Any

import requests
from bs4 import BeautifulSoup

from scrapers.isyatirim_market_data import TICKER_RE


COMPANY_CARD_URL = "https://www.isyatirim.com.tr/tr-tr/analiz/hisse/Sayfalar/sirket-karti.aspx"
NUMBER_RE = re.compile(r"[-−]?\d[\d.]*,\d+|[-−]?\d+[\d.]*")


def _number(value: str | None) -> float | None:
    """Parse a single Turkish-formatted decimal, retaining null for ambiguous text."""
    if not value:
        return None
    matches = NUMBER_RE.findall(value.replace("−", "-"))
    if len(matches) != 1:
        return None
    number = matches[0].replace(".", "").replace(",", ".")
    try:
        return float(number)
    except ValueError:
        return None


def _box_with_heading(document: BeautifulSoup, title: str):
    for heading in document.select(".box-title h3"):
        if heading.get_text(" ", strip=True).rstrip("*") == title:
            return heading.find_parent(class_="box")
    return None


def _table_map(box) -> dict[str, str]:
    if box is None:
        return {}
    return {
        row.find("th").get_text(" ", strip=True): row.find("td").get_text(" ", strip=True)
        for row in box.select("tr")
        if row.find("th") is not None and row.find("td") is not None
    }


def fetch_fundamentals(instrument: str) -> dict[str, Any]:
    """Fetch and normalize public, source-reported company-card fundamentals.

    The source labels financial-table values as ``mn TL``.  They remain explicitly
    labelled as millions of TRY and are not merged with the KAP statement pipeline.
    """
    ticker = instrument.strip().upper()
    if not TICKER_RE.fullmatch(ticker):
        raise ValueError("invalid BIST instrument")
    response = requests.get(
        COMPANY_CARD_URL,
        params={"hisse": ticker},
        headers={"User-Agent": "TurkishFinancialResearch/1.0"},
        timeout=20,
    )
    response.raise_for_status()
    document = BeautifulSoup(response.text, "html.parser")
    short_table = document.select_one("#malitabloShortTbody")
    if short_table is None:
        raise LookupError("İş Yatırım does not expose a financial table for this instrument")

    selected_periods = [
        select.select_one("option[selected]").get_text(" ", strip=True)
        for select in document.select("#ddlMaliTabloFirst, #ddlMaliTabloSecond")
        if select.select_one("option[selected]") is not None
    ]
    statement = {}
    statement_labels = {
        "Özkaynaklar": "equity_million_try",
        "Ödenmiş Sermaye": "paid_in_capital_million_try",
        "Net Kâr": "net_income_million_try",
    }
    for row in short_table.select("tr"):
        cells = row.find_all("td")
        if len(cells) < 2:
            continue
        key = statement_labels.get(cells[0].get_text(" ", strip=True))
        if key:
            statement[key] = _number(cells[1].get_text(" ", strip=True))

    current = _table_map(_box_with_heading(document, "Cari Değerler"))
    valuation_labels = {
        "F/K": "price_to_earnings",
        "FD/FAVÖK": "enterprise_value_to_ebitda",
        "PD/DD": "price_to_book",
        "FD/Satışlar": "enterprise_value_to_sales",
        "Yabancı Oranı (%)": "foreign_ownership_percent",
        "Piyasa Değeri": "market_cap_million_try",
        "Net Borç": "net_debt_million_try",
        "Halka Açıklık Oranı (%)": "free_float_percent",
    }
    current_values = {
        key: _number(current.get(label))
        for label, key in valuation_labels.items()
        if label in current
    }
    full_table = document.select_one('table[data-csvname="malitablo"]')
    history_periods = [
        select.select_one("option[selected]").get_text(" ", strip=True)
        for select in document.select("#ddlMaliTabloDonem1, #ddlMaliTabloDonem2, #ddlMaliTabloDonem3, #ddlMaliTabloDonem4")
        if select.select_one("option[selected]") is not None
    ]
    history = [{"report_period": period, "unit": "TRY", "items": []} for period in history_periods]
    if full_table is not None:
        for row in full_table.select("tbody tr"):
            cells = row.find_all(["th", "td"])
            if len(cells) < 2:
                continue
            label = cells[0].get_text(" ", strip=True)
            for index, cell in enumerate(cells[1:len(history) + 1]):
                value = _number(cell.get_text(" ", strip=True))
                if value is not None:
                    history[index]["items"].append({"label": label, "value_try": value})
    if not statement and not current_values:
        raise LookupError("İş Yatırım returned no recognizable fundamentals for this instrument")
    return {
        "currency": "TRY",
        "statement_unit": "million TRY",
        "upstream": "isyatirim-public-company-card",
        "reported_periods": selected_periods,
        "statement_snapshot": statement,
        "one_year_statement_history": history,
        "current_valuation": current_values,
        "fields": {
            "statement_snapshot": "Reported statement snapshot from the public company card, in million TRY",
            "current_valuation": "Current market ratios and source-reported ownership/valuation indicators",
        },
    }
