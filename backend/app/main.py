"""Punto de entrada FastAPI — Plataforma Intercompany Atenea."""
from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import get_settings
from app.routers import arap as arap_router
from app.routers import auth as auth_router
from app.routers import data as data_router
from app.routers import health as health_router
from app.routers import ingest as ingest_router
from app.routers import users as users_router

settings = get_settings()

app = FastAPI(
    title=settings.app_name,
    version="0.1.0",
    description="Conciliación intercompany Colombia (Siesa) ↔ España (DELSOL).",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"] if settings.debug else [],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health_router.router)
app.include_router(auth_router.router)
app.include_router(data_router.router)
app.include_router(ingest_router.router)
app.include_router(users_router.router)
app.include_router(arap_router.router)


@app.get("/")
def root():
    return {"app": settings.app_name, "docs": "/docs", "health": "/api/health"}
