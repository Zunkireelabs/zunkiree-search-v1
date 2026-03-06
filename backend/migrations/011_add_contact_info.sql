-- Add contact email and phone to widget_configs
ALTER TABLE widget_configs ADD COLUMN IF NOT EXISTS contact_email VARCHAR(255);
ALTER TABLE widget_configs ADD COLUMN IF NOT EXISTS contact_phone VARCHAR(50);
