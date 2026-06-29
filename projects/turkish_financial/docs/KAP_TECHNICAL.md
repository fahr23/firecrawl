# KAP Technical Reference

## Why KAP Requires Direct API Access

KAP (`kap.org.tr`) is a Single Page Application (SPA). The HTML interface renders content with JavaScript, so standard HTML crawling yields empty pages or bot-interception errors. The correct approach is to call the same JSON API the browser uses.

**Direct API advantages over HTML crawling:**
- 500+ disclosure records in under 1 second
- Structured data — no fragile parsing
- Not affected by UI redesigns
- `disclosureIndex` field directly gives the PDF URL

---

## Core API Endpoints

### Disclosure Query

```
POST https://www.kap.org.tr/tr/api/memberDisclosureQuery
Content-Type: application/json
```

```json
{
  "fromDate": "2026-01-18",
  "toDate":   "2026-01-25",
  "memberType": "IGS",
  "disclosureClass": "",
  "subjectList": []
}
```

Date format: `YYYY-MM-DD` (confirmed working).

`memberType`: `"IGS"` = BIST-listed companies.

**Response:** array of disclosure objects:

| Field | Description |
|-------|-------------|
| `disclosureIndex` | Key ID — use to build PDF URL |
| `kapTitle` | Report title |
| `publishDate` | ISO timestamp |
| `stockCodes` | Comma-separated ticker codes |
| `subject` | Report subject |
| `summary` | Brief text summary |
| `disclosureType` | Disclosure category |
| `attachmentCount` | Number of PDFs attached |

### PDF Download

```
GET https://www.kap.org.tr/tr/BildirimPdf/{disclosureIndex}
```

Returns binary PDF. Note: the `/tr/Bildirim/{disclosureIndex}` **page** (HTML) is different from the PDF download URL.

### Financial Table (Fundamentals)

```
GET https://www.kap.org.tr/tr/api/financialTable/listCompanyExcelMembers/{mkkMemberOid}/{year}/T
```

Returns a list of financial report disclosure indexes for a company/year. Use these indexes to fetch the actual disclosure pages (not the old `.xlsx` download, which is dead at KAP).

### Company Page (OID Resolution)

```
GET https://www.kap.org.tr/tr/bist-sirketler
```

Contains company summary URLs. Scrape each company's summary page to extract its `mkkMemberOid` (needed for financial table lookups).

---

## mkkMemberOid Resolution

OIDs are required for financial statement queries. Resolution process:

1. Fetch `/tr/bist-sirketler` — company listing
2. For each ticker, follow its summary URL
3. Extract `mkkMemberOid` from embedded page data
4. Persist to `bist_companies.mkk_member_oid` — resolve once, reuse forever

**Critical:** KAP rate-limits bursts. Use `KAP_PAGE_DELAY_S` (default 4s) between requests. Batch OID resolution is a slow one-time crawl; subsequent runs use cached values.

```python
# Force OID refresh (rarely needed)
await scraper.refresh_member_oids_via_get()
```

---

## Anti-Bot Considerations

KAP uses an anti-bot interstitial on its API endpoints. Behavior depends on deployment:

| Environment | Working proxy type |
|-------------|-------------------|
| Self-hosted Firecrawl | `basic` succeeds; `stealth` trips `document_antibot` |
| Firecrawl Cloud | Usually needs `stealth` |

The scraper tries proxies in order: `KAP_FIRECRAWL_PROXY=basic,auto,stealth` (configurable).

Disclosure-query POST endpoints (`/tr/api/memberDisclosureQuery`) remain hardest to reach from server context. If these return zero results, see [ANTI_BOT.md](ANTI_BOT.md) for proxy/stealth configuration.

---

## Implementation (kap_scraper.py)

```python
from scrapers.kap_scraper import KAPScraper
from database.db_manager import DatabaseManager

db = DatabaseManager()
scraper = KAPScraper(db_manager=db)

# Scrape last 7 days
result = await scraper.scrape(days_back=7)
# result: {"scraped": 145, "companies": 87, "date_range": "..."}

# Resolve OIDs for financial table access
await scraper.refresh_member_oids_via_get()

# Get financial statements for a company/year
statements = await scraper.fetch_financial_statements(ticker="AKBNK", year=2025)
```

---

## Financial Statement Flow

```
1. Resolve mkkMemberOid for ticker (cached in bist_companies)
2. GET /tr/api/financialTable/listCompanyExcelMembers/{oid}/{year}/T
   → list of disclosureIndex values for that year
3. For each disclosureIndex:
   GET /tr/Bildirim/{disclosureIndex}   (HTML page, not PDF)
   → scrape rendered financial tables
4. Parse → kap_financial_statements table
5. Compute ratios → kap_fundamentals table
```

---

## Disclosure Classes (disclosureClass filter)

| Code | Meaning |
|------|---------|
| `FR` | Financial Reports |
| `ODA` | Material Disclosures |
| `SCA` | Special Case Disclosures |
| `` (empty) | All types |

---

## Why Not Use Firecrawl for KAP HTML Pages?

Firecrawl excels at converting rendered HTML to markdown. For KAP:

- The SPA requires JS execution — stock `fetch` engine gets empty content
- KAP anti-bot blocks the Playwright engine without proxy/stealth (see [ANTI_BOT.md](ANTI_BOT.md))
- PDF downloads are binary, not web pages

**Use Firecrawl for:** individual disclosure pages (`/tr/Bildirim/{index}`) where you need rendered HTML — with the right proxy level.

**Use direct `requests` for:** the JSON API endpoints where you already have structured data.

---

## Known Limitations

- POST endpoints (`/tr/api/memberDisclosureQuery`) can be blocked from bare server context; use Firecrawl proxy chain
- OID resolution must be paced at ≥4s/request to avoid rate-limit blocks
- The old `.xlsx` financial report download endpoint is dead (404 even in a real browser); use the HTML disclosure page instead
