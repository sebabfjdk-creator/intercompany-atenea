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
from datetime import datetime, timezone

from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from app.config import get_settings
from db.models import ArApBalance, ArApMovimiento, TerceroBridge
from ingestion.arap import (
    normalizar_doc,
    parse_arap_colombia,
    parse_arap_colombia_movimientos,
    parse_arap_espana,
    tipo_documento,
)
from ingestion.utils import limpiar_concepto

settings = get_settings()

# Formas legales a ignorar al normalizar razones sociales para el cruce por nombre
_LEGAL = {"SAS", "SA", "SLU", "SL", "LTDA", "LTD", "ESP", "EU", "INC", "LLC", "CIA", "SUCURSAL"}


def _norm_nombre(nombre: str) -> str:
    """Razón social normalizada para cruce CO<->ES: sin acentos/puntuación,
    sin formas legales (SAS/SLU/SL/LTDA…) ni letras sueltas."""
    base = limpiar_concepto(nombre)  # MAYÚSCULAS, sin acentos ni signos
    toks = [t for t in base.split() if len(t) > 1 and t not in _LEGAL]
    norm = " ".join(toks).strip()
    return norm if len(norm) >= 5 else ""  # evita matches por nombres demasiado cortos


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
                                      documento=str(m.documento)[:60], tipo_documento=tipo_documento(m.documento),
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
                                   nombre=t.nombre[:255], saldo=t.saldo_cliente,
                                   saldo_a=t.saldo_1305, saldo_b=t.saldo_2805,
                                   error_contab=t.error_contabilizacion))
            else:
                # Proveedor CO = (220501+221001+230501+23351001) - 13300501 (anticipos)
                db.add(ArApBalance(pais="CO", tipo="AP", nit=t.nit, cuenta="22xx/23xx-1330",
                                   nombre=t.nombre[:255], saldo=t.saldo_proveedor,
                                   saldo_a=t.saldo_prov, saldo_b=-t.saldo_anticipo_prov))
        for nit, m in parse_arap_colombia_movimientos(path, sheet):
            db.add(ArApMovimiento(pais="CO", tipo=tipo, nit=nit, cuenta=m.cuenta,
                                  fecha=m.fecha, concepto=str(m.concepto)[:500],
                                  documento=str(m.documento)[:60], tipo_documento=tipo_documento(m.documento),
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
    from app.services import config_service
    umbral, _ = config_service.get_tolerancia(db)
    sumas = _sumas_mov(db, desde, hasta)
    rows = db.scalars(select(ArApBalance).where(ArApBalance.es_provisional.is_(False))).all()

    co_rows = [r for r in rows if r.pais == "CO"]
    es_rows = [r for r in rows if r.pais == "ES"]
    co_by_nit = {(r.tipo, r.nit): r for r in co_rows if r.nit}
    co_by_nombre = {(r.tipo, _norm_nombre(r.nombre)): r for r in co_rows if r.nombre}
    co_usados: set[int] = set()

    def fila(c, e, tp, matched_por):
        saldo_co = float(c.saldo) if c else 0.0
        saldo_es = float(e.saldo) if e else 0.0
        error_co = bool(c.error_contab) if c else False
        estado = _estado(saldo_co, saldo_es, c is not None, e is not None, error_co, umbral)
        nit_real = (c.nit if c else "") or (e.nit if e else "")
        co_deb, co_hab = sumas.get(("CO", tp, nit_real), (0.0, 0.0)) if nit_real else (0.0, 0.0)
        es_deb, es_hab = sumas.get(("ES", tp, nit_real), (0.0, 0.0)) if nit_real else (0.0, 0.0)
        return {
            "tipo": tp, "categoria": "CLIENTE" if tp == "AR" else "PROVEEDOR",
            "nit": nit_real, "nombre": (c.nombre if c else None) or (e.nombre if e else ""),
            "saldo_co": round(saldo_co, 2), "saldo_es": round(saldo_es, 2),
            "saldo_1305": float(c.saldo_a) if c else None, "saldo_2805": float(c.saldo_b) if c else None,
            "debitos_mes": round(co_deb + es_deb, 2), "creditos_mes": round(co_hab + es_hab, 2),
            "diferencia": round(saldo_co - saldo_es, 2),
            "estado": estado, "error_contab": error_co, "matched_por": matched_por,
        }

    out = []
    for e in es_rows:
        if tipo and e.tipo != tipo:
            continue
        c = co_by_nit.get((e.tipo, e.nit)) if e.nit else None
        matched = "nit" if c else None
        if c is None:  # fallback: cruce por nombre (entidades ES con NIF de letra, sin NIT CO)
            c = co_by_nombre.get((e.tipo, _norm_nombre(e.nombre)))
            matched = "nombre" if c else None
        if c is not None:
            co_usados.add(id(c))
        out.append(fila(c, e, e.tipo, matched))
    # CO sin contraparte
    for c in co_rows:
        if tipo and c.tipo != tipo:
            continue
        if id(c) in co_usados:
            continue
        out.append(fila(c, None, c.tipo, None))
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


def _antiguedad_bucket(dias: int | None) -> str:
    if dias is None:
        return "—"
    if dias <= 30:
        return "0-30 días"
    if dias <= 60:
        return "31-60 días"
    if dias <= 90:
        return "61-90 días"
    return "Más de 90 días"


def tercero_360(db: Session, nit: str) -> dict:
    """Vista 360 de un tercero: resumen ejecutivo, movimientos CO/ES con documento,
    línea de tiempo, análisis automático y matching documental (trazabilidad)."""
    from app.services import config_service
    from db.models import ArApMovimiento
    umbral, _ = config_service.get_tolerancia(db)

    bal = db.scalars(select(ArApBalance).where(ArApBalance.nit == nit)).all()
    co_rows = [b for b in bal if b.pais == "CO"]
    saldo_co = round(sum(float(b.saldo) for b in co_rows), 2)
    saldo_es = round(sum(float(b.saldo) for b in bal if b.pais == "ES"), 2)
    diferencia = round(saldo_co - saldo_es, 2)
    nombre = (co_rows[0].nombre if co_rows else None) or (bal[0].nombre if bal else "")

    movs = db.scalars(select(ArApMovimiento).where(ArApMovimiento.nit == nit).order_by(ArApMovimiento.fecha)).all()

    def serial(m):
        return {
            "fecha": m.fecha.isoformat() if m.fecha else None,
            "periodo": (m.fecha.strftime("%Y-%m") if m.fecha else m.periodo if hasattr(m, "periodo") else ""),
            "cuenta": m.cuenta, "documento": m.documento, "tipo_documento": m.tipo_documento,
            "concepto": m.concepto, "debe": float(m.debe), "haber": float(m.haber), "saldo": float(m.saldo),
        }
    mov_co = [serial(m) for m in movs if m.pais == "CO"]
    mov_es = [serial(m) for m in movs if m.pais == "ES"]

    fechas = [m.fecha for m in movs if m.fecha]
    hoy = datetime.now(timezone.utc)
    ult = max(fechas) if fechas else None
    prim = min(fechas) if fechas else None
    dias_ult = (hoy - ult.replace(tzinfo=timezone.utc)).days if ult else None
    conciliado = abs(diferencia) <= umbral
    error_co = any(b.error_contab for b in co_rows)
    if conciliado:
        estado = "Conciliado"
    elif error_co:
        estado = "Pendiente de revisión"
    elif dias_ult is not None and dias_ult <= 60:
        estado = "Diferencia temporal"
    else:
        estado = "Diferencia permanente"

    # línea de tiempo (CO + ES por fecha)
    timeline = []
    for m in movs:
        if not m.fecha:
            continue
        pais_lbl = "Colombia" if m.pais == "CO" else "España"
        valor = round(float(m.debe) - float(m.haber), 2)
        evento = f"{m.tipo_documento or 'Movimiento'} registrado en {pais_lbl}"
        timeline.append({"fecha": m.fecha.isoformat(), "pais": m.pais, "evento": evento,
                         "documento": m.documento, "valor": valor})
    timeline.sort(key=lambda x: x["fecha"])

    # análisis automático (reglas)
    analisis = []
    if conciliado:
        analisis.append("Conciliado: los saldos de Colombia y España coinciden dentro de la tolerancia.")
    else:
        if error_co:
            analisis.append("Posible error de contabilización: saldo negativo en cuenta 1305 (revisar reclasificación a 2805).")
        if saldo_es == 0 and saldo_co != 0:
            analisis.append("La diferencia está abierta en Colombia y no tiene contraparte en España (factura/provisión solo en Colombia o pendiente de registro en España).")
        elif saldo_co == 0 and saldo_es != 0:
            analisis.append("La diferencia está abierta en España sin contraparte en Colombia.")
        elif (saldo_co > 0) != (saldo_es > 0):
            analisis.append("Saldos con signos opuestos: posible error de imputación o nota crédito registrada en un solo país.")
        else:
            analisis.append("Diferencia entre ambos saldos: revisar documentos sin contraparte.")
        pagos_es = any(m.pais == "ES" and (m.tipo_documento or "").lower().startswith(("recibo", "pago")) for m in movs)
        pagos_co = any(m.pais == "CO" and (m.tipo_documento or "").lower().startswith(("recibo", "pago")) for m in movs)
        if pagos_es and not pagos_co:
            analisis.append("Se registró un pago en España pero la operación sigue abierta en Colombia (diferencia temporal por timing).")
        if pagos_co and not pagos_es:
            analisis.append("Se registró un pago en Colombia pero la operación sigue abierta en España (diferencia temporal por timing).")

    return {
        "nit": nit, "nombre": nombre,
        "resumen": {
            "saldo_co": saldo_co, "saldo_es": saldo_es, "diferencia": diferencia,
            "estado": estado, "antiguedad": _antiguedad_bucket(dias_ult), "dias_ultimo_mov": dias_ult,
            "mes_origen": prim.strftime("%Y-%m") if prim else None,
            "ultimo_movimiento": ult.isoformat() if ult else None,
            "ultima_conciliacion": None,
        },
        "movimientos_co": mov_co, "movimientos_es": mov_es,
        "timeline": timeline,
        "analisis": analisis,
        "matching": matching_documental(mov_co, mov_es),
    }


def matching_documental(mov_co: list[dict], mov_es: list[dict]) -> list[dict]:
    """Cruza documentos CO<->ES por nº de referencia normalizado + valor + (cercanía).
    Confianza: 95 (nº doc + valor), 80 (nº doc), 60 (solo valor)."""
    def absval(m):
        return round(abs(m["debe"] - m["haber"]), 2)
    es_por_doc: dict[str, list[dict]] = defaultdict(list)
    for e in mov_es:
        es_por_doc[normalizar_doc(e["documento"])].append(e)
    usados = set()
    out = []
    for c in mov_co:
        dc = normalizar_doc(c["documento"])
        cand = es_por_doc.get(dc, []) if dc else []
        match, conf = None, 0
        for e in cand:
            if id(e) in usados:
                continue
            conf = 95 if absval(e) == absval(c) and absval(c) > 0 else 80
            match = e
            break
        if not match and absval(c) > 0:  # fallback por valor exacto
            for e in mov_es:
                if id(e) in usados:
                    continue
                if absval(e) == absval(c):
                    match, conf = e, 60
                    break
        if match:
            usados.add(id(match))
            out.append({
                "co_documento": c["documento"], "co_valor": absval(c), "co_fecha": c["fecha"],
                "es_documento": match["documento"], "es_valor": absval(match), "es_fecha": match["fecha"],
                "confianza": conf,
            })
    return out


def kpis_arap(db: Session) -> dict:
    """KPIs ejecutivos AR/AP: diferencias abiertas/conciliadas, >90 días, top terceros y cuentas."""
    from db.models import ArApMovimiento
    rec = reconciliacion(db)
    filas = rec["filas"]
    abiertas = [f for f in filas if f["estado"] != "CONCILIADO"]
    conciliadas = [f for f in filas if f["estado"] == "CONCILIADO"]

    rows = db.execute(select(ArApMovimiento.nit, func.max(ArApMovimiento.fecha)).group_by(ArApMovimiento.nit)).all()
    last = {nit: f for nit, f in rows if f}
    hoy = datetime.now(timezone.utc)

    def dias(nit):
        f = last.get(nit)
        return (hoy - f.replace(tzinfo=timezone.utc)).days if f else None

    mayores90 = [f for f in abiertas if f["nit"] and (dias(f["nit"]) is None or dias(f["nit"]) > 90)]
    top_terceros = sorted(filas, key=lambda x: abs(x["diferencia"]), reverse=True)[:20]

    cta: dict[str, float] = defaultdict(float)
    for b in db.scalars(select(ArApBalance).where(ArApBalance.es_provisional.is_(False))).all():
        if b.cuenta:
            cta[b.cuenta] += abs(float(b.saldo))
    top_cuentas = sorted([{"cuenta": k, "monto": round(v, 2)} for k, v in cta.items()],
                         key=lambda x: x["monto"], reverse=True)[:10]
    return {
        "diferencias_abiertas": len(abiertas),
        "diferencias_conciliadas": len(conciliadas),
        "mayores_90_dias": len(mayores90),
        "monto_abierto": round(sum(abs(f["diferencia"]) for f in abiertas), 2),
        "top_terceros": [{"nit": f["nit"], "nombre": f["nombre"], "diferencia": f["diferencia"],
                          "estado": f["estado"], "dias": dias(f["nit"])} for f in top_terceros],
        "top_cuentas": top_cuentas,
    }


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
