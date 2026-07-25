#!/usr/bin/env python3
"""
Slow, non-blocking, GET-only fetcher for KAP financial / fundamental data.

KAP's disclosure POST API is anti-bot blocked, but its financial-statement data is
reachable over GET (financialTable list + the /tr/Bildirim/{index} report page). This
runner sweeps a set of BIST tickers gently — pacing between companies so KAP's
rate-based anti-bot is never tripped — and optionally repeats on an interval for
continuous collection.

Egress goes through the configured ProxyProvider (infrastructure/proxy); switch backends
via PROXY_PROVIDER / USE_PROXY in .env without touching this script.

Usage:
  # one pass over all known tickers, 6s between each
  python run_financials.py --year 2024 --delay 6

  # specific tickers, resolve missing member OIDs over GET first
  python run_financials.py -i ASELS,THYAO,GARAN --resolve-oids

  # continuous: repeat the full sweep every 6 hours
  python run_financials.py --interval 21600 --delay 8 -o financials.json
"""
import argparse
import asyncio
import json
import os
import sys
from datetime import datetime
from typing import List, Optional

sys.path.insert(0, os.path.dirname(__file__))
os.environ.setdefault("FIRECRAWL_BASE_URL", "http://localhost:3002")
os.environ.setdefault("FIRECRAWL_API_KEY", "fc-local")

from dotenv import load_dotenv
load_dotenv()

from scrapers.kap_scraper import KAPScraper, _PROXY_PROVIDER

PASS = "\033[32m✓\033[0m"
FAIL = "\033[31m✗\033[0m"
INFO = "\033[36mℹ\033[0m"


def _default_instruments() -> List[str]:
    from infrastructure.contracts.instrument_identity_map import STATIC_BIST_MAP
    return sorted(STATIC_BIST_MAP.keys())


async def _one_pass(
    scraper: KAPScraper,
    instruments: List[str],
    year: int,
    delay: float,
    resolve_oids: bool,
    output_path: Optional[str],
) -> dict:
    # Resolve any missing member OIDs over GET (paced internally by KAP_PAGE_DELAY_S).
    if resolve_oids:
        print(f"  {INFO} Resolving member OIDs over GET for {len(instruments)} tickers …")
        res = await scraper.refresh_member_oids_via_get(instruments=instruments)
        if res.get("success"):
            print(f"  {PASS} Resolved {res.get('resolved', 0)} OIDs "
                  f"(missing: {len(res.get('missing', []))})")
        else:
            print(f"  {FAIL} OID resolution failed: {res.get('error')}")

    print(f"  {INFO} Fetching {year} financial statements "
          f"for {len(instruments)} tickers ({delay}s between each) …")
    t0 = datetime.now()
    result = await scraper.scrape_financial_statements(
        instruments=instruments, year=year, delay_s=delay,
    )
    elapsed = round((datetime.now() - t0).total_seconds(), 1)

    processed = result.get("processed", 0)
    failed = result.get("failed", [])
    print(f"  {PASS} Processed {processed}/{result.get('requested', 0)} "
          f"in {elapsed}s  (failed: {len(failed)})")

    # ── Per-company summary ────────────────────────────────────────────────────
    for r in result.get("results", []):
        facts = r.get("facts") or {}
        payload = r.get("payload") or {}
        ratios = payload.get("ratios") if isinstance(payload, dict) else None
        ratio_str = ""
        if isinstance(ratios, dict) and ratios:
            head = list(ratios.items())[:3]
            ratio_str = "  " + " ".join(f"{k}={v}" for k, v in head)
        print(f"    {r.get('stock_code'):<8} {r.get('period'):<10} "
              f"facts={len(facts)} saved={r.get('saved')}{ratio_str}")

    if failed:
        reasons: dict[str, int] = {}
        for f in failed:
            reasons[f.get("reason", "?")] = reasons.get(f.get("reason", "?"), 0) + 1
        print(f"    failures by reason: {reasons}")

    if output_path:
        export = {
            "fetched_at": datetime.now().isoformat(),
            "year": year,
            "requested": result.get("requested"),
            "processed": processed,
            "failed": failed,
            "results": result.get("results", []),
        }
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(export, f, ensure_ascii=False, indent=2, default=str)
        print(f"  {PASS} Wrote results → {output_path}")

    return result


async def run(args) -> None:
    instruments = (
        [t.strip().upper() for t in args.instruments.split(",") if t.strip()]
        if args.instruments else _default_instruments()
    )
    year = args.year or datetime.now().year

    print(f"\n{'='*65}")
    print(f"  KAP Financial / Fundamental Fetch (GET-only, slow)")
    print(f"  Date: {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    print(f"  Proxy provider: {_PROXY_PROVIDER.name} (enabled={_PROXY_PROVIDER.enabled})")
    print(f"  Tickers: {len(instruments)} | year: {year} | "
          f"delay: {args.delay}s | interval: {args.interval}s")
    print(f"{'='*65}\n")

    scraper = KAPScraper()
    cycle = 0
    while True:
        cycle += 1
        if args.interval:
            print(f"\n── Cycle {cycle} @ {datetime.now().strftime('%H:%M:%S')} ──")
        await _one_pass(
            scraper, instruments, year, args.delay, args.resolve_oids, args.output,
        )
        if not args.interval:
            break
        print(f"  {INFO} Sleeping {args.interval}s until next cycle …")
        await asyncio.sleep(args.interval)

    print(f"\n{'='*65}\n")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("-i", "--instruments", default="",
                    help="Comma-separated BIST tickers (default: all known)")
    ap.add_argument("--year", type=int, default=None,
                    help="Reporting year (default: current calendar year)")
    ap.add_argument("--delay", type=float, default=5.0,
                    help="Seconds to pause between companies (default 5)")
    ap.add_argument("--interval", type=int, default=0,
                    help="Seconds between full sweeps; 0 = run once (default 0)")
    ap.add_argument("--resolve-oids", action="store_true",
                    help="Resolve missing member OIDs over GET before fetching")
    ap.add_argument("-o", "--output", default=None, help="JSON output file")
    args = ap.parse_args()
    try:
        asyncio.run(run(args))
    except KeyboardInterrupt:
        print("\n  Interrupted — exiting cleanly.")


if __name__ == "__main__":
    main()
