"""
Pluggable proxy providers.

Scrapers talk to a ``ProxyProvider`` instead of hard-coding ScraperAPI, so a new
egress backend can be added later (e.g. routing through Firecrawl, or a residential
provider) without touching call sites. The provider yields the two shapes the codebase
needs — a ``requests``-style proxies dict and an ``aiohttp`` proxy URL — plus a TLS
verification hint.

Selection order (first hit wins):
  1. ``ProxyConfig.provider`` / ``PROXY_PROVIDER`` env, one of:
       - ``"direct"``     → no proxy (direct connection)
       - ``"scraperapi"`` → ScraperAPI proxy port
       - ``"firecrawl"``  → placeholder for future Firecrawl-routed egress
  2. ``"scraperapi"`` when ``USE_PROXY=true`` (back-compat default), else ``"direct"``.

To add a backend: subclass ``ProxyProvider``, implement the three methods, and register
it in ``get_proxy_provider``.
"""
from __future__ import annotations

import logging
import os
from abc import ABC, abstractmethod
from typing import Dict, Optional, Tuple

logger = logging.getLogger(__name__)


class ProxyProvider(ABC):
    """Abstract egress backend. Implementations must be cheap to construct."""

    name: str = "base"

    @property
    @abstractmethod
    def enabled(self) -> bool:
        """True when this provider actually routes traffic (vs. a direct connection)."""

    @abstractmethod
    def requests_proxies(self) -> Optional[Dict[str, str]]:
        """``proxies=`` dict for the ``requests`` library, or None for direct."""

    @abstractmethod
    def aiohttp_proxy(self) -> Optional[str]:
        """``proxy=`` URL (auth embedded) for ``aiohttp``, or None for direct."""

    def verify_tls(self) -> bool:
        """Whether TLS certificates should be verified through this provider."""
        return True

    def __repr__(self) -> str:  # pragma: no cover - cosmetic
        return f"<{type(self).__name__} name={self.name!r} enabled={self.enabled}>"


class DirectProvider(ProxyProvider):
    """No proxy — connect directly. Safe default when proxying is off."""

    name = "direct"

    @property
    def enabled(self) -> bool:
        return False

    def requests_proxies(self) -> Optional[Dict[str, str]]:
        return None

    def aiohttp_proxy(self) -> Optional[str]:
        return None


class ScraperAPIProvider(ProxyProvider):
    """
    ScraperAPI proxy-port backend.

    The username encodes per-request options ScraperAPI-style
    (``scraperapi.<k>=<v>.<k>=<v>``). Geo / premium options are passed in from config
    so that, e.g., upgrading to a premium plan only needs an env change
    (``SCRAPERAPI_PREMIUM=true``, ``SCRAPERAPI_COUNTRY_CODE=tr``) — no code edit.
    """

    name = "scraperapi"

    def __init__(
        self,
        *,
        host: str,
        port: int,
        api_key: str,
        username: str = "scraperapi",
        country_code: Optional[str] = None,
        premium: bool = False,
        ultra_premium: bool = False,
        render: bool = False,
    ) -> None:
        self._host = host
        self._port = port
        self._key = api_key
        self._username = username or "scraperapi"
        # Ordered so the resulting username is deterministic (stable for tests/caching).
        self._opts: Dict[str, str] = {}
        if country_code:
            self._opts["country_code"] = str(country_code).strip().lower()
        if premium:
            self._opts["premium"] = "true"
        if ultra_premium:
            self._opts["ultra_premium"] = "true"
        if render:
            self._opts["render"] = "true"

    @property
    def enabled(self) -> bool:
        return bool(self._key and self._host)

    def _user(self) -> str:
        parts = [self._username] + [f"{k}={v}" for k, v in self._opts.items()]
        return ".".join(parts)

    def _url(self) -> Optional[str]:
        if not self.enabled:
            return None
        return f"http://{self._user()}:{self._key}@{self._host}:{self._port}"

    def requests_proxies(self) -> Optional[Dict[str, str]]:
        url = self._url()
        return {"http": url, "https": url} if url else None

    def aiohttp_proxy(self) -> Optional[str]:
        return self._url()

    def verify_tls(self) -> bool:
        # ScraperAPI re-signs TLS, so cert verification must be off for the tunnel.
        return False


class FirecrawlProxyProvider(ProxyProvider):
    """
    Placeholder for routing scraper egress through Firecrawl in the future.

    Firecrawl proxies at the browser/engine layer (proxy=basic/stealth on a scrape job)
    rather than exposing a forward HTTP proxy, so plain ``requests``/``aiohttp`` calls
    cannot point at it via a proxy URL. This stub keeps the extension point explicit:
    when implemented, direct-HTTP call sites should instead be funnelled through the
    Firecrawl scrape API. Until then it behaves as a direct connection so nothing breaks.
    """

    name = "firecrawl"

    @property
    def enabled(self) -> bool:
        return False

    def requests_proxies(self) -> Optional[Dict[str, str]]:
        return None

    def aiohttp_proxy(self) -> Optional[str]:
        return None


def _split_host_port(proxy_url: Optional[str], default_port: int = 8001) -> Tuple[str, int]:
    """Pull ``host, port`` out of a ``scheme://host:port`` proxy URL."""
    if not proxy_url:
        return "", default_port
    rest = proxy_url.split("://", 1)[-1]
    rest = rest.split("/", 1)[0]  # drop any path
    if "@" in rest:  # strip userinfo if present
        rest = rest.rsplit("@", 1)[-1]
    if ":" in rest:
        host, _, port_s = rest.rpartition(":")
        try:
            return host, int(port_s)
        except ValueError:
            return host, default_port
    return rest, default_port


def get_proxy_provider(app_config=None) -> ProxyProvider:
    """
    Build the configured ``ProxyProvider`` from app config / environment.

    Falls back to ``config.config`` when ``app_config`` is omitted. Always returns a
    provider (never None); ``DirectProvider`` is the no-op fallback.
    """
    if app_config is None:
        from config import config as app_config  # local import avoids a cycle

    pcfg = app_config.proxy
    name = (
        getattr(pcfg, "provider", None)
        or os.getenv("PROXY_PROVIDER")
        or ("scraperapi" if pcfg.use_proxy else "direct")
    ).strip().lower()

    if not pcfg.use_proxy or name == "direct":
        return DirectProvider()

    if name == "firecrawl":
        return FirecrawlProxyProvider()

    if name == "scraperapi":
        host, port = _split_host_port(pcfg.proxy_url)
        return ScraperAPIProvider(
            host=host,
            port=port,
            api_key=pcfg.proxy_password or "",
            username=pcfg.proxy_username or "scraperapi",
            country_code=getattr(pcfg, "scraperapi_country_code", None),
            premium=getattr(pcfg, "scraperapi_premium", False),
            ultra_premium=getattr(pcfg, "scraperapi_ultra_premium", False),
        )

    logger.warning("Unknown PROXY_PROVIDER %r — falling back to direct", name)
    return DirectProvider()
