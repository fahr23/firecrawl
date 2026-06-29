# Anti-Bot & Proxy Configuration

**Scope:** Self-hosted Firecrawl deployment. Cloud Firecrawl handles this automatically via the proprietary Fire-engine (IP rotation, residential proxies, TLS spoofing, CAPTCHA bypass).

---

## Problem

Self-hosted Firecrawl blocks are caused by three independent layers:

1. **IP reputation** — datacenter IPs are trivially blocklisted
2. **Browser fingerprint** — stock Playwright leaks `navigator.webdriver = true`
3. **TLS/HTTP-2 fingerprint** — advanced WAFs (Cloudflare UAM, Datadome) fingerprint the TLS handshake

Without Fire-engine (`FIRE_ENGINE_BETA_URL` not set), the self-hosted engine fallback order is:

```
playwright → fetch → pdf → document
```

---

## Solution Levels

| Level | Action | Files | Effort | Solves |
|-------|--------|-------|--------|--------|
| **1** | Set proxy env vars | `apps/api/.env` + `docker-compose.yml` | 5 min | IP bans |
| **2** | Add `--disable-blink-features=AutomationControlled` | `playwright-service-ts/api.ts:196` | 2 min + rebuild | `navigator.webdriver` leak |
| **3** | Install `playwright-extra` + stealth plugin | `playwright-service-ts/api.ts` | 15 min + rebuild | Canvas/WebGL/audio fingerprint |
| **4** | TLS-impersonation sidecar via `FIRE_ENGINE_BETA_URL` | new service | Complex | Cloudflare UAM / HTTP-2 fingerprint |

**Levels 1–3 cover ~80–90% of blocks.** Level 4 is only needed for sites with active Cloudflare Browser Integrity Check.

**For KAP specifically: Levels 1–2 are sufficient.** KAP does not use Cloudflare UAM.

---

## Level 1 — Proxy (IP Rotation)

Proxy support is already coded — it just needs env vars. No patching required.

**How it works** (source reference):
- `fetch` engine: [`engines/utils/safeFetch.ts:23-34`](apps/api/src/scraper/scrapeURL/engines/utils/safeFetch.ts) — uses `undici.ProxyAgent`
- `playwright` engine: [`apps/playwright-service-ts/api.ts:217-227`](apps/playwright-service-ts/api.ts) — injects `proxy` into every `browser.newContext()`

`apps/api/.env`:
```env
PROXY_SERVER=http://your-provider.com:8000
PROXY_USERNAME=user
PROXY_PASSWORD=pass
BLOCK_MEDIA=True    # saves proxy bandwidth
```

> The playwright-service is a **separate container** and reads its own environment. You must set the same vars in `docker-compose.yml`:

```yaml
services:
  playwright-service:
    environment:
      - PROXY_SERVER=http://your-provider.com:8000
      - PROXY_USERNAME=user
      - PROXY_PASSWORD=pass
      - BLOCK_MEDIA=True
```

```bash
docker compose down && docker compose up -d
```

Use a **rotating residential/mobile proxy** (Oxylabs, BrightData, Smartproxy) so the IP changes per request.

---

## Level 2 — Automation Flag Bypass

Removes the `navigator.webdriver = true` signal that Cloudflare/Datadome detect.

Edit [`apps/playwright-service-ts/api.ts:190-200`](apps/playwright-service-ts/api.ts):

```ts
args: [
  '--no-sandbox',
  '--disable-setuid-sandbox',
  '--disable-dev-shm-usage',
  '--disable-accelerated-2d-canvas',
  '--no-first-run',
  '--no-zygote',
  '--disable-gpu',
  '--disable-blink-features=AutomationControlled'   // ADD THIS
]
```

Rebuild: `docker compose build playwright-service && docker compose up -d playwright-service`

---

## Level 3 — Stealth Plugin (Canvas/WebGL Fingerprint)

```bash
cd apps/playwright-service-ts
npm install playwright-extra puppeteer-extra-plugin-stealth
```

Edit [`apps/playwright-service-ts/api.ts`](apps/playwright-service-ts/api.ts) top:

```ts
// Replace:
import { chromium, Browser, BrowserContext, Route, Request as PlaywrightRequest, Page } from 'playwright';

// With:
import { Browser, BrowserContext, Route, Request as PlaywrightRequest, Page } from 'playwright';
import { chromium } from 'playwright-extra';
import stealthPlugin from 'puppeteer-extra-plugin-stealth';
chromium.use(stealthPlugin());
```

Rebuild: `docker compose build playwright-service && docker compose up -d playwright-service`

---

## Level 4 — TLS Impersonation (Advanced)

Only needed for sites with active Cloudflare Browser Integrity Check.

Run a small HTTP service wrapping `curl_cffi` (Python) or `tls-client` (Go) that mimics a real Chrome TLS/HTTP-2 fingerprint, then point `FIRE_ENGINE_BETA_URL` at it. This re-enables the `fire-engine;tlsclient;stealth` engines in Firecrawl's fallback list ([`engines/index.ts:69-78`](apps/api/src/scraper/scrapeURL/engines/index.ts)).

---

## Behavioral Layer (works at any level)

Even with perfect IP and fingerprint, instant DOM extraction gets flagged. Add human-like delays using Firecrawl `actions`:

```json
{
  "url": "https://example.com",
  "actions": [
    { "type": "wait", "milliseconds": 2000 },
    { "type": "scroll", "direction": "down" }
  ]
}
```

The playwright-service already executes these ([`api.ts:449-533`](apps/playwright-service-ts/api.ts)).

---

## KAP-Specific Proxy Config

KAP uses an anti-bot interstitial but not Cloudflare UAM. The scraper tries proxy types in order:

```env
KAP_FIRECRAWL_PROXY=basic,auto,stealth
```

On self-hosted Firecrawl:
- `basic` — works for most KAP requests
- `stealth` — trips `document_antibot` on self-hosted (no stealth driver installed)
- `auto` — fallback

On Firecrawl Cloud:
- `stealth` is usually needed

For high-volume OID resolution (see [KAP_TECHNICAL.md](KAP_TECHNICAL.md)), use Firecrawl Cloud's rotating proxies; self-hosted gets rate-limited during bursts.

---

## Summary

| Problem | Solution |
|---------|----------|
| IP bans | Level 1: proxy env vars (already coded) |
| `navigator.webdriver` | Level 2: `--disable-blink-features` arg |
| Canvas/WebGL fingerprint | Level 3: `playwright-extra` + stealth plugin |
| Cloudflare UAM / TLS | Level 4: `curl_cffi` sidecar |
| Rate-based blocks | Slow crawl: `KAP_PAGE_DELAY_S=4` |
| KAP specifically | Levels 1–2 are sufficient |
