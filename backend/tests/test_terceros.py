"""Tests del puente de terceros NIF<->NIT contra datos reales.

- normalizar_nif() reproduce la columna 'NIF normalizado' precalculada del archivo.
- Se verifican >= 5 cruces NIF->NIT contra los NIT que aparecen en los
  movimientos de Colombia (requisito de la Fase 1b).
"""
import pytest

from ingestion.colombia import parse_colombia_movimientos
from ingestion.terceros import (
    load_puente_terceros,
    load_reporte_terceros,
    validar_normalizacion,
)


@pytest.fixture(scope="module")
def puente(f_homologacion):
    if not f_homologacion.exists():
        pytest.skip(f"Falta archivo: {f_homologacion}")
    return load_puente_terceros(f_homologacion)


def test_puente_carga(puente):
    assert len(puente) > 1500
    assert all(t.cuenta_es for t in puente)


def test_normalizar_nif_reproduce_archivo(puente):
    diffs = validar_normalizacion(puente)
    # Tolerancia: el archivo recorta un RFC mexicano (PMG170123LIA) de forma
    # discutible; aceptamos hasta 2 discrepancias documentadas.
    assert len(diffs) <= 2, f"demasiadas discrepancias: {diffs[:10]}"


def test_reporte_delsol(f_terceros):
    if not f_terceros.exists():
        pytest.skip(f"Falta archivo: {f_terceros}")
    rep = load_reporte_terceros(f_terceros)
    assert len(rep) > 1500
    assert {r["tipo"] for r in rep} == {"Cliente", "Proveedor"}


def test_cruces_nif_nit(puente, f_colombia):
    if not f_colombia.exists():
        pytest.skip(f"Falta archivo: {f_colombia}")
    nits_co = {m.nit for m in parse_colombia_movimientos(f_colombia, "Mvto_Febrero-Marzo")}
    nits_co |= {m.nit for m in parse_colombia_movimientos(f_colombia, "Mvto_Enero", solo_detalle=False)}
    cruces = [t for t in puente if t.nit_colombia and t.nit_colombia in nits_co]
    assert len(cruces) >= 5, f"solo {len(cruces)} cruces NIF->NIT"
