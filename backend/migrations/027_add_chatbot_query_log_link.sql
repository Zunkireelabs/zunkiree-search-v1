-- Link chatbot message log to query_logs for analytics and feedback tracking
ALTER TABLE chatbot_message_log ADD COLUMN IF NOT EXISTS query_log_id UUID REFERENCES query_logs(id) ON DELETE SET NULL;
CREATE INDEX IF NOT EXISTS idx_chatbot_msglog_query ON chatbot_message_log(query_log_id);
