-- 008: User profiles and identity signup flow
-- Creates user_profiles table, adds signup columns to verification_sessions,
-- and adds identity_custom_fields to widget_configs.

-- User profiles table (one per email per tenant)
CREATE TABLE IF NOT EXISTS user_profiles (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    customer_id UUID NOT NULL REFERENCES customers(id) ON DELETE CASCADE,
    email VARCHAR(255) NOT NULL,
    name VARCHAR(255) NOT NULL,
    custom_fields TEXT,  -- JSON object of tenant-defined fields
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW(),
    UNIQUE (customer_id, email)
);

CREATE INDEX IF NOT EXISTS idx_user_profiles_customer_email
    ON user_profiles (customer_id, email);

-- Verification session columns for signup flow
ALTER TABLE verification_sessions
    ADD COLUMN IF NOT EXISTS user_name VARCHAR(255),
    ADD COLUMN IF NOT EXISTS pending_custom_fields TEXT,
    ADD COLUMN IF NOT EXISTS current_field_index INTEGER DEFAULT 0;

-- Widget config column for tenant-defined custom signup fields
ALTER TABLE widget_configs
    ADD COLUMN IF NOT EXISTS identity_custom_fields TEXT;
