### KAP Scraper Advanced Features

Complete guide for PDF extraction and LLM analysis capabilities added to the KAP scraper.

---

## 🎯 Overview

The enhanced KAP scraper now includes:

1. **PDF Download & Text Extraction** - Automatically download and extract text from PDF attachments
2. **LLM Analysis** - Analyze financial disclosures using local or cloud LLM providers
3. **PDF Report Generation** - Generate comprehensive analysis reports in PDF format
4. **Modular Architecture** - Clean separation using design patterns

---

## 🏗️ Architecture & Design Patterns

### Strategy Pattern
```python
# Text extraction uses Strategy pattern
class TextExtractor(ABC):
    @abstractmethod
    def extract_text(self, content: bytes) -> str:
        pass

class PDFTextExtractor(TextExtractor):
    def extract_text(self, content: bytes) -> str:
        # PDF-specific implementation
        ...
```

### Factory Pattern
```python
# Create appropriate extractor based on content type
extractor = TextExtractorFactory.create('pdf')
text = extractor.extract_text(pdf_content)
```

### Dependency Injection
```python
# LLM provider is injected
analyzer = LLMAnalyzer(provider=LocalLLMProvider())
```

---

## 📦 New Components

### 1. Text Extractor (`utils/text_extractor.py`)

**Purpose**: Extract and normalize text from various document formats

**Classes**:
- `TextExtractor` (ABC) - Base interface
- `PDFTextExtractor` - PDF extraction using PyMuPDF
- `TextExtractorFactory` - Create extractors by type

**Features**:
- Unicode normalization
- Multiple format support (extensible)
- Clean text output

**Usage**:
```python
from utils.text_extractor import TextExtractorFactory

extractor = TextExtractorFactory.create('pdf')
text = extractor.extract_text(pdf_bytes)
```

### 1.1. PDF Downloader (`utils/pdf_downloader.py`)

Purpose: Reliable async PDF downloads with retries and integrated text extraction.

Features:
- Async downloads via aiohttp with retry + exponential backoff
- Content-Type detection and basic validation
- Saves PDF and extracted text to configured directories
- Returns rich metadata (paths, size, attempts, content type)

Usage:
```python
from pathlib import Path
from utils.text_extractor import TextExtractorFactory
from utils.pdf_downloader import PDFDownloader

factory = TextExtractorFactory()
downloader = PDFDownloader(
    download_dir=Path('data/kap_pdfs'),
    text_dir=Path('data/kap_texts'),
    extractor_factory=factory,
)

result = await downloader.download_and_extract('https://example.com/report.pdf')
print(result['pdf_path'], result['text_path'])
```

### 2. LLM Analyzer (`utils/llm_analyzer.py`)

**Purpose**: Analyze financial data using LLM providers

**Classes**:
- `LLMProvider` (ABC) - Base interface
- `LocalLLMProvider` - Local LLM (LM Studio, Ollama)
- `OpenAIProvider` - OpenAI API
- `PDFReportGenerator` - Generate analysis reports
- `LLMAnalyzer` - Main analyzer with DI

**Features**:
- Multiple provider support
- Automatic content chunking
- Turkish financial analysis prompts
- PDF report generation with Unicode support

**Usage**:
```python
from utils.llm_analyzer import LLMAnalyzer, LocalLLMProvider

provider = LocalLLMProvider(
    base_url="http://localhost:1234/v1",
    model="Llama-3-8B-Instruct-Finance-RAG"
)
analyzer = LLMAnalyzer(provider)

analyses = analyzer.analyze_reports(reports)
analyzer.generate_pdf_report(analyses, "output.pdf")
```

### 3. Enhanced KAP Scraper (`scrapers/kap_scraper.py`)

**New Methods**:

#### `configure_llm(provider_type, **config)`
Configure LLM provider for analysis

```python
scraper.configure_llm(
    provider_type="local",
    base_url="http://localhost:1234/v1",
    model="Llama-3-8B-Instruct-Finance-RAG"
)
```

#### `download_pdf_attachment(pdf_url, filename)`
Download PDF and extract text (delegates to `PDFDownloader`)

```python
result = await scraper.download_pdf_attachment(
    "https://www.kap.org.tr/.../report.pdf"
)
# Returns: {pdf_path, text_path, extracted_text, filename}
```

#### `analyze_reports_with_llm(reports, generate_pdf, output_filename)`
Analyze reports using configured LLM

```python
result = await scraper.analyze_reports_with_llm(
    reports=reports,
    generate_pdf=True,
    output_filename="analysis.pdf"
)
```

#### `scrape_with_analysis(days_back, company_symbols, download_pdfs, analyze_with_llm)`
Complete workflow: scrape → extract → analyze

```python
result = await scraper.scrape_with_analysis(
    days_back=7,
    download_pdfs=True,
    analyze_with_llm=True
)
```

---

## 🚀 Quick Start

### 1. Install Dependencies

```bash
cd examples/turkish-financial-data-scraper
pip install -r requirements.txt
```

New dependencies:
- `PyMuPDF` - PDF text extraction
- `fpdf2` - PDF generation with Unicode
- `aiohttp` - Async HTTP client
- `openai` - LLM integration (OpenAI & local)

### 2. Basic Usage

```python
import asyncio
from database.db_manager import DatabaseManager
from scrapers.kap_scraper import KAPScraper

async def main():
    db_manager = DatabaseManager()
    scraper = KAPScraper(db_manager=db_manager)
    
    # Just scrape (no extras)
    result = await scraper.scrape(days_back=7)
    
    # With PDF extraction
    result = await scraper.scrape_with_analysis(
        days_back=7,
        download_pdfs=True,
        analyze_with_llm=False
    )
    
    # Full workflow with LLM
    scraper.configure_llm(provider_type="local")
    result = await scraper.scrape_with_analysis(
        days_back=7,
        download_pdfs=True,
        analyze_with_llm=True
    )

asyncio.run(main())
```

### 3. Run Examples

```bash
python examples/example_kap_advanced.py
```

---

## 🔧 Configuration

### Local LLM Setup (LM Studio)

1. Install [LM Studio](https://lmstudio.ai/)
2. Download a finance-focused model (e.g., Llama-3-8B-Instruct-Finance-RAG)
3. Start local server on port 1234
4. Configure scraper:

```python
scraper.configure_llm(
    provider_type="local",
    base_url="http://localhost:1234/v1",
    api_key="lm-studio",
    model="your-model-name",
    temperature=0.7,
    chunk_size=4000
)
```

### OpenAI Configuration

```python
import os

scraper.configure_llm(
    provider_type="openai",
    api_key=os.getenv("OPENAI_API_KEY"),
    model="gpt-4",
    temperature=0.7
)
```

### Storage Paths

Default paths (customizable in `__init__`):
```
data/
├── kap_pdfs/       # Downloaded PDF files
├── kap_texts/      # Extracted text files
└── kap_analysis/   # LLM analysis reports
```

---

## 📊 Complete Workflow Example

```python
async def complete_workflow():
    """Full KAP analysis workflow"""
    
    # 1. Initialize
    db_manager = DatabaseManager()
    scraper = KAPScraper(db_manager=db_manager)
    
    # 2. Configure LLM
    scraper.configure_llm(
        provider_type="local",
        base_url="http://localhost:1234/v1",
        model="Llama-3-8B-Instruct-Finance-RAG"
    )
    
    # 3. Run complete workflow
    result = await scraper.scrape_with_analysis(
        days_back=7,
        company_symbols=["AKBNK", "THYAO"],  # Specific companies
        download_pdfs=True,
        analyze_with_llm=True
    )
    
    # 4. Process results
    if result['success']:
        print(f"Scraped {result['total_companies']} companies")
        
        # PDF extractions
        for report in result['reports']:
            if 'pdf_extraction' in report:
                print(f"Extracted: {report['pdf_extraction']['filename']}")
        
        # LLM analysis
        if 'llm_analysis' in result:
            analysis = result['llm_analysis']
            print(f"Analyzed {analysis['total_analyzed']} reports")
            print(f"Report saved: {analysis.get('pdf_report')}")
            
            # Show analyses
            for a in analysis['analyses']:
                print(f"\n{a['title']}")
                print(a['content'][:300])
    
    return result
```

---

## 🎨 Customization

### Add New Text Extractor

```python
from utils.text_extractor import TextExtractor, TextExtractorFactory

class DocxTextExtractor(TextExtractor):
    def extract_text(self, content: bytes) -> str:
        # Your implementation
        ...

# Register
TextExtractorFactory.register_extractor('docx', DocxTextExtractor)
```

### Add New LLM Provider

```python
from utils.llm_analyzer import LLMProvider

class CustomLLMProvider(LLMProvider):
    def analyze(self, content: str, prompt: Optional[str] = None) -> str:
        # Your implementation
        ...

# Use
provider = CustomLLMProvider()
analyzer = LLMAnalyzer(provider)
```

### Custom Analysis Prompt

Modify the default prompt in `LocalLLMProvider.analyze()` or pass custom prompt:

```python
custom_prompt = """
Analyze this financial disclosure focusing on:
1. Revenue trends
2. Risk factors
3. Growth opportunities
Provide recommendations in Turkish.
"""

# Would need to extend analyze_reports_with_llm to accept custom prompts
```

---

## 📝 Best Practices

1. **Error Handling**
   - All methods include comprehensive try/except blocks
   - Failed operations log errors but don't crash the workflow
   - Check `success` status in results

2. **Resource Management**
   - Temporary files are cleaned automatically
   - Database connections pooled and returned
   - Async sessions properly closed

3. **Performance**
   - LLM chunking prevents context overflow
   - Async operations for I/O-bound tasks
   - Configurable chunk sizes

4. **Extensibility**
   - Factory pattern for easy extractor additions
   - Strategy pattern for LLM providers
   - DI allows testing and mocking

5. **Logging**
   - All operations logged at appropriate levels
   - Progress tracking for long operations
   - Error details with context

---

## 🐛 Troubleshooting

### PDF Extraction Fails

```python
# Check PyMuPDF installation
pip install --upgrade PyMuPDF

# Verify PDF is valid
extractor = PDFTextExtractor()
text = extractor.extract_text(pdf_bytes)
```

### LLM Connection Issues

```python
# Test LM Studio connection
import requests
response = requests.get("http://localhost:1234/v1/models")
print(response.json())

# Check model is loaded
# Verify base_url and port
```

### Unicode/Turkish Characters

```python
# Ensure fonts are available for PDF generation
# Check font paths in PDFReportGenerator
```

### Memory Issues with Large PDFs

```python
# Reduce chunk size
scraper.configure_llm(
    provider_type="local",
    chunk_size=2000  # Smaller chunks
)
```

---

## 🔍 Testing

Run the test suite:

```bash
# Test text extraction
python -m pytest tests/test_text_extractor.py

# Test LLM analyzer
python -m pytest tests/test_llm_analyzer.py

# Test KAP scraper integration
python -m pytest tests/test_kap_scraper_advanced.py
```

---

## 📚 API Reference

See inline docstrings for complete API documentation:

```python
help(KAPScraper.scrape_with_analysis)
help(LLMAnalyzer.analyze_reports)
help(TextExtractorFactory)
```

---

## 🎯 Use Cases

1. **Daily Report Monitoring**
   - Scrape new disclosures daily
   - Extract PDF attachments
   - Get LLM summaries

2. **Investment Research**
   - Analyze specific companies
   - Compare multiple reports
   - Generate insight reports

3. **Compliance Tracking**
   - Monitor regulatory filings
   - Extract key information
   - Archive with analysis

4. **Market Intelligence**
   - Track industry trends
   - Identify opportunities
   - Risk assessment

---

## 📖 Further Reading

- [Firecrawl Documentation](https://docs.firecrawl.dev)
- [PyMuPDF Documentation](https://pymupdf.readthedocs.io/)
- [OpenAI API Reference](https://platform.openai.com/docs/api-reference)
- [LM Studio Guide](https://lmstudio.ai/docs)

---

**Your KAP scraper is now enterprise-ready with AI-powered analysis! 🚀**
