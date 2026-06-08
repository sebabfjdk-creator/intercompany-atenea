"""Tests del módulo AR/AP contra el archivo real CarteraYPasivos.xlsx."""
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.services import arap_service as svc
from app.services import ingest as ingest_svc
from db.base import Base
from ingestion.arap import parse_arap_colombia, parse_arap_espana


@pytest.fixture(scope="module")
def db(tmp_path_factory, f_homologacion, f_cartera):
    for f in (f_homologacion, f_cartera):
        if not f.exists():
            pytest.skip("faltan archivos de datos")
    p = tmp_path_factory.mktemp("db") / "arap.sqlite"
    engine = create_engine(f"sqlite:///{p}", connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    S = sessionmaker(bind=engine)
    with S() as d:
        ingest_svc.ingest_terceros(d, str(f_homologacion))  # puente NIF<->NIT
        svc.ingest_espana(d, str(f_cartera))
        svc.ingest_colombia(d, str(f_cartera))
        yield d


# --- parsers puros ---
def test_parser_espana_provisionales(f_cartera):
    if not f_cartera.exists():
        pytest.skip("falta cartera")
    es = parse_arap_espana(f_cartera, "CarteraAtenea")
    assert len([t for t in es if t.es_provisional]) == 7
    link = next((t for t in es if t.cuenta_es == "430.0.0.271"), None)
    assert link and round(link.saldo, 2) == 501657.75


def test_parser_colombia_error_1305(f_cartera):
    if not f_cartera.exists():
        pytest.skip("falta cartera")
    co = parse_arap_colombia(f_cartera, "CarteraNeuron")
    errores = [t for t in co if t.error_contabilizacion]
    assert len(errores) >= 1
    assert all(t.saldo_1305 < 0 for t in errores)


# --- servicio / motor ---
def test_estado_datos(db):
    e = svc.estado_datos(db)
    assert e["espana_terceros"] > 100
    assert e["colombia_terceros"] > 100
    assert e["espana_provisionales"] == 10  # 7 en AR (430.9.x/431.9.9.x) + 3 en AP (410.9.x)
    assert e["listo"] is True


def test_reconciliacion_y_estados(db):
    r = svc.reconciliacion(db)
    estados = {f["estado"] for f in r["filas"]}
    assert "CONCILIADO" in estados or "DIFERENCIA" in estados
    assert r["kpis"]["terceros"] > 0
    for f in r["filas"]:
        assert f["diferencia"] == round(f["saldo_co"] - f["saldo_es"], 2)


def test_provisionales_y_errores(db):
    assert len(svc.provisionales(db)) == 10  # AR + AP
    assert len(svc.errores_contables(db)) >= 1


def test_movimientos_y_totales(db):
    r = svc.reconciliacion(db)
    # §4 totales por categoría
    assert set(r["totales"]) == {"CLIENTES", "PROVEEDORES", "TOTAL"}
    # §2 cada fila trae débitos/créditos del periodo y categoría
    assert all("debitos_mes" in f and f["categoria"] in ("CLIENTE", "PROVEEDOR") for f in r["filas"])
    # §5 movimientos por tercero: tomar uno con match (tiene CO y ES)
    con_match = next((f for f in r["filas"] if f["estado"] in ("CONCILIADO", "DIFERENCIA") and f["nit"]), None)
    assert con_match, "no hay tercero con match"
    det = svc.movimientos_tercero(db, con_match["nit"])
    assert "resumen" in det and "movimientos_co" in det and "movimientos_es" in det
    assert det["movimientos_co"] or det["movimientos_es"]
    # consistencia interna del resumen (detalle por NIT, agrega AR+AP)
    rr = det["resumen"]
    assert rr["diferencia"] == round(rr["saldo_co"] - rr["saldo_es"], 2)


def test_resumen_proveedor_usa_22xx(db):
    # Regresión: para un proveedor PURO (solo AP, sin AR) el saldo_co del detalle
    # debe venir de 22xx (no quedarse en 0 por usar solo 1305/2805).
    r = svc.reconciliacion(db)
    nits_ar = {f["nit"] for f in r["filas"] if f["tipo"] == "AR" and f["nit"]}
    prov = next((f for f in r["filas"]
                 if f["tipo"] == "AP" and f["nit"] and f["nit"] not in nits_ar and abs(f["saldo_co"]) > 1), None)
    if prov:
        det = svc.movimientos_tercero(db, prov["nit"])
        assert det["resumen"]["saldo_co"] == prov["saldo_co"]
        assert det["resumen"]["saldo_co"] != 0


def test_tercero_360(db):
    r = svc.reconciliacion(db)
    fila = next((f for f in r["filas"] if f["nit"] and f["estado"] in ("CONCILIADO", "DIFERENCIA")), None)
    assert fila
    v = svc.tercero_360(db, fila["nit"])
    assert set(v["resumen"]) >= {"saldo_co", "saldo_es", "diferencia", "estado", "antiguedad", "mes_origen", "ultimo_movimiento"}
    assert v["resumen"]["estado"] in ("Conciliado", "Diferencia temporal", "Diferencia permanente", "Pendiente de revisión")
    assert isinstance(v["timeline"], list) and isinstance(v["analisis"], list) and v["analisis"]
    assert "matching" in v
    # los movimientos traen documento y tipo_documento
    todos = v["movimientos_co"] + v["movimientos_es"]
    if todos:
        assert set(todos[0]) >= {"documento", "tipo_documento", "saldo", "debe", "haber"}


def test_cruce_por_nombre(db):
    # entidades ES con NIF de letra (sin NIT CO) deben cruzar por nombre
    filas = svc.reconciliacion(db)["filas"]
    assert any(f.get("matched_por") == "nombre" for f in filas), "no hubo ningún cruce por nombre"
    assert all("matched_por" in f for f in filas)


def test_kpis_arap(db):
    k = svc.kpis_arap(db)
    assert set(k) >= {"diferencias_abiertas", "diferencias_conciliadas", "mayores_90_dias", "top_terceros", "top_cuentas"}
    assert len(k["top_terceros"]) <= 20
    assert k["diferencias_abiertas"] + k["diferencias_conciliadas"] > 0


def test_documento_capturado(f_cartera):
    if not f_cartera.exists():
        pytest.skip("falta cartera")
    from ingestion.arap import parse_arap_espana, tipo_documento
    es = parse_arap_espana(f_cartera, "CarteraAtenea")
    docs = [m.documento for t in es for m in (t.movimientos or []) if m.documento]
    assert docs, "no se capturó ningún documento ES"
    assert tipo_documento("FA3621") == "Factura" and tipo_documento("NC100") == "Nota crédito"


def test_filtro_fecha(db):
    # rango imposible -> sin débitos
    r = svc.reconciliacion(db, desde="2030-01-01", hasta="2030-12-31")
    assert r["totales"]["TOTAL"]["debitos"] == 0
