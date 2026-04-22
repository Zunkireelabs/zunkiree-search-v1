-- 030: Add product source toggle to widget_configs
-- Allows admin to choose where products come from: scraped website or Stella storefront
ALTER TABLE widget_configs ADD COLUMN IF NOT EXISTS product_source VARCHAR(20) NOT NULL DEFAULT 'scraped';
ALTER TABLE widget_configs ADD COLUMN IF NOT EXISTS storefront_fetch_mode VARCHAR(20) NOT NULL DEFAULT 'synced';
-- product_source: 'scraped' (from website ingestion) | 'storefront' (from Stella/Agenticom)
-- storefront_fetch_mode: 'realtime' (query Agenticom API) | 'synced' (cached in local DB)
