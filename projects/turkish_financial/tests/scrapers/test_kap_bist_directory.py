"""KAP's BIST directory page embeds each company's mkkMemberOid and stock code(s);
one plain GET resolves every OID, including multi-code companies."""
import asyncio
from unittest.mock import AsyncMock, patch

from scrapers.kap_scraper import KAPScraper

# As served: JSON inside a JS string, so quotes arrive escaped.
RAW = (
    '<script>self.__next_f.push([1,"[{\\"mkkMemberOid\\":\\"1DE05DAA81E9073AE0530A4A622A2EBD\\",'
    '\\"kapMemberTitle\\":\\"AVRUPA YATIRIM HOLDİNG A.Ş.\\",\\"stockCode\\":\\"AVHOL\\",\\"kapMemberType\\":\\"IGS\\"},'
    '{\\"mkkMemberOid\\":\\"4028e4a2420327a4014209c55161144d\\",\\"kapMemberTitle\\":\\"A1 CAPİTAL\\",'
    '\\"stockCode\\":\\"A1CAP, ACP\\",\\"kapMemberType\\":\\"IGS\\"},'
    '{\\"mkkMemberOid\\":\\"not-an-oid\\",\\"stockCode\\":\\"BAD\\"}]"])</script>'
)


def _run(coro):
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


def setup_function():
    KAPScraper._BIST_DIRECTORY_CACHE.update({"at": 0.0, "data": {}})


def test_parses_oids_and_splits_multi_code_companies():
    parsed = KAPScraper.parse_bist_directory_json(RAW)
    assert parsed["AVHOL"]["oid"] == "1DE05DAA81E9073AE0530A4A622A2EBD"  # case kept
    assert parsed["A1CAP"]["oid"] == parsed["ACP"]["oid"] == "4028e4a2420327a4014209c55161144d"
    assert "BAD" not in parsed  # no valid OID, never guessed


def test_refresh_uses_directory_oids_without_rendering_pages():
    db = type("DB", (), {"upserts": [], "upsert_bist_company": lambda self, code, mkk_member_oid=None: self.upserts.append((code, mkk_member_oid))})()
    scraper = KAPScraper(db_manager=db)
    render = AsyncMock(return_value=None)
    with patch.object(KAPScraper, "_get_kap_html_direct", return_value=RAW), \
            patch.object(KAPScraper, "_scrape_kap_page", render):
        result = _run(scraper.refresh_member_oids_via_get(instruments=["A1CAP", "AVHOL", "ALMAD"]))
    assert result["oids"] == {"A1CAP": "4028e4a2420327a4014209c55161144d", "AVHOL": "1DE05DAA81E9073AE0530A4A622A2EBD"}
    assert result["missing"] == ["ALMAD"]  # not listed on KAP: honest miss
    assert render.await_count == 0  # no Firecrawl needed
    assert db.upserts == [("A1CAP", "4028e4a2420327a4014209c55161144d"), ("AVHOL", "1DE05DAA81E9073AE0530A4A622A2EBD")]


def test_falls_back_to_rendered_page_and_splits_codes_there_too():
    page = "[A1CAP, ACP](https://www.kap.org.tr/tr/sirket-bilgileri/ozet/1-a1)"
    with patch.object(KAPScraper, "_get_kap_html_direct", return_value=None), \
            patch.object(KAPScraper, "_scrape_kap_page", AsyncMock(return_value=page)):
        listing = _run(KAPScraper(db_manager=None).list_bist_companies_via_get())
    assert set(listing) == {"A1CAP", "ACP"}


def test_live_page_shape():
    """The real page parses (if reachable): hundreds of companies, all with OIDs."""
    import pytest
    raw = KAPScraper(db_manager=None)._get_kap_html_direct("https://www.kap.org.tr/tr/bist-sirketler")
    if not raw:
        pytest.skip("KAP unreachable")
    parsed = KAPScraper.parse_bist_directory_json(raw)
    assert len(parsed) > 500 and {"THYAO", "A1CAP", "ALBRK"} <= set(parsed)
