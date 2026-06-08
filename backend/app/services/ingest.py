"""Servicio de ingesta: parsea un Excel subido y puebla la BD.

Tipos soportados:
  - 'espana'       -> AccountPeriod (pais ES) desde el Libro Mayor DELSOL
  - 'colombia'     -> AccountPeriod (pais CO) desde los balances Siesa
  - 'homologacion' -> account_mapping (grupos CO<->ES)
  - 'terceros'     -> tercero_bridge (puente NIF<->NIT) [requiere homologacion]

Idempotente por (pais, codigo, periodo) / por grupo: hace upsert sencillo
borrando lo previo del mismo sistema antes de recargar.
"""
from __future__ import annotations

import hashlib
import re
import uuid
from collections import defaultdict
from datetime import datetime, timezone

import openpyxl
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from db.models import (
    AccountMapping,
    AccountPeriod,
    FileUpload,
    ImportBatch,
    PygMovimiento,
    SourceSystem,
    TerceroBridge,
)
from ingestion.colombia import parse_colombia_balance, parse_colombia_movimientos
from ingestion.espana import parse_espana_movimientos
from ingestion.homologacion import load_homologacion
from ingestion.terceros import load_puente_terceros

# Mapea nombre de hoja -> periodo lógico
_ES_SHEETS = {
    "AteneaEneroMvto": "2026-01",
    "AteneaFebrero-MarzoMvti": "2026-02-03",
}
_CO_SHEETS = {
    "Balance_Enero": "2026-01",
    "Balance_Febrero-Marzo": "2026-02-03",
}
_CO_MVTO_SHEETS = {
    "Mvto_Enero": "2026-01",
    "Mvto_Febrero-Marzo": "2026-02-03",
}


def _hash_file(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            h.update(chunk)
    return h.hexdigest()


def _sheets(path: str) -> list[str]:
    wb = openpyxl.load_workbook(path, read_only=True)
    try:
        return list(wb.sheetnames)
    finally:
        wb.close()


def _match_sheet(disponibles: list[str], mapa: dict[str, str]) -> dict[str, str]:
    """Empareja hojas reales con periodos, tolerando variaciones de nombre."""
    out = {}
    for real in disponibles:
        for patron, periodo in mapa.items():
            if real.replace(" ", "").lower() == patron.replace(" ", "").lower():
                out[real] = periodo
    # fallback: por palabra clave
    if not out:
        for real in disponibles:
            low = real.lower()
            if "enero" in low and "balance" not in low.replace("balance_enero", ""):
                pass
    return out


def ingest_espana(db: Session, path: str) -> dict:
    sis = _ensure_system(db, "DELSOL", "ES", "delsol_mayor")
    matched = _match_sheet(_sheets(path), _ES_SHEETS)
    if not matched:
        raise ValueError(f"No se reconocieron hojas de España. Hojas: {_sheets(path)}")
    # Borrado quirúrgico: solo los periodos presentes en este archivo (no todo el país).
    periodos = list(set(matched.values()))
    db.execute(delete(AccountPeriod).where(AccountPeriod.pais == "ES", AccountPeriod.periodo.in_(periodos)))
    db.execute(delete(PygMovimiento).where(PygMovimiento.pais == "ES", PygMovimiento.periodo.in_(periodos)))
    n = 0
    for sheet, periodo in matched.items():
        cuentas = parse_espana_movimientos(path, sheet)
        agg: dict[str, dict] = defaultdict(lambda: {"debe": 0.0, "haber": 0.0, "nombre": ""})
        for c in cuentas:
            a = agg[c.codigo]
            a["nombre"] = c.nombre
            for m in c.movimientos:
                a["debe"] += m.debe
                a["haber"] += m.haber
            # movimientos individuales PYG (clase 6 gasto / 7 ingreso)
            if c.codigo[:1] in ("6", "7"):
                for m in c.movimientos:
                    db.add(PygMovimiento(pais="ES", codigo=c.codigo, periodo=periodo, fecha=m.fecha,
                                         concepto=str(m.concepto)[:500], debe=round(m.debe, 2), haber=round(m.haber, 2)))
        for codigo, a in agg.items():
            db.add(AccountPeriod(
                pais="ES", codigo=codigo, nombre=a["nombre"][:255], periodo=periodo,
                debe=round(a["debe"], 2), haber=round(a["haber"], 2),
            ))
            n += 1
    _record_batch(db, sis.id, _hash_file(path), n)
    db.commit()
    return {"tipo": "espana", "periodos": sorted(set(matched.values())), "cuentas": n}


def ingest_colombia(db: Session, path: str) -> dict:
    sis = _ensure_system(db, "Siesa", "CO", "siesa_xlsx")
    matched = _match_sheet(_sheets(path), _CO_SHEETS)
    if not matched:
        raise ValueError(f"No se reconocieron hojas de Colombia. Hojas: {_sheets(path)}")
    matched_mvto = _match_sheet(_sheets(path), _CO_MVTO_SHEETS)
    # Borrado quirúrgico: solo los periodos presentes (balance + movimientos), no todo el país.
    periodos = list(set(matched.values()) | set(matched_mvto.values()))
    db.execute(delete(AccountPeriod).where(AccountPeriod.pais == "CO", AccountPeriod.periodo.in_(periodos)))
    db.execute(delete(PygMovimiento).where(PygMovimiento.pais == "CO", PygMovimiento.periodo.in_(periodos)))
    n = 0
    for sheet, periodo in matched.items():
        for c in parse_colombia_balance(path, sheet):
            # debe=debitos, haber=creditos (uniforme con la normalización del motor)
            db.add(AccountPeriod(
                pais="CO", codigo=c.codigo, nombre=c.nombre[:255], periodo=periodo,
                debe=round(c.debitos, 2), haber=round(c.creditos, 2),
            ))
            n += 1
    # movimientos individuales PYG (clase 4 ingreso / 5 gasto) desde hojas Mvto_*.
    # En Siesa las cuentas PYG NO traen 'Referencia' (no son filas de detalle), vienen
    # por tercero. Enero es arrastre (débito/crédito = 0); Feb-Marzo trae movimiento real.
    nmov = 0
    for sheet, periodo in matched_mvto.items():
        for m in parse_colombia_movimientos(path, sheet, solo_detalle=False):
            if m.cuenta[:1] not in ("4", "5") or not m.nit:
                continue
            if m.debito == 0 and m.credito == 0:
                continue  # sin movimiento del periodo (arrastre)
            concepto = (m.nombre_tercero or m.nombre_cuenta or "")
            if m.referencia:
                concepto = f"{concepto} · {m.referencia}".strip(" ·")
            db.add(PygMovimiento(pais="CO", codigo=m.cuenta, periodo=periodo, fecha=m.fecha,
                                 concepto=concepto[:500], debe=round(m.debito, 2), haber=round(m.credito, 2)))
            nmov += 1
    _record_batch(db, sis.id, _hash_file(path), n)
    db.commit()
    return {"tipo": "colombia", "periodos": sorted(set(matched.values())), "cuentas": n, "movimientos": nmov}


def ingest_homologacion(db: Session, path: str) -> dict:
    db.execute(delete(AccountMapping))
    grupos = load_homologacion(path)
    n = 0
    for g in grupos:
        # una fila por par CO×ES (o por cuenta suelta) para account_mapping
        pares = [(co, es) for co in (g.cuentas_co or [""]) for es in (g.cuentas_es or [""])]
        for co, es in pares:
            db.add(AccountMapping(
                cuenta_co_patron=co, cuenta_es=es, grupo_homologado=g.grupo,
                tipo_relacion=g.tipo_relacion, confianza="alta", activo=True,
            ))
            n += 1
    db.commit()
    return {"tipo": "homologacion", "grupos": len(grupos), "mappings": n}


def ingest_terceros(db: Session, path: str) -> dict:
    db.execute(delete(TerceroBridge))
    puente = load_puente_terceros(path)
    for t in puente:
        db.add(TerceroBridge(
            cuenta_es=t.cuenta_es, nombre_fiscal=t.nombre_fiscal[:255],
            nif_normalizado=t.nif_normalizado, tipo_nif=t.tipo_nif,
            nit_colombia=t.nit_colombia, tipo=t.tipo, activo=True,
        ))
    db.commit()
    return {"tipo": "terceros", "terceros": len(puente)}


def _ensure_system(db: Session, nombre: str, pais: str, fmt: str) -> SourceSystem:
    sis = db.scalar(select(SourceSystem).where(SourceSystem.nombre == nombre))
    if not sis:
        sis = SourceSystem(nombre=nombre, pais=pais, tipo_formato=fmt)
        db.add(sis)
        db.flush()
    return sis


def _record_batch(db: Session, sistema_id: int, file_hash: str, n: int) -> None:
    # Idempotente: re-subir el mismo archivo no debe romper por la constraint única.
    h = file_hash[:64]
    existe = db.scalar(select(ImportBatch).where(
        ImportBatch.sistema_id == sistema_id,
        ImportBatch.periodo_mes == "2026-Q1",
        ImportBatch.archivo_hash == h,
    ))
    if existe:
        return
    db.add(ImportBatch(sistema_id=sistema_id, periodo_mes="2026-Q1", archivo_hash=h, estado="cargado"))


def registrar_carga(db: Session, *, tipo: str, nombre_original: str, path: str,
                    resultado: dict, usuario_id: int | None) -> None:
    """Registra una carga en `file_upload` (historial/auditoría de ingesta).

    Marca como 'reemplazado' las cargas previas activas del mismo tipo+periodo.
    No almacena el binario, solo metadatos + hash sha256.
    """
    file_hash = _hash_file(path)[:64]
    periodos = resultado.get("periodos") or ([resultado["periodo"]] if resultado.get("periodo") else [])
    periodo = ",".join(periodos)
    registros = int(
        resultado.get("cuentas")
        or resultado.get("terceros")
        or resultado.get("mappings")
        or (resultado.get("ar_terceros", 0) + resultado.get("ap_terceros", 0))
        or 0
    )
    prev = db.scalars(select(FileUpload).where(
        FileUpload.tipo_archivo == tipo,
        FileUpload.periodo == periodo,
        FileUpload.estado == "cargado",
    )).all()
    for p in prev:
        p.estado = "reemplazado"
        p.fecha_actualizacion = datetime.now(timezone.utc)
    db.add(FileUpload(
        tipo_archivo=tipo, nombre_original=(nombre_original or "")[:255],
        nombre_interno=uuid.uuid4().hex, periodo=periodo, usuario_id=usuario_id,
        registros_insertados=registros, hash_archivo=file_hash, estado="cargado",
    ))
    db.commit()


INGESTORS = {
    "espana": ingest_espana,
    "colombia": ingest_colombia,
    "homologacion": ingest_homologacion,
    "terceros": ingest_terceros,
}


def detectar_tipo(path: str) -> str | None:
    """Heurística por nombres de hoja para auto-detectar el tipo de archivo."""
    sheets = [s.lower() for s in _sheets(path)]
    joined = " ".join(sheets)
    if any("mvto" in s or "delsol" in s or re.search(r"atenea.*balance", s) for s in sheets):
        return "espana"
    if any(s.startswith("balance_") or s.startswith("mvto_") for s in sheets):
        return "colombia"
    if "puente terceros" in joined:
        return "homologacion"
    if "clientes" in sheets and "proveedor" in sheets:
        return "terceros"
    return None
