"""
Unit tests for the KAP event classifier (FA-07).

Pure function over a kap_disclosures-shaped dict — no DB, no network.
"""
from datetime import date

from domain.services.kap_event_classifier import classify, MAPPING_VERSION


def _disclosure(title, subject="", subject_code="", **over):
    row = {
        "disclosure_id": "1234567",
        "title": title,
        "subject": subject,
        "subject_code": subject_code,
        "disclosure_date": date(2026, 5, 8),
    }
    row.update(over)
    return row


class TestBonusAndRightsIssues:
    def test_bonus_issue_detected(self):
        result = classify(_disclosure("Bedelsiz Sermaye Artırımı Hakkında Bildirim"))
        assert result["event_type"] == "bonus_issue"

    def test_rights_issue_detected(self):
        result = classify(_disclosure("Bedelli Sermaye Artırımı Hakkında Bildirim"))
        assert result["event_type"] == "rights_issue"

    def test_bonus_not_confused_with_rights(self):
        # "bedelsiz" and "bedelli" differ only by one syllable — must not cross-match.
        bonus = classify(_disclosure("Şirketimizin Bedelsiz Pay Dağıtımı"))
        rights = classify(_disclosure("Şirketimizin Bedelli Pay Dağıtımı"))
        assert bonus["event_type"] == "bonus_issue"
        assert rights["event_type"] == "rights_issue"


class TestOtherEventTypes:
    def test_cash_dividend(self):
        result = classify(_disclosure("2025 Yılı Kâr Payı Ödemesi Hakkında"))
        assert result["event_type"] == "cash_dividend"

    def test_share_buyback(self):
        result = classify(_disclosure("Pay Geri Alım Programı Kapsamında İşlem"))
        assert result["event_type"] == "share_buyback"

    def test_insider_trade(self):
        result = classify(_disclosure("İçerden Öğrenenlerin Ticareti Bildirimi"))
        assert result["event_type"] == "insider_trade"

    def test_major_holder_change(self):
        result = classify(_disclosure("Ortaklık Yapısı Değişikliği Bildirimi"))
        assert result["event_type"] == "major_holder_change"

    def test_financial_report_from_title(self):
        result = classify(_disclosure("Finansal Rapor"))
        assert result["event_type"] == "financial_report"

    def test_financial_report_from_subject_code_fallback(self):
        result = classify(_disclosure("Bildirim", subject_code="FR"))
        assert result["event_type"] == "financial_report"

    def test_ozkd_fallback_is_special_situation(self):
        result = classify(_disclosure("Yönetim Kurulu Kararı", subject_code="ÖZKD"))
        assert result["event_type"] == "special_situation"

    def test_unmatched_is_other_not_a_guess(self):
        result = classify(_disclosure("Tamamen İlgisiz Bir Konu Hakkında Bildirim"))
        assert result["event_type"] == "other"


class TestEnvelopeFields:
    def test_mapping_version_and_source_index(self):
        result = classify(_disclosure("Finansal Rapor"))
        assert result["mapping_version"] == MAPPING_VERSION
        assert result["source_disclosure_index"] == "1234567"
        assert result["title"] == "Finansal Rapor"
        assert result["published_at"] == date(2026, 5, 8)

    def test_missing_title_still_classifies_from_subject_code(self):
        result = classify({"disclosure_id": "1", "subject_code": "FR"})
        assert result["event_type"] == "financial_report"
        assert result["title"] is None
