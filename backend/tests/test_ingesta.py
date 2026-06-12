"""Fase 0+1 del módulo de ingesta:
- Borrado QUIRÚRGICO por periodo (no por país) -> no se pierde otro periodo.
- Historial de cargas (FileUpload): registro + marca de reemplazo.
"""
import pytest
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import sessionmaker

from app.services import ingest as ingest_svc
from db.base import Base
from db.models import AccountPeriod, FileUpload


def _session(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path/'i.sqlite'}", connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine)


def test_consolidacion_net_real(tmp_path, f_homologacion):
    if not f_homologacion.exists():
        pytest.skip("falta homologacion")
    from app.services import config_service
    S = _session(tmp_path)
    with S() as db:
        ingest_svc.ingest_homologacion(db, str(f_homologacion))
        gh = {g.grupo: g for g in config_service.grupos_homologados(db)}
        ing = gh.get("NET REAL SOLUTIONS - Ingresos")
        gas = gh.get("NET REAL SOLUTIONS - Gastos")
        assert ing and gas, "faltan los rubros NET REAL"
        assert set(ing.cuentas_co) == {"41553503", "42102005"}
        assert set(ing.cuentas_es) == {"700.0.0.101"} and ing.tipo == "ingreso"
        assert set(gas.cuentas_co) == {"51351501", "51351503", "51352001", "515505", "515595", "51950505"}
        assert set(gas.cuentas_es) == {"602.0.0.101", "602.0.0.103", "629.0.0.100"} and gas.tipo == "gasto"
        # ninguna cuenta NET REAL queda en OTRO grupo (sin doble conteo)
        for nombre, g in gh.items():
            if nombre.startswith("NET REAL"):
                continue
            assert "51352001" not in g.cuentas_co, f"51352001 duplicada en {nombre}"
            assert "41553503" not in g.cuentas_co
            assert "700.0.0.101" not in g.cuentas_es


def test_detect_co_sheets_export_mensual():
    # Export mensual de Siesa (nombres variables) -> reconoce balance/mov y mes
    bal, mov = ingest_svc._detect_co_sheets(["Consulta_ Mayor y balances ENER", "Rept Mov. Ctas. Aux"])
    assert bal.get("Consulta_ Mayor y balances ENER") == "2026-01"
    assert mov.get("Rept Mov. Ctas. Aux") == "2026-01"
    # Febrero por nombre
    bal_f, _ = ingest_svc._detect_co_sheets(["Consulta Mayor y balances FEBRERO", "Rept Mov Ctas Aux"])
    assert list(bal_f.values()) == ["2026-02"]
    # Formato consolidado fijo sigue funcionando
    bal2, mov2 = ingest_svc._detect_co_sheets(["Balance_Enero", "Mvto_Enero", "Balance_Febrero-Marzo", "Mvto_Febrero-Marzo"])
    assert bal2.get("Balance_Enero") == "2026-01" and mov2.get("Mvto_Enero") == "2026-01"


def test_detectar_tipo(f_homologacion, f_colombia, f_espana, f_cartera):
    casos = [
        (f_espana, "espana"), (f_colombia, "colombia"),
        (f_homologacion, ("homologacion", "terceros")),
        (f_cartera, ("arap_co", "arap_es")),  # cartera/pasivos -> AR/AP
    ]
    for f, esperado in casos:
        if not f.exists():
            continue
        tipo = ingest_svc.detectar_tipo(str(f))
        if isinstance(esperado, tuple):
            assert tipo in esperado, f"{f.name}: {tipo} no en {esperado}"
        else:
            assert tipo == esperado, f"{f.name}: {tipo} != {esperado}"


def test_borrado_por_periodo_no_pierde_otro_periodo(tmp_path, f_espana):
    if not f_espana.exists():
        pytest.skip("falta espana_delsol.xlsx")
    S = _session(tmp_path)
    with S() as db:
        ingest_svc.ingest_espana(db, str(f_espana))
        n1 = db.scalar(select(func.count()).select_from(AccountPeriod).where(AccountPeriod.pais == "ES"))
        # centinela: un periodo que NO está en el archivo (no debe borrarse al recargar)
        db.add(AccountPeriod(pais="ES", codigo="SENTINEL", periodo="2099-12", debe=1, haber=0))
        db.commit()

        ingest_svc.ingest_espana(db, str(f_espana))  # recarga: solo 2026-01 y 2026-02-03

        # el centinela de 2099-12 SIGUE vivo (antes el delete borraba todo el país)
        assert db.scalar(select(func.count()).select_from(AccountPeriod)
                         .where(AccountPeriod.codigo == "SENTINEL")) == 1
        # y no se duplicaron las cuentas reales (mismo conteo tras recargar)
        n2 = db.scalar(select(func.count()).select_from(AccountPeriod)
                       .where(AccountPeriod.pais == "ES", AccountPeriod.codigo != "SENTINEL"))
        assert n2 == n1


def test_registrar_carga_historial_y_reemplazo(tmp_path, f_espana):
    if not f_espana.exists():
        pytest.skip("falta espana_delsol.xlsx")
    S = _session(tmp_path)
    with S() as db:
        res = ingest_svc.ingest_espana(db, str(f_espana))
        ingest_svc.registrar_carga(db, tipo="espana", nombre_original="ene-mar.xlsx",
                                   path=str(f_espana), resultado=res, usuario_id=None)
        ingest_svc.registrar_carga(db, tipo="espana", nombre_original="ene-mar-v2.xlsx",
                                   path=str(f_espana), resultado=res, usuario_id=None)

        cargas = db.scalars(select(FileUpload).where(FileUpload.tipo_archivo == "espana")
                            .order_by(FileUpload.id)).all()
        assert len(cargas) == 2
        assert cargas[0].estado == "reemplazado"   # la primera quedó sustituida
        assert cargas[1].estado == "cargado"        # la última es la activa
        assert cargas[1].registros_insertados == res["cuentas"]
        assert set(cargas[1].periodo.split(",")) == set(res["periodos"])
        assert len(cargas[1].hash_archivo) == 64


def test_conflicto_periodo_y_eliminar(tmp_path, f_espana):
    if not f_espana.exists():
        pytest.skip("falta espana_delsol.xlsx")
    S = _session(tmp_path)
    with S() as db:
        res = ingest_svc.ingest_espana(db, str(f_espana))
        ingest_svc.registrar_carga(db, tipo="espana", nombre_original="v1.xlsx",
                                   path=str(f_espana), resultado=res, usuario_id=None)
        # mismos periodos -> conflicto detectado (control de duplicados)
        conflicto = ingest_svc.periodos_en_conflicto(db, "espana", res["periodos"])
        assert set(conflicto) == set(res["periodos"])
        # un periodo nuevo NO entra en conflicto
        assert ingest_svc.periodos_en_conflicto(db, "espana", ["2030-07"]) == []

        # eliminar_datos_de borra las cuentas del periodo
        from db.models import AccountPeriod as AP
        n_antes = db.scalar(select(func.count()).select_from(AP).where(AP.pais == "ES"))
        assert n_antes > 0
        ingest_svc.eliminar_datos_de(db, "espana", ",".join(res["periodos"]))
        db.commit()
        assert db.scalar(select(func.count()).select_from(AP).where(AP.pais == "ES")) == 0


def test_eliminar_periodo_solo_afecta_ese_periodo(tmp_path, f_espana):
    if not f_espana.exists():
        pytest.skip("falta espana_delsol.xlsx")
    S = _session(tmp_path)
    with S() as db:
        ingest_svc.ingest_espana(db, str(f_espana))  # carga 2026-01 y 2026-02-03
        from db.models import AccountPeriod as AP
        cargados = ingest_svc.periodos_cargados(db)
        periodos = {r["periodo"] for r in cargados if r["pais"] == "ES"}
        assert {"2026-01", "2026-02-03"} <= periodos

        n01 = db.scalar(select(func.count()).select_from(AP).where(AP.pais == "ES", AP.periodo == "2026-01"))
        assert n01 > 0
        # eliminar SOLO Feb-Marzo
        res = ingest_svc.eliminar_periodo(db, "ES", "2026-02-03")
        db.commit()
        assert res["cuentas"] > 0
        # Enero intacto; Feb-Marzo borrado
        assert db.scalar(select(func.count()).select_from(AP).where(AP.pais == "ES", AP.periodo == "2026-02-03")) == 0
        assert db.scalar(select(func.count()).select_from(AP).where(AP.pais == "ES", AP.periodo == "2026-01")) == n01
