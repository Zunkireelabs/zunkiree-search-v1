-- SBAL-Z4: the clinic agent gets a name ("Sammy" for sbal). Nullable,
-- no default, no backfill — tenants without it keep today's generic
-- "<brand>'s AI assistant" / booking-assistant framing (brief §1, §3).

ALTER TABLE widget_configs ADD COLUMN IF NOT EXISTS assistant_name VARCHAR(80) NULL;
