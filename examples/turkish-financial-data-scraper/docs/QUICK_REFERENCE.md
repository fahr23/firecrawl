# 🚀 Quick Reference - KAP Scraper Advanced Features

## Installation
```bash
cd examples/turkish-financial-data-scraper
pip install -r requirements.txt
```

## Basic Scraping (No Extras)
```python
from database.db_manager import DatabaseManager
from scrapers.kap_scraper import KAPScraper
import asyncio

async def basic():
    db = DatabaseManager()
    scraper = KAPScraper(db_manager=db)
    result = await scraper.scrape(days_back=7)

asyncio.run(basic())
```

## With PDF Extraction
```python
async def with_pdfs():
    db = DatabaseManager()
    scraper = KAPScraper(db_manager=db)
    
    result = await scraper.scrape_with_analysis(
        days_back=7,
        download_pdfs=True,
        analyze_with_llm=False  # Just extract PDFs
    )
    
    # Check extracted files in data/kap_pdfs/ and data/kap_texts/

asyncio.run(with_pdfs())
```

## With Local LLM Analysis
```python
async def with_local_llm():
    db = DatabaseManager()
    scraper = KAPScraper(db_manager=db)
    
    # 1. Configure local LLM (LM Studio on port 1234)
    scraper.configure_llm(
        provider_type="local",
        base_url="http://localhost:1234/v1",
        model="Llama-3-8B-Instruct-Finance-RAG",
        temperature=0.7
    )
    
    # 2. Run full workflow
    result = await scraper.scrape_with_analysis(
        days_back=7,
        download_pdfs=True,
        analyze_with_llm=True
    )
    
    # 3. Check analysis report in data/kap_analysis/

asyncio.run(with_local_llm())
```

## With OpenAI API
```python
import os

async def with_openai():
    db = DatabaseManager()
    scraper = KAPScraper(db_manager=db)
    
    # Configure OpenAI
    scraper.configure_llm(
        provider_type="openai",
        api_key=os.getenv("OPENAI_API_KEY"),
        model="gpt-4",
        temperature=0.7
    )
    
    result = await scraper.scrape_with_analysis(
        days_back=7,
        download_pdfs=True,
        analyze_with_llm=True
    )

asyncio.run(with_openai())
```

## Specific Companies Only
```python
async def specific_companies():
    db = DatabaseManager()
    scraper = KAPScraper(db_manager=db)
    scraper.configure_llm(provider_type="local")
    
    result = await scraper.scrape_with_analysis(
        days_back=30,
        company_symbols=["AKBNK", "THYAO", "EREGL"],  # Only these
        download_pdfs=True,
        analyze_with_llm=True
    )

asyncio.run(specific_companies())
```

## Command Line Examples
```bash
# Run test suite
python tests/test_dependencies.py

# Run advanced examples
python examples/example_kap_advanced.py

# Run with specific scraper
python main.py --scraper kap --log-level INFO
```

## File Locations

| What | Where |
|------|-------|
| Downloaded PDFs | `data/kap_pdfs/` |
| Extracted text | `data/kap_texts/` |
| Analysis reports | `data/kap_analysis/` |
| Database | PostgreSQL (see .env) |

## Common Issues

### PDF extraction fails
```python
# Check PyMuPDF installed
pip install --upgrade PyMuPDF
```

### LLM connection fails
```python
# Test LM Studio is running
import requests
r = requests.get("http://localhost:1234/v1/models")
print(r.json())
```

### Unicode/Turkish text issues
The PDF generator uses DejaVu fonts automatically - should work out of the box.

## Configuration Options

### `configure_llm()` Parameters

**For Local LLM:**
```python
scraper.configure_llm(
    provider_type="local",
    base_url="http://localhost:1234/v1",  # LM Studio default
    api_key="lm-studio",                   # Required but unused
    model="your-model-name",               # Model loaded in LM Studio
    temperature=0.7,                       # 0.0-1.0 (creativity)
    chunk_size=4000                        # Characters per chunk
)
```

**For OpenAI:**
```python
scraper.configure_llm(
    provider_type="openai",
    api_key="sk-...",                      # Your OpenAI key
    model="gpt-4",                         # or gpt-3.5-turbo
    temperature=0.7
)
```

### `scrape_with_analysis()` Parameters

```python
result = await scraper.scrape_with_analysis(
    days_back=7,                  # How far back to scrape
    company_symbols=None,         # None = all, or ["AKBNK", ...]
    download_pdfs=True,           # Download & extract PDFs
    analyze_with_llm=True         # Run LLM analysis
)
```

## Return Structure

```python
{
    'success': True,
    'total_companies': 10,
    'reports': [
        {
            'company': 'AKBNK',
            'title': '...',
            'pdf_extraction': {
                'pdf_path': 'data/kap_pdfs/...',
                'text_path': 'data/kap_texts/...',
                'extracted_text': '...',
                'success': True
            }
        }
    ],
    'llm_analysis': {
        'total_analyzed': 10,
        'analyses': [...],
        'pdf_report': 'data/kap_analysis/analysis_20250105_120000.pdf'
    }
}
```

---

**For full documentation, see `/docs/ADVANCED_FEATURES.md`**
