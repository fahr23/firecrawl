# FA-15 — Investment-fund holdings spike report

**Status:** Feasibility not yet determined. This is a scoping document, not a
go/no-go — the spike itself (checking TEFAS/KAP fund portfolio-distribution
disclosures) has not been run.

## What the spike asks

Per the requirements doc (§FA-15): spike on funds' portfolio-distribution
disclosures (KAP / TEFAS) — coverage, publication frequency, publication lag,
and terms of use. If feasible, build the `fund_holdings` kind:
`{fund_code, instrument, report_date, published_at, shares_held, weight_pct}`.

## Why this wasn't run in this session

TEFAS (Turkey Electronic Fund Trading Platform, tefas.gov.tr) is a separate
public data source this provider does not currently integrate with at all —
no scraper, no adapter, nothing in `scrapers/` touches it today. Running the
spike means:

- fetching TEFAS's actual fund-comparison/portfolio pages (or its data API,
  if one exists publicly) to see what portfolio-distribution data it exposes
  per fund and at what frequency/lag,
- separately checking whether KAP's own disclosure feed carries fund
  portfolio-distribution notices (funds are KAP-listed issuers too, so some
  disclosure types may apply), and
- reading TEFAS's terms of use to confirm scraping/storing its data is
  permitted — this is a legal/compliance check, not something to assume.

None of that live inspection or terms-of-use reading happened in this working
session. As with FA-14, producing a fabricated "coverage is X%, lag is Y days"
finding without having actually looked at TEFAS would misrepresent the spike's
result.

## What is already known, not guessed

- This provider has no existing TEFAS integration, so FA-15 would be new
  end-to-end work (adapter + schema + scraper), not an extension of an
  existing pipeline — unlike FA-14, which could potentially reuse the KAP
  disclosure-page scrape path.
- TEFAS is a known, real, publicly-browsable Turkish platform (not something
  that needs inventing), so the spike is about site structure and terms, not
  about whether the data exists at all.
- The target consumer (per provider-wait-list §5) is "fund liquidity
  fragility research" (F14) — a lower-priority feature than the families
  FA-06/FA-07/FA-11 unblock, consistent with this being the lowest-priority
  item (a "Spike, any time, early is better" row, not gating any M1–M3
  milestone).

## What running the spike actually requires

1. Browse tefas.gov.tr's public fund-comparison / fund-detail pages (or find
   whether TEFAS publishes a documented data API) and identify where
   portfolio-distribution-by-instrument data is shown per fund.
2. Check a handful of funds across types (equity, debt, mixed) for how
   current/stale the shown distribution is — this determines `published_at`
   and lag.
3. Read TEFAS's terms of use / robots.txt for any restriction on automated
   access or redistribution of the data; flag anything ambiguous for an
   explicit owner decision rather than proceeding on an assumption.
4. Separately check whether KAP's `memberDisclosureQuery` subject-code
   taxonomy includes a fund-portfolio-disclosure type this provider's
   existing disclosure scraper could already be picking up without a
   dedicated TEFAS integration.

## Recommendation

Do not build the `fund_holdings` kind or any TEFAS adapter yet. This is the
lowest-priority, least-connected-to-existing-infrastructure item in the
requirements doc; treat it as genuinely optional until someone runs the
TEFAS/KAP inspection above and confirms both feasibility and terms-of-use
clearance.
