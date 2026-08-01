# Cocopan Inventory Management System (CIMS)

Read [`docs/SPEC.md`](docs/SPEC.md) for the full system specification and
[`CLAUDE.md`](CLAUDE.md) for the engineering standards this repo holds itself
to. This file is just the "get it running" quickstart.

## Prerequisites

- [gcloud CLI](https://cloud.google.com/sdk/docs/install), authenticated
  (`gcloud auth login` + `gcloud auth application-default login`) with
  access to the `cocoims` GCP project
- [Cloud SQL Auth Proxy](https://cloud.google.com/sql/docs/postgres/connect-auth-proxy) —
  dev DB connectivity
- Python 3.12+
- Node 18+ (LTS 24.x confirmed working)
- Docker — only needed for the optional local-Postgres fallback and for
  building deploy images

## Quickstart

```bash
# 1. Environment
cp .env.example .env
# fill in the real Cloud SQL passwords (ask a teammate / check Secret
# Manager — never commit real values)

# 2. Database — Cloud SQL (cocoims:asia-southeast1:cocoims-db) via the
#    Cloud SQL Auth Proxy, not a local container. This is a prototype with
#    no live client data yet, so there's nothing local isolation is
#    protecting you from, and Cloud SQL bills for instance uptime, not
#    query volume — pointing dev traffic at it costs nothing extra.
#    Requires `gcloud auth application-default login` once per machine.
cloud-sql-proxy --port 5433 cocoims:asia-southeast1:cocoims-db &

# 3. Backend
cd backend
python -m venv .venv
./.venv/Scripts/activate      # Windows Git Bash; use bin/activate on macOS/Linux
pip install -r requirements.txt
pip install -r requirements-dev.txt   # pytest, mypy, ruff — needed to run tests/lint

# 4. Bring the database to current schema + seed data
alembic upgrade head

# 5. Optional, dev-only: set a bcrypt password on every seeded account for
#    the dormant /api/v1/auth/login fallback (not what the frontend UI
#    actually uses — see step 6's login note below). Skip this unless
#    you're specifically testing that fallback path.
python -m scripts.set_dev_passwords

# 6. Run the API
#    Port 8000 is the FastAPI/uvicorn convention, but collides with an
#    unrelated project on at least one dev machine this has been built on
#    — 8010 is what's actually been used and tested throughout. Either
#    works; the frontend's Vite proxy (frontend/vite.config.ts) assumes 8010.
uvicorn app.main:app --reload --port 8010
```

Check it worked: `curl http://127.0.0.1:8010/health` → `{"status":"ok"}`.
That endpoint round-trips a real query to Cloud SQL, so it's a genuine
smoke test, not just "the process started."

Login is via Firebase (Google sign-in or email+password), not the seeded
`password_hash` column — accounts are admin-provisioned, no public sign-up.
`regie.gumapal@gmail.com` is the one real, already-provisioned account.
To get a second login for testing, create a user through the app itself
(Users & Roles → New User) — that auto-provisions a Firebase credential and
returns a one-time password-setup link.

Once logged in via the frontend (below), `http://127.0.0.1:8010/docs` is
still useful for exercising endpoints directly (FastAPI's auto-generated
Swagger UI) — click **Authorize** and paste the access token from your
browser's session (`localStorage`) rather than using `/api/v1/auth/login`,
which is the dormant bcrypt fallback the UI no longer calls.

### Frontend

```bash
cd frontend
npm install
npm run dev
```

Opens on `http://localhost:5173` (Vite's default) and proxies `/api/*` to
the backend on port 8010 (see `frontend/vite.config.ts`) — the backend must
already be running. Log in as `regie.gumapal@gmail.com` via Google, or
create your own account through the app first (see the login note above).

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

**Backend API**: Firebase Auth (Google sign-in + email/password,
admin-provisioned accounts only — no public sign-up; the old JWT/bcrypt
`/api/v1/auth/login` stays as a dormant fallback), permission and
branch-scope enforcement (API-layer permission check + DB-layer RLS, per
SPEC §7.4 — neither substitutes for the other), a post-login dashboard
(one permission-gated aggregate read per nav screen), and the core
data-entry surface: items (CRUD, aliases, effective-dated prices),
locations (CRUD, lifecycle status transitions with full history, OM
assignment, closures), six reference tables
(categories/uom/clusters/areas/routes/reason-codes), stock (balance + FEFO
ageing, paginated ledger, manual adjustments), receiving and sales
(diff-based edits against the append-only ledger — editing a saved day
writes a signed correction, never an UPDATE/DELETE), waste, transfers, and
physical counts (with separation-of-duties on approval). 18 backend tests,
all passing. See `backend/app/api/v1/` and `backend/tests/`.

**Not yet built**: forecast engine, replenishment ladder, AC-1 calibration,
accuracy/bias analytics, the order run / Exception Workbench, file-ingest
pipeline, branch onboarding wizard, assortment templates. See
`docs/SPEC.md` §15 for the full build sequence — this repo is partway
through it.

**Frontend**: React 18 + Vite + TypeScript (strict) + Tailwind, design
tokens from SPEC §12.2 verbatim, TanStack Query/Table. Screens: login,
dashboard, items, branches, reference data, stock explorer, counts,
receiving, sales, waste log, users & roles — the same surface the backend
exposes above.

**Deployment**: both services run on Cloud Run (`cocoims-api`,
`cocoims-web`) behind the custom domain `cims.rgsuite.net`, built via
`gcloud builds submit` from each service's `Dockerfile`/`cloudbuild.yaml`.
See the `deploy` skill for the full build → migrate → deploy sequence.

Every schema/seed change after the first is a normal Alembic migration in
`backend/alembic/versions/` — run `alembic history` to see them, `alembic
upgrade head` to apply anything new (against Cloud SQL directly — see
above).

## Repository layout

```
cocopan-ims/
├── CLAUDE.md            # engineering standards — read before writing code
├── docs/SPEC.md         # the full system specification
├── docker-compose.yml   # cocoims-db (Postgres 16) — optional/fallback, see below
├── backend/
│   ├── app/              # FastAPI application
│   │   ├── api/v1/        # routers: dashboard, items, locations, refdata, stock, receiving, sales, waste, transfers, counts, users
│   │   ├── auth/           # Firebase verification/provisioning, JWT fallback, permission + scope dependencies
│   │   ├── core/           # settings, DB engine/session, RLS session-context plumbing
│   │   ├── domain/         # ledger.py — balance, FEFO ageing, write_movement
│   │   └── models/         # SQLAlchemy models mirroring db/ddl
│   ├── alembic/           # migrations — the source of truth for schema history
│   ├── scripts/            # set_dev_passwords.py (dev-only, dormant-fallback only)
│   ├── Dockerfile          # Cloud Run image
│   └── tests/              # pytest — deny-by-default, RLS-at-DB-layer, immutability, NULL≠0
├── frontend/             # React 18 + Vite + TypeScript + Tailwind
│   ├── Dockerfile          # Cloud Run image (nginx + built static assets)
│   └── cloudbuild.yaml     # bakes VITE_* build args (API URL, Firebase config) at build time
└── db/
    ├── ddl/                # baseline schema SQL + rpt schema
    ├── perf/               # performance indexes
    └── seed/                # baseline + client-data seed SQL
```

## Common tasks

| Task | Command |
|---|---|
| Start the Cloud SQL Auth Proxy | `cloud-sql-proxy --port 5433 cocoims:asia-southeast1:cocoims-db` |
| See pending migrations | `cd backend && alembic history` |
| Connect with psql (via the proxy, above) | `psql "postgresql://cocoims@127.0.0.1:5433/cocoims"` |
| Run the API with auto-reload | `cd backend && uvicorn app.main:app --reload --port 8010` |
| Run the frontend dev server | `cd frontend && npm run dev` |
| Run backend tests | `cd backend && pytest` |
| Lint / type-check backend | `cd backend && ruff check app tests scripts && mypy app tests scripts` |
| Type-check frontend | `cd frontend && npm run typecheck` |
| Isolated local Postgres (risky migration iteration only) | `docker compose up -d`, point `.env` at `localhost:5433` with the `POSTGRES_*` creds, `docker compose down -v` to wipe |
| Build + deploy | see the `deploy` skill |

## Known open items

`docs/SPEC.md` §16 lists everything still blocking a full build (unit costs,
authoritative SRP, POS availability, etc.). The `PENDING_REVIEW` rows in
`core.item_price` are a live instance of one of them — flagged, not resolved.
