-- 029: Add profile_locked flag to prevent auto-profile from overwriting cloned templates
ALTER TABLE business_profiles ADD COLUMN IF NOT EXISTS profile_locked BOOLEAN NOT NULL DEFAULT FALSE;
