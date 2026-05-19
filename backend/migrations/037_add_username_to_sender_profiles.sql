-- Add Instagram username to sender profile cache.
-- Fetched alongside name so IG customers display as handle when display name is unavailable.

ALTER TABLE chatbot_sender_profiles ADD COLUMN IF NOT EXISTS username TEXT NULL;
