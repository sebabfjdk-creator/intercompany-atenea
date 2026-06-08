"""Configuración editable: homologación de cuentas y tolerancias.

La propagación a Comparativa/Resumen/Terceros/Excepciones es automática: esos
endpoints calculan en vivo desde account_mapping en cada request, así que al
reescribir los mappings los resultados reflejan los cambios sin recálculo persistido.
"""
from __future__ import annotations

from collections import defaultdict

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.config import get_settings
from db.models import AccountMapping, AppConfig, AuditLog, HomologationGroup
from ingestion.homologacion import GrupoHomologado

settings = get_settings()
TIPOS_VALIDOS = ("gasto", "ingreso", "activo", "pasivo")
RELACIONES_VALIDAS = ("directa", "n_a_n", "sin_par")


# ---------- Tolerancias ----------
def get_tolerancia(db: Session) -> tuple[float, float]:
    rows = {c.clave: c.valor for c in db.scalars(select(AppConfig)).all()}
    try:
        abs_cop = float(rows.get("tolerancia_abs_cop", settings.tolerancia_abs_cop))
    except ValueError:
        abs_cop = settings.tolerancia_abs_cop
    try:
        pct = float(rows.get("tolerancia_pct", settings.tolerancia_pct))
    except ValueError:
        pct = settings.tolerancia_pct
    return abs_cop, pct


def set_tolerancia(db: Session, abs_cop: float, pct: float, usuario_id=None) -> None:
    antes = get_tolerancia(db)
    for clave, valor in (("tolerancia_abs_cop", abs_cop), ("tolerancia_pct", pct)):
        row = db.get(AppConfig, clave)
        if row:
            row.valor = str(valor)
        else:
            db.add(AppConfig(clave=clave, valor=str(valor)))
    db.add(AuditLog(entidad="tolerancia", entidad_id="", accion="update",
                    valor_antes=str(antes), valor_despues=str((abs_cop, pct)), usuario_id=usuario_id))
    db.commit()


# ---------- Grupos homologados ----------
def _inferir_tipo(co: list[str], es: list[str]) -> str:
    if any(c[:1] == "4" for c in co) or any(c[:1] == "7" for c in es):
        return "ingreso"
    return "gasto"


def grupos_homologados(db: Session) -> list[GrupoHomologado]:
    """Lista para el motor: account_mapping + tipo desde HomologationGroup (o inferido)."""
    meta = {g.nombre: g for g in db.scalars(select(HomologationGroup)).all()}
    by: dict[str, dict] = defaultdict(lambda: {"co": set(), "es": set()})
    for r in db.scalars(select(AccountMapping).where(AccountMapping.activo.is_(True))).all():
        if r.cuenta_co_patron:
            by[r.grupo_homologado]["co"].add(r.cuenta_co_patron)
        if r.cuenta_es:
            by[r.grupo_homologado]["es"].add(r.cuenta_es)
    out = []
    for nombre, d in by.items():
        co, es = sorted(d["co"]), sorted(d["es"])
        m = meta.get(nombre)
        tipo = m.tipo if m else _inferir_tipo(co, es)
        rel = m.tipo_relacion if m else ("directa" if len(co) == 1 and len(es) == 1 else "n_a_n")
        out.append(GrupoHomologado(grupo=nombre, tipo=tipo, cuentas_co=co, cuentas_es=es, descripcion=rel))
    return out


def get_homologacion(db: Session) -> dict:
    meta = {g.nombre: g for g in db.scalars(select(HomologationGroup)).all()}
    grupos = grupos_homologados(db)
    abs_cop, pct = get_tolerancia(db)
    return {
        "grupos": [{
            "id": meta[g.grupo].id if g.grupo in meta else None,
            "grupo": g.grupo, "tipo": g.tipo,
            "tipo_relacion": (meta[g.grupo].tipo_relacion if g.grupo in meta else g.descripcion),
            "cuentas_co": g.cuentas_co, "cuentas_es": g.cuentas_es,
        } for g in sorted(grupos, key=lambda x: (x.tipo, x.grupo))],
        "tolerancia_abs_cop": abs_cop,
        "tolerancia_pct": pct,
    }


def save_homologacion(db: Session, grupos: list[dict], usuario_id=None) -> dict:
    """Reescribe HomologationGroup + account_mapping desde el payload completo."""
    # validación
    for g in grupos:
        if not (g.get("grupo") or "").strip():
            raise ValueError("Cada grupo requiere un nombre")
        if g.get("tipo") not in TIPOS_VALIDOS:
            raise ValueError(f"Tipo inválido en '{g.get('grupo')}': {g.get('tipo')}")
        if not g.get("cuentas_co") and not g.get("cuentas_es"):
            raise ValueError(f"El grupo '{g.get('grupo')}' necesita al menos una cuenta CO o ES")
    nombres = [g["grupo"].strip() for g in grupos]
    if len(nombres) != len(set(nombres)):
        raise ValueError("Hay nombres de grupo duplicados")

    antes = get_homologacion(db)
    db.execute(delete(AccountMapping))
    db.execute(delete(HomologationGroup))
    for g in grupos:
        nombre = g["grupo"].strip()
        rel = g.get("tipo_relacion") if g.get("tipo_relacion") in RELACIONES_VALIDAS else "n_a_n"
        db.add(HomologationGroup(nombre=nombre, tipo=g["tipo"], tipo_relacion=rel, activo=True))
        co = [str(c).strip() for c in (g.get("cuentas_co") or []) if str(c).strip()]
        es = [str(c).strip() for c in (g.get("cuentas_es") or []) if str(c).strip()]
        pares = [(c, e) for c in (co or [""]) for e in (es or [""])]
        for c, e in pares:
            db.add(AccountMapping(cuenta_co_patron=c, cuenta_es=e, grupo_homologado=nombre,
                                  tipo_relacion=rel, confianza="alta", activo=True))
    db.add(AuditLog(entidad="homologacion", entidad_id="", accion="update",
                    valor_antes=f"{len(antes['grupos'])} grupos",
                    valor_despues=f"{len(grupos)} grupos", usuario_id=usuario_id))
    db.commit()
    return get_homologacion(db)
