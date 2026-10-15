"""extract_disclosure_basic on an excerpt of a live KAP detail page (/tr/Bildirim/1680281)."""
from datetime import datetime, timezone

from scrapers.kap_disclosure_page import extract_disclosure_basic

# As served: JSON inside an escaped server-rendered payload.
RAW = (
    r'27:[\"$\",\"$L31\",null,{\"CLIENT_BASE_URL\":\"https://www.kap.org.tr\",\"lang\":\"tr\",'
    r'\"index\":\"1680281\",\"sendData\":{\"disclosure\":{\"disclosureBasic\":{\"title\":'
    r'\"Genel Kurul İşlemlerine İlişkin Bildirim\",\"mkkMemberOid\":\"4028e4a240e95dc90140ee21c40601aa\",'
    r'\"companyTitle\":\"BİRKO BİRLEŞİK KOYUNLULULAR MENSUCAT TİCARET VE SANAYİ A.Ş.\",\"stockCode\":\"BRKO\",'
    r'\"relatedStocks\":null,\"disclosureClass\":\"ODA\",\"disclosureType\":\"CA\",\"disclosureCategory\":\"STT\",'
    r'\"publishDate\":\"2026.10.13 14:48:14\",\"disclosureId\":\"4028328ca0b8418501a13512b2e907d2\",'
    r'\"disclosureIndex\":1680281,\"summary\":null,\"attachmentCount\":6,\"isLate\":false},'
    r'\"disclosureDetail\":{\"memberType\":\"IGS\"}}}}]'
)


def test_reads_identity_from_the_embedded_payload():
    basic = extract_disclosure_basic(RAW)
    assert basic["disclosure_index"] == "1680281"
    assert basic["stock_code"] == "BRKO"
    assert basic["company_name"].startswith("BİRKO")
    assert basic["title"] == "Genel Kurul İşlemlerine İlişkin Bildirim"
    assert basic["disclosure_class"] == "ODA"
    assert basic["is_late"] is False
    assert basic["attachment_count"] == 6


def test_publish_time_is_istanbul_converted_to_utc():
    assert extract_disclosure_basic(RAW)["published_at"] == datetime(2026, 10, 13, 11, 48, 14, tzinfo=timezone.utc)


def test_multi_stock_code_keeps_the_primary():
    raw = RAW.replace(r'\"stockCode\":\"BRKO\"', r'\"stockCode\":\"AEFES, SUNTK\"')
    assert extract_disclosure_basic(raw)["stock_code"] == "AEFES"


def test_page_without_payload_is_none_not_guessed():
    assert extract_disclosure_basic("<html>no payload</html>") is None
    assert extract_disclosure_basic("") is None
