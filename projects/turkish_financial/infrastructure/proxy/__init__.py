"""Pluggable proxy backends for the Turkish-financial scrapers."""
from .providers import (
    ProxyProvider,
    DirectProvider,
    ScraperAPIProvider,
    FirecrawlProxyProvider,
    get_proxy_provider,
)

__all__ = [
    "ProxyProvider",
    "DirectProvider",
    "ScraperAPIProvider",
    "FirecrawlProxyProvider",
    "get_proxy_provider",
]
