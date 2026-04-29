# Examples

Production-ready scripts for academic literature search.

## Scripts

### academic_literature_search.py
Full-featured search across multiple sources (OpenAlex, Crossref).

**Usage:**
```bash
python academic_literature_search.py "renewable energy" --max-results 50
```

---

### academic_literature_search_v2.py
Enhanced version with improved abstract enrichment and topic extraction.

**Usage:**
```bash
python academic_literature_search_v2.py "machine learning healthcare" --output results.json
```

---

### sciencedirect_literature_search.py
Search ScienceDirect via Elsevier API with institutional access.

**Prerequisites:**
- Elsevier API key (set `ELSEVIER_API_KEY` env var)
- Institutional network access recommended

**Usage:**
```bash
export ELSEVIER_API_KEY=your-key
python sciencedirect_literature_search.py "deep learning" --max-results 25
```

---

### sciencedirect_search_with_abstracts.py
Extended ScienceDirect search with full abstract retrieval.

**Usage:**
```bash
python sciencedirect_search_with_abstracts.py "neural networks" --enrich-abstracts
```

## Output
Results are saved to `../results/` in JSON, Markdown, and CSV formats.
