"""Tests del adapter Colombia (Siesa) contra balances y movimientos reales."""
import pytest

from ingestion.colombia import (
    parse_colombia_balance,
    parse_colombia_movimientos,
    validar_balance,
)

BALANCES = ["Balance_Enero", "Balance_Febrero-Marzo"]


@pytest.fixture(scope="module")
def _f(f_colombia):
    if not f_colombia.exists():
        pytest.skip(f"Falta archivo de datos: {f_colombia}")
    return f_colombia


@pytest.mark.parametrize("sheet", BALANCES)
def test_identidad_balance(_f, sheet):
    cuentas = parse_colombia_balance(_f, sheet)
    assert cuentas, "no se parseó ninguna cuenta de balance"
    descuadres = validar_balance(cuentas)
    assert descuadres == [], f"{len(descuadres)} cuentas rompen la identidad: {descuadres[:5]}"


def test_niveles_jerarquicos(_f):
    cuentas = parse_colombia_balance(_f, "Balance_Enero")
    niveles = {c.nivel for c in cuentas}
    # códigos Siesa: 1, 11, 1120, 112005, 11200501 -> niveles 1,2,4,6,8
    assert {1, 2, 4, 6, 8}.issubset(niveles)


def test_movimientos_terceros(_f):
    movs = parse_colombia_movimientos(_f, "Mvto_Febrero-Marzo")
    assert movs, "no se extrajeron movimientos"
    # cada movimiento de detalle tiene NIT y neto = débito - crédito
    assert all(m.nit for m in movs)
    m = movs[0]
    assert m.neto == round(m.debito - m.credito, 2)
