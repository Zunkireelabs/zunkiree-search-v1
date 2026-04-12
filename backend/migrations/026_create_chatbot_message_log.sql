-- Create chatbot_message_log for audit trail and deduplication

CREATE TABLE IF NOT EXISTS chatbot_message_log (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    channel_id UUID NOT NULL REFERENCES chatbot_channels(id) ON DELETE CASCADE,
    customer_id UUID NOT NULL REFERENCES customers(id) ON DELETE CASCADE,
    platform_sender_id VARCHAR(255) NOT NULL,
    platform_message_id VARCHAR(255),
    direction VARCHAR(10) NOT NULL,
    message_text TEXT,
    response_time_ms INTEGER,
    error TEXT,
    created_at TIMESTAMP DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_chatbot_msglog_customer
    ON chatbot_message_log(customer_id, created_at DESC);

-- Unique index for webhook deduplication (only on non-null message IDs)
CREATE UNIQUE INDEX IF NOT EXISTS idx_chatbot_msglog_dedup
    ON chatbot_message_log(platform_message_id) WHERE platform_message_id IS NOT NULL;
