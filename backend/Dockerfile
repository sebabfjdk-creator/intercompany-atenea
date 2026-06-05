# Backend FastAPI — Intercompany Atenea
FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

COPY requirements.txt .
RUN pip install -r requirements.txt

COPY . .

EXPOSE 8000

# Railway inyecta $PORT; en local cae a 8000.
# v0.1: el esquema se crea en seed (create_all). Migrar a `alembic upgrade head`
# cuando existan migraciones versionadas.
CMD ["sh", "-c", "python -m app.seed && uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
