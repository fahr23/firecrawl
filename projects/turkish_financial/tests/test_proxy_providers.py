"""Unit tests for the pluggable proxy providers (infrastructure/proxy)."""
import sys
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).parent.parent))

from infrastructure.proxy import (  # noqa: E402
    DirectProvider,
    ScraperAPIProvider,
    FirecrawlProxyProvider,
    get_proxy_provider,
)
from infrastructure.proxy.providers import _split_host_port  # noqa: E402


def _cfg(**proxy):
    """Build an app-config-like object with a .proxy namespace."""
    defaults = dict(
        use_proxy=True, provider=None,
        proxy_url="http://proxy-server.scraperapi.com:8001",
        proxy_username="scraperapi", proxy_password="KEY123",
        scraperapi_country_code=None, scraperapi_premium=False,
        scraperapi_ultra_premium=False,
    )
    defaults.update(proxy)
    return SimpleNamespace(proxy=SimpleNamespace(**defaults))


# ── DirectProvider ────────────────────────────────────────────────────────────
def test_direct_provider_is_noop():
    p = DirectProvider()
    assert p.name == "direct"
    assert p.enabled is False
    assert p.requests_proxies() is None
    assert p.aiohttp_proxy() is None
    assert p.verify_tls() is True


# ── ScraperAPIProvider ────────────────────────────────────────────────────────
def test_scraperapi_basic_url():
    p = ScraperAPIProvider(host="proxy-server.scraperapi.com", port=8001, api_key="KEY123")
    assert p.enabled is True
    assert p.verify_tls() is False  # ScraperAPI re-signs TLS
    url = "http://scraperapi:KEY123@proxy-server.scraperapi.com:8001"
    assert p.aiohttp_proxy() == url
    assert p.requests_proxies() == {"http": url, "https": url}


def test_scraperapi_encodes_geo_and_premium_in_username():
    p = ScraperAPIProvider(
        host="proxy-server.scraperapi.com", port=8001, api_key="KEY123",
        country_code="TR", premium=True,
    )
    # country_code is lowercased; options are dot-joined onto the username
    assert "scraperapi.country_code=tr.premium=true:KEY123@" in p.aiohttp_proxy()


def test_scraperapi_disabled_without_key():
    p = ScraperAPIProvider(host="proxy-server.scraperapi.com", port=8001, api_key="")
    assert p.enabled is False
    assert p.requests_proxies() is None
    assert p.aiohttp_proxy() is None


# ── FirecrawlProxyProvider (future stub) ──────────────────────────────────────
def test_firecrawl_provider_is_direct_stub():
    p = FirecrawlProxyProvider()
    assert p.name == "firecrawl"
    assert p.enabled is False
    assert p.requests_proxies() is None
    assert p.aiohttp_proxy() is None


# ── _split_host_port ──────────────────────────────────────────────────────────
def test_split_host_port_variants():
    assert _split_host_port("http://proxy-server.scraperapi.com:8001") == (
        "proxy-server.scraperapi.com", 8001)
    assert _split_host_port("http://user:pass@host.example:7000") == ("host.example", 7000)
    assert _split_host_port("http://host.example") == ("host.example", 8001)  # default port
    assert _split_host_port(None) == ("", 8001)


# ── get_proxy_provider selection ──────────────────────────────────────────────
def test_get_provider_defaults_to_scraperapi_when_use_proxy():
    p = get_proxy_provider(_cfg())
    assert isinstance(p, ScraperAPIProvider)
    assert p.enabled is True


def test_get_provider_direct_when_use_proxy_false():
    p = get_proxy_provider(_cfg(use_proxy=False))
    assert isinstance(p, DirectProvider)


def test_get_provider_explicit_direct():
    p = get_proxy_provider(_cfg(provider="direct"))
    assert isinstance(p, DirectProvider)


def test_get_provider_explicit_firecrawl():
    p = get_proxy_provider(_cfg(provider="firecrawl"))
    assert isinstance(p, FirecrawlProxyProvider)


def test_get_provider_unknown_falls_back_to_direct():
    p = get_proxy_provider(_cfg(provider="bananas"))
    assert isinstance(p, DirectProvider)


def test_get_provider_threads_scraperapi_options():
    p = get_proxy_provider(_cfg(scraperapi_country_code="tr", scraperapi_premium=True))
    assert isinstance(p, ScraperAPIProvider)
    assert "country_code=tr.premium=true" in p.aiohttp_proxy()
