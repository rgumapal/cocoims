-- =====================================================================
-- Cocopan IMS — performance indexes
-- Implements SPEC §6.3.
--
-- Separate from 001_schema.sql because these are tuning, not structure.
-- Nothing here changes what the data MEANS; every index below can be
-- dropped and rebuilt without affecting correctness. Keeping them in one
-- file makes it possible to review the access-path story on its own, and
-- to re-tune after pg_stat_statements shows real query shapes.
--
-- Indexes that enforce a constraint or serve a defined lookup path live
-- with their table in 001_schema.sql instead (idx_item_search,
-- idx_closure_lookup, idx_outbox_pending, idx_stg_unprocessed).
-- =====================================================================

-- ---------------------------------------------------------------------
-- core.order_line — the Exception Workbench working set
-- ---------------------------------------------------------------------

-- Covering index: the workbench grid renders these columns and nothing
-- else, so INCLUDE lets the whole grid read be an index-only scan and
-- never touch the heap. This is the read path for ~19,500 rows per run
-- and the single most performance-sensitive query in the UI.
CREATE INDEX IF NOT EXISTS idx_ol_grid
    ON core.order_line (order_id, location_code, item_code)
    INCLUDE (suggested_order, cx_reco, om_adjustment, final_order, exception_flags);

-- Partial index for the default workbench filter. Reviewers see flagged,
-- un-reviewed lines by default (SPEC §12.6 rule 1, target under 10% of
-- lines), so the hot working set is a small fraction of the table and a
-- partial index keeps it small enough to stay cached.
CREATE INDEX IF NOT EXISTS idx_ol_needs_review
    ON core.order_line (order_id)
    WHERE cx_at IS NULL AND exception_flags IS NOT NULL;

-- ---------------------------------------------------------------------
-- core.stock_movement — the append-only ledger
-- ---------------------------------------------------------------------

-- BRIN, not btree, on the date columns. The ledger is append-only and
-- therefore physically ordered by business_date already, which is exactly
-- the correlation BRIN exploits: this index is a few pages against a table
-- that grows without bound, where the btree equivalent would rival the
-- table in size for no gain on the range scans the rollup actually runs.
CREATE INDEX IF NOT EXISTS idx_movement_brin
    ON core.stock_movement USING brin (business_date, occurred_at)
    WITH (pages_per_range = 64);

-- Point lookups: "every movement for this item at this branch, newest
-- first" — the Stock Explorer drill-down and the FEFO balance walk.
CREATE INDEX IF NOT EXISTS idx_movement_lookup
    ON core.stock_movement (location_code, item_code, business_date DESC);

-- ---------------------------------------------------------------------
-- core.item_price — effective-dated price resolution
-- ---------------------------------------------------------------------

-- Serves core.v_effective_price, which resolves branch override then falls
-- back to the network row. DESC on effective_from so the current row is
-- the first one found rather than requiring a sort of the item's history.
CREATE INDEX IF NOT EXISTS idx_item_price_lookup
    ON core.item_price (item_code, location_code, effective_from DESC);
