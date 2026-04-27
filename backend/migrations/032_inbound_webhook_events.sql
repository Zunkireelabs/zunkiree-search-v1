-- Z4: Inbound webhook receiver for Stella events.
--
-- Two changes in one migration (locked Z4 §1.2):
--   1. New table inbound_webhook_events — append-only ledger keyed by
--      (source, event_id) so SHARED-CONTRACT.md §7.5 at-least-once delivery
--      is naturally idempotent (ON CONFLICT DO NOTHING on the dedup key).
--   2. ALTER tenant_backend_credentials to add the two columns Z2 didn't
--      land but Z4 needs: webhook_signing_secret_prefix (last-4-of-secret-
--      style identifier for log diagnostics) and webhook_id (Stella's
--      "whk_..." registration id, returned by POST /api/sync/v1/webhooks
--      per SHARED-CONTRACT.md §7.1).
--
-- Discipline (per zunkiree_environment_topology memory): stage and prod
-- containers share one Supabase. This migration runs once per deploy and
-- must be safely re-runnable, hence IF NOT EXISTS / ADD COLUMN IF NOT
-- EXISTS on every statement.

CREATE TABLE IF NOT EXISTS inbound_webhook_events (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    customer_id UUID NOT NULL REFERENCES customers(id) ON DELETE CASCADE,

    source VARCHAR(40) NOT NULL,                -- "stella"
    event_id VARCHAR(80) NOT NULL,              -- envelope.id, e.g. "evt_..."
    event_type VARCHAR(100) NOT NULL,           -- envelope.event, e.g. "product.updated"

    payload JSONB NOT NULL,                     -- full envelope (incl. data)
    correlation_id UUID,                        -- envelope.correlation_id when uuid-shaped

    received_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    processed_at TIMESTAMP WITH TIME ZONE,
    processing_error TEXT,

    UNIQUE (source, event_id)
);

-- Per-tenant scan: dashboards / debug filtered by customer + event type.
CREATE INDEX IF NOT EXISTS idx_inbound_events_customer_type
    ON inbound_webhook_events(customer_id, event_type);

-- Dispatcher's hot-path: WHERE processed_at IS NULL ORDER BY received_at.
-- Partial index keeps it tiny (only the unprocessed backlog).
CREATE INDEX IF NOT EXISTS idx_inbound_events_unprocessed
    ON inbound_webhook_events(received_at)
    WHERE processed_at IS NULL;


-- tenant_backend_credentials column additions (Z2 left these unfilled).
-- webhook_signing_secret_encrypted already exists (Z2 §3.2.1). Z4 adds the
-- prefix + id columns so we can identify which registration a delivery
-- belongs to without decrypting (prefix = first 8 chars of "whsec_..." for
-- logging; webhook_id = Stella's "whk_..." returned at registration time).
ALTER TABLE tenant_backend_credentials
    ADD COLUMN IF NOT EXISTS webhook_signing_secret_prefix VARCHAR(16);

ALTER TABLE tenant_backend_credentials
    ADD COLUMN IF NOT EXISTS webhook_id VARCHAR(80);
