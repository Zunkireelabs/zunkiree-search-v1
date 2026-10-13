-- Education agent memory (generative-UI counselor, website_type = 'education').
--
-- visitor_profiles: what we know about a student (countries, budget, scores,
--   contact, plus the record of which blocks were shown so the same question
--   re-shows the identical block). Keyed by (customer_id, session_id): the
--   widget's session id lives in localStorage, so it is stable per browser.
--   `email` is set once the student shares contact details. It is stored for
--   the team's follow-up only: profiles are never linked or merged across
--   sessions by email (an unverified email must not expose another student's data).
-- widget_messages: the chat transcript incl. the UI blocks shown, so a page
--   reload re-renders exactly what the student saw and the agent has real
--   history instead of per-process memory.
--
-- Additive only. Both tables are tenant-owned (customer_id FK, ON DELETE CASCADE).

CREATE TABLE IF NOT EXISTS visitor_profiles (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    customer_id UUID NOT NULL REFERENCES customers(id) ON DELETE CASCADE,
    session_id VARCHAR(100) NOT NULL,
    email VARCHAR(255),
    profile JSONB NOT NULL DEFAULT '{}',
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    CONSTRAINT uq_visitor_profiles_customer_session UNIQUE (customer_id, session_id)
);

CREATE INDEX IF NOT EXISTS idx_visitor_profiles_customer_email
    ON visitor_profiles (customer_id, lower(email)) WHERE email IS NOT NULL;

CREATE TABLE IF NOT EXISTS widget_messages (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    customer_id UUID NOT NULL REFERENCES customers(id) ON DELETE CASCADE,
    session_id VARCHAR(100) NOT NULL,
    role VARCHAR(10) NOT NULL,           -- user | assistant
    content TEXT NOT NULL DEFAULT '',
    blocks JSONB NOT NULL DEFAULT '[]',  -- UI blocks shown with this message
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_widget_messages_session
    ON widget_messages (customer_id, session_id, created_at);
