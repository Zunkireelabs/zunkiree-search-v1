-- 009: Lead intents for tenant-aware lead capture
-- Adds lead_intents config, user_type/lead_intent on profiles,
-- detected_intent/intent_signup_fields on verification sessions

ALTER TABLE widget_configs ADD COLUMN IF NOT EXISTS lead_intents TEXT;
ALTER TABLE user_profiles ADD COLUMN IF NOT EXISTS user_type VARCHAR(100);
ALTER TABLE user_profiles ADD COLUMN IF NOT EXISTS lead_intent VARCHAR(100);
ALTER TABLE verification_sessions ADD COLUMN IF NOT EXISTS detected_intent VARCHAR(100);
ALTER TABLE verification_sessions ADD COLUMN IF NOT EXISTS intent_signup_fields TEXT;

-- Prevent duplicate profiles per tenant+email
CREATE UNIQUE INDEX IF NOT EXISTS uq_user_profiles_customer_email
    ON user_profiles (customer_id, email);
