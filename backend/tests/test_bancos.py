"""Conciliación Bancaria: motor de cruce + validación de febrero contra archivos reales."""
import shutil
import tempfile
from datetime import datetime
from pathlib import Path

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.services import bank_service as svc
from db.base import Base
from ingestion.bancos import MovBanco, conciliar


def _m(fecha, monto):
    return MovBanco(fecha=datetime.fromisoformat(fecha), monto=monto, concepto="x")


def test_conciliar_engine_sintetico():
    cont = [_m("2026-02-01", 100.0), _m("2026-02-02", -50.0), _m("2026-02-03", 30.0), _m("2026-02-10", 999.0)]
    ext = [_m("2026-02-01", 100.0),   # exacto
           _m("2026-02-04", -50.0),   # mismo monto, +2 días -> fecha_dif
           _m("2026-02-28", 777.0)]   # solo banco
    pares, solo_l, solo_b = conciliar(cont, ext, tol_dias=3)
    tipos = sorted(t for _, _, t in pares)
    assert tipos == ["exacto", "fecha_dif"]
    assert len(solo_l) == 2   # 30.0 y 999.0 sin contraparte
    assert len(solo_b) == 1   # 777.0
    # 1:1 — un extracto no se reutiliza
    assert len({j for _, j, _ in pares}) == len(pares)


def _copia_temp(p: Path) -> str:
    """Copia a temp para evitar el lock si el archivo está abierto en Excel."""
    dst = Path(tempfile.gettempdir()) / ("t_" + p.name)
    shutil.copy(p, dst)
    return str(dst)


def test_febrero_real_cuadra_cero(f_bancos_contable, f_banco_extracto):
    if not (f_bancos_contable.exists() and f_banco_extracto.exists()):
        pytest.skip("faltan archivos de bancos")
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    with sessionmaker(bind=engine)() as db:
        svc.ingest(db, "contable", _copia_temp(f_bancos_contable))
        svc.ingest(db, "extracto", _copia_temp(f_banco_extracto))
        d = svc.conciliacion(db, "2026-02")
        k = d["kpis"]
        assert k["exactos"] >= 190, k          # ~191 exactos
        assert k["solo_banco"] == 0, k         # todo el extracto cruzó
        # saldos iniciales 0 (febrero) -> diferencia exacta 0
        assert d["bloque_conciliar"]["diferencia"] == 0.0, d["bloque_conciliar"]
