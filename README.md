# Cocopan Inventory Management System (CIMS)

Read [`docs/SPEC.md`](docs/SPEC.md) for the full system specification and
[`CLAUDE.md`](CLAUDE.md) for the engineering standards this repo holds itself
to. This file is just the "get it running" quickstart.

## Prerequisites

- Docker
- Python 3.12+
- Node 18+ (LTS 24.x confirmed working)

## Quickstart

```bash
# 1. Environment
cp .env.example .env          # already has working local defaults

# 2. Database — Postgres 16 in Docker, named cocoims-db, on host port 5433
#    (5432 was already taken by another project on this machine)
docker compose up -d
docker compose logs cocoims-db --tail 20   # confirm no errors on first boot

# 3. Backend
cd backend
python -m venv .venv
./.venv/Scripts/activate      # Windows Git Bash; use bin/activate on macOS/Linux
pip install -r requirements.txt
pip install -r requirements-dev.txt   # pytest, mypy, ruff — needed to run tests/lint

# 4. Bring the database to current schema + seed data
alembic upgrade head

# 5. Dev-only: set a known password on every seeded interactive account.
#    Seeded users have password_hash IS NULL (SSO-first — SPEC §16 open
#    item #11 is unresolved) so there is nothing to log in with until this
#    runs. Never run this outside local dev — see the script's own
#    docstring.
python -m scripts.set_dev_passwords

# 6. Run the API
#    Port 8000 is the FastAPI/uvicorn convention, but collides with an
#    unrelated project on at least one dev machine this has been built on
#    — 8010 is what's actually been used and tested throughout. Either
#    works; the frontend's Vite proxy (frontend/vite.config.ts) assumes 8010.
uvicorn app.main:app --reload --port 8010
```

Check it worked: `curl http://127.0.0.1:8010/health` → `{"status":"ok"}`.
That endpoint round-trips a real query to `cocoims-db`, so it's a genuine
smoke test, not just "the process started." Then open
`http://127.0.0.1:8010/docs` — every endpoint is usable from there directly
(FastAPI's auto-generated Swagger UI): click **Authorize**, log in via
`/api/v1/auth/login` with any seeded email (e.g. `it.admin@cocopan.ph`) and
the dev password printed by step 5, and every other endpoint becomes
callable from the browser.

### Frontend

```bash
cd frontend
npm install
npm run dev
```

Opens on `http://localhost:5173` (Vite's default) and proxies `/api/*` to
the backend on port 8010 (see `frontend/vite.config.ts`) — the backend must
already be running. Log in with the same seeded email + dev password from
step 5 above.

## What's actually built right now

**Database**: full SPEC §4 data model — partitioned ledger/audit tables,
generated columns, row-level security (genuinely enforced — the API
connects as an unprivileged, non-superuser role; see migration `0004`'s
docstring for why that distinction matters), audit triggers, an
append-only ledger backed by both a grant-level REVOKE and a trigger. RBAC:
12 roles, 33 permissions, the full SPEC §7.3 grant matrix. Client data: 34
real items and 122 real locations (121 branches + 1 commissary) from the
client's workbook, plus assumed reference data (areas/clusters/routes/
calendar) not yet confirmed by the client — `db/seed/002_client_data.sql`
is annotated `[REAL]` / `[ASSUMED]` / `[DERIVED]` section by section.

**Backend API**: auth (JWT access/refresh + bcrypt), permission and
branch-scope enforcement (API-layer permission check + DB-layer RLS, per
SPEC §7.4 — neither substitutes for the other), and the core data-entry
surface: items (CRUD, aliases, effective-dated prices), locations (CRUD,
lifecycle status transitions with full history, OM assignment, closures),
six reference tables (categories/uom/clusters/areas/routes/reason-codes),
stock (balance + FEFO ageing, paginated ledger, manual adjustments),
receiving, waste, transfers, and physical counts (with separation-of-duties
on approval). 17 backend tests, all passing. See `backend/app/api/v1/` and
`backend/tests/`.

**Not yet built**: forecast engine, replenishment ladder, AC-1 calibration,
accuracy/bias analytics, the order run / Exception Workbench, file-ingest
pipeline, branch onboarding wizard, assortment templates. See
`docs/SPEC.md` §15 for the full build sequence — this repo is partway
through it.

**Frontend**: React 18 + Vite + TypeScript (strict) + Tailwind, design
tokens from SPEC §12.2 verbatim, TanStack Query/Table. Screens: login,
items, branches, reference data, stock explorer, counts, receiving, waste
log — the same surface the backend exposes above.

Every schema/seed change after the first is a normal Alembic migration in
`backend/alembic/versions/` — run `alembic history` to see them, `alembic
upgrade head` to apply anything new.

## Repository layout

```
cocopan-ims/
├── CLAUDE.md            # engineering standards — read before writing code
├── docs/SPEC.md         # the full system specification
├── docker-compose.yml   # cocoims-db (Postgres 16)
├── backend/
│   ├── app/              # FastAPI application
│   │   ├── api/v1/        # routers: items, locations, refdata, stock, receiving, waste, transfers, counts
│   │   ├── auth/           # JWT, permission + scope dependencies, login/refresh/logout/me
│   │   ├── core/           # settings, DB engine/session, RLS session-context plumbing
│   │   ├── domain/         # ledger.py — balance, FEFO ageing, write_movement
│   │   └── models/         # SQLAlchemy models mirroring db/ddl
│   ├── alembic/           # migrations — the source of truth for schema history
│   ├── scripts/            # set_dev_passwords.py (dev-only)
│   └── tests/              # pytest — deny-by-default, RLS-at-DB-layer, immutability, NULL≠0
├── frontend/             # React 18 + Vite + TypeScript + Tailwind
└── db/
    ├── ddl/                # baseline schema SQL + rpt schema
    ├── perf/               # performance indexes
    └── seed/                # baseline + client-data seed SQL
```

## Common tasks

| Task | Command |
|---|---|
| Reset the local database from scratch | `docker compose down -v && docker compose up -d` then `alembic upgrade head` |
| See pending migrations | `cd backend && alembic history` |
| Connect with psql | `docker exec -it cocoims-db psql -U cocoims -d cocoims` |
| Run the API with auto-reload | `cd backend && uvicorn app.main:app --reload --port 8010` |
| Run the frontend dev server | `cd frontend && npm run dev` |
| Run backend tests | `cd backend && pytest` |
| Lint / type-check backend | `cd backend && ruff check app tests scripts && mypy app tests scripts` |
| Type-check frontend | `cd frontend && npm run typecheck` |

## Known open items

`docs/SPEC.md` §16 lists everything still blocking a full build (unit costs,
authoritative SRP, POS availability, etc.). The `PENDING_REVIEW` rows in
`core.item_price` are a live instance of one of them — flagged, not resolved.
