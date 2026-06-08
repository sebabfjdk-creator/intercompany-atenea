"""Consultas de negocio: construyen las respuestas de los tableros desde la BD."""
from __future__ import annotations

from collections import defaultdict

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.services import config_service
from db.models import AccountMapping, AccountPeriod, AuditLog, TerceroBridge
from domain.reconciliacion import causa_sugerida, cruzar_pyg_periodos

settings = get_settings()


def _resultados(db: Session):
    grupos = config_service.grupos_homologados(db)
    abs_cop, pct = config_service.get_tolerancia(db)
    filas = db.scalars(select(AccountPeriod)).all()
    return cruzar_pyg_periodos(grupos, filas, abs_cop, pct)


def comparativa(db: Session) -> dict:
    res = _resultados(db)
    periodos = sorted({r.periodo for r in res})
    filas: dict[str, dict] = {}
    for r in res:
        f = filas.setdefault(r.grupo, {
            "grupo": r.grupo, "tipo": r.tipo, "celdas": {},
            "total_co": 0.0, "total_es": 0.0, "total_dif": 0.0,
        })
        f["celdas"][r.periodo] = {
            "co": r.total_co, "es": r.total_es, "dif": r.diferencia,
            "pct": r.pct_dif, "estado": r.estado, "causa": causa_sugerida(r),
        }
        f["total_co"] = round(f["total_co"] + r.total_co, 2)
        f["total_es"] = round(f["total_es"] + r.total_es, 2)
        f["total_dif"] = round(f["total_dif"] + r.diferencia, 2)

    filas_list = sorted(filas.values(), key=lambda x: (x["tipo"], x["grupo"]))
    conc = sum(1 for r in res if r.estado == "conciliado")
    return {
        "periodos": periodos,
        "filas": filas_list,
        "kpis": {
            "grupos": len(filas_list),
            "cruces": len(res),
            "conciliados": conc,
            "excepciones": len(res) - conc,
            "dif_total_abs": round(sum(abs(r.diferencia) for r in res), 2),
        },
    }


def resumen(db: Session) -> dict:
    comp = comparativa(db)
    por_tipo: dict[str, dict] = defaultdict(lambda: {"co": 0.0, "es": 0.0, "dif": 0.0, "grupos": 0})
    for f in comp["filas"]:
        t = por_tipo[f["tipo"]]
        t["co"] = round(t["co"] + f["total_co"], 2)
        t["es"] = round(t["es"] + f["total_es"], 2)
        t["dif"] = round(t["dif"] + f["total_dif"], 2)
        t["grupos"] += 1
    return {
        "rubros": [{"tipo": k, **v} for k, v in por_tipo.items()],
        "kpis": comp["kpis"],
    }


def excepciones(db: Session) -> list[dict]:
    res = _resultados(db)
    out = []
    for r in res:
        if r.estado == "excepcion":
            out.append({
                "grupo": r.grupo, "tipo": r.tipo, "periodo": r.periodo,
                "total_co": r.total_co, "total_es": r.total_es,
                "diferencia": r.diferencia, "pct": r.pct_dif,
                "causa": causa_sugerida(r), "estado": r.estado,
            })
    out.sort(key=lambda x: abs(x["diferencia"]), reverse=True)
    return out


def terceros(db: Session) -> dict:
    rows = db.scalars(select(TerceroBridge).where(TerceroBridge.activo.is_(True))).all()
    items = [{
        "cuenta_es": t.cuenta_es, "nombre_fiscal": t.nombre_fiscal,
        "nif_normalizado": t.nif_normalizado, "nit_colombia": t.nit_colombia,
        "tipo": t.tipo,
    } for t in rows]
    return {
        "items": items,
        "kpis": {
            "total": len(items),
            "clientes": sum(1 for i in items if i["tipo"].lower().startswith("cliente")),
            "proveedores": sum(1 for i in items if i["tipo"].lower().startswith("proveedor")),
        },
    }


def homologacion(db: Session) -> dict:
    return config_service.get_homologacion(db)


def movimientos_cuenta(db: Session, pais: str, cuenta: str, periodo: str | None = None) -> dict:
    """Transacciones individuales de una cuenta (trazabilidad Grupo→Cuenta→Transacción).
    Match por prefijo: cubre cuentas jerárquicas CO (510570 -> 51057001) y wildcard ES."""
    from db.models import PygMovimiento
    pref = cuenta[:-1] if (cuenta and cuenta[-1] in ("x", "X", "*")) else cuenta
    q = select(PygMovimiento).where(PygMovimiento.pais == pais, PygMovimiento.codigo.startswith(pref))
    if periodo:
        q = q.where(PygMovimiento.periodo == periodo)
    movs = db.scalars(q.order_by(PygMovimiento.fecha)).all()
    items = [{
        "cuenta": m.codigo, "periodo": m.periodo,
        "fecha": m.fecha.isoformat() if m.fecha else None,
        "concepto": m.concepto, "debe": float(m.debe), "haber": float(m.haber),
    } for m in movs]
    return {
        "pais": pais, "cuenta": cuenta, "periodo": periodo, "items": items,
        "total_debe": round(sum(i["debe"] for i in items), 2),
        "total_haber": round(sum(i["haber"] for i in items), 2),
    }


def detalle_grupo(db: Session, grupo: str) -> dict:
    """Cuentas CO y ES que componen un grupo, con su valor por periodo (drill-down)."""
    from domain.reconciliacion import valor_periodo

    g = next((x for x in config_service.grupos_homologados(db) if x.grupo == grupo), None)
    if g is None:
        return {"grupo": grupo, "periodos": [], "colombia": [], "espana": [], "encontrado": False}

    filas = db.scalars(select(AccountPeriod)).all()
    periodos = sorted({f.periodo for f in filas})
    # índice pais -> codigo -> {nombre, periodo: valor}
    idx: dict[str, dict[str, dict]] = {"CO": {}, "ES": {}}
    for f in filas:
        d = idx[f.pais].setdefault(f.codigo, {"nombre": f.nombre, "vals": {}})
        d["vals"][f.periodo] = valor_periodo(f.pais, f.codigo, float(f.debe), float(f.haber))
        if f.nombre:
            d["nombre"] = f.nombre

    def expandir(pais: str, codes: list[str]) -> list[dict]:
        out = []
        for code in codes:
            if code and code[-1] in ("x", "X", "*"):
                pref = code[:-1]
                matched = sorted(k for k in idx[pais] if k.startswith(pref))
            else:
                matched = [code] if code in idx[pais] else ([code] if code else [])
            for k in matched:
                info = idx[pais].get(k, {"nombre": "", "vals": {}})
                out.append({"cuenta": k, "nombre": info["nombre"],
                            "valores": {p: round(info["vals"].get(p, 0.0), 2) for p in periodos}})
        return out

    co = expandir("CO", g.cuentas_co)
    es = expandir("ES", g.cuentas_es)

    def totales(rows):
        return {p: round(sum(r["valores"].get(p, 0.0) for r in rows), 2) for p in periodos}

    return {
        "grupo": grupo, "tipo": g.tipo, "periodos": periodos,
        "colombia": co, "espana": es,
        "total_co": totales(co), "total_es": totales(es), "encontrado": True,
    }


def auditoria(db: Session, limit: int = 200) -> list[dict]:
    rows = db.scalars(select(AuditLog).order_by(AuditLog.ts.desc()).limit(limit)).all()
    return [{
        "entidad": a.entidad, "entidad_id": a.entidad_id, "accion": a.accion,
        "valor_antes": a.valor_antes, "valor_despues": a.valor_despues,
        "usuario_id": a.usuario_id, "ts": a.ts.isoformat() if a.ts else None,
    } for a in rows]


def estado_datos(db: Session) -> dict:
    """Resumen de qué se ha ingerido (para el dashboard/ingesta)."""
    n_co = db.scalar(select(func.count()).select_from(AccountPeriod).where(AccountPeriod.pais == "CO")) or 0
    n_es = db.scalar(select(func.count()).select_from(AccountPeriod).where(AccountPeriod.pais == "ES")) or 0
    n_map = db.scalar(select(func.count()).select_from(AccountMapping)) or 0
    n_ter = db.scalar(select(func.count()).select_from(TerceroBridge)) or 0
    periodos = sorted({p for (p,) in db.execute(select(AccountPeriod.periodo).distinct())})
    return {
        "colombia_cuentas": n_co, "espana_cuentas": n_es,
        "homologacion_mappings": n_map, "terceros": n_ter,
        "periodos": periodos,
        "listo_para_comparativa": bool(n_co and n_es and n_map),
    }
