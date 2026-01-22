"""Quick test to verify all dependencies are installed and working"""
import sys
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

def test_imports():
    """Test that all required modules can be imported"""
    try:
        import aiohttp
        print("✓ aiohttp:", aiohttp.__version__)
        
        import fitz  # PyMuPDF
        print("✓ PyMuPDF:", fitz.version)
        
        from fpdf import FPDF
        print("✓ fpdf2: imported successfully")
        
        from openai import OpenAI
        print("✓ openai: imported successfully")
        
        print("\n✓ All core dependencies installed!")
        return True
    except ImportError as e:
        print(f"✗ Import error: {e}")
        return False

def test_text_extractor():
    """Test text extractor utility"""
    try:
        from utils.text_extractor import TextExtractorFactory, PDFTextExtractor
        
        # Test factory
        extractor = TextExtractorFactory.create('pdf')
        assert isinstance(extractor, PDFTextExtractor)
        print("✓ TextExtractorFactory working")
        
        # Test extractor has required methods
        assert hasattr(extractor, 'extract_text')
        assert hasattr(extractor, 'normalize_text')
        print("✓ PDFTextExtractor has required methods")
        
        return True
    except Exception as e:
        print(f"✗ Text extractor error: {e}")
        return False

def test_llm_analyzer():
    """Test LLM analyzer utility"""
    try:
        from utils.llm_analyzer import (
            LLMAnalyzer, 
            LocalLLMProvider, 
            OpenAIProvider,
            PDFReportGenerator
        )
        
        # Test provider classes exist
        assert LocalLLMProvider is not None
        assert OpenAIProvider is not None
        print("✓ LLM provider classes available")
        
        # Test analyzer initialization (without actual provider)
        print("✓ LLMAnalyzer class available")
        
        # Test PDF generator
        generator = PDFReportGenerator()
        assert hasattr(generator, 'generate_report')
        print("✓ PDFReportGenerator working")
        
        return True
    except Exception as e:
        print(f"✗ LLM analyzer error: {e}")
        return False

def test_kap_scraper_enhancements():
    """Test KAP scraper has new methods"""
    try:
        from scrapers.kap_scraper import KAPScraper
        
        # Test new methods exist
        assert hasattr(KAPScraper, 'configure_llm')
        assert hasattr(KAPScraper, 'download_pdf_attachment')
        assert hasattr(KAPScraper, 'analyze_reports_with_llm')
        assert hasattr(KAPScraper, 'scrape_with_analysis')
        print("✓ KAPScraper has all new methods")
        
        return True
    except Exception as e:
        print(f"✗ KAP scraper error: {e}")
        return False

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
