---
name: deploy
description: Build, migrate, and deploy the Cocopan IMS backend and/or frontend to Cloud Run (project "cocoims").
---

Deploys this repo's current `HEAD` to Cloud Run. Invoking this skill IS the
user's authorization to push to production — don't ask for confirmation
again before running the `gcloud` commands below, but DO stop and flag
anything unexpected (see "Before running a destructive migration" below).

## Fixed facts (verified working — don't rediscover these)

- GCP project: `cocoims`. Region: `asia-southeast1`.
- Cloud SQL instance: `cocoims:asia-southeast1:cocoims-db` (the *only*
  database — local dev also connects directly to it, see CLAUDE.md).
- Cloud Run services: `cocoims-api` (backend), `cocoims-web` (frontend).
- Artifact Registry images: `asia-southeast1-docker.pkg.dev/cocoims/cocoims/backend:latest`
  and `.../frontend:latest`.
- Backend secrets (already attached to `cocoims-api`, don't need to be
  re-passed on redeploy unless you're changing them): `cocoims-database-url`,
  `cocoims-app-database-url`, `cocoims-jwt-secret`.
- Frontend has no runtime env vars — everything is baked in at *build* time
  via Vite `--build-arg`s (see `frontend/cloudbuild.yaml`). Current values
  (Firebase web API keys are meant to be public/client-embedded, not
  secret — restricted via Firebase Console, not confidentiality):
  ```
  _VITE_API_BASE_URL=https://cocoims-api-107351275174.asia-southeast1.run.app
  _VITE_FIREBASE_API_KEY=AIzaSyB6jl2yHbS5gVrJSjYt-SK6We2gFUbCST8
  _VITE_FIREBASE_APP_ID=1:107351275174:web:865d30b32dea5ff8542667
  _VITE_FIREBASE_AUTH_DOMAIN=cocoims.firebaseapp.com
  _VITE_FIREBASE_PROJECT_ID=cocoims
  ```
  If these ever need to change, `gcloud builds list --limit=5 --format="table(id,substitutions)"`
  shows what the last successful build actually used.

## Step 0 — decide scope

Ask (or infer from what changed): backend only, frontend only, or both?
Skip the sections that don't apply.

## Step 1 — commit and push first

Deploying uncommitted work makes `git log` lie about what's actually
running in production. If there are uncommitted changes, commit them
(grouped by logical change, matching this repo's existing commit style —
`git log --oneline -10` for reference) and `git push origin master` before
building anything.

## Step 2 — backend: build, migrate, deploy

```bash
# from repo root
gcloud builds submit --tag=asia-southeast1-docker.pkg.dev/cocoims/cocoims/backend:latest backend/
```

**Before running a destructive migration** (anything that deletes/alters
existing rows, not just adds a nullable column or a new table): check what
`alembic upgrade head` is actually about to touch. `alembic history` in
`backend/` shows pending revisions; read any migration between prod's
current revision and head that isn't purely additive. If one deletes or
transforms existing data, inspect the actual affected rows in Cloud SQL
first (via the job pattern below, read-only) before applying — don't
assume prod's data matches local/dev assumptions.

Run migrations via a Cloud Run Job using the image just pushed (reuses the
exact same secrets/Cloud SQL connection as the live service — don't
hand-roll a separate psycopg2 connection string, and don't use raw
`psycopg2.connect()` against `DATABASE_URL` directly: it's a
`postgresql+psycopg2://` SQLAlchemy DSN, which psycopg2 alone can't parse.
Use `alembic` or SQLAlchemy's `create_engine`, both of which handle the
`+psycopg2` suffix correctly):

```bash
# Create once (idempotent — if it already exists, `update` instead of `create`)
gcloud run jobs create cocoims-migrate \
  --image=asia-southeast1-docker.pkg.dev/cocoims/cocoims/backend:latest \
  --region=asia-southeast1 \
  --set-cloudsql-instances=cocoims:asia-southeast1:cocoims-db \
  --set-secrets=DATABASE_URL=cocoims-database-url:latest,APP_DATABASE_URL=cocoims-app-database-url:latest,JWT_SECRET_KEY=cocoims-jwt-secret:latest \
  --command=alembic --args=upgrade,head
# (on a later deploy, the job already exists — just update its image then execute)
gcloud run jobs update cocoims-migrate --region=asia-southeast1 \
  --image=asia-southeast1-docker.pkg.dev/cocoims/cocoims/backend:latest \
  --command=alembic --args=upgrade,head

gcloud run jobs execute cocoims-migrate --region=asia-southeast1 --wait
gcloud logging read 'resource.type="cloud_run_job" AND resource.labels.job_name="cocoims-migrate"' \
  --limit=50 --format="value(textPayload)" --freshness=10m
```

**Gotcha:** `gcloud run jobs update --args=a,b,c` splits on *every* comma
in the value, including ones inside a quoted string you didn't mean as a
separator (e.g. a Python `-c` one-liner, or a SQL column list). If you need
a custom read-only check via `--command=python --args=-c,"<code>"`, the
`<code>` string must contain **zero commas** — use `;` to separate
statements and `chr(9)`/string concatenation instead of comma-separated
function args where needed.

Then deploy the service itself:

```bash
gcloud run deploy cocoims-api \
  --image=asia-southeast1-docker.pkg.dev/cocoims/cocoims/backend:latest \
  --region=asia-southeast1 --platform=managed
```

(Existing env vars/secrets on the service carry over automatically — no
need to re-pass them unless you're changing one.)

## Step 3 — frontend: build, deploy

```bash
# from repo root — cloudbuild.yaml's build context is frontend/
gcloud builds submit --config=frontend/cloudbuild.yaml \
  --substitutions=_VITE_API_BASE_URL=https://cocoims-api-107351275174.asia-southeast1.run.app,_VITE_FIREBASE_API_KEY=AIzaSyB6jl2yHbS5gVrJSjYt-SK6We2gFUbCST8,_VITE_FIREBASE_APP_ID=1:107351275174:web:865d30b32dea5ff8542667,_VITE_FIREBASE_AUTH_DOMAIN=cocoims.firebaseapp.com,_VITE_FIREBASE_PROJECT_ID=cocoims \
  frontend/

gcloud run deploy cocoims-web \
  --image=asia-southeast1-docker.pkg.dev/cocoims/cocoims/frontend:latest \
  --region=asia-southeast1 --platform=managed
```

## Step 4 — verify

```bash
curl -s -o /dev/null -w "api: %{http_code}\n" https://cocoims-api-107351275174.asia-southeast1.run.app/openapi.json
curl -s -o /dev/null -w "web: %{http_code}\n" https://cocoims-web-107351275174.asia-southeast1.run.app/
curl -s -o /dev/null -w "domain: %{http_code}\n" https://cims.rgsuite.net/
```

Then, per the standing "browser verification is the default" preference:
open `https://cims.rgsuite.net` in the browser and confirm the specific
thing you shipped actually works there — a 200 response only proves the
server started, not that the feature is correct. Confirm the frontend is
serving the *new* bundle, not a cached one, by checking the hashed asset
filename changed:
```js
[...document.scripts].find(s => s.src.includes('/assets/index-')).src
```

## After

Report back: what was deployed, the revision names now serving 100%
traffic (`gcloud run services describe <service> --region=asia-southeast1 --format="value(status.latestReadyRevisionName)"`),
and what was verified. Don't delete `cocoims-migrate` — it's reused every
deploy that has pending migrations.
