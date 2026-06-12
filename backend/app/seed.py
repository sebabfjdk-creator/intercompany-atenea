"""Bootstrap de esquema y datos iniciales.

Para el MVP el esquema se crea con `Base.metadata.create_all` (idempotente).
Alembic queda cableado (db/migrations) para migraciones incrementales futuras.

Crea los usuarios iniciales (§C) si no existen:
- admin    (responsable España): lee/modifica todo.
- admin_co (responsable Colombia): modifica Colombia, lee España.
"""
from __future__ import annotations

import os

from sqlalchemy import select, text

from app.auth import hash_password
from db.base import Base, SessionLocal, engine
from db.models import SourceSystem, User

# Mini-migraciones idempotentes para columnas añadidas a tablas existentes
# (en prod usamos create_all, que NO altera tablas ya creadas). Solo Postgres.
_PG_ALTERS = [
    "ALTER TABLE arap_movimiento ADD COLUMN IF NOT EXISTS documento VARCHAR(60) DEFAULT ''",
    "ALTER TABLE arap_movimiento ADD COLUMN IF NOT EXISTS tipo_documento VARCHAR(20) DEFAULT ''",
    "ALTER TABLE pyg_movimiento ADD COLUMN IF NOT EXISTS nit VARCHAR(40) DEFAULT ''",
]


def crear_esquema() -> None:
    Base.metadata.create_all(bind=engine)
    if engine.dialect.name == "postgresql":
        with engine.begin() as conn:
            for stmt in _PG_ALTERS:
                conn.execute(text(stmt))


def _ensure_user(db, email: str, nombre: str, password: str, rol: str) -> None:
    if db.scalar(select(User).where(User.email == email)):
        return
    db.add(User(email=email, nombre=nombre, hashed_password=hash_password(password), rol=rol))


def _ensure_source(db, nombre: str, pais: str, fmt: str) -> None:
    if db.scalar(select(SourceSystem).where(SourceSystem.nombre == nombre)):
        return
    db.add(SourceSystem(nombre=nombre, pais=pais, tipo_formato=fmt))


def seed() -> None:
    crear_esquema()
    with SessionLocal() as db:
        _ensure_user(
            db,
            os.getenv("SEED_ADMIN_EMAIL", "admin@atenea.com"),
            "Responsable España",
            os.getenv("SEED_ADMIN_PASSWORD", "atenea-admin"),
            "admin",
        )
        _ensure_user(
            db,
            os.getenv("SEED_ADMINCO_EMAIL", "colombia@atenea.com"),
            "Responsable Colombia",
            os.getenv("SEED_ADMINCO_PASSWORD", "atenea-co"),
            "admin_co",
        )
        _ensure_user(
            db,
            os.getenv("SEED_USER3_EMAIL", "financiero@atenea.com"),
            "Financiero",
            os.getenv("SEED_USER3_PASSWORD", "atenea-fin"),
            "admin",
        )
        _ensure_source(db, "Siesa", "CO", "siesa_xlsx")
        _ensure_source(db, "DELSOL", "ES", "delsol_mayor")
        db.commit()
    print("[seed] esquema y datos iniciales listos")


if __name__ == "__main__":
    seed()
