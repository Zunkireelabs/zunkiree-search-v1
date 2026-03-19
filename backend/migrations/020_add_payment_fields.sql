ALTER TABLE widget_configs ADD COLUMN IF NOT EXISTS stripe_account_id VARCHAR(255);
ALTER TABLE widget_configs ADD COLUMN IF NOT EXISTS payment_enabled BOOLEAN DEFAULT FALSE;
ALTER TABLE widget_configs ADD COLUMN IF NOT EXISTS shipping_countries TEXT;
