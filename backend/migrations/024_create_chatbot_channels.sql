-- Create chatbot_channels table for multi-platform messaging integration
-- Maps tenant Instagram/Messenger/WhatsApp accounts to customers

CREATE TABLE IF NOT EXISTS chatbot_channels (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    customer_id UUID NOT NULL REFERENCES customers(id) ON DELETE CASCADE,
    platform VARCHAR(20) NOT NULL,
    platform_page_id VARCHAR(255) NOT NULL,
    page_access_token TEXT NOT NULL,
    is_active BOOLEAN DEFAULT TRUE,
    channel_name VARCHAR(255),
    config JSONB DEFAULT '{}',
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW(),
    UNIQUE(platform, platform_page_id)
);

CREATE INDEX IF NOT EXISTS idx_chatbot_channels_customer ON chatbot_channels(customer_id);
CREATE INDEX IF NOT EXISTS idx_chatbot_channels_platform_page ON chatbot_channels(platform, platform_page_id);
