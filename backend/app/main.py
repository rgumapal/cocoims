from fastapi import FastAPI
from sqlalchemy import create_engine, text

from app.core.config import settings

app = FastAPI(title="Cocopan IMS API")
engine = create_engine(settings.database_url, pool_pre_ping=True)


@app.get("/health")
def health() -> dict:
    with engine.connect() as conn:
        conn.execute(text("SELECT 1"))
    return {"status": "ok"}
