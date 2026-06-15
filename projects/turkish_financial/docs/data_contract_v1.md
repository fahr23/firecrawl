# External Analysis Provider — Data Contract v1.0

**Date:** 2026-06-14
**Contract version:** `1.0` (carried in every response as `contract_version`)
**Audience:** Owners/engineers of the **external sentiment** and **external fundamental** services.
**Doc set:** [00 overview](00_overview_and_placement_20260614.md) · **01 data contract (this)** ·
[02 web admin spec](02_web_admin_spec_20260614.md) · [03 provider decisions](03_provider_decisions_20260614.md).

> This is the single source of truth for the data each external service must **produce**. Both services
> implement the **same response envelope**; they differ only in the `payload`. `strategy_management` is
> the only consumer — it pulls over HTTP, normalizes into this shape, caches, and serves an admin UI.
> Your service keeps its own database; we never share a schema or a DB handle.

> **Implementation status — `kap-scraper` provider (verified 2026-06-14).** This repository **is** the
> reference provider, and it now emits **both** kinds (earlier drafts of this doc said fundamental was
> "modelled only" — that is no longer true):
> - **Sentiment** — live. Sourced from KAP company disclosures (`kap_disclosures` ⋈ `kap_disclosure_sentiment`).
> - **Fundamental** — live. Sourced from KAP "Finansal Tablolar" (`kap_financial_statements` → ratios in
>   `kap_fundamentals`), parsed by `scrapers/kap_financial_parser.py` and computed by
>   `domain/services/fundamental_analyzer_service.py`.
> Both kinds report `provider = "kap-scraper"`. This provider serves **`market=bist` only**; `usa`/`coin`
> resolve to an honest `unavailable` envelope (§5). The concrete BIST values it emits differ from the
> generic enums below — see **§2.1** and **§3.1**, and the real captured envelopes in **§6.5.1 / §6.9**.
>
> **Upstream availability & anti-bot (resolved for fundamentals — 2026-06-15).** KAP guards its
> `/api/...` JSON endpoints and report pages with an anti-bot interstitial. We clear it through Firecrawl,
> but **which proxy works depends on the deployment**: self-hosted Firecrawl has no working `stealth`
> proxy (it trips `document_antibot`), whereas `basic` succeeds; Firecrawl Cloud generally needs
> `stealth`. The scraper now tries an ordered list (`KAP_FIRECRAWL_PROXY`, default `basic,auto,stealth`).
> With that, **fundamentals are fetched live**: the financialTable JSON list + the financial-report
> **disclosure page** (`/tr/Bildirim/{idx}`, parsed from its rendered statements — the old `.xlsx`
> download endpoint is dead at KAP and 404s even via a real browser). The disclosure-query/news **POST**
> endpoints remain blocked from a bare server context (Firecrawl can't issue arbitrary POST bodies and
> this self-hosted build doesn't execute action JS), so company-disclosure **sentiment** ingestion can
> still yield zero rows. When an upstream is unreachable we persist nothing and endpoints degrade to
> `unavailable` (§5) — we never fabricate data.
>
> **GET-only ingestion (no POST).** To avoid the blocked POST APIs entirely, the scraper resolves
> `mkkMemberOid` over GET — `KAPScraper.refresh_member_oids_via_get()` reads the public BIST companies
> page (`/tr/bist-sirketler`) for each ticker's summary URL, then scrapes that page and lifts
> `mkkMemberOid` from its embedded data — then lists financial-report `disclosureIndex`es
> (`/tr/api/financialTable/listCompanyExcelMembers/{oid}/{year}/T`) and page-scrapes each report. **Caveat:**
> KAP's anti-bot is **rate-based**; isolated requests succeed but bursts get flagged (`document_antibot`),
> and this self-hosted Firecrawl has no rotating/stealth proxy to rotate out. So OID resolution must be a
> **slow, cached crawl** — pace with `KAP_PAGE_DELAY_S` (default 4 s) and rely on the fact that resolved
> OIDs persist to `bist_companies` (resolve once, reuse forever). For high-volume/low-latency resolution
> use Firecrawl Cloud (rotating proxies + `stealth`).

---

## 0. Identity mapping — resolve this first

Our platform addresses everything by **`instrument` + `market`** (e.g. `AAPL`/`usa`, `THYAO`/`bist`,
`BTCUSDT`/`coin`). The existing sentiment service keys by `company_code` / `company_name`.

**Required:** your endpoints accept our `instrument` + `market` and perform any internal mapping on your
side. If you genuinely cannot, we maintain a static map on our adapter side
(`app/config/instrument_identity_map.py`) — but that is a fallback, owned by us, never a shared table.
**Action:** answer the key-by-instrument question in [doc 03](03_provider_decisions_20260614.md).

`market` enum: `bist | usa | coin`. **This `kap-scraper` provider only carries `bist`** (KAP is a
Turkish-market source); `usa`/`coin` always return `unavailable`.

---

## 1. Common response envelope

Every endpoint returns this envelope (point endpoints return one; batch/history wrap many). Our adapter
keeps these fields and **discards anything else**.

| Field | Type | Req | Constraint / meaning |
|---|---|---|---|
| `contract_version` | string | ✓ | `"1.0"` |
| `instrument` | string | ✓ | Echo of request (our canonical symbol) |
| `market` | enum | ✓ | `bist \| usa \| coin` (echo) |
| `kind` | enum | ✓ | `sentiment \| fundamental` |
| `as_of` | string (ISO-8601 UTC) | ✓ | Effective timestamp of the data point |
| `provider` | string | ✓ | Provenance id, e.g. `kap-scraper`, `fundamentals-svc` |
| `source` | enum | ✓ | `external-db` (must never claim our DB) |
| `freshness_seconds` | integer ≥ 0 | ✓ | Age of the data at response time (drives the UI freshness badge) |
| `status` | enum | ✓ | `ok \| partial \| unavailable` |
| `payload` | object \| null | ✓ | Kind-specific (§2 / §3). `null` only when `status ≠ ok` |

---

## 2. Sentiment payload

Normalizes the existing KAP shape — reuse it, don't reinvent.

| Field | Type | Req | Constraint |
|---|---|---|---|
| `overall_sentiment` | enum | ✓ | `positive \| neutral \| negative` |
| `score` | number | ✓ | **−1.0 … +1.0** (negative→positive); our canonical scalar |
| `confidence` | number | ✓ | `0.0 … 1.0` |
| `impact_horizon` | enum | – | `short_term \| medium_term \| long_term` |
| `key_drivers` | string[] | – | e.g. `["earnings_beat","guidance_raise"]` — **array**, not a delimited string |
| `risk_flags` | string[] | – | e.g. `["litigation","fx_exposure"]` |
| `risk_level` | enum | – | `low \| medium \| high` |
| `tone_descriptors` | string[] | – | optional qualitative tags |
| `sample_size` | integer ≥ 0 | – | # disclosures/articles behind this point |
| `analyzer` | string | – | `keyword \| huggingface \| llm:<model>` (NLP method provenance) |

> If you do not emit `score`, we derive it from `overall_sentiment × confidence`
> (`positive→+`, `negative→−`, `neutral→0`). Emitting it yourself is preferred. Today `key_drivers` /
> `risk_flags` are sometimes a string and sometimes an array — **always send arrays** in v1.

### 2.1 `kap-scraper` provider specifics (sentiment)

Observed behaviour of this implementation — useful when consuming its envelopes:

- **`score` is always the derived value** `sign(overall_sentiment) × confidence`, rounded to 4 dp
  (e.g. `positive` @ `confidence 0.78` → `score 0.78`). It does **not** publish an independent magnitude;
  treat `score` and `confidence` as the same number with the sentiment's sign.
- `key_drivers` falls back to the legacy `key_sentiments` column when `key_drivers` is empty.
- `analyzer` reflects the configured NLP method (`keyword` / `huggingface` / `llm:<model>`); `sample_size`
  is the number of disclosures behind the point (usually `1` per disclosure today).
- Platform-level KAP/SPK/MKK **news** is collected into a separate `kap_news` store and is now served
  under its own `kind = "news"` endpoints (§3.2 / §4 / §6.10) — distinct from company-disclosure sentiment.

---

## 3. Fundamental payload

All fields nullable (send what you have; we render `null` as "—"). Every numeric value is for the stated
`period` / `fiscal_period` / `currency`.

| Group | Fields (type) |
|---|---|
| **Period** | `period` (ISO date, ✓), `fiscal_period` (`FY2025 \| Q1-2026 \| TTM`), `currency` (ISO-4217), `reporting_standard` (`IFRS \| US-GAAP`) |
| **Valuation** | `pe_ratio`, `pb_ratio`, `ps_ratio`, `ev_ebitda`, `peg_ratio` (number) |
| **Per-share** | `eps`, `book_value_per_share`, `dividend_per_share`, `dividend_yield` (0–1 fraction) |
| **Profitability** | `gross_margin`, `operating_margin`, `net_margin`, `roe`, `roa`, `roic` (fractions) |
| **Leverage / liquidity** | `debt_to_equity`, `net_debt_to_ebitda`, `current_ratio`, `quick_ratio`, `interest_coverage` |
| **Scale / growth** | `revenue`, `ebitda`, `net_income`, `free_cash_flow` (absolute, in `currency`), `revenue_growth_yoy`, `eps_growth_yoy` (fractions) |
| **Quality flags** | `is_estimated` (bool), `restated` (bool), `data_completeness` (0–1) |

**Unit conventions (binding):**
- Ratios / margins / yields / growth are **decimal fractions** — `0.182`, **not** `18.2`. The UI formats `%`.
- Absolute monetary values are in **true `currency` units** — not thousands or millions.
- Missing = `null`. `0` means a real zero.

### 3.1 `kap-scraper` provider specifics (fundamental)

What this BIST/KAP implementation actually emits (verified against real served envelopes — §6.5.1):

| Field | Generic enum (§3) | **Value emitted by this provider** |
|---|---|---|
| `provider` | any | `kap-scraper` (same as sentiment) |
| `period` | ISO date | `"YYYY"` (annual) or `"YYYY-Qn"` (interim) — the KAP reporting period, **not** a calendar date |
| `fiscal_period` | `FY2025 \| Q1-2026 \| TTM` | `"annual"` or `"interim"` |
| `currency` | ISO-4217 | `"TRY"` |
| `reporting_standard` | `IFRS \| US-GAAP` | `"TFRS"` (Turkish IFRS) |

- **Nulls are omitted, not sent.** Unlike §3's "send `null`", the served payload **drops** any metric it
  could not compute — a **missing key means `null`**. (`is_estimated`/`restated` are always present.)
- **Price multiples and per-share metrics require out-of-band market data.** `pe_ratio`, `pb_ratio`,
  `ps_ratio`, `ev_ebitda`, `peg_ratio`, `dividend_yield` are computed only when a `{price, shares_outstanding}`
  pair is supplied to the scrape. A **default KAP-only scrape omits all of them**; it yields statement-derived
  metrics (margins, returns, leverage, liquidity, `revenue`/`ebitda`/`net_income`/`free_cash_flow`, YoY growth)
  plus `eps`/`book_value_per_share` when a share count is known.
- **Per-share provenance.** When no market `shares_outstanding` is given, the analyzer uses paid-in capital
  ("Ödenmiş Sermaye") as the share count. This equals true shares only for a 1-TRY nominal value, so
  `eps`/`book_value_per_share` may be off for other nominals — prefer supplying explicit market data.
- `data_completeness` is the filled fraction of the 17 statement-only ratio fields (price multiples excluded),
  so a complete statement scores near `1.0` even with no market data.
- `ebitda` is derived as operating profit (or EBIT) + depreciation/amortisation; `free_cash_flow` as
  operating cash flow − |capex|; `net_debt` as total interest-bearing debt − cash.
- **Source & parsing.** Facts come from the KAP financial-report **disclosure page** scraped via Firecrawl
  and parsed by `kap_financial_parser.parse_financial_table_markdown`, which keys on the statement's
  **English XBRL labels** (e.g. `Revenue`, `Profit (Loss)`, `Total current assets`) for unambiguous
  mapping. (The legacy `.xlsx` path is kept as a fallback but KAP currently 404s it.)
- **Unit caveat.** Absolute monetary fields (`revenue`, `ebitda`, `net_income`, `free_cash_flow`) are
  emitted in the **statement's native unit — KAP files in thousand TRY**, so e.g. `revenue: 120205594`
  means ≈120.2 bn TRY. Ratios, margins and **per-share** values (`eps`, `book_value_per_share`) are
  unit-invariant (numerator and share count share the unit) and therefore correct as-is. A consumer that
  needs true-TRY absolutes should ×1000. (This is a known deviation from §3's "true currency units".)

---

## 3.2 News payload (`kind = "news"`)

Platform-level KAP/SPK/MKK/BIST announcements — regulatory/system news that affects whole sectors or the
market, **not** company disclosures. These are addressed by `news_id` / `category`, **not** by `instrument`.

| Field | Type | Req | Meaning |
|---|---|---|---|
| `news_id` | string | ✓ | Stable id for the item (KAP id, or a content-hash for scraped items) |
| `category` | string | ✓ | Source/category — `SPK \| MKK \| BIST \| KAP \| …` |
| `title` | string | ✓ | Headline |
| `content` | string | – | Body text (omitted when empty) |
| `source_url` | string | – | Origin URL on KAP |
| `sentiment` | object | – | Present only when the item has been NLP-scored: `{overall_sentiment, score (−1..+1), confidence (0..1), analyzer?}` |

The wrapping envelope carries `kind:"news"`, `provider:"kap-scraper"`, `source:"external-db"`, `as_of`
(the publish date), `freshness_seconds`, and `status`. List responses wrap items as `{as_of, payload}`
(same shape as `history`).

---

## 4. Endpoint surface

`{base}` = your service root (configured on our side as `SENTIMENT_API_INTERNAL_URL` /
`FUNDAMENTAL_API_INTERNAL_URL`). `{kind}` ∈ `sentiment | fundamental`.

| Purpose | Method + path | Notes |
|---|---|---|
| **Point** | `GET {base}/{kind}/{instrument}?market=&as_of=` | `as_of` omitted → latest. Returns one envelope |
| **Batch** | `POST {base}/{kind}/batch` — body `{market, instruments[], as_of?}` | Returns `{contract_version, items: Envelope[]}`. Per-item `status` allows **partial** |
| **History** | `GET {base}/{kind}/{instrument}/history?market=&from=&to=&limit=&cursor=` | Time series; cursor pagination (`next_cursor`) |
| **Overview** (sentiment only) | `GET {base}/sentiment/overview?market=&from=&to=` | Distribution + daily trend for the admin overview panel |
| **News list** | `GET {base}/news?category=&from=&to=&limit=&cursor=` | Platform news, newest-first, cursor pagination. **Not** instrument-keyed (no `market`) |
| **News point** | `GET {base}/news/{news_id}` | One news item by its `news_id` |
| **Health** | `GET {base}/health` | `{status, contract_version}` for the connectivity/freshness badge |

**`kap-scraper` surface (as mounted at `/api/external/v1`):** all rows above are implemented for
`{kind} = sentiment`; `point`, `batch`, and `history` are also implemented for `{kind} = fundamental`.
There is **no `fundamental/overview`** (overview is sentiment-only). The two `news` routes serve the
platform-news `kind` (§3.2). `health` reports `{status, contract_version, provider:"kap-scraper"}`.

### 4.1 Client quick-start — live `kap-scraper` calls & **real responses**

> Everything below was captured from the running service (FastAPI). Use this as the client integration
> reference. `market=bist` only (§0); other markets return `unavailable`.

- **Base URL** `{base}` = `http://<host>:8000/api/external/v1` (uvicorn listens on `0.0.0.0:8000`;
  router mounted at `/api/external/v1`). Locally: `http://localhost:8000/api/external/v1`.
- **Interactive docs (Swagger):** `http://localhost:8000/docs` — try every endpoint from the browser.
- **Auth:** none today (CORS is open `*`). Do not expose publicly without a gateway.
- **Content type:** JSON. `instrument` is the BIST ticker (upper-cased), `market` is a required query enum.

**Running the service (provider side).** The DB defaults (`localhost:5432`, db/user `backtofuture`) are
wired in `config.py`, so only Postgres and the app need to be up:
```bash
# 1) Postgres (the app's own DB — separate from Firecrawl's queue DB)
pg_ctlcluster 15 main start            # or: service postgresql start

# 2) API server — from the project dir, using its venv
cd projects/turkish_financial
FIRECRAWL_BASE_URL=http://localhost:3002 \
  .venv/bin/python -m uvicorn api.main:app --host 0.0.0.0 --port 8000
# tables auto-create on first boot; visit http://localhost:8000/docs
```
Override the DB target with env vars if needed: `APP_DB_HOST`, `APP_DB_PORT`, `APP_DB_NAME`,
`APP_DB_USER`, `APP_DB_PASSWORD`, `DB_SCHEMA` (default schema `turkish_financial`).

**Reaching it as a client:** just `GET`/`POST` the `{base}` URLs in §4.1(1–6) — no key, no handshake.
A smoke test:
```bash
curl http://localhost:8000/api/external/v1/health
# {"status":"ok","contract_version":"1.0","provider":"kap-scraper"}
```

> **Data note.** Endpoints only return `ok` for instruments present in the DB. With live KAP reachable,
> rows arrive via the scrape pipeline (`KAPScraper.scrape_and_save_disclosures` / `scrape_financial_statements`).
> KAP is anti-bot-protected, so from a bare server context those scrapes can yield zero rows and every
> instrument then returns `200` + `status:"unavailable"` until data is ingested.

**Status / error semantics (important — differs from a naive reading of §5):**

| Situation | HTTP | Body |
|---|---|---|
| Data found | `200` | full envelope, `status:"ok"` |
| No data / unknown ticker / non-`bist` market | **`200`** | envelope with `status:"unavailable"`, `payload:null`, `as_of:null` |
| Invalid query param (e.g. bad `market`) | **`422`** | FastAPI validation body `{"detail":[…]}` — **not** the contract error envelope |
| DB / infrastructure failure | `503` | contract error envelope `{contract_version,status:"unavailable",error_code,detail}` (§6.7) |

So a client must treat **`200` + `status:"unavailable"`** (not an HTTP error) as "no data", and validate inputs
to avoid `422`.

**1) Health**
```bash
curl -s "{base}/health"
# {"status":"ok","contract_version":"1.0","provider":"kap-scraper"}
```

**2) Point — latest sentiment for one instrument**
```bash
curl -s "{base}/sentiment/THYAO?market=bist"
```
```json
{
  "contract_version": "1.0", "instrument": "THYAO", "market": "bist", "kind": "sentiment",
  "as_of": "2026-06-14T08:15:00Z", "provider": "kap-scraper", "source": "external-db",
  "freshness_seconds": 33543, "status": "ok",
  "payload": {
    "overall_sentiment": "positive", "score": 0.78, "confidence": 0.78,
    "key_drivers": ["traffic_growth", "fuel_cost_decline"], "risk_flags": ["fx_exposure"],
    "tone_descriptors": ["optimistic", "forward_looking"], "impact_horizon": "medium_term",
    "risk_level": "medium", "sample_size": 1, "analyzer": "huggingface"
  }
}
```
Add `&as_of=2026-06-13T23:59:59Z` to get the latest point at/<= that instant.

**3) Batch — many instruments at once** (per-item `status`; here `SISE` resolves but has no stored data)
```bash
curl -s -X POST "{base}/sentiment/batch" \
  -H 'Content-Type: application/json' \
  -d '{"market":"bist","instruments":["THYAO","GARAN","SISE"]}'
```
```json
{
  "contract_version": "1.0",
  "items": [
    { "instrument": "THYAO", "status": "ok",
      "payload": { "overall_sentiment": "positive", "score": 0.78, "confidence": 0.78, "...": "…" } },
    { "instrument": "GARAN", "status": "ok",
      "payload": { "overall_sentiment": "negative", "score": -0.71, "confidence": 0.71,
                   "risk_flags": ["regulatory_pressure","asset_quality"], "risk_level": "high" } },
    { "instrument": "SISE", "as_of": null, "status": "unavailable", "payload": null }
  ]
}
```
(Each item is a full envelope; trimmed above for brevity. Note `negative` → `score` is **negative**.)

**4) History — time series, cursor-paginated**
```bash
curl -s "{base}/sentiment/THYAO/history?market=bist&from=2026-06-01&to=2026-06-15&limit=50"
```
```json
{
  "contract_version": "1.0", "instrument": "THYAO", "market": "bist", "kind": "sentiment",
  "items": [
    { "as_of": "2026-06-13T08:00:00Z",
      "payload": { "overall_sentiment": "positive", "score": 0.75, "confidence": 0.75,
                   "key_drivers": ["traffic_growth","capacity_expansion"], "risk_level": "medium" } },
    { "as_of": "2026-06-12T08:00:00Z",
      "payload": { "overall_sentiment": "positive", "score": 0.72, "confidence": 0.72,
                   "key_drivers": ["traffic_growth"], "risk_level": "low" } }
  ],
  "next_cursor": null
}
```
Items are newest-first. When `next_cursor` is non-null, pass it back as `&cursor=<value>` for the next page.
**Date gotcha:** `from`/`to` compare against the full timestamp, and a bare `to=YYYY-MM-DD` is **midnight UTC**,
so it **excludes** that day's later entries — pass the next day (or an ISO datetime) to include "today".

**5) Overview — distribution + daily trend (sentiment only)**
```bash
curl -s "{base}/sentiment/overview?market=bist&from=2026-06-01&to=2026-06-30"
```
```json
{
  "contract_version": "1.0", "market": "bist",
  "period": { "from": "2026-06-01", "to": "2026-06-30" },
  "summary": {
    "total_analyses": 6, "unique_instruments": 4, "average_confidence": 0.695,
    "distribution": { "positive": 0.6667, "neutral": 0.1667, "negative": 0.1667 }
  },
  "daily_trend": [
    { "date": "2026-06-12", "avg_score": 0.72,   "count": 1, "unique_instruments": 1 },
    { "date": "2026-06-13", "avg_score": 0.75,   "count": 1, "unique_instruments": 1 },
    { "date": "2026-06-14", "avg_score": 0.1825, "count": 4, "unique_instruments": 4 }
  ]
}
```
`distribution` fractions sum to 1; `avg_score` is the mean signed score (direction × confidence) for the day.

**6) Fundamental** uses the same shapes under `/fundamental/...` (point/batch/history; no overview) — see §6.5.1.

**7) News — platform announcements (not instrument-keyed)**
```bash
curl -s "{base}/news?limit=3"                       # newest-first, all categories
curl -s "{base}/news?category=SPK&from=2026-06-10"  # filter by category / date
curl -s "{base}/news/SEED-NEWS-MKK-1"               # one item by news_id
```
```json
{
  "contract_version": "1.0", "kind": "news",
  "items": [
    { "as_of": "2026-06-14T19:07:30Z",
      "payload": { "news_id": "SEED-NEWS-SPK-0", "category": "SPK",
                   "title": "SPK Bülteni: Halka arz onayları açıklandı",
                   "content": "…", "source_url": "https://www.kap.org.tr/tr/duyurular" } },
    { "as_of": "2026-06-13T19:07:30Z",
      "payload": { "news_id": "SEED-NEWS-MKK-1", "category": "MKK",
                   "title": "MKK: Genel kurul e-oylama takvimi güncellendi", "content": "…" } }
  ],
  "next_cursor": "2026-06-12T19:07:30Z"
}
```
No `market` param (platform news is market-wide). When an item has been NLP-scored, its `payload.sentiment`
carries `{overall_sentiment, score, confidence, analyzer}`. Same `from`/`to` midnight-UTC gotcha as history.

---

## 5. Cross-cutting rules (binding)

- **Informational only.** No buy/sell/hold, price targets, or position sizing in **any** field. Our
  adapter rejects/strips unknown or directive fields (platform compliance Gate 1).
- **Own your DB.** We pull over HTTP only; we never receive a DB handle and never share a schema.
- **Nulls, not zeros.** Missing data is `null`.
- **Errors.** Use standard HTTP status. Error body:
  `{contract_version, status:"unavailable", error_code, detail}`. On any failure we degrade to an honest
  empty/error state — we never fabricate data.
- **Pagination.** Cursor-based (`next_cursor`) on `history`.
- **Versioning.** Additive changes keep `1.0`. Any field removal/rename → `2.0`; we negotiate on
  `contract_version`. Always send `contract_version` so we can detect drift.

---

## 6. Concrete examples

### 6.1 Sentiment — point query

**Request**
```
GET {base}/sentiment/THYAO?market=bist
```
**Response `200`**
```json
{
  "contract_version": "1.0",
  "instrument": "THYAO",
  "market": "bist",
  "kind": "sentiment",
  "as_of": "2026-06-14T08:15:00Z",
  "provider": "kap-scraper",
  "source": "external-db",
  "freshness_seconds": 1840,
  "status": "ok",
  "payload": {
    "overall_sentiment": "positive",
    "score": 0.62,
    "confidence": 0.78,
    "impact_horizon": "medium_term",
    "key_drivers": ["traffic_growth", "fuel_cost_decline"],
    "risk_flags": ["fx_exposure"],
    "risk_level": "medium",
    "tone_descriptors": ["optimistic", "forward_looking"],
    "sample_size": 12,
    "analyzer": "llm:gemini-1.5"
  }
}
```

### 6.2 Sentiment — batch

**Request**
```
POST {base}/sentiment/batch
Content-Type: application/json

{ "market": "usa", "instruments": ["AAPL", "MSFT", "NVDA"] }
```
**Response `200`** (note the per-item `partial`)
```json
{
  "contract_version": "1.0",
  "items": [
    {
      "contract_version": "1.0", "instrument": "AAPL", "market": "usa", "kind": "sentiment",
      "as_of": "2026-06-14T09:00:00Z", "provider": "news-nlp", "source": "external-db",
      "freshness_seconds": 600, "status": "ok",
      "payload": { "overall_sentiment": "neutral", "score": 0.05, "confidence": 0.55,
                   "key_drivers": [], "risk_flags": [], "sample_size": 30, "analyzer": "huggingface" }
    },
    {
      "contract_version": "1.0", "instrument": "MSFT", "market": "usa", "kind": "sentiment",
      "as_of": "2026-06-14T09:00:00Z", "provider": "news-nlp", "source": "external-db",
      "freshness_seconds": 600, "status": "ok",
      "payload": { "overall_sentiment": "positive", "score": 0.41, "confidence": 0.66,
                   "key_drivers": ["cloud_growth"], "risk_flags": [], "sample_size": 22, "analyzer": "huggingface" }
    },
    {
      "contract_version": "1.0", "instrument": "NVDA", "market": "usa", "kind": "sentiment",
      "as_of": null, "provider": "news-nlp", "source": "external-db",
      "freshness_seconds": 0, "status": "partial", "payload": null
    }
  ]
}
```

### 6.3 Sentiment — history

**Request**
```
GET {base}/sentiment/THYAO/history?market=bist&from=2026-05-01&to=2026-06-14&limit=3
```
**Response `200`**
```json
{
  "contract_version": "1.0",
  "instrument": "THYAO", "market": "bist", "kind": "sentiment",
  "items": [
    { "as_of": "2026-06-12T08:00:00Z", "payload": { "overall_sentiment": "positive", "score": 0.58, "confidence": 0.72, "sample_size": 9 } },
    { "as_of": "2026-06-13T08:00:00Z", "payload": { "overall_sentiment": "positive", "score": 0.60, "confidence": 0.75, "sample_size": 11 } },
    { "as_of": "2026-06-14T08:00:00Z", "payload": { "overall_sentiment": "positive", "score": 0.62, "confidence": 0.78, "sample_size": 12 } }
  ],
  "next_cursor": null
}
```

### 6.4 Sentiment — overview

**Request**
```
GET {base}/sentiment/overview?market=bist&from=2026-05-15&to=2026-06-14
```
**Response `200`**
```json
{
  "contract_version": "1.0",
  "market": "bist",
  "period": { "from": "2026-05-15", "to": "2026-06-14" },
  "summary": {
    "total_analyses": 1840,
    "unique_instruments": 312,
    "average_confidence": 0.69,
    "distribution": { "positive": 0.46, "neutral": 0.33, "negative": 0.21 }
  },
  "daily_trend": [
    { "date": "2026-06-12", "avg_score": 0.21, "count": 142, "unique_instruments": 120 },
    { "date": "2026-06-13", "avg_score": 0.24, "count": 138, "unique_instruments": 118 },
    { "date": "2026-06-14", "avg_score": 0.27, "count": 96,  "unique_instruments": 88 }
  ]
}
```

### 6.5 Fundamental — point query

**Request**
```
GET {base}/fundamental/AAPL?market=usa
```
**Response `200`**
```json
{
  "contract_version": "1.0",
  "instrument": "AAPL",
  "market": "usa",
  "kind": "fundamental",
  "as_of": "2026-05-02T00:00:00Z",
  "provider": "fundamentals-svc",
  "source": "external-db",
  "freshness_seconds": 86400,
  "status": "ok",
  "payload": {
    "period": "2026-03-29",
    "fiscal_period": "Q2-2026",
    "currency": "USD",
    "reporting_standard": "US-GAAP",
    "pe_ratio": 31.4, "pb_ratio": 48.2, "ps_ratio": 8.1, "ev_ebitda": 24.7, "peg_ratio": 2.6,
    "eps": 1.53, "book_value_per_share": 4.10, "dividend_per_share": 0.25, "dividend_yield": 0.0048,
    "gross_margin": 0.461, "operating_margin": 0.302, "net_margin": 0.252,
    "roe": 1.48, "roa": 0.29, "roic": 0.56,
    "debt_to_equity": 1.52, "net_debt_to_ebitda": 0.6, "current_ratio": 0.94,
    "quick_ratio": 0.88, "interest_coverage": 28.5,
    "revenue": 95800000000, "ebitda": 31200000000, "net_income": 24160000000,
    "free_cash_flow": 22100000000, "revenue_growth_yoy": 0.051, "eps_growth_yoy": 0.078,
    "is_estimated": false, "restated": false, "data_completeness": 0.97
  }
}
```

### 6.5.1 Fundamental — actual `kap-scraper` output (BIST)

Real envelope served by this provider for a BIST instrument (representative ASELS figures, market data
supplied so multiples are present). Note `provider:"kap-scraper"`, `currency:"TRY"`,
`reporting_standard:"TFRS"`, `fiscal_period:"annual"`, `period:"2024"`, and that **absent metrics are
omitted** rather than sent as `null` (here `interest_coverage`, `dividend_per_share`).

**Request** `GET {base}/fundamental/ASELS?market=bist` → **Response `200`**
```json
{
  "contract_version": "1.0",
  "instrument": "ASELS",
  "market": "bist",
  "kind": "fundamental",
  "as_of": "2026-06-14T17:22:16Z",
  "provider": "kap-scraper",
  "source": "external-db",
  "freshness_seconds": 0,
  "status": "ok",
  "payload": {
    "period": "2024",
    "fiscal_period": "annual",
    "currency": "TRY",
    "reporting_standard": "TFRS",
    "pe_ratio": 11.2637, "pb_ratio": 2.5702, "ps_ratio": 3.1137, "ev_ebitda": 12.9455, "peg_ratio": 0.28,
    "eps": 5.5044, "book_value_per_share": 24.1228,
    "gross_margin": 0.3943, "operating_margin": 0.2247, "net_margin": 0.2764,
    "roe": 0.2282, "roa": 0.1249, "roic": 0.136,
    "debt_to_equity": 0.3636, "net_debt_to_ebitda": 0.9149,
    "current_ratio": 1.7143, "quick_ratio": 1.1286,
    "revenue": 90800000000.0, "ebitda": 23500000000.0, "net_income": 25100000000.0,
    "free_cash_flow": 16000000000.0, "revenue_growth_yoy": 0.4413, "eps_growth_yoy": 0.4023,
    "data_completeness": 0.9412, "is_estimated": false, "restated": false
  }
}
```

> A **default KAP-only scrape** (no market data) omits the five price multiples and `dividend_yield`,
> emitting just the statement-derived metrics + `eps`/`book_value_per_share` (see §3.1).

### 6.6 Fundamental — history (one metric over fiscal periods)

**Request**
```
GET {base}/fundamental/AAPL/history?market=usa&from=2025-01-01&to=2026-06-14&limit=4
```
**Response `200`**
```json
{
  "contract_version": "1.0",
  "instrument": "AAPL", "market": "usa", "kind": "fundamental",
  "items": [
    { "as_of": "2025-08-01T00:00:00Z", "payload": { "fiscal_period": "Q3-2025", "eps": 1.40, "net_margin": 0.246, "revenue": 90800000000 } },
    { "as_of": "2025-11-01T00:00:00Z", "payload": { "fiscal_period": "Q4-2025", "eps": 1.46, "net_margin": 0.249, "revenue": 94900000000 } },
    { "as_of": "2026-02-01T00:00:00Z", "payload": { "fiscal_period": "Q1-2026", "eps": 2.18, "net_margin": 0.261, "revenue": 124300000000 } },
    { "as_of": "2026-05-02T00:00:00Z", "payload": { "fiscal_period": "Q2-2026", "eps": 1.53, "net_margin": 0.252, "revenue": 95800000000 } }
  ],
  "next_cursor": null
}
```

### 6.7 Error / unavailable

Two distinct cases (see the §4.1 status table):

- **No data / unknown ticker / non-`bist` market** → **HTTP `200`** with `status:"unavailable"`, `payload:null`
  (e.g. `GET {base}/sentiment/AAPL?market=usa` or `GET {base}/sentiment/ZZZZZ?market=bist`).
- **DB / infrastructure failure** → **HTTP `503`** with the contract error envelope. The `kap-scraper`
  provider emits `error_code: "UPSTREAM_DB_ERROR"`:

**Response `503`**
```json
{
  "contract_version": "1.0",
  "status": "unavailable",
  "error_code": "UPSTREAM_DB_ERROR",
  "detail": "database temporarily unavailable"
}
```

> Invalid query params (e.g. an unsupported `market`) are rejected **before** this layer with FastAPI's
> standard **`422`** `{"detail":[…]}` validation body — that is *not* the contract error envelope.

### 6.8 Health

**Request** `GET {base}/health` → **Response `200`**
```json
{ "status": "ok", "contract_version": "1.0", "provider": "kap-scraper" }
```

> `status` is `"ok"` when the DB check passes, `"degraded"` otherwise (health never raises).

### 6.9 Sentiment — actual `kap-scraper` output (BIST)

Real envelope served by this provider. Note `provider:"kap-scraper"` and that `score == confidence`
(positive sign): this provider always derives `score = sign × confidence` rather than publishing an
independent magnitude (§2.1).

**Request** `GET {base}/sentiment/THYAO?market=bist` → **Response `200`**
```json
{
  "contract_version": "1.0",
  "instrument": "THYAO",
  "market": "bist",
  "kind": "sentiment",
  "as_of": "2026-06-14T17:22:16Z",
  "provider": "kap-scraper",
  "source": "external-db",
  "freshness_seconds": 0,
  "status": "ok",
  "payload": {
    "overall_sentiment": "positive",
    "score": 0.78,
    "confidence": 0.78,
    "key_drivers": ["traffic_growth", "fuel_cost_decline"],
    "risk_flags": ["fx_exposure"],
    "tone_descriptors": ["optimistic"],
    "impact_horizon": "medium_term",
    "risk_level": "medium",
    "sample_size": 1,
    "analyzer": "huggingface"
  }
}
```

### 6.10 News — actual `kap-scraper` output

Real point envelope (`GET {base}/news/SEED-NEWS-MKK-1`). News items are addressed by `news_id`, carry no
`instrument`/`market`, and expose an optional `payload.sentiment` block when NLP-scored.

**Response `200`**
```json
{
  "contract_version": "1.0",
  "kind": "news",
  "news_id": "SEED-NEWS-MKK-1",
  "as_of": "2026-06-13T19:07:30Z",
  "provider": "kap-scraper",
  "source": "external-db",
  "freshness_seconds": 86570,
  "status": "ok",
  "payload": {
    "news_id": "SEED-NEWS-MKK-1",
    "category": "MKK",
    "title": "MKK: Genel kurul e-oylama takvimi güncellendi",
    "content": "Merkezi Kayıt Kuruluşu elektronik genel kurul takvimini yayımladı.",
    "source_url": "https://www.kap.org.tr/tr/duyurular"
  }
}
```

A missing `news_id` returns the same shape with `status:"unavailable"`, `payload:null` (HTTP `200`).

---

## 7. TypeScript / Pydantic shapes (reference)

These mirror the tables above; the web side lands in `src/types/api/external-analysis.types.ts`, the
backend in `app/domain/entities/external_analysis.py`.

```ts
type Market = 'bist' | 'usa' | 'coin';
type Kind = 'sentiment' | 'fundamental' | 'news';
type ProviderStatus = 'ok' | 'partial' | 'unavailable';

interface ProviderEnvelope<P> {
  contract_version: string;
  instrument: string;
  market: Market;
  kind: Kind;
  as_of: string | null;
  provider: string;
  source: 'external-db';
  freshness_seconds: number;
  status: ProviderStatus;
  payload: P | null;
}

// News is platform-wide: keyed by news_id, no instrument/market.
interface NewsEnvelope {
  contract_version: string;
  kind: 'news';
  news_id: string;
  as_of: string | null;
  provider: string;
  source: 'external-db';
  freshness_seconds: number;
  status: ProviderStatus;
  payload: NewsPayload | null;
}

interface NewsPayload {
  news_id: string;
  category: string;              // SPK | MKK | BIST | KAP | …
  title: string;
  content?: string;
  source_url?: string;
  sentiment?: {                  // present only when NLP-scored
    overall_sentiment: 'positive' | 'neutral' | 'negative';
    score: number;               // -1..+1
    confidence: number;          // 0..1
    analyzer?: string;
  };
}

interface NewsListResponse {
  contract_version: string;
  kind: 'news';
  items: { as_of: string | null; payload: NewsPayload }[];
  next_cursor: string | null;
}

interface SentimentPayload {
  overall_sentiment: 'positive' | 'neutral' | 'negative';
  score: number;                 // -1..+1
  confidence: number;            // 0..1
  impact_horizon?: 'short_term' | 'medium_term' | 'long_term';
  key_drivers?: string[];
  risk_flags?: string[];
  risk_level?: 'low' | 'medium' | 'high';
  tone_descriptors?: string[];
  sample_size?: number;
  analyzer?: string;
}

interface FundamentalPayload {
  period: string;                // ISO date
  fiscal_period?: string;        // FY2025 | Q1-2026 | TTM
  currency?: string;             // ISO-4217
  reporting_standard?: 'IFRS' | 'US-GAAP';
  pe_ratio?: number | null; pb_ratio?: number | null; ps_ratio?: number | null;
  ev_ebitda?: number | null; peg_ratio?: number | null;
  eps?: number | null; book_value_per_share?: number | null;
  dividend_per_share?: number | null; dividend_yield?: number | null;
  gross_margin?: number | null; operating_margin?: number | null; net_margin?: number | null;
  roe?: number | null; roa?: number | null; roic?: number | null;
  debt_to_equity?: number | null; net_debt_to_ebitda?: number | null;
  current_ratio?: number | null; quick_ratio?: number | null; interest_coverage?: number | null;
  revenue?: number | null; ebitda?: number | null; net_income?: number | null; free_cash_flow?: number | null;
  revenue_growth_yoy?: number | null; eps_growth_yoy?: number | null;
  is_estimated?: boolean; restated?: boolean; data_completeness?: number | null;
}
```
