# External analysis data contract

Use `projects/turkish_financial/docs/data_contract_v1.md` as the detailed source, then
verify behavior with contract tests because prose and implementation can drift.

## Common envelope

External analysis responses carry:

- `contract_version`
- `instrument`
- `market`
- `kind`
- `as_of`
- `provider`
- `source`
- `freshness_seconds`
- `status`
- `payload`

Keep `contract_version: "1.0"` for compatible changes, `source: "external-db"`, and
status `ok | partial | unavailable`. The provider supports `market=bist`; unsupported
markets must return `unavailable`.

## Instrument identity

Use `instrument + market` as the public identity. Resolve BIST tickers through
`infrastructure/contracts/instrument_identity_map.py` using persisted mappings first,
then static mappings, then limited name-pattern fallback. Expand mappings additively
and test both detection and resolution.

## Sentiment

- `overall_sentiment`: positive, neutral, or negative.
- `score`: signed value in `[-1, 1]`.
- `confidence`: value in `[0, 1]`.
- `key_drivers`, `risk_flags`, and `tone_descriptors`: arrays.
- Missing source data: `unavailable`, not fabricated neutral data.

`SentimentAnalysis.to_score()` returns signed confidence. Some collection paths then
multiply by confidence again. Treat signed-confidence-squared as an explicit product
decision to test and document, not an accidental invariant.

The configured base blend currently uses news `0.6`, social `0.4`, and YouTube `0.25`,
then renormalizes present sources. With all present, effective weights are
`0.48/0.32/0.20`. Update code, provider identifiers, tests, and docs together when
changing it.

Decide and test whether `provider` names the configured algorithm or only sources that
actually contributed. The current combined path can label the analyzer/provider
`news+social+youtube` even when a source is absent. Likewise, `abs(combined_score)` is
sent as confidence in some paths; net sentiment magnitude is not automatically a
well-founded confidence measure.

## Fundamentals

Store canonical statement facts separately from computed ratios. Missing values remain
null/absent; zero means a real zero.

Provider-specific values currently include:

- provider `kap-scraper`;
- currency `TRY`;
- reporting standard `TFRS`;
- period `YYYY` or `YYYY-Qn`;
- fiscal period `annual` or `interim`.

Price multiples require price and shares outstanding. Without market data, serve only
statement-derived values.

KAP absolutes are currently interpreted in the statement's native thousand-TRY unit,
which differs from the generic true-currency-unit contract. Do not silently rescale or
relabel historical rows. Introduce explicit unit provenance plus a migration and
compatibility decision.

## Routes

Primary routes are mounted at `/api/external/v1` and cover sentiment, fundamentals,
regulatory news, portal news, social, combined, and YouTube point/history/collection
surfaces. Legacy routes remain under `/api/v1` and `/api/sentiment`.

Any field removal, rename, or semantic change requires contract negotiation. Additive
fields may remain v1 only when consumers tolerate them.
