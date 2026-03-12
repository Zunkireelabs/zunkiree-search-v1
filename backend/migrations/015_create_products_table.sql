-- Create products table for ecommerce product data
CREATE TABLE IF NOT EXISTS products (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    customer_id UUID NOT NULL REFERENCES customers(id) ON DELETE CASCADE,
    name VARCHAR(500) NOT NULL,
    description TEXT,
    price FLOAT,
    currency VARCHAR(10),
    original_price FLOAT,
    images TEXT,  -- JSON array of image URLs
    url TEXT,
    sku VARCHAR(100),
    brand VARCHAR(255),
    category VARCHAR(255),
    sizes TEXT,  -- JSON array
    colors TEXT,  -- JSON array
    in_stock BOOLEAN DEFAULT TRUE,
    tags TEXT,  -- JSON array
    vector_id VARCHAR(255),
    source_hash VARCHAR(64),
    scraped_at TIMESTAMP,
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_products_customer_id ON products(customer_id);
CREATE INDEX IF NOT EXISTS idx_products_source_hash ON products(source_hash);
