-- Z5: Persist external IDs returned by Stella's order-create endpoint so
-- Zunkiree orders can be joined back to their Stella counterparts without
-- relying on string matches against order_number alone.
--
-- After Z3 wired ConnectorResolver into _sync_to_agenticom, the connector
-- returns a ConnectorOrderReceipt that today is parsed but only used for
-- logging (services/order.py). Z5 closes that gap: write external_id +
-- external_order_number back onto the local orders row in the same flow,
-- tagged with external_backend_type='stella' for both v1 and legacy modes.
--
-- Discipline (per zunkiree_environment_topology memory): stage and prod
-- containers share one Supabase. This migration runs once per deploy and
-- must be safely re-runnable, hence ADD COLUMN IF NOT EXISTS on every
-- statement. Three nullable columns, no constraints, no indexes — query
-- patterns aren't established yet, and ALTER ADD on a nullable column with
-- no default is metadata-only on Postgres (no row rewrite).
--
-- No backfill of pre-Z5 orders (locked Z5-BRIEF §1.5): a future maintenance
-- PR can backfill from Stella's listing API if the diagnostic value emerges.

ALTER TABLE orders
    ADD COLUMN IF NOT EXISTS external_backend_type VARCHAR(40),
    ADD COLUMN IF NOT EXISTS external_order_id VARCHAR(255),
    ADD COLUMN IF NOT EXISTS external_order_number VARCHAR(100);
