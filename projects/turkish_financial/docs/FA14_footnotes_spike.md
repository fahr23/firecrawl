# FA-14 — Footnotes spike report

**Status:** Feasibility not yet determined. This is a scoping document, not a
go/no-go — the spike itself (inspecting 30 real KAP annual reports' footnote
sections) has not been run.

## What the spike asks

Per the requirements doc (§FA-14): spike on 30 companies — can KAP reports'
footnote notes (foreign-currency position, financial-liabilities maturity,
interest-rate risk) be parsed reliably? If yes, build the `footnotes` kind:
`fx_positions[]`, `debt_maturity` buckets, `fixed_rate_debt`/`floating_rate_debt`.

## Why this wasn't run in this session

The spike's method is explicitly document inspection: open 30 real KAP annual
report disclosures, find each report's FX-position / debt-maturity /
interest-rate-risk footnote, and judge whether its structure (table layout,
label wording, units) is consistent enough across companies to parse
automatically. That requires either:

- live KAP access to fetch real annual-report disclosures (financial
  statements include footnotes as attached PDF/XBRL sections, not the
  structured `financialTable` rows this provider already parses), or
- a set of sample footnote excerpts supplied by the person running the spike.

Neither was available in this working session. Guessing at footnote structure
from general knowledge of TFRS disclosure requirements would not be a
feasibility finding — it would be fabricating the spike's own result, which
contradicts the honest-absence principle this provider is built around (§3.4).

## What is already known, not guessed

- The existing statement-parsing pipeline (`scrapers/kap_financial_parser.py`)
  parses the **primary statements** (balance sheet, income statement, cash
  flow) from the financial-report disclosure page's rendered markdown. It does
  **not** currently parse footnote/note sections — those are a distinct part
  of the same disclosure (or a separate attachment) with their own layout.
- KAP's financial-report disclosure page (`/tr/Bildirim/{disclosureIndex}`)
  is the page this provider already scrapes via Firecrawl for the primary
  statements (`fetch_financial_statement_facts` in `scrapers/kap_scraper.py`).
  If footnotes are rendered on the same page (common for TFRS filings, since
  footnotes are part of the same financial-statement disclosure), the existing
  Firecrawl scrape+markdown pipeline could plausibly serve as the fetch layer
  without new infrastructure — but this is a plausibility note, not a
  confirmed finding, since no real page was inspected.
- TFRS 7 (Financial Instruments: Disclosures) is the standard that mandates
  the three note types FA-14 wants (currency risk, liquidity/maturity risk,
  interest-rate risk), so companies reporting under TFRS are required to
  disclose *something* in this shape. Whether the KAP-rendered HTML exposes it
  in a machine-parseable table (vs. embedded in a PDF attachment, or as prose)
  varies by company/filing and is exactly what the spike needs to check.

## What running the spike actually requires

1. Pick ~30 BIST companies across a few sectors (the FX/debt-maturity notes
   differ in relevance between, say, an exporter and a domestic retailer —
   sampling across sectors matters more than picking 30 at random from one).
2. For each, fetch its latest annual financial-report disclosure via the
   existing `KAPScraper.fetch_financial_statement_facts` path (or the
   disclosure page directly) and locate the three footnote sections.
3. Record, per company: found/not-found for each note type, and if found,
   whether it rendered as a parseable table or unstructured text/PDF.
4. Compute a success rate; the requirements doc's own accept criterion is "a
   spike report with success rate and failure reasons; decision to proceed or
   stop" — this document is the shape that report should take, filled in once
   steps 1–3 actually run.

## Recommendation

Do not build the `footnotes` kind or its schema yet. Run the sampling
described above first — ideally reusing the already-proven disclosure-page
scrape path — and only design `fx_positions[]`/`debt_maturity` storage once
real footnote markup confirms the layout is parseable.
