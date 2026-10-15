-- instrument_id (FK -> instruments) on every per-instrument fact table.
-- Existing writers keep writing their code column; a BEFORE trigger fills
-- instrument_id from it, so integrity is enforced without touching each writer.

-- Fills NEW.instrument_id from the code column named in TG_ARGV[1], for the
-- market in TG_ARGV[0].
CREATE OR REPLACE FUNCTION set_instrument_id()
RETURNS trigger LANGUAGE plpgsql SET search_path FROM CURRENT AS $$
BEGIN
    NEW.instrument_id := instrument_id_for(TG_ARGV[0], to_jsonb(NEW) ->> TG_ARGV[1]);
    RETURN NEW;
END
$$;

DO $$
DECLARE
    t RECORD;
BEGIN
    FOR t IN SELECT * FROM (VALUES
        ('kap_disclosures',               'bist', 'stock_code'),
        ('kap_events',                    'bist', 'stock_code'),
        ('kap_fundamentals',              'bist', 'stock_code'),
        ('kap_financial_statements',      'bist', 'stock_code'),
        ('stock_classification_history',  'bist', 'stock_code'),
        ('index_membership_history',      'bist', 'stock_code'),
        ('corporate_actions',             'bist', 'ticker'),
        ('isyatirim_ownership_history',   'bist', 'ticker'),
        ('isyatirim_fundamentals',        'bist', 'ticker'),
        ('isyatirim_fundamental_periods', 'bist', 'ticker'),
        ('aggregated_ticker_sentiment',   'bist', 'ticker'),
        ('news_articles',                 'bist', 'ticker'),
        ('youtube_video_sentiment',       'bist', 'ticker'),
        ('social_media_posts',            'bist', 'ticker')
    ) AS v(tbl, market, code_col)
    LOOP
        EXECUTE format('ALTER TABLE %I ADD COLUMN IF NOT EXISTS instrument_id BIGINT REFERENCES instruments(id)', t.tbl);
        EXECUTE format(
            'UPDATE %I SET instrument_id = instrument_id_for(%L, %I) WHERE %I IS NOT NULL AND instrument_id IS NULL',
            t.tbl, t.market, t.code_col, t.code_col);
        EXECUTE format('CREATE INDEX IF NOT EXISTS %I ON %I (instrument_id)', 'idx_' || t.tbl || '_instrument', t.tbl);
        EXECUTE format('DROP TRIGGER IF EXISTS %I ON %I', 'trg_' || t.tbl || '_instrument', t.tbl);
        EXECUTE format(
            'CREATE TRIGGER %I BEFORE INSERT OR UPDATE OF %I ON %I FOR EACH ROW EXECUTE FUNCTION set_instrument_id(%L, %L)',
            'trg_' || t.tbl || '_instrument', t.code_col, t.tbl, t.market, t.code_col);
    END LOOP;
END
$$;
