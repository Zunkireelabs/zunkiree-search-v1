-- Create payments table for eSewa/Khalti payment tracking
CREATE TABLE IF NOT EXISTS payments (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    order_id UUID NOT NULL REFERENCES orders(id) ON DELETE CASCADE,
    customer_id UUID NOT NULL REFERENCES customers(id) ON DELETE CASCADE,
    gateway VARCHAR(20) NOT NULL,
    amount FLOAT NOT NULL,
    currency VARCHAR(10) DEFAULT 'NPR',
    status VARCHAR(30) DEFAULT 'pending',
    gateway_ref VARCHAR(255),
    transaction_id VARCHAR(255),
    gateway_response TEXT,
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_payments_order_id ON payments(order_id);
CREATE INDEX IF NOT EXISTS idx_payments_status ON payments(status);
CREATE INDEX IF NOT EXISTS idx_payments_gateway_ref ON payments(gateway_ref);
