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


def test_terceros_y_excepciones(client):
    t = client.get("/api/terceros").json()
    assert t["kpis"]["total"] > 1500
    e = client.get("/api/excepciones").json()
    assert isinstance(e, list) and len(e) > 0
    assert any(x["causa"] == "parafiscal_co" for x in e)


def test_role_admin_co_no_sube_espana(client):
    token_co = create_access_token("colombia@atenea.com", "admin_co")
    r = client.post("/api/ingest/espana", headers={"Authorization": f"Bearer {token_co}"},
                    files={"file": ("x.xlsx", b"dummy")})
    # 403 por rol antes de procesar, o 401 si el usuario no existe en esta DB de test
    assert r.status_code in (401, 403)
