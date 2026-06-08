"""Modelo de datos (§E del prompt) en SQLAlchemy 2.0.

Convenciones contables clave:
- `neto = debe - haber` por movimiento. La normalización por naturaleza de clase
  (ingresos/pasivos en crédito, gastos/activos en débito) se aplica en el motor
  de conciliación, no aquí.
- Todos los importes en COP (Numeric(20,2)). No hay multimoneda.
- `audit_log` es append-only.
"""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from db.base import Base

# ------------------------------------------------------------------ constantes

ROLES = ("admin", "admin_co")  # admin = España+todo ; admin_co = CO write, ES read-only
PAISES = ("CO", "ES")
ESTADOS_RECON = ("conciliado", "excepcion", "en_revision", "aprobado", "con_observacion")
CAUSAS_EXCEPCION = (
    "redondeo",
    "timing",
    "parafiscal_co",
    "diferencia_nif",
    "error_imputacion",
    "sin_homologar",
    "pendiente_libro_diario",
)
CONFIANZA = ("alta", "media", "baja")


# ------------------------------------------------------------------ usuarios

class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    nombre: Mapped[str] = mapped_column(String(120))
    hashed_password: Mapped[str] = mapped_column(String(255))
    rol: Mapped[str] = mapped_column(String(20), default="admin_co")
    activo: Mapped[bool] = mapped_column(Boolean, default=True)
    creado: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


# ------------------------------------------------------------------ catálogo

class SourceSystem(Base):
    __tablename__ = "source_system"

    id: Mapped[int] = mapped_column(primary_key=True)
    nombre: Mapped[str] = mapped_column(String(80))         # 'Siesa', 'DELSOL'
    pais: Mapped[str] = mapped_column(String(2))            # 'CO' | 'ES'
    tipo_formato: Mapped[str] = mapped_column(String(40))   # 'siesa_xlsx' | 'delsol_mayor'


class Account(Base):
    __tablename__ = "account"
    __table_args__ = (UniqueConstraint("sistema_id", "codigo", name="uq_account_sis_cod"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    codigo: Mapped[str] = mapped_column(String(40), index=True)
    nombre: Mapped[str] = mapped_column(String(255), default="")
    sistema_id: Mapped[int] = mapped_column(ForeignKey("source_system.id"))
    tipo: Mapped[str] = mapped_column(String(20), default="")  # gasto|ingreso|cliente|proveedor|balance
    nivel: Mapped[int] = mapped_column(Integer, default=0)     # jerarquía CO por longitud de código


class AccountMapping(Base):
    """Homologación CO <-> ES, editable desde la app."""
    __tablename__ = "account_mapping"

    id: Mapped[int] = mapped_column(primary_key=True)
    cuenta_co_patron: Mapped[str] = mapped_column(String(40), default="")  # patrón o código CO
    cuenta_es: Mapped[str] = mapped_column(String(40), default="")
    grupo_homologado: Mapped[str] = mapped_column(String(120), index=True)
    tipo_relacion: Mapped[str] = mapped_column(String(20), default="directa")  # directa|grupo|n_a_n
    confianza: Mapped[str] = mapped_column(String(10), default="alta")
    activo: Mapped[bool] = mapped_column(Boolean, default=True)


class TerceroBridge(Base):
    """Puente NIF(ES) <-> NIT(CO). Fuente de verdad para AR/AP y etiquetado."""
    __tablename__ = "tercero_bridge"
    __table_args__ = (
        Index("ix_tercero_nif_norm", "nif_normalizado"),
        Index("ix_tercero_nit_co", "nit_colombia"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    cuenta_es: Mapped[str] = mapped_column(String(40), default="")
    nombre_fiscal: Mapped[str] = mapped_column(String(255), default="")
    nif_normalizado: Mapped[str] = mapped_column(String(40), default="")
    tipo_nif: Mapped[str] = mapped_column(String(40), default="")
    nit_colombia: Mapped[str] = mapped_column(String(40), default="")
    tipo: Mapped[str] = mapped_column(String(20), default="")  # cliente|proveedor
    activo: Mapped[bool] = mapped_column(Boolean, default=True)


# ------------------------------------------------------------------ ingesta

class ImportBatch(Base):
    __tablename__ = "import_batch"
    __table_args__ = (
        UniqueConstraint("sistema_id", "periodo_mes", "archivo_hash", name="uq_batch_idem"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    sistema_id: Mapped[int] = mapped_column(ForeignKey("source_system.id"))
    periodo_mes: Mapped[str] = mapped_column(String(7), index=True)  # 'YYYY-MM'
    fecha_carga: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    usuario_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    archivo_hash: Mapped[str] = mapped_column(String(64))  # sha256, idempotencia
    estado: Mapped[str] = mapped_column(String(20), default="cargado")  # cargado|cerrado|error

    entries: Mapped[list["JournalEntry"]] = relationship(back_populates="batch")


class JournalEntry(Base):
    __tablename__ = "journal_entry"
    __table_args__ = (
        Index("ix_je_cuenta_periodo", "cuenta_id", "periodo_mes"),
        Index("ix_je_periodo", "periodo_mes"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    batch_id: Mapped[int] = mapped_column(ForeignKey("import_batch.id"))
    cuenta_id: Mapped[int] = mapped_column(ForeignKey("account.id"))
    tercero_nit: Mapped[str] = mapped_column(String(40), default="", index=True)
    fecha: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    debe: Mapped[float] = mapped_column(Numeric(20, 2), default=0)
    haber: Mapped[float] = mapped_column(Numeric(20, 2), default=0)
    neto: Mapped[float] = mapped_column(Numeric(20, 2), default=0)  # debe - haber
    concepto: Mapped[str] = mapped_column(Text, default="")
    referencia: Mapped[str] = mapped_column(String(120), default="")
    periodo_mes: Mapped[str] = mapped_column(String(7), index=True)

    # --- atribución vía puente de terceros (§D) ---
    nit_co: Mapped[str] = mapped_column(String(40), default="", index=True)
    conf_tercero: Mapped[str | None] = mapped_column(String(10), nullable=True)  # alta|media|baja
    cuenta_es_origen: Mapped[str] = mapped_column(String(40), default="")

    batch: Mapped["ImportBatch"] = relationship(back_populates="entries")


# ------------------------------------------------------------------ conciliación

class ReconciliationGroup(Base):
    __tablename__ = "reconciliation_group"
    __table_args__ = (
        UniqueConstraint("grupo_homologado", "periodo_mes", name="uq_recon_grupo_periodo"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    grupo_homologado: Mapped[str] = mapped_column(String(120), index=True)
    periodo_mes: Mapped[str] = mapped_column(String(7), index=True)
    total_co: Mapped[float] = mapped_column(Numeric(20, 2), default=0)
    total_es: Mapped[float] = mapped_column(Numeric(20, 2), default=0)
    diferencia: Mapped[float] = mapped_column(Numeric(20, 2), default=0)
    pct_dif: Mapped[float] = mapped_column(Numeric(10, 6), default=0)
    estado: Mapped[str] = mapped_column(String(20), default="en_revision")
    umbral_aplicado: Mapped[str] = mapped_column(String(40), default="")


class RunningBalance(Base):
    __tablename__ = "running_balance"
    __table_args__ = (
        UniqueConstraint("grupo_homologado", "periodo_mes", name="uq_rb_grupo_periodo"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    grupo_homologado: Mapped[str] = mapped_column(String(120), index=True)
    periodo_mes: Mapped[str] = mapped_column(String(7), index=True)
    saldo_acumulado_co: Mapped[float] = mapped_column(Numeric(20, 2), default=0)
    saldo_acumulado_es: Mapped[float] = mapped_column(Numeric(20, 2), default=0)
    dif_acumulada: Mapped[float] = mapped_column(Numeric(20, 2), default=0)


class Exception_(Base):
    __tablename__ = "exception"

    id: Mapped[int] = mapped_column(primary_key=True)
    reconciliation_id: Mapped[int] = mapped_column(ForeignKey("reconciliation_group.id"))
    causa: Mapped[str] = mapped_column(String(40))
    comentario: Mapped[str] = mapped_column(Text, default="")
    etiqueta: Mapped[str] = mapped_column(String(80), default="")
    usuario_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    ts: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Approval(Base):
    __tablename__ = "approval"

    id: Mapped[int] = mapped_column(primary_key=True)
    reconciliation_id: Mapped[int] = mapped_column(ForeignKey("reconciliation_group.id"))
    estado: Mapped[str] = mapped_column(String(20), default="pendiente")
    usuario_revisor: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    usuario_aprobador: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    ts_revision: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    ts_aprobacion: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class AuditLog(Base):
    """Append-only. Nunca update/delete."""
    __tablename__ = "audit_log"

    id: Mapped[int] = mapped_column(primary_key=True)
    entidad: Mapped[str] = mapped_column(String(60))
    entidad_id: Mapped[str] = mapped_column(String(40), default="")
    accion: Mapped[str] = mapped_column(String(20))  # create|update|delete|close
    valor_antes: Mapped[str | None] = mapped_column(Text, nullable=True)
    valor_despues: Mapped[str | None] = mapped_column(Text, nullable=True)
    usuario_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    ts: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class AccountPeriod(Base):
    """Cifras agregadas por cuenta × periodo, uniformes para CO y ES.
    Alimenta el motor de conciliación PYG sin re-parsear Excel en cada consulta.
    pais: 'CO' | 'ES'. periodo: 'YYYY-MM' o rango '2026-02-03'.
    """
    __tablename__ = "account_period"
    __table_args__ = (
        UniqueConstraint("pais", "codigo", "periodo", name="uq_acctperiod"),
        Index("ix_acctperiod_periodo", "periodo"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    pais: Mapped[str] = mapped_column(String(2), index=True)
    codigo: Mapped[str] = mapped_column(String(40), index=True)
    nombre: Mapped[str] = mapped_column(String(255), default="")
    periodo: Mapped[str] = mapped_column(String(10))
    debe: Mapped[float] = mapped_column(Numeric(20, 2), default=0)
    haber: Mapped[float] = mapped_column(Numeric(20, 2), default=0)


class ArApBalance(Base):
    """Saldos por tercero para conciliación AR/AP (Cuentas por Cobrar y Pagar).

    pais: CO|ES · tipo: AR|AP. Para ES, `nit` se resuelve vía tercero_bridge en la
    ingesta (las cuentas provisionales amarillas quedan con nit='' y es_provisional).
    Para CO se guardan los componentes 1305/2805 (o 22xx) y el saldo neto.
    """
    __tablename__ = "arap_balance"
    __table_args__ = (Index("ix_arap_pais_tipo_nit", "pais", "tipo", "nit"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    pais: Mapped[str] = mapped_column(String(2), index=True)
    tipo: Mapped[str] = mapped_column(String(2))                # AR | AP
    nit: Mapped[str] = mapped_column(String(40), default="", index=True)
    cuenta: Mapped[str] = mapped_column(String(60), default="")  # cuenta_es o '1305/2805'
    nombre: Mapped[str] = mapped_column(String(255), default="")
    saldo: Mapped[float] = mapped_column(Numeric(20, 2), default=0)        # saldo neto
    saldo_a: Mapped[float] = mapped_column(Numeric(20, 2), default=0)      # CO: 1305 ; ES: n/a
    saldo_b: Mapped[float] = mapped_column(Numeric(20, 2), default=0)      # CO: 2805 ; ES: n/a
    es_provisional: Mapped[bool] = mapped_column(Boolean, default=False)
    error_contab: Mapped[bool] = mapped_column(Boolean, default=False)
    periodo: Mapped[str] = mapped_column(String(10), default="2026-Q1")


class HomologationGroup(Base):
    """Metadatos editables de cada grupo homologado (tipo y relación).
    Las cuentas viven en account_mapping (grupo_homologado == nombre)."""
    __tablename__ = "homologation_group"

    id: Mapped[int] = mapped_column(primary_key=True)
    nombre: Mapped[str] = mapped_column(String(120), unique=True, index=True)
    tipo: Mapped[str] = mapped_column(String(20), default="gasto")  # gasto|ingreso|activo|pasivo
    tipo_relacion: Mapped[str] = mapped_column(String(20), default="directa")
    activo: Mapped[bool] = mapped_column(Boolean, default=True)


class AppConfig(Base):
    """Configuración clave-valor editable desde la app (p.ej. tolerancias)."""
    __tablename__ = "app_config"

    clave: Mapped[str] = mapped_column(String(60), primary_key=True)
    valor: Mapped[str] = mapped_column(String(120), default="")


class PygMovimiento(Base):
    """Movimientos individuales PYG por cuenta (trazabilidad Grupo→Cuenta→Transacción).
    ES desde el Libro Mayor DELSOL; CO desde las hojas Mvto_* de Siesa.
    """
    __tablename__ = "pyg_movimiento"
    __table_args__ = (Index("ix_pygmov_pais_cod_per", "pais", "codigo", "periodo"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    pais: Mapped[str] = mapped_column(String(2), index=True)
    codigo: Mapped[str] = mapped_column(String(40), index=True)
    periodo: Mapped[str] = mapped_column(String(10))
    fecha: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    concepto: Mapped[str] = mapped_column(Text, default="")
    debe: Mapped[float] = mapped_column(Numeric(20, 2), default=0)
    haber: Mapped[float] = mapped_column(Numeric(20, 2), default=0)


class ArApMovimiento(Base):
    """Movimientos individuales AR/AP por tercero (para detalle 'Ver más' y filtros de fecha)."""
    __tablename__ = "arap_movimiento"
    __table_args__ = (Index("ix_arapmov_pais_nit", "pais", "nit"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    pais: Mapped[str] = mapped_column(String(2), index=True)
    tipo: Mapped[str] = mapped_column(String(2))                # AR | AP
    nit: Mapped[str] = mapped_column(String(40), default="", index=True)
    cuenta: Mapped[str] = mapped_column(String(40), default="")
    fecha: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    concepto: Mapped[str] = mapped_column(Text, default="")
    debe: Mapped[float] = mapped_column(Numeric(20, 2), default=0)
    haber: Mapped[float] = mapped_column(Numeric(20, 2), default=0)
    saldo: Mapped[float] = mapped_column(Numeric(20, 2), default=0)
