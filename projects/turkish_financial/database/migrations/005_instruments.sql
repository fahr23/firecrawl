-- Instrument master: one row per (market, code), the identity every fact table
-- points to. Seeded from the BIST catalogue; instruments seen first in source
-- data (KAP covers ~90 issuers outside BIST TÜM, USA tickers, coin ids) are
-- created on first sight by instrument_id_for().
CREATE TABLE IF NOT EXISTS instruments (
    id              BIGSERIAL PRIMARY KEY,
    market          TEXT NOT NULL CHECK (market IN ('bist', 'usa', 'coin')),
    code            TEXT NOT NULL CHECK (code <> ''),
    name            TEXT,
    sector          TEXT,
    kap_member_oid  TEXT,
    in_bist_catalog BOOLEAN NOT NULL DEFAULT FALSE,
    active          BOOLEAN NOT NULL DEFAULT TRUE,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (market, code)
);

-- Codes are upper-case except CoinGecko ids, which are lower-case slugs.
CREATE OR REPLACE FUNCTION normalize_instrument_code(p_market TEXT, p_code TEXT)
RETURNS TEXT LANGUAGE sql IMMUTABLE AS $$
    SELECT CASE WHEN p_market = 'coin' THEN lower(btrim(p_code)) ELSE upper(btrim(p_code)) END
$$;

-- The id for (market, code), creating the instrument on first sight.
CREATE OR REPLACE FUNCTION instrument_id_for(p_market TEXT, p_code TEXT)
RETURNS BIGINT LANGUAGE plpgsql SET search_path FROM CURRENT AS $$
DECLARE
    v_code TEXT := normalize_instrument_code(p_market, p_code);
    v_id   BIGINT;
BEGIN
    IF v_code IS NULL OR v_code = '' THEN
        RETURN NULL;
    END IF;
    SELECT id INTO v_id FROM instruments WHERE market = p_market AND code = v_code;
    IF v_id IS NULL THEN
        INSERT INTO instruments (market, code) VALUES (p_market, v_code)
        ON CONFLICT (market, code) DO UPDATE SET code = EXCLUDED.code
        RETURNING id INTO v_id;
    END IF;
    RETURN v_id;
END
$$;

INSERT INTO instruments (market, code, name, sector, kap_member_oid, in_bist_catalog, active)
SELECT 'bist', normalize_instrument_code('bist', code), name, sector, mkk_member_oid, TRUE, COALESCE(is_active, TRUE)
FROM bist_companies
WHERE code IS NOT NULL AND btrim(code) <> ''
ON CONFLICT (market, code) DO UPDATE SET
    name = EXCLUDED.name, sector = EXCLUDED.sector,
    kap_member_oid = COALESCE(EXCLUDED.kap_member_oid, instruments.kap_member_oid),
    in_bist_catalog = TRUE, active = EXCLUDED.active, updated_at = now();

-- bist_companies stays the catalogue's write target (startup seed, OID
-- resolution); mirror every change into the master.
CREATE OR REPLACE FUNCTION sync_instrument_from_bist_company()
RETURNS trigger LANGUAGE plpgsql SET search_path FROM CURRENT AS $$
BEGIN
    IF NEW.code IS NULL OR btrim(NEW.code) = '' THEN
        RETURN NEW;
    END IF;
    INSERT INTO instruments (market, code, name, sector, kap_member_oid, in_bist_catalog, active)
    VALUES ('bist', normalize_instrument_code('bist', NEW.code), NEW.name, NEW.sector,
            NEW.mkk_member_oid, TRUE, COALESCE(NEW.is_active, TRUE))
    ON CONFLICT (market, code) DO UPDATE SET
        name = COALESCE(EXCLUDED.name, instruments.name),
        sector = COALESCE(EXCLUDED.sector, instruments.sector),
        kap_member_oid = COALESCE(EXCLUDED.kap_member_oid, instruments.kap_member_oid),
        in_bist_catalog = TRUE, active = EXCLUDED.active, updated_at = now();
    RETURN NEW;
END
$$;

DROP TRIGGER IF EXISTS trg_bist_companies_sync_instrument ON bist_companies;
CREATE TRIGGER trg_bist_companies_sync_instrument
    AFTER INSERT OR UPDATE ON bist_companies
    FOR EACH ROW EXECUTE FUNCTION sync_instrument_from_bist_company();
