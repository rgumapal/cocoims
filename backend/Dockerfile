FROM python:3.12-slim

WORKDIR /app

# libpq (via psycopg2-binary's wheel) needs no extra system packages on
# slim; kept minimal deliberately — no build-essential, since
# psycopg2-binary ships a prebuilt wheel.
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY alembic.ini .
COPY alembic ./alembic
COPY app ./app

# Cloud Run injects PORT (default 8080) and expects the container to listen
# on it — shell form so ${PORT} expands at container start, not build time.
ENV PORT=8080
CMD exec uvicorn app.main:app --host 0.0.0.0 --port ${PORT}
