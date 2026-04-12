-- Create chatbot_conversations table for persistent multi-turn DM history

CREATE TABLE IF NOT EXISTS chatbot_conversations (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    channel_id UUID NOT NULL REFERENCES chatbot_channels(id) ON DELETE CASCADE,
    platform_sender_id VARCHAR(255) NOT NULL,
    role VARCHAR(20) NOT NULL,
    content TEXT NOT NULL,
    created_at TIMESTAMP DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_chatbot_conv_channel_sender
    ON chatbot_conversations(channel_id, platform_sender_id, created_at DESC);
