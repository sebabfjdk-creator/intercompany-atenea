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
import uuid
from collections import defaultdict
from datetime import datetime, timezone

import openpyxl
from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from db.models import (
    AccountMapping,
    AccountPeriod,
    ArApBalance,
    ArApMovimiento,
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
    return out


# Meses (ES) para inferir el periodo desde el nombre de hoja del export mensual de Siesa.
_CO_MESES = {
    "ener": "01", "febr": "02", "marz": "03", "abr": "04", "may": "05", "juni": "06",
    "juli": "07", "agos": "08", "sept": "09", "octu": "10", "novi": "11", "dici": "12",
}


def _periodo_de_nombre(nombre: str, anio: str = "2026") -> str | None:
    low = nombre.lower()
    for k, mm in _CO_MESES.items():
        if k in low:
            return f"{anio}-{mm}"
    return None


def _detect_co_sheets(sheets: list[str]) -> tuple[dict[str, str], dict[str, str]]:
    """Devuelve (hojas_balance, hojas_movimiento) -> periodo, soportando tanto el
    formato consolidado fijo (Balance_Enero/Mvto_Enero…) como el export mensual de
    Siesa con nombres variables ('Consulta_ Mayor y balances ENERO', 'Rept Mov.
    Ctas. Aux'). El parser ya localiza la cabecera dinámicamente."""
    bal = _match_sheet(sheets, _CO_SHEETS)
    mov = _match_sheet(sheets, _CO_MVTO_SHEETS)
    if bal or mov:
        return bal, mov
    # Export mensual: detectar por palabras clave + inferir el mes del nombre.
    periodo = next((p for s in sheets if (p := _periodo_de_nombre(s))), None) or "2026-01"
    bal2, mov2 = {}, {}
    for s in sheets:
        low = s.lower()
        if "mov" in low or "aux" in low or "auxiliar" in low:
            mov2[s] = periodo
        elif "mayor" in low or "balance" in low or "consulta" in low or "saldos" in low:
            bal2[s] = periodo
    return bal2, mov2


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
    sheets = _sheets(path)
    matched, matched_mvto = _detect_co_sheets(sheets)
    if not matched and not matched_mvto:
        raise ValueError(f"No se reconocieron hojas de Colombia. Hojas: {sheets}")
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
                                 concepto=concepto[:500], nit=str(m.nit or "")[:40],
                                 debe=round(m.debito, 2), haber=round(m.credito, 2)))
            nmov += 1
    _record_batch(db, sis.id, _hash_file(path), n)
    db.commit()
    return {"tipo": "colombia", "periodos": sorted(set(matched.values())), "cuentas": n, "movimientos": nmov}


# Consolidación de terceros intercompany "grandes": fuerza estas cuentas a un único
# grupo (Ingresos/Gastos), quitándolas de cualquier otro grupo (evita doble conteo).
# Se aplica tras cargar la homologación, así que sobrevive a re-cargas del Excel.
# Terceros intercompany grandes: rubro propio (Ingresos/Gastos) filtrado por NIT.
# CO: las cuentas son COMPARTIDAS -> el motor separa por NIT (la cuenta se queda en
# su grupo original con el resto). ES: las cuentas son DEDICADAS al tercero -> se
# quitan de otros grupos y van completas al rubro intercompany.
_INTERCOMPANY = [
    {"grupo": "NET REAL SOLUTIONS - Ingresos", "tipo": "ingreso", "nit": "B12550877",
     "co": ["41553503", "42102005"], "es": ["700.0.0.101"]},
    {"grupo": "NET REAL SOLUTIONS - Gastos", "tipo": "gasto", "nit": "B12550877",
     "co": ["51351501", "51351503", "51352001", "515505", "515595", "51950505"],
     "es": ["602.0.0.101", "602.0.0.103", "629.0.0.100"]},
]


def _consolidar_intercompany(grupos: list) -> list:
    from ingestion.homologacion import GrupoHomologado
    ic_es = {c for ic in _INTERCOMPANY for c in ic["es"]}
    nombres_ic = {ic["grupo"] for ic in _INTERCOMPANY}
    out = []
    for g in grupos:
        if g.grupo in nombres_ic:
            continue  # se reconstruye abajo
        es = [c for c in g.cuentas_es if c not in ic_es]   # ES dedicado: quitar de otros grupos
        co = list(g.cuentas_co)                              # CO compartido: NO quitar (split por NIT)
        if co or es:
            out.append(GrupoHomologado(grupo=g.grupo, tipo=g.tipo, cuentas_co=co,
                                       cuentas_es=es, descripcion=g.descripcion))
    for ic in _INTERCOMPANY:
        out.append(GrupoHomologado(grupo=ic["grupo"], tipo=ic["tipo"],
                                   cuentas_co=list(ic["co"]), cuentas_es=list(ic["es"]),
                                   descripcion="intercompany"))
    return out


def ic_porcion_co(db: Session) -> tuple[dict, dict]:
    """Porción CO de los terceros intercompany por (periodo, codigo), desde
    pyg_movimiento filtrado por NIT. Devuelve (porcion, group_codes)."""
    from sqlalchemy import func as _func

    from db.models import PygMovimiento
    from domain.reconciliacion import valor_periodo
    code_nit = {c: ic["nit"] for ic in _INTERCOMPANY for c in ic["co"]}
    group_codes = {ic["grupo"]: set(ic["co"]) for ic in _INTERCOMPANY}
    if not code_nit:
        return {}, group_codes
    rows = db.execute(
        select(PygMovimiento.periodo, PygMovimiento.codigo, PygMovimiento.nit,
               _func.coalesce(_func.sum(PygMovimiento.debe), 0),
               _func.coalesce(_func.sum(PygMovimiento.haber), 0))
        .where(PygMovimiento.pais == "CO",
               PygMovimiento.codigo.in_(list(code_nit)),
               PygMovimiento.nit.in_(list(set(code_nit.values()))))
        .group_by(PygMovimiento.periodo, PygMovimiento.codigo, PygMovimiento.nit)
    ).all()
    porcion: dict[tuple, float] = {}
    for periodo, codigo, nit, sdeb, shaber in rows:
        if code_nit.get(codigo) == nit:
            porcion[(periodo, codigo)] = round(valor_periodo("CO", codigo, float(sdeb), float(shaber)), 2)
    return porcion, group_codes


def ingest_homologacion(db: Session, path: str) -> dict:
    db.execute(delete(AccountMapping))
    grupos = _consolidar_intercompany(load_homologacion(path))
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


def periodos_de(tipo: str, path: str) -> list[str]:
    """Periodos que cargaría un archivo, SIN escribir (para control de duplicados).
    Para homologacion/terceros/AR-AP no hay periodo -> [''] (dataset único)."""
    if tipo == "espana":
        return sorted(set(_match_sheet(_sheets(path), _ES_SHEETS).values()))
    if tipo == "colombia":
        s = _sheets(path)
        return sorted(set(_match_sheet(s, _CO_SHEETS).values()) | set(_match_sheet(s, _CO_MVTO_SHEETS).values()))
    return [""]


def periodos_en_conflicto(db: Session, tipo: str, periodos: list[str]) -> list[str]:
    """Periodos que ya tienen una carga activa ('cargado') del mismo tipo."""
    nuevos = set(periodos)
    activas = db.scalars(select(FileUpload).where(
        FileUpload.tipo_archivo == tipo, FileUpload.estado == "cargado")).all()
    return sorted({p for f in activas for p in f.periodo.split(",") if p in nuevos})


def eliminar_datos_de(db: Session, tipo: str, periodo: str) -> None:
    """Borra los registros contables asociados a una carga (para 🗑️ Eliminar).
    La conciliación se recalcula sola (motor en vivo)."""
    periodos = [p for p in periodo.split(",") if p]
    if tipo == "espana":
        db.execute(delete(AccountPeriod).where(AccountPeriod.pais == "ES", AccountPeriod.periodo.in_(periodos)))
        db.execute(delete(PygMovimiento).where(PygMovimiento.pais == "ES", PygMovimiento.periodo.in_(periodos)))
    elif tipo == "colombia":
        db.execute(delete(AccountPeriod).where(AccountPeriod.pais == "CO", AccountPeriod.periodo.in_(periodos)))
        db.execute(delete(PygMovimiento).where(PygMovimiento.pais == "CO", PygMovimiento.periodo.in_(periodos)))
    elif tipo == "arap_es":
        db.execute(delete(ArApBalance).where(ArApBalance.pais == "ES"))
        db.execute(delete(ArApMovimiento).where(ArApMovimiento.pais == "ES"))
    elif tipo == "arap_co":
        db.execute(delete(ArApBalance).where(ArApBalance.pais == "CO"))
        db.execute(delete(ArApMovimiento).where(ArApMovimiento.pais == "CO"))
    elif tipo == "homologacion":
        db.execute(delete(AccountMapping))
    elif tipo == "terceros":
        db.execute(delete(TerceroBridge))


def periodos_cargados(db: Session) -> list[dict]:
    """Periodos PYG actualmente en BD (para el panel 'Periodos cargados'),
    con conteo de cuentas y movimientos por (pais, periodo)."""
    cta = db.execute(select(AccountPeriod.pais, AccountPeriod.periodo, func.count())
                     .group_by(AccountPeriod.pais, AccountPeriod.periodo)).all()
    mov = {(p, per): n for p, per, n in db.execute(
        select(PygMovimiento.pais, PygMovimiento.periodo, func.count())
        .group_by(PygMovimiento.pais, PygMovimiento.periodo)).all()}
    out = [{"pais": p, "periodo": per, "cuentas": int(n), "movimientos": int(mov.get((p, per), 0))}
           for p, per, n in cta]
    out.sort(key=lambda x: (x["periodo"], x["pais"]))
    return out


def eliminar_periodo(db: Session, pais: str, periodo: str) -> dict:
    """Borra los datos PYG de un (pais, periodo) y marca como 'eliminado' las
    cargas del historial que lo cubran. NO hace commit (lo hace el router)."""
    nc = db.execute(delete(AccountPeriod).where(
        AccountPeriod.pais == pais, AccountPeriod.periodo == periodo)).rowcount
    nm = db.execute(delete(PygMovimiento).where(
        PygMovimiento.pais == pais, PygMovimiento.periodo == periodo)).rowcount
    tipo = "espana" if pais == "ES" else "colombia"
    for f in db.scalars(select(FileUpload).where(
            FileUpload.tipo_archivo == tipo, FileUpload.estado == "cargado")).all():
        if periodo in f.periodo.split(","):
            f.estado = "eliminado"
            f.fecha_actualizacion = datetime.now(timezone.utc)
    return {"cuentas": int(nc or 0), "movimientos": int(nm or 0)}


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
    """Heurística por nombres de hoja para auto-detectar el tipo de archivo.
    Orden importante: AR/AP (Cartera*/CXP*) antes que PYG, porque las hojas de
    cartera España también contienen 'atenea'. Colombia se distingue por el
    prefijo 'balance_'/'mvto_' (las hojas de España son 'Atenea…Mvto')."""
    sheets = [s.lower() for s in _sheets(path)]
    joined = " ".join(sheets)
    # 1) AR/AP (cartera/pasivos): hojas Cartera*/CXP*
    if any("cartera" in s or "cxp" in s for s in sheets):
        if any("neuron" in s for s in sheets):
            return "arap_co"
        if any("atenea" in s for s in sheets):
            return "arap_es"
    # 2) Homologación / terceros
    if "puente terceros" in joined:
        return "homologacion"
    if "clientes" in sheets and "proveedor" in sheets:
        return "terceros"
    # 3) PYG Colombia (Siesa): Balance_/Mvto_ o el export mensual (Consulta_ Mayor y
    #    balances… / Rept Mov. Ctas. Aux). Antes que España para no chocar con 'mvto'.
    if any(s.startswith("balance_") or s.startswith("mvto_") for s in sheets):
        return "colombia"
    if any(("mayor" in s and "balance" in s) or "ctas. aux" in s or "mov. ctas" in s for s in sheets):
        return "colombia"
    # 4) PYG España (Libro Mayor DELSOL): hojas Atenea…/DELSOL
    if any("delsol" in s or "atenea" in s for s in sheets):
        return "espana"
    return None
