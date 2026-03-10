-- Add supported_languages column to widget_configs
-- JSON array of language codes, e.g. '["en", "ne"]'
-- NULL or empty means single language (no toggle shown)
ALTER TABLE widget_configs
ADD COLUMN IF NOT EXISTS supported_languages TEXT DEFAULT NULL;
