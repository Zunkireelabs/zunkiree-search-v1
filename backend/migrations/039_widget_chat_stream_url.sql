-- P3-WIDGET-THROUGH-ORCA-BRIEF Part B (B1): opt-in field that routes a
-- tenant's widget chat stream through Orca's chat adapter instead of
-- Zunkiree's own /api/v1/query/stream. Absent by default, so every
-- existing widget is untouched. Rollback is clearing this one column
-- (config only, no deploy) — see brief §2.
--
-- Nullable, no default: config, autocomplete, feedback and payments all
-- keep using apiUrl unchanged (brief §1) — this only ever steers the
-- widget's chat stream.

ALTER TABLE widget_configs ADD COLUMN IF NOT EXISTS chat_stream_url TEXT NULL;
