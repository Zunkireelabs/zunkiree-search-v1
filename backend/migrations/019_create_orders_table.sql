CREATE TABLE IF NOT EXISTS orders (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    order_number VARCHAR(20) UNIQUE NOT NULL,
    customer_id UUID NOT NULL REFERENCES customers(id) ON DELETE CASCADE,
    session_id VARCHAR(255) NOT NULL,
    shopper_email VARCHAR(255),
    items TEXT NOT NULL DEFAULT '[]',
    subtotal FLOAT NOT NULL DEFAULT 0,
    tax FLOAT NOT NULL DEFAULT 0,
    shipping_cost FLOAT NOT NULL DEFAULT 0,
    total FLOAT NOT NULL DEFAULT 0,
    currency VARCHAR(10) NOT NULL DEFAULT 'USD',
    status VARCHAR(30) NOT NULL DEFAULT 'pending',
    payment_status VARCHAR(30) NOT NULL DEFAULT 'unpaid',
    payment_intent_id VARCHAR(255),
    payment_method VARCHAR(50),
    billing_address TEXT,
    shipping_address TEXT,
    notes TEXT,
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_orders_customer_id ON orders(customer_id);
CREATE INDEX IF NOT EXISTS idx_orders_session_id ON orders(session_id);
CREATE INDEX IF NOT EXISTS idx_orders_status ON orders(status);
