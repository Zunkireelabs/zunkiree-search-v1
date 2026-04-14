-- Add rooms table for hospitality industry
CREATE TABLE IF NOT EXISTS rooms (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    customer_id UUID NOT NULL REFERENCES customers(id) ON DELETE CASCADE,
    name VARCHAR(255) NOT NULL,
    description TEXT,
    price_per_night FLOAT,
    currency VARCHAR(10),
    original_price FLOAT,
    images TEXT,
    amenities TEXT,
    capacity INTEGER DEFAULT 2,
    room_type VARCHAR(50),
    available BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_rooms_customer_id ON rooms(customer_id);
