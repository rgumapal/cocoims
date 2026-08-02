# Cocopan Inventory Management System (CIMS)
## Complete System Specification

**Version:** 3.3
**Supersedes:** SPEC v3.2
**Changes in 3.3:** Token CSS extracted to `frontend/src/design/tokens.css`
(§12.2 now carries the rationale and points at the file, same pattern as the
v3.1 DDL extraction — the CSS file is authoritative). Appendix CLAUDE.md
starter removed; the root `CLAUDE.md` is maintained directly and the copy
here had already drifted. No requirement changed.
**Changes in 3.2:** Added an implementation-status overview (§0) and a status
note on §13's API surface, reflecting what's actually built (Firebase auth,
dashboard, receiving/sales, Cloud Run deployment) vs. still spec-only
(forecast, replenishment, accuracy, integration layer). Documents reality;
no requirement changed.
**Changes in 3.1:** DDL extracted to `db/` — §4, §6.2–6.4 and §7.2 now carry the
rationale and point at the SQL that defines it, rather than duplicating it. The
SQL is authoritative; where this document and `db/` disagree, this document is
the bug. No requirement changed.
**Changes in 3.0:** supplies module deferred (no source data exists); Cocopan colours reduced to accent-only with full light/dark theming; roles restructured around real Cocopan positions with branch scope; branch lifecycle management and a complete reference-data catalogue added (§5).
**Target runtime:** Google Cloud Platform · Cloud SQL for PostgreSQL 16
**Intended use:** `docs/SPEC.md`. Referenced from `CLAUDE.md`.

---

## 0. How to use this document

This is a build specification. Sections 1–2 are domain context — read them before writing code, because the business logic is non-obvious and the vocabulary must match the client's exactly. Sections 4–11 are the buildable core. Section 12 is the design system and is **binding**, not suggestive. Section 14 defines done.

Rules marked **⚠️ CALIBRATE** are derived from the client's spreadsheet but the exact formula was not recoverable. Implement as configurable and fit against §14 AC-1.

### Implementation status

This spec describes the full intended system; the sections below are not
all built yet. Check here before assuming a section is live — this table
is maintained loosely (it will drift), `README.md`'s "What's actually built
right now" is the more current source when the two disagree.

| Section | Status |
|---|---|
| §4 Data model, §5 Branch/reference data | Built — full schema, RLS, RBAC. Onboarding wizard (§5.2) and assortment templates (§5.5) are not. |
| §7 Roles and permissions | Built — API-layer permission checks + DB-layer RLS, per §7.4. |
| §12 UX and design system | Built for every shipped screen (login, dashboard, items, branches, reference data, stock explorer, counts, receiving, sales, waste log, users & roles). |
| §13 API surface | Partial — see the status note at the top of that section. |
| §8 Forecast engine, §9 Replenishment engine, §10 Accuracy and bias | Not built. No calibration against §14 AC-1 has happened yet. |
| §11 Integration layer | Not built. Manual entry (receiving/sales/waste screens) covers the ledger for now instead. |
| Auth | Built, but not as specced in §7/§13: Firebase Auth (Google + email/password), admin-provisioned accounts only, not the bcrypt-only flow those sections describe. See CLAUDE.md's auth notes. |
| Deployment | Not in this spec at all — both services run on Cloud Run behind `cims.rgsuite.net`. See the `deploy` skill (`.claude/skills/deploy/`). |

---

## 1. Domain context

Cocopan is a Philippine bakery chain — ~122 branches across Metro Manila and Bulacan, founded 2022, targeting 1,000 stores by 2028. Bread is baked centrally at one commissary and delivered daily. Branches do not bake; they sell, count and reorder.

### The problem

Every day someone decides how many units of ~40 SKUs to send to each of ~122 branches — roughly 5,000 decisions. Today this happens in a 135-tab Excel workbook maintained by one analyst, emailed to Operations Managers for markup, and submitted to PPIC by 8 PM for next-day production.

| Measure | Current state |
|---|---|
| Excess (unsold) as % of deliveries | **15–16%** (daily range 12.4–22.1%) |
| Excess per store per day | **~103 units** (681 delivered / 578 sold) |
| Network beginning inventory, one week | **27,066 → 55,914** — stock accumulating |
| Worst SKU | Choco Roll **25.5%**; best is Glazed Donut **7.5%** |
| Forecast accuracy tracking | **None exists** |

**Root cause:** five sequential adjustments (safety stock, excess top-up, MOQ uplift, CX recommendation, OM top-up) that are nearly all additive. A sold-out is visible and blamed; excess is invisible and absorbed. Nothing measures the net effect.

### The two shelf-life regimes

Cocopan is migrating SKUs to machine-wrapped pillow packs, splitting the catalogue:

- **Same-day** (`Manual Packing`, shelf_life_days = 0) — newsvendor problem, no carryover
- **Multi-day** (`Machine - Wrapped`, `PD + 3` / `PD + 4`) — real inventory with ageing and FEFO

The current spreadsheet treats everything as same-day. **This is the mechanical cause of inventory accumulation.** Carryover logic is the highest-value code in this system.

### Glossary — use these exact terms in code, API and UI

| Term | Meaning |
|---|---|
| **DR** | Delivery Receipt — record of what shipped to a store |
| **Offtake** | Units sold at branch |
| **Excess** | Delivered but unsold |
| **EI** | End Inventory — stock counted at close |
| **PPIC** | Production Planning & Inventory Control — receives the final order |
| **CX** | Customer Experience team — reviews suggested orders |
| **OM** | Operations Manager — owns a group of stores |
| **SRP** | Suggested Retail Price |
| **MOQ** | Minimum Order Quantity |
| **PD** | Production Date |
| **Baseline Order** | First computed quantity, before adjustments |
| **Suggested Order** | System output after all rules |
| **CX Reco** | CX team's recommended override |
| **Final Order** | What is sent to PPIC |

---

## 2. Scope

### 2.1 In scope

**Inventory management**
- Item model for finished goods (bread, pastries, donuts)
- Immutable stock movement ledger — the single source of truth for all stock
- Physical counts, receiving, transfers, waste, adjustments
- Multi-location: commissary, branches, in-transit

**Replenishment and forecasting**
- Weekday-indexed forecasting with calendar overlays and censored-demand correction
- Dual replenishment policy: same-day newsvendor vs multi-day carryover
- The order ladder, persisted step by step
- Exception workbench with reason-coded overrides

**Administration**
- Full CRUD on every master and reference table
- Role-based access control with data scoping
- User and permission management
- Complete audit trail on every mutation
- Configurable, effective-dated parameters

**Integration**
- File ingestion (CSV/XLSX) with reusable column-mapping profiles
- REST API with service accounts for POS/ERP integration
- Staging layer with idempotent upserts
- Outbound webhooks for downstream systems

### 2.2 Out of scope

Financial accounting and statutory inventory valuation · payroll and HR · POS replacement · commissary production scheduling (PPIC's system) · dealer billing (design for, build later)

**Deferred — supplies, packaging and ingredients.** No source data for these exists in anything the client has shared, so building the module now would mean creating a catalogue and count discipline at 122 branches before a single number could be produced. The data model below keeps `item_type` and the ledger generic so supplies can be switched on later without migration, but nothing in v1 depends on them. Raise it as a phase 2 conversation, not a v1 scope item.

---

## 3. Architecture

| Layer | Choice | Rationale |
|---|---|---|
| Database | **Cloud SQL for PostgreSQL 16** | Specified. `db-custom-4-15360` for pilot |
| Backend | **Python 3.12 + FastAPI** | Forecasting benefits from pandas/numpy |
| ORM / migrations | **SQLAlchemy 2.x + Alembic** | |
| Batch | **Cloud Run Jobs + Cloud Scheduler** | Nightly ingest, rollups, order generation |
| API | **Cloud Run** | |
| Files | **Cloud Storage** | Upload landing, triggers ingestion |
| Cache | **Memorystore (Redis)** | Session, permission cache, hot reference data |
| Secrets | **Secret Manager** | |
| Frontend | **React 18 + Vite + TypeScript**, TanStack Table + Query, Tailwind | Dense grids need TanStack Table |

**Connectivity:** Cloud Run → Cloud SQL via Auth Proxy Unix socket (`/cloudsql/PROJECT:REGION:INSTANCE`). No public IP. PgBouncer in transaction mode for connection pooling.

### Repository layout

```
cocopan-ims/
├── CLAUDE.md
├── docs/SPEC.md
├── backend/
│   ├── app/
│   │   ├── api/v1/            # routers by resource
│   │   ├── domain/
│   │   │   ├── forecast.py
│   │   │   ├── replenishment.py    # the ladder
│   │   │   ├── ledger.py           # stock movements
│   │   │   └── accuracy.py
│   │   ├── auth/              # RBAC, scoping, RLS session vars
│   │   ├── ingest/            # parsers, mapping profiles, DQ
│   │   ├── integration/       # adapters, staging, webhooks, outbox
│   │   ├── models/
│   │   └── jobs/
│   ├── alembic/
│   └── tests/
├── frontend/
│   └── src/
│       ├── design/            # tokens.css — §12
│       ├── components/
│       └── routes/
└── db/{ddl,seed,perf}/
```

---

## 4. Data model

The schema is authored as plain SQL in `db/`, not generated from ORM models: it
uses partitioned tables, generated columns, exclusion constraints, row-level
security and triggers, none of which SQLAlchemy autogenerate produces reliably.

**This section is the rationale; `db/` is the definition.** Where the two
disagree the SQL wins and this section is the bug. Every file in `db/` carries
`-- §X.Y` banner comments matching the subsection headings below, so each
subsection here maps to a greppable anchor there.

| Subsection | Contents | Defined in |
|---|---|---|
| 4.1 | Enums | `db/ddl/001_schema.sql § 4.1` |
| 4.2 | Identity, RBAC, scoping, API keys | `db/ddl/001_schema.sql § 4.2` |
| 4.3 | Item, location, geography, calendar, assortment, reason codes | `db/ddl/001_schema.sql § 4.3` |
| 4.4 | `core.stock_movement` — the ledger | `db/ddl/001_schema.sql § 4.4` |
| 4.5 | `core.fact_daily_store_item` — the daily rollup | `db/ddl/001_schema.sql § 4.5` |
| 4.6 | Params, forecast runs, order header and line | `db/ddl/001_schema.sql § 4.6` |
| 4.7 | Count sessions and lines | `db/ddl/001_schema.sql § 4.7` |
| 4.8 | Source systems, mapping profiles, staging, outbox, webhooks | `db/ddl/001_schema.sql § 4.8` |
| 4.9 | Audit tables, capture trigger, retention | `db/ddl/001_schema.sql § 4.9` |
| 6.2 / 6.4 | `rpt.agg_location_item_dow`, materialised views | `db/ddl/002_rpt.sql` |
| 6.3 | Performance indexes | `db/perf/001_indexes.sql` |
| — | RBAC seed: roles, permissions, reason codes, param sets | `db/seed/001_seed.sql` |
| — | Client item and branch master | `db/seed/002_client_data.sql` |
| 4.3 | `item_price.location_code` / `price_status`, `core.v_effective_price`, `app_user.role_hint` | `backend/alembic/versions/0002_*.py` |

`db/ddl` holds the baseline only — it is what a fresh container bootstraps, and
it matches Alembic revision `0001`. Anything added after that is an incremental
migration, so a handful of objects are defined in `backend/alembic/versions/`
rather than `db/ddl` (the last row above). Run `alembic upgrade head` to reach
current state; grep both places when hunting for a definition.

**Conventions:** `snake_case`; natural keys on dimensions, `BIGSERIAL` on facts;
all timestamps `TIMESTAMPTZ`; money `NUMERIC(12,2)`; quantities `NUMERIC(12,3)`
in the ledger (keeps it generic for future item types), `INTEGER` on
finished-goods orders. Four schemas: `core` (business data), `audit` (audit
trail), `stg` (integration staging), `rpt` (rollups and materialised views).

The rules below are the parts a reader cannot recover from the DDL alone.

### 4.1 Enums

Fifteen enums cover item type and status, packaging, location type/format/status,
replenishment policy, movement type, order status, excess source and audit
action. `item_type` includes `SUPPLY`, `PACKAGING`, `RAW_MATERIAL` and
`INGREDIENT` for forward compatibility only — v1 seeds `FINISHED_GOOD` alone
(§2.2).

### 4.2 Identity, RBAC and scoping

Permissions are `resource.action` strings (`item.create`, `order.submit_ppic`).
A user's authority is the intersection of their permissions and their branch
scope; both are enforced, neither substitutes for the other (§7.4).

`permission.is_destructive` drives the typed-confirmation dialog in the UI, so
destructiveness is data rather than a hard-coded list in the frontend.

**Row-level security.** Scoped tables enable RLS so data scoping is enforced in
the database, not only in application code. The policy reads
`app.location_scope` and `app.unrestricted`, which the API sets per request from
the authenticated session. A bug in a router cannot leak another OM's stores.

RLS is required on `core.stock_movement` **and** `core.order_line` — §7.2 rule 3
scopes writes as well as reads, and AC-3 verifies it with the API bypassed.

### 4.3 Master data

**Items.** `is_orderable` is a generated column derived from `lifecycle_status`,
never set by hand. `shelf_life_days = 0` means same-day; anything higher means
the item carries over, and a check constraint ties `MULTI_DAY` policy to a
non-zero shelf life so the two cannot drift apart.

`desc_dr` and `desc_offtake` exist because the Delivery Receipt and the sales
system name the same item differently; `core.item_alias` resolves further
variants per source system. Do not collapse these into one name — ingestion
depends on matching the source's vocabulary.

**Prices.** `core.item_price` is effective-dated, and `location_code` is
nullable: NULL is the network price applying to every branch, a non-null row is
a branch-specific override that takes precedence. This exists because the source
workbook shows conflicting SRPs for the same item (Double Cheese Roll 15 vs 18)
and it is not yet confirmed whether that is a genuine per-branch price
(concession vs standalone, NCR vs provincial) or a data-entry inconsistency. The
schema supports either answer without a later migration. See §16 open item 2.

Application code reads `core.v_effective_price`, never `item_price` directly, so
the branch-then-network fallback lives in one place.

**Locations** unify branches, commissary and warehouses. `is_active` and
`is_orderable` are generated from `status` — see §5.1 for the lifecycle and why
this prevents a closed branch from silently continuing to receive deliveries.
`parent_location_code` models a concession inside a host, which is what lets
host closures cascade (§5.3).

**Closures.** `core.location_closure` rows with `exclude_from_forecast` remove
dates from reference windows entirely. A closed day is an absence, not a zero —
this is the single most consequential reference-data rule in the system (§5.3).

### 4.4 The stock ledger — core of the system

All stock changes for all item types are recorded as immutable movements in one
append-only ledger. Balances are derived, never stored as mutable running
totals. This makes every balance explainable and eliminates the class of bug
where a stored quantity drifts from its history.

`production_date` and `expiry_date` on the movement are what make FEFO and
ageing possible, and therefore what make carryover (§9 step 6) possible.

`idempotency_key` carries a unique partial index, so replaying an ingestion is
safe by construction rather than by convention.

> **Immutability.** No `UPDATE` or `DELETE` grants on `stock_movement`.
> Corrections are new offsetting movements with `reason_code = 'CORRECTION'`.
> This makes the ledger legally and operationally defensible, and is what allows
> the audit trail to be trusted.

### 4.5 Derived daily fact — the replenishment working table

`core.fact_daily_store_item` is a **rollup projected from the ledger**, rebuilt
nightly. It exists because the forecast and ladder need fast weekday-indexed
reads, and scanning the raw ledger for four weeks of history across 122 stores
on every order run would not meet the batch window.

`ei_reported` separates a counted zero from an absent count; `excess_source`
records whether excess was counted or derived; `is_store_open` is derived from
closures during the rollup.

> **DQ rule, absolute:** the quantity columns are nullable on purpose. The source
> workbook mixes blanks, `0`, `-` and `-` with trailing whitespace in the same
> row. **Never coerce NULL to 0.** Blank, zero and not-counted are three
> different facts, and conflating them is why the client's end-inventory data is
> currently unusable.

### 4.6 Replenishment

`core.param_set` is effective-dated and scoped (`GLOBAL | CLUSTER | LOCATION |
ITEM | CATEGORY`), so a parameter change is a new row and never an overwrite.
`carryover_enabled` is the feature flag that keeps AC-1 reproducible: the
client's as-is baseline runs with it false.

`ref_week_flags` selects which of weeks 1..4 participate in the reference
window, per weekday. This is why `rpt.agg_location_item_dow` stores weeks
separately instead of pre-averaged (§6.2).

**`core.order_line` is the ladder.** Its column names mirror the client's
spreadsheet headers deliberately — `ave_deliveries`, `ave_sales`, `ave_excess`,
`baseline_order`, `moq_uplift`, `suggested_order_wo_ei`, `cx_reco`,
`final_order`. Do not rename them for elegance; adoption depends on the
vocabulary matching what people already read every day. Every intermediate value
is persisted, which is what makes the Ladder Trace (§12.4) possible.

### 4.7 Physical counts

> `was_counted` is not redundant with `counted_qty`. A branch that counted zero
> and a branch that skipped the item are different facts, and conflating them is
> precisely what makes the client's current end-inventory data unusable.

`variance_qty` is generated from counted minus expected, so it cannot be
recorded inconsistently with its inputs.

### 4.8 Integration and staging

Every inbound path lands in `stg`, resolves references, then writes to the
ledger — never directly from an external payload to a fact table (§11).

`core.mapping_profile.column_map` and `transform_rules` make a new file layout a
config change rather than a deployment. `transform_rules` carries the null-token
list (`['', '-', 'N/A', 'null']`), which is where the NULL-is-not-zero rule is
enforced at the boundary.

`core.outbox_event` is a transactional outbox: events are written in the same
transaction as the business change, then published separately. This gives
reliable publishing without distributed transactions.

### 4.9 Audit trail

`audit.fn_capture()` is applied as a trigger to every master, reference and
parameter table, so application code cannot forget to audit. It records
before/after JSONB plus a computed `changed_fields` array, which makes filtering
by "what changed" cheap.

`changed_by_email` is denormalised on purpose: the audit record must survive
deletion or anonymisation of the user it refers to.

The API must set `app.user_id`, `app.user_email` and `app.request_id` at the
start of every transaction. **A write without session context is a bug** — add a
guard that rejects it in non-migration contexts.

**Retention:** audit partitions retained 24 months hot, then detached to Cloud
Storage as Parquet.

---

## 5. Branch and reference data management

At Cocopan's growth rate — ~122 branches today, targeting 1,000 by 2028 — **opening a branch is the most frequent master-data operation in the system**, not an occasional admin task. It must be a guided workflow, not CRUD scattered across five screens. Equally, a branch that closes for a day and is handled carelessly will quietly corrupt the forecast.

### 5.1 Branch lifecycle

| Status | Meaning | Orderable | Counted in network KPIs | Forecast treatment |
|---|---|---|---|---|
| `PLANNED` | Site identified, not built | No | No | — |
| `PRE_OPENING` | Fitting out; opening stock needed | **Yes** | No | Cluster analog only |
| `RAMP_UP` | Trading, within `ramp_weeks` | Yes | Yes, flagged | Blend cluster analog → own history |
| `ACTIVE` | Normal trading | Yes | Yes | Own history |
| `TEMP_CLOSED` | Short closure | No | Excluded for closed days | Days excluded from reference window |
| `RENOVATION` | Extended closure | No | Excluded | Days excluded; ramp restarts on reopen |
| `RELOCATED` | Moved to a new code | No | No | History transfers to `relocated_to` |
| `CLOSED` | Permanently shut | No | No | History retained for cluster analogs |

Rules:

- **Status is never overwritten silently.** Every transition writes `location_status_history` with effective dates. Forecasting must be able to ask what a branch *was* on any past date, not just what it is now.
- `is_active` and `is_orderable` are **generated columns**, never set by hand. This prevents the classic bug where a closed branch keeps receiving deliveries because someone forgot a checkbox.
- `PRE_OPENING` is orderable on purpose — a new branch needs opening stock before it has sold anything.
- Reopening from `RENOVATION` restarts the ramp window. A branch shut for six weeks does not resume at its old volumes.

### 5.2 New branch onboarding

A single guided flow. Target: **under five minutes, one screen, no prior system knowledge.**

```
1  Identity        code, name, format (standalone / concession / kiosk)
2  Geography       region → province → city → barangay, address, coordinates
3  Operations      cluster, area, route, operating hours, planned open date
4  Ownership       assign Operations Manager   → grants branch scope automatically
5  Assortment      pick template (pre-filled from format + cluster) → review & adjust
6  Schedule        delivery days per SKU, inherited from template
7  Forecast basis  confirm cluster analog + ramp weeks
8  Go live         status → PRE_OPENING, opening order generated
```

Design notes:

- **Step 5 is the one that must not be manual.** Applying an assortment template writes all `item_location_param` and `delivery_schedule` rows at once. Any subsequent divergence sets `is_overridden = true`, so drift from the template stays visible.
- Step 4 is the only access-control action needed. Because `location.om_user_id` grants scope, no separate permission step exists.
- The wizard is resumable — a `PLANNED` branch can sit half-configured for weeks.
- Bulk import for multi-store openings, using the same validation as the wizard.

### 5.3 Closures — the quiet forecast killer

If a branch is closed on a Tuesday and records zero sales, a naive weekday average treats that as genuine zero demand and under-orders every following Tuesday. **The client's current spreadsheet has no closure concept at all**, which means this error is almost certainly present in their live numbers today.

Requirements:

- `location_closure` rows with `exclude_from_forecast = true` remove those dates from reference windows entirely — they are not zeros, they are absences.
- `fact_daily_store_item.is_store_open` is derived from closures during the nightly rollup.
- `obs_count` decrements accordingly, and a line whose window collapses below `min_observations` falls back to cluster analog with `confidence_flag = LOW_HISTORY`.
- Concessions inherit host closures: if the host supermarket shuts, so does the concession. Model with `parent_location_code` and cascade automatically.
- Half-day closures (`is_full_day = false`) scale rather than exclude the observation.

**Show closures on the order screen.** A planner looking at an unexpectedly small suggestion must be able to see instantly that the branch was shut last Tuesday.

### 5.4 Reassignment, relocation and closure

| Operation | Behaviour |
|---|---|
| **Reassign OM** | Update `location.om_user_id`. Access moves immediately; old OM loses it. Audited. |
| **Change cluster** | Affects forecasting for new stores only; existing history is unaffected. Requires a reason. |
| **Change route** | Takes effect from the next order run, never mid-run on a locked order. |
| **Relocate** | Create the new code, set `relocated_to` on the old, transfer assortment. Sales history links through for forecasting continuity. |
| **Close** | Status `CLOSED` with an effective date. Blocks ordering, retains all history. **Never delete a branch** — its history feeds cluster analogs for future openings. |

### 5.5 Assortment management

Not every branch carries every SKU. A supermarket concession, a transport-hub kiosk and a 24-hour residential store are different businesses.

- **Templates by format × cluster**, with one marked default.
- **Apply, review, diverge** — a template application is a suggestion the OM can adjust, with divergence tracked.
- **Bulk assortment changes**: adding a new SKU to all `HIGH_TRAFFIC_24H` branches is one operation, not 40.
- **De-listing at branch level** sets `is_stocked = false`; it does not delete the row, so history survives.
- **`display_capacity`** caps the suggested order. A branch cannot merchandise 60 pan de coco on a shelf that holds 30, and ordering beyond capacity is guaranteed waste.

### 5.6 Reference data catalogue

Every reference table, its owner, and its deletion policy. **No reference table permits hard delete where transactional history exists** — deactivation only.

| Table | Purpose | Managed by | Delete policy |
|---|---|---|---|
| `core.item` | Product master | Planner, Sys Admin | Soft — `DELISTED` |
| `core.item_category` | Category hierarchy | Planner | Soft — blocked if items exist |
| `core.item_alias` | DR ↔ Offtake name mapping | Planner | Hard — aliases are disposable |
| `core.item_price` | Effective-dated SRP and cost | Finance, Sys Admin | Hard on future rows only |
| `core.uom_conversion` | Pack conversions | Planner | Hard if unused |
| `core.uom` | Unit codes | Sys Admin | Soft |
| `core.location` | Branch master | Planner, Sys Admin | **Never** — status `CLOSED` |
| `core.location_status_history` | Branch lifecycle trail | System | **Never** — append-only |
| `core.location_closure` | Day-level closures | OM, Planner | Hard before effective date only |
| `core.geography` | PH region/province/city/barangay | Sys Admin | Soft |
| `core.area` | Operational areas | Planner | Soft — blocked if branches assigned |
| `core.cluster` | Forecast analog groups | Planner | Soft — blocked if branches assigned |
| `core.route` | Delivery routes | Planner | Soft |
| `core.assortment_template` | Branch assortment sets | Planner | Soft |
| `core.assortment_template_item` | Template contents | Planner | Hard |
| `core.item_location_param` | Per-branch par, MOQ, capacity | Planner, OM | Soft — `is_stocked = false` |
| `core.delivery_schedule` | SKU × branch × weekday | Planner | Hard |
| `core.calendar` | Dates, paydays, holidays, seasons | Sys Admin | **Never** |
| `core.calendar_location_event` | Local events, fiestas, promos | OM, Planner | Hard before effective date |
| `core.reason_code` | Override, waste, adjustment reasons | Sys Admin | Soft — never hard, history references them |
| `core.param_set` | Forecast and ladder parameters | Planner | **Never** — effective-dated, superseded |
| `core.source_system` | Integration sources | Sys Admin | Soft |
| `core.mapping_profile` | File column mappings | Sys Admin, Planner | Soft |
| `core.role` / `permission` | Access definitions | Sys Admin | Soft — system roles locked |
| `core.app_user` | Users | Sys Admin | Soft — deactivate; audit references persist |

### 5.7 Governance rules for all reference data

1. **Every table gets full CRUD UI.** No reference data may require a database console or a developer. This is the difference between a system operations owns and one it depends on IT for.
2. **Every mutation is audited** via the trigger in §4.9, including who and from where.
3. **Referential deactivation, not deletion.** Attempting to delete a referenced row returns a clear message naming what depends on it — never a raw foreign-key error.
4. **Effective dating** on anything that changes the maths: prices, parameters, assortments, branch status. Never overwrite history.
5. **Bulk operations** on every reference table: import, export, and multi-select edit. At 1,000 branches, row-by-row administration does not scale.
6. **Search everywhere.** Trigram and full-text search on items and branches; users will search by partial name, not by code.
7. **Templates over repetition.** Assortment templates, parameter sets and mapping profiles all exist so that the common case is one action.
8. **Validation at write, not at read.** A branch cannot go `ACTIVE` without a cluster, route, OM and assortment. Enforce it at the transition, not by producing a broken forecast later.

---

## 6. Performance design

This is a small-data, high-read system: ~122 locations × ~40 SKUs × 4 days = ~19,500 order lines per run. It must feel instant. The techniques below matter more than raw instance size.

### 6.1 Partitioning

| Table | Strategy |
|---|---|
| `core.stock_movement` | RANGE monthly on `business_date` |
| `core.fact_daily_store_item` | RANGE monthly on `business_date` |
| `audit.record_change` | RANGE monthly on `occurred_at` |
| `audit.access_log` | RANGE monthly on `occurred_at` |

Automate partition creation three months ahead with a scheduled job. Detach and archive partitions older than 24 months.

### 6.2 Precomputed weekday aggregates — the key optimisation

The forecast needs, for every (location, item, weekday), the mean of the last N
same-weekday observations. Computing that at order time means scanning four
weeks of history per line. **Precompute it nightly instead** —
`rpt.agg_location_item_dow`, defined in `db/ddl/002_rpt.sql § 6.2`.

Weeks are stored separately (`weeks_back` 1..4) rather than pre-averaged, so any
window can be assembled at read time from `param_set.ref_week_flags`.
Pre-averaging would bake one window into the data and make calibration against
the client's workbook impossible.

Order generation then becomes a **single set-based SQL statement** joining this
table, not a Python loop over 19,500 lines. Target: full network run under 10
seconds.

> Do not implement the ladder as a per-row Python loop with per-row queries.
> That is the difference between a 10-second run and a 20-minute one.

### 6.3 Indexing

Defined in `db/perf/001_indexes.sql`. The access-path story:

| Index | Table | Why |
|---|---|---|
| `idx_ol_grid` | `order_line` | Covering — the workbench grid reads index-only and never touches the heap |
| `idx_ol_needs_review` | `order_line` | Partial — the default filter is flagged-and-unreviewed, a small slice |
| `idx_movement_brin` | `stock_movement` | BRIN suits an append-only, date-correlated table; tiny where btree would rival the table |
| `idx_movement_lookup` | `stock_movement` | Point lookups for Stock Explorer and the FEFO balance walk |
| `idx_item_price_lookup` | `item_price` | Serves `v_effective_price`'s branch-then-network fallback |

Indexes that enforce a constraint or serve a single defined lookup path live
with their table in `db/ddl/001_schema.sql` instead.

### 6.4 Materialised views for dashboards

`rpt.mv_daily_network` is defined in `db/ddl/002_rpt.sql § 6.4`, with a unique
index so the nightly job can `REFRESH MATERIALIZED VIEW CONCURRENTLY` without
taking a lock the dashboard would block on.

Also specified, in prose only, and built alongside the Accuracy work rather than
guessed at now: `mv_item_performance` (excess % and rank per SKU),
`mv_location_scorecard` (bias, WAPE, excess % per store) and `mv_current_stock`
(ledger balance per location/item with FEFO ageing buckets).

### 6.5 Other measures

- **PgBouncer** transaction pooling; Cloud Run instances are ephemeral and would otherwise exhaust connections
- **Redis** caches the permission set and reference tables (items, locations) — invalidate on write via outbox
- `NUMERIC(12,3)` not `FLOAT` for quantities; never compare money or stock with floating point
- Bulk ingestion via `COPY` into staging, then set-based `INSERT ... ON CONFLICT`
- Cursor-based pagination on all list endpoints; never `OFFSET` on large tables
- `pg_stat_statements` enabled; alert on any statement exceeding 500 ms

---

## 7. Roles and permissions

Roles map to **actual Cocopan positions**, not abstract system tiers. A person's authority is the intersection of two things: what their job lets them *do*, and which branches they are responsible *for*. Both are enforced.

### 7.1 Roles by position

| Role | Cocopan position | Default scope | Core responsibility |
|---|---|---|---|
| `SYS_ADMIN` | IT / systems | All | Configuration, users, integrations |
| `DEMAND_PLANNER` | Demand planning analyst | All | Owns order runs, forecast and parameters |
| `CX_SPECIALIST` | Customer Experience team | All | Reviews and recommends order adjustments |
| `OPS_MANAGER` | Operations Manager (OM) | Assigned branches | Final order adjustment for own branches |
| `AREA_HEAD` | Area / Regional head | Assigned area | Oversight across several OMs |
| `STORE_HEAD` | Store Head | Own branch | Counts, receiving, waste, branch review |
| `STORE_TEAM` | Store Team Member | Own branch | Count and waste capture only |
| `PPIC_PLANNER` | PPIC | All (read-mostly) | Receives and confirms production requirement |
| `COMMISSARY_SUPERVISOR` | Production supervisor | Commissary | Production receipts, dispatch confirmation |
| `FINANCE_ANALYST` | Finance | All (read-only) | Cost, waste valuation, analytics |
| `EXECUTIVE` | CFO / leadership | All (read-only) | Dashboards and scorecards |
| `INTEGRATION` | Service account | Configured | API ingestion only |

> One person may hold more than one role. Effective permissions are the **union** of their roles; effective data scope is the **union** of their scopes. A Store Head covering two branches during a vacancy needs no special handling — grant a second scope row.

### 7.2 Branch scope model

```sql
-- scope_type: LOCATION | ROUTE | AREA | CLUSTER | ALL
-- Effective scope = explicit user_scope rows
--                 ∪ locations where location.om_user_id = user_id
```

Rules:

1. **Scope is deny-by-default.** A user with no scope row and no `ALL` grant sees nothing. There is no implicit "everything" fallback.
2. **OM assignment on `core.location` grants scope automatically.** Reassigning a branch to a new OM moves access with it — no second administrative step, no stale permissions when someone changes area.
3. **Scope applies to reads *and* writes.** An OM can adjust order lines only for branches in scope, enforced by RLS on `core.order_line` and `core.stock_movement`.
4. **Aggregate views respect scope.** An Area Head's dashboard totals cover their area only. Network figures require an `ALL` scope.
5. **Branch users are pinned to one location** by convention, but the model does not forbid more — vacancy cover is a real operational need.

`core.v_user_effective_scope` (defined in `db/ddl/001_schema.sql § 7.2`) unions
the explicit `user_scope` rows with every location whose `om_user_id` is the
user — which is what makes OM assignment grant access with no second
administrative step.


The API resolves this once per session, caches it in Redis, and sets `app.location_scope` on every transaction for RLS.

### 7.3 Permission matrix (abridged — seed the full set)

| Permission | SYS_ADMIN | DEMAND_PLANNER | CX | OPS_MGR | AREA_HEAD | STORE_HEAD | STORE_TEAM | PPIC | FINANCE |
|---|:-:|:-:|:-:|:-:|:-:|:-:|:-:|:-:|:-:|
| `item.read` | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |
| `item.create` / `item.update` | ✓ | ✓ | — | — | — | — | — | — | — |
| `item.delete` | ✓ | — | — | — | — | — | — | — | — |
| `item.price.update` | ✓ | — | — | — | — | — | — | — | ✓ |
| `location.read` | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |
| `location.create` / `location.update` | ✓ | ✓ | — | — | — | — | — | — | — |
| `location.status_change` | ✓ | ✓ | — | — | — | — | — | — | — |
| `location.assign_om` | ✓ | ✓ | — | — | ✓ | — | — | — | — |
| `location.closure.manage` | ✓ | ✓ | — | ✓ | ✓ | — | — | — | — |
| `assortment.manage` | ✓ | ✓ | — | ✓* | — | — | — | — | — |
| `refdata.manage` | ✓ | ✓ | — | — | — | — | — | — | — |
| `param.read` | ✓ | ✓ | ✓ | ✓ | ✓ | — | — | — | ✓ |
| `param.update` | ✓ | ✓ | — | — | — | — | — | — | — |
| `order.read` | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | — | ✓ | ✓ |
| `order.generate` | ✓ | ✓ | — | — | — | — | — | — | — |
| `order.adjust_cx` | ✓ | ✓ | ✓ | — | — | — | — | — | — |
| `order.adjust_om` | ✓ | ✓ | — | ✓ | ✓ | — | — | — | — |
| `order.lock` | ✓ | ✓ | — | — | — | — | — | — | — |
| `order.submit_ppic` | ✓ | ✓ | — | — | — | — | — | — | — |
| `order.confirm_production` | ✓ | — | — | — | — | — | — | ✓ | — |
| `count.submit` | ✓ | — | — | ✓ | — | ✓ | ✓ | — | — |
| `count.approve` | ✓ | — | — | ✓ | ✓ | ✓ | — | — | — |
| `receiving.confirm` | ✓ | — | — | ✓ | — | ✓ | ✓ | — | — |
| `waste.record` | ✓ | — | — | ✓ | — | ✓ | ✓ | — | — |
| `movement.adjust` | ✓ | ✓ | — | ✓ | — | — | — | — | — |
| `accuracy.read` | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | — | ✓ | ✓ |
| `user.manage` / `role.manage` | ✓ | — | — | — | — | — | — | — | — |
| `audit.read` | ✓ | ✓ | — | — | — | — | — | — | ✓ |
| `integration.manage` | ✓ | — | — | — | — | — | — | — | — |
| `export.data` | ✓ | ✓ | ✓ | ✓ | ✓ | — | — | ✓ | ✓ |

\* OMs may adjust assortment for branches in scope only.

`EXECUTIVE` = read-only across `order.read`, `accuracy.read`, `item.read`, `location.read`. `COMMISSARY_SUPERVISOR` = `order.read`, `receiving.confirm`, `movement.adjust` scoped to the commissary.

### 7.4 Enforcement rules

- **Deny by default.** Absent permission returns 403; absent scope returns an empty result, never another branch's data.
- **Two layers, both mandatory.** API checks the permission; Postgres RLS enforces the scope. Neither substitutes for the other.
- **Destructive actions** (`permission.is_destructive`) require typed confirmation in the UI and always write an audit record.
- **No hard deletes on master data.** `item.delete` sets `lifecycle_status = 'DELISTED'`. Physical deletion is blocked wherever transactional history exists.
- **Separation of duties:** the user who records a stock adjustment cannot approve their own count variance above a configurable threshold. Enforce in the service layer, not the UI.
- **Store Team is capture-only by design.** Given daily-rate, high-turnover branch staff, the safest posture is that they can enter observations but never change an order.

## 8. Forecast engine

Module: `backend/app/domain/forecast.py`

### 8.1 `WEEKDAY_AVG_V1` (default)

```
for each (location, item, target_date):
    dow = ISO weekday(target_date)
    weeks = [k for k in 1..4 if param.ref_week_flags[k][dow]]
    agg = rpt.agg_location_item_dow rows for (location,item,dow,weeks)

    if sum(agg.obs_count) >= param.min_observations:
        forecast = weighted_mean(agg.ave_demand_est, weights = obs_count)
        confidence = OK
    else:
        forecast = cluster_analog(location.cluster, item, dow)
        confidence = LOW_HISTORY | NEW_STORE
```

### 8.2 Rules

- A missing row is **not** zero sales. Exclude it and decrement `obs_count`.
- Exclude closed-store days (`core.location_closure` with `exclude_from_forecast`) and non-deliverable days. A closure is an **absence**, not a zero — see §5.3.
- Exclude outliers beyond 3 MAD from the median, but **log the exclusion** — a fiesta spike may be signal, not noise.
- Persist `obs_count` on every line. An average built on one observation must be visibly distinct from one built on four.

### 8.3 Calendar overlays

Multiply by factors for payday, holiday, season and weather, fitted from history where sufficient data exists, otherwise from a seeded default table. Store applied factors on the forecast line so the number stays explainable.

### 8.4 Censored demand

Where `sold_out_flag` is true, sales understate demand. Compute `demand_estimate = sales_qty × uplift(sell_out_hour, closing_hour)` and forecast on that. **This replaces the client's blunt "+10% if it ran out two days running" rule with a measured correction.**

### 8.5 New stores

Assign a `cluster` (`TRANSPORT_HUB`, `RESIDENTIAL`, `SUPERMARKET_CONCESSION`, `HIGH_TRAFFIC_24H`). Use the cluster's per-item, per-weekday mean scaled by the store's observed basket index, blending to own history linearly over 8 weeks.

---

## 9. Replenishment engine

Module: `backend/app/domain/replenishment.py`. Persist every intermediate value — this is the primary trust mechanism for adoption.

```
STEP 0  GATE
        skip if not location.is_orderable            # PRE_OPENING | RAMP_UP | ACTIVE
        skip if location closed on delivery_date
        skip if not item.is_orderable
        skip if not delivery_schedule.is_deliverable(location, item, dow)
        skip if not item_location_param.is_stocked

STEP 1  BASELINE ORDER
        baseline_order = forecast_qty

STEP 2  ADJUSTMENT                                    # ⚠️ CALIBRATE
        with_excess_flag = (ave_excess > 0)
        pct = with_excess_flag
              ? (ave_sales <= topup_threshold_units ? topup_pct_low : topup_pct_high)
              : safety_stock_pct                       # client default 0.05
        adjustment = baseline_order * pct

STEP 3  net_of_adjustment = baseline_order + adjustment

STEP 4  MOQ UPLIFT
        effective_moq = coalesce(item_location_param.moq_override, item.moq)
        if moq_trigger_enabled and not item.moq_exempt
           and 0 < net_of_adjustment < max(effective_moq, moq_trigger_qty):
              moq_uplift = max(effective_moq, moq_trigger_qty) - ceil(net_of_adjustment)
        if effective_moq > ave_sales * moq_demand_multiple:
              flag(MOQ_EXCEEDS_DEMAND)                 # surface, never silently absorb

STEP 5  reduction = (net_of_adjustment + moq_uplift) * reduction_pct

STEP 6  CARRYOVER                                      # MULTI_DAY items only
        if param.carryover_enabled
           and item.replen_policy = MULTI_DAY
           and fact.ei_reported:
              usable = FEFO qty with remaining shelf life >= cover horizon
              carryover_applied = least(usable, computed_qty)

STEP 7  suggested_order_wo_ei = ceil_to_multiple(net_of_adjustment + moq_uplift - reduction)
        suggested_order       = greatest(0, suggested_order_wo_ei - carryover_applied)
        if item_location_param.display_capacity is not null:
              suggested_order = least(suggested_order, display_capacity)
              flag(CAPPED_BY_CAPACITY) if capped

STEP 8  cx_reco         -> optional, reason code required
STEP 9  om_adjustment   -> optional, reason code required
STEP 10 final_order = coalesce(om_adjustment, cx_reco, suggested_order)
```

**Step 6 is the highest-value logic in the system.** The current spreadsheet has no carryover step, so for `PD+3`/`PD+4` wrapped SKUs it orders as though yesterday's sellable stock does not exist. That is why network inventory climbed from 27,066 to 55,914 in one week.

## 10. Accuracy and bias

Nightly job backfills `actual_sales` and `actual_excess` onto `order_line`.

| Metric | Formula | Why |
|---|---|---|
| **Bias** | `mean(final_order − actual_sales)` | **The core metric.** Persistent positive bias is the entire problem |
| WAPE | `Σ\|final_order − actual_sales\| / Σ actual_sales` | Accuracy |
| Excess % | `Σ excess / Σ deliveries` | Client's own headline — baseline 15–16% |
| Sold-out rate | `sold_out_lines / total_lines` | The invisible cost |
| Override rate | `overridden_lines / total_lines` | Process discipline |
| **Override value-add** | bias with overrides vs bias of `suggested_order` alone | **Proves whether human adjustments help or hurt** |

**Rung attribution.** Decompose total excess into contribution from baseline error, adjustment, MOQ uplift, ignored carryover, CX Reco and OM adjustment. This single report is the most persuasive artifact the system produces, and nobody at Cocopan can currently see it.

---

## 11. Integration layer

**Principle:** every inbound path lands in staging, resolves references, then writes to the ledger. Never write directly from an external payload to a fact table.

```
File upload  ─┐
POS webhook  ─┼─► stg.* ──► resolve (alias, location) ──► validate (DQ) ──► core.stock_movement
REST API     ─┤                    │
Manual entry ─┘                    └─► core.ingest_quarantine (unresolved)
```

- **Idempotency:** every inbound record carries `idempotency_key` or `(source_code, external_id)`. Replays are safe.
- **Mapping profiles:** a new file layout is a config change, not a deployment.
- **Null tokens:** configurable per profile — `['', '-', 'N/A', 'null']` map to NULL, never to 0.
- **Adapter contract:** POS integrations normalise to a single sales-event shape; adding a new POS means writing one adapter.
- **Outbound:** transactional outbox → webhook publisher, with retry and dead-lettering. Events: `order.generated`, `order.locked`, `order.submitted`, `stock.adjusted`, `item.updated`.
- **Reconciliation job:** daily comparison of ingested totals against source control totals; discrepancies raise an alert rather than failing silently.

---

## 12. UX and design system

**Theme:** neutral-first, professional, with Cocopan's gold used purely as an accent. In a tool where people scan thousands of rows for problems, a dominant brand colour destroys the signal that something needs attention. The brand should be recognisable in the chrome, never competing with the data.

Full **light and dark** themes are required. Planners and CX work long sessions in this interface, often at the 7 PM cutoff.

### 12.1 Accent discipline — read before styling anything

Cocopan gold appears in exactly these places:

- The brand mark in the top bar
- Primary action buttons (one per screen, at most)
- The active navigation indicator
- Row-selection highlight (as a 2px left border, not a fill)
- The "current value" marker in the Ladder Trace

Gold **never** appears as: body or label text, table fills, chart series for routine data, status badges, borders on inputs, or backgrounds of any panel. If a screen has more than roughly three gold elements visible at once, it is wrong.

> On light backgrounds gold fails text-contrast requirements (≈1.9:1 on white). Treat it strictly as a fill or indicator colour, and always pair a gold fill with near-black text, never white.

### 12.2 Tokens

Two layers: fixed primitives, then semantic tokens that flip per theme. Components only ever reference semantic tokens.

The token values live in `frontend/src/design/tokens.css` and that file is
authoritative — where this document and the CSS disagree, this document is
the bug (same rule as `db/` for DDL). The file defines: gold + bark brand
primitives, a warm-cast neutral ramp (`--n-0`…`--n-950`), cool semantic
colours (green/blue/red in 400/500), radius + spacing scales, and a full
`[data-theme="light"]` / `[data-theme="dark"]` semantic layer
(bg/surface/border/text/accent/attention/positive/negative + shadows).

**Theme behaviour**

- Default follows `prefers-color-scheme`
- User override persists per account (stored server-side, so it follows them across devices)
- Toggle lives in the top bar, not buried in settings
- Transition on theme change is a 120ms fade on `background-color` and `color` only — never on layout properties
- Charts read their series colours from CSS variables, so they re-theme with everything else. **Do not hard-code hex values in chart configs.**

**Semantic colours are deliberately cool.** Because gold owns the brand, an amber "warning" would be visually indistinguishable from a branded control. Attention is steel blue, positive is deep green, negative is red — all three unmistakable against gold in either theme.

### 12.3 Typography

**IBM Plex superfamily** — Sans for UI, Mono for every quantity, Condensed for dense table headers.

Rationale: Plex was drawn for technical and industrial contexts, carries genuine tabular figures (essential when comparing columns of order quantities), and has enough warmth to sit alongside a food brand without turning playful. Using one superfamily across three roles keeps a data-dense interface disciplined.

```css
--font-ui:    'IBM Plex Sans', system-ui, sans-serif;
--font-data:  'IBM Plex Mono', ui-monospace, monospace;   /* ALL numbers */
--font-dense: 'IBM Plex Sans Condensed', sans-serif;      /* table headers */

--t-display: 28px/1.2 600;
--t-h1:      20px/1.3 600;
--t-h2:      16px/1.4 600;
--t-body:    14px/1.5 400;
--t-small:   13px/1.4 400;
--t-micro:   11px/1.3 500;   /* uppercase, .06em tracking — labels only */
```

**Rule: every quantity renders in `--font-data` with `font-variant-numeric: tabular-nums`.** Columns of order figures must align on the digit. This is not cosmetic — misaligned numerals cause misreads during review.

Dark mode: drop body weight from 400 to 380–390 if the chosen webfont supports variable weights. Light text on dark backgrounds optically gains weight, and dense tables become muddy without the correction.

### 12.4 Signature element — the Ladder Trace

The one memorable component, taken directly from the client's own mental model.

Any quantity anywhere in the system expands into a horizontal waterfall showing exactly how it was derived:

```
Baseline  Adjust   MOQ    Reduce  Carryover  Suggested   CX    OM    FINAL
   58  →   +3   →   0   →   0    →   −12    →    49    →  49  → +5  →  54
   ▇▇▇▇▇▇▇  ▏      ·        ·       ▇▇▇          ▇▇▇▇▇▇      ·     ▎     ▇▇▇▇▇▇▇
```

Segments are neutral grey; only the final value carries the gold marker. Each segment is hoverable and names the rule and parameter that produced it; overrides show their reason code.

This is the trust mechanism that turns a black box into something people accept — and it is the direct descendant of the spreadsheet columns they already read every day.

### 12.5 Layout

```
┌──────────────────────────────────────────────────────────────┐
│ ▮ Cocopan IMS    Orders  Inventory  Items  Admin      ⌘K  ◐  │  56px, --cp-surface
├────────┬─────────────────────────────────────────────────────┤
│        │  Order run · 30 Jul – 2 Aug        [Lock] [Submit]  │
│  Side  │  ─────────────────────────────────────────────────  │
│  nav   │  ▸ 214 lines need review   1,986 auto-approved      │
│ 220px  │  ┌───────────────────────────────────────────────┐  │
│        │  │  dense grid, 40px rows, sticky header + col   │  │
│        │  └───────────────────────────────────────────────┘  │
└────────┴─────────────────────────────────────────────────────┘
```

Single fixed top bar, collapsible left nav, content maximised. No nested panels — reviewers work in one plane.

### 12.6 Workflow principles

1. **Exceptions, not everything.** Reviewers see flagged lines by default. Target: **under 10% of lines flagged.** More than that and people rubber-stamp, which is exactly today's failure.
2. **Three clicks to a decision.** Open run → filter exceptions → adjust and confirm.
3. **Inline editing.** Type in the cell. `Tab` commits and advances, `Esc` reverts. No modal for a number change.
4. **Reason codes are a picker, never free text.** Free text cannot be analysed, and analysis is the point.
5. **Bulk actions everywhere.** "Apply +10% to all sold-out items in my area" is a real request — support it with one reason code for the batch.
6. **Never a blank screen.** Empty states state what to do next: "No orders yet. Generate a run for 30 Jul – 2 Aug."
7. **Optimistic UI with clear rollback.** Edits apply immediately; failures revert visibly with the reason.
8. **Show the cost of a decision.** Before an override saves, show the estimated peso impact. This is the behavioural lever that shifts the additive-bias culture.
9. **Undo over confirm.** Reserve confirmation dialogs for destructive and irreversible actions.
10. **Keyboard first.** `⌘K` command palette; `j`/`k` row navigation; `e` edit; `f` flag. Planners live in this screen for hours.

### 12.7 Screens

| Screen | Roles | Purpose |
|---|---|---|
| Dashboard | All | Excess % trend, bias, network inventory, top exceptions |
| Order Runs | Planner | Generate, monitor, lock, submit |
| **Exception Workbench** | CX, OM | The primary daily screen. Flagged lines, inline edit, bulk actions |
| Order Line Detail | All | Ladder Trace + 4-week history sparkline |
| Stock Explorer | All | Ledger by location/item, FEFO ageing, movement history |
| Counts | Store Head, Store Team, OM | Guided count entry, mobile-first, under 3 minutes |
| Receiving | Store Head, Store Team | Confirm delivery, capture discrepancies |
| Waste Log | Store Head, Store Team, OM | Quantity + reason code |
| Items | Sys Admin, Planner | CRUD, aliases, prices, MOQ, shelf life, lifecycle |
| Branches | Sys Admin, Planner | List, lifecycle status, OM assignment, bulk actions |
| Branch Onboarding | Sys Admin, Planner | Guided 8-step wizard (§5.2), resumable |
| Branch Detail | Planner, OM | Profile, assortment, schedule, closures, status history |
| Closures | OM, Planner | Calendar view; add, edit, cascade to concessions |
| Assortment Templates | Planner | Define by format × cluster, apply in bulk, view divergence |
| Reference Data | Sys Admin | Categories, reason codes, clusters, areas, routes, calendar |
| Parameters | Planner, Sys Admin | Effective-dated sets with version history and diff view |
| Users & Roles | Sys Admin | CRUD, role assignment, branch scoping, API keys |
| Audit Log | Sys Admin, Planner, Finance | Filterable trail, field-level diffs |
| Integrations | Sys Admin | Sources, mapping profiles, webhooks, reconciliation status |
| Data Ingest | Planner | Upload, DQ results, quarantine resolution |
| Accuracy | Planner, Finance | Bias/WAPE/excess by dimension, rung attribution, override value-add |

### 12.8 Accessibility floor

WCAG 2.1 AA contrast **verified in both themes** — dark mode is not exempt and usually fails first on secondary text and borders · visible keyboard focus (2px `--accent` ring on `--surface`, offset 2px) · full keyboard operability · `prefers-reduced-motion` respected · **never colour alone to convey state** — pair with icon or label, since red/green deficiency is common and this system's core signals are over/under.

---

## 13. API surface

**Status (see §0's implementation-status table for the full picture):** the
Master data / Users & access / Inventory groups below are built, with two
real deviations worth knowing before you go looking for the spec'd shape —
auth is Firebase-based in practice (`POST /api/v1/auth/firebase`; the
`/auth/login` shown below is a dormant bcrypt fallback the frontend no
longer calls, kept for admin/scripting use), and there's a `GET
/api/v1/dashboard` endpoint not listed here at all (one permission-gated
aggregate read per nav screen, powering the post-login landing page).
Locations' onboarding wizard, assortment templates, `params`, and
`geography` are not built. Replenishment / Analytics / Admin & integration
/ Inbound integration are entirely spec-only — nothing in those four groups
exists yet.

```
POST   /api/v1/auth/login | refresh | logout
GET    /api/v1/auth/me                          -> permissions + scope

# Master data (full CRUD, permission-gated)
GET|POST        /api/v1/items
GET|PATCH|DELETE /api/v1/items/{code}
GET|POST        /api/v1/items/{code}/aliases | prices
GET|POST        /api/v1/locations   ... /{code}
POST            /api/v1/locations/{code}/status        # lifecycle transition + reason
POST            /api/v1/locations/{code}/assign-om
GET|POST        /api/v1/locations/{code}/assortment    # apply template / adjust
GET|POST        /api/v1/locations/{code}/schedule
GET|POST        /api/v1/locations/{code}/closures ... /{id}
GET             /api/v1/locations/{code}/status-history
POST            /api/v1/locations/onboard              # wizard submit, transactional
POST            /api/v1/locations/import               # bulk openings
GET|POST        /api/v1/assortment-templates ... /{code}/items
POST            /api/v1/assortment-templates/{code}/apply   # bulk to matching branches
GET|POST        /api/v1/geography
GET|POST        /api/v1/categories | clusters | areas | routes | reason-codes
GET|POST|PATCH  /api/v1/params
GET             /api/v1/params/{id}/diff?against={id}

# Users & access
GET|POST        /api/v1/users  ... /{id}
POST            /api/v1/users/{id}/roles | scopes | api-keys   # scopes = branch/area/cluster
GET|POST        /api/v1/roles ... /{code}/permissions
GET             /api/v1/permissions

# Inventory
GET             /api/v1/stock?location=&item=&as_of=
GET             /api/v1/stock/movements
POST            /api/v1/stock/movements          # manual adjustment, reason required
POST            /api/v1/counts | /counts/{id}/submit
POST            /api/v1/receiving | /waste | /transfers

# Replenishment
POST            /api/v1/forecast/runs
POST            /api/v1/orders/runs
GET             /api/v1/orders/{id}/lines?exception_only=true&cursor=
PATCH           /api/v1/orders/{id}/lines/{lineId}
POST            /api/v1/orders/{id}/lines/bulk
POST            /api/v1/orders/{id}/lock | submit-ppic
GET             /api/v1/orders/{id}/export?format=xlsx|csv|ppic

# Analytics
GET             /api/v1/accuracy/summary?group_by=location|item|dow|om
GET             /api/v1/accuracy/attribution?order_id=
GET             /api/v1/accuracy/overrides

# Admin & integration
GET             /api/v1/audit?table=&record=&user=&from=&to=
GET|POST        /api/v1/integrations/sources | mapping-profiles | webhooks
POST            /api/v1/ingest/upload
GET             /api/v1/ingest/files/{id} | quarantine
POST            /api/v1/ingest/quarantine/{id}/resolve

# Inbound integration
POST            /api/v1/ingest/events/sales      # POS push, idempotent
POST            /api/v1/ingest/events/deliveries
```

**Conventions:** cursor pagination · `If-Match` optimistic concurrency on updates · `Idempotency-Key` header on POST · RFC 7807 problem responses · every request carries `X-Request-Id`, persisted to audit.

---

## 14. Acceptance criteria

### AC-1 Calibration — defines prototype complete

Load the client's reference data (sales 29 Jun – 26 Jul), generate an order for 30 Jul – 2 Aug using the "Client Baseline (as-is)" parameter set with `carryover_enabled = false`.

> **`suggested_order` must match the workbook's `Suggested Order` within ±1 unit on ≥95% of lines.**

Until this passes, enable no improvements. Reproducing their current answers is what earns permission to change them — and it is how the ⚠️ CALIBRATE parameters get fitted.

### AC-2 Functional
- 12 weeks × all pilot locations × full catalogue ingested with zero silent data loss; every rejected row appears in quarantine
- Blank, `0` and `-` resolve to distinct states; `ei_reported` correctly false where no count was submitted
- Full-network order generation completes in **under 10 seconds**
- Every quantity exposes its Ladder Trace
- No override saves without a reason code
- Locked orders reject edits
- Excel export opens in a layout current users recognise
- Light and dark themes both pass AA contrast; no hard-coded colour outside the token file
- A branch can be onboarded end-to-end through the wizard in under 5 minutes, producing assortment and schedule rows without manual entry
- A branch closed on a given weekday is excluded from that weekday's reference window; `obs_count` decrements and the line falls back correctly
- Every reference table in §5.6 has working create, read, update and deactivate in the UI
- Deleting a referenced reference row is blocked with a message naming the dependency, never a raw FK error

### AC-3 Access & audit
- Deny-by-default verified: every endpoint returns 403 without explicit permission
- An OM cannot read or write another OM's branches, and a Store Head sees only their own, verified at the **database** layer with the API bypassed
- Reassigning `location.om_user_id` moves access immediately, with no separate permission change
- Every mutation on every master table produces an audit record with before/after and actor
- Audit records cannot be updated or deleted by any application role

### AC-4 Value demonstration
- Accuracy dashboard reports bias and WAPE by location, item and weekday
- Rung attribution shows peso contribution per adjustment step
- **Enabling carryover for MULTI_DAY SKUs demonstrably reduces simulated excess versus the as-is baseline — this is the headline demo**
- MOQ exception report lists every item/location where MOQ exceeds 3× daily demand

---

## 15. Build sequence

| # | Milestone | Contents |
|---|---|---|
| 1 | Foundation | Repo, Docker Postgres, Alembic, schemas, enums, audit triggers, RBAC tables, seed |
| 2 | Master data | Item CRUD, aliases, prices, UOM, categories, search |
| 2b | Branch management | Lifecycle + history, onboarding wizard, closures, assortment templates, full reference CRUD (§5) |
| 3 | Access | Auth, permissions, branch scope + RLS, user admin, API keys, audit viewer |
| 4 | Ledger | `stock_movement`, balances, FEFO ageing, counts, receiving, waste, transfers |
| 5 | Ingest | Mapping profiles, parsers, DQ rules, quarantine, staging, nightly rollup |
| 6 | Forecast | `agg_location_item_dow`, `WEEKDAY_AVG_V1`, cluster analog, calendar overlays |
| 7 | Ladder | Steps 0–7 set-based, carryover behind flag, exception flagging |
| 8 | **Calibration** | Run AC-1, fit ⚠️ CALIBRATE parameters, document deviations |
| 9 | Workbench | Grid, exception filters, inline edit, bulk actions, Ladder Trace, lock/submit |
| 10 | Accuracy | Backfill, metrics, rung attribution, dashboards |
| 11 | Integration | Adapters, outbox, webhooks, reconciliation |
| 12 | Deploy | Cloud SQL, Cloud Run, Scheduler, PgBouncer, Redis, monitoring |

---

## 16. Open items blocking full build

| # | Item | Blocks |
|---|---|---|
| 1 | Unit cost per SKU | Waste valuation, service-level optimisation, ROI |
| 2 | Whether SRP genuinely varies by branch/format (concession vs standalone, NCR vs provincial) or the 15-vs-18 / 20-vs-22 conflicts are data entry errors | Whether conflicting values become confirmed branch overrides or get reconciled to one network price |
| 3 | Is `Excess` counted or derived? | Shrink visibility, `excess_source` default |
| 4 | Source systems for DR and Offtake; API availability | Replacing file upload |
| 5 | Does POS capture time of sale? | Censored-demand correction |
| 6 | Full location master with format and cluster | New-store forecasting, RLS scoping |
| 7 | Shelf life per SKU beyond the pillow-pack pilot list | Policy assignment |
| 8 | Confirmed store count (tabs ~122, summary sheets ~105) | Sizing |
| 9 | Disposition of excess bread (markdown / staff / donation / disposal) | ROI model |
| 10 | Exact spreadsheet formulas for the adjustment step | Removes parameter fitting in AC-1 |
| 11 | SSO provider (Google Workspace?) | Auth design |
| 12 | Org chart: which OMs cover which branches today | Seeding branch scope |
| 13 | Existing branch closure history (any record kept?) | Cleaning historical forecast reference data |
| 14 | Do assortments differ by branch today, or does every store carry everything? | Assortment template design |
| 15 | Shelf/display capacity per branch | `display_capacity` cap in the ladder |

---

## Appendix

The project instructions file is the root `CLAUDE.md`, maintained directly
(no starter copy is kept here — a duplicate drifts). Deep rationale it
references lives in `docs/local-dev.md` and `docs/migration-notes.md`.
