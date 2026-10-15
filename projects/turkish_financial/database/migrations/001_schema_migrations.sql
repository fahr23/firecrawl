-- Marks the start of versioned migrations. The tables that existed before this
-- point are created by DatabaseManager (the baseline); every schema change from
-- here on is a numbered file in this directory, applied once by `python -m database.migrate`.
SELECT 1;
