-- Last KAP financial-statement collection attempt per ticker. The collection queue
-- orders by "last collected", and a ticker that never yields a statement (no
-- member OID, no table, unknown unit) has none, so without this it took a slot at
-- the head of every daily run forever and starved the rest of the universe.
CREATE TABLE IF NOT EXISTS kap_fundamental_attempts (
    stock_code      VARCHAR(20) PRIMARY KEY,
    last_attempt_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    last_outcome    VARCHAR(40) NOT NULL
);
