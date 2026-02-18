-- Migration: Add full content column to document_chunks
-- Date: 2026-02-18
-- Description: Stores full chunk text in PostgreSQL instead of relying on
--              Pinecone metadata (which was truncated to 1000 chars).
--
-- SAFE: This is an additive change. No columns are removed or renamed.
-- BACKWARD COMPATIBLE: Existing rows will have content = '' until re-ingested.
--
-- Run against Supabase SQL Editor or psql:
--   psql $DATABASE_URL -f 001_add_content_column.sql

-- Add content column (NOT NULL with empty string default for existing rows)
ALTER TABLE document_chunks
ADD COLUMN IF NOT EXISTS content TEXT NOT NULL DEFAULT '';

-- Remove the default after migration (new rows must provide content explicitly)
ALTER TABLE document_chunks
ALTER COLUMN content DROP DEFAULT;

-- Verify
SELECT column_name, data_type, is_nullable
FROM information_schema.columns
WHERE table_name = 'document_chunks'
ORDER BY ordinal_position;
