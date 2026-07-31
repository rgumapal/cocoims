from fastapi import FastAPI
from sqlalchemy import create_engine, text

from app.auth.router import router as auth_router
from app.core.config import settings

app = FastAPI(title="Cocopan IMS API")
app.include_router(auth_router)

# Health check only — deliberately the owning-role engine, not
# app.core.db.engine: it touches no data, so there is nothing here for the
# unprivileged app role's RLS restrictions to apply to.
engine = create_engine(settings.database_url, pool_pre_ping=True)


@app.get("/health")
def health() -> dict:
    with engine.connect() as conn:
        conn.execute(text("SELECT 1"))
    return {"status": "ok"}
