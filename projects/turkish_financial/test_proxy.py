#!/usr/bin/env python3
"""
Proxy connectivity test using ScraperAPI.

Tests:
  1. Direct request (no proxy) to httpbin.org/ip  — shows your real IP
  2. Proxied request through ScraperAPI            — shows proxy exit IP
  3. ProxyConfig helper from config.py             — verifies env wiring
  4. KAP homepage through proxy                    — verifies anti-bot bypass

Run from the turkish_financial directory:
  python test_proxy.py
"""

import os
import sys
import requests

sys.path.insert(0, os.path.dirname(__file__))

from dotenv import load_dotenv
load_dotenv()

PASS = "\033[32m✓\033[0m"
FAIL = "\033[31m✗\033[0m"
INFO = "\033[36mℹ\033[0m"

SCRAPERAPI_KEY = os.getenv("APP_PROXY_PASSWORD", "")
PROXY_URL = os.getenv("APP_PROXY_URL", "http://proxy-server.scraperapi.com:8001")
PROXY_USER = os.getenv("APP_PROXY_USERNAME", "scraperapi")
USE_PROXY = os.getenv("USE_PROXY", "false").lower() == "true"


def proxies_dict() -> dict:
    auth_url = f"http://{PROXY_USER}:{SCRAPERAPI_KEY}@proxy-server.scraperapi.com:8001"
    return {"http": auth_url, "https": auth_url}


# ScraperAPI re-signs SSL certs; macOS Python doesn't trust the intermediate CA
# so we disable verification for proxy requests (the tunnel itself is authenticated
# by the API key, so this is an acceptable tradeoff for scraping use).
PROXY_VERIFY = False


def section(title: str):
    print(f"\n{'─'*55}")
    print(f"  {title}")
    print(f"{'─'*55}")


def ok(msg):  print(f"  {PASS} {msg}")
def fail(msg): print(f"  {FAIL} {msg}")
def info(msg): print(f"  {INFO} {msg}")


# ── Test 1: direct (no proxy) ───────────────────────────────────────────────
def test_direct_ip():
    section("Test 1 — Direct request (real IP)")
    # ifconfig.me is more reliable than httpbin.org for a simple IP echo
    for url in ["https://ifconfig.me/ip", "https://api.ipify.org", "https://checkip.amazonaws.com"]:
        try:
            r = requests.get(url, timeout=10)
            r.raise_for_status()
            ip = r.text.strip()
            ok(f"Real IP: {ip}  (via {url})")
            return True
        except Exception as e:
            info(f"  {url} → {e}")
    fail("All direct IP endpoints failed")
    return False


# ── Test 2: proxied IP echo ──────────────────────────────────────────────────
def test_proxy_httpbin():
    section("Test 2 — ScraperAPI proxy → IP echo (shows exit IP)")
    if not SCRAPERAPI_KEY:
        fail("APP_PROXY_PASSWORD not set in .env")
        return False

    import warnings, urllib3
    warnings.filterwarnings("ignore", category=urllib3.exceptions.InsecureRequestWarning)

    for url in ["https://api.ipify.org", "https://checkip.amazonaws.com", "https://ifconfig.me/ip"]:
        try:
            r = requests.get(
                url,
                proxies=proxies_dict(),
                verify=PROXY_VERIFY,
                timeout=30,
            )
            r.raise_for_status()
            ip = r.text.strip()
            ok(f"Proxy exit IP: {ip}  (via {url})")
            return True
        except Exception as e:
            info(f"  {url} → {e}")

    fail("All proxy IP-echo endpoints failed")
    return False


# ── Test 3: ScraperAPI native endpoint ──────────────────────────────────────
def test_scraperapi_native():
    section("Test 3 — ScraperAPI native API endpoint")
    if not SCRAPERAPI_KEY:
        fail("APP_PROXY_PASSWORD not set in .env")
        return False

    try:
        payload = {"api_key": SCRAPERAPI_KEY, "url": "https://httpbin.org/ip"}
        r = requests.get("https://api.scraperapi.com/", params=payload, timeout=30)
        r.raise_for_status()
        data = r.json()
        ip = data.get("origin", "?")
        ok(f"ScraperAPI native response — origin: {ip}")
        return True
    except Exception as e:
        fail(f"ScraperAPI native endpoint failed: {e}")
        return False


# ── Test 4: ProxyConfig from config.py ──────────────────────────────────────
def test_proxy_config():
    section("Test 4 — ProxyConfig wiring (config.py)")
    try:
        from config import config
        pc = config.proxy
        info(f"use_proxy       = {pc.use_proxy}")
        info(f"proxy_url       = {pc.proxy_url}")
        info(f"proxy_username  = {pc.proxy_username}")
        key_preview = (pc.proxy_password or "")[:8] + "..."
        info(f"proxy_password  = {key_preview}")
        proxy_str = pc.get_proxy_string()
        if proxy_str:
            safe = proxy_str.replace(pc.proxy_password or "", "***")
            info(f"get_proxy_string() = {safe}")
            ok("ProxyConfig built correctly")
            return True
        else:
            fail("get_proxy_string() returned None — check USE_PROXY / APP_PROXY_URL in .env")
            return False
    except Exception as e:
        fail(f"ProxyConfig test error: {e}")
        return False


# ── Test 5: KAP homepage through proxy ──────────────────────────────────────
def test_kap_through_proxy():
    section("Test 5 — KAP homepage via ScraperAPI proxy")
    if not SCRAPERAPI_KEY:
        fail("APP_PROXY_PASSWORD not set in .env")
        return False

    import warnings, urllib3
    warnings.filterwarnings("ignore", category=urllib3.exceptions.InsecureRequestWarning)
    try:
        r = requests.get(
            "https://www.kap.org.tr/tr/",
            proxies=proxies_dict(),
            verify=PROXY_VERIFY,
            timeout=30,
            headers={"User-Agent": "Mozilla/5.0"},
        )
        status = r.status_code
        if status == 200:
            ok(f"KAP returned 200 — {len(r.text)} chars")
            return True
        else:
            fail(f"KAP returned HTTP {status}")
            return False
    except Exception as e:
        fail(f"KAP proxy request failed: {e}")
        return False


# ── Main ─────────────────────────────────────────────────────────────────────
def main():
    print("\n" + "="*55)
    print("  ScraperAPI Proxy Test")
    print(f"  USE_PROXY = {USE_PROXY}")
    key_preview = SCRAPERAPI_KEY[:8] + "..." if SCRAPERAPI_KEY else "(not set)"
    print(f"  API key   = {key_preview}")
    print(f"  Proxy URL = {PROXY_URL}")
    print("="*55)

    tests = [
        ("Direct IP check",           test_direct_ip),
        ("Proxy → httpbin.org/ip",    test_proxy_httpbin),
        ("ScraperAPI native endpoint", test_scraperapi_native),
        ("ProxyConfig (config.py)",   test_proxy_config),
        ("KAP homepage via proxy",    test_kap_through_proxy),
    ]

    results = {}
    for name, fn in tests:
        try:
            results[name] = fn()
        except Exception as exc:
            fail(f"Uncaught exception: {exc}")
            results[name] = False

    print("\n" + "="*55)
    print("  Summary")
    print("="*55)
    passed = sum(results.values())
    for name, flag in results.items():
        marker = PASS if flag else FAIL
        print(f"  {marker} {name}")
    print(f"\n  {passed}/{len(results)} tests passed")
    print("="*55 + "\n")
    sys.exit(0 if passed == len(results) else 1)


if __name__ == "__main__":
    main()
