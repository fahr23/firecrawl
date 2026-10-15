-- Disclosures stored by the old HTML list scraper under synthetic ids
-- (live_kap_<time>_<n>, live_kap_div_..., demo_kap_...): no KAP index, no ticker,
-- the same disclosure re-inserted every run, company cells run together. They
-- can't be linked to an instrument; their sentiment rows go with them
-- (kap_disclosure_sentiment.disclosure_id ON DELETE CASCADE).
DELETE FROM kap_disclosures
WHERE disclosure_id LIKE 'live\_kap\_%' OR disclosure_id LIKE 'demo\_kap\_%';
