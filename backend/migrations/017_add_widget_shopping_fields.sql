-- Add shopping-related fields to widget_configs
ALTER TABLE widget_configs
ADD COLUMN IF NOT EXISTS enable_shopping BOOLEAN DEFAULT FALSE;

ALTER TABLE widget_configs
ADD COLUMN IF NOT EXISTS checkout_mode VARCHAR(20) DEFAULT 'redirect';
