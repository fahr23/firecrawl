-- Every timestamp column becomes timestamptz.
--
-- Verified 2026-10-15 before writing this: the Postgres server and the API pods
-- both run in UTC, CURRENT_TIMESTAMP defaults and datetime.now()/utcnow() writes
-- are therefore UTC, aware datetimes were normalised to UTC on insert, and no
-- source-parsed column (news/YouTube/KAP news/social) holds future or
-- Istanbul-shifted values. So every stored value is UTC wall time and is
-- reinterpreted as such: no value changes, only its type.
DO $$
DECLARE
    col record;
BEGIN
    FOR col IN
        SELECT table_name, column_name
        FROM information_schema.columns
        WHERE table_schema = current_schema()
          AND data_type = 'timestamp without time zone'
        ORDER BY table_name, column_name
    LOOP
        EXECUTE format(
            'ALTER TABLE %I ALTER COLUMN %I TYPE timestamptz USING %I AT TIME ZONE ''UTC''',
            col.table_name, col.column_name, col.column_name
        );
    END LOOP;
END
$$;
