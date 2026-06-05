# Intercompany Atenea — Conciliación Colombia ↔ España

Plataforma web que automatiza la conciliación intercompany entre **Colombia (Siesa)**
y **España (DELSOL)** de Atenea Mobile S.A.S. Son los mismos movimientos en dos libros;
el sistema encuentra, explica y gestiona las diferencias. Lo que hoy toma 10+ días por
rubro, se reduce a minutos, con trazabilidad y auditoría completa.

> Moneda única **COP**. Datos iniciales **Ene–Mar 2026**, ingesta incremental mensual.
> Modelo de saldo **acumulado rolling**.

## Stack

| Capa | Tecnología |
|---|---|
| Backend | Python 3.12, FastAPI, SQLAlchemy 2 + Alembic, pandas + openpyxl |
| BD | PostgreSQL 16 |
| Frontend | React + TypeScript + Vite + Tailwind, Recharts, TanStack Table |
| Auth | JWT + autorización por rol |
| Deploy | Docker + docker-compose · Railway |

## Estructura

```
backend/
  app/         API, config, auth, routers, seed
  ingestion/   adapters: espana.py, colombia.py, terceros.py + utils.py
  domain/      reconciliacion, anomalías, running_balance (Fase 2+)
  db/          models.py, base.py, migrations/ (Alembic)
  tests/       35 tests (utils + parsers contra datos reales)
frontend/      React/Vite (Comparativa, Resumen, Terceros, Excepciones, Auditoría, Config)
data/          5 Excel de dev/test (NO versionados)
```

## Puesta en marcha

### Con Docker (recomendado)
```bash
cp .env.example .env        # ajustar JWT_SECRET
docker compose up --build
# API:  http://localhost:8000/docs
# Web:  http://localhost:5173
```

### Local sin Docker
```bash
# Backend
cd backend
python -m venv .venv && .venv\Scripts\activate   # Windows
pip install -r requirements.txt
pytest -q                                         # 35 tests
uvicorn app.main:app --reload

# Frontend
cd frontend
npm install
npm run dev
```

## Usuarios y roles (§C)

| Usuario (seed) | Rol | Permisos |
|---|---|---|
| `admin@atenea.com` | `admin` | Lee/modifica todo (España, Colombia, homologación, cierres) |
| `colombia@atenea.com` | `admin_co` | Modifica Colombia; **solo lectura** en España |

Contraseñas por defecto en `.env.example` (cambiar en producción).

## Ingesta — detalles validados contra datos reales

- **España (DELSOL, Libro Mayor)**: bloques por cuenta `NNN.N.N.NNN`. Identidad de
  control verificada por cuenta: `Total: = saldo_anterior + Σ movimientos`
  (0 descuadres en Ene y Feb–Mar). `parse_es_number()` tolera formato español
  (`4.500.000,00-`) y numérico nativo.
- **Colombia (Siesa)**: balance jerárquico (nivel por longitud de código). Identidad
  `Saldo actual = Saldo Ant + Débitos − Créditos` (0 descuadres). Movimientos por tercero
  para AR/AP.
- **Puente NIF↔NIT**: `normalizar_nif()` reproduce la columna precalculada en 1.805/1.806
  casos; **525 cruces NIF→NIT** verificados contra los NIT de Colombia.

## Convenciones contables

- `neto = débito − crédito` por movimiento.
- Tolerancia conciliación: `|dif| ≤ $1.000 COP` o `≤ 0,5%` (parametrizable).
- ICBF/SENA: parafiscales sin equivalente en España → causa `parafiscal_co`.

## Estado (roadmap)

- [x] **Fase 0** — Andamiaje (repo, Docker, BD, CI, auth, seed)
- [x] **Fase 1** — Parsers España + Colombia con tests contra datos reales
- [x] **Fase 1b** — Puente terceros NIF↔NIT
- [x] **Fase 2** — Homologación (72 grupos) + motor de conciliación PYG por grupo×periodo
      (decenas de grupos cuadran a <$1; ICBF/SENA → `parafiscal_co`)
- [ ] Wiring API + frontend de los tableros Comparativa/Resumen
- [ ] AR/AP por tercero · Excepciones · Anomalías v1 · Exportación Excel/PDF

> **Nota de validación**: el bosquejo (#5) es una maqueta de formato; sus cifras no
> reconcilian con el consolidado (#3) en Ene–Mar, así que la Fase 2 se valida por
> consistencia interna y por el cuadre real entre los dos libros, no contra el bosquejo.
> El balance de Colombia de Feb–Marzo viene combinado, por lo que el cruce opera con
> periodos `2026-01` y `2026-02-03`.
