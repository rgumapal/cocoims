# Cocopan Inventory Management System (CIMS)

Read [`docs/SPEC.md`](docs/SPEC.md) for the full system specification and
[`CLAUDE.md`](CLAUDE.md) for the engineering standards this repo holds itself
to. This file is just the "get it running" quickstart.

## Prerequisites

- Docker
- Python 3.12+
- Node 18+ (once the frontend is scaffolded — not yet present)

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

# 4. Bring the database to current schema + seed data
alembic upgrade head

# 5. Run the API
uvicorn app.main:app --reload --port 8000
```

Check it worked: `curl http://127.0.0.1:8000/health` → `{"status":"ok"}`.
That endpoint round-trips a real query to `cocoims-db`, so it's a genuine
smoke test, not just "the process started."

## What's actually in the database right now

- **Schema**: full SPEC §4 data model — partitioned ledger/audit tables,
  generated columns, row-level security, audit triggers. See `db/ddl/001_schema.sql`.
- **RBAC**: 12 roles, 33 permissions, the full SPEC §7.3 grant matrix. See `db/seed/001_seed.sql`.
- **Client data**: 34 real items and 121 real branches from the client's
  workbook, plus assumed reference data (areas/clusters/routes/calendar) not
  yet confirmed by the client. See `db/seed/002_client_data.sql` — it's
  annotated `[REAL]` / `[ASSUMED]` / `[DERIVED]` section by section.

Every schema/seed change after the first is a normal Alembic migration in
`backend/alembic/versions/` — run `alembic history` to see them, `alembic
upgrade head` to apply anything new.

## Repository layout

```
cocopan-ims/
├── CLAUDE.md          # engineering standards — read before writing code
├── docs/SPEC.md        # the full system specification
├── docker-compose.yml  # cocoims-db (Postgres 16)
├── backend/
│   ├── app/            # FastAPI application (api/, domain/, auth/, ingest/, integration/, models/, jobs/)
│   └── alembic/         # migrations — the source of truth for schema history
├── frontend/            # React 18 + Vite + TypeScript (scaffolding pending)
└── db/
    ├── ddl/              # baseline schema SQL
    └── seed/              # baseline + client-data seed SQL
```

## Common tasks

| Task | Command |
|---|---|
| Reset the local database from scratch | `docker compose down -v && docker compose up -d` then `alembic upgrade head` |
| See pending migrations | `cd backend && alembic history` |
| Connect with psql | `docker exec -it cocoims-db psql -U cocoims -d cocoims` |
| Run the API with auto-reload | `cd backend && uvicorn app.main:app --reload --port 8000` |

## Known open items

`docs/SPEC.md` §16 lists everything still blocking a full build (unit costs,
authoritative SRP, POS availability, etc.). The 26 `PENDING_REVIEW` rows in
`core.item_price` are a live instance of one of them — flagged, not resolved.
