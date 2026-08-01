from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import create_engine, text

from app.api.v1 import router as api_v1_router
from app.auth.router import router as auth_router
from app.core.config import settings

app = FastAPI(title="Cocopan IMS API")
# Only needed once the frontend is served from a different origin than the
# API (e.g. a separately deployed Cloud Run service) — same-origin dev
# traffic via Vite's proxy never triggers CORS at all.
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_allowed_origins_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(auth_router)
app.include_router(api_v1_router)

# Health check only — deliberately the owning-role engine, not
# app.core.db.engine: it touches no data, so there is nothing here for the
# unprivileged app role's RLS restrictions to apply to.
engine = create_engine(settings.database_url, pool_pre_ping=True)


@app.get("/health")
def health() -> dict:
    with engine.connect() as conn:
        conn.execute(text("SELECT 1"))
    return {"status": "ok"}
