-- Add feedback columns to query_logs table
ALTER TABLE query_logs ADD COLUMN IF NOT EXISTS feedback_vote SMALLINT;
ALTER TABLE query_logs ADD COLUMN IF NOT EXISTS feedback_at TIMESTAMP;
