# Documentation Index

All documentation for the Turkish Financial Data Scraper is in the `docs/` directory.

---

## Getting Started

| Document | Purpose |
|----------|---------|
| [QUICK_START_GUIDE.md](QUICK_START_GUIDE.md) | Up and running in 5 minutes |
| [SETUP.md](SETUP.md) | Full setup: Docker, Python env, DB schema, env vars |
| [USER_GUIDE.md](USER_GUIDE.md) | Comprehensive usage guide (all features) |
| [FEATURES_OVERVIEW.md](FEATURES_OVERVIEW.md) | What the system can do |

## API

| Document | Purpose |
|----------|---------|
| [CLIENT_GUIDE.md](CLIENT_GUIDE.md) | **Consuming the API as a client** — instruments catalog, schedule control, curl + Python + TypeScript examples for sentiment, fundamentals, news, batch, history |
| [API_REFERENCE.md](API_REFERENCE.md) | Full endpoint reference: scrapers, reports, KAP sentiment, fundamentals, news, news-portal sentiment (collect + schedule), social sentiment, combined sentiment, proposed roadmap endpoints |

## Sentiment Analysis

| Document | Purpose |
|----------|---------|
| [SENTIMENT.md](SENTIMENT.md) | Analyzers, endpoints, PDF content, cost optimization, HuggingFace setup |

## Technical Reference

| Document | Purpose |
|----------|---------|
| [ARCHITECTURE.md](ARCHITECTURE.md) | DDD layers, data flow, DB schema, SOLID principles |
| [KAP_TECHNICAL.md](KAP_TECHNICAL.md) | KAP API internals, OID resolution, financial statements |
| [ANTI_BOT.md](ANTI_BOT.md) | Proxy setup, stealth levels, self-hosted vs Cloud |
| [data_contract_v1.md](data_contract_v1.md) | External provider data contract spec (sentiment + fundamental) |

## Testing & Operations

| Document | Purpose |
|----------|---------|
| [OPERATIONS.md](OPERATIONS.md) | **Start, restart, stop the server; read logs; fix common bugs** |
| [TESTING_GUIDE.md](TESTING_GUIDE.md) | Running tests (domain, application, integration) |
| [TROUBLESHOOTING.md](TROUBLESHOOTING.md) | KAP blocking, empty tables, DB issues, common errors |
| [CHANGELOG.md](CHANGELOG.md) | Version history |

---

## Quick Navigation

**I want to set up the project** → [SETUP.md](SETUP.md)

**I want to see which tickers have data** → [CLIENT_GUIDE.md](CLIENT_GUIDE.md) → Section 0 (instruments catalog)

**I want to control when news is collected** → [CLIENT_GUIDE.md](CLIENT_GUIDE.md) → Section 8 (schedule) or [API_REFERENCE.md](API_REFERENCE.md) → `GET/POST /news-sentiment/schedule`

**I want to see the full list of endpoints** → [API_REFERENCE.md](API_REFERENCE.md) → External Analysis API v1

**I want to suggest or plan new endpoints** → [API_REFERENCE.md](API_REFERENCE.md) → Proposed Endpoints (Roadmap)

**I want to call the API** → [API_REFERENCE.md](API_REFERENCE.md)

**I want to run sentiment analysis** → [SENTIMENT.md](SENTIMENT.md)

**KAP is returning zero records** → [TROUBLESHOOTING.md](TROUBLESHOOTING.md) → [ANTI_BOT.md](ANTI_BOT.md)

**I need to understand the KAP API internals** → [KAP_TECHNICAL.md](KAP_TECHNICAL.md)

**I need to understand the architecture** → [ARCHITECTURE.md](ARCHITECTURE.md)

**I'm building an external sentiment/fundamental provider** → [data_contract_v1.md](data_contract_v1.md)
