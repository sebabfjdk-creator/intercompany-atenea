"""Tests del motor de conciliación PYG y del loader de homologación.

Validación clave: contra los datos reales, un número sustancial de grupos de
gasto debe reconciliar a < tolerancia (cuadran contra dos libros independientes),
y la diferencia ICBF/SENA debe clasificarse como parafiscal_co.
"""
import pytest

from domain.reconciliacion import (
    causa_sugerida,
    cruzar_pyg,
    running_balance,
    valor_co,
)
from ingestion.colombia import CuentaBalanceCO, parse_colombia_balance
from ingestion.espana import parse_espana_movimientos
from ingestion.homologacion import load_homologacion


def test_valor_co_signo_por_clase():
    ingreso = CuentaBalanceCO("41xxxx", "Ventas", 6, 0, 100, 900, -800)
    gasto = CuentaBalanceCO("51xxxx", "Sueldos", 6, 0, 900, 100, 800)
    assert valor_co(ingreso) == 800   # clase 4: crédito - débito
    assert valor_co(gasto) == 800     # clase 5: débito - crédito


def test_homologacion_carga(f_homologacion):
    if not f_homologacion.exists():
        pytest.skip("falta homologacion")
    grupos = load_homologacion(f_homologacion)
    assert len(grupos) > 30
    assert any(g.tipo == "ingreso" for g in grupos)
    assert any(g.tipo == "gasto" for g in grupos)


@pytest.fixture(scope="module")
def resultados(f_homologacion, f_colombia, f_espana):
    for f in (f_homologacion, f_colombia, f_espana):
        if not f.exists():
            pytest.skip("faltan archivos de datos")
    grupos = load_homologacion(f_homologacion)
    co = {
        "2026-01": parse_colombia_balance(f_colombia, "Balance_Enero"),
        "2026-02-03": parse_colombia_balance(f_colombia, "Balance_Febrero-Marzo"),
    }
    es = {
        "2026-01": parse_espana_movimientos(f_espana, "AteneaEneroMvto"),
        "2026-02-03": parse_espana_movimientos(f_espana, "AteneaFebrero-MarzoMvti"),
    }
    return cruzar_pyg(grupos, co, es)


def test_diferencia_es_consistente(resultados):
    for r in resultados:
        assert r.diferencia == round(r.total_co - r.total_es, 2)


def test_muchos_grupos_reconcilian(resultados):
    # Validación dura: contra datos reales, >= 20 cruces deben quedar conciliados.
    conc = [r for r in resultados if r.estado == "conciliado"]
    assert len(conc) >= 20, f"solo {len(conc)} conciliados"


def test_parafiscal_co_detectado(resultados):
    causas = {causa_sugerida(r) for r in resultados}
    assert "parafiscal_co" in causas


def test_running_balance_acumula(resultados):
    rb = running_balance(resultados)
    assert rb
    assert all(set(x) >= {"saldo_acumulado_co", "saldo_acumulado_es", "dif_acumulada"} for x in rb)
