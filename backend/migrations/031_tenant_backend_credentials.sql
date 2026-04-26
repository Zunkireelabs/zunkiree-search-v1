-- Per-tenant backend credentials (Stella sync key, webhook signing secret).
-- Each customer can have at most one row per backend_type. Sync key secret is
-- Fernet-encrypted at rest (BACKEND_CREDENTIALS_ENCRYPTION_KEY). A standby
-- pair holds the previous primary during the 24h overlap window described in
-- SHARED-CONTRACT.md §4.4.

CREATE TABLE IF NOT EXISTS tenant_backend_credentials (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    customer_id UUID NOT NULL REFERENCES customers(id) ON DELETE CASCADE,

    backend_type VARCHAR(40) NOT NULL,            -- "stella", "shopify", etc.
    remote_site_id VARCHAR(255) NOT NULL,         -- merchant identifier in the backend

    -- Primary credential pair (Fernet-encrypted secret)
    sync_key_id VARCHAR(40),
    sync_key_secret_encrypted TEXT,

    -- Standby slot for rotation (previous primary)
    sync_key_id_standby VARCHAR(40),
    sync_key_secret_standby_encrypted TEXT,

    -- Webhook signing secret returned by Stella when we register a webhook with it
    webhook_signing_secret_encrypted TEXT,

    extra_config JSONB DEFAULT '{}',              -- backend-specific extras (Shopify shop domain, etc.)

    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),

    UNIQUE (customer_id, backend_type)
);

CREATE INDEX IF NOT EXISTS idx_tbc_customer ON tenant_backend_credentials(customer_id);
