"""
Example: KAP Scraper with PDF Extraction and LLM Analysis
Demonstrates the complete workflow with all features
"""
import asyncio
import logging
import sys
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from database.db_manager import DatabaseManager
from scrapers.kap_scraper import KAPScraper
from utils.text_extractor import TextExtractorFactory
from utils.pdf_downloader import PDFDownloader

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


async def example_basic_scraping():
    """Example 1: Basic KAP scraping without additional features"""
    logger.info("=" * 60)
    logger.info("Example 1: Basic KAP Scraping")
    logger.info("=" * 60)
    
    db_manager = DatabaseManager()
    scraper = KAPScraper(db_manager=db_manager)
    
    # Scrape last 7 days of reports
    result = await scraper.scrape(days_back=7)
    
    logger.info(f"Success: {result.get('success')}")
    logger.info(f"Total companies: {result.get('total_companies')}")
    logger.info(f"Processed: {result.get('processed_companies')}")
    
    return result


async def example_with_pdf_extraction():
    """Example 2: Scraping with PDF download and text extraction"""
    logger.info("=" * 60)
    logger.info("Example 2: KAP with PDF Extraction")
    logger.info("=" * 60)
    
    db_manager = DatabaseManager()
    scraper = KAPScraper(db_manager=db_manager)
    
    # Scrape with PDF download and text extraction
    result = await scraper.scrape_with_analysis(
        days_back=3,
        download_pdfs=True,
        analyze_with_llm=False  # No LLM yet
    )
    
    logger.info(f"Success: {result.get('success')}")
    logger.info(f"Reports with PDFs extracted:")
    
    for report in result.get('reports', []):
        if 'pdf_extraction' in report:
            extraction = report['pdf_extraction']
            logger.info(f"  - {extraction['filename']}")
            logger.info(f"    Text saved to: {extraction['text_path']}")
            logger.info(f"    Text length: {len(extraction['extracted_text'])} characters")
    
    return result


async def example_pdf_downloader_demo():
    """Example 3: Standalone PDF download + text extraction demo"""
    logger.info("=" * 60)
    logger.info("Example 3: PDF Downloader (Standalone)")
    logger.info("=" * 60)

    # Initialize downloader
    factory = TextExtractorFactory()
    downloader = PDFDownloader(
        download_dir=Path("data/kap_pdfs"),
        text_dir=Path("data/kap_texts"),
        extractor_factory=factory,
    )

    # Public sample PDF (small)
    sample_pdf = "https://www.w3.org/WAI/ER/tests/xhtml/testfiles/resources/pdf/dummy.pdf"

    result = await downloader.download_and_extract(sample_pdf)
    if result and result.get("pdf_path"):
        logger.info("PDF Downloader demo completed:")
        logger.info(f"  - PDF saved:  {result['pdf_path']}")
        logger.info(f"  - Text saved: {result['text_path']}")
        logger.info(f"  - Detected Content-Type: {result.get('content_type')}")
        logger.info(f"  - Attempts: {result.get('attempts')}")
        # Preview first 120 chars
        preview = (result.get("extracted_text") or "")[:120].replace("\n", " ")
        logger.info(f"  - Text preview: {preview}...")
    else:
        logger.warning("PDF Downloader demo failed")
    return result


async def example_with_llm_analysis():
    """Example 3: Complete workflow with LLM analysis"""
    logger.info("=" * 60)
    logger.info("Example 3: KAP with LLM Analysis")
    logger.info("=" * 60)
    
    db_manager = DatabaseManager()
    scraper = KAPScraper(db_manager=db_manager)
    
    # Configure Local LLM (LM Studio)
    scraper.configure_llm(
        provider_type="local",
        base_url="http://localhost:1234/v1",
        api_key="lm-studio",
        model="QuantFactory/Llama-3-8B-Instruct-Finance-RAG-GGUF",
        temperature=0.7,
        chunk_size=4000
    )
    
    # Scrape with full analysis workflow
    result = await scraper.scrape_with_analysis(
        days_back=3,
        download_pdfs=True,
        analyze_with_llm=True
    )
    
    logger.info(f"Success: {result.get('success')}")
    
    if 'llm_analysis' in result:
        analysis = result['llm_analysis']
        logger.info(f"Total analyzed: {analysis.get('total_analyzed')}")
        
        if 'pdf_report' in analysis:
            logger.info(f"PDF report generated: {analysis['pdf_report']}")
        
        # Show first analysis summary
        if analysis.get('analyses'):
            first = analysis['analyses'][0]
            logger.info(f"\nFirst analysis title: {first['title']}")
            logger.info(f"Analysis preview: {first['content'][:200]}...")
    
    return result


async def example_openai_provider():
    """Example 4: Using OpenAI instead of local LLM"""
    logger.info("=" * 60)
    logger.info("Example 4: KAP with OpenAI Analysis")
    logger.info("=" * 60)
    
    db_manager = DatabaseManager()
    scraper = KAPScraper(db_manager=db_manager)
    
    # Configure OpenAI
    # Note: Requires OPENAI_API_KEY environment variable or pass api_key directly
    scraper.configure_llm(
        provider_type="openai",
        api_key="your-openai-api-key",  # Or use env var
        model="gpt-4",
        temperature=0.7
    )
    
    # Scrape specific companies
    result = await scraper.scrape_with_analysis(
        days_back=7,
        company_symbols=["AKBNK", "THYAO", "TUPRS"],  # Specific companies
        download_pdfs=True,
        analyze_with_llm=True
    )
    
    logger.info(f"Analysis complete: {result.get('success')}")
    
    return result


async def example_custom_analysis():
    """Example 5: Custom LLM prompt for specific analysis"""
    logger.info("=" * 60)
    logger.info("Example 5: Custom LLM Analysis Prompt")
    logger.info("=" * 60)
    
    db_manager = DatabaseManager()
    scraper = KAPScraper(db_manager=db_manager)
    
    # Configure LLM
    scraper.configure_llm(
        provider_type="local",
        base_url="http://localhost:1234/v1",
        api_key="lm-studio"
    )
    
    # Scrape reports
    scrape_result = await scraper.scrape(days_back=3)
    
    if scrape_result.get('success'):
        reports = scrape_result.get('reports', [])
        
        # Custom analysis with specific prompt
        # Note: This would require extending the analyze_reports_with_llm method
        # to accept custom prompts
        analysis_result = await scraper.analyze_reports_with_llm(
            reports=reports,
            generate_pdf=True,
            output_filename="custom_analysis.pdf"
        )
        
        logger.info(f"Custom analysis complete: {analysis_result.get('success')}")
    
    return scrape_result


async def main():
    """Run all examples"""
    
    # Choose which examples to run
    examples = [
        ("Basic Scraping", example_basic_scraping),
        ("PDF Extraction", example_with_pdf_extraction),
        ("PDF Downloader Demo", example_pdf_downloader_demo),
        # ("LLM Analysis", example_with_llm_analysis),  # Uncomment if LLM is available
        # ("OpenAI Provider", example_openai_provider),  # Uncomment with API key
        # ("Custom Analysis", example_custom_analysis),  # Uncomment if LLM is available
    ]
    
    for name, example_func in examples:
        try:
            logger.info(f"\n\nRunning: {name}\n")
            await example_func()
        except Exception as e:
            logger.error(f"Error in {name}: {e}", exc_info=True)
        
        # Wait between examples
        await asyncio.sleep(2)
    
    logger.info("\n\nAll examples completed!")


if __name__ == "__main__":
    asyncio.run(main())
