# Cocopan IMS — Cleanup Plan (Phase 1 discovery)

Branch: `chore/cleanup-2026-08-02`. Everything below is **read-only discovery** — nothing has
been deleted or changed. Full raw audit notes: `backend_audit.md`, `frontend_audit.md`,
`db_audit.md` were written to the session scratchpad during discovery; this file is the
synthesized deliverable per Phase 1D.

## Phase 0 baseline (recorded before any discovery)

| Check | Result |
|---|---|
| `backend`: `pytest -q` | **18/18 pass** (against live Cloud SQL — no local test DB) |
| `backend`: `ruff check .` | clean |
| `backend`: `mypy .` | 4 pre-existing errors (not introduced by this task, not fixed here): missing stubs for `firebase_admin`/`psycopg2` (harmless, needs `types-psycopg2`), plus one real issue at `app/api/v1/users.py:87` (`Incompatible types in assignment` — `list[UserRoleOut]` vs declared `list[str]`) |
| `frontend`: `npm run typecheck` | clean |
| `frontend`: `npm run build` | clean, 139 modules |
| `frontend`: lint | no eslint config exists in this repo — nothing to baseline |
| DB connectivity | Confirmed read-only as `cocoims_app` (NOSUPERUSER, NOBYPASSRLS) against `cocoims:asia-southeast1:cocoims-db`, database `cocoims` |

---

## ⚠️ Not a cleanup item — flag before anything else

**RLS does not apply to individual partitions of `core.stock_movement`, `core.count_session`, or
`core.order_line`.** `ENABLE`/`FORCE ROW LEVEL SECURITY` was only ever run against the parent
table names; Postgres does not cascade that to child partitions. Verified empirically:
`select count(*) from core.stock_movement` returns `0` under a non-matching scope (correct), but
`select count(*) from core.stock_movement_2026_07` returns all `10522` rows regardless of scope.
Normal API traffic is unaffected (the ORM always queries the parent name), so this isn't
user-facing today — but any raw SQL, Cloud SQL Studio session, or future reporting/ingest job that
touches a partition by name would silently return cross-branch data with no error.

This isn't part of the LOC/table-count cleanup below. It needs its own decision and its own
migration — see `PERF_FIXES` for the concrete fix. Flagging it here so it doesn't get lost in the
larger list.

---

## SAFE_TO_DELETE

| # | Item | Evidence | Est. LOC |
|---|---|---|---|
| 1 | `backend/app/ingest/`, `backend/app/integration/`, `backend/app/jobs/` (3 dirs, `__init__.py` only) | Zero references anywhere in the codebase (`grep -rn "app.ingest\|app.integration\|app.jobs" backend/` → nothing outside their own files). No Cloud Scheduler config exists in the repo at all. SPEC's own status table marks these groups "entirely spec-only — nothing exists yet." | ~3 (empty files) |
| 2 | `frontend/src/auth/firebase.ts` → `signInWithEmailPassword()`, `frontend/src/api/auth.ts` → `login()`, `frontend/src/auth/AuthContext.tsx` → `login` wrapper + its entry in the `AuthContextValue` interface | 3-file dead chain. Zero call sites for any of the three (every `useAuth()` call site checked — `LoginPage`, `ReceivingPage`, `DashboardPage`, `SalesPage`, `RequireAuth`, `AppShell` — none destructure `login`; `LoginPage` only uses `loginWithFirebase`). The code's own comment at `auth.ts:52-55` says it's "left in place as a dormant fallback but no longer called by the UI." **Do not delete the backend `POST /api/v1/auth/login` route based on this** — that's a separate, still-real backend endpoint that may be used by scripts/ops/tests; this entry is frontend-only. | ~35-45 |
| 3 | `frontend/src/api/types.ts` → `ItemCategory` (line 183), `Uom` (line 191) interfaces | Zero references anywhere, including within `types.ts` itself. The actual Categories/UOM CRUD tabs go through the generic `RefRow = Record<string, unknown>` type in `RefDataTab.tsx` instead — these are orphaned duplicates from an earlier iteration, not missing functionality. | ~16 |

**Total: ~55-65 LOC, 3 empty backend directories, 0 DB objects.** Small — this is a clean codebase.

---

## NOT_SURE — needs your call

| # | Item | Question |
|---|---|---|
| 1 | `POST /api/v1/transfers` (backend, fully implemented, `movement.adjust` permission) + `frontend/src/api/types.ts:285` `TransferResponse` (zero frontend usage) | SPEC's status table marks Transfers as "built," but there's no Transfers page/route anywhere in the frontend, and no test covers the endpoint. **Is a Transfers UI in progress / planned soon, or was it deprioritized?** If deprioritized indefinitely, the backend route can stay (matches spec, costs nothing) but the orphaned `TransferResponse` type should go with item 3 above once you confirm no near-term UI work needs it. |
| 2 | `GET/POST/DELETE /api/v1/items/{code}/uom-conversions...` (backend, fully implemented) | Same shape as #1: `core.uom_conversion` is real in-scope reference data per SPEC, backend route exists, zero frontend caller, zero test. Same question — unbuilt UI or abandoned? |
| 3 | ORM models `ApiKey`, `Geography`, `SourceSystem` (backend `app/models/`) | Zero usage outside `app/models/*.py` — no route/service reads or writes them. Unlike the CLAUDE.md-blessed "keep `item_type`/ledger generic for Supplies" case, nothing calls for pre-built ORM classes for API-keys or the Geography onboarding wizard, both of which SPEC marks "not built." Keep them because the underlying DB tables already exist and the model is just mirroring schema (per this repo's own convention), or delete the model classes until the feature is actually built? |
| 4 | `stg` schema / `stg.sales_event` table | `db/ddl/001_schema.sql:644` defines this table, but it **does not exist in the live database** — the `stg` schema is empty. Either it was manually dropped post-baseline, or added to the DDL file after `0001_baseline` already ran and never got a follow-up migration. This is schema/DDL drift either way: if someone spins up the `docker-compose` local-Postgres fallback, they'll get a table Cloud SQL doesn't have. **Is sales-event ingest still planned?** If yes, a migration is missing. If no, the DDL file should be corrected to match reality. |
| 5 | `core.mapping_profile` (table + 3 seed rows, no SQLAlchemy model, zero code references) | Every other reference table has a model; this one doesn't. Same "ingest layer not built yet" family as #4 — drop alongside it, or keep as still-planned? |
| 6 | 17 tables with zero code references but named directly in CLAUDE.md/SPEC as core scope: `core.outbox_event`, `webhook_subscription`, `api_key`, `ingest_file`, `ingest_quarantine`, `calendar_location_event`, `forecast_run`, `forecast_line`, `order_header`, `order_line`, `delivery_schedule`, `assortment_template(_item)`, `param_set`, `item_location_param`; `rpt.agg_location_item_dow`, `rpt.mv_daily_network` | This reads as **schema built ahead of the API code that will use it** — CLAUDE.md explicitly says the order ladder runs "set-based SQL over `rpt.agg_location_item_dow`" and names most of these tables as the order-ladder/forecast core value. Applying "flag unbuilt features for deletion" here would delete the foundation of a feature that's explicitly in scope and just not started. **Not put in SAFE_TO_DELETE.** Confirming: is order-ladder/forecast/outbox/ingest work actually in-flight, or has scope changed since these were authored? |
| 7 | `core.item.target_date`, `core.item_price.unit_cost`, `core.location.om_user_id` (+7 other location columns), `core.source_system.config`, `core.calendar.weather_flag`, `core.param_set.target_service_level` — all 100% NULL | Per CLAUDE.md's own rule (NULL/zero/not-counted are different facts), **none of these were treated as deletion candidates** — this is a 2-day-old dataset (34 items, 122 locations, seeded 2026-07-31) where nothing has happened yet, not evidence of dead columns. One is worth a specific look: **`location.om_user_id`** is the column CLAUDE.md calls out by name as the access-scope mechanism ("grants scope automatically"), and it's unset for all 122 real branches — meaning that mechanism has never been exercised with real data. Is OM assignment a rollout step that hasn't happened, or does something else currently substitute for it? The rest are just "ask if the workflow that sets this exists yet" — not urgent. |

**None of the NOT_SURE items are in SAFE_TO_DELETE.** I'd rather under-claim on a system with no
staging environment to rehearse against than hand you a false positive.

---

## KEEP_BUT_FLAG

| Item | Why |
|---|---|
| `frontend/src/routes/waste/WastePage.tsx:177` — `{m.qty.replace(/^-/, "")}` instead of `formatQty()` | Every other quantity column in the app uses the shared formatter (`format.ts`'s own docstring: "never show the raw Decimal string directly"). This one likely renders `"50.000"` instead of `"50"`. Not dead code — a one-line display inconsistency. Flagging rather than fixing because Prime Directive #4 says no behavior change without approval, and visible text is a behavior change even if trivial. |
| `frontend/src/api/client.ts` — `ApiError` class, `apiFetch` function exported but never imported elsewhere | Both are exercised at runtime, just don't need the `export` keyword. Trivial, not worth its own commit — mention if `client.ts` gets touched for another reason. |
| `backend/app/auth/router.py:129` `logout(user: AppUser = Depends(get_current_user))` | Ruff flags `user` as unused, but the dependency is what enforces "must be authenticated to log out" — removing the parameter would make `/logout` callable while unauthenticated. Not dead code. |
| 3 `deptry`/`vulture` hits in backend (Pydantic `cls` in validators, `uvicorn`/`python-dotenv` "unused" deps) | All false positives — `uvicorn` runs from the Dockerfile `CMD` (not imported in Python), `python-dotenv` backs `pydantic_settings`'s `env_file` loading indirectly. No action. |
| `depcheck` flagging `autoprefixer`/`postcss`/`tailwindcss` as unused frontend deps | False positive — all three are used via `postcss.config.js`/`tailwind.config.js`, which depcheck's static analysis doesn't trace into config files. No action. |
| `core.app_user.password_hash`/`failed_attempts`/`locked_until` (100% NULL/0) | Looked dead at first, but `auth/router.py:45` actively uses `password_hash` for dual-auth (SSO or password); all-NULL today just means every seeded user happens to be SSO-only. Documenting so it doesn't get re-flagged later. |
| Connection pool size vs Cloud SQL `max_connections=25` | `backend/app/core/db.py` uses SQLAlchemy's default pool (5 + 10 overflow = 15 connections/container). No `--max-instances` cap is set on the Cloud Run deploy. **Two Cloud Run instances at full pool utilization alone would exceed the DB's connection limit** — not an issue at current traffic, but a real outage mode waiting for load. See PERF_FIXES. |

---

## PERF_FIXES

| Fix | Expected impact | Risk |
|---|---|---|
| Enable + force RLS on every existing partition of `stock_movement`/`count_session`/`order_line` individually (`ALTER TABLE core.stock_movement_2026_07 ENABLE ROW LEVEL SECURITY; ... FORCE ROW LEVEL SECURITY;` × each partition), and add the same statements wherever future partitions get created | Closes the direct-partition RLS bypass described above. Correctness/security fix, not speed — but the highest-value finding in this audit. | Low — additive `ALTER TABLE`, no data change, but needs a migration + confirmation of whether partition creation is manual or scheduled (didn't find a job; 2026-09 through 2027-01 partitions already exist from the original DDL loop) |
| Set explicit `pool_size`/`max_overflow` in `backend/app/core/db.py` and add `--max-instances` to the Cloud Run deploy command, sized so `instances × (pool_size + max_overflow) < 25` with headroom | Prevents connection-exhaustion outages under real concurrent load — currently invisible in dev, would surface as unexplained "connection refused" in production traffic | Low — config only, no behavior change to any request |
| FK columns without a supporting index (~35, mostly on tables ≤122 rows: `location.area_code/route_code/cluster_code/geo_code`, `item_category.parent_code`, etc.) | Not urgent at current row counts. Revisit once `stock_movement`/`order_line`/`count_line`'s FK columns see real query-time joins at scale (i.e. once the order-ladder work in NOT_SURE #6 actually ships) | N/A — deferred, not a current action |

No redundant indexes, no `float`-for-quantity violations, no naive `timestamp` columns, no
app-only-enforced FKs found — the schema is clean on all of CLAUDE.md's other non-negotiables.

---

## Environment note that changes Phase 3's plan

**There is no staging database.** CLAUDE.md documents this as a deliberate choice for this
prototype phase — local dev and whatever's deployed both point at the single
`cocoims:asia-southeast1:cocoims-db` instance. The cleanup task's Phase 3 assumes "apply to
staging first, then production" — that step doesn't exist here as written. Before any Phase 3 DB
work starts, we need to decide: spin up a temporary throwaway Cloud SQL instance to rehearse
migrations against, use the `docker-compose` local-Postgres fallback (already mentioned in
CLAUDE.md for "iterate on a risky migration before it touches the real thing"), or accept
soft-drop-only changes with no rehearsal step. Given Phase 1C found **zero DB objects that
actually qualify for deletion**, this may not matter for this round — but it will the moment any
future cleanup pass wants to drop something for real.

---

## Ordered execution plan (lowest risk first) — pending your approval

1. Delete the 3 empty backend package directories (`app/ingest`, `app/integration`, `app/jobs`) — zero risk, zero references.
2. Delete the 2 orphaned frontend type interfaces (`ItemCategory`, `Uom`) — zero risk, zero references.
3. Delete the frontend dead auth chain (3 files/spots) — very low risk, but re-run `npm run typecheck` and `npm run build` immediately after since it touches a shared interface (`AuthContextValue`).
4. Get your answers on the 7 NOT_SURE items above — nothing else proceeds until then.
5. Separately from "cleanup": decide on the RLS-partition fix and the connection-pool fix — both are real but neither is blocked on the NOT_SURE answers, so they could move in parallel if you want them prioritized sooner.

**Nothing above has been deleted or changed.** Waiting for your go-ahead on item 1-3, your answers
on NOT_SURE 1-7, and a decision on whether the RLS/pool fixes get their own fast-tracked migration
or wait for the normal Phase 3 sequence.
