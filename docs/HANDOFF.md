# HANDOFF — Intercompany Atenea
> Documento de transferencia para continuar el desarrollo en una nueva sesión sin pérdida de contexto.
> Última actualización: 2026-06-08 · Commit de referencia: `c5ba153` · 67 tests en verde.

---

## 1. RESUMEN EJECUTIVO DEL PROYECTO

- **Objetivo**: plataforma web que automatiza la **conciliación intercompany** entre **Colombia (Siesa)** y **España (DELSOL)** de **Atenea Mobile S.A.S.** Son los mismos movimientos en dos libros; el sistema encuentra, explica y gestiona las diferencias.
- **Problema de negocio**: hoy la conciliación es manual (10+ días por rubro). Meta: minutos, con trazabilidad y auditoría completas — del estado financiero hasta el asiento que origina una diferencia.
- **Usuarios objetivo**: responsable España (rol `admin`), responsable Colombia (rol `admin_co`, solo lectura en España), financiero (rol `admin`). Perfil: contadores, auditores, revisores fiscales.
- **Estado actual**: **MVP avanzado, desplegado y operativo en producción (Railway)**. Moneda única COP. Datos Ene–Mar 2026 (ingesta incremental mensual).

### Funcionalidades terminadas (todas en producción)
- Ingesta por upload de Excel (PYG España/Colombia, homologación, terceros, AR/AP CO/ES).
- **Comparativa PYG** con drill-down de 3 niveles: Grupo → Cuenta → Transacción.
- **Resumen** por gran rubro.
- **Excepciones** (diferencias > tolerancia, causa sugerida).
- **Anomalías v1** (cuentas sin homologar + grupos atípicos por z-score).
- **AR/AP** completo: conciliación por tercero, vista 360 (resumen ejecutivo, movimientos con documento/tipo, línea de tiempo, análisis automático, matching documental CO↔ES), KPIs, errores contables, cuentas provisionales.
- **Homologación editable** desde la app (crear/editar/eliminar grupos, tags de cuentas, tolerancias).
- **Gestión de usuarios** (crear, cambiar contraseña, activar/desactivar).
- **Auditoría** (log inmutable).
- **Export a Excel** en todas las páginas.
- Auth JWT con roles. Sidebar con acordeón "Configuración".

### Funcionalidades en progreso
- Ninguna a medias; cada feature está commiteada y desplegada.

### Funcionalidades pendientes
- **Workflow de aprobaciones** (revisión → aprobación de excepciones). Tablas `exception`/`approval` ya existen pero **no expuestas**. ← Siguiente mejora grande.
- Export **PDF**.
- **z-score temporal por cuenta** (requiere ≥3 periodos; hoy solo Ene + Feb-Mar).
- Filtro por cuenta en Excepciones.
- Migración Alembic real (hoy `create_all` + mini-migraciones).
- AR/AP por tercero a nivel de saldos por subcuenta CO más granular.

---

## 2. ARQUITECTURA GENERAL

- **Backend**: Python 3.12, **FastAPI**, **SQLAlchemy 2.0**, pandas + openpyxl (parsers), python-jose (JWT), **bcrypt directo** (NO passlib), uvicorn.
- **Frontend**: **React 18 + TypeScript + Vite 6 + TailwindCSS**, Recharts (gráficos), axios, react-router-dom. **Zero-dependency** en split-pane y date-picker (CSS grid + inputs nativos).
- **Base de datos**: **PostgreSQL 16** (Railway).
- **APIs**: REST bajo `/api/*`, JSON. Auth Bearer JWT.
- **Servicios** (capa `app/services/`): `ingest` (PYG), `arap_service` (AR/AP), `queries` (lecturas/tableros PYG), `config_service` (homologación/tolerancias).
- **Integraciones**: ninguna externa; ingesta por archivos Excel subidos por el usuario.
- **Flujo de datos**: Excel → parser (`ingestion/*`) → BD (tablas `account_period`, `account_mapping`, `tercero_bridge`, `arap_balance`, `arap_movimiento`, `pyg_movimiento`) → servicios calculan **en vivo** (motor `domain/reconciliacion.py`) → endpoints JSON → frontend. **No hay tablas de resultados persistidas**: la conciliación se recalcula en cada request (por eso editar homologación/tolerancia se refleja al instante).

### Estructura de carpetas
```
backend/
  app/
    main.py            # FastAPI, registra routers
    config.py          # Settings (env): DATABASE_URL, JWT, tolerancias
    auth.py            # JWT + bcrypt directo + roles
    seed.py            # create_all + mini-migración + usuarios/sources
    routers/           # auth, health, data, ingest, users, arap
    services/          # ingest, queries, config_service, arap_service
  ingestion/           # utils, espana, colombia, terceros, homologacion, arap
  domain/reconciliacion.py   # motor de cruce (normalización, wildcard, causa)
  db/                  # base.py, models.py, migrations/ (Alembic cableado, no usado)
  tests/               # 67 tests
  Dockerfile           # backend (también hay Dockerfile raíz, ver §9)
  requirements.txt
frontend/
  src/
    main.tsx           # router
    api.ts             # axios + descargarArchivo (export autenticado)
    lib/               # format, daterange, useFetch
    components/ui.tsx  # PageHeader, Kpi, Card, DataState, badges
    pages/             # Login, Layout, Dashboard, Comparativa, Resumen,
                       # Excepciones, Anomalias, ArAp, Ingesta, Auditoria,
                       # Usuarios, Config, Parametros
  Dockerfile           # multi-stage build + nginx en $PORT
  nginx.conf.template  # SPA fallback
  railway.json         # builder DOCKERFILE
data/                  # 5 Excel + cartera_pasivos.xlsx (NO versionados)
railway.json           # raíz (builder DOCKERFILE backend)
docs/HANDOFF.md        # este documento
```

---

## 3. MODELO DE NEGOCIO Y REGLAS CONTABLES

- **Moneda**: todo COP. Si un archivo ES dice "Euros" es etiqueta incorrecta; sin TRM.
- **Normalización de signo por naturaleza de clase**:
  - Ingreso (CO clase **4** / ES clase **7**) → `crédito − débito` (haber − debe).
  - Gasto/resto (CO clase **5** / ES clase **6**) → `débito − crédito`.
- **Diferencia** = `total_CO − total_ES` por grupo×periodo.
- **Tolerancia** (editable, tabla `app_config`): `|dif| ≤ $1.000 COP` **o** `≤ 0,5%` sobre la base mayor → conciliado.
- **Homologación**: grupos que asocian cuentas CO ↔ ES. Soporta **wildcard** `642.0.0.x` (agrupa subcuentas por prefijo). Hoja Gastos = pares N:N por bloques; hoja Ingresos = bloques CO/ES.
- **España (DELSOL Libro Mayor)**: bloques por cuenta `NNN.N.N.NNN`. Identidad de control por subcuenta: **`Total:` = saldo_anterior + Σ movimientos**. (NO usar `Total de cuenta:`, que agrega el grupo padre.) Enero numérico nativo; **Feb-Marzo formato español** `4.500.000,00-` → `parse_es_number`.
- **Colombia (Siesa)**: balance jerárquico (nivel por longitud de código), identidad `Saldo actual = Saldo Ant + Débitos − Créditos`. En `Mvto_Enero` débito/crédito = 0 (arrastre, el dato está en saldo); `Mvto_Febrero-Marzo` trae movimiento real.
- **AR/AP**:
  - ES: **430** clientes (AR), **410** proveedores (AP). Saldo por tercero = columna Saldo de la fila `Total:` de cada subcuenta. Cuentas **amarillas (relleno FFFFFF00)** = provisionales "FACTURAS PEND. EMITIR" → `es_provisional=True`, **no cruzan**.
  - CO: **1305** clientes, **2805** anticipos/saldo a favor, **22xx** proveedores. `saldo_neto_co = 1305 + 2805`. Saldo por tercero = fila resumen sin Referencia (en Excel, fuente azul `FF000080`).
  - **Negativo en 1305** → `error_contabilizacion` (debería reclasificarse a 2805).
- **Tipo de documento** (por prefijo): FA/FE/FV→Factura, NC/NCA→Nota crédito, ND→Nota débito, RC→Recibo/Pago, CL→Pago, PR→Provisión, resto→Otro.
- **Causas de excepción**: redondeo, timing, **parafiscal_co** (ICBF/SENA, sin equivalente en España), diferencia_nif, error_imputación, sin_homologar.

---

## 4. MOTOR DE CONCILIACIÓN

`backend/domain/reconciliacion.py`:
- `valor_periodo(pais, codigo, debe, haber)`: normaliza a naturaleza positiva por clase.
- `cruzar_pyg_periodos(grupos, filas_account_period, tol_abs, tol_pct)`: indexa CO y ES por periodo, suma por grupo (con `_suma_codigos` que expande **wildcards** `x/*`), calcula diferencia, % y estado.
- `causa_sugerida(resultado)`: heurística (parafiscal_co, sin_homologar, redondeo, timing).
- `running_balance(resultados)`: saldo acumulado rolling por grupo.

**AR/AP** (`app/services/arap_service.py`):
- `reconciliacion()`: **emparejamiento explícito** por tercero:
  1. **Por NIT** (`co_by_nit[(tipo,nit)]`).
  2. **Fallback por nombre** (`_norm_nombre`: sin acentos/puntuación, sin formas legales SAS/SLU/SL/LTDA, ≥5 chars) → para entidades ES con NIF de letra sin NIT colombiano.
  3. CO/ES sin contraparte → SIN_MATCH.
  - Campo `matched_por` ∈ {nit, nombre, None}. Estados: CONCILIADO / DIFERENCIA / ERROR_CO / SIN_MATCH.
- `tercero_360()`: resumen ejecutivo (estado, antigüedad por días desde último mov, mes origen), movimientos CO/ES, timeline, análisis automático por reglas, matching documental.
- `matching_documental(mov_co, mov_es)`: cruza por **nº documento normalizado** (`PR3516`↔`PR-3516`) + valor → confianza **95** (doc+valor), **80** (doc), **60** (solo valor).
- `kpis_arap()`: abiertas/conciliadas/>90 días/top 20 terceros/top cuentas.

### Casos problemáticos y soluciones
- ES Feb-Mar en texto español → `parse_es_number` tolera ambos.
- CO PYG Enero sin desglose por tercero (arrastre) → movimientos solo Feb-Marzo.
- Entidades ES con NIF letra (NET REAL SOLUTIONS) → **cruce por nombre** (36 cruces logrados).
- Wildcards en homologación → `_suma_codigos`.

---

## 5. CASOS REALES IMPORTANTES DESCUBIERTOS

| # | Problema | Causa raíz | Solución | Impacto | Lección |
|---|---|---|---|---|---|
| 1 | Bosquejo (#5) no reconcilia con consolidado (#3) Ene-Mar | El bosquejo es **maqueta de formato**, datos de otra cosecha | Validar por consistencia interna + cuadre real entre libros, no contra el bosquejo | Evitó "perseguir" números falsos | No asumir que un mock-up es oráculo numérico |
| 2 | `NET REAL SOLUTIONS SLU` (NIF B12550877) → SIN_MATCH | Entidad española intercompany, sin NIT colombiano | **Cruce por nombre** (`_norm_nombre`) | ~$2.9–3.6B dejaron de quedar sin conciliar | Las entidades intercompany cruzan por razón social |
| 3 | Deploy 502 en frontend | Railway usaba **Nixpacks** (corría `vite dev` en 5173) ignorando el Dockerfile | `frontend/railway.json` + Dockerfile nginx en `$PORT` | Frontend caído | Forzar builder DOCKERFILE en monorepos |
| 4 | Commits no se desplegaban | **Auto-deploy desconectado**; "Redeploy" repite el commit activo (no el último) | Reconectar Source / `railway up` desde **raíz** | Confusión repetida | "Redeploy" ≠ "Deploy latest commit" |
| 5 | `railway up` os error 5 | Se corría desde `C:\Users\sebas` (home), no del proyecto | `cd` al proyecto antes de `railway up` | Upload fallido | `railway up` siempre desde la raíz del repo |
| 6 | Re-ingesta rompía (UniqueViolation `uq_batch_idem`) | `import_batch` no idempotente | `_record_batch` ahora hace skip-if-exists | Re-subir mismo archivo | Ingesta debe ser idempotente |
| 7 | Crash bcrypt "password > 72 bytes" | passlib 1.7.4 incompatible con bcrypt 4.x | **bcrypt directo** + truncado 72 bytes | Login caído | No usar passlib con bcrypt 4.x |
| 8 | ICBF/SENA siempre con diferencia | Parafiscales propios de Colombia | Causa `parafiscal_co` | Diferencia estructural esperada | Documentar diferencias estructurales |
| 9 | Errores 1305<0 (GAVIRIA, AUTOLUX) | Saldo negativo en cuenta de cliente | Flag `error_contabilizacion` + pestaña Errores | Reclasificar a 2805 | Validar naturaleza de cuenta |

---

## 6. BASE DE DATOS

Tablas (SQLAlchemy `backend/db/models.py`):
- **users** (id, email, nombre, hashed_password, rol[admin|admin_co], activo).
- **source_system**, **account**, **account_mapping** (cuenta_co_patron, cuenta_es, grupo_homologado, tipo_relacion, activo).
- **tercero_bridge** (cuenta_es, nombre_fiscal, nif_normalizado, nit_colombia, tipo) — puente NIF↔NIT (1806 filas).
- **import_batch** (sistema_id, periodo_mes, archivo_hash, estado) — UNIQUE(sistema_id, periodo_mes, archivo_hash) `uq_batch_idem`.
- **account_period** (pais, codigo, nombre, periodo, debe, haber) — agregados PYG por cuenta×periodo. UNIQUE(pais,codigo,periodo).
- **homologation_group** (nombre UNIQUE, tipo[gasto|ingreso|activo|pasivo], tipo_relacion, activo) — metadatos editables de grupos.
- **app_config** (clave PK, valor) — tolerancias editables.
- **arap_balance** (pais, tipo[AR|AP], nit, cuenta, nombre, saldo, saldo_a=1305, saldo_b=2805, es_provisional, error_contab).
- **arap_movimiento** (pais, tipo, nit, cuenta, fecha, concepto, **documento**, **tipo_documento**, debe, haber, saldo).
- **pyg_movimiento** (pais, codigo, periodo, fecha, concepto, debe, haber) — movimientos PYG individuales.
- Tablas existentes NO usadas aún: **journal_entry**, **reconciliation_group**, **running_balance**, **exception**, **approval**, **audit_log** (audit_log SÍ se usa).
- **Índices**: en (pais,codigo,periodo), (pais,nit), nit, documento, etc.
- **Restricción clave**: `uq_batch_idem`.
- **Mejoras pendientes**: migrar de `create_all` + mini-migraciones a Alembic versionado; usar `reconciliation_group`/`approval` para el workflow.

---

## 7. ENDPOINTS Y SERVICIOS

**Auth**: `POST /api/auth/login`, `GET /api/auth/me`
**Health**: `GET /api/health`, `GET /api/ready`
**Datos PYG / config**:
- `GET /api/estado-datos`
- `GET /api/comparativa` · `GET /api/comparativa/export` · `GET /api/comparativa/detalle-grupo?grupo=` · `GET /api/comparativa/movimientos-cuenta?pais&cuenta&periodo`
- `GET /api/resumen` · `/api/resumen/export`
- `GET /api/excepciones` · `/api/excepciones/export`
- `GET /api/terceros` · `/api/terceros/export`
- `GET /api/anomalias`
- `GET /api/auditoria`
- `GET/PUT /api/config/homologacion` · `GET /api/config/homologacion/export` · `PUT /api/config/tolerancia` · `POST /api/config/recalcular`
**Ingesta**: `POST /api/ingest/{espana|colombia|homologacion|terceros}` · `POST /api/ingest/auto/detect` · `POST /api/ingest/ar-ap/{colombia|espana}`
**Usuarios**: `GET/POST /api/users` · `PATCH /api/users/{id}/password` · `PATCH /api/users/{id}/activo`
**AR/AP**: `GET /api/ar-ap/estado-datos` · `/comparativa` · `/tercero/{nit}` · `/kpis` · `/export` · `/excepciones` · `/errores` · `/cuentas-amarillas` · `/movimientos-tercero?nit&desde&hasta`

**Servicios críticos**: `ingest.py` (PYG + idempotencia), `arap_service.py` (motor AR/AP + 360 + matching + KPIs), `queries.py` (tableros PYG + anomalías + detalle/movimientos), `config_service.py` (homologación/tolerancias). **Dependencias**: queries→config_service→models; arap_service→config_service; routers→services.

---

## 8. ARCHIVOS MÁS IMPORTANTES

| Archivo | Propósito | Criticidad |
|---|---|---|
| `domain/reconciliacion.py` | Motor de cruce PYG + wildcard + causa | 🔴 Crítica |
| `app/services/arap_service.py` | Motor AR/AP, 360, matching, KPIs, cruce por nombre | 🔴 Crítica |
| `app/services/queries.py` | Tableros PYG, detalle-grupo, movimientos-cuenta, anomalías | 🔴 Crítica |
| `app/services/ingest.py` | Ingesta PYG + idempotencia + movimientos | 🔴 Crítica |
| `app/services/config_service.py` | Homologación editable + tolerancias | 🟠 Alta |
| `ingestion/espana.py`, `colombia.py`, `arap.py`, `terceros.py`, `homologacion.py` | Parsers Excel | 🟠 Alta |
| `db/models.py` | Esquema completo | 🔴 Crítica |
| `app/auth.py` | JWT + bcrypt + roles | 🟠 Alta |
| `app/seed.py` | Bootstrap + mini-migraciones | 🟠 Alta |
| `frontend/src/pages/ArAp.tsx` | Conciliación + vista 360 + KPIs | 🟠 Alta |
| `frontend/src/pages/Comparativa.tsx` | Drill-down 3 niveles | 🟠 Alta |
| `frontend/src/api.ts` | axios + descarga autenticada | 🟠 Alta |
| `frontend/src/pages/Layout.tsx` | Sidebar con acordeón | 🟡 Media |

---

## 9. DESPLIEGUE

- **Railway**, proyecto **`capable-empathy`**, entorno **`production`**. Workspace: `sebabfjdk-creator's Projects`.
- **Servicios**: `intercompany-atenea` (backend, Root Directory `backend/`, usa `backend/Dockerfile`), `intercompany-atenea-frontend` (Root Directory `frontend/`, usa `frontend/Dockerfile` nginx multi-stage en `$PORT`), `Postgres`.
- **URLs**: backend `https://intercompany-atenea-production.up.railway.app` · frontend `https://intercompany-atenea-frontend-production.up.railway.app`.
- **Repo GitHub**: `sebabfjdk-creator/intercompany-atenea` (público), branch `main`.
- **Variables de entorno**: `DATABASE_URL` (Railway la inyecta), `JWT_SECRET`, `SEED_ADMIN_*`, `SEED_ADMINCO_*`, `SEED_USER3_*`, `PORT` (auto). `config.py` normaliza `postgresql://`→`postgresql+psycopg://`.
- **Esquema**: al arrancar, `app.seed` corre `create_all` + mini-migraciones Postgres (`ALTER TABLE arap_movimiento ADD COLUMN IF NOT EXISTS documento/tipo_documento`) + seed de usuarios.
- **Usuarios seed**: `admin@atenea.com`/`atenea-admin` (admin), `colombia@atenea.com`/`atenea-co` (admin_co), `financiero@atenea.com`/`atenea-fin` (admin).
- **Procedimiento de despliegue (CLI Railway, instalado v5.5)**:
  ```
  cd <raíz del repo>            # SIEMPRE desde la raíz, NO desde subcarpeta ni home
  railway link                 # capable-empathy → production → <servicio>
  railway up                   # backend o frontend según el servicio linkeado
  ```
  Tras cambios de ingesta, **re-ingestar** los Excel vía API (httpx multipart con el venv) para poblar tablas nuevas.
- **Riesgos conocidos**: auto-deploy intermitente (verificar Settings→Source→Enable); `railway up` falla con "os error 5" si se corre desde fuera del proyecto; subir datos financieros solo por la app (no versionar `data/`).

---

## 10. ERRORES Y PROBLEMAS ABIERTOS

| Bug/limitación | Impacto | Prioridad | Posible solución |
|---|---|---|---|
| CO PYG Enero sin movimientos por tercero | Drill-down Enero muestra solo nivel cuenta | Media | Limitación del archivo Siesa; documentar |
| z-score temporal inactivo (2 periodos) | Anomalías solo transversal | Baja | Se activa solo con ≥3 meses |
| Auto-deploy Railway intermitente | Requiere `railway up` manual | Media | Confirmar/activar auto-deploy + Connect Repo frontend |
| Bosquejo no reconcilia | No es bug; aclarar con negocio | Baja | Confirmar si hay extracto que coincida |
| Alembic no usado (create_all + ALTERs) | Riesgo en cambios de esquema | Media | Migrar a Alembic versionado |
| Discrepancia signo en algunos rubros timing | Diferencias esperadas | Baja | Workflow de excepciones |

No hay bugs que rompan funcionalidad actual; 67 tests en verde.

---

## 11. BACKLOG PRIORIZADO

**Alta**
- **Workflow de aprobaciones** (excepción: en_revisión→aprobada, con usuario/fecha, comentario, causa). Tablas `exception`/`approval` ya existen. Es lo que cierra el ciclo de gestión de diferencias.
- Confirmar **auto-deploy** Railway (backend + Connect Repo frontend) para eliminar fricción de despliegue.

**Media**
- Migración **Alembic** real (reemplazar create_all + mini-migraciones).
- **Export PDF** de Comparativa/Resumen/360.
- Filtro por cuenta en Excepciones; enlace desde Comparativa.
- Persistir resultados (`reconciliation_group`, `running_balance`) para histórico y velocidad.

**Baja**
- z-score temporal por cuenta (cuando haya ≥3 periodos).
- Refinar segmentación fina de Ingresos vs bosquejo.
- Code-splitting del bundle (Recharts pesa).
- Tests de frontend.

Justificación: Alta = cierra valor de negocio (gestión de diferencias) y estabilidad de despliegue; Media = robustez técnica y entregables a auditores; Baja = depende de más datos o es cosmético.

---

## 12. PRÓXIMOS PASOS RECOMENDADOS

1. **Workflow de aprobaciones** (fase siguiente):
   - Backend: endpoints `POST /api/excepciones/{id}/revisar|aprobar`, comentario y causa; persistir en `exception`/`approval` con usuario/timestamp; registrar en `audit_log`.
   - Frontend: en Excepciones/AR-AP, acciones "Marcar en revisión" / "Aprobar" con badge de estado y filtro por estado.
2. **Migración Alembic**: generar migración inicial desde el modelo actual; reemplazar el `ALTER IF NOT EXISTS` de seed.
3. **Export PDF** (reusar datos de los endpoints export; usar una lib de PDF server-side).
4. **Confirmar auto-deploy** y documentar el pipeline.
5. (Cuando lleguen más meses) activar z-score temporal y comparativas multi-mes.

---

## 13. CONTEXTO INICIAL PARA NUEVA CONVERSACIÓN

> **Proyecto**: Intercompany Atenea — plataforma de conciliación intercompany **Colombia (Siesa) ↔ España (DELSOL)** de Atenea Mobile S.A.S. Stack: **FastAPI + SQLAlchemy2 + PostgreSQL** (backend), **React+TS+Vite+Tailwind** (frontend), desplegado en **Railway** (Docker). Moneda COP. Datos Ene–Mar 2026.
>
> **Repo local**: `C:\Users\sebas\OneDrive\Escritorio\Cloude\Programa de automatizacion\Intercompany_Atenea` · GitHub `sebabfjdk-creator/intercompany-atenea` (branch main). Backend prod: `https://intercompany-atenea-production.up.railway.app` · Frontend: `https://intercompany-atenea-frontend-production.up.railway.app`. Login admin: `admin@atenea.com` / `atenea-admin`.
>
> **Entorno Windows**: Python real en `backend\.venv\Scripts\python.exe` (el `python` del PATH es el stub de Microsoft Store, NO funciona). Tests: `& "backend\.venv\Scripts\python.exe" -m pytest backend\tests -q` (67 en verde). Frontend: `cd frontend; npm run build`. Consola cp1252 → fijar `$env:PYTHONIOENCODING="utf-8"`. Desplegar: `cd` a la RAÍZ → `railway link` → `railway up` (CLI v5.5 instalado).
>
> **Ya construido** (todo en prod): ingesta por upload; Comparativa PYG con drill-down Grupo→Cuenta→Transacción; Resumen; Excepciones; Anomalías v1; AR/AP completo (conciliación por tercero + vista 360 con resumen/timeline/análisis/matching documental + KPIs + errores + provisionales); cruce por NIT y **por nombre** (entidades ES sin NIT); homologación editable; usuarios; auditoría; export Excel; sidebar con acordeón.
>
> **Prioridad actual / qué falta**: **workflow de aprobaciones** de excepciones (tablas `exception`/`approval` existen, no expuestas). Luego: Alembic real, export PDF, filtro por cuenta en Excepciones, z-score temporal (cuando haya ≥3 meses).
>
> **Archivos a revisar primero**: `backend/domain/reconciliacion.py`, `backend/app/services/arap_service.py`, `backend/app/services/queries.py`, `backend/db/models.py`, `frontend/src/pages/ArAp.tsx`, `frontend/src/pages/Comparativa.tsx`, y la memoria del proyecto en `~/.claude/projects/.../memory/` (`estado-proyecto.md`, `datos-formato-hallazgos.md`, `toolchain-entorno.md`).
>
> **Reglas clave**: normalización de signo por clase (ingreso=crédito−débito, gasto=débito−crédito); tolerancia $1.000 COP / 0,5% (editable); ES identidad `Total: = anterior + Σmov`; CO identidad `Saldo = Ant + Déb − Créd`; AR/AP ES 430/410 + amarillas provisionales, CO 1305+2805/22xx, negativo 1305 = error; matching documental por nº doc normalizado + valor (95/80/60); usar **bcrypt directo** (no passlib); `railway up` SIEMPRE desde la raíz; ingesta idempotente.
