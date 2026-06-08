"""Endpoints del módulo AR/AP (Cuentas por Cobrar y Pagar)."""
from __future__ import annotations

import os
import tempfile

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile
from sqlalchemy.orm import Session

from app.auth import get_current_user
from app.services import arap_service as svc
from app.services import ingest as ingest_svc
from db.base import get_db
from db.models import AuditLog, User

router = APIRouter(prefix="/api", tags=["ar-ap"])


async def _save_tmp(file: UploadFile) -> str:
    suffix = os.path.splitext(file.filename or "")[1] or ".xlsx"
    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=suffix)
    tmp.write(await file.read())
    tmp.close()
    return tmp.name


def _conflicto_arap(db: Session, tipo: str, replace: bool) -> None:
    if replace:
        return
    if ingest_svc.periodos_en_conflicto(db, tipo, [""]):
        raise HTTPException(409, detail={
            "code": "periodo_existe", "periodos": [],
            "mensaje": "Ya existe una cartera AR/AP cargada para este país. ¿Deseas reemplazarla?",
        })


@router.post("/ingest/ar-ap/colombia")
async def ingest_co(file: UploadFile = File(...), replace: bool = Query(False),
                    db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    _conflicto_arap(db, "arap_co", replace)
    path = await _save_tmp(file)
    try:
        try:
            res = svc.ingest_colombia(db, path)
        except Exception as e:  # noqa: BLE001
            raise HTTPException(422, f"Error procesando el archivo: {e}")
        db.add(AuditLog(entidad="arap", entidad_id="colombia", accion="create",
                        valor_despues=str(res), usuario_id=user.id))
        db.commit()
        ingest_svc.registrar_carga(db, tipo="arap_co", nombre_original=file.filename or "",
                                   path=path, resultado=res, usuario_id=user.id)
        return {"ok": True, "archivo": file.filename, **res}
    finally:
        try: os.unlink(path)
        except OSError: pass


@router.post("/ingest/ar-ap/espana")
async def ingest_es(file: UploadFile = File(...), replace: bool = Query(False),
                    db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    if user.rol == "admin_co":
        raise HTTPException(403, "admin_co no puede modificar datos del libro de España")
    _conflicto_arap(db, "arap_es", replace)
    path = await _save_tmp(file)
    try:
        try:
            res = svc.ingest_espana(db, path)
        except Exception as e:  # noqa: BLE001
            raise HTTPException(422, f"Error procesando el archivo: {e}")
        db.add(AuditLog(entidad="arap", entidad_id="espana", accion="create",
                        valor_despues=str(res), usuario_id=user.id))
        db.commit()
        ingest_svc.registrar_carga(db, tipo="arap_es", nombre_original=file.filename or "",
                                   path=path, resultado=res, usuario_id=user.id)
        return {"ok": True, "archivo": file.filename, **res}
    finally:
        try: os.unlink(path)
        except OSError: pass


@router.get("/ar-ap/estado-datos")
def estado(db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    return svc.estado_datos(db)


@router.get("/ar-ap/comparativa")
def comparativa(tipo: str | None = Query(None, pattern="^(AR|AP)$"),
                desde: str | None = Query(None), hasta: str | None = Query(None),
                db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    return svc.reconciliacion(db, tipo, desde, hasta)


@router.get("/ar-ap/movimientos-tercero")
def movimientos_tercero(nit: str = Query(...), desde: str | None = Query(None), hasta: str | None = Query(None),
                        db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    return svc.movimientos_tercero(db, nit, desde, hasta)


@router.get("/ar-ap/tercero/{nit}")
def tercero_360(nit: str, db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    return svc.tercero_360(db, nit)


@router.get("/ar-ap/kpis")
def kpis(db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    return svc.kpis_arap(db)


@router.get("/ar-ap/export")
def export_arap(db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    import io

    import openpyxl
    from fastapi.responses import StreamingResponse
    data = svc.reconciliacion(db)
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "AR-AP"
    ws.append(["Tercero", "NIT", "Categoría", "Saldo CO", "Saldo ES", "Diferencia", "Estado", "Cruce"])
    for f in data["filas"]:
        ws.append([f["nombre"], f["nit"], f["categoria"], f["saldo_co"], f["saldo_es"],
                   f["diferencia"], f["estado"], f.get("matched_por") or ""])
    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)
    return StreamingResponse(
        buf, media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": "attachment; filename=ar-ap.xlsx"})


@router.get("/ar-ap/excepciones")
def excepciones(db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    return svc.excepciones(db)


@router.get("/ar-ap/errores")
def errores(db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    return svc.errores_contables(db)


@router.get("/ar-ap/cuentas-amarillas")
def provisionales(db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    return svc.provisionales(db)
