"""
extract_statement_meta / scale_facts on excerpts of a live KAP financial-report
page (/tr/Bildirim/1598405, EREGL 2026-Q1, fetched 2026-10-15).
"""
from datetime import date, datetime, timezone

from scrapers.kap_financial_parser import extract_statement_meta, scale_facts

RAW = (r'{\"disclosureClass\":\"FR\",\"disclosureType\":\"FR\",'
       r'\"publishDate\":\"2026.04.28 20:12:13\",\"disclosureId\":\"4028328c9d\"}')
MD = (
    "Finansal Tablolara İlişkin Genel Açıklama\n\n"
    "|     |     |\n| --- | --- |\n| Sunum Para Birimi | 1.000 TL |\n"
    "| Finansal Tablo Niteliği | Konsolide |\n\n"
    "| Cari Dönem<br>31.03.2026<br>Current Period<br>31.03.2026 | Önceki Dönem |\n\n"
    "ULAŞ YİRMİBEŞ\n\nMali Kontrol ve Raporlama Direktörü\n\n28.04.2026 18:56:33\n"
)


def test_publish_date_is_istanbul_time_converted_to_utc():
    assert extract_statement_meta(MD, RAW)["published_at"] == datetime(2026, 4, 28, 17, 12, 13, tzinfo=timezone.utc)


def test_signature_timestamps_are_not_mistaken_for_publish_time():
    assert "published_at" not in extract_statement_meta(MD, "")


def test_presentation_unit_and_period_end():
    meta = extract_statement_meta(MD, RAW)
    assert meta["unit_multiplier"] == 1000
    assert meta["currency"] == "TRY"
    assert meta["period_end"] == date(2026, 3, 31)


def test_whole_tl_and_foreign_presentation_units():
    assert extract_statement_meta("| Sunum Para Birimi | TL |")["unit_multiplier"] == 1
    usd = extract_statement_meta("| Sunum Para Birimi | 1.000 USD |")
    assert (usd["unit_multiplier"], usd["currency"]) == (1000, "USD")


def test_missing_fields_are_absent_not_guessed():
    assert extract_statement_meta("nothing here", "") == {}


def test_scale_facts_converts_thousands_to_whole_units():
    facts = {"revenue": 59_684_848.0, "shares_outstanding": 7_000_000.0, "note": "x"}
    scaled = scale_facts(facts, 1000)
    assert scaled["revenue"] == 59_684_848_000.0
    assert scaled["shares_outstanding"] == 7_000_000_000.0  # paid-in capital at 1 TL nominal
    assert scaled["note"] == "x"
    assert scale_facts(facts, 1) == facts
