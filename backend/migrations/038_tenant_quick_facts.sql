-- Per-tenant "quick facts" fast-path (ZUNKIREE-FAST-FACTS-BRIEF).
--
-- search_knowledge's embeddings call was measured at 16-20s on dental-city
-- (tracker 2026-09-21, call d7e0c73c..., turn 8) and cost a live voice call
-- via LLM Cascade Error. Most questions that hit search_knowledge are static
-- facts a clinic rarely changes (hours, address, contact, staff, a services
-- overview) — this table lets clinic_tools.py answer those directly, no
-- embeddings call, no Pinecone round trip, no search_knowledge invocation.
--
-- Deliberately NOT a home for booking hours that ClinicMD already owns
-- (branches.open_time/close_time) — S4-TENANT-CONFIG-BRIEF finding #3. A
-- tenant whose ClinicMD branch has open_time/close_time populated is served
-- from there instead (see clinic_tools._quick_fact_lookup); this table is
-- for facts ClinicMD has no column for at all, or leaves NULL.
--
-- Anything that doesn't match a row here falls through to the existing
-- search_knowledge RAG path unchanged.

CREATE TABLE IF NOT EXISTS tenant_quick_facts (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    customer_id UUID NOT NULL REFERENCES customers(id) ON DELETE CASCADE,

    category VARCHAR(30) NOT NULL,   -- hours, address, contact, staff, services_overview, policy, other
    keywords JSONB NOT NULL DEFAULT '[]',  -- lowercase trigger words/phrases matched against the visitor's question
    answer TEXT NOT NULL,

    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_tenant_quick_facts_customer ON tenant_quick_facts(customer_id) WHERE is_active;
