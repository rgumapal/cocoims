-- Cocopan IMS — baseline schema
-- Source of truth: docs/SPEC.md §4 (data model), §5.6 (reference data), §6.1 (partitioning), §7.2 (RLS)
--
-- This file is executed automatically on first container boot via
-- docker-entrypoint-initdb.d, and is also what Alembic's baseline migration
-- (backend/alembic/versions/0001_baseline.py) applies on a fresh environment.
--
-- Statements are reordered from the spec's document order where needed so that
-- every foreign key references a table that already exists (the spec presents
-- them in narrative order, not dependency order).
--
-- Two additions beyond the literal spec text, both required for the DDL to run
-- at all, called out here rather than silently:
--   1. `CREATE EXTENSION citext` — core.app_user.email is CITEXT but the spec's
--      extension list (§4) omits it.
--   2. Initial partitions + DEFAULT partitions for the four PARTITION BY RANGE
--      tables — the spec defines the partitioned parents (§4.4, §4.5, §4.9) and
--      a monthly partitioning *strategy* (§6.1), but not bootstrap partitions.
--      A DEFAULT partition is a safety net for dev only; §6.1's "automate
--      partition creation three months ahead" job (Milestone 12) should retire
--      it in production once scheduled partition creation exists.

BEGIN;

-- =====================================================================
-- Schemas & extensions
-- =====================================================================
CREATE SCHEMA IF NOT EXISTS core;      -- business data
CREATE SCHEMA IF NOT EXISTS audit;     -- audit trail
CREATE SCHEMA IF NOT EXISTS stg;       -- integration staging
CREATE SCHEMA IF NOT EXISTS rpt;       -- rollups and materialized views

CREATE EXTENSION IF NOT EXISTS btree_gist;
CREATE EXTENSION IF NOT EXISTS pg_trgm;      -- fuzzy search on item names
CREATE EXTENSION IF NOT EXISTS pgcrypto;
CREATE EXTENSION IF NOT EXISTS citext;       -- core.app_user.email

-- =====================================================================
-- §4.1 Enums
-- =====================================================================
CREATE TYPE item_type        AS ENUM ('FINISHED_GOOD','SUPPLY','PACKAGING','RAW_MATERIAL','INGREDIENT');
CREATE TYPE packaging_type   AS ENUM ('MANUAL_PACKING','MACHINE_WRAPPED','BULK','NA');
CREATE TYPE item_status      AS ENUM ('ACTIVE','PILOT','TEMPORARILY_NOT_AVAILABLE','DO_NOT_INCLUDE_YET','DELISTED');
CREATE TYPE location_type    AS ENUM ('BRANCH','COMMISSARY','WAREHOUSE','IN_TRANSIT','VIRTUAL');
CREATE TYPE store_format     AS ENUM ('STANDALONE','CONCESSION','KIOSK');
CREATE TYPE location_status  AS ENUM ('PLANNED','PRE_OPENING','RAMP_UP','ACTIVE',
                                      'TEMP_CLOSED','RENOVATION','RELOCATED','CLOSED');
CREATE TYPE replen_policy    AS ENUM ('SAME_DAY','MULTI_DAY','MIN_MAX','NONE');
CREATE TYPE movement_type    AS ENUM ('RECEIPT','SALE','WASTE','TRANSFER_OUT','TRANSFER_IN',
                                      'COUNT_ADJUSTMENT','RETURN','PRODUCTION','CONSUMPTION','OPENING');
CREATE TYPE order_status     AS ENUM ('DRAFT','PENDING_CX','PENDING_OM','LOCKED','SUBMITTED','CANCELLED');
CREATE TYPE excess_source    AS ENUM ('COUNTED','DERIVED');
CREATE TYPE audit_action     AS ENUM ('INSERT','UPDATE','DELETE','LOGIN','LOGOUT','EXPORT','APPROVE','LOCK','SUBMIT');

-- =====================================================================
-- §4.2 Identity, RBAC and scoping
-- =====================================================================
CREATE TABLE core.app_user (
    user_id         BIGSERIAL PRIMARY KEY,
    email           CITEXT UNIQUE NOT NULL,
    full_name       VARCHAR(120) NOT NULL,
    password_hash   TEXT,                       -- null when SSO-only
    sso_subject     VARCHAR(255) UNIQUE,
    is_active       BOOLEAN NOT NULL DEFAULT TRUE,
    is_service      BOOLEAN NOT NULL DEFAULT FALSE,   -- integration accounts
    last_login_at   TIMESTAMPTZ,
    failed_attempts SMALLINT NOT NULL DEFAULT 0,
    locked_until    TIMESTAMPTZ,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    created_by      BIGINT
);

CREATE TABLE core.role (
    role_code   VARCHAR(30) PRIMARY KEY,
    label       VARCHAR(80) NOT NULL,
    description TEXT,
    is_system   BOOLEAN NOT NULL DEFAULT FALSE   -- system roles cannot be deleted
);

-- Permissions are resource.action strings, e.g. 'item.create', 'order.submit_ppic'
CREATE TABLE core.permission (
    permission_code VARCHAR(60) PRIMARY KEY,
    resource        VARCHAR(30) NOT NULL,
    action          VARCHAR(30) NOT NULL,
    label           VARCHAR(120) NOT NULL,
    is_destructive  BOOLEAN NOT NULL DEFAULT FALSE   -- drives confirm-dialog in UI
);

CREATE TABLE core.role_permission (
    role_code       VARCHAR(30) REFERENCES core.role(role_code) ON DELETE CASCADE,
    permission_code VARCHAR(60) REFERENCES core.permission(permission_code) ON DELETE CASCADE,
    PRIMARY KEY (role_code, permission_code)
);

CREATE TABLE core.user_role (
    user_id     BIGINT REFERENCES core.app_user(user_id) ON DELETE CASCADE,
    role_code   VARCHAR(30) REFERENCES core.role(role_code),
    granted_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    granted_by  BIGINT,
    PRIMARY KEY (user_id, role_code)
);

-- Data scoping: which rows a user may see. Empty = all.
CREATE TABLE core.user_scope (
    scope_id    BIGSERIAL PRIMARY KEY,
    user_id     BIGINT NOT NULL REFERENCES core.app_user(user_id) ON DELETE CASCADE,
    scope_type  VARCHAR(20) NOT NULL,    -- 'LOCATION' | 'AREA' | 'CLUSTER'
    scope_value VARCHAR(30) NOT NULL,
    UNIQUE (user_id, scope_type, scope_value)
);

CREATE TABLE core.api_key (
    key_id          BIGSERIAL PRIMARY KEY,
    user_id         BIGINT NOT NULL REFERENCES core.app_user(user_id),
    key_hash        TEXT NOT NULL,
    key_prefix      VARCHAR(12) NOT NULL,     -- shown in UI for identification
    label           VARCHAR(80) NOT NULL,
    scopes          TEXT[],
    expires_at      TIMESTAMPTZ,
    revoked_at      TIMESTAMPTZ,
    last_used_at    TIMESTAMPTZ
);

-- =====================================================================
-- §4.3 Master data — independent lookups first
-- (reordered ahead of core.item / core.location, which reference them)
-- =====================================================================
CREATE TABLE core.item_category (
    category_code VARCHAR(30) PRIMARY KEY,
    parent_code   VARCHAR(30) REFERENCES core.item_category(category_code),
    label         VARCHAR(80) NOT NULL,
    sort_order    SMALLINT NOT NULL DEFAULT 0
);

CREATE TABLE core.area    (area_code VARCHAR(30) PRIMARY KEY, label VARCHAR(80) NOT NULL);
CREATE TABLE core.cluster (cluster_code VARCHAR(30) PRIMARY KEY, label VARCHAR(80) NOT NULL,
                           description TEXT);   -- TRANSPORT_HUB, RESIDENTIAL, SUPERMARKET_CONCESSION, HIGH_TRAFFIC_24H
CREATE TABLE core.route   (route_code VARCHAR(20) PRIMARY KEY, label VARCHAR(80) NOT NULL,
                           dispatch_sequence SMALLINT);

-- Philippine geography hierarchy. Matters as Cocopan expands beyond NCR:
-- holidays, fiestas and paydays are locally variable.
CREATE TABLE core.geography (
    geo_code      VARCHAR(20) PRIMARY KEY,
    parent_code   VARCHAR(20) REFERENCES core.geography(geo_code),
    geo_level     VARCHAR(20) NOT NULL,   -- REGION | PROVINCE | CITY | BARANGAY
    label         VARCHAR(120) NOT NULL
);

CREATE TABLE core.uom (
    uom_code      VARCHAR(10) PRIMARY KEY,
    label         VARCHAR(40) NOT NULL,
    is_fractional BOOLEAN NOT NULL DEFAULT FALSE
);

CREATE TABLE core.reason_code (
    reason_code VARCHAR(40) PRIMARY KEY,
    category    VARCHAR(20) NOT NULL,   -- OVERRIDE | WASTE | ADJUSTMENT
    label       VARCHAR(120) NOT NULL,
    requires_note BOOLEAN NOT NULL DEFAULT FALSE,
    sort_order  SMALLINT DEFAULT 0,
    is_active   BOOLEAN NOT NULL DEFAULT TRUE
);

CREATE TABLE core.calendar (
    calendar_date   DATE PRIMARY KEY,
    day_of_week     SMALLINT NOT NULL,           -- ISO 1=Mon
    day_name        VARCHAR(10) NOT NULL,
    iso_week        SMALLINT NOT NULL,
    is_payday       BOOLEAN NOT NULL DEFAULT FALSE,   -- 15th / 30th: material in PH retail
    is_holiday      BOOLEAN NOT NULL DEFAULT FALSE,
    holiday_name    VARCHAR(80),
    season_flag     VARCHAR(30),                 -- HOLY_WEEK, UNDAS, CHRISTMAS, BACK_TO_SCHOOL
    weather_flag    VARCHAR(20)
);

-- Integration sources — created here (ahead of §4.8's other integration tables)
-- because core.item_alias references it below.
CREATE TABLE core.source_system (
    source_code     VARCHAR(30) PRIMARY KEY,     -- 'POS_MAIN','DR_SYSTEM','MANUAL_UPLOAD','GRABFOOD'
    label           VARCHAR(80) NOT NULL,
    system_type     VARCHAR(20) NOT NULL,        -- POS | ERP | FILE | API | AGGREGATOR
    is_active       BOOLEAN NOT NULL DEFAULT TRUE,
    config          JSONB
);

-- =====================================================================
-- §4.3 Master data — item, location and what hangs off them
-- =====================================================================

-- item_type is retained for forward compatibility. v1 seeds FINISHED_GOOD only.
CREATE TABLE core.item (
    item_code           VARCHAR(20) PRIMARY KEY,        -- 'CP001', 'SUP-CUP-12'
    item_type           item_type NOT NULL,
    desc_dr             VARCHAR(150) NOT NULL,          -- name on Delivery Receipt
    desc_offtake        VARCHAR(150),                   -- name in sales system
    display_name        VARCHAR(150) NOT NULL,          -- canonical name for UI
    category_code       VARCHAR(30) REFERENCES core.item_category(category_code),
    base_uom            VARCHAR(10) NOT NULL DEFAULT 'pc',
    packaging           packaging_type NOT NULL DEFAULT 'NA',
    shelf_life_days     SMALLINT NOT NULL DEFAULT 0,    -- 0 = same-day; 3 = 'PD + 3 days'
    replen_policy       replen_policy NOT NULL,
    moq                 NUMERIC(12,3) NOT NULL DEFAULT 0,
    moq_exempt          BOOLEAN NOT NULL DEFAULT FALSE, -- loaves & pandesal packs
    order_multiple      NUMERIC(12,3) DEFAULT 1,        -- round orders to this
    lifecycle_status    item_status NOT NULL DEFAULT 'ACTIVE',
    status_remark       TEXT,                           -- client wording, verbatim
    target_date         DATE,
    is_orderable        BOOLEAN GENERATED ALWAYS AS
                          (lifecycle_status IN ('ACTIVE','PILOT')) STORED,
    search_vector       tsvector GENERATED ALWAYS AS
                          (to_tsvector('simple', coalesce(display_name,'') || ' ' || item_code)) STORED,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT chk_policy_shelf CHECK (
        (replen_policy = 'MULTI_DAY' AND shelf_life_days > 0)
     OR (replen_policy <> 'MULTI_DAY')
    )
);
CREATE INDEX idx_item_search ON core.item USING gin(search_vector);
CREATE INDEX idx_item_trgm   ON core.item USING gin(display_name gin_trgm_ops);
CREATE INDEX idx_item_type_active ON core.item(item_type) WHERE is_orderable;

-- Alias resolution: DR and Offtake systems use different names for the same item.
CREATE TABLE core.item_alias (
    alias_id    BIGSERIAL PRIMARY KEY,
    item_code   VARCHAR(20) NOT NULL REFERENCES core.item(item_code) ON DELETE CASCADE,
    source_code VARCHAR(30) NOT NULL REFERENCES core.source_system(source_code),
    alias_text  VARCHAR(200) NOT NULL,
    UNIQUE (source_code, alias_text)
);

-- Unit conversions: sack -> kg, case -> sleeve -> piece
CREATE TABLE core.uom_conversion (
    item_code     VARCHAR(20) NOT NULL REFERENCES core.item(item_code) ON DELETE CASCADE,
    from_uom      VARCHAR(10) NOT NULL,
    to_uom        VARCHAR(10) NOT NULL,
    factor        NUMERIC(14,6) NOT NULL CHECK (factor > 0),
    PRIMARY KEY (item_code, from_uom, to_uom)
);

-- Effective-dated price and cost; resolves the conflicting SRPs in the source workbook.
CREATE TABLE core.item_price (
    price_id       BIGSERIAL PRIMARY KEY,
    item_code      VARCHAR(20) NOT NULL REFERENCES core.item(item_code),
    srp            NUMERIC(12,2) CHECK (srp >= 0),
    unit_cost      NUMERIC(12,4) CHECK (unit_cost >= 0),
    effective_from DATE NOT NULL,
    effective_to   DATE,
    EXCLUDE USING gist (
        item_code WITH =,
        daterange(effective_from, COALESCE(effective_to,'infinity'::date),'[)') WITH &&
    )
);

-- Locations unify branches, commissary and warehouses.
CREATE TABLE core.location (
    location_code   VARCHAR(10) PRIMARY KEY,        -- 'SAR', 'CMSY-01'
    location_type   location_type NOT NULL,
    location_name   VARCHAR(150) NOT NULL,
    store_format    store_format,
    cluster_code    VARCHAR(30) REFERENCES core.cluster(cluster_code),
    area_code       VARCHAR(30) REFERENCES core.area(area_code),
    route_code      VARCHAR(20) REFERENCES core.route(route_code),
    om_user_id      BIGINT REFERENCES core.app_user(user_id),
    address         TEXT,
    latitude        NUMERIC(9,6),
    longitude       NUMERIC(9,6),
    geo_code        VARCHAR(20) REFERENCES core.geography(geo_code),
    status          location_status NOT NULL DEFAULT 'PLANNED',
    planned_open_date DATE,
    open_date       DATE,
    close_date      DATE,
    ramp_weeks      SMALLINT NOT NULL DEFAULT 8,    -- blend window for new-store forecasting
    operating_hours JSONB,                          -- 24/7 stores exist
    display_capacity_units INTEGER,                 -- shelf capacity caps total order
    parent_location_code VARCHAR(10) REFERENCES core.location(location_code), -- concessions inside a host
    relocated_to    VARCHAR(10) REFERENCES core.location(location_code),
    is_active       BOOLEAN GENERATED ALWAYS AS
                      (status IN ('RAMP_UP','ACTIVE')) STORED,
    is_orderable    BOOLEAN GENERATED ALWAYS AS
                      (status IN ('PRE_OPENING','RAMP_UP','ACTIVE')) STORED,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX idx_location_status ON core.location(status);
CREATE INDEX idx_location_active ON core.location(location_type) WHERE is_active;

-- Full lifecycle history of every branch. Never overwrite location.status
-- without writing here; forecasting depends on knowing what a branch WAS.
CREATE TABLE core.location_status_history (
    history_id     BIGSERIAL PRIMARY KEY,
    location_code  VARCHAR(10) NOT NULL REFERENCES core.location(location_code) ON DELETE CASCADE,
    from_status    location_status,
    to_status      location_status NOT NULL,
    effective_from DATE NOT NULL,
    effective_to   DATE,
    reason_code    VARCHAR(40),
    note           TEXT,
    changed_by     BIGINT,
    changed_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
    EXCLUDE USING gist (
        location_code WITH =,
        daterange(effective_from, COALESCE(effective_to,'infinity'::date),'[)') WITH &&
    )
);

-- Day-level closures. CRITICAL: closed days must be excluded from forecast
-- reference windows, or a zero-sales day silently drags the weekday average down.
CREATE TABLE core.location_closure (
    closure_id     BIGSERIAL PRIMARY KEY,
    location_code  VARCHAR(10) NOT NULL REFERENCES core.location(location_code) ON DELETE CASCADE,
    start_date     DATE NOT NULL,
    end_date       DATE NOT NULL,
    closure_type   VARCHAR(30) NOT NULL,   -- HOLIDAY | RENOVATION | UTILITY | WEATHER | HOST_CLOSED | OTHER
    is_full_day    BOOLEAN NOT NULL DEFAULT TRUE,
    exclude_from_forecast BOOLEAN NOT NULL DEFAULT TRUE,
    note           TEXT,
    created_by     BIGINT,
    CHECK (end_date >= start_date)
);
CREATE INDEX idx_closure_lookup ON core.location_closure (location_code, start_date, end_date);

-- Assortment templates: what a branch of a given cluster/format carries.
-- Opening a new branch becomes "apply template", not 40 manual rows.
CREATE TABLE core.assortment_template (
    template_code  VARCHAR(30) PRIMARY KEY,
    label          VARCHAR(80) NOT NULL,
    store_format   store_format,
    cluster_code   VARCHAR(30) REFERENCES core.cluster(cluster_code),
    is_default     BOOLEAN NOT NULL DEFAULT FALSE,
    is_active      BOOLEAN NOT NULL DEFAULT TRUE
);

CREATE TABLE core.assortment_template_item (
    template_code  VARCHAR(30) NOT NULL REFERENCES core.assortment_template(template_code) ON DELETE CASCADE,
    item_code      VARCHAR(20) NOT NULL REFERENCES core.item(item_code) ON DELETE CASCADE,
    par_qty        NUMERIC(12,3),
    moq_override   NUMERIC(12,3),
    day_flags      SMALLINT[] DEFAULT '{1,2,3,4,5,6,7}',  -- delivery days
    PRIMARY KEY (template_code, item_code)
);

-- Item x Location parameters: MOQ and par differ per store.
CREATE TABLE core.item_location_param (
    item_code       VARCHAR(20) NOT NULL REFERENCES core.item(item_code) ON DELETE CASCADE,
    location_code   VARCHAR(10) NOT NULL REFERENCES core.location(location_code) ON DELETE CASCADE,
    is_stocked      BOOLEAN NOT NULL DEFAULT TRUE,
    par_qty         NUMERIC(12,3),
    moq_override    NUMERIC(12,3),
    display_capacity NUMERIC(12,3),      -- hard cap: shelf space for this SKU
    source_template VARCHAR(30) REFERENCES core.assortment_template(template_code),
    is_overridden   BOOLEAN NOT NULL DEFAULT FALSE,   -- diverged from template
    PRIMARY KEY (item_code, location_code)
);

CREATE TABLE core.delivery_schedule (
    location_code   VARCHAR(10) NOT NULL REFERENCES core.location(location_code) ON DELETE CASCADE,
    item_code       VARCHAR(20) NOT NULL REFERENCES core.item(item_code) ON DELETE CASCADE,
    day_of_week     SMALLINT NOT NULL CHECK (day_of_week BETWEEN 1 AND 7),
    is_deliverable  BOOLEAN NOT NULL DEFAULT TRUE,
    PRIMARY KEY (location_code, item_code, day_of_week)
);

CREATE TABLE core.calendar_location_event (
    event_id      BIGSERIAL PRIMARY KEY,
    calendar_date DATE NOT NULL REFERENCES core.calendar(calendar_date),
    location_code VARCHAR(10) REFERENCES core.location(location_code),
    event_type    VARCHAR(30) NOT NULL,          -- FIESTA, CLOSURE, RENOVATION, PROMO
    expected_impact_pct NUMERIC(6,3),
    note          TEXT,
    created_by    BIGINT
);

-- =====================================================================
-- §4.4 The stock ledger — core of the system
-- =====================================================================
-- Design decision: all stock changes for all item types are recorded as
-- immutable movements in one append-only ledger. Balances are derived, never
-- stored as mutable running totals.

CREATE TABLE core.stock_movement (
    movement_id     BIGSERIAL,
    business_date   DATE NOT NULL,
    occurred_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
    location_code   VARCHAR(10) NOT NULL REFERENCES core.location(location_code),
    item_code       VARCHAR(20) NOT NULL REFERENCES core.item(item_code),
    movement_type   movement_type NOT NULL,
    qty             NUMERIC(12,3) NOT NULL,      -- signed: +in, -out
    uom             VARCHAR(10) NOT NULL,
    production_date DATE,                        -- enables FEFO and ageing
    expiry_date     DATE,
    unit_cost       NUMERIC(12,4),
    reason_code     VARCHAR(40) REFERENCES core.reason_code(reason_code),
    ref_doc_type    VARCHAR(30),                 -- DR | ORDER | COUNT | POS | TRANSFER
    ref_doc_id      VARCHAR(60),
    counterparty_location VARCHAR(10),           -- for transfers
    source_code     VARCHAR(30) REFERENCES core.source_system(source_code),
    idempotency_key VARCHAR(120),                -- prevents duplicate ingestion
    created_by      BIGINT,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (business_date, movement_id)
) PARTITION BY RANGE (business_date);

-- Postgres requires a unique index on a partitioned table to include the
-- partition key (business_date). A plain unique index on idempotency_key
-- alone, as literally written in SPEC §4.4, is rejected by Postgres 16 with
-- "unique constraint on partitioned table must include all partitioning
-- columns". Including business_date only guarantees uniqueness within a
-- given business_date, not globally — acceptable here since idempotency
-- replay windows are inbound files/events scoped to a business_date anyway.
CREATE UNIQUE INDEX uq_movement_idem
  ON core.stock_movement (business_date, idempotency_key) WHERE idempotency_key IS NOT NULL;

-- Immutability: no UPDATE or DELETE grants on stock_movement. Corrections are
-- new offsetting movements with reason_code = 'CORRECTION'. Enforced at the
-- application-role grant level in Milestone 3 (access); see docs/SPEC.md §4.4.

-- =====================================================================
-- §4.5 Derived daily fact — the replenishment working table
-- =====================================================================
-- Rollup projected from the ledger, rebuilt nightly.

CREATE TABLE core.fact_daily_store_item (
    business_date           DATE NOT NULL,
    location_code           VARCHAR(10) NOT NULL,
    item_code               VARCHAR(20) NOT NULL,
    deliveries_qty          NUMERIC(12,3),
    sales_qty               NUMERIC(12,3),
    excess_qty              NUMERIC(12,3),
    excess_source           excess_source NOT NULL DEFAULT 'DERIVED',
    end_inventory_qty       NUMERIC(12,3),
    ei_reported             BOOLEAN NOT NULL DEFAULT FALSE,  -- separates true 0 from "not counted"
    carryover_usable_qty    NUMERIC(12,3),
    waste_qty               NUMERIC(12,3),
    sold_out_flag           BOOLEAN NOT NULL DEFAULT FALSE,
    sold_out_at              TIMESTAMPTZ,
    demand_estimate         NUMERIC(12,3),                   -- censored-demand corrected
    is_store_open            BOOLEAN NOT NULL DEFAULT TRUE,
    is_deliverable           BOOLEAN NOT NULL DEFAULT TRUE,
    rebuilt_at               TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (business_date, location_code, item_code)
) PARTITION BY RANGE (business_date);

-- DQ rule, absolute: these quantity columns are nullable on purpose. Never
-- coerce NULL to 0 anywhere this table is read or written. See CLAUDE.md.

-- =====================================================================
-- §4.6 Replenishment
-- =====================================================================
CREATE TABLE core.param_set (
    param_set_id    BIGSERIAL PRIMARY KEY,
    name            VARCHAR(80) NOT NULL,
    scope_level     VARCHAR(20) NOT NULL DEFAULT 'GLOBAL',  -- GLOBAL|CLUSTER|LOCATION|ITEM|CATEGORY
    scope_key       VARCHAR(30),
    effective_from  DATE NOT NULL,
    effective_to    DATE,
    ref_week_flags          JSONB NOT NULL,   -- {"1":{"mon":true,...},"2":{...}} weeks back
    safety_stock_pct        NUMERIC(6,4) NOT NULL DEFAULT 0.0500,
    topup_threshold_units   NUMERIC(12,3) NOT NULL DEFAULT 20,
    topup_pct_low           NUMERIC(6,4) NOT NULL DEFAULT 0,   -- CALIBRATE, see SPEC §14 AC-1
    topup_pct_high          NUMERIC(6,4) NOT NULL DEFAULT 0,   -- CALIBRATE
    reduction_pct           NUMERIC(6,4) NOT NULL DEFAULT 0,
    moq_trigger_enabled     BOOLEAN NOT NULL DEFAULT TRUE,
    moq_trigger_qty         NUMERIC(12,3) NOT NULL DEFAULT 6,
    moq_demand_multiple     NUMERIC(6,2) NOT NULL DEFAULT 3.0, -- flag threshold
    target_service_level    NUMERIC(6,4),
    min_observations        SMALLINT NOT NULL DEFAULT 2,
    carryover_enabled       BOOLEAN NOT NULL DEFAULT FALSE,    -- feature flag for AC-1
    cutoff_time             TIME NOT NULL DEFAULT '19:00',
    ppic_submit_time        TIME NOT NULL DEFAULT '20:00',
    created_by  BIGINT,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE core.forecast_run (
    run_id        BIGSERIAL PRIMARY KEY,
    run_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
    method        VARCHAR(40) NOT NULL,     -- 'WEEKDAY_AVG_V1'
    param_set_id  BIGINT NOT NULL REFERENCES core.param_set(param_set_id),
    horizon_start DATE NOT NULL,
    horizon_end   DATE NOT NULL,
    status        VARCHAR(20) NOT NULL DEFAULT 'RUNNING',
    created_by    BIGINT
);

CREATE TABLE core.forecast_line (
    run_id          BIGINT NOT NULL REFERENCES core.forecast_run(run_id) ON DELETE CASCADE,
    forecast_date   DATE NOT NULL,
    location_code   VARCHAR(10) NOT NULL,
    item_code       VARCHAR(20) NOT NULL,
    forecast_qty    NUMERIC(12,3) NOT NULL,
    method_used     VARCHAR(40) NOT NULL,
    obs_count       SMALLINT,
    confidence_flag VARCHAR(20),            -- OK | LOW_HISTORY | NEW_STORE | FALLBACK
    PRIMARY KEY (run_id, forecast_date, location_code, item_code)
);

CREATE TABLE core.order_header (
    order_id            BIGSERIAL PRIMARY KEY,
    order_reference     VARCHAR(50) UNIQUE NOT NULL,
    order_type          VARCHAR(20) NOT NULL DEFAULT 'FINISHED_GOOD', -- or 'SUPPLY'
    generated_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
    cover_start_date    DATE NOT NULL,
    cover_end_date      DATE NOT NULL,
    ref_period_start    DATE NOT NULL,
    ref_period_end      DATE NOT NULL,
    param_set_id        BIGINT NOT NULL REFERENCES core.param_set(param_set_id),
    forecast_run_id     BIGINT REFERENCES core.forecast_run(run_id),
    status              order_status NOT NULL DEFAULT 'DRAFT',
    cutoff_at           TIMESTAMPTZ,
    locked_at           TIMESTAMPTZ,
    locked_by           BIGINT,
    submitted_at        TIMESTAMPTZ,
    submitted_by        BIGINT,
    created_by          BIGINT
);

-- THE LADDER. Column names mirror the client's spreadsheet headers deliberately.
CREATE TABLE core.order_line (
    order_line_id       BIGSERIAL PRIMARY KEY,
    order_id            BIGINT NOT NULL REFERENCES core.order_header(order_id) ON DELETE CASCADE,
    delivery_date       DATE NOT NULL,
    location_code       VARCHAR(10) NOT NULL REFERENCES core.location(location_code),
    item_code           VARCHAR(20) NOT NULL REFERENCES core.item(item_code),

    ave_deliveries      NUMERIC(12,3),
    ave_sales           NUMERIC(12,3),
    ave_excess          NUMERIC(12,3),
    obs_count           SMALLINT,
    with_excess_flag    BOOLEAN,

    baseline_order      NUMERIC(12,3),      -- step 1
    adjustment          NUMERIC(12,3),      -- step 2
    net_of_adjustment   NUMERIC(12,3),      -- step 3
    moq_uplift          NUMERIC(12,3) DEFAULT 0,  -- step 4  "To meet MOQ, if any"
    reduction           NUMERIC(12,3) DEFAULT 0,  -- step 5  "Volume Reductions"
    carryover_applied   NUMERIC(12,3) DEFAULT 0,  -- step 6  multi-day only
    suggested_order_wo_ei NUMERIC(12,3),
    suggested_order     NUMERIC(12,3),      -- step 7

    cx_reco             NUMERIC(12,3),      -- step 8
    cx_user_id          BIGINT,
    cx_reason_code      VARCHAR(40),
    cx_at               TIMESTAMPTZ,

    om_adjustment       NUMERIC(12,3),      -- step 9
    om_user_id          BIGINT,
    om_reason_code      VARCHAR(40),
    om_at               TIMESTAMPTZ,

    final_order         NUMERIC(12,3) NOT NULL,   -- step 10

    exception_flags     TEXT[],             -- MOQ_EXCEEDS_DEMAND, LOW_HISTORY, ...
    actual_sales        NUMERIC(12,3),      -- backfilled
    actual_excess       NUMERIC(12,3),
    forecast_error      NUMERIC(12,3),
    abs_error           NUMERIC(12,3),

    UNIQUE (order_id, delivery_date, location_code, item_code)
);
CREATE INDEX idx_ol_lookup     ON core.order_line (delivery_date, location_code, item_code);
CREATE INDEX idx_ol_exceptions ON core.order_line USING gin(exception_flags);
CREATE INDEX idx_ol_pending    ON core.order_line (order_id) WHERE cx_at IS NULL;

-- =====================================================================
-- §4.7 Physical counts
-- =====================================================================
CREATE TABLE core.count_session (
    count_id        BIGSERIAL PRIMARY KEY,
    location_code   VARCHAR(10) NOT NULL REFERENCES core.location(location_code),
    count_type      VARCHAR(20) NOT NULL,      -- DAILY_EI | CYCLE | FULL
    business_date   DATE NOT NULL,
    started_at      TIMESTAMPTZ,
    submitted_at    TIMESTAMPTZ,
    submitted_by    BIGINT,
    status          VARCHAR(20) NOT NULL DEFAULT 'OPEN',
    UNIQUE (location_code, count_type, business_date)
);

CREATE TABLE core.count_line (
    count_id            BIGINT NOT NULL REFERENCES core.count_session(count_id) ON DELETE CASCADE,
    item_code           VARCHAR(20) NOT NULL REFERENCES core.item(item_code),
    counted_qty         NUMERIC(12,3),
    expected_qty        NUMERIC(12,3),          -- theoretical from ledger
    variance_qty        NUMERIC(12,3) GENERATED ALWAYS AS (counted_qty - expected_qty) STORED,
    variance_reason     VARCHAR(40),
    was_counted         BOOLEAN NOT NULL DEFAULT FALSE,   -- NOT the same as counted_qty = 0
    PRIMARY KEY (count_id, item_code)
);

-- was_counted is not redundant with counted_qty. A branch that counted zero and
-- a branch that skipped the item are different facts. See CLAUDE.md.

-- =====================================================================
-- §4.8 Integration and staging
-- (core.source_system already created above, ahead of core.item_alias)
-- =====================================================================

-- Saved column-mapping profiles make new file formats a config change, not a code change.
CREATE TABLE core.mapping_profile (
    profile_id      BIGSERIAL PRIMARY KEY,
    source_code     VARCHAR(30) NOT NULL REFERENCES core.source_system(source_code),
    profile_name    VARCHAR(80) NOT NULL,
    file_type       VARCHAR(20) NOT NULL,        -- DELIVERIES | SALES | END_INVENTORY | ITEM_MASTER
    column_map      JSONB NOT NULL,              -- {"Store":"location_code","Qty":"sales_qty",...}
    date_format     VARCHAR(30),
    header_row      SMALLINT DEFAULT 1,
    sheet_name      VARCHAR(80),
    transform_rules JSONB,                       -- trim, null-tokens ['-','','N/A'], multipliers
    is_active       BOOLEAN NOT NULL DEFAULT TRUE,
    UNIQUE (source_code, profile_name)
);

CREATE TABLE core.ingest_file (
    file_id         BIGSERIAL PRIMARY KEY,
    gcs_uri         TEXT NOT NULL,
    original_name   VARCHAR(255),
    source_code     VARCHAR(30) REFERENCES core.source_system(source_code),
    profile_id      BIGINT REFERENCES core.mapping_profile(profile_id),
    file_hash       CHAR(64),                    -- detect re-upload of identical file
    row_count       INTEGER,
    rows_accepted   INTEGER,
    rows_quarantined INTEGER,
    status          VARCHAR(20) NOT NULL DEFAULT 'PENDING',
    error_summary   JSONB,
    uploaded_by     BIGINT,
    uploaded_at     TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE core.ingest_quarantine (
    quarantine_id   BIGSERIAL PRIMARY KEY,
    file_id         BIGINT REFERENCES core.ingest_file(file_id),
    row_number      INTEGER,
    raw_payload     JSONB NOT NULL,
    error_code      VARCHAR(50) NOT NULL,
    error_detail    TEXT,
    resolved        BOOLEAN NOT NULL DEFAULT FALSE,
    resolved_by     BIGINT,
    resolved_at     TIMESTAMPTZ,
    resolution_note TEXT
);

CREATE TABLE stg.sales_event (
    stg_id          BIGSERIAL PRIMARY KEY,
    source_code     VARCHAR(30) NOT NULL,
    external_id     VARCHAR(120) NOT NULL,
    business_date   DATE NOT NULL,
    location_ref    VARCHAR(60) NOT NULL,        -- raw, pre-resolution
    item_ref        VARCHAR(200) NOT NULL,
    qty             NUMERIC(12,3) NOT NULL,
    occurred_at     TIMESTAMPTZ,
    raw_payload     JSONB,
    processed       BOOLEAN NOT NULL DEFAULT FALSE,
    processed_at    TIMESTAMPTZ,
    error_code      VARCHAR(50),
    UNIQUE (source_code, external_id)
);
CREATE INDEX idx_stg_unprocessed ON stg.sales_event (source_code) WHERE NOT processed;

-- Transactional outbox: reliable event publishing without distributed transactions.
CREATE TABLE core.outbox_event (
    event_id      BIGSERIAL PRIMARY KEY,
    event_type    VARCHAR(60) NOT NULL,         -- order.locked, order.submitted, item.updated
    payload       JSONB NOT NULL,
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    published_at  TIMESTAMPTZ,
    attempts      SMALLINT NOT NULL DEFAULT 0,
    last_error    TEXT
);
CREATE INDEX idx_outbox_pending ON core.outbox_event (created_at) WHERE published_at IS NULL;

CREATE TABLE core.webhook_subscription (
    subscription_id BIGSERIAL PRIMARY KEY,
    label           VARCHAR(80) NOT NULL,
    target_url      TEXT NOT NULL,
    event_types     TEXT[] NOT NULL,
    secret_hash     TEXT NOT NULL,
    is_active       BOOLEAN NOT NULL DEFAULT TRUE
);

-- =====================================================================
-- §4.9 Audit trail
-- =====================================================================
CREATE TABLE audit.record_change (
    audit_id        BIGSERIAL,
    occurred_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
    schema_name     VARCHAR(30) NOT NULL,
    table_name      VARCHAR(60) NOT NULL,
    record_pk       TEXT NOT NULL,
    action          audit_action NOT NULL,
    changed_by      BIGINT,
    changed_by_email VARCHAR(150),        -- denormalised: survives user deletion
    old_values      JSONB,
    new_values      JSONB,
    changed_fields  TEXT[],               -- computed, makes filtering cheap
    request_id      UUID,
    ip_address      INET,
    user_agent      TEXT,
    PRIMARY KEY (occurred_at, audit_id)
) PARTITION BY RANGE (occurred_at);

CREATE INDEX idx_audit_record ON audit.record_change (table_name, record_pk, occurred_at DESC);
CREATE INDEX idx_audit_user   ON audit.record_change (changed_by, occurred_at DESC);
CREATE INDEX idx_audit_fields ON audit.record_change USING gin(changed_fields);

CREATE TABLE audit.access_log (
    log_id      BIGSERIAL,
    occurred_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    user_id     BIGINT,
    action      audit_action NOT NULL,
    resource    VARCHAR(60),
    detail      JSONB,
    ip_address  INET,
    success     BOOLEAN NOT NULL DEFAULT TRUE,
    PRIMARY KEY (occurred_at, log_id)
) PARTITION BY RANGE (occurred_at);

-- Trigger-based capture. Applied below (after partitions exist) to every
-- master, reference and parameter table so application code cannot forget to
-- audit. fn_capture()'s TG_ARGV[0] pattern only supports a single-column
-- primary key, matching the spec's own example — the handful of tables with
-- composite keys (role_permission, uom_conversion, assortment_template_item,
-- item_location_param, delivery_schedule) are join/parameter tables whose
-- history is reconstructable from their parent entities, so they are left
-- unaudited for now rather than bending the function's contract.
CREATE OR REPLACE FUNCTION audit.fn_capture() RETURNS TRIGGER AS $$
DECLARE
    v_old JSONB := CASE WHEN TG_OP='INSERT' THEN NULL ELSE to_jsonb(OLD) END;
    v_new JSONB := CASE WHEN TG_OP='DELETE' THEN NULL ELSE to_jsonb(NEW) END;
BEGIN
    INSERT INTO audit.record_change(
        schema_name, table_name, record_pk, action,
        changed_by, changed_by_email, old_values, new_values, changed_fields, request_id)
    VALUES (
        TG_TABLE_SCHEMA, TG_TABLE_NAME,
        COALESCE(v_new->>TG_ARGV[0], v_old->>TG_ARGV[0]),
        TG_OP::audit_action,
        NULLIF(current_setting('app.user_id', true),'')::BIGINT,
        NULLIF(current_setting('app.user_email', true),''),
        v_old, v_new,
        CASE WHEN TG_OP='UPDATE' THEN
            ARRAY(SELECT key FROM jsonb_each(v_new)
                  WHERE v_new->key IS DISTINCT FROM v_old->key)
        END,
        NULLIF(current_setting('app.request_id', true),'')::UUID);
    RETURN COALESCE(NEW, OLD);
END $$ LANGUAGE plpgsql SECURITY DEFINER;

-- =====================================================================
-- §6.1 Bootstrap partitions
-- Rolling window: 3 months back through 6 months forward, plus a DEFAULT
-- catch-all per partitioned table so inserts never fail during development.
-- Replace with the scheduled "3 months ahead" job (§6.1) before production.
-- =====================================================================
DO $$
DECLARE
    d date := date_trunc('month', now() - interval '3 months');
    end_month date := date_trunc('month', now() + interval '6 months');
    tbl text;
BEGIN
    WHILE d <= end_month LOOP
        FOREACH tbl IN ARRAY ARRAY['core.stock_movement','core.fact_daily_store_item'] LOOP
            EXECUTE format(
                'CREATE TABLE IF NOT EXISTS %s_%s PARTITION OF %s FOR VALUES FROM (%L) TO (%L)',
                tbl, to_char(d,'YYYY_MM'), tbl, d, (d + interval '1 month')::date
            );
        END LOOP;
        d := d + interval '1 month';
    END LOOP;
END $$;

CREATE TABLE core.stock_movement_default PARTITION OF core.stock_movement DEFAULT;
CREATE TABLE core.fact_daily_store_item_default PARTITION OF core.fact_daily_store_item DEFAULT;

DO $$
DECLARE
    d date := date_trunc('month', now() - interval '3 months');
    end_month date := date_trunc('month', now() + interval '6 months');
    tbl text;
BEGIN
    WHILE d <= end_month LOOP
        FOREACH tbl IN ARRAY ARRAY['audit.record_change','audit.access_log'] LOOP
            EXECUTE format(
                'CREATE TABLE IF NOT EXISTS %s_%s PARTITION OF %s FOR VALUES FROM (%L) TO (%L)',
                tbl, to_char(d,'YYYY_MM'), tbl, d::timestamptz, (d + interval '1 month')::timestamptz
            );
        END LOOP;
        d := d + interval '1 month';
    END LOOP;
END $$;

CREATE TABLE audit.record_change_default PARTITION OF audit.record_change DEFAULT;
CREATE TABLE audit.access_log_default PARTITION OF audit.access_log DEFAULT;

-- =====================================================================
-- Audit triggers — every master/reference/parameter table (§4.9, §5.7 rule 2)
-- =====================================================================
CREATE TRIGGER trg_audit_item                AFTER INSERT OR UPDATE OR DELETE ON core.item                FOR EACH ROW EXECUTE FUNCTION audit.fn_capture('item_code');
CREATE TRIGGER trg_audit_item_category       AFTER INSERT OR UPDATE OR DELETE ON core.item_category       FOR EACH ROW EXECUTE FUNCTION audit.fn_capture('category_code');
CREATE TRIGGER trg_audit_item_price          AFTER INSERT OR UPDATE OR DELETE ON core.item_price          FOR EACH ROW EXECUTE FUNCTION audit.fn_capture('price_id');
CREATE TRIGGER trg_audit_uom                 AFTER INSERT OR UPDATE OR DELETE ON core.uom                 FOR EACH ROW EXECUTE FUNCTION audit.fn_capture('uom_code');
CREATE TRIGGER trg_audit_location            AFTER INSERT OR UPDATE OR DELETE ON core.location            FOR EACH ROW EXECUTE FUNCTION audit.fn_capture('location_code');
CREATE TRIGGER trg_audit_area                AFTER INSERT OR UPDATE OR DELETE ON core.area                FOR EACH ROW EXECUTE FUNCTION audit.fn_capture('area_code');
CREATE TRIGGER trg_audit_cluster             AFTER INSERT OR UPDATE OR DELETE ON core.cluster             FOR EACH ROW EXECUTE FUNCTION audit.fn_capture('cluster_code');
CREATE TRIGGER trg_audit_route               AFTER INSERT OR UPDATE OR DELETE ON core.route               FOR EACH ROW EXECUTE FUNCTION audit.fn_capture('route_code');
CREATE TRIGGER trg_audit_geography           AFTER INSERT OR UPDATE OR DELETE ON core.geography           FOR EACH ROW EXECUTE FUNCTION audit.fn_capture('geo_code');
CREATE TRIGGER trg_audit_location_closure    AFTER INSERT OR UPDATE OR DELETE ON core.location_closure    FOR EACH ROW EXECUTE FUNCTION audit.fn_capture('closure_id');
CREATE TRIGGER trg_audit_assortment_template AFTER INSERT OR UPDATE OR DELETE ON core.assortment_template FOR EACH ROW EXECUTE FUNCTION audit.fn_capture('template_code');
CREATE TRIGGER trg_audit_reason_code         AFTER INSERT OR UPDATE OR DELETE ON core.reason_code         FOR EACH ROW EXECUTE FUNCTION audit.fn_capture('reason_code');
CREATE TRIGGER trg_audit_param_set           AFTER INSERT OR UPDATE OR DELETE ON core.param_set           FOR EACH ROW EXECUTE FUNCTION audit.fn_capture('param_set_id');
CREATE TRIGGER trg_audit_source_system       AFTER INSERT OR UPDATE OR DELETE ON core.source_system       FOR EACH ROW EXECUTE FUNCTION audit.fn_capture('source_code');
CREATE TRIGGER trg_audit_mapping_profile     AFTER INSERT OR UPDATE OR DELETE ON core.mapping_profile     FOR EACH ROW EXECUTE FUNCTION audit.fn_capture('profile_id');
CREATE TRIGGER trg_audit_role                AFTER INSERT OR UPDATE OR DELETE ON core.role                FOR EACH ROW EXECUTE FUNCTION audit.fn_capture('role_code');
CREATE TRIGGER trg_audit_permission          AFTER INSERT OR UPDATE OR DELETE ON core.permission          FOR EACH ROW EXECUTE FUNCTION audit.fn_capture('permission_code');
CREATE TRIGGER trg_audit_app_user            AFTER INSERT OR UPDATE OR DELETE ON core.app_user            FOR EACH ROW EXECUTE FUNCTION audit.fn_capture('user_id');
CREATE TRIGGER trg_audit_webhook_subscription AFTER INSERT OR UPDATE OR DELETE ON core.webhook_subscription FOR EACH ROW EXECUTE FUNCTION audit.fn_capture('subscription_id');

-- Retention: audit partitions retained 24 months hot, then detached to Cloud
-- Storage as Parquet — a scheduled job, not part of this baseline (Milestone 12).

-- =====================================================================
-- §7.2 Row-level security
-- Only stock_movement is enabled here per the spec's own worked example.
-- Extending RLS to order_line and the rest of the scoped tables is Milestone 3
-- (Access), once the API's session-variable contract (app.location_scope,
-- app.unrestricted) is implemented end-to-end.
-- =====================================================================
ALTER TABLE core.stock_movement ENABLE ROW LEVEL SECURITY;

CREATE POLICY scope_by_location ON core.stock_movement
  FOR SELECT USING (
    current_setting('app.unrestricted', true) = 'on'
    OR location_code = ANY (string_to_array(current_setting('app.location_scope', true), ','))
  );

CREATE OR REPLACE VIEW core.v_user_effective_scope AS
SELECT us.user_id, l.location_code
  FROM core.user_scope us
  JOIN core.location l
    ON (us.scope_type='LOCATION' AND l.location_code = us.scope_value)
    OR (us.scope_type='AREA'     AND l.area_code     = us.scope_value)
    OR (us.scope_type='CLUSTER'  AND l.cluster_code  = us.scope_value)
    OR (us.scope_type='ROUTE'    AND l.route_code    = us.scope_value)
    OR (us.scope_type='ALL')
UNION
SELECT l.om_user_id, l.location_code
  FROM core.location l
 WHERE l.om_user_id IS NOT NULL;

COMMIT;
