"""Endpoints del módulo AR/AP (Cuentas por Cobrar y Pagar)."""
from __future__ import annotations

import os
import tempfile

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile
from sqlalchemy.orm import Session

from app.auth import get_current_user
from app.services import arap_service as svc
from db.base import get_db
from db.models import AuditLog, User

router = APIRouter(prefix="/api", tags=["ar-ap"])


async def _save_tmp(file: UploadFile) -> str:
    suffix = os.path.splitext(file.filename or "")[1] or ".xlsx"
    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=suffix)
    tmp.write(await file.read())
    tmp.close()
    return tmp.name


@router.post("/ingest/ar-ap/colombia")
async def ingest_co(file: UploadFile = File(...), db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    path = await _save_tmp(file)
    try:
        try:
            res = svc.ingest_colombia(db, path)
        except Exception as e:  # noqa: BLE001
            raise HTTPException(422, f"Error procesando el archivo: {e}")
        db.add(AuditLog(entidad="arap", entidad_id="colombia", accion="create",
                        valor_despues=str(res), usuario_id=user.id))
        db.commit()
        return {"ok": True, "archivo": file.filename, **res}
    finally:
        try: os.unlink(path)
        except OSError: pass


@router.post("/ingest/ar-ap/espana")
async def ingest_es(file: UploadFile = File(...), db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    if user.rol == "admin_co":
        raise HTTPException(403, "admin_co no puede modificar datos del libro de España")
    path = await _save_tmp(file)
    try:
        try:
            res = svc.ingest_espana(db, path)
        except Exception as e:  # noqa: BLE001
            raise HTTPException(422, f"Error procesando el archivo: {e}")
        db.add(AuditLog(entidad="arap", entidad_id="espana", accion="create",
                        valor_despues=str(res), usuario_id=user.id))
        db.commit()
        return {"ok": True, "archivo": file.filename, **res}
    finally:
        try: os.unlink(path)
        except OSError: pass


@router.get("/ar-ap/estado-datos")
def estado(db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    return svc.estado_datos(db)


@router.get("/ar-ap/comparativa")
def comparativa(tipo: str | None = Query(None, pattern="^(AR|AP)$"),
                db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    return svc.reconciliacion(db, tipo)


@router.get("/ar-ap/excepciones")
def excepciones(db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    return svc.excepciones(db)


@router.get("/ar-ap/errores")
def errores(db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    return svc.errores_contables(db)


@router.get("/ar-ap/cuentas-amarillas")
def provisionales(db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    return svc.provisionales(db)
