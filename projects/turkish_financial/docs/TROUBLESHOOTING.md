# Troubleshooting

## KAP Returns Zero Records

**Root cause:** KAP blocks automated access at the network level, not a code bug.

Evidence:
- Company-specific URLs return HTTP 500 with "hata_500" image and error code `XXXXX-PPE`
- Main reports page returns empty content (JavaScript not rendering)
- Scraper error-detection, HTML parsing, and DB saving all work correctly

**Solutions by severity:**

| Solution | Effort | Effectiveness |
|----------|--------|---------------|
| Set proxy env vars (Level 1) | 5 min | Resolves most IP bans |
| Add `--disable-blink-features` (Level 2) | 2 min + rebuild | Removes `webdriver` signal |
| Use Firecrawl Cloud instead of self-hosted | Immediate | Best for high-volume |
| Rate limiting: `KAP_PAGE_DELAY_S=4` | Config only | Prevents burst blocks |

See [ANTI_BOT.md](ANTI_BOT.md) for detailed implementation.

**If disclosure POST endpoints (`/tr/api/memberDisclosureQuery`) return 0 results:**
- These endpoints are hardest to reach from server context
- `basic` proxy works on self-hosted; `stealth` may not
- Firecrawl Cloud with `stealth` is the most reliable path

---

## TradingView Returns Zero Sectors/Industries

**Causes:**
1. LLM API not configured (no API key in `.env`)
2. LLM quota exceeded
3. Page structure changed at TradingView

**Checks:**
```bash
# Verify LLM key is set
grep -E "OPENAI_API_KEY|GEMINI_API_KEY|LOCAL_LLM_BASE_URL" .env

# Test LLM manually
python3 -c "from utils.llm_analyzer import LLMAnalyzer; print('LLM OK')"
```

---

## Database: Schema Not Found

```
psycopg2.errors.InvalidSchemaName: schema "turkish_financial" does not exist
```

**Fix:**
1. Ensure `DB_SCHEMA=turkish_financial` is in `.env`
2. Run the app once — schema auto-creates on `DatabaseManager.__init__()`
3. Or create manually: `CREATE SCHEMA turkish_financial;`

---

## Database: Tables in Wrong Schema

If tables were created in `public` schema before schema isolation was added:

```bash
# Temporary fix: keep using public
DB_SCHEMA=public

# Permanent: migrate tables
psql -h nuq-postgres -U postgres -d postgres
ALTER TABLE kap_reports SET SCHEMA turkish_financial;
ALTER TABLE bist_companies SET SCHEMA turkish_financial;
# ... repeat for all tables
```

---

## PDF Extraction Fails

```
Error: pdfplumber not installed / PyMuPDF extraction failed
```

```bash
pip install pdfplumber pymupdf
```

If PDF text is empty (scanned image PDF), the document has no extractable text layer — this is a KAP source issue, not a code issue.

---

## API Server Won't Start

```
ERROR: [Errno 98] Address already in use: ('0.0.0.0', 8000)
```

```bash
lsof -i :8000        # find the process
kill -9 <PID>         # or change port in api_server.py
```

---

## HuggingFace Model Download Fails

```bash
# Check internet/proxy
python3 -c "from transformers import AutoTokenizer; AutoTokenizer.from_pretrained('savasy/bert-base-turkish-sentiment-cased')"
```

If network is blocked in the container, pre-download the model outside and mount it, then set:
```env
HUGGINGFACE_MODEL=/path/to/local/model
```

---

## Firecrawl API Connection Refused

```
ConnectionRefusedError: [Errno 111] Connection refused (http://api:3002)
```

```bash
docker ps | grep api     # check Firecrawl API container is running
docker logs api          # inspect startup errors
```

Ensure `FIRECRAWL_BASE_URL=http://api:3002` in `.env` (not `localhost:3002`).

---

## Import Errors After Refactoring

```
ModuleNotFoundError: No module named 'domain'
```

Ensure you're running from the project root:
```bash
cd /workspaces/firecrawl/projects/turkish_financial
python3 api_server.py   # not from a subdirectory
```

Or check `requirements.txt` is fully installed:
```bash
pip install -r requirements.txt
```

---

## Log Locations

```bash
tail -f logs/scraper.log          # main scraper log
docker logs api --follow           # Firecrawl API log
docker logs playwright-service     # Playwright service log
```

Enable debug logging:
```bash
LOG_LEVEL=DEBUG python3 main.py --scraper kap
```
