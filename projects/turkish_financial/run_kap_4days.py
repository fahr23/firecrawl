#!/usr/bin/env python3
"""
Fetch last 4 days of KAP disclosures and print a structured report.

Usage:
  python run_kap_4days.py
  python run_kap_4days.py --days 4 --output kap_data.json
"""

import asyncio
import json
import os
import sys
import argparse
from datetime import datetime
from typing import Optional

sys.path.insert(0, os.path.dirname(__file__))
os.environ.setdefault("FIRECRAWL_BASE_URL", "http://localhost:3002")
os.environ.setdefault("FIRECRAWL_API_KEY", "fc-local")

from dotenv import load_dotenv
load_dotenv()

from scrapers.kap_scraper import KAPScraper

PASS = "\033[32m✓\033[0m"
FAIL = "\033[31m✗\033[0m"
INFO = "\033[36mℹ\033[0m"


def fmt(d: dict, key: str, width: int = 0) -> str:
    v = str(d.get(key) or "")
    return v[:width].ljust(width) if width else v


async def run(days: int, output_path: Optional[str]):
    print(f"\n{'='*65}")
    print(f"  KAP Disclosure Fetch — last {days} days")
    print(f"  Date: {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    proxy_url = os.getenv("APP_PROXY_URL", "")
    use_proxy = os.getenv("USE_PROXY", "false").lower() == "true"
    print(f"  Proxy: {'ON → ' + proxy_url if use_proxy else 'OFF'}")
    print(f"{'='*65}\n")

    scraper = KAPScraper()

    print(f"  {INFO} Querying KAP API for last {days} days …")
    t0 = datetime.now()
    result = await scraper.scrape_and_save_disclosures(days_back=days)
    elapsed = round((datetime.now() - t0).total_seconds(), 1)

    if not result.get("success"):
        print(f"  {FAIL} scrape_and_save_disclosures failed: {result.get('error')}")
        sys.exit(1)

    total = result.get("total", 0)
    disclosures = result.get("disclosures", [])
    saved = result.get("saved", 0)

    print(f"  {PASS} Fetched {total} disclosures in {elapsed}s  (saved to DB: {saved})\n")

    if not disclosures:
        print("  No disclosures returned.")
        return

    # ── Summary table ────────────────────────────────────────────────────────
    print(f"  {'#':<4} {'Stock':<8} {'Date':<12} {'Subject':<30} {'Late':<5} {'PDF':<4}")
    print(f"  {'─'*4} {'─'*8} {'─'*12} {'─'*30} {'─'*5} {'─'*4}")

    for i, d in enumerate(disclosures[:100], 1):
        stock   = fmt(d, "stock_code", 7)
        date    = fmt(d, "disclosure_date", 11)
        subj    = fmt(d, "subject", 29)
        is_late = "Y" if d.get("is_late") else "-"
        has_pdf = "Y" if d.get("has_attachment") else "-"
        print(f"  {i:<4} {stock} {date} {subj} {is_late:<5} {has_pdf}")

    if total > 100:
        print(f"\n  … and {total - 100} more (showing first 100)")

    # ── By-stock breakdown ───────────────────────────────────────────────────
    by_stock: dict[str, int] = {}
    for d in disclosures:
        k = d.get("stock_code") or "?"
        by_stock[k] = by_stock.get(k, 0) + 1

    top = sorted(by_stock.items(), key=lambda x: -x[1])[:15]
    print(f"\n  Top companies by disclosure count (last {days} days):")
    for ticker, cnt in top:
        bar = "█" * min(cnt, 30)
        print(f"    {ticker:<8} {cnt:>4}  {bar}")

    # ── JSON export ──────────────────────────────────────────────────────────
    if output_path:
        export = {
            "fetched_at": datetime.now().isoformat(),
            "days_back": days,
            "total": total,
            "disclosures": disclosures,
        }
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(export, f, ensure_ascii=False, indent=2, default=str)
        print(f"\n  {PASS} Saved {total} disclosures → {output_path}")

    print(f"\n{'='*65}\n")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--days", type=int, default=4, help="Days to look back (default 4)")
    ap.add_argument("--output", "-o", default="kap_4days.json", help="JSON output file")
    args = ap.parse_args()
    asyncio.run(run(args.days, args.output))


if __name__ == "__main__":
    main()
