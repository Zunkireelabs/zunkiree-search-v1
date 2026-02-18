-- Add tsvector column for full-text search
ALTER TABLE document_chunks
ADD COLUMN IF NOT EXISTS search_vector tsvector;

-- Backfill existing rows
UPDATE document_chunks
SET search_vector = to_tsvector('english', content)
WHERE search_vector IS NULL;

-- GIN index for fast full-text queries
CREATE INDEX IF NOT EXISTS idx_document_chunks_search_vector
ON document_chunks USING GIN (search_vector);
