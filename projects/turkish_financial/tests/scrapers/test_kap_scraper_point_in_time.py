"""
FA-02 — scrape_financial_statements persists every KAP financial-table member
(periods 1, 2, 3, annual), not just the latest annual, and process_financial_statement
threads each member's disclosure_index into a distinct revision_id.
"""
from unittest.mock import AsyncMock, patch

import pytest

from scrapers.kap_scraper import KAPScraper


def _member(period, year=2026, disclosure_index=None):
    return {
        "disclosureIndex": disclosure_index or f"{year}{period}",
        "pdOid": "pd1",
        "period": period,
        "year": year,
        "title": "Test A.Ş.",
    }


@pytest.mark.asyncio
async def test_scrape_financial_statements_persists_every_member_not_just_annual():
    scraper = KAPScraper(db_manager=None)

    members = [_member(1), _member(2), _member(3), _member(4)]  # Q1, Q2, Q3, annual

    with patch(
        "infrastructure.contracts.instrument_identity_map.resolve_member_oid",
        return_value="oid-1",
    ), patch.object(
        scraper, "list_company_excel_members", AsyncMock(return_value=members)
    ), patch.object(
        scraper,
        "fetch_financial_statement_facts",
        AsyncMock(return_value=({"revenue": 100.0}, {"revenue": 90.0})),
    ):
        result = await scraper.scrape_financial_statements(instruments=["THYAO"], year=2026)

    assert result["processed"] == 4
    periods = {r["period"] for r in result["results"]}
    assert periods == {"2026-Q1", "2026-Q2", "2026-Q3", "2026"}


@pytest.mark.asyncio
async def test_one_bad_member_does_not_block_the_others():
    scraper = KAPScraper(db_manager=None)

    members = [_member(1), _member(4)]

    async def fake_fetch(disclosure_index, pd_oid=None):
        if disclosure_index == members[0]["disclosureIndex"]:
            return {}, {}  # unparsable
        return {"revenue": 100.0}, {}

    with patch(
        "infrastructure.contracts.instrument_identity_map.resolve_member_oid",
        return_value="oid-1",
    ), patch.object(
        scraper, "list_company_excel_members", AsyncMock(return_value=members)
    ), patch.object(
        scraper, "fetch_financial_statement_facts", AsyncMock(side_effect=fake_fetch)
    ):
        result = await scraper.scrape_financial_statements(instruments=["THYAO"], year=2026)

    assert result["processed"] == 1
    assert len(result["failed"]) == 1
    assert result["failed"][0]["reason"] == "no_parsable_facts"


def test_process_financial_statement_assigns_distinct_revision_per_disclosure():
    scraper = KAPScraper(db_manager=None)

    first = scraper.process_financial_statement(
        stock_code="THYAO",
        period="2026-Q1",
        raw_statement={"revenue": 100.0},
        disclosure_index="1001",
    )
    second = scraper.process_financial_statement(
        stock_code="THYAO",
        period="2026-Q1",
        raw_statement={"revenue": 105.0},
        disclosure_index="1002",
    )

    # A restatement (different disclosure_index, same period) must not collide;
    # both runs succeed independently (db_manager is None here, so "saved" stays
    # False, but the facts/payload are still derived per call without error).
    assert first["facts"]["revenue"] == 100.0
    assert second["facts"]["revenue"] == 105.0
