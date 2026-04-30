-- Z-Ops hardening sweep: admin_audit_log
--
-- Forward-only append log capturing every destructive admin action: customer
-- deletes (legacy + Z6 tenant), admin-token rotations (legacy api-key + Z6
-- per-tenant), and chatbot channel disconnects. Surfaced by the kasa-clothing
-- recovery (2026-04-29) where a destructive op left no actor / timestamp /
-- payload trail; the next-or-later out-of-band incident is now visible.
--
-- Idempotent (IF NOT EXISTS) per Z2 discipline. Stage and prod share Supabase
-- so this migration runs against the shared DB on whichever env deploys first.
-- No backfill — past destructive ops have no rows.

CREATE TABLE IF NOT EXISTS admin_audit_log (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),

    actor VARCHAR(80) NOT NULL,             -- 'master_admin', 'tenant_admin:<token_id>', 'legacy_admin'
    action VARCHAR(80) NOT NULL,            -- 'customer.deleted', 'tenant.deleted', 'admin_token.rotated', 'customer_api_key.rotated', 'chatbot_channel.disconnected'
    target_table VARCHAR(80) NOT NULL,      -- 'customers', 'tenant_admin_tokens', 'chatbot_channels'
    target_id UUID,                         -- nullable; some targets are composite-keyed
    target_site_id VARCHAR(255),            -- denormalized for searchability ("what happened to kasa-clothing?")

    payload_json JSONB,                     -- snapshot of the deleted/mutated row plus relevant request context
    request_id VARCHAR(64),                 -- correlation ID from middleware (X-Correlation-Id)
    ip_address INET,                        -- best-effort from X-Forwarded-For / request.client.host

    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_admin_audit_log_target_site
    ON admin_audit_log(target_site_id, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_admin_audit_log_action_time
    ON admin_audit_log(action, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_admin_audit_log_actor
    ON admin_audit_log(actor, created_at DESC);
