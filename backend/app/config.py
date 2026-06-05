"""Configuración central de la app (12-factor). Lee de variables de entorno
y de un archivo .env opcional. En Railway las vars se inyectan automáticamente.
"""
from __future__ import annotations

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # --- App ---
    app_name: str = "Intercompany Atenea"
    environment: str = "development"
    debug: bool = True

    # --- Base de datos ---
    # Railway expone DATABASE_URL. En local usamos el servicio 'db' de docker-compose.
    database_url: str = "postgresql+psycopg://atenea:atenea@db:5432/atenea"

    # --- Auth / JWT ---
    jwt_secret: str = "dev-insecure-change-me"
    jwt_algorithm: str = "HS256"
    jwt_expire_minutes: int = 60 * 12

    # --- Conciliación (parametrizable, §B) ---
    tolerancia_abs_cop: float = 1000.0      # |dif| <= $1.000 COP => conciliado
    tolerancia_pct: float = 0.005           # o <= 0,5% sobre la base mayor

    # --- Fuzzy matching de terceros por concepto (§D) ---
    umbral_match_min: float = 0.65          # por debajo: no se asigna
    umbral_match_alta: float = 0.85
    umbral_match_media: float = 0.70

    @property
    def sync_database_url(self) -> str:
        """URL normalizada. Railway entrega 'postgresql://...'; SQLAlchemy 2.x
        con psycopg 3 requiere el driver explícito 'postgresql+psycopg://'."""
        url = self.database_url
        if url.startswith("postgresql://"):
            url = url.replace("postgresql://", "postgresql+psycopg://", 1)
        return url


@lru_cache
def get_settings() -> Settings:
    return Settings()
