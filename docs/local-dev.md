# Local Development Database — Details & Rationale

## Why local dev connects directly to Cloud SQL

This is deliberate, not an oversight:

- This is still a prototype with no live client/business data to protect from
  dev traffic.
- Cloud SQL bills for instance uptime and storage, not query volume — the
  instance already runs 24/7 for production regardless of whether local dev
  also connects.
- A single database means no local/prod migration drift — the kind of drift
  that cost real time reconciling two databases mid-deploy before this
  decision.

**Revisit this** if/when real client testing begins and live transactional
data needs protecting from dev experiments.

## Setup

```
cloud-sql-proxy --port 5433 cocoims:asia-southeast1:cocoims-db
```

Auto-authenticates via `gcloud auth application-default login`. Connection
details come from `.env` (copy from `.env.example`, fill in real passwords).
Nothing about `DATABASE_URL`/`APP_DATABASE_URL` changed shape — only what's
on the other end of `127.0.0.1:5433`.

## Local Postgres fallback

`docker-compose.yml` (`cocoims-db`, local Postgres 16) exists as a **fallback
only** — spin it up when you deliberately want an isolated, disposable
database to iterate on a risky migration before it touches the one real
thing. Swap `.env`'s two URLs to the `POSTGRES_*` block in the same file
(matching the old `localhost:5433` local-Postgres credentials).
`docker-entrypoint-initdb.d` runs the `db/ddl`/`db/seed` baseline on a fresh
fallback container.

## Why schema is plain SQL, not ORM-generated

The schema uses partitioned tables, generated columns, exclusion constraints,
row-level security and triggers — none of which Alembic/SQLAlchemy
autogenerate can produce reliably. `db/ddl`/`db/seed` baseline files are what
`0001_baseline.py` replays, matching Alembic revision `0001`. Everything
after is a normal incremental Alembic migration.

Migrations run with `alembic upgrade head` from `backend/` — against Cloud
SQL directly, so **this is the one and only migration run**; there's no
separate "did I also apply this to prod" step. Deploying code still requires
running migrations against Cloud SQL too, since Cloud Run doesn't do that
automatically on deploy — see the `deploy` skill.
