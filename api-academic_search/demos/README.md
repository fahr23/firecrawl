# Demos

Interactive demonstration scripts for the academic search features.

## Scripts

### firecrawl_actions_demo.py
Demonstrates Firecrawl API with browser automation actions:
- Navigate to search engines
- Type search queries
- Click, scroll, wait actions
- Take screenshots
- Extract links from results

**Usage:**
```bash
python firecrawl_actions_demo.py
```
**Output:** Screenshot saved to `screenshots/`, links saved to `results/misc/`

---

### sciencedirect_demo.py
Demonstrates searching academic content via Bing as a workaround for ScienceDirect's bot protection.

**Usage:**
```bash
python sciencedirect_demo.py
```
**Note:** Direct ScienceDirect access is blocked by Cloudflare; uses Bing site-search.

## Requirements
- Firecrawl API running locally (`docker compose up`)
- `firecrawl-py` SDK installed
