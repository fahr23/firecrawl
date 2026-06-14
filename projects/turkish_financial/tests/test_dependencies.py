"""Quick test to verify all dependencies are installed and working"""
import sys
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

def test_imports():
    """Test that all required modules can be imported"""
    import aiohttp
    assert aiohttp.__version__

    import fitz  # PyMuPDF
    assert fitz.version

    from fpdf import FPDF
    assert FPDF is not None

    from openai import OpenAI
    assert OpenAI is not None


def test_text_extractor():
    """Test text extractor utility"""
    from utils.text_extractor import TextExtractorFactory, PDFTextExtractor

    # Test factory
    extractor = TextExtractorFactory.create('pdf')
    assert isinstance(extractor, PDFTextExtractor)

    # Test extractor has required methods
    assert hasattr(extractor, 'extract_text')
    assert hasattr(extractor, 'normalize_text')


def test_llm_analyzer():
    """Test LLM analyzer utility"""
    from utils.llm_analyzer import (
        LLMAnalyzer,
        LocalLLMProvider,
        OpenAIProvider,
        PDFReportGenerator
    )

    # Test provider classes exist
    assert LocalLLMProvider is not None
    assert OpenAIProvider is not None
    assert LLMAnalyzer is not None

    # Test PDF generator
    generator = PDFReportGenerator()
    assert hasattr(generator, 'generate_report')


def test_kap_scraper_enhancements():
    """Test KAP scraper has new methods"""
    from scrapers.kap_scraper import KAPScraper

    # Test new methods exist
    assert hasattr(KAPScraper, 'configure_llm')
    assert hasattr(KAPScraper, 'download_pdf_attachment')
    assert hasattr(KAPScraper, 'analyze_reports_with_llm')
    assert hasattr(KAPScraper, 'scrape_with_analysis')

if __name__ == "__main__":
    print("=" * 60)
    print("DEPENDENCY & INTEGRATION TESTS")
    print("=" * 60)
    
    tests = [
        ("Core Dependencies", test_imports),
        ("Text Extractor", test_text_extractor),
        ("LLM Analyzer", test_llm_analyzer),
        ("KAP Scraper Enhancements", test_kap_scraper_enhancements),
    ]
    
    results = []
    for name, test_func in tests:
        print(f"\n{'─' * 60}")
        print(f"Testing: {name}")
        print('─' * 60)
        results.append(test_func())
    
    print("\n" + "=" * 60)
    print("RESULTS")
    print("=" * 60)
    for (name, _), result in zip(tests, results):
        status = "✓ PASS" if result else "✗ FAIL"
        print(f"{status}: {name}")
    
    all_passed = all(results)
    print("\n" + ("✓ ALL TESTS PASSED" if all_passed else "✗ SOME TESTS FAILED"))
    sys.exit(0 if all_passed else 1)
