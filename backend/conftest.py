"""Configuración de pytest: asegura que `backend/` esté en sys.path para
importar `ingestion`, `domain`, etc. como paquetes de primer nivel, y expone
la ruta a los datos de dev/test.
"""
import sys
from pathlib import Path

import pytest

BACKEND_DIR = Path(__file__).resolve().parent
REPO_ROOT = BACKEND_DIR.parent
DATA_DIR = REPO_ROOT / "data"

if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))


@pytest.fixture(scope="session")
def data_dir() -> Path:
    return DATA_DIR


# Rutas canónicas de los archivos de dev/test
@pytest.fixture(scope="session")
def f_homologacion(data_dir) -> Path:
    return data_dir / "homologacion.xlsx"


@pytest.fixture(scope="session")
def f_colombia(data_dir) -> Path:
    return data_dir / "colombia_siesa.xlsx"


@pytest.fixture(scope="session")
def f_espana(data_dir) -> Path:
    return data_dir / "espana_delsol.xlsx"


@pytest.fixture(scope="session")
def f_terceros(data_dir) -> Path:
    return data_dir / "reporte_terceros.xlsx"


@pytest.fixture(scope="session")
def f_bosquejo(data_dir) -> Path:
    return data_dir / "bosquejo_pyg.xlsx"
