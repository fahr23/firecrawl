-- One typed daily price table for every market, replacing three JSONB-blob
-- tables. Old names stay readable as views producing the exact old JSON shape,
-- so existing readers keep working; the old tables are kept as *_legacy.
--
-- volume   = units traded (shares, coins)
-- turnover = value traded, in `currency`
CREATE TABLE IF NOT EXISTS market_daily (
    instrument_id             BIGINT NOT NULL REFERENCES instruments(id),
    trading_date              DATE NOT NULL,
    open                      DOUBLE PRECISION,
    high                      DOUBLE PRECISION,
    low                       DOUBLE PRECISION,
    close                     DOUBLE PRECISION,
    vwap                      DOUBLE PRECISION,
    volume                    DOUBLE PRECISION,
    turnover                  DOUBLE PRECISION,
    market_cap                DOUBLE PRECISION,
    free_float_market_cap     DOUBLE PRECISION,
    shares_outstanding        DOUBLE PRECISION,
    currency                  TEXT NOT NULL,
    usd_rate                  DOUBLE PRECISION,
    close_usd                 DOUBLE PRECISION,
    market_cap_usd            DOUBLE PRECISION,
    free_float_market_cap_usd DOUBLE PRECISION,
    index_value               DOUBLE PRECISION,
    source                    TEXT NOT NULL,
    fetched_at                TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (instrument_id, trading_date)
);
-- Cross-sectional reads ("every instrument on date D"); BRIN stays tiny as the
-- table grows because rows arrive roughly in date order.
CREATE INDEX IF NOT EXISTS idx_market_daily_date_brin ON market_daily USING brin (trading_date);

INSERT INTO market_daily (instrument_id, trading_date, close, high, low, vwap, turnover, market_cap,
                          free_float_market_cap, shares_outstanding, currency, usd_rate, close_usd,
                          market_cap_usd, free_float_market_cap_usd, index_value, source, fetched_at)
SELECT instrument_id_for('bist', ticker), market_date,
       (data->>'close_try')::float8, (data->>'high_try')::float8, (data->>'low_try')::float8,
       (data->>'average_price_try')::float8, (data->>'volume_try')::float8, (data->>'market_cap_try')::float8,
       (data->>'free_float_market_cap_try')::float8, (data->>'shares_outstanding')::float8, 'TRY',
       (data->>'usd_try')::float8, (data->>'close_usd')::float8, (data->>'market_cap_usd')::float8,
       (data->>'free_float_market_cap_usd')::float8, (data->>'index_value')::float8, 'isyatirim', fetched_at
FROM isyatirim_market_history
ON CONFLICT (instrument_id, trading_date) DO NOTHING;

INSERT INTO market_daily (instrument_id, trading_date, open, high, low, close, volume, currency, source, fetched_at)
SELECT instrument_id_for('usa', ticker), market_date,
       (data->>'open')::float8, (data->>'high')::float8, (data->>'low')::float8, (data->>'close')::float8,
       (data->>'volume')::float8, 'USD', 'yahoo', fetched_at
FROM yahoo_market_history
ON CONFLICT (instrument_id, trading_date) DO NOTHING;

INSERT INTO market_daily (instrument_id, trading_date, close, market_cap, turnover, currency, source, fetched_at)
SELECT instrument_id_for('coin', coin_id), market_date,
       (data->>'close')::float8, (data->>'market_cap')::float8, (data->>'volume')::float8, 'USD', 'coingecko', fetched_at
FROM coingecko_market_history
ON CONFLICT (instrument_id, trading_date) DO NOTHING;

ALTER TABLE isyatirim_market_history RENAME TO isyatirim_market_history_legacy;
ALTER TABLE yahoo_market_history RENAME TO yahoo_market_history_legacy;
ALTER TABLE coingecko_market_history RENAME TO coingecko_market_history_legacy;

CREATE VIEW isyatirim_market_history AS
SELECT i.code AS ticker, d.trading_date AS market_date,
       jsonb_build_object(
           'trading_date', to_char(d.trading_date, 'DD-MM-YYYY'),
           'close_try', d.close, 'high_try', d.high, 'low_try', d.low,
           'average_price_try', d.vwap, 'volume_try', d.turnover,
           'market_cap_try', d.market_cap, 'free_float_market_cap_try', d.free_float_market_cap,
           'shares_outstanding', d.shares_outstanding, 'usd_try', d.usd_rate, 'close_usd', d.close_usd,
           'market_cap_usd', d.market_cap_usd, 'free_float_market_cap_usd', d.free_float_market_cap_usd,
           'index_value', d.index_value
       ) AS data,
       d.fetched_at
FROM market_daily d JOIN instruments i ON i.id = d.instrument_id
WHERE i.market = 'bist';

CREATE VIEW yahoo_market_history AS
SELECT i.code AS ticker, d.trading_date AS market_date,
       jsonb_build_object('trading_date', to_char(d.trading_date, 'YYYY-MM-DD'),
                          'open', d.open, 'high', d.high, 'low', d.low, 'close', d.close, 'volume', d.volume) AS data,
       d.fetched_at
FROM market_daily d JOIN instruments i ON i.id = d.instrument_id
WHERE i.market = 'usa';

CREATE VIEW coingecko_market_history AS
SELECT i.code AS coin_id, d.trading_date AS market_date,
       jsonb_build_object('trading_date', to_char(d.trading_date, 'YYYY-MM-DD'),
                          'close', d.close, 'market_cap', d.market_cap, 'volume', d.turnover) AS data,
       d.fetched_at
FROM market_daily d JOIN instruments i ON i.id = d.instrument_id
WHERE i.market = 'coin';
