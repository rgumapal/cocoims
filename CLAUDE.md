# Cocopan Inventory Management System

`docs/SPEC.md` is the build authority. Do NOT read it whole by default:
read §0 (how-to-use + implementation status) + the §§ for the task at hand —
`grep -n "^#" docs/SPEC.md` gives the TOC. Read it fully only before
implementing a new engine/module (forecast §8, replenishment §9, accuracy §10).
Stack: Python 3.12 / FastAPI / SQLAlchemy 2.x / Alembic / PostgreSQL 16 (Cloud SQL).
Frontend: React 18 / Vite / TypeScript / TanStack Table / Tailwind.

## Workflow & Token Discipline
- Read only files needed for the task; grep for symbols instead of opening directories.
- Minimal diffs; no drive-by refactors or unasked features. YAGNI — rule of three:
  the third duplication earns an abstraction, not the second.
- Deep rationale lives in `docs/` — load on demand: @docs/local-dev.md (Cloud SQL
  setup + why no local Postgres), @docs/migration-notes.md (migration changelog).

## DATA — non-negotiable
- Never coerce NULL to 0 in fact tables. Blank, zero and "not counted" are three
  different facts. The single most important rule in the system.
- `core.stock_movement` is append-only. No UPDATE/DELETE; corrections are
  offsetting movements.
- `core.order_line` column names mirror the client's spreadsheet headers exactly.
  Do not rename for elegance — adoption depends on matching vocabulary.
- Quantities are NUMERIC, never FLOAT.

## LOGIC
- The order ladder (SPEC §9) runs in strict sequence; persist every intermediate
  value. Do not collapse steps.
- Ladder and forecast are single set-based SQL statements over
  `rpt.agg_location_item_dow` (SPEC §6.2). Never per-row Python loops with
  per-row queries — set-based is both the readable and the fast way.
- Items with shelf_life_days > 0 use MULTI_DAY carryover. This is the core value.

## ACCESS
- Roles mirror real Cocopan positions. Authority = permission × branch scope.
- Deny by default. Permission checked at API; branch scope enforced by Postgres RLS.
  RLS default-denies any command type lacking a policy — every table needs
  policies for every command it must support (see migration 0014).
- `location.om_user_id` grants scope automatically; never duplicate in user_scope.
- Every transaction sets app.user_id, app.user_email, app.request_id. A write
  without session context is a bug.

## DESIGN
- Tokens in `frontend/src/design/tokens.css` are binding. Semantic tokens only —
  never primitives, never raw hex, never inline styles.
- Light AND dark themes required; both pass AA contrast (SPEC §12.8 is the floor,
  built-to first time, not a follow-up pass).
- Cocopan gold is an ACCENT only: brand mark, one primary button, active nav,
  row-selection border, final Ladder Trace value. Never gold text on light
  backgrounds. Attention state is steel blue, never amber.
- All numbers: IBM Plex Mono, tabular-nums.
- The Ladder Trace is the signature component: any quantity expands to show
  its derivation.

## ENGINEERING STANDARDS
Audience: capable engineers new to this stack. Optimize for them without
sacrificing performance or UX — the rules below serve all three at once.
- Docstrings on every public function/endpoint (FastAPI docstrings render in
  `/docs`): what it does, which `permission.*` it requires, which scope applies.
  Domain modules cite their SPEC section (`# Implements SPEC §9 steps 0-7`),
  matching the existing pattern in `db/ddl` and migrations.
- Comments explain WHY, never WHAT. Clear names replace "what" comments.
- Types are documentation: mypy-clean Python, TS `strict: true`, no `any`.
- One obvious way per thing: TanStack Query for all server state (no ad hoc
  fetch/useEffect, no duplicating server state into local state), Tailwind +
  semantic tokens for all styling.

## PERFORMANCE — backend
- No N+1: explicit `selectinload`/`joinedload`; comment WHY when a query is
  deliberately split.
- Full-network order generation under 10s (SPEC AC-2).
- Cursor pagination only; never OFFSET on growable tables (SPEC §6.5).
- `pg_stat_statements` stays on; a statement over 500ms is a bug, not a follow-up.
- Cache hot reference data (items, locations, resolved permissions) in Redis;
  invalidate on write via the outbox, never poll.

## PERFORMANCE & UX — frontend
- Route-level code splitting (`React.lazy` + dynamic import).
- Virtualize any grid over ~100 rows (TanStack Table + virtual scrolling).
- Optimistic UI on every inline edit, visible rollback on failure (SPEC §12.6.7).
- Loading states are content-shaped skeletons, never spinners/blank (SPEC §12.6.6).
- Error states say what happened and what to do next — never raw traces.
- Debounce search/filter inputs (~250ms).

## BRANCHES & REFERENCE DATA
- `location.status` drives everything; is_active / is_orderable are GENERATED —
  never set by hand. Every transition writes location_status_history.
- A closed day is an ABSENCE, not a zero — exclude from forecast reference
  windows or the weekday average silently degrades (SPEC §5.3).
- Never delete branches, items, clusters, areas or reason codes — deactivate.
  History and cluster analogs depend on them.
- Every reference table gets full CRUD in the UI; no refdata task may require
  a database console.

## SCOPE & DONE
- v1 is FINISHED GOODS ONLY. Supplies/packaging/ingredients deferred — keep
  item_type and the ledger generic, build nothing that depends on supply items.
- Acceptance = SPEC §14 AC-1: reproduce the client's existing numbers before
  improving them.

## Database & Migrations (essentials)
- Local dev connects directly to Cloud SQL via the proxy (deliberate — see
  @docs/local-dev.md for rationale and the local-Postgres fallback):
  `cloud-sql-proxy --port 5433 cocoims:asia-southeast1:cocoims-db`
- Schema is authored as plain SQL in `db/ddl/` + `db/seed/` (partitioned
  tables, generated columns, RLS, triggers — autogenerate can't produce these).
  Baseline = Alembic `0001`; everything after is a normal incremental migration:
  `alembic upgrade head` from `backend/`. Cloud Run does NOT run migrations on
  deploy — run them yourself (see the `deploy` skill).
- New migrations: add a why-entry to @docs/migration-notes.md.
