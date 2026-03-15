-- Add rich product details column
ALTER TABLE products ADD COLUMN IF NOT EXISTS details TEXT;
