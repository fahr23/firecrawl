-- Indexes matched to the API's reads.

-- kap_disclosures.disclosure_id had two identical unique indexes: the table's
-- UNIQUE constraint (used by ON CONFLICT) and a partial copy. Keep the constraint.
DROP INDEX IF EXISTS idx_kap_disclosures_disclosure_id;

-- Per-ticker disclosure history, newest first (replaces the stock_code-only index).
DROP INDEX IF EXISTS idx_kap_disclosures_stock_code;
CREATE INDEX IF NOT EXISTS idx_kap_disclosures_stock_date
    ON kap_disclosures (stock_code, disclosure_date DESC);

-- Fundamental point-in-time reads filter by ticker and order by
-- COALESCE(available_at, published_at, effective_at); index exactly that
-- (replaces the stock_code-only index).
DROP INDEX IF EXISTS idx_fundamentals_stock_code;
CREATE INDEX IF NOT EXISTS idx_fundamentals_pit
    ON kap_fundamentals (stock_code, (COALESCE(available_at, published_at, effective_at)) DESC);

-- Events: dividends / earnings calendar filter by ticker + type, newest first.
CREATE INDEX IF NOT EXISTS idx_kap_events_stock_type_published
    ON kap_events (stock_code, event_type, published_at DESC);
