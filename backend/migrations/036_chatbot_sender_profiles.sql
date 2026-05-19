-- Cache of Meta-fetched profile data per platform sender.
-- Populated lazily on first DM; refreshed if name is null (fetch previously failed).

CREATE TABLE IF NOT EXISTS chatbot_sender_profiles (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    channel_id UUID NOT NULL REFERENCES chatbot_channels(id) ON DELETE CASCADE,
    platform_sender_id VARCHAR(255) NOT NULL,
    name VARCHAR(255),
    profile_pic_url TEXT,
    fetched_at TIMESTAMPTZ,
    fetch_failed_at TIMESTAMPTZ,
    fetch_error TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT chatbot_sender_profiles_unique UNIQUE (channel_id, platform_sender_id)
);

CREATE INDEX IF NOT EXISTS idx_chatbot_sender_profiles_channel_sender
    ON chatbot_sender_profiles (channel_id, platform_sender_id);
