"""Módulo Cartera 360° (Executive Receivables Center) sobre la cartera de
clientes España: cuenta 430 (clientes) y 431 (clientes dudoso cobro).

IMPORTANTE — honestidad del dato: el export DELSOL NO provee fecha de
vencimiento por factura, por lo que el 'aging' se calcula por ANTIGÜEDAD del
último movimiento contable (proxy), NO por días vencidos reales. No se inventan
vencimientos. Tampoco hay histórico mensual (un solo snapshot), así que no se
calcula evolución temporal.
"""
from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from db.models import ArApBalance, ArApMovimiento

_BUCKETS = ["0-30", "31-60", "61-90", "91-120", "120+", "Sin movimiento"]
_PROV_PCT = {"0-30": 0.0, "31-60": 0.05, "61-90": 0.15, "91-120": 0.35, "120+": 0.60, "Sin movimiento": 0.10}
_RIESGO = {"0-30": "bajo", "31-60": "medio", "61-90": "alto", "91-120": "critico", "120+": "critico", "Sin movimiento": "medio"}


def _bucket(dias: int | None) -> str:
    if dias is None:
        return "Sin movimiento"
    if dias <= 30:
        return "0-30"
    if dias <= 60:
        return "31-60"
    if dias <= 90:
        return "61-90"
    if dias <= 120:
        return "91-120"
    return "120+"


def _clientes(db: Session) -> tuple[list[dict], float]:
    rows = db.scalars(select(ArApBalance).where(
        ArApBalance.pais == "ES", ArApBalance.tipo == "AR")).all()
    provisional = round(sum(float(r.saldo) for r in rows if r.es_provisional), 2)
    activos = [r for r in rows if not r.es_provisional and round(float(r.saldo), 2) != 0]

    mv = db.execute(select(ArApMovimiento.nit, func.max(ArApMovimiento.fecha))
                    .where(ArApMovimiento.pais == "ES", ArApMovimiento.tipo == "AR")
                    .group_by(ArApMovimiento.nit)).all()
    last = {nit: f for nit, f in mv if f}
    hoy = datetime.now(timezone.utc)

    out = []
    for r in activos:
        f = last.get(r.nit)
        dias = (hoy - f.replace(tzinfo=timezone.utc)).days if f else None
        b = _bucket(dias)
        out.append({
            "nit": r.nit, "nombre": r.nombre or r.nit, "saldo": round(float(r.saldo), 2),
            "saldo_430": round(float(r.saldo_a), 2), "saldo_431": round(float(r.saldo_b), 2),
            "dias": dias, "antiguedad": b, "riesgo": _RIESGO[b],
        })
    out.sort(key=lambda x: x["saldo"], reverse=True)
    return out, provisional


def _analisis(total: float, clientes: list[dict], criticos: list[dict], top10: list[dict], dudoso: float) -> list[str]:
    a = [f"La cartera de clientes (430/431, España) asciende a ${total:,.0f} COP, repartida entre {len(clientes)} clientes con saldo."]
    if total and criticos:
        m = sum(c["saldo"] for c in criticos)
        a.append(f"El {100 * m / total:.0f}% (${m:,.0f}) está en antigüedad superior a 90 días, en {len(criticos)} clientes — requiere gestión prioritaria de cobro.")
    elif clientes:
        a.append("Ningún cliente supera los 90 días de antigüedad: la cartera se considera sana.")
    if dudoso > 0:
        a.append(f"Se reconocen ${dudoso:,.0f} como dudoso cobro (cuenta 431).")
    if top10:
        t = top10[0]
        if t["pct"] >= 20:
            a.append(f"Concentración elevada: {t['nombre']} representa el {t['pct']:.0f}% de toda la cartera — existe riesgo de concentración.")
        else:
            a.append(f"El mayor cliente ({t['nombre']}) representa el {t['pct']:.0f}% de la cartera: concentración moderada.")
    a.append("Nota metodológica: la antigüedad se mide desde el último movimiento contable; el origen DELSOL no provee fecha de vencimiento por factura, por lo que no se calculan días vencidos reales ni DSO.")
    return a


def dashboard(db: Session) -> dict:
    clientes, provisional = _clientes(db)
    total = round(sum(c["saldo"] for c in clientes), 2)
    dudoso = round(sum(c["saldo_431"] for c in clientes), 2)
    criticos = [c for c in clientes if c["antiguedad"] in ("91-120", "120+")]

    aging = []
    for b in _BUCKETS:
        s = round(sum(c["saldo"] for c in clientes if c["antiguedad"] == b), 2)
        n = sum(1 for c in clientes if c["antiguedad"] == b)
        if n:
            aging.append({"bucket": b, "saldo": s, "clientes": n})

    top10 = [{"nombre": c["nombre"], "nit": c["nit"], "saldo": c["saldo"],
              "pct": round(100 * c["saldo"] / total, 1) if total else 0.0} for c in clientes[:10]]
    provision = round(sum(c["saldo"] * _PROV_PCT.get(c["antiguedad"], 0) for c in clientes), 2)

    kpis = {
        "cartera_total": total,
        "clientes": len(clientes),
        "dudoso_431": dudoso,
        "provisional_es": provisional,
        "monto_critico_90": round(sum(c["saldo"] for c in criticos), 2),
        "clientes_riesgo": len(criticos),
        "provision_recomendada": provision,
        "concentracion_top1": top10[0]["pct"] if top10 else 0.0,
    }
    return {
        "kpis": kpis, "aging": aging, "top10": top10, "clientes": clientes,
        "analisis": _analisis(total, clientes, criticos, top10, dudoso),
        "nota": "Aging por ANTIGÜEDAD del último movimiento contable (el origen no provee fecha de vencimiento).",
    }
