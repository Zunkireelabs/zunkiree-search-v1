-- Z6: Per-tenant admin API for Stella callers.
--
-- Adds:
--   1. tenant_admin_tokens — Stella's per-tenant admin tokens (zka_live_<id>,
--      zka_sec_<48> hashed with Argon2id). Max 2 active per tenant enforced by
--      trigger (24h overlap rotation, SHARED-CONTRACT §12.3).
--   2. tenant_outbound_webhooks — subscriptions that Z7 will deliver to (events
--      from SHARED-CONTRACT §12.5: lead.captured, query.logged,
--      order.created.via_widget). Soft-revoke via revoked_at, never hard-delete
--      so signatures on past deliveries remain auditable.
--   3. customers.stella_merchant_id — needed by Z7 webhook envelopes
--      (merchant.id field per §12.5 mirroring §7.3). Additive nullable; no
--      backfill.
--
-- All idempotent (IF NOT EXISTS, CREATE OR REPLACE FUNCTION, DROP TRIGGER IF
-- EXISTS) per Z2 discipline.

CREATE TABLE IF NOT EXISTS tenant_admin_tokens (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    customer_id UUID NOT NULL REFERENCES customers(id) ON DELETE CASCADE,

    token_id VARCHAR(40) UNIQUE NOT NULL,          -- "zka_live_<20 base32>"
    secret_prefix VARCHAR(12) NOT NULL,            -- first 8 chars of secret, log-safe diagnostic
    secret_hash TEXT NOT NULL,                     -- argon2id

    description VARCHAR(255),
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    last_used_at TIMESTAMP WITH TIME ZONE,
    revoked_at TIMESTAMP WITH TIME ZONE
);

CREATE INDEX IF NOT EXISTS idx_tenant_admin_tokens_customer
    ON tenant_admin_tokens(customer_id);

CREATE INDEX IF NOT EXISTS idx_tenant_admin_tokens_active
    ON tenant_admin_tokens(customer_id) WHERE revoked_at IS NULL;

-- Bearer-auth lookup hits secret_prefix first to scope candidates before
-- Argon2id verify (no full table scan on every request).
CREATE INDEX IF NOT EXISTS idx_tenant_admin_tokens_prefix
    ON tenant_admin_tokens(secret_prefix) WHERE revoked_at IS NULL;

CREATE OR REPLACE FUNCTION check_admin_token_limit() RETURNS TRIGGER AS $$
BEGIN
    IF (SELECT COUNT(*) FROM tenant_admin_tokens
        WHERE customer_id = NEW.customer_id
          AND revoked_at IS NULL) >= 2
    THEN
        RAISE EXCEPTION 'Tenant % already has 2 active admin tokens', NEW.customer_id;
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS enforce_admin_token_limit ON tenant_admin_tokens;
CREATE TRIGGER enforce_admin_token_limit
    BEFORE INSERT ON tenant_admin_tokens
    FOR EACH ROW
    WHEN (NEW.revoked_at IS NULL)
    EXECUTE FUNCTION check_admin_token_limit();


CREATE TABLE IF NOT EXISTS tenant_outbound_webhooks (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    customer_id UUID NOT NULL REFERENCES customers(id) ON DELETE CASCADE,

    url TEXT NOT NULL,                             -- Stella receiver URL
    events JSONB NOT NULL DEFAULT '[]'::jsonb,     -- subset of {lead.captured, query.logged, order.created.via_widget}

    signing_secret_encrypted TEXT NOT NULL,        -- Fernet-encrypted whsec_<...>
    signing_secret_prefix VARCHAR(16) NOT NULL,    -- first chars of plaintext, log-safe diagnostic

    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    revoked_at TIMESTAMP WITH TIME ZONE            -- soft-revoke; never hard-delete
);

CREATE INDEX IF NOT EXISTS idx_tenant_outbound_webhooks_customer
    ON tenant_outbound_webhooks(customer_id);

CREATE INDEX IF NOT EXISTS idx_tenant_outbound_webhooks_active
    ON tenant_outbound_webhooks(customer_id) WHERE revoked_at IS NULL;


-- Stella's merchant identifier so Z7 outbound envelopes can fill merchant.id
-- per SHARED-CONTRACT §12.5. Additive nullable; existing rows stay NULL until
-- re-provisioned.
ALTER TABLE customers
    ADD COLUMN IF NOT EXISTS stella_merchant_id VARCHAR(255);
