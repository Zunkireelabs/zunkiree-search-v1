-- Add website_type column to customers table
-- Stores auto-detected website type: ecommerce, blog, saas, service, portfolio, restaurant, other
ALTER TABLE customers
ADD COLUMN IF NOT EXISTS website_type VARCHAR(20) DEFAULT NULL;
