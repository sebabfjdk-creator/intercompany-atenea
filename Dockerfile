# Dockerfile RAÍZ — para Railway (que busca el Dockerfile en la raíz del repo).
# Construye y arranca el BACKEND FastAPI, cuyo código vive en backend/.
# El contexto de build es la raíz del repo, por eso las rutas usan el prefijo backend/.
#
# Para desarrollo local se sigue usando docker-compose.yml (build: ./backend) y
# backend/Dockerfile. Este archivo es el punto de entrada de despliegue en Railway.
FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# Dependencias primero (capa cacheable)
COPY backend/requirements.txt .
RUN pip install -r requirements.txt

# Código del backend -> /app (los imports son app.*, db.*, ingestion.*, domain.*)
COPY backend/ .

EXPOSE 8000

# Railway inyecta $PORT y DATABASE_URL; en local cae a 8000.
# v0.1: el esquema se crea en seed (create_all). Migrar a `alembic upgrade head`
# cuando existan migraciones versionadas.
CMD ["sh", "-c", "python -m app.seed && uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
