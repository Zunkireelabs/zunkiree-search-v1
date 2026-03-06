-- Add question_count to verification_sessions for lead capture after N questions
ALTER TABLE verification_sessions ADD COLUMN IF NOT EXISTS question_count INTEGER DEFAULT 0;
