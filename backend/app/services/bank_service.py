"""Servicio del módulo Conciliación Bancaria: ingesta de los dos insumos,
motor de cruce persistido y construcción del tablero de 3 bloques.

Identidad de conciliación (la que cuadra, signos correctos):
  saldo_banco = saldo_libros − Σ(partidas solo en libros) + Σ(partidas solo en banco)
La diferencia final = saldo_contable_inicial − saldo_banco_inicial (0 si ambos cuadran).
"""
from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from db.models import BankAccount, BankMovement, BankReconPeriod
from ingestion.bancos import (
    MovBanco,
    conciliar,
    mes_dominante,
    parse_banco_extracto,
    parse_bancos_contable,
)


def _account(db: Session, numero: str | None = None, sistema: str = "ES") -> BankAccount:
    acc = db.scalars(select(BankAccount)).first()
    if not acc:
        acc = BankAccount(nombre="Banco principal", numero_cuenta=numero or "—",
                          cuenta_contable="572", sistema=sistema)
        db.add(acc)
        db.flush()
    elif numero and acc.numero_cuenta in ("", "—"):
        acc.numero_cuenta = numero
    return acc


def _period(db: Session, account_id: int, mes: str) -> BankReconPeriod:
    p = db.scalar(select(BankReconPeriod).where(
        BankReconPeriod.bank_account_id == account_id, BankReconPeriod.mes == mes))
    if not p:
        p = BankReconPeriod(bank_account_id=account_id, mes=mes)
        db.add(p)
        db.flush()
    return p


def _rematch(db: Session, period_id: int) -> None:
    cont = db.scalars(select(BankMovement).where(
        BankMovement.period_id == period_id, BankMovement.origen == "contable").order_by(BankMovement.id)).all()
    ext = db.scalars(select(BankMovement).where(
        BankMovement.period_id == period_id, BankMovement.origen == "extracto").order_by(BankMovement.id)).all()
    cm = [MovBanco(fecha=m.fecha, monto=round(float(m.monto_firmado), 2), concepto=m.concepto, documento=m.documento) for m in cont]
    em = [MovBanco(fecha=m.fecha, monto=round(float(m.monto_firmado), 2), concepto=m.concepto) for m in ext]
    pares, solo_l, solo_b = conciliar(cm, em)
    for m in (*cont, *ext):
        m.estado = ""; m.match_id = None; m.match_tipo = ""
    for i, j, tipo in pares:
        c, e = cont[i], ext[j]
        c.estado = e.estado = "cruzado"
        c.match_tipo = e.match_tipo = tipo
        c.match_id, e.match_id = e.id, c.id
    for i in solo_l:
        cont[i].estado = "solo_libros"
    for j in solo_b:
        ext[j].estado = "solo_banco"


def ingest(db: Session, origen: str, path: str, usuario_id=None) -> dict:
    """origen: 'contable' | 'extracto'. Reemplaza los movimientos de ese lado en
    el periodo detectado y re-ejecuta el cruce."""
    if origen == "contable":
        movs = parse_bancos_contable(path)
        numero = None
    else:
        movs = parse_banco_extracto(path)
        numero = next((m.numero_cuenta for m in movs if m.numero_cuenta), None)
    if not movs:
        raise ValueError("No se reconocieron movimientos en el archivo")
    mes = mes_dominante(movs)
    if not mes:
        raise ValueError("No se pudo determinar el mes (fechas inválidas)")

    acc = _account(db, numero)
    period = _period(db, acc.id, mes)
    db.execute(delete(BankMovement).where(
        BankMovement.period_id == period.id, BankMovement.origen == origen))
    for m in movs:
        db.add(BankMovement(period_id=period.id, origen=origen, fecha=m.fecha,
                            concepto=m.concepto, documento=m.documento,
                            monto_firmado=round(m.monto, 2), codigo_banco=m.codigo))
    db.flush()
    _rematch(db, period.id)
    db.commit()
    return {"origen": origen, "mes": mes, "movimientos": len(movs), "cuenta": acc.numero_cuenta}


def set_saldos(db: Session, mes: str, saldo_contable: float, saldo_banco: float) -> dict:
    acc = _account(db)
    p = _period(db, acc.id, mes)
    p.saldo_contable_inicial = round(saldo_contable, 2)
    p.saldo_banco_inicial = round(saldo_banco, 2)
    db.commit()
    return {"ok": True, "mes": mes}


def cerrar(db: Session, mes: str, usuario_id=None) -> dict:
    acc = _account(db)
    p = _period(db, acc.id, mes)
    p.estado = "cerrada"
    p.fecha_cierre = datetime.now(timezone.utc)
    p.usuario_id = usuario_id
    db.commit()
    return {"ok": True, "mes": mes, "estado": "cerrada"}


def periodos(db: Session) -> list[dict]:
    acc = db.scalars(select(BankAccount)).first()
    if not acc:
        return []
    rows = db.scalars(select(BankReconPeriod).where(
        BankReconPeriod.bank_account_id == acc.id).order_by(BankReconPeriod.mes.desc())).all()
    return [{"mes": p.mes, "estado": p.estado, "cuenta": acc.numero_cuenta} for p in rows]


def _serial(m: BankMovement) -> dict:
    return {"id": m.id, "fecha": m.fecha.date().isoformat() if m.fecha else None,
            "concepto": m.concepto, "documento": m.documento, "codigo": m.codigo_banco,
            "monto": round(float(m.monto_firmado), 2), "match_tipo": m.match_tipo}


def conciliacion(db: Session, mes: str | None = None) -> dict:
    acc = db.scalars(select(BankAccount)).first()
    if not acc:
        return {"vacio": True}
    p = (db.scalar(select(BankReconPeriod).where(BankReconPeriod.bank_account_id == acc.id, BankReconPeriod.mes == mes))
         if mes else
         db.scalars(select(BankReconPeriod).where(BankReconPeriod.bank_account_id == acc.id).order_by(BankReconPeriod.mes.desc())).first())
    if not p:
        return {"vacio": True}

    movs = db.scalars(select(BankMovement).where(BankMovement.period_id == p.id)).all()
    cont = [m for m in movs if m.origen == "contable"]
    ext = [m for m in movs if m.origen == "extracto"]
    sc_ini = round(float(p.saldo_contable_inicial), 2)
    sb_ini = round(float(p.saldo_banco_inicial), 2)

    def pos(xs):
        return round(sum(float(m.monto_firmado) for m in xs if float(m.monto_firmado) > 0), 2)

    def neg(xs):
        return round(sum(-float(m.monto_firmado) for m in xs if float(m.monto_firmado) < 0), 2)

    deb, cre = pos(cont), neg(cont)
    ing, egr = pos(ext), neg(ext)
    saldo_cont = round(sc_ini + deb - cre, 2)
    saldo_banco = round(sb_ini + ing - egr, 2)

    solo_libros = [m for m in cont if m.estado == "solo_libros"]
    solo_banco = [m for m in ext if m.estado == "solo_banco"]
    ab_sl, ca_sl = pos(solo_libros), neg(solo_libros)
    ing_sb, egr_sb = pos(solo_banco), neg(solo_banco)
    saldo_conciliado = round(saldo_cont + ing_sb - egr_sb - ab_sl + ca_sl, 2)
    diferencia = round(saldo_conciliado - saldo_banco, 2)

    # conciliados (pares contable ↔ extracto)
    ext_by_id = {m.id: m for m in ext}
    conciliados = []
    for c in cont:
        if c.estado == "cruzado" and c.match_id in ext_by_id:
            e = ext_by_id[c.match_id]
            conciliados.append({
                "fecha_c": c.fecha.date().isoformat() if c.fecha else None, "concepto_c": c.concepto,
                "documento": c.documento, "monto": round(float(c.monto_firmado), 2),
                "fecha_e": e.fecha.date().isoformat() if e.fecha else None, "descripcion_e": e.concepto,
                "match_tipo": c.match_tipo,
            })

    return {
        "vacio": False, "mes": p.mes, "cuenta": acc.numero_cuenta, "estado": p.estado,
        "saldos_iniciales": {"contable": sc_ini, "banco": sb_ini},
        "bloque_contable": {"inicial": sc_ini, "debito": deb, "credito": cre, "final": saldo_cont,
                            "n_cargos": sum(1 for m in cont if float(m.monto_firmado) > 0),
                            "n_abonos": sum(1 for m in cont if float(m.monto_firmado) < 0)},
        "bloque_banco": {"inicial": sb_ini, "ingresos": ing, "egresos": egr, "final": saldo_banco},
        "bloque_conciliar": {
            "saldo_libros": saldo_cont, "ing_no_libros": ing_sb, "egr_no_libros": egr_sb,
            "abonos_no_banco": ab_sl, "cargos_no_banco": ca_sl,
            "saldo_bancos": saldo_conciliado, "diferencia": diferencia,
        },
        "conciliados": conciliados,
        "solo_libros": [_serial(m) for m in solo_libros],
        "solo_banco": [_serial(m) for m in solo_banco],
        "kpis": {"contable": len(cont), "extracto": len(ext), "conciliados": len(conciliados),
                 "solo_libros": len(solo_libros), "solo_banco": len(solo_banco),
                 "exactos": sum(1 for c in conciliados if c["match_tipo"] == "exacto")},
    }
