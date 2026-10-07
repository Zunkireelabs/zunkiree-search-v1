-- SBAL-Z6: the web widget renders a clinic tenant's `ui.services`/
-- `ui.service_detail` as cards (and a one-line caption instead of the
-- model's enumerated list) only when this flag is on. Default false —
-- every existing tenant (including dental-city) keeps today's widget
-- behaviour exactly; turned on for sbal only, as app-level data, not a
-- code branch.

ALTER TABLE widget_configs ADD COLUMN IF NOT EXISTS service_cards BOOLEAN NOT NULL DEFAULT false;
