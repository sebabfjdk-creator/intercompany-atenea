"""Motor de conciliación PYG por grupo homologado × periodo.

Normalización de signos (§B): cada lado se lleva a su naturaleza positiva.
  CO ingreso (clase 4): crédito - débito      CO gasto (clase 5): débito - crédito
  ES ingreso (clase 7): haber  - debe         ES gasto (clase 6): debe  - haber

Diferencia = total_CO - total_ES. Estado por tolerancia (|dif| <= abs o <= pct).

Nota sobre granularidad: el balance de Colombia de Feb-Marzo viene combinado en
un solo periodo, por lo que el cruce opera con los periodos disponibles
('2026-01' y '2026-02-03'); el movimiento de España se agrega al mismo periodo.
"""
from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass

from ingestion.colombia import CuentaBalanceCO
from ingestion.espana import CuentaES
from ingestion.homologacion import GrupoHomologado


def valor_co(cuenta: CuentaBalanceCO) -> float:
    clase = cuenta.codigo[:1]
    if clase == "4":      # ingreso -> naturaleza crédito
        return round(cuenta.creditos - cuenta.debitos, 2)
    return round(cuenta.debitos - cuenta.creditos, 2)  # gasto / resto -> débito


def valor_es_movs(cuenta: CuentaES) -> float:
    clase = cuenta.codigo[:1]
    sd = sum(m.debe for m in cuenta.movimientos)
    sh = sum(m.haber for m in cuenta.movimientos)
    if clase == "7":      # ingreso -> naturaleza crédito
        return round(sh - sd, 2)
    return round(sd - sh, 2)  # gasto (6) / resto -> débito


@dataclass
class ResultadoConciliacion:
    grupo: str
    tipo: str
    periodo: str
    total_co: float
    total_es: float
    diferencia: float
    pct_dif: float
    estado: str


def _estado(co: float, es: float, tol_abs: float, tol_pct: float) -> tuple[float, float, str]:
    dif = round(co - es, 2)
    base = max(abs(co), abs(es))
    pct = (abs(dif) / base) if base else 0.0
    conciliado = abs(dif) <= tol_abs or pct <= tol_pct
    return dif, round(pct, 6), ("conciliado" if conciliado else "excepcion")


def cruzar_pyg(
    grupos: list[GrupoHomologado],
    co_balances: dict[str, list[CuentaBalanceCO]],
    es_movs: dict[str, list[CuentaES]],
    tol_abs: float = 1000.0,
    tol_pct: float = 0.005,
) -> list[ResultadoConciliacion]:
    """Cruza cada grupo homologado contra cada periodo presente en ambos lados."""
    # índices código -> valor por periodo
    co_idx: dict[str, dict[str, float]] = {}
    for periodo, cuentas in co_balances.items():
        co_idx[periodo] = {c.codigo: valor_co(c) for c in cuentas}
    es_idx: dict[str, dict[str, float]] = {}
    for periodo, cuentas in es_movs.items():
        agg: dict[str, float] = defaultdict(float)
        for c in cuentas:
            agg[c.codigo] += valor_es_movs(c)
        es_idx[periodo] = dict(agg)

    return _cruzar(grupos, co_idx, es_idx, tol_abs, tol_pct)


def _suma_codigos(idx_periodo: dict, codes) -> float:
    """Suma los valores de las cuentas del grupo. Soporta wildcard final
    ('642.0.0.x' / '642.0.0.*') que agrupa todas las subcuentas con ese prefijo."""
    total = 0.0
    for code in codes:
        if code and code[-1] in ("x", "X", "*"):
            pref = code[:-1]
            total += sum(v for k, v in idx_periodo.items() if k.startswith(pref))
        else:
            total += idx_periodo.get(code, 0.0)
    return total


def _cruzar(grupos, co_idx, es_idx, tol_abs, tol_pct) -> list[ResultadoConciliacion]:
    periodos = sorted(set(co_idx) & set(es_idx))
    resultados: list[ResultadoConciliacion] = []
    for g in grupos:
        for periodo in periodos:
            total_co = round(_suma_codigos(co_idx[periodo], g.cuentas_co), 2)
            total_es = round(_suma_codigos(es_idx[periodo], g.cuentas_es), 2)
            dif, pct, estado = _estado(total_co, total_es, tol_abs, tol_pct)
            resultados.append(ResultadoConciliacion(
                grupo=g.grupo, tipo=g.tipo, periodo=periodo,
                total_co=total_co, total_es=total_es,
                diferencia=dif, pct_dif=pct, estado=estado,
            ))
    return resultados


def valor_periodo(pais: str, codigo: str, debe: float, haber: float) -> float:
    """Normaliza a naturaleza positiva: ingreso (CO clase 4 / ES clase 7) = haber - debe;
    resto (gastos, etc.) = debe - haber."""
    clase = codigo[:1]
    ingreso = (pais == "CO" and clase == "4") or (pais == "ES" and clase == "7")
    return round((haber - debe) if ingreso else (debe - haber), 2)


def cruzar_pyg_periodos(
    grupos: list[GrupoHomologado],
    filas,  # iterable de objetos/tuplas con (pais, codigo, periodo, debe, haber)
    tol_abs: float = 1000.0,
    tol_pct: float = 0.005,
) -> list[ResultadoConciliacion]:
    """Variante que cruza desde filas AccountPeriod (BD)."""
    from collections import defaultdict
    co_idx: dict[str, dict[str, float]] = defaultdict(dict)
    es_idx: dict[str, dict[str, float]] = defaultdict(dict)
    for r in filas:
        pais = r.pais if hasattr(r, "pais") else r[0]
        codigo = r.codigo if hasattr(r, "codigo") else r[1]
        periodo = r.periodo if hasattr(r, "periodo") else r[2]
        debe = float(r.debe if hasattr(r, "debe") else r[3])
        haber = float(r.haber if hasattr(r, "haber") else r[4])
        v = valor_periodo(pais, codigo, debe, haber)
        (co_idx if pais == "CO" else es_idx)[periodo][codigo] = v
    return _cruzar(grupos, dict(co_idx), dict(es_idx), tol_abs, tol_pct)


def causa_sugerida(r: ResultadoConciliacion) -> str | None:
    """Heurística de causa para una excepción (§F). None si está conciliado."""
    if r.estado == "conciliado":
        return None
    g = r.grupo.lower()
    if ("icbf" in g or "i.c.b.f" in g or "sena" in g) and abs(r.total_es) < 1.0:
        return "parafiscal_co"          # parafiscal propio de Colombia
    if abs(r.total_co) < 1.0 and abs(r.total_es) > 0:
        return "sin_homologar"          # solo aparece en España
    if abs(r.total_es) < 1.0 and abs(r.total_co) > 0:
        return "sin_homologar"          # solo aparece en Colombia
    if r.pct_dif <= 0.02:
        return "redondeo"
    return "timing"                      # por defecto: periodificación/timing


def running_balance(resultados: list[ResultadoConciliacion]) -> list[dict]:
    """Saldo acumulado rolling por grupo a través de los periodos (ordenados)."""
    acc: dict[str, dict[str, float]] = defaultdict(lambda: {"co": 0.0, "es": 0.0})
    out = []
    for r in sorted(resultados, key=lambda x: (x.grupo, x.periodo)):
        a = acc[r.grupo]
        a["co"] = round(a["co"] + r.total_co, 2)
        a["es"] = round(a["es"] + r.total_es, 2)
        out.append({
            "grupo": r.grupo, "periodo": r.periodo,
            "saldo_acumulado_co": a["co"], "saldo_acumulado_es": a["es"],
            "dif_acumulada": round(a["co"] - a["es"], 2),
        })
    return out
