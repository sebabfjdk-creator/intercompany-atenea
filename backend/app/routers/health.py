"""Health / readiness."""
from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.orm import Session

from db.base import get_db

router = APIRouter(prefix="/api", tags=["health"])


@router.get("/health")
def health():
    return {"status": "ok", "service": "intercompany-atenea"}


@router.get("/ready")
def ready(db: Session = Depends(get_db)):
    db.execute(text("SELECT 1"))
    return {"status": "ready", "db": "ok"}
