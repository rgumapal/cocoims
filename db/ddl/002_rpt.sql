-- =====================================================================
-- Cocopan IMS — reporting layer
-- Implements SPEC §6.2 (precomputed weekday aggregates) and §6.4
-- (materialised views for dashboards).
--
-- Separate from 001_schema.sql because everything here is DERIVED: every
-- table and view below is rebuilt from core.fact_daily_store_item or
-- core.stock_movement by the nightly job. Dropping and recreating this
-- file loses no business data, which is not true of 001.
-- =====================================================================

-- =====================================================================
-- §6.2 Precomputed weekday aggregates — the key optimisation
-- =====================================================================

-- The forecast needs, per (location, item, weekday), the mean of the last
-- N same-weekday observations. Computing that at order time means scanning
-- four weeks of history for every one of ~19,500 lines. Precompute nightly
-- instead, so order generation is a single set-based join against this
-- table (SPEC §6.2, and the hard rule in CLAUDE.md LOGIC).
--
-- weeks_back is stored per-week rather than pre-averaged across the window
-- so that any window can be assembled at read time: param_set.ref_week_flags
-- decides which of weeks 1..4 participate, and that varies by parameter set.
-- Pre-averaging here would bake one window into the data and make
-- calibration against the client's workbook impossible.
CREATE TABLE IF NOT EXISTS rpt.agg_location_item_dow (
    location_code   VARCHAR(10) NOT NULL REFERENCES core.location(location_code),
    item_code       VARCHAR(20) NOT NULL REFERENCES core.item(item_code),
    day_of_week     SMALLINT NOT NULL CHECK (day_of_week BETWEEN 1 AND 7),
    weeks_back      SMALLINT NOT NULL CHECK (weeks_back BETWEEN 1 AND 4),

    -- Nullable on purpose. A (location, item, weekday, week) with no
    -- observation is an ABSENCE, not a zero — see CLAUDE.md DATA and
    -- SPEC §5.3. obs_count carries how many observations backed the mean.
    ave_sales       NUMERIC(12,3),
    ave_deliveries  NUMERIC(12,3),
    ave_excess      NUMERIC(12,3),
    ave_demand_est  NUMERIC(12,3),          -- censored-demand corrected, SPEC §8.4

    obs_count       SMALLINT NOT NULL,
    stddev_sales    NUMERIC(12,3),          -- feeds safety-stock maths
    sold_out_days   SMALLINT NOT NULL DEFAULT 0,
    computed_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (location_code, item_code, day_of_week, weeks_back)
);

-- =====================================================================
-- §6.4 Materialised views for dashboards
-- =====================================================================

CREATE MATERIALIZED VIEW IF NOT EXISTS rpt.mv_daily_network AS
SELECT business_date,
       SUM(deliveries_qty) AS deliveries,
       SUM(sales_qty)      AS sales,
       SUM(excess_qty)     AS excess,
       ROUND(SUM(excess_qty) / NULLIF(SUM(deliveries_qty), 0) * 100, 2) AS excess_pct,
       COUNT(DISTINCT location_code) AS active_locations
FROM core.fact_daily_store_item
GROUP BY business_date;

-- Required for REFRESH MATERIALIZED VIEW CONCURRENTLY, which is how the
-- nightly job refreshes without taking a lock the dashboard would block on.
CREATE UNIQUE INDEX IF NOT EXISTS idx_mv_daily_network
    ON rpt.mv_daily_network (business_date);

-- NOTE: SPEC §6.4 also names mv_item_performance, mv_location_scorecard and
-- mv_current_stock, but describes them in prose only — no DDL was specified.
-- They are deliberately NOT invented here. All three are consumed by the
-- Accuracy screens, so they land with that work rather than being guessed at
-- now and rewritten later (CLAUDE.md ENGINEERING STANDARDS: YAGNI).
