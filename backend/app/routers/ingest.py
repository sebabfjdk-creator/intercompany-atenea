"""Endpoint de ingesta por subida de Excel."""
from __future__ import annotations

import os
import tempfile
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth import get_current_user
from app.services import ingest as ingest_svc
from db.base import get_db
from db.models import AuditLog, FileUpload, User

router = APIRouter(prefix="/api/ingest", tags=["ingest"])

# tipos que tocan el libro de España (admin_co no puede escribirlos)
_ES_TIPOS = {"espana", "homologacion", "terceros", "arap_es"}


@router.post("/{tipo}")
async def subir(
    tipo: str,
    file: UploadFile = File(...),
    replace: bool = Query(False, description="Confirma reemplazar un periodo ya cargado"),
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
        # Control de duplicados: si el periodo ya está cargado y no se confirmó, 409.
        if not replace:
            try:
                periodos = ingest_svc.periodos_de(tipo, tmp.name)
            except Exception as e:  # noqa: BLE001
                raise HTTPException(422, f"Error leyendo el archivo: {e}")
            conflicto = ingest_svc.periodos_en_conflicto(db, tipo, periodos)
            if conflicto:
                etiqueta = ", ".join(p for p in conflicto if p) or tipo
                raise HTTPException(409, detail={
                    "code": "periodo_existe", "periodos": conflicto,
                    "mensaje": f"Ya existe información cargada para {etiqueta}. ¿Deseas reemplazarla?",
                })
        try:
            resultado = ingest_svc.INGESTORS[tipo](db, tmp.name)
        except Exception as e:  # noqa: BLE001
            raise HTTPException(422, f"Error procesando el archivo: {e}")
        db.add(AuditLog(
            entidad="import", entidad_id=tipo, accion="create",
            valor_despues=str(resultado), usuario_id=user.id,
        ))
        db.commit()
        ingest_svc.registrar_carga(db, tipo=tipo, nombre_original=file.filename or "",
                                   path=tmp.name, resultado=resultado, usuario_id=user.id)
        return {"ok": True, "archivo": file.filename, **resultado}
    finally:
        try:
            os.unlink(tmp.name)
        except OSError:
            pass


_TIPO_LABEL = {
    "espana": "España (DELSOL)", "colombia": "Colombia (Siesa)",
    "homologacion": "Homologación", "terceros": "Puente terceros",
    "arap_co": "AR/AP Colombia", "arap_es": "AR/AP España",
}


@router.get("/archivos")
def listar_archivos(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """Historial de cargas (gestión de archivos): qué, qué periodo, quién y cuándo."""
    rows = db.execute(
        select(FileUpload, User.email)
        .join(User, FileUpload.usuario_id == User.id, isouter=True)
        .order_by(FileUpload.fecha_carga.desc())
    ).all()
    return [{
        "id": f.id, "tipo": f.tipo_archivo, "tipo_label": _TIPO_LABEL.get(f.tipo_archivo, f.tipo_archivo),
        "archivo": f.nombre_original, "periodo": f.periodo, "usuario": email or "—",
        "fecha": f.fecha_carga.isoformat() if f.fecha_carga else None,
        "registros": f.registros_insertados, "estado": f.estado, "observaciones": f.observaciones,
    } for f, email in rows]


class ObservacionIn(BaseModel):
    observaciones: str = ""


@router.put("/archivos/{fid}")
def editar_archivo(fid: int, payload: ObservacionIn, db: Session = Depends(get_db),
                   user: User = Depends(get_current_user)):
    """✏️ Editar SOLO observaciones/comentarios. Nunca toca datos contables."""
    fu = db.get(FileUpload, fid)
    if not fu:
        raise HTTPException(404, "Carga no encontrada")
    fu.observaciones = (payload.observaciones or "")[:1000]
    fu.fecha_actualizacion = datetime.now(timezone.utc)
    db.add(AuditLog(entidad="file_upload", entidad_id=str(fid), accion="update",
                    valor_despues=fu.observaciones[:200], usuario_id=user.id))
    db.commit()
    return {"ok": True}


@router.delete("/archivos/{fid}")
def eliminar_archivo(fid: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """🗑️ Elimina la carga y los registros contables del periodo. Recalculo en vivo."""
    fu = db.get(FileUpload, fid)
    if not fu:
        raise HTTPException(404, "Carga no encontrada")
    if fu.tipo_archivo in _ES_TIPOS and user.rol == "admin_co":
        raise HTTPException(403, "admin_co no puede eliminar datos del libro de España/homologación")
    if fu.estado == "eliminado":
        raise HTTPException(409, "La carga ya estaba eliminada")
    ingest_svc.eliminar_datos_de(db, fu.tipo_archivo, fu.periodo)
    fu.estado = "eliminado"
    fu.fecha_actualizacion = datetime.now(timezone.utc)
    db.add(AuditLog(entidad="file_upload", entidad_id=str(fid), accion="delete",
                    valor_antes=f"{fu.tipo_archivo} {fu.periodo} ({fu.registros_insertados} reg)",
                    usuario_id=user.id))
    db.commit()
    return {"ok": True, "tipo": fu.tipo_archivo, "periodo": fu.periodo}


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
