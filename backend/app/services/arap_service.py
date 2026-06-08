"""Servicio del módulo AR/AP: ingesta a BD (resolviendo NIT vía puente) y motor
de conciliación por tercero.

Estados de conciliación:
  CONCILIADO    |dif| <= umbral
  DIFERENCIA    |dif| > umbral
  ERROR_CO      saldo negativo en 1305 (debería reclasificarse a 2805)
  PROVISIONAL_ES cuenta amarilla España (no cruza) -> pestaña aparte
  SIN_MATCH     el tercero existe en un solo lado
"""
from __future__ import annotations

from collections import defaultdict
from datetime import datetime

from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from app.config import get_settings
from db.models import ArApBalance, ArApMovimiento, TerceroBridge
from ingestion.arap import (
    parse_arap_colombia,
    parse_arap_colombia_movimientos,
    parse_arap_espana,
)

settings = get_settings()


def _sheets(path: str) -> list[str]:
    import openpyxl
    wb = openpyxl.load_workbook(path, read_only=True)
    try:
        return list(wb.sheetnames)
    finally:
        wb.close()


def _find(sheets: list[str], *keys: str) -> str | None:
    for s in sheets:
        low = s.lower().replace(" ", "")
        if all(k in low for k in keys):
            return s
    return None


def ingest_espana(db: Session, path: str) -> dict:
    sheets = _sheets(path)
    ar_sheet = _find(sheets, "cartera", "atenea") or _find(sheets, "430")
    ap_sheet = _find(sheets, "cxp", "atenea") or _find(sheets, "410")
    if not ar_sheet and not ap_sheet:
        raise ValueError(f"No se hallaron hojas AR/AP de España. Hojas: {sheets}")

    # mapa cuenta_es -> nit_colombia (puente)
    bridge = {b.cuenta_es: b.nit_colombia for b in db.scalars(select(TerceroBridge)).all() if b.cuenta_es}
    nombres = {b.cuenta_es: b.nombre_fiscal for b in db.scalars(select(TerceroBridge)).all() if b.cuenta_es}

    db.execute(delete(ArApBalance).where(ArApBalance.pais == "ES"))
    db.execute(delete(ArApMovimiento).where(ArApMovimiento.pais == "ES"))
    resumen = {}
    for sheet, tipo in [(ar_sheet, "AR"), (ap_sheet, "AP")]:
        if not sheet:
            continue
        terceros = parse_arap_espana(path, sheet)
        agg: dict[str, dict] = defaultdict(lambda: {"saldo": 0.0, "nombre": ""})
        for t in terceros:
            if t.es_provisional:
                db.add(ArApBalance(pais="ES", tipo=tipo, nit="", cuenta=t.cuenta_es,
                                   nombre=t.nombre[:255], saldo=round(t.saldo, 2), es_provisional=True))
                continue
            nit = bridge.get(t.cuenta_es, "")
            key = nit or f"ES:{t.cuenta_es}"
            a = agg[key]
            a["saldo"] = round(a["saldo"] + t.saldo, 2)
            a["nombre"] = nombres.get(t.cuenta_es) or t.nombre
            a["nit"] = nit
            a["cuenta"] = t.cuenta_es
            for m in (t.movimientos or []):
                db.add(ArApMovimiento(pais="ES", tipo=tipo, nit=nit, cuenta=t.cuenta_es,
                                      fecha=m.fecha, concepto=str(m.concepto)[:500],
                                      debe=round(m.debe, 2), haber=round(m.haber, 2), saldo=round(m.saldo, 2)))
        for key, a in agg.items():
            db.add(ArApBalance(pais="ES", tipo=tipo, nit=a.get("nit", ""), cuenta=a["cuenta"],
                               nombre=a["nombre"][:255], saldo=a["saldo"]))
        resumen[tipo] = len(terceros)
    db.commit()
    return {"tipo": "ar-ap/espana", "ar_terceros": resumen.get("AR", 0), "ap_terceros": resumen.get("AP", 0)}


def ingest_colombia(db: Session, path: str) -> dict:
    sheets = _sheets(path)
    ar_sheet = _find(sheets, "cartera", "neuron") or _find(sheets, "1305")
    ap_sheet = _find(sheets, "cxp", "neuron") or _find(sheets, "22")
    if not ar_sheet and not ap_sheet:
        raise ValueError(f"No se hallaron hojas AR/AP de Colombia. Hojas: {sheets}")

    db.execute(delete(ArApBalance).where(ArApBalance.pais == "CO"))
    db.execute(delete(ArApMovimiento).where(ArApMovimiento.pais == "CO"))
    resumen = {}
    for sheet, tipo in [(ar_sheet, "AR"), (ap_sheet, "AP")]:
        if not sheet:
            continue
        co = parse_arap_colombia(path, sheet)
        for t in co:
            if tipo == "AR":
                db.add(ArApBalance(pais="CO", tipo="AR", nit=t.nit, cuenta="1305/2805",
                                   nombre=t.nombre[:255], saldo=round(t.saldo_1305 + t.saldo_2805, 2),
                                   saldo_a=t.saldo_1305, saldo_b=t.saldo_2805,
                                   error_contab=t.error_contabilizacion))
            else:
                db.add(ArApBalance(pais="CO", tipo="AP", nit=t.nit, cuenta="22xx",
                                   nombre=t.nombre[:255], saldo=round(t.saldo_22xx, 2)))
        for nit, m in parse_arap_colombia_movimientos(path, sheet):
            db.add(ArApMovimiento(pais="CO", tipo=tipo, nit=nit, cuenta=m.cuenta,
                                  fecha=m.fecha, concepto=str(m.concepto)[:500],
                                  debe=round(m.debe, 2), haber=round(m.haber, 2), saldo=round(m.saldo, 2)))
        resumen[tipo] = len(co)
    db.commit()
    return {"tipo": "ar-ap/colombia", "ar_terceros": resumen.get("AR", 0), "ap_terceros": resumen.get("AP", 0)}


def _estado(co: float, es: float, hay_co: bool, hay_es: bool, error_co: bool, umbral: float):
    if error_co:
        return "ERROR_CO"
    if not (hay_co and hay_es):
        return "SIN_MATCH"
    return "CONCILIADO" if abs(round(co - es, 2)) <= umbral else "DIFERENCIA"


def _parse_fecha(s):
    if not s:
        return None
    try:
        return datetime.fromisoformat(str(s)[:19])
    except ValueError:
        return None


def _sumas_mov(db: Session, desde=None, hasta=None) -> dict:
    """{(pais,tipo,nit): (debe, haber)} de movimientos en el rango [desde,hasta]."""
    q = select(ArApMovimiento.pais, ArApMovimiento.tipo, ArApMovimiento.nit,
               func.coalesce(func.sum(ArApMovimiento.debe), 0),
               func.coalesce(func.sum(ArApMovimiento.haber), 0))
    d, h = _parse_fecha(desde), _parse_fecha(hasta)
    if d is not None:
        q = q.where(ArApMovimiento.fecha >= d)
    if h is not None:
        q = q.where(ArApMovimiento.fecha <= h)
    q = q.group_by(ArApMovimiento.pais, ArApMovimiento.tipo, ArApMovimiento.nit)
    out = {}
    for pais, tipo, nit, deb, hab in db.execute(q):
        out[(pais, tipo, nit)] = (float(deb), float(hab))
    return out


def reconciliacion(db: Session, tipo: str | None = None, desde=None, hasta=None) -> dict:
    umbral = settings.tolerancia_abs_cop
    sumas = _sumas_mov(db, desde, hasta)
    rows = db.scalars(select(ArApBalance).where(ArApBalance.es_provisional.is_(False))).all()
    # indexar por (tipo, nit)
    co_idx: dict[tuple, ArApBalance] = {}
    es_idx: dict[tuple, ArApBalance] = {}
    for r in rows:
        if not r.nit:
            es_idx[(r.tipo, f"ES:{r.cuenta}")] = r  # ES sin NIT resuelto
            continue
        (co_idx if r.pais == "CO" else es_idx)[(r.tipo, r.nit)] = r

    claves = set(co_idx) | set(es_idx)
    out = []
    for k in claves:
        tp, nit = k
        if tipo and tp != tipo:
            continue
        c = co_idx.get(k)
        e = es_idx.get(k)
        saldo_co = float(c.saldo) if c else 0.0
        saldo_es = float(e.saldo) if e else 0.0
        error_co = bool(c.error_contab) if c else False
        estado = _estado(saldo_co, saldo_es, c is not None, e is not None, error_co, umbral)
        nit_real = nit if not str(nit).startswith("ES:") else ""
        co_deb, co_hab = sumas.get(("CO", tp, nit_real), (0.0, 0.0)) if nit_real else (0.0, 0.0)
        es_deb, es_hab = sumas.get(("ES", tp, nit_real), (0.0, 0.0)) if nit_real else (0.0, 0.0)
        out.append({
            "tipo": tp, "categoria": "CLIENTE" if tp == "AR" else "PROVEEDOR",
            "nit": nit_real,
            "nombre": (c.nombre if c else None) or (e.nombre if e else ""),
            "saldo_co": round(saldo_co, 2), "saldo_es": round(saldo_es, 2),
            "saldo_1305": float(c.saldo_a) if c else None, "saldo_2805": float(c.saldo_b) if c else None,
            "debitos_mes": round(co_deb + es_deb, 2), "creditos_mes": round(co_hab + es_hab, 2),
            "diferencia": round(saldo_co - saldo_es, 2),
            "estado": estado, "error_contab": error_co,
        })
    out.sort(key=lambda x: abs(x["diferencia"]), reverse=True)

    def _tot(rows):
        return {
            "debitos": round(sum(x["debitos_mes"] for x in rows), 2),
            "creditos": round(sum(x["creditos_mes"] for x in rows), 2),
            "saldo_neto": round(sum(x["saldo_co"] - x["saldo_es"] for x in rows), 2),
        }
    clientes = [x for x in out if x["tipo"] == "AR"]
    proveedores = [x for x in out if x["tipo"] == "AP"]
    kpis = {
        "terceros": len(out),
        "conciliados": sum(1 for x in out if x["estado"] == "CONCILIADO"),
        "diferencias": sum(1 for x in out if x["estado"] == "DIFERENCIA"),
        "errores_co": sum(1 for x in out if x["estado"] == "ERROR_CO"),
        "sin_match": sum(1 for x in out if x["estado"] == "SIN_MATCH"),
        "sum_co": round(sum(x["saldo_co"] for x in out), 2),
        "sum_es": round(sum(x["saldo_es"] for x in out), 2),
        "sum_dif": round(sum(x["diferencia"] for x in out), 2),
    }
    totales = {"CLIENTES": _tot(clientes), "PROVEEDORES": _tot(proveedores), "TOTAL": _tot(out)}
    return {"filas": out, "kpis": kpis, "totales": totales}


def movimientos_tercero(db: Session, nit: str, desde=None, hasta=None) -> dict:
    """Movimientos CO y ES de un tercero, con resumen de conciliación y alertas."""
    q = select(ArApMovimiento).where(ArApMovimiento.nit == nit)
    d, h = _parse_fecha(desde), _parse_fecha(hasta)
    if d is not None:
        q = q.where(ArApMovimiento.fecha >= d)
    if h is not None:
        q = q.where(ArApMovimiento.fecha <= h)
    movs = db.scalars(q.order_by(ArApMovimiento.fecha)).all()

    def serial(m):
        return {"fecha": m.fecha.isoformat() if m.fecha else None, "cuenta": m.cuenta,
                "concepto": m.concepto, "debe": float(m.debe), "haber": float(m.haber), "saldo": float(m.saldo)}
    co = [serial(m) for m in movs if m.pais == "CO"]
    es = [serial(m) for m in movs if m.pais == "ES"]

    bal = db.scalars(select(ArApBalance).where(ArApBalance.nit == nit)).all()
    co_rows = [b for b in bal if b.pais == "CO"]
    # saldo neto CO = suma de saldos CO (AR: 1305+2805 ; AP: 22xx)
    saldo_co = round(sum(float(b.saldo) for b in co_rows), 2)
    saldo_1305 = round(sum(float(b.saldo_a) for b in co_rows), 2)   # solo AR aporta
    saldo_2805 = round(sum(float(b.saldo_b) for b in co_rows), 2)
    es_saldo = round(sum(float(b.saldo) for b in bal if b.pais == "ES"), 2)
    nombre = (co_rows[0].nombre if co_rows else None) or (bal[0].nombre if bal else "")

    alertas = []
    if any(b.error_contab for b in co_rows):
        alertas.append({"tipo": "error", "msg": "Saldo negativo detectado en cuenta 1305 — posible error de contabilización."})
    if saldo_2805 < 0:
        alertas.append({"tipo": "info", "msg": "Saldo a favor del cliente (2805) incluido en el neto de Colombia."})
    return {
        "nit": nit, "nombre": nombre,
        "movimientos_co": co, "movimientos_es": es,
        "resumen": {"saldo_1305": saldo_1305, "saldo_2805": saldo_2805, "saldo_co": saldo_co,
                    "saldo_es": es_saldo, "diferencia": round(saldo_co - es_saldo, 2)},
        "alertas": alertas,
    }


def excepciones(db: Session) -> list[dict]:
    return [r for r in reconciliacion(db)["filas"] if r["estado"] in ("DIFERENCIA", "ERROR_CO", "SIN_MATCH")]


def errores_contables(db: Session) -> list[dict]:
    rows = db.scalars(
        select(ArApBalance).where(ArApBalance.pais == "CO", ArApBalance.error_contab.is_(True))
    ).all()
    return [{"nit": r.nit, "nombre": r.nombre, "saldo_1305": float(r.saldo_a),
             "saldo_2805": float(r.saldo_b), "tipo": r.tipo} for r in rows]


def provisionales(db: Session) -> list[dict]:
    rows = db.scalars(select(ArApBalance).where(ArApBalance.es_provisional.is_(True))).all()
    return [{"cuenta_es": r.cuenta, "nombre": r.nombre, "saldo": float(r.saldo), "tipo": r.tipo} for r in rows]


def estado_datos(db: Session) -> dict:
    from sqlalchemy import func
    def n(pais, prov=False):
        return db.scalar(select(func.count()).select_from(ArApBalance).where(
            ArApBalance.pais == pais, ArApBalance.es_provisional.is_(prov))) or 0
    return {
        "espana_terceros": n("ES"),
        "espana_provisionales": db.scalar(select(func.count()).select_from(ArApBalance).where(
            ArApBalance.es_provisional.is_(True))) or 0,
        "colombia_terceros": n("CO"),
        "listo": bool(n("ES") and n("CO")),
    }
