"""
Tests for detect_instruments() in instrument_identity_map.

Verifies: ticker-code detection, company-name substring detection (Turkish lowercase),
multi-ticker return, and no false positives on unrelated text.
"""
import pytest

from infrastructure.contracts.instrument_identity_map import detect_instruments


class TestDetectInstruments:

    def test_detects_uppercase_ticker_token(self):
        result = detect_instruments("THYAO bugün yüzde iki arttı.")
        assert "THYAO" in result

    def test_detects_company_name_in_lowercase(self):
        # YouTube auto-captions are lowercase
        result = detect_instruments("türk hava yolları bu çeyrekte kar açıkladı.")
        assert "THYAO" in result

    def test_detects_multiple_tickers(self):
        text = "akbank ve garanti bugün iyi performans sergiledi."
        result = detect_instruments(text)
        assert "AKBNK" in result
        assert "GARAN" in result

    def test_no_false_positives_on_unrelated_text(self):
        result = detect_instruments("bugün hava çok güzel ve sıcak.")
        assert result == []

    def test_deduplicates_results(self):
        text = "akbank akbank akbank"
        result = detect_instruments(text)
        assert result.count("AKBNK") == 1

    def test_mixed_case_ticker_with_company_name(self):
        """Ticker appears both as uppercase code and via company name — deduplicated."""
        text = "AKBNK yani akbank rekor kırdı."
        result = detect_instruments(text)
        assert result.count("AKBNK") == 1

    def test_empty_text_returns_empty(self):
        assert detect_instruments("") == []

    def test_detects_thyao_from_alt_name(self):
        # "turk hava yollari" is a STATIC_BIST_MAP variant
        result = detect_instruments("turk hava yollari genel kurul kararı açıkladı.")
        assert "THYAO" in result

    def test_detects_tupras(self):
        result = detect_instruments("tüpraş rafinerisi bu yıl rekor üretim yaptı.")
        assert "TUPRS" in result

    def test_detects_arcelik(self):
        result = detect_instruments("arçelik ihracat rakamlarını açıkladı.")
        assert "ARCLK" in result

    def test_order_uppercase_before_name(self):
        """Uppercase ticker scan runs first; order of results is deterministic."""
        text = "GARAN ve garanti bankası iyi haber verdi."
        result = detect_instruments(text)
        assert result[0] == "GARAN"  # uppercase match wins first position

    def test_returns_list_not_set(self):
        result = detect_instruments("akbank büyüyor")
        assert isinstance(result, list)
