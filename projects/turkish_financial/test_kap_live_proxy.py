#!/usr/bin/env python3
"""
Live integration test for KAP proxy approach.

Tests the three blocked call patterns against real kap.org.tr:
  1. _kap_api_via_js() — JS injection GET (financialTable → anti-bot/429 fix)
  2. _kap_api_via_js() — JS injection POST (memberDisclosureQuery → 404 fix)
  3. _post_kap_api_json() — full fallback chain (JS → cookie-warm → bare POST)
  4. _fetch_kap_api_json() — full fallback chain (JS → Firecrawl → aiohttp)
  5. scrape_and_save_disclosures() — end-to-end: disclosures land in result
  6. list_company_excel_members() — financialTable list via ASELS OID

Run from turkish_financial directory with:
  FIRECRAWL_BASE_URL=http://localhost:3002 python test_kap_live_proxy.py

Or (uses FIRECRAWL_API_KEY=fc-local + local base URL from env):
  python test_kap_live_proxy.py
"""

import asyncio
import os
import sys
import time
from datetime import datetime

# Ensure project root is on path
sys.path.insert(0, os.path.dirname(__file__))

# Point at local Firecrawl unless overridden
os.environ.setdefault("FIRECRAWL_BASE_URL", "http://localhost:3002")
os.environ.setdefault("FIRECRAWL_API_KEY", "fc-local")
os.environ.setdefault("FIRECRAWL_WAIT_FOR", "3000")
os.environ.setdefault("FIRECRAWL_TIMEOUT", "120000")

from config import config  # noqa: E402  must come after env setup
from scrapers.kap_scraper import KAPScraper  # noqa: E402

PASS = "\033[32m✓\033[0m"
FAIL = "\033[31m✗\033[0m"
WARN = "\033[33m⚠\033[0m"
INFO = "\033[36mℹ\033[0m"


def banner(title: str):
    print(f"\n{'─'*60}")
    print(f"  {title}")
    print(f"{'─'*60}")


def ok(msg: str):
    print(f"  {PASS} {msg}")


def fail(msg: str):
    print(f"  {FAIL} {msg}")


def warn(msg: str):
    print(f"  {WARN} {msg}")


def info(msg: str):
    print(f"  {INFO} {msg}")


def make_scraper() -> KAPScraper:
    return KAPScraper()


# ---------------------------------------------------------------------------
# Test 1: _kap_api_via_js  — GET (financialTable list for ASELS)
# ---------------------------------------------------------------------------

async def test_js_api_get(scraper: KAPScraper) -> bool:
    banner("Test 1 — _kap_api_via_js GET (financialTable/listCompanyExcelMembers)")

    asels_oid = "4028e4a1413b7ef401413bc2251e0047"
    year = datetime.now().year
    api_path = f"/tr/api/financialTable/listCompanyExcelMembers/{asels_oid}/{year}/T"
    info(f"Calling {api_path}")

    t0 = time.perf_counter()
    result = await scraper._kap_api_via_js(api_path=api_path, method="GET")
    elapsed = round(time.perf_counter() - t0, 1)

    if result is None:
        fail(f"Returned None after {elapsed}s")
        return False
    if not isinstance(result, list):
        fail(f"Expected list, got {type(result).__name__}: {str(result)[:200]}")
        return False

    ok(f"Got list with {len(result)} members in {elapsed}s")
    if result:
        sample = result[0]
        info(f"  First member keys: {list(sample.keys())[:8]}")
        di = sample.get("disclosureIndex")
        info(f"  disclosureIndex = {di}")
        ok("disclosureIndex present") if di else warn("disclosureIndex missing")
    return True


# ---------------------------------------------------------------------------
# Test 2: _kap_api_via_js  — POST (memberDisclosureQuery)
# ---------------------------------------------------------------------------

async def test_js_api_post(scraper: KAPScraper) -> bool:
    banner("Test 2 — _kap_api_via_js POST (memberDisclosureQuery)")

    api_path = "/tr/api/memberDisclosureQuery"
    today = datetime.now()
    from_date = today.strftime("%Y-%m-%d")
    # 3-day window to keep the result set small
    import datetime as _dt
    from_date = (_dt.date.today() - _dt.timedelta(days=3)).strftime("%Y-%m-%d")
    to_date = _dt.date.today().strftime("%Y-%m-%d")

    body = {
        "fromDate": from_date,
        "toDate": to_date,
        "year": "", "prd": "", "term": "", "ruleType": "", "bdkReview": "",
        "disclosureClass": "", "index": "", "market": "", "isLate": "",
        "subjectList": [], "mkkMemberOidList": [], "inactiveMkkMemberOidList": [],
        "bdkMemberOidList": [], "mainSector": "", "sector": "", "subSector": "",
        "memberType": "IGS", "fromSrc": "N", "srcCategory": "", "discIndex": [],
    }

    info(f"POST {api_path} | fromDate={from_date} toDate={to_date}")

    t0 = time.perf_counter()
    result = await scraper._kap_api_via_js(api_path=api_path, method="POST", body=body)
    elapsed = round(time.perf_counter() - t0, 1)

    if result is None:
        fail(f"Returned None after {elapsed}s")
        return False
    if not isinstance(result, list):
        fail(f"Expected list, got {type(result).__name__}: {str(result)[:200]}")
        return False

    ok(f"Got {len(result)} disclosures in {elapsed}s")
    if result:
        first = result[0]
        info(f"  Keys: {list(first.keys())[:8]}")
        codes = first.get("stockCodes", "?")
        title = first.get("kapTitle") or first.get("subject") or "?"
        ok(f"  First: {codes} — {title[:60]}")
    return True


# ---------------------------------------------------------------------------
# Test 3: _post_kap_api_json  — full fallback chain
# ---------------------------------------------------------------------------

async def test_post_fallback_chain(scraper: KAPScraper) -> bool:
    banner("Test 3 — _post_kap_api_json full fallback chain")

    url = f"{scraper.BASE_URL}/tr/api/memberDisclosureQuery"
    import datetime as _dt
    body = {
        "fromDate": (_dt.date.today() - _dt.timedelta(days=2)).strftime("%Y-%m-%d"),
        "toDate": _dt.date.today().strftime("%Y-%m-%d"),
        "year": "", "prd": "", "term": "", "ruleType": "", "bdkReview": "",
        "disclosureClass": "", "index": "", "market": "", "isLate": "",
        "subjectList": [], "mkkMemberOidList": [], "inactiveMkkMemberOidList": [],
        "bdkMemberOidList": [], "mainSector": "", "sector": "", "subSector": "",
        "memberType": "IGS", "fromSrc": "N", "srcCategory": "", "discIndex": [],
    }

    info(f"POST {url}")
    t0 = time.perf_counter()
    result = await scraper._post_kap_api_json(url, body)
    elapsed = round(time.perf_counter() - t0, 1)

    if result is None:
        fail(f"All fallbacks returned None after {elapsed}s")
        return False
    if isinstance(result, list):
        ok(f"Got {len(result)} disclosures in {elapsed}s")
        return True
    fail(f"Unexpected result type {type(result).__name__}: {str(result)[:200]}")
    return False


# ---------------------------------------------------------------------------
# Test 4: _fetch_kap_api_json  — GET financialTable list
# ---------------------------------------------------------------------------

async def test_fetch_fallback_chain(scraper: KAPScraper) -> bool:
    banner("Test 4 — _fetch_kap_api_json full fallback chain (financialTable GET)")

    asels_oid = "4028e4a1413b7ef401413bc2251e0047"
    year = datetime.now().year
    url = (
        f"{scraper.BASE_URL}/tr/api/financialTable/"
        f"listCompanyExcelMembers/{asels_oid}/{year}/T"
    )

    info(f"GET {url}")
    t0 = time.perf_counter()
    result = await scraper._fetch_kap_api_json(url)
    elapsed = round(time.perf_counter() - t0, 1)

    if result is None:
        fail(f"All fallbacks returned None after {elapsed}s")
        return False
    if isinstance(result, list):
        ok(f"Got {len(result)} members in {elapsed}s")
        return True
    fail(f"Unexpected type {type(result).__name__}: {str(result)[:200]}")
    return False


# ---------------------------------------------------------------------------
# Test 5: scrape_and_save_disclosures  — end-to-end (no DB)
# ---------------------------------------------------------------------------

async def test_scrape_and_save_disclosures(scraper: KAPScraper) -> bool:
    banner("Test 5 — scrape_and_save_disclosures (3 days, no DB)")

    t0 = time.perf_counter()
    result = await scraper.scrape_and_save_disclosures(days_back=3)
    elapsed = round(time.perf_counter() - t0, 1)

    if not result.get("success"):
        fail(f"Call failed after {elapsed}s: {result.get('error')}")
        return False

    total = result.get("total", 0)
    disclosures = result.get("disclosures", [])

    if total == 0:
        fail(f"Zero disclosures returned after {elapsed}s")
        return False

    ok(f"total={total}, returned={len(disclosures)} in {elapsed}s")
    if disclosures:
        d = disclosures[0]
        info(f"  First: [{d.get('stock_code')}] {str(d.get('content', ''))[:60]}")
        info(f"  date={d.get('disclosure_date')} id={d.get('disclosure_id')}")
    return True


# ---------------------------------------------------------------------------
# Test 6: list_company_excel_members  — ASELS financial tables
# ---------------------------------------------------------------------------

async def test_list_excel_members(scraper: KAPScraper) -> bool:
    banner("Test 6 — list_company_excel_members (ASELS)")

    asels_oid = "4028e4a1413b7ef401413bc2251e0047"
    year = datetime.now().year

    info(f"Listing ASELS financial table members for {year}")
    t0 = time.perf_counter()
    members = await scraper.list_company_excel_members(asels_oid, year)
    elapsed = round(time.perf_counter() - t0, 1)

    if not members:
        # Try prior year if current year has no data yet
        year -= 1
        info(f"No members for current year, trying {year}")
        members = await scraper.list_company_excel_members(asels_oid, year)
        elapsed = round(time.perf_counter() - t0, 1)

    if not members:
        fail(f"No members found after {elapsed}s")
        return False

    ok(f"Got {len(members)} members in {elapsed}s")
    annual = [m for m in members if m.get("period") == 4]
    info(f"  Annual (period=4): {len(annual)}, total: {len(members)}")
    if members:
        m = members[0]
        info(f"  disclosureIndex={m.get('disclosureIndex')} period={m.get('period')} year={m.get('year')}")
    return True


# ---------------------------------------------------------------------------
# Runner
# ---------------------------------------------------------------------------

async def main():
    print("\n" + "="*60)
    print("  KAP Live Proxy Integration Test")
    print(f"  Firecrawl: {os.environ.get('FIRECRAWL_BASE_URL', 'cloud')}")
    print(f"  KAP proxy tiers: {KAPScraper.KAP_FIRECRAWL_PROXIES}")
    print("="*60)

    scraper = make_scraper()

    tests = [
        ("JS-API GET  (financialTable)",         test_js_api_get),
        ("JS-API POST (memberDisclosureQuery)",   test_js_api_post),
        ("_post_kap_api_json fallback chain",     test_post_fallback_chain),
        ("_fetch_kap_api_json fallback chain",    test_fetch_fallback_chain),
        ("scrape_and_save_disclosures e2e",       test_scrape_and_save_disclosures),
        ("list_company_excel_members (ASELS)",    test_list_excel_members),
    ]

    results = {}
    for name, fn in tests:
        try:
            passed = await fn(scraper)
        except Exception as exc:
            print(f"\n  {FAIL} EXCEPTION in '{name}': {exc}")
            import traceback; traceback.print_exc()
            passed = False
        results[name] = passed

    print("\n" + "="*60)
    print("  Summary")
    print("="*60)
    total = len(results)
    passed_count = sum(results.values())
    for name, ok_flag in results.items():
        marker = PASS if ok_flag else FAIL
        print(f"  {marker} {name}")
    print(f"\n  {passed_count}/{total} tests passed")
    print("="*60 + "\n")

    sys.exit(0 if passed_count == total else 1)


if __name__ == "__main__":
    asyncio.run(main())
