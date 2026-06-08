"""Test end-to-end de la API: ingesta (servicio) + endpoints de tableros.

Usa SQLite en archivo temporal para no requerir Postgres. Valida el flujo completo
upload -> DB -> motor -> JSON de comparativa contra los Excel reales.
"""
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.auth import create_access_token, hash_password
from app.main import app
from app.services import ingest as ingest_svc
from db.base import Base, get_db
from db.models import User


@pytest.fixture(scope="module")
def client(tmp_path_factory, f_homologacion, f_colombia, f_espana, f_terceros):
    for f in (f_homologacion, f_colombia, f_espana, f_terceros):
        if not f.exists():
            pytest.skip("faltan archivos de datos")
    db_path = tmp_path_factory.mktemp("db") / "test.sqlite"
    engine = create_engine(f"sqlite:///{db_path}", connect_args={"check_same_thread": False})
    TestSession = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    Base.metadata.create_all(engine)

    # usuario admin + ingesta de los 4 archivos
    with TestSession() as db:
        db.add(User(email="admin@atenea.com", nombre="Admin",
                    hashed_password=hash_password("x"), rol="admin"))
        db.commit()
        ingest_svc.ingest_homologacion(db, str(f_homologacion))
        ingest_svc.ingest_terceros(db, str(f_homologacion))
        ingest_svc.ingest_colombia(db, str(f_colombia))
        ingest_svc.ingest_espana(db, str(f_espana))

    def _override():
        db = TestSession()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = _override
    c = TestClient(app)
    c.headers.update({"Authorization": f"Bearer {create_access_token('admin@atenea.com', 'admin')}"})
    yield c
    app.dependency_overrides.clear()


def test_estado_datos(client):
    r = client.get("/api/estado-datos")
    assert r.status_code == 200
    d = r.json()
    assert d["espana_cuentas"] > 100 and d["colombia_cuentas"] > 100
    assert d["homologacion_mappings"] > 30
    assert d["terceros"] > 1500
    assert d["listo_para_comparativa"] is True


def test_comparativa(client):
    r = client.get("/api/comparativa")
    assert r.status_code == 200
    d = r.json()
    assert set(d["periodos"]) == {"2026-01", "2026-02-03"}
    assert d["kpis"]["conciliados"] >= 20
    assert d["filas"], "sin filas de comparativa"
    # consistencia: dif == co - es en cada celda
    for fila in d["filas"]:
        for celda in fila["celdas"].values():
            assert celda["dif"] == round(celda["co"] - celda["es"], 2)


def test_comparativa_detalle_grupo(client):
    comp = client.get("/api/comparativa").json()
    fila = next((f for f in comp["filas"] if f["celdas"]), None)
    assert fila
    det = client.get("/api/comparativa/detalle-grupo", params={"grupo": fila["grupo"]}).json()
    assert det["encontrado"] is True
    assert det["colombia"] or det["espana"]
    # consistencia: suma del detalle == total del grupo por periodo
    for periodo, celda in fila["celdas"].items():
        assert det["total_co"].get(periodo, 0) == celda["co"]
        assert det["total_es"].get(periodo, 0) == celda["es"]


def test_ingest_idempotente_y_movimientos(tmp_path_factory, f_colombia):
    if not f_colombia.exists():
        pytest.skip("falta colombia")
    from sqlalchemy import func, select
    from db.models import PygMovimiento
    p = tmp_path_factory.mktemp("idem") / "i.sqlite"
    engine = create_engine(f"sqlite:///{p}", connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    S = sessionmaker(bind=engine)
    with S() as d:
        ingest_svc.ingest_colombia(d, str(f_colombia))
        ingest_svc.ingest_colombia(d, str(f_colombia))  # 2ª vez: NO debe romper (idempotente)
        n = d.scalar(select(func.count()).select_from(PygMovimiento)) or 0
        assert n > 0  # movimientos PYG poblados


def test_movimientos_cuenta_pyg(client):
    # tomar un grupo con cuentas ES y bajar al nivel de transacción
    comp = client.get("/api/comparativa").json()
    det = None
    for f in comp["filas"]:
        d = client.get("/api/comparativa/detalle-grupo", params={"grupo": f["grupo"]}).json()
        if d.get("espana"):
            det = d
            break
    assert det, "no se encontró grupo con cuentas ES"
    cuenta = det["espana"][0]["cuenta"]
    mov = client.get("/api/comparativa/movimientos-cuenta", params={"pais": "ES", "cuenta": cuenta}).json()
    assert "items" in mov
    if mov["items"]:
        m = mov["items"][0]
        assert set(m) >= {"fecha", "concepto", "debe", "haber", "cuenta"}


def test_terceros_y_excepciones(client):
    t = client.get("/api/terceros").json()
    assert t["kpis"]["total"] > 1500
    e = client.get("/api/excepciones").json()
    assert isinstance(e, list) and len(e) > 0
    assert any(x["causa"] == "parafiscal_co" for x in e)


def test_users_crud(client):
    # listar (admin)
    r = client.get("/api/users")
    assert r.status_code == 200
    assert any(u["email"] == "admin@atenea.com" for u in r.json())
    # crear
    r = client.post("/api/users", json={"email": "nuevo@atenea.com", "nombre": "Nuevo", "password": "secreta1", "rol": "admin_co"})
    assert r.status_code == 201, r.text
    uid = r.json()["id"]
    # el nuevo usuario puede loguear
    r = client.post("/api/auth/login", data={"username": "nuevo@atenea.com", "password": "secreta1"},
                    headers={"Content-Type": "application/x-www-form-urlencoded"})
    assert r.status_code == 200
    # email duplicado -> 409
    r = client.post("/api/users", json={"email": "nuevo@atenea.com", "nombre": "X", "password": "secreta1", "rol": "admin"})
    assert r.status_code == 409
    # cambiar contraseña de otro (admin) sin 'actual'
    r = client.patch(f"/api/users/{uid}/password", json={"nueva": "otra1234"})
    assert r.status_code == 200


def test_config_homologacion_editable(client):
    # GET inicial
    h = client.get("/api/config/homologacion").json()
    assert h["grupos"] and "tipo" in h["grupos"][0]
    # editar: tomar los grupos, renombrar el primero y guardar
    grupos = [{"grupo": g["grupo"], "tipo": g["tipo"], "tipo_relacion": g["tipo_relacion"],
               "cuentas_co": g["cuentas_co"], "cuentas_es": g["cuentas_es"]} for g in h["grupos"]]
    grupos[0]["grupo"] = "GRUPO EDITADO TEST"
    r = client.put("/api/config/homologacion", json={"grupos": grupos})
    assert r.status_code == 200, r.text
    # GET refleja el cambio
    h2 = client.get("/api/config/homologacion").json()
    assert any(g["grupo"] == "GRUPO EDITADO TEST" for g in h2["grupos"])
    # validación: grupo sin cuentas -> 422
    bad = client.put("/api/config/homologacion", json={"grupos": [{"grupo": "X", "tipo": "gasto", "cuentas_co": [], "cuentas_es": []}]})
    assert bad.status_code == 422


def test_config_tolerancia(client):
    r = client.put("/api/config/tolerancia", json={"tolerancia_abs_cop": 5000, "tolerancia_pct": 0.01})
    assert r.status_code == 200
    h = client.get("/api/config/homologacion").json()
    assert h["tolerancia_abs_cop"] == 5000
    # recalcular es no-op (live)
    assert client.post("/api/config/recalcular").json()["ok"] is True


def test_mover_cuenta_tras_ingesta_sin_homologation_group(tmp_path_factory, f_homologacion, f_colombia, f_espana):
    """Regresión: el drag&drop debe funcionar tras una ingesta por Excel, donde
    HomologationGroup está vacío (los grupos viven en account_mapping)."""
    for f in (f_homologacion, f_colombia, f_espana):
        if not f.exists():
            pytest.skip("faltan archivos")
    from app.services import config_service
    p = tmp_path_factory.mktemp("mv") / "m.sqlite"
    engine = create_engine(f"sqlite:///{p}", connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    Sx = sessionmaker(bind=engine)
    with Sx() as db:
        ingest_svc.ingest_homologacion(db, str(f_homologacion))
        ingest_svc.ingest_colombia(db, str(f_colombia))
        ingest_svc.ingest_espana(db, str(f_espana))
        grupos = config_service.get_homologacion(db)["grupos"]
        origen = next(g for g in grupos if g["cuentas_co"])
        destino = next(g for g in grupos if g["grupo"] != origen["grupo"] and g["cuentas_co"])
        cuenta = origen["cuentas_co"][0]
        # NO debe lanzar "El grupo destino no existe" (HomologationGroup está vacío)
        res = config_service.mover_cuenta(db, cuenta, "CO", origen["grupo"], destino["grupo"])
        h = {g["grupo"]: g for g in res["grupos"]}
        assert cuenta in h[destino["grupo"]]["cuentas_co"]
        assert cuenta not in h.get(origen["grupo"], {}).get("cuentas_co", [])


def test_homologacion_mover_cuenta(client):
    h = client.get("/api/config/homologacion").json()
    grupos = h["grupos"]
    origen = next((g for g in grupos if g["cuentas_co"]), None)
    destino = next((g for g in grupos if origen and g["grupo"] != origen["grupo"]), None)
    assert origen and destino, "se requieren 2 grupos para mover"
    cuenta = origen["cuentas_co"][0]
    r = client.post("/api/config/homologacion/mover", json={
        "cuenta": cuenta, "pais": "CO",
        "grupo_origen": origen["grupo"], "grupo_destino": destino["grupo"]})
    assert r.status_code == 200, r.text
    h2 = {g["grupo"]: g for g in r.json()["grupos"]}
    assert cuenta not in h2.get(origen["grupo"], {}).get("cuentas_co", [])
    assert cuenta in h2[destino["grupo"]]["cuentas_co"]
    # mover al mismo grupo -> 422
    bad = client.post("/api/config/homologacion/mover", json={
        "cuenta": cuenta, "pais": "CO",
        "grupo_origen": destino["grupo"], "grupo_destino": destino["grupo"]})
    assert bad.status_code == 422
    # cuenta inexistente en origen -> 422
    bad2 = client.post("/api/config/homologacion/mover", json={
        "cuenta": "NO_EXISTE_999", "pais": "CO",
        "grupo_origen": origen["grupo"], "grupo_destino": destino["grupo"]})
    assert bad2.status_code == 422


def test_config_export(client):
    r = client.get("/api/config/homologacion/export")
    assert r.status_code == 200
    assert r.content[:2] == b"PK"  # xlsx es un zip


def test_anomalias(client):
    r = client.get("/api/anomalias")
    assert r.status_code == 200
    d = r.json()
    assert set(d) >= {"sin_homologar", "grupos_atipicos", "kpis"}
    assert isinstance(d["sin_homologar"], list) and isinstance(d["grupos_atipicos"], list)


def test_exports_excel(client):
    for url in ("/api/comparativa/export", "/api/ar-ap/export"):
        r = client.get(url)
        assert r.status_code == 200, url
        assert r.content[:2] == b"PK"


def test_role_admin_co_no_sube_espana(client):
    token_co = create_access_token("colombia@atenea.com", "admin_co")
    r = client.post("/api/ingest/espana", headers={"Authorization": f"Bearer {token_co}"},
                    files={"file": ("x.xlsx", b"dummy")})
    # 403 por rol antes de procesar, o 401 si el usuario no existe en esta DB de test
    assert r.status_code in (401, 403)
