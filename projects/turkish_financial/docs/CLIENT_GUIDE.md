# Client Guide — Consuming the Analysis API

**Service:** `kap-scraper` provider  
**Base URL:** `http://localhost:8000/api/external/v1`  
**Auth:** none (open CORS — do not expose publicly without a gateway)  
**Market scope:** `bist` only — `usa`/`coin` always return `unavailable`  
**Contract version:** `1.0`

Quick smoke test:
```bash
curl -s http://localhost:8000/api/external/v1/health
# {"status":"ok","contract_version":"1.0","provider":"kap-scraper"}
```

Swagger UI (try every endpoint in the browser): `http://localhost:8000/docs`

---

## Response envelope

Every response wraps its data in the same shape:

```json
{
  "contract_version": "1.0",
  "instrument":       "THYAO",
  "market":           "bist",
  "kind":             "sentiment | fundamental | news",
  "as_of":            "2026-06-14T08:15:00Z",
  "provider":         "kap-scraper",
  "source":           "external-db",
  "freshness_seconds": 3600,
  "status":           "ok | partial | unavailable",
  "payload":          { ... }
}
```

**Status rules:**
- `status: "ok"` + `payload: {...}` → data found
- `status: "unavailable"` + `payload: null` → no data for this ticker yet (HTTP **200**, not 4xx)
- HTTP **503** → database/infrastructure failure
- HTTP **422** → bad query param (FastAPI validation error, not the contract envelope)

Always check `status` before reading `payload`.

---

## 0. Discover available instruments (start here)

Call this **before** anything else. It lists every registered company and tells you
exactly which data types are available for each ticker right now.

```bash
curl "http://localhost:8000/api/external/v1/instruments?market=bist"
```

```json
{
  "contract_version": "1.0",
  "market": "bist",
  "total": 20,
  "items": [
    {
      "ticker": "THYAO",
      "company_name": "Türk Hava Yolları A.O.",
      "sector": "Havacılık",
      "market": "bist",
      "available_data": ["sentiment", "fundamental", "news_sentiment", "combined_sentiment"]
    },
    {
      "ticker": "ARCLK",
      "company_name": "Arçelik A.Ş.",
      "sector": "Teknoloji",
      "market": "bist",
      "available_data": []
    }
  ]
}
```

`available_data` tells you exactly which endpoints will return `"status": "ok"` for that ticker:

| `available_data` value | Endpoint |
|------------------------|---------|
| `sentiment` | `GET /sentiment/{ticker}?market=bist` |
| `fundamental` | `GET /fundamental/{ticker}?market=bist` |
| `news_sentiment` | `GET /news-sentiment/{ticker}?market=bist` |
| `combined_sentiment` | `GET /combined-sentiment/{ticker}?market=bist` |

Tickers with `available_data: []` are registered but have no data yet — their endpoints return `"status": "unavailable"`.

**Python — build a picker:**

```python
import requests

BASE = "http://localhost:8000/api/external/v1"

catalog = requests.get(f"{BASE}/instruments", params={"market": "bist"}).json()

# All tickers with any data
available = [i for i in catalog["items"] if i["available_data"]]

# Full-coverage tickers only (sentiment + fundamental + news)
full = [
    i for i in catalog["items"]
    if {"sentiment", "fundamental", "news_sentiment"} <= set(i["available_data"])
]

print("Available tickers:", [i["ticker"] for i in available])
print("Full-coverage:    ", [i["ticker"] for i in full])
```

**TypeScript:**

```typescript
const BASE = "http://localhost:8000/api/external/v1";

interface Instrument {
  ticker: string;
  company_name: string;
  sector: string;
  market: string;
  available_data: string[];
}

async function getInstruments(): Promise<Instrument[]> {
  const res = await fetch(`${BASE}/instruments?market=bist`);
  const data = await res.json();
  return data.items as Instrument[];
}

// Usage
const instruments = await getInstruments();
const withSentiment = instruments.filter(i => i.available_data.includes("sentiment"));
```

---

## 1. Latest sentiment for a ticker

```bash
curl -s "http://localhost:8000/api/external/v1/sentiment/THYAO?market=bist"
```

```json
{
  "contract_version": "1.0",
  "instrument": "THYAO",
  "market": "bist",
  "kind": "sentiment",
  "as_of": "2026-06-14T08:15:00Z",
  "provider": "kap-scraper",
  "source": "external-db",
  "freshness_seconds": 3600,
  "status": "ok",
  "payload": {
    "overall_sentiment": "positive",
    "score":      0.78,
    "confidence": 0.78,
    "impact_horizon": "medium_term",
    "key_drivers": ["traffic_growth", "fuel_cost_decline"],
    "risk_flags":  ["fx_exposure"],
    "risk_level":  "medium",
    "tone_descriptors": ["optimistic"],
    "sample_size": 1,
    "analyzer":    "huggingface"
  }
}
```

**`score`** is `−1.0 … +1.0` (negative = bearish, positive = bullish).  
For this provider `score == confidence` (same number, signed by sentiment direction).

Get sentiment **at a specific point in time**:
```bash
curl -s "http://localhost:8000/api/external/v1/sentiment/THYAO?market=bist&as_of=2026-06-13T23:59:59Z"
```

---

## 2. Latest fundamentals for a ticker

```bash
curl -s "http://localhost:8000/api/external/v1/fundamental/ASELS?market=bist"
```

```json
{
  "contract_version": "1.0",
  "instrument": "ASELS",
  "market": "bist",
  "kind": "fundamental",
  "as_of": "2026-06-14T17:22:16Z",
  "status": "ok",
  "payload": {
    "period":             "2024",
    "fiscal_period":      "annual",
    "currency":           "TRY",
    "reporting_standard": "TFRS",

    "pe_ratio":  11.26,
    "pb_ratio":   2.57,
    "ps_ratio":   3.11,
    "ev_ebitda": 12.95,

    "eps":                   5.50,
    "book_value_per_share": 24.12,

    "gross_margin":     0.394,
    "operating_margin": 0.225,
    "net_margin":       0.276,
    "roe":  0.228,
    "roa":  0.125,
    "roic": 0.136,

    "debt_to_equity":    0.364,
    "current_ratio":     1.714,
    "quick_ratio":       1.129,

    "revenue":         90800000000.0,
    "ebitda":          23500000000.0,
    "net_income":      25100000000.0,
    "free_cash_flow":  16000000000.0,

    "revenue_growth_yoy": 0.4413,
    "eps_growth_yoy":     0.4023,

    "data_completeness": 0.94,
    "is_estimated": false,
    "restated":     false
  }
}
```

**Unit notes:**
- Ratios/margins/growth are **decimal fractions** — `0.394` means 39.4%
- Absolute values (`revenue`, `ebitda`, etc.) are in **thousands of TRY** — multiply by 1000 for true TRY
- Missing fields are **omitted** (absent key = `null`)
- Price multiples (`pe_ratio`, `pb_ratio`, etc.) only appear when market price data was supplied at scrape time

---

## 3. Latest news

Platform-level announcements from KAP/SPK/MKK/BIST — not company-specific disclosures.

```bash
# Newest items (all categories)
curl -s "http://localhost:8000/api/external/v1/news?limit=10"

# Filter by source category
curl -s "http://localhost:8000/api/external/v1/news?category=SPK&limit=10"
curl -s "http://localhost:8000/api/external/v1/news?category=MKK&limit=10"
curl -s "http://localhost:8000/api/external/v1/news?category=BIST&limit=10"

# Filter by date range (newest-first)
curl -s "http://localhost:8000/api/external/v1/news?from=2026-06-01&to=2026-06-30"

# One item by ID
curl -s "http://localhost:8000/api/external/v1/news/SEED-NEWS-MKK-1"
```

```json
{
  "contract_version": "1.0",
  "kind": "news",
  "items": [
    {
      "as_of": "2026-06-14T19:07:30Z",
      "payload": {
        "news_id":    "SEED-NEWS-SPK-0",
        "category":   "SPK",
        "title":      "SPK Bülteni: Halka arz onayları açıklandı",
        "content":    "...",
        "source_url": "https://www.kap.org.tr/tr/duyurular",
        "sentiment": {
          "overall_sentiment": "neutral",
          "score": 0.05,
          "confidence": 0.55,
          "analyzer": "keyword"
        }
      }
    }
  ],
  "next_cursor": "2026-06-12T19:07:30Z"
}
```

`sentiment` inside a news item is present only when the item has been NLP-scored.  
Pass `&cursor=<next_cursor>` to page through older items.

---

## 4. Batch — multiple tickers at once

Efficient for dashboards: one request, many instruments.

```bash
# Batch sentiment
curl -s -X POST "http://localhost:8000/api/external/v1/sentiment/batch" \
  -H "Content-Type: application/json" \
  -d '{"market": "bist", "instruments": ["THYAO", "AKBNK", "GARAN", "ASELS", "EREGL"]}'

# Batch fundamentals
curl -s -X POST "http://localhost:8000/api/external/v1/fundamental/batch" \
  -H "Content-Type: application/json" \
  -d '{"market": "bist", "instruments": ["THYAO", "AKBNK", "ASELS"]}'
```

```json
{
  "contract_version": "1.0",
  "items": [
    {
      "instrument": "THYAO", "status": "ok",
      "payload": { "overall_sentiment": "positive", "score": 0.78, "..." : "..." }
    },
    {
      "instrument": "AKBNK", "status": "ok",
      "payload": { "overall_sentiment": "negative", "score": -0.71, "..." : "..." }
    },
    {
      "instrument": "EREGL", "as_of": null, "status": "unavailable", "payload": null
    }
  ]
}
```

Each item is a full envelope. `status: "unavailable"` on one item does not fail the whole batch.

---

## 5. Sentiment history (time series)

```bash
curl -s "http://localhost:8000/api/external/v1/sentiment/THYAO/history?market=bist&from=2026-06-01&to=2026-06-30&limit=50"
```

```json
{
  "contract_version": "1.0",
  "instrument": "THYAO",
  "market": "bist",
  "kind": "sentiment",
  "items": [
    { "as_of": "2026-06-13T08:00:00Z", "payload": { "overall_sentiment": "positive", "score": 0.75, "confidence": 0.75 } },
    { "as_of": "2026-06-14T08:00:00Z", "payload": { "overall_sentiment": "positive", "score": 0.78, "confidence": 0.78 } }
  ],
  "next_cursor": null
}
```

Items are **newest-first**. When `next_cursor` is non-null, pass it as `&cursor=<value>` for the next page.

**Date gotcha:** `to=2026-06-14` means midnight UTC, so it **excludes** entries from that day. Use `to=2026-06-15` or `to=2026-06-14T23:59:59Z` to include the full day.

---

## 6. Fundamental history

```bash
curl -s "http://localhost:8000/api/external/v1/fundamental/ASELS/history?market=bist&from=2025-01-01&to=2026-12-31"
```

Returns one envelope item per reporting period (annual / quarterly).

---

## 7. Sentiment overview (market-wide)

Distribution and daily trend across all BIST instruments in a date range.

```bash
curl -s "http://localhost:8000/api/external/v1/sentiment/overview?market=bist&from=2026-06-01&to=2026-06-30"
```

```json
{
  "contract_version": "1.0",
  "market": "bist",
  "period": { "from": "2026-06-01", "to": "2026-06-30" },
  "summary": {
    "total_analyses":     6,
    "unique_instruments": 4,
    "average_confidence": 0.695,
    "distribution": { "positive": 0.667, "neutral": 0.167, "negative": 0.167 }
  },
  "daily_trend": [
    { "date": "2026-06-12", "avg_score": 0.72,  "count": 1, "unique_instruments": 1 },
    { "date": "2026-06-13", "avg_score": 0.75,  "count": 1, "unique_instruments": 1 },
    { "date": "2026-06-14", "avg_score": 0.183, "count": 4, "unique_instruments": 4 }
  ]
}
```

`distribution` fractions sum to 1. `avg_score` is the mean signed score for the day.

---

## Python client

```python
import requests

BASE = "http://localhost:8000/api/external/v1"

def get_sentiment(ticker: str) -> dict | None:
    r = requests.get(f"{BASE}/sentiment/{ticker}", params={"market": "bist"})
    r.raise_for_status()
    envelope = r.json()
    return envelope["payload"] if envelope["status"] == "ok" else None

def get_fundamentals(ticker: str) -> dict | None:
    r = requests.get(f"{BASE}/fundamental/{ticker}", params={"market": "bist"})
    r.raise_for_status()
    envelope = r.json()
    return envelope["payload"] if envelope["status"] == "ok" else None

def get_news(category: str = None, limit: int = 20) -> list[dict]:
    params = {"limit": limit}
    if category:
        params["category"] = category
    r = requests.get(f"{BASE}/news", params=params)
    r.raise_for_status()
    return r.json().get("items", [])

def batch_sentiment(tickers: list[str]) -> dict[str, dict | None]:
    r = requests.post(f"{BASE}/sentiment/batch",
                      json={"market": "bist", "instruments": tickers})
    r.raise_for_status()
    return {
        item["instrument"]: item["payload"] if item["status"] == "ok" else None
        for item in r.json()["items"]
    }

def sentiment_history(ticker: str, from_date: str, to_date: str) -> list[dict]:
    params = {"market": "bist", "from": from_date, "to": to_date, "limit": 100}
    items = []
    while True:
        r = requests.get(f"{BASE}/sentiment/{ticker}/history", params=params)
        r.raise_for_status()
        body = r.json()
        items.extend(body.get("items", []))
        if not body.get("next_cursor"):
            break
        params["cursor"] = body["next_cursor"]
    return items


# --- Usage examples ---

# Latest sentiment for one ticker
s = get_sentiment("THYAO")
if s:
    print(f"THYAO: {s['overall_sentiment']} score={s['score']:.2f} drivers={s['key_drivers']}")

# Latest fundamentals
f = get_fundamentals("ASELS")
if f:
    revenue_bn = f["revenue"] / 1_000_000_000_000  # thousands-TRY → trillion TRY
    print(f"ASELS net_margin={f['net_margin']:.1%}  revenue≈{revenue_bn:.1f}T TRY")

# Latest news from SPK
for item in get_news(category="SPK", limit=5):
    print(f"[{item['as_of']}] {item['payload']['title']}")

# Batch sentiment for a watchlist
results = batch_sentiment(["THYAO", "AKBNK", "GARAN", "ASELS", "EREGL"])
for ticker, payload in results.items():
    if payload:
        print(f"{ticker}: {payload['overall_sentiment']} ({payload['score']:+.2f})")
    else:
        print(f"{ticker}: no data")

# Sentiment history with auto-pagination
history = sentiment_history("THYAO", "2026-06-01", "2026-06-30")
for point in history:
    print(f"  {point['as_of']}: score={point['payload']['score']:+.2f}")
```

---

## TypeScript / fetch client

```ts
const BASE = 'http://localhost:8000/api/external/v1';

interface Envelope<P> {
  contract_version: string;
  instrument?: string;
  market?: string;
  kind: string;
  as_of: string | null;
  status: 'ok' | 'partial' | 'unavailable';
  freshness_seconds: number;
  payload: P | null;
}

async function getSentiment(ticker: string) {
  const r = await fetch(`${BASE}/sentiment/${ticker}?market=bist`);
  const env: Envelope<SentimentPayload> = await r.json();
  return env.status === 'ok' ? env.payload : null;
}

async function getFundamentals(ticker: string) {
  const r = await fetch(`${BASE}/fundamental/${ticker}?market=bist`);
  const env: Envelope<FundamentalPayload> = await r.json();
  return env.status === 'ok' ? env.payload : null;
}

async function getNews(opts?: { category?: string; limit?: number }) {
  const params = new URLSearchParams();
  if (opts?.category) params.set('category', opts.category);
  if (opts?.limit)    params.set('limit', String(opts.limit));
  const r = await fetch(`${BASE}/news?${params}`);
  const body = await r.json();
  return body.items as { as_of: string; payload: NewsPayload }[];
}

async function batchSentiment(tickers: string[]) {
  const r = await fetch(`${BASE}/sentiment/batch`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ market: 'bist', instruments: tickers }),
  });
  const body = await r.json();
  return Object.fromEntries(
    body.items.map((item: any) => [item.instrument, item.status === 'ok' ? item.payload : null])
  );
}

// Usage
const s = await getSentiment('THYAO');
if (s) console.log(`THYAO ${s.overall_sentiment} score=${s.score}`);

const f = await getFundamentals('ASELS');
if (f) console.log(`ASELS net_margin=${(f.net_margin * 100).toFixed(1)}%`);

const news = await getNews({ category: 'SPK', limit: 5 });
news.forEach(n => console.log(`[${n.as_of}] ${n.payload.title}`));
```

---

## Field reference

### Sentiment payload fields

| Field | Type | Notes |
|-------|------|-------|
| `overall_sentiment` | `positive \| neutral \| negative` | Direction |
| `score` | `−1.0 … +1.0` | Signed strength; for this provider equals `±confidence` |
| `confidence` | `0.0 … 1.0` | Model confidence |
| `impact_horizon` | `short_term \| medium_term \| long_term` | May be absent |
| `key_drivers` | `string[]` | Positive factors driving the sentiment |
| `risk_flags` | `string[]` | Risk factors identified |
| `risk_level` | `low \| medium \| high` | May be absent |
| `tone_descriptors` | `string[]` | Qualitative tone tags |
| `sample_size` | `integer` | Number of disclosures behind this point |
| `analyzer` | `string` | `keyword \| huggingface \| llm:<model>` |

### Fundamental payload fields

| Group | Fields | Unit |
|-------|--------|------|
| Period | `period`, `fiscal_period`, `currency`, `reporting_standard` | — |
| Valuation | `pe_ratio`, `pb_ratio`, `ps_ratio`, `ev_ebitda`, `peg_ratio` | ratio |
| Per-share | `eps`, `book_value_per_share`, `dividend_per_share`, `dividend_yield` | TRY / fraction |
| Profitability | `gross_margin`, `operating_margin`, `net_margin`, `roe`, `roa`, `roic` | decimal fraction |
| Leverage | `debt_to_equity`, `net_debt_to_ebitda`, `current_ratio`, `quick_ratio`, `interest_coverage` | ratio |
| Scale | `revenue`, `ebitda`, `net_income`, `free_cash_flow` | **thousands of TRY** (×1000 for true TRY) |
| Growth | `revenue_growth_yoy`, `eps_growth_yoy` | decimal fraction |
| Quality | `is_estimated`, `restated`, `data_completeness` | bool / 0–1 |

Missing fields are **omitted** from the response (not sent as `null`).

### News payload fields

| Field | Notes |
|-------|-------|
| `news_id` | Stable ID for the item |
| `category` | `SPK \| MKK \| BIST \| KAP` |
| `title` | Headline |
| `content` | Body text (may be absent) |
| `source_url` | Origin URL on KAP |
| `sentiment` | NLP result block — present only when item has been scored |

---

## 8. News collection schedule

Control **when** news is collected without restarting the server.  
Two modes: `manual` (you trigger it) or `interval` (auto-runs every N minutes).

### 8a. Read current schedule

```bash
curl "http://localhost:8000/api/external/v1/news-sentiment/schedule"
```

```json
{
  "contract_version": "1.0",
  "mode": "manual",
  "interval_minutes": 30,
  "sources": ["bloomberght", "mynetfinans"],
  "days_back": 1,
  "include_investing_comments": false,
  "is_running": false,
  "last_run": "2026-06-29T08:12:04Z",
  "next_run": null,
  "last_result": {
    "scraped": 18,
    "saved": 11,
    "analyzed": 11,
    "triggered_at": "2026-06-29T08:12:04Z"
  }
}
```

`next_run` is `null` in manual mode and set to a future timestamp in interval mode.

### 8b. Switch to interval mode (auto-collect)

```bash
curl -s -X POST "http://localhost:8000/api/external/v1/news-sentiment/schedule" \
  -H "Content-Type: application/json" \
  -d '{"mode":"interval","interval_minutes":60,"sources":["bloomberght"],"days_back":1}'
```

```json
{
  "contract_version": "1.0",
  "ok": true,
  "message": "Scheduler set to interval mode — runs every 60 min",
  "mode": "interval",
  "interval_minutes": 60,
  "next_run": "2026-06-29T09:15:00Z",
  ...
}
```

### 8c. Switch back to manual mode

```bash
curl -s -X POST "http://localhost:8000/api/external/v1/news-sentiment/schedule" \
  -H "Content-Type: application/json" \
  -d '{"mode":"manual"}'
```

### Schedule body parameters

| Field | Type | Default | Notes |
|-------|------|---------|-------|
| `mode` | `"manual"` \| `"interval"` | required | switches mode immediately |
| `interval_minutes` | int 5–1440 | `30` | ignored in manual mode |
| `sources` | list[str] | `["bloomberght","mynetfinans"]` | portal source keys |
| `days_back` | int 1–30 | `1` | how far back each run looks |

### Python example

```python
import requests

BASE = "http://localhost:8000/api/external/v1"

def get_schedule():
    return requests.get(f"{BASE}/news-sentiment/schedule").json()

def set_interval(every_minutes: int = 30):
    return requests.post(f"{BASE}/news-sentiment/schedule", json={
        "mode": "interval",
        "interval_minutes": every_minutes,
        "sources": ["bloomberght", "mynetfinans"],
        "days_back": 1,
    }).json()

def set_manual():
    return requests.post(f"{BASE}/news-sentiment/schedule", json={"mode": "manual"}).json()

# Example: run every hour
set_interval(60)

# Check when the next run is scheduled
sched = get_schedule()
print(f"Next auto-collect: {sched['next_run']}")
print(f"Last run result:   {sched['last_result']}")
```

### TypeScript example

```typescript
const BASE = "http://localhost:8000/api/external/v1";

async function getSchedule() {
  const res = await fetch(`${BASE}/news-sentiment/schedule`);
  return res.json();
}

async function setSchedule(mode: "manual" | "interval", intervalMinutes = 30) {
  const res = await fetch(`${BASE}/news-sentiment/schedule`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ mode, interval_minutes: intervalMinutes }),
  });
  return res.json();
}

// Switch to hourly auto-collect
await setSchedule("interval", 60);

// Poll schedule state
const sched = await getSchedule();
console.log("Last result:", sched.last_result);
console.log("Is collecting now:", sched.is_running);
```

---

## 9. YouTube channel sentiment

Sentiment derived from Turkish finance YouTube channels (e.g. `@bistyatirimcipsikolojisi`).
Videos are discovered via yt-dlp, transcripts fetched via youtube-transcript-api, and each
video is scored **per BIST ticker mentioned** — so one video can contribute to multiple tickers.
Results feed the same `aggregated_ticker_sentiment` rollup as news and social sentiment.

The `combined-sentiment` endpoint already blends YouTube into its score automatically once
you collect it.

### 9a. Trigger a collection run

```bash
curl -s -X POST "http://localhost:8000/api/external/v1/youtube-sentiment/collect" \
  -H "Content-Type: application/json" \
  -d '{
    "channels": ["https://www.youtube.com/@bistyatirimcipsikolojisi/videos"],
    "days_back": 7,
    "limit_per_channel": 50
  }'
```

```json
{
  "contract_version": "1.0",
  "success": true,
  "scraped": 12,
  "analyzed": 34,
  "saved": 34,
  "aggregated_tickers": 8,
  "by_channel": {
    "https://www.youtube.com/@bistyatirimcipsikolojisi/videos": 12
  }
}
```

| Field | Notes |
|-------|-------|
| `scraped` | Videos fetched that had a transcript |
| `analyzed` | Sentiment calls made (≥ `scraped` because each video can mention many tickers) |
| `saved` | Per-(video, ticker) sentiment rows persisted |
| `aggregated_tickers` | Daily rollup rows updated |
| `by_channel` | Video count per channel URL |

When `channels` is omitted the service uses its configured seed list
(`YOUTUBE_CHANNELS` env var, defaulting to `@bistyatirimcipsikolojisi`).

### 9b. Latest YouTube sentiment for a ticker

```bash
curl -s "http://localhost:8000/api/external/v1/youtube-sentiment/THYAO?market=bist"
```

```json
{
  "contract_version": "1.0",
  "instrument": "THYAO",
  "market": "bist",
  "kind": "sentiment",
  "as_of": "2026-06-29T00:00:00Z",
  "provider": "youtube-scraper",
  "source": "external-db",
  "freshness_seconds": 7200,
  "status": "ok",
  "payload": {
    "overall_sentiment": "positive",
    "score": 0.62,
    "confidence": 0.62,
    "analyzer": "youtube-scraper",
    "sample_size": 4
  }
}
```

`sample_size` is the number of (video, ticker) sentiment rows that fed the daily aggregate.

### 9c. YouTube sentiment history

```bash
curl -s "http://localhost:8000/api/external/v1/youtube-sentiment/THYAO/history?market=bist&from=2026-06-01&to=2026-06-30&limit=30"
```

Response shape is identical to `/sentiment/{ticker}/history` — cursor-paginated, newest-first.

### 9d. Schedule automatic collection

```bash
# Read current schedule
curl "http://localhost:8000/api/external/v1/youtube-sentiment/schedule"

# Switch to hourly auto-collect
curl -s -X POST "http://localhost:8000/api/external/v1/youtube-sentiment/schedule" \
  -H "Content-Type: application/json" \
  -d '{
    "mode": "interval",
    "interval_minutes": 60,
    "channels": ["https://www.youtube.com/@bistyatirimcipsikolojisi/videos"],
    "days_back": 7,
    "limit_per_channel": 50
  }'

# Switch back to manual
curl -s -X POST "http://localhost:8000/api/external/v1/youtube-sentiment/schedule" \
  -H "Content-Type: application/json" \
  -d '{"mode": "manual"}'
```

Schedule body parameters:

| Field | Type | Default | Notes |
|-------|------|---------|-------|
| `mode` | `"manual"` \| `"interval"` | required | switches immediately |
| `interval_minutes` | int 5–1440 | `60` | ignored in manual mode |
| `channels` | list[str] | seed list | channel URLs to scrape |
| `days_back` | int 1–30 | `7` | look-back window per run |
| `limit_per_channel` | int 1–200 | `50` | max videos per channel |

### Python example

```python
import requests

BASE = "http://localhost:8000/api/external/v1"

def collect_youtube(channels=None, days_back=7):
    payload = {"days_back": days_back, "limit_per_channel": 50}
    if channels:
        payload["channels"] = channels
    r = requests.post(f"{BASE}/youtube-sentiment/collect", json=payload)
    r.raise_for_status()
    return r.json()

def get_youtube_sentiment(ticker: str) -> dict | None:
    r = requests.get(f"{BASE}/youtube-sentiment/{ticker}", params={"market": "bist"})
    r.raise_for_status()
    envelope = r.json()
    return envelope["payload"] if envelope["status"] == "ok" else None

def youtube_sentiment_history(ticker: str, from_date: str, to_date: str) -> list[dict]:
    params = {"market": "bist", "from": from_date, "to": to_date, "limit": 100}
    items = []
    while True:
        r = requests.get(f"{BASE}/youtube-sentiment/{ticker}/history", params=params)
        r.raise_for_status()
        body = r.json()
        items.extend(body.get("items", []))
        if not body.get("next_cursor"):
            break
        params["cursor"] = body["next_cursor"]
    return items

def set_youtube_schedule(mode="interval", every_minutes=60, channels=None, days_back=7):
    payload = {"mode": mode, "interval_minutes": every_minutes, "days_back": days_back}
    if channels:
        payload["channels"] = channels
    r = requests.post(f"{BASE}/youtube-sentiment/schedule", json=payload)
    r.raise_for_status()
    return r.json()


# --- Usage examples ---

# One-shot collection from the default seed channel
result = collect_youtube(days_back=7)
print(f"Scraped {result['scraped']} videos → {result['aggregated_tickers']} ticker-days updated")

# Collect from a specific channel
result = collect_youtube(
    channels=["https://www.youtube.com/@bistyatirimcipsikolojisi/videos"],
    days_back=14,
)

# Latest YouTube-derived sentiment for THYAO
yt = get_youtube_sentiment("THYAO")
if yt:
    print(f"THYAO YouTube: {yt['overall_sentiment']} score={yt['score']:+.2f}")

# Full YouTube history for the month
history = youtube_sentiment_history("THYAO", "2026-06-01", "2026-06-30")
for point in history:
    print(f"  {point['as_of']}: score={point['payload']['score']:+.2f}")

# Schedule hourly auto-collection
set_youtube_schedule(mode="interval", every_minutes=60, days_back=7)
```

### TypeScript example

```typescript
const BASE = "http://localhost:8000/api/external/v1";

async function collectYouTube(channels?: string[], daysBack = 7) {
  const res = await fetch(`${BASE}/youtube-sentiment/collect`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ channels, days_back: daysBack, limit_per_channel: 50 }),
  });
  return res.json();
}

async function getYouTubeSentiment(ticker: string) {
  const res = await fetch(`${BASE}/youtube-sentiment/${ticker}?market=bist`);
  const env = await res.json();
  return env.status === "ok" ? env.payload : null;
}

async function setYouTubeSchedule(
  mode: "manual" | "interval",
  intervalMinutes = 60,
  channels?: string[],
) {
  const res = await fetch(`${BASE}/youtube-sentiment/schedule`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ mode, interval_minutes: intervalMinutes, channels }),
  });
  return res.json();
}

// Usage
const result = await collectYouTube(
  ["https://www.youtube.com/@bistyatirimcipsikolojisi/videos"],
  7,
);
console.log(`Scraped ${result.scraped} videos → ${result.aggregated_tickers} ticker-days updated`);

const yt = await getYouTubeSentiment("THYAO");
if (yt) console.log(`THYAO YouTube: ${yt.overall_sentiment} score=${yt.score}`);

// Hourly auto-collection
await setYouTubeSchedule("interval", 60);
```

---

## Common patterns

**Is the service fresh?**
```python
env = requests.get(f"{BASE}/sentiment/THYAO", params={"market": "bist"}).json()
stale_threshold = 24 * 3600  # 24 hours
is_stale = env["freshness_seconds"] > stale_threshold
```

**Loop over all tickers in a watchlist:**
```python
WATCHLIST = ["THYAO", "AKBNK", "GARAN", "ASELS", "EREGL", "KCHOL", "BIMAS"]
results = batch_sentiment(WATCHLIST)
bullish = [t for t, p in results.items() if p and p["overall_sentiment"] == "positive"]
bearish = [t for t, p in results.items() if p and p["overall_sentiment"] == "negative"]
```

**Build a simple dashboard row:**
```python
def dashboard_row(ticker: str) -> str:
    s = get_sentiment(ticker)
    f = get_fundamentals(ticker)
    sentiment_str = f"{s['overall_sentiment']} ({s['score']:+.2f})" if s else "n/a"
    pe_str        = f"PE {f['pe_ratio']:.1f}"                       if f and f.get("pe_ratio") else "PE n/a"
    margin_str    = f"NM {f['net_margin']:.1%}"                     if f and f.get("net_margin") else ""
    return f"{ticker:<8} {sentiment_str:<25} {pe_str:<12} {margin_str}"

for ticker in WATCHLIST:
    print(dashboard_row(ticker))
```
