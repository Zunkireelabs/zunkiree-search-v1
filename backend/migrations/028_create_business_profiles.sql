-- 028: Create business_profiles table for auto-extracted business intelligence
CREATE TABLE IF NOT EXISTS business_profiles (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    customer_id UUID NOT NULL UNIQUE REFERENCES customers(id) ON DELETE CASCADE,

    -- Core business info
    business_description TEXT,
    business_category VARCHAR(100),
    business_model VARCHAR(20),       -- B2C / B2B / B2B2C
    sales_approach VARCHAR(20),       -- checkout / catalog / inquiry

    -- Extracted fields (JSON stored as TEXT)
    services_products TEXT,           -- JSON array of key offerings
    pricing_info TEXT,                -- Pricing summary or "Not found"
    policies TEXT,                    -- JSON: return, refund, support policies
    unique_selling_points TEXT,       -- JSON array of differentiators
    target_audience TEXT,

    -- Optional fields
    business_hours TEXT,
    location_info TEXT,
    team_info TEXT,

    -- Meta
    detected_tone VARCHAR(20),        -- formal / neutral / friendly
    content_gaps TEXT,                -- JSON array of missing info
    raw_extraction TEXT,              -- Full LLM response for debugging

    -- Pre-composed prompt block
    system_prompt_block TEXT,

    -- Status tracking
    status VARCHAR(20) NOT NULL DEFAULT 'pending',  -- pending / building / completed / failed
    llm_tokens_used INTEGER,

    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_business_profiles_customer_id ON business_profiles(customer_id);
CREATE INDEX IF NOT EXISTS idx_business_profiles_status ON business_profiles(status);

-- Add checkout_mode = 'inquiry' as a valid option for widget_configs
-- (The column already exists with varchar(20), so 'inquiry' is already valid — this is just a comment)
