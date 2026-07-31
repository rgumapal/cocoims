# Cocopan Inventory Management System

Read `docs/SPEC.md` fully before implementing. Non-negotiable constraints:

DATA
- Never coerce NULL to 0 in fact tables. Blank, zero and "not counted" are three
  different facts. This is the single most important data rule in the system.
- `core.stock_movement` is append-only. No UPDATE or DELETE. Corrections are
  offsetting movements.
- Column names in `core.order_line` mirror the client's spreadsheet headers exactly.
  Do not rename them for elegance — adoption depends on the vocabulary matching.
- Quantities are NUMERIC, never FLOAT.

LOGIC
- The order ladder (SPEC §9) runs in strict sequence and every intermediate value
  is persisted. Do not collapse steps.
- Generate orders with set-based SQL over `rpt.agg_location_item_dow`. Never a
  per-row Python loop with per-row queries.
- items with shelf_life_days > 0 use MULTI_DAY carryover. This is the core value.

ACCESS
- Roles mirror real Cocopan positions. Authority = permission x branch scope.
- Deny by default. Permission checked at API; branch scope enforced by Postgres RLS.
- location.om_user_id grants scope automatically. Do not duplicate it in user_scope.
- Every transaction sets app.user_id, app.user_email, app.request_id. A write
  without session context is a bug.

DESIGN
- Tokens in `frontend/src/design/tokens.css` are binding. Components reference
  semantic tokens only, never primitives, never raw hex.
- Light AND dark themes are required. Both must pass AA contrast.
- Cocopan gold is an ACCENT: brand mark, one primary button, active nav indicator,
  row-selection border, final value in the Ladder Trace. Nothing else.
  Never gold text on light backgrounds. Attention state is steel blue, never amber.
- All numbers render in IBM Plex Mono with tabular-nums.
- The Ladder Trace is the signature component. Any quantity expands to show its
  derivation.

ENGINEERING STANDARDS
Applies to every line of code in this repo, front and back. The audience for
this codebase is not just experienced engineers — assume the next person to
open it is capable but new to this stack, and optimize for them without
sacrificing performance or UX. Those three (readability, speed, UX) are not
in tension here; the rules below are chosen because they serve all three at
once (e.g. set-based SQL is both the readable way and the fast way to express
"apply this rule to 19,500 rows" — a Python loop is neither).

- **Docstrings on every public function/endpoint, not comments on every line.**
  A FastAPI route's docstring is live documentation — it renders in `/docs`
  (Swagger UI), so a beginner can read the entire API from a browser with zero
  setup. State what it does, which `permission.*` it requires, and which scope
  applies. Domain modules (`forecast.py`, `replenishment.py`, `accuracy.py`)
  get a module-level docstring pointing at the SPEC section they implement
  (`# Implements SPEC §9 steps 0-7`), the same way `db/ddl` and the Alembic
  migrations already cite spec sections — keep that pattern going in Python.
- **Comments explain WHY, never WHAT.** Clear names replace "what" comments;
  a comment earns its place only for a non-obvious constraint, a workaround,
  or a business rule a reader can't derive from the code (see `db/ddl/001_schema.sql`
  and the Alembic migrations for the standard this repo already holds itself to).
- **Types are documentation.** Every Python function signature is fully typed
  (mypy-clean); every TypeScript file uses `strict: true`, no `any`. A
  beginner should be able to hover a variable and know its shape without
  reading the implementation.
- **One obvious way to do each thing.** One data-fetching pattern (TanStack
  Query — no ad hoc `fetch`/`useEffect`), one styling mechanism (Tailwind +
  the semantic tokens in `frontend/src/design/tokens.css`, never inline
  styles or a second CSS approach), one state pattern for server data (never
  duplicate server state into local component state "just in case"). A repo
  with two ways to do the same thing is a repo where a beginner picks the
  wrong one.
- **YAGNI over architecture.** No abstraction, config layer, or plugin system
  for a requirement that doesn't exist yet (SPEC's own scope discipline in
  §2.2 and the deferred-supplies decision are the model — build what's asked,
  keep the seams generic where the spec says to, nothing more). Rule of three:
  the third duplication earns an abstraction, not the second.

PERFORMANCE (backend)
- No N+1 queries — use SQLAlchemy `selectinload`/`joinedload` explicitly, and
  say why in a short comment when a query looks like it should be one call
  but is deliberately two.
- The ladder and forecast are single set-based SQL statements over
  `rpt.agg_location_item_dow` (SPEC §6.2) — this is already a hard rule under
  LOGIC above; it is also the performance rule. Full-network order generation
  target is under 10 seconds (SPEC AC-2).
- Cursor pagination only on list endpoints; never `OFFSET` on a table that can
  grow past a few thousand rows (SPEC §6.5).
- `pg_stat_statements` stays enabled; a statement over 500ms is treated as a
  bug, not a follow-up.
- Cache hot, rarely-changing reference data (items, locations, the resolved
  permission set) in Redis; invalidate on write via the outbox, never poll.

PERFORMANCE & UX (frontend)
- Route-level code splitting (`React.lazy` + Vite dynamic `import()`) — the
  Exception Workbench should not ship the Admin screens' JS on first paint.
- Virtualize any grid over ~100 rows (TanStack Table + virtual scrolling).
  This is a dense-grid system by design (SPEC §12.5); an unvirtualized table
  is the single most common way to make it feel slow.
- TanStack Query owns all server state — automatic caching, dedup and
  background revalidation instead of hand-rolled loading flags.
- Optimistic UI on every inline edit, with visible rollback on failure (SPEC
  §12.6 rule 7) — this is what makes 19,500 rows feel instant to review even
  when the network isn't.
- Every loading state is a skeleton shaped like the content it replaces, never
  a bare spinner or blank panel (SPEC §12.6 rule 6: never a blank screen).
- Every error state says what happened and what to do next — never a raw
  stack trace or a generic "Something went wrong."
- Debounce search/filter inputs (~250ms); never fire a request per keystroke.
- SPEC §12.8's accessibility floor and §12's token/theme rules are the UX
  baseline, not a follow-up pass — build to them the first time, not after.

BRANCHES & REFERENCE DATA
- location.status drives everything; is_active / is_orderable are GENERATED. Never
  set them by hand. Every transition writes location_status_history.
- A closed day is an ABSENCE, not a zero. Exclude it from forecast reference
  windows or the weekday average silently degrades. See SPEC §5.3.
- Never delete a branch, item, cluster, area or reason code. Deactivate. History
  and cluster analogs depend on them.
- Every reference table needs full CRUD in the UI. No refdata task may require a
  database console.

SCOPE
- v1 is FINISHED GOODS ONLY. Supplies, packaging and ingredients are deferred —
  no source data exists. Keep item_type and the ledger generic, but build nothing
  that depends on supply items.

DONE
- Acceptance is SPEC §14 AC-1: reproduce the client's existing numbers before
  improving them.

Stack: Python 3.12 / FastAPI / SQLAlchemy 2.x / Alembic / PostgreSQL 16 (Cloud SQL)
Frontend: React 18 / Vite / TypeScript / TanStack Table / Tailwind

## Local development database

`cocoims-db` is a local Docker Postgres 16 container (see `docker-compose.yml`),
standing in for Cloud SQL during development. It listens on host port **5433**
(5432 was already in use by another project's container) — connection details
are in `.env` (copy from `.env.example`).

Schema is authored as plain SQL in `db/ddl/` and `db/seed/`, not generated from
ORM models. This is deliberate: the schema uses partitioned tables, generated
columns, exclusion constraints, row-level security and triggers, none of which
Alembic/SQLAlchemy autogenerate can produce reliably. The files in `db/ddl` and
`db/seed` are mounted into the container's `docker-entrypoint-initdb.d/`, so a
fresh `docker compose up` bootstraps schema + core RBAC seed (`db/ddl/001_schema.sql`,
`db/seed/001_seed.sql`) automatically — that mount only ever covers the
baseline, matching Alembic revision `0001`. Everything after that (client data,
future schema changes) is a normal incremental Alembic migration, run with
`alembic upgrade head` from `backend/`:

- `0001_baseline.py` executes the same two files docker-entrypoint-initdb.d
  runs, so it reproduces the schema+RBAC seed on any environment (CI, a
  teammate's machine) — the dev container is stamped rather than re-run.
- `0002_item_price_location_scope.py` extends `core.item_price` with
  `location_code`/`price_status` (per-branch price overrides, needed once real
  SRP data showed the network sheet and store tabs disagree) and adds
  `core.app_user.role_hint`. Not in SPEC §4.3's literal DDL — a genuine
  extension surfaced by real data, not a spec deviation.
- `0003_client_data.py` executes `db/seed/002_client_data.sql`: the real item
  master (34 SKUs) and branch master (121 locations) from the client's
  workbook. Marked `[REAL]`/`[ASSUMED]`/`[DERIVED]` per-section inside the file
  itself — areas/clusters/routes/geography/calendar/users are placeholders
  pending client confirmation; items and branch codes/names/ADS are verbatim.

So: `docker compose up` (fresh container) → `alembic upgrade head` (from
`backend/`, with the venv active) gets a dev database to full current state
in two commands.
