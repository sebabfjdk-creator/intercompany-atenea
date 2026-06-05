"""Tests del adapter España (DELSOL) contra el Libro Mayor real.

Verifican la identidad contable del export:  Total: = saldo_anterior + Σ movimientos
para CADA cuenta. Si esto cuadra, el parseo de bloques, propagación de código y
formato numérico (español/nativo) son correctos.
"""
import pytest

from ingestion.espana import parse_espana_movimientos, validar_totales

SHEETS = ["AteneaEneroMvto", "AteneaFebrero-MarzoMvti"]


@pytest.fixture(scope="module")
def _require_file(f_espana):
    if not f_espana.exists():
        pytest.skip(f"Falta archivo de datos: {f_espana}")
    return f_espana


@pytest.mark.parametrize("sheet", SHEETS)
def test_totales_cuadran(_require_file, sheet):
    cuentas = parse_espana_movimientos(_require_file, sheet)
    assert cuentas, "no se parseó ninguna cuenta"
    descuadres = validar_totales(cuentas)
    assert descuadres == [], f"{len(descuadres)} cuentas descuadran: {descuadres[:5]}"


def test_codigos_y_movimientos(_require_file):
    cuentas = parse_espana_movimientos(_require_file, "AteneaEneroMvto")
    # códigos en formato DELSOL NNN.N.N.NNN
    assert all(len(c.codigo) == 11 and c.codigo.count(".") == 3 for c in cuentas)
    # debe haber movimientos con neto = debe - haber
    movs = [m for c in cuentas for m in c.movimientos]
    assert len(movs) > 1000
    m = movs[0]
    assert m.neto == round(m.debe - m.haber, 2)
