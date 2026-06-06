"""Consultas de negocio: construyen las respuestas de los tableros desde la BD."""
from __future__ import annotations

from collections import defaultdict

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.config import get_settings
from db.models import AccountMapping, AccountPeriod, AuditLog, TerceroBridge
from domain.reconciliacion import causa_sugerida, cruzar_pyg_periodos
from ingestion.homologacion import GrupoHomologado

settings = get_settings()


def _grupos_desde_mapping(db: Session) -> list[GrupoHomologado]:
    rows = db.scalars(select(AccountMapping).where(AccountMapping.activo.is_(True))).all()
    by: dict[str, dict] = defaultdict(lambda: {"co": set(), "es": set()})
    for r in rows:
        if r.cuenta_co_patron:
            by[r.grupo_homologado]["co"].add(r.cuenta_co_patron)
        if r.cuenta_es:
            by[r.grupo_homologado]["es"].add(r.cuenta_es)
    grupos = []
    for grupo, d in by.items():
        co = sorted(d["co"])
        es = sorted(d["es"])
        tipo = "ingreso" if any(c[:1] == "4" for c in co) or any(c[:1] == "7" for c in es) else "gasto"
        grupos.append(GrupoHomologado(grupo=grupo, tipo=tipo, cuentas_co=co, cuentas_es=es))
    return grupos


def _resultados(db: Session):
    grupos = _grupos_desde_mapping(db)
    filas = db.scalars(select(AccountPeriod)).all()
    return cruzar_pyg_periodos(grupos, filas, settings.tolerancia_abs_cop, settings.tolerancia_pct)


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
    grupos = _grupos_desde_mapping(db)
    return {
        "grupos": [{
            "grupo": g.grupo, "tipo": g.tipo, "tipo_relacion": g.tipo_relacion,
            "cuentas_co": g.cuentas_co, "cuentas_es": g.cuentas_es,
        } for g in sorted(grupos, key=lambda x: (x.tipo, x.grupo))],
        "tolerancia_abs_cop": settings.tolerancia_abs_cop,
        "tolerancia_pct": settings.tolerancia_pct,
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
