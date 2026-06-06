"""Endpoints de datos para los tableros (lectura)."""
from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.auth import get_current_user
from app.services import queries
from db.base import get_db
from db.models import User

router = APIRouter(prefix="/api", tags=["data"])


@router.get("/estado-datos")
def estado_datos(db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    return queries.estado_datos(db)


@router.get("/comparativa")
def comparativa(db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    return queries.comparativa(db)


@router.get("/resumen")
def resumen(db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    return queries.resumen(db)


@router.get("/excepciones")
def excepciones(db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    return queries.excepciones(db)


@router.get("/terceros")
def terceros(db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    return queries.terceros(db)


@router.get("/config/homologacion")
def homologacion(db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    return queries.homologacion(db)


@router.get("/auditoria")
def auditoria(db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    return queries.auditoria(db)
