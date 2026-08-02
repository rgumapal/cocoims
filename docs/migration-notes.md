# Migration Changelog — Why, Not Just What

`alembic history` gives the full technical list; this records intent.

- `0001_baseline.py` — schema + core RBAC seed (`db/ddl/001_schema.sql`,
  `db/seed/001_seed.sql`).
- `0002_item_price_location_scope.py` — `core.item_price` gains
  `location_code`/`price_status` (per-branch price overrides, needed once
  real SRP data showed the network sheet and store tabs disagree) and
  `core.app_user.role_hint`. Not in SPEC §4.3's literal DDL — a genuine
  extension surfaced by real data, not a spec deviation.
- `0003_client_data.py` — the real item master (34 SKUs) and branch master
  (121 locations) from the client's workbook (`db/seed/002_client_data.sql`,
  annotated `[REAL]`/`[ASSUMED]`/`[DERIVED]` section by section).
- `0004_operational_rls_and_rpt.py` — closes a real RLS gap (write-path
  policies were missing on several tables) and lands the `rpt`/`perf`
  schema catch-up.
- `0005`–`0009` — small fixes surfaced by real use: a missing seeded admin
  user, `is_active` added to reference tables that lacked it, count-session
  approval columns, an `item_price` EXCLUDE constraint that wrongly treated
  two NULL `location_code` rows as conflicting, and the developer's own
  SYS_ADMIN account.
- `0010_sales_and_sold_out.py` — `sales.record` permission and
  `core.sold_out_event` (the Sales page's "ran out" flag; a same-day fact,
  not a ledger entry, so it lives outside `stock_movement`).
- `0011`/`0012` — deactivate then hard-delete placeholder seed users
  (explicit exception to "never delete, deactivate" — these were prototype
  placeholders, not real history; keeps only `system@cocopan.ph`,
  `svc.pos@cocopan.ph`, and the real developer account).
- `0013_stock_movement_confirmed_by_name.py` — `confirmed_by_name`: who
  physically handled a delivery/sale, if different from the logged-in
  account (free text, not an `app_user` FK — the physical handler isn't
  necessarily a system user).
- `0014_sold_out_event_delete_policy.py` — `sold_out_event` had RLS with
  SELECT/INSERT policies only; DELETE silently affected zero rows (Postgres
  RLS default-denies any command type lacking a policy). Found by testing
  the Sales edit flow end-to-end, not by inspection.
