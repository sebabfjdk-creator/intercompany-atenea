"""Gestión de usuarios: listar, crear, cambiar contraseña y activar/desactivar.

Reglas de rol:
- Solo 'admin' puede listar, crear y desactivar usuarios o cambiar la contraseña de otros.
- Cualquier usuario autenticado puede cambiar SU propia contraseña.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth import get_current_user, hash_password, require_admin, verify_password
from db.base import get_db
from db.models import ROLES, AuditLog, User

router = APIRouter(prefix="/api/users", tags=["users"])


class UserOut(BaseModel):
    id: int
    email: str
    nombre: str
    rol: str
    activo: bool


class UserCreate(BaseModel):
    email: str = Field(min_length=3, max_length=255)
    nombre: str = Field(min_length=1, max_length=120)
    password: str = Field(min_length=4, max_length=200)
    rol: str = "admin_co"


class PasswordChange(BaseModel):
    # actual requerido solo cuando cambias tu propia contraseña
    actual: str | None = None
    nueva: str = Field(min_length=4, max_length=200)


def _to_out(u: User) -> UserOut:
    return UserOut(id=u.id, email=u.email, nombre=u.nombre, rol=u.rol, activo=u.activo)


@router.get("", response_model=list[UserOut])
def listar(db: Session = Depends(get_db), _: User = Depends(require_admin)):
    return [_to_out(u) for u in db.scalars(select(User).order_by(User.id)).all()]


@router.post("", response_model=UserOut, status_code=201)
def crear(body: UserCreate, db: Session = Depends(get_db), admin: User = Depends(require_admin)):
    if body.rol not in ROLES:
        raise HTTPException(400, f"Rol inválido. Use uno de {list(ROLES)}")
    if "@" not in body.email:
        raise HTTPException(400, "Email inválido")
    if db.scalar(select(User).where(User.email == str(body.email))):
        raise HTTPException(409, "Ya existe un usuario con ese email")
    u = User(email=str(body.email), nombre=body.nombre,
             hashed_password=hash_password(body.password), rol=body.rol, activo=True)
    db.add(u)
    db.flush()
    db.add(AuditLog(entidad="user", entidad_id=str(u.id), accion="create",
                    valor_despues=f"{u.email} ({u.rol})", usuario_id=admin.id))
    db.commit()
    db.refresh(u)
    return _to_out(u)


@router.patch("/{user_id}/password", response_model=UserOut)
def cambiar_password(user_id: int, body: PasswordChange,
                     db: Session = Depends(get_db), actor: User = Depends(get_current_user)):
    objetivo = db.get(User, user_id)
    if not objetivo:
        raise HTTPException(404, "Usuario no encontrado")
    es_propia = actor.id == user_id
    if not es_propia and actor.rol != "admin":
        raise HTTPException(403, "Solo un admin puede cambiar la contraseña de otros usuarios")
    if es_propia:
        if not body.actual or not verify_password(body.actual, objetivo.hashed_password):
            raise HTTPException(400, "La contraseña actual no es correcta")
    objetivo.hashed_password = hash_password(body.nueva)
    db.add(AuditLog(entidad="user", entidad_id=str(objetivo.id), accion="update",
                    valor_despues="cambio de contraseña", usuario_id=actor.id))
    db.commit()
    db.refresh(objetivo)
    return _to_out(objetivo)


@router.patch("/{user_id}/activo", response_model=UserOut)
def set_activo(user_id: int, activo: bool, db: Session = Depends(get_db), admin: User = Depends(require_admin)):
    u = db.get(User, user_id)
    if not u:
        raise HTTPException(404, "Usuario no encontrado")
    if u.id == admin.id and not activo:
        raise HTTPException(400, "No puedes desactivarte a ti mismo")
    u.activo = activo
    db.add(AuditLog(entidad="user", entidad_id=str(u.id), accion="update",
                    valor_despues=f"activo={activo}", usuario_id=admin.id))
    db.commit()
    db.refresh(u)
    return _to_out(u)
