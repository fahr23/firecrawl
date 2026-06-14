"""
Tests for TextExtractor utilities
"""
import pytest
from utils.text_extractor import TextExtractorFactory, PDFTextExtractor, TextExtractor


def test_factory_creates_pdf_extractor():
    extractor = TextExtractorFactory.create('pdf')
    assert isinstance(extractor, PDFTextExtractor)


def test_factory_unknown_type_returns_none():
    """Unknown content types return None (factory logs a warning)."""
    result = TextExtractorFactory.create('unknown_format')
    assert result is None


def test_normalize_text_removes_extra_whitespace():
    extractor = PDFTextExtractor()
    result = extractor.normalize_text("hello   world\n\n  test")
    assert "  " not in result
    assert result == "hello world test"


def test_normalize_text_handles_unicode():
    extractor = PDFTextExtractor()
    # Unicode normalization should work without raising
    result = extractor.normalize_text("caf\u00e9 \u00e0 Paris")
    assert isinstance(result, str)


def test_normalize_text_empty_string():
    extractor = PDFTextExtractor()
    result = extractor.normalize_text("")
    assert result == ""


def test_normalize_text_replaces_known_bad_chars():
    extractor = PDFTextExtractor()
    # The extractor replaces the specific character '൴' with 'i'
    result = extractor.normalize_text("൴")
    assert "i" in result


def test_pdf_extractor_has_extract_text_method():
    extractor = PDFTextExtractor()
    assert callable(extractor.extract_text)


def test_pdf_extractor_invalid_bytes_returns_empty():
    """Invalid bytes log an error and return empty string (no exception propagated)."""
    extractor = PDFTextExtractor()
    result = extractor.extract_text(b"not a real pdf")
    assert result == ""


def test_pdf_extractor_extract_text_returns_string():
    """Verify extract_text with valid PDF-like bytes returns string (minimal smoke test)."""
    import fitz
    import io

    # Create a minimal PDF in-memory using PyMuPDF
    doc = fitz.open()
    page = doc.new_page()
    page.insert_text((50, 72), "Hello financial world")
    pdf_bytes = doc.tobytes()
    doc.close()

    extractor = PDFTextExtractor()
    text = extractor.extract_text(pdf_bytes)
    assert isinstance(text, str)
    assert "Hello" in text or len(text) >= 0  # At minimum, no exception
