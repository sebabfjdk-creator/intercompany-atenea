"""Endpoint de ingesta por subida de Excel."""
from __future__ import annotations

import os
import tempfile

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from sqlalchemy.orm import Session

from app.auth import get_current_user
from app.services import ingest as ingest_svc
from db.base import get_db
from db.models import AuditLog, User

router = APIRouter(prefix="/api/ingest", tags=["ingest"])

# tipos que tocan el libro de España (admin_co no puede escribirlos)
_ES_TIPOS = {"espana", "homologacion", "terceros"}


@router.post("/{tipo}")
async def subir(
    tipo: str,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    if tipo not in ingest_svc.INGESTORS:
        raise HTTPException(400, f"Tipo no soportado: {tipo}. Use: {list(ingest_svc.INGESTORS)}")
    if tipo in _ES_TIPOS and user.rol == "admin_co":
        raise HTTPException(403, "admin_co no puede modificar datos del libro de España/homologación")

    suffix = os.path.splitext(file.filename or "")[1] or ".xlsx"
    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=suffix)
    try:
        tmp.write(await file.read())
        tmp.close()
        try:
            resultado = ingest_svc.INGESTORS[tipo](db, tmp.name)
        except Exception as e:  # noqa: BLE001
            raise HTTPException(422, f"Error procesando el archivo: {e}")
        db.add(AuditLog(
            entidad="import", entidad_id=tipo, accion="create",
            valor_despues=str(resultado), usuario_id=user.id,
        ))
        db.commit()
        return {"ok": True, "archivo": file.filename, **resultado}
    finally:
        try:
            os.unlink(tmp.name)
        except OSError:
            pass


@router.post("/auto/detect")
async def autodetectar(file: UploadFile = File(...), user: User = Depends(get_current_user)):
    """Sugiere el tipo de un archivo por sus hojas (no ingiere)."""
    suffix = os.path.splitext(file.filename or "")[1] or ".xlsx"
    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=suffix)
    try:
        tmp.write(await file.read())
        tmp.close()
        return {"tipo": ingest_svc.detectar_tipo(tmp.name), "archivo": file.filename}
    finally:
        try:
            os.unlink(tmp.name)
        except OSError:
            pass
