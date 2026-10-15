"""
The KAP disclosure scrape (production_kap_final, behind POST /api/v1/scrapers/kap)
read only FIRECRAWL_API_URL, while compose/k8s set FIRECRAWL_BASE_URL — so in every
deployment it called localhost:3002 and no disclosure was ever collected.
"""
import pytest

from production_kap_final import ProductionKAPScraper


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch):
    monkeypatch.delenv("FIRECRAWL_API_URL", raising=False)
    monkeypatch.delenv("FIRECRAWL_BASE_URL", raising=False)


def test_uses_the_deployment_variable(monkeypatch):
    monkeypatch.setenv("FIRECRAWL_BASE_URL", "http://firecrawl-api:3002")
    assert ProductionKAPScraper(use_test_data=True).firecrawl_api_url == "http://firecrawl-api:3002"


def test_explicit_api_url_still_wins(monkeypatch):
    monkeypatch.setenv("FIRECRAWL_BASE_URL", "http://firecrawl-api:3002")
    monkeypatch.setenv("FIRECRAWL_API_URL", "http://other:3002")
    assert ProductionKAPScraper(use_test_data=True).firecrawl_api_url == "http://other:3002"


def test_localhost_only_when_nothing_is_configured():
    assert ProductionKAPScraper(use_test_data=True).firecrawl_api_url == "http://localhost:3002"
