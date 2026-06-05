"""Autenticación JWT y autorización por rol.

Roles (§C):
- 'admin'    : lee y modifica todo (España, Colombia, homologación, cierres).
- 'admin_co' : lee y modifica Colombia; SOLO LECTURA sobre datos de España.

`require_es_write` bloquea a admin_co la escritura sobre datos del libro España.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from jose import JWTError, jwt
from passlib.context import CryptContext
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import get_settings
from db.base import get_db
from db.models import User

settings = get_settings()
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/auth/login")


def hash_password(p: str) -> str:
    return pwd_context.hash(p)


def verify_password(plain: str, hashed: str) -> bool:
    return pwd_context.verify(plain, hashed)


def create_access_token(sub: str, rol: str) -> str:
    expire = datetime.now(timezone.utc) + timedelta(minutes=settings.jwt_expire_minutes)
    payload = {"sub": sub, "rol": rol, "exp": expire}
    return jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)


def get_current_user(token: str = Depends(oauth2_scheme), db: Session = Depends(get_db)) -> User:
    cred_exc = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Credenciales inválidas",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(token, settings.jwt_secret, algorithms=[settings.jwt_algorithm])
        email = payload.get("sub")
        if not email:
            raise cred_exc
    except JWTError:
        raise cred_exc
    user = db.scalar(select(User).where(User.email == email))
    if user is None or not user.activo:
        raise cred_exc
    return user


def require_admin(user: User = Depends(get_current_user)) -> User:
    if user.rol != "admin":
        raise HTTPException(status_code=403, detail="Requiere rol admin")
    return user


def require_es_write(user: User = Depends(get_current_user)) -> User:
    """Permite escribir sobre datos de España. admin_co es solo lectura allí."""
    if user.rol == "admin_co":
        raise HTTPException(
            status_code=403,
            detail="admin_co no puede modificar datos del libro de España (solo lectura)",
        )
    return user
