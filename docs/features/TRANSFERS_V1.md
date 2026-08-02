# Build Brief — Transfers v1 (prototype scope)

**Scope:** branch → branch rebalance only, for daily operations. Nothing downstream.
**Deferred to `TRANSFERS_ROADMAP.md`:** returns to commissary, opening-stock transfers, approval workflow, forecast/ladder integration, accuracy attribution, suggested transfers, in-transit ageing reports, capacity and route gates.

**How to use:** save as `docs/features/TRANSFERS.md`, then: *"Read docs/SPEC.md, CLAUDE.md and docs/features/TRANSFERS.md. Do Phase 0 and report back before writing code."*

You are a senior engineer on CIMS (FastAPI · SQLAlchemy 2.x · Alembic · Postgres 16 with RLS · React 18 + TS + TanStack + Tailwind). Build the smallest thing that lets a branch move sellable bread to a branch that ran out, and have every unit still be explainable in the ledger.

---

## Phase 0 — grep before creating (no code)

`docs/SPEC.md` §13 already lists `POST /api/v1/transfers`; §2.1 already scopes transfers and an in-transit location. Some of this may exist. Report:

1. `db/ddl/001_schema.sql § 4.1` — does `movement_type` already have transfer values? Does `location_type` have in-transit? Is an in-transit location seeded?
2. `core.stock_movement` — confirm `production_date`, `expiry_date`, `idempotency_key`, `reason_code`.
3. Read the **receiving** router + service end to end. Transfer receive is receiving with a different counterparty — mirror it, don't invent.
4. `domain/ledger.py` — the movement-posting helper and the FEFO balance walk.
5. RLS policy names and predicate shape on `core.stock_movement`.
6. Does the nightly rollup / forecast path filter `stock_movement` by movement type, or does it sum everything?
7. Alembic `head`.

**Migration rule (§4):** `db/ddl` is the baseline for Alembic `0001` only. New objects go in `backend/alembic/versions/`, next after `0002_*`. Do not edit `db/ddl`.

---

## The five rules that survive simplification

Everything else here is negotiable. These are not — each one is cheap now and a rewrite later.

1. **Ledger only.** No transfer stock table, no mutable balance. Balances stay derived.
2. **In-transit is a real leg.** Ship posts source → in-transit. Receive posts in-transit → destination. Never one instantaneous movement, or stock vanishes while the rider is in traffic. In-transit nets to zero when a transfer completes.
3. **Lot identity survives.** The destination movement copies `production_date` / `expiry_date` from the source lot consumed. **Never stamp today's date.** Ship consumes FEFO; a line spanning two lots posts two movement rows. The ledger *is* the lot record — no extra table needed.
4. **Received is counted, not defaulted.** Do not pre-fill received with shipped. Blank ≠ 0 ≠ not counted, same as everywhere.
5. **Transfers stay out of demand history.** The one downstream thing you must not skip: confirm the rollup/forecast path filters transfer movement types out of sales and excess. If it sums all movement types, add that filter now. It's one predicate, and without it both branches' forecasts drift and nobody notices.

---

## Data model

Two tables, Alembic migration, `core` schema, §4.9 audit trigger on both.

**`core.transfer`** — `transfer_no` (human-readable, riders read it aloud), `source_location_code`, `dest_location_code` (CHECK ≠), `status`, `reason_code`, `notes`, `created_by/at`, `shipped_by/at`, `received_by/at`, `idempotency_key`.

**`core.transfer_line`** — `transfer_id`, `item_code`, `qty_requested`, `qty_shipped` (NULL until ship), `qty_received` (NULL until receive), `variance_qty` **generated** `qty_received - qty_shipped`, `variance_reason_code`.

One enum: `transfer_status`. Extend `movement_type` / `location_type` only if Phase 0 says they lack transfer and in-transit values.

Indexes: partial `(dest_location_code)` on open statuses for the receive queue; `(source_location_code, created_at DESC)` for branch history.

No fact-table columns, no history table (the audit trigger covers status changes), no partitioning.

---

## State machine

```
DRAFT ──► IN_TRANSIT ──► RECEIVED
   └──► CANCELLED
```

- Ledger posts on exactly two transitions: ship and receive. Nothing else touches stock.
- The **sending branch creates the transfer** — creator needs scope on `source_location_code`. No approval step in v1. (Request-from-the-receiving-side flow is deferred; today OMs agree it on chat first anyway.)
- Cancel is only valid before ship. After ship, the only correction is a reverse transfer.
- Variance at receive: transfer still goes `RECEIVED`, `variance_reason_code` is **required** when shipped ≠ received, and the service posts the difference against in-transit as an adjustment so in-transit still zeroes. Assert zero in a test.
- Allowed transitions live in one dict in `domain/transfer.py`. No `if status ==` chains in routers.

---

## Validation gates (only three)

1. Source has enough FEFO-available stock. Under-stock → warn and allow with a reason (ledger lags reality at branch level), never a hard block.
2. Destination stocks the item (`item_location_param.is_stocked`). Warn + reason on override.
3. `shelf_life_days = 0` items may only transfer on the same business date. Past that they cannot be sold on arrival and you are relabelling waste. Hard block in v1.

---

## RBAC and RLS

Permissions: `transfer.read`, `transfer.create`, `transfer.ship`, `transfer.receive`, `transfer.cancel`.

| | SYS_ADMIN | PLANNER | OPS_MGR | AREA_HEAD | STORE_HEAD | STORE_TEAM |
|---|:-:|:-:|:-:|:-:|:-:|:-:|
| read | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |
| create | ✓ | ✓ | ✓ | ✓ | ✓ | — |
| ship / receive | ✓ | — | ✓ | — | ✓ | ✓ |
| cancel | ✓ | ✓ | ✓ | ✓ | ✓ | — |

Store Team ships and receives — they physically handle the bread, and that's capture, consistent with §7.4.

Scope, the one genuinely new bit (a transfer straddles two branches):

- **Read:** visible if **either** endpoint is in scope — an OR over `v_user_effective_scope`. Write this policy explicitly; don't copy the single-location one.
- **Write:** ship requires scope on source, receive requires scope on destination. Enforced at API *and* in RLS on the resulting `stock_movement` rows.
- The in-transit location is in nobody's scope. Never grant blanket scope on it — that leaks the network.
- Verify at the DB layer with the API bypassed, per AC-3.

Seed reason codes: `REBALANCE_SOLD_OUT`, `REBALANCE_SURPLUS`, `NEAR_EXPIRY`, `SHORT_RECEIPT`, `OVER_RECEIPT`, `DAMAGED_IN_TRANSIT`, `CORRECTION`.

---

## API

Existing conventions: cursor pagination, `Idempotency-Key` on POST, RFC 7807, `X-Request-Id` to audit.

```
GET    /api/v1/transfers?status=&location=&direction=inbound|outbound&cursor=
POST   /api/v1/transfers                 # create draft, returns validation flags
GET    /api/v1/transfers/{id}
POST   /api/v1/transfers/{id}/ship       # per-line qty_shipped -> FEFO allocation
POST   /api/v1/transfers/{id}/receive    # per-line qty_received + variance reasons
POST   /api/v1/transfers/{id}/cancel
```

Ship and receive must be idempotent by key — a rider on bad signal double-taps.

Also surface inbound in-transit on the existing stock/Stock Explorer read, so a Store Head sees "12 pan de coco arriving" without opening this feature.

---

## UI (three screens)

§12 binding: semantic tokens only, light + dark AA, IBM Plex Mono + `tabular-nums` on every quantity, gold accent only.

| Screen | Notes |
|---|---|
| **Transfers list** | Inbound / Outbound tabs, scoped by default. Status chips. TanStack Table, 40px rows. |
| **Ship** | Mobile-first, under 2 minutes. Pick destination → items → quantities. FEFO allocation shown, not editable. Numeric steppers, not text inputs. |
| **Receive** | Mobile-first. Count fields **empty by default**. Variance forces a reason picker before submit. Reuse the receiving screen's components wholesale. |

Detail view can be a drawer off the list, not its own route. Reason codes are pickers, never free text.

---

## Acceptance (AC-5, prototype)

- Ship then receive equal quantities: source down, destination up, in-transit exactly zero, four ledger rows, no stored balance mutated.
- Destination lot carries the **source's** production/expiry date. Assert explicitly. Assert FEFO order when a line spans lots.
- Short receipt: reason required, adjustment posted, in-transit still zero.
- Replaying ship and receive with the same `Idempotency-Key` posts nothing extra.
- Same-day SKU cannot transfer across business dates.
- An OM cannot ship from or receive into a branch outside scope, but **can** read a transfer where only one side is theirs — verified at the DB layer with the API bypassed.
- Transferred units appear in neither `sales_qty` nor excess at either branch.
- **AC-1 output identical before and after this migration.**
- Both new screens pass AA in both themes; no hard-coded colour outside `tokens.css`.

---

## Build order

1. Phase 0 report, plan agreed.
2. Migration: enum, two tables, indexes, RLS, audit triggers, permission + reason-code seeds.
3. `domain/transfer.py` — state machine, three gates, FEFO allocation, ledger posting via `ledger.py`. Pure functions, unit-tested without the API.
4. `api/v1/transfers.py`.
5. Scope/RLS tests with the API bypassed. Don't proceed until green.
6. Ship and Receive mobile screens.
7. Transfers list + drawer, in-transit on Stock Explorer.
8. Rule 5 check on the rollup, then AC-1 regression run.

---

## Do not

- No separate transfer stock table or mutable balance.
- No `UPDATE` / `DELETE` on `stock_movement`, ever.
- No NULL coerced to 0 in the receive path; no received defaulted to shipped.
- No today's-date production dates on the destination.
- No skipping the in-transit leg "for simplicity".
- No per-row Python loops with per-row queries for the FEFO walk (§6.2).
- No auto-executing transfers. A human moves every loaf.

---

## Docs to update in the same PR

`docs/SPEC.md`: §0 status table, §5.6 catalogue rows, §7.3 matrix, §12.7 screens, §13 API, §14 AC-5, changelog. `CLAUDE.md`: two lines only — lot identity survives transfers; in-transit nets to zero. `README.md`: what's built.
