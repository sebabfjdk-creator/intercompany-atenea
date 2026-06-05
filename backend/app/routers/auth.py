"""Rutas de autenticación."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from fastapi.security import OAuth2PasswordRequestForm
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth import create_access_token, get_current_user, verify_password
from db.base import get_db
from db.models import User

router = APIRouter(prefix="/api/auth", tags=["auth"])


class TokenOut(BaseModel):
    access_token: str
    token_type: str = "bearer"
    rol: str
    nombre: str


class MeOut(BaseModel):
    email: str
    nombre: str
    rol: str


@router.post("/login", response_model=TokenOut)
def login(form: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)):
    user = db.scalar(select(User).where(User.email == form.username))
    if user is None or not verify_password(form.password, user.hashed_password):
        raise HTTPException(status_code=401, detail="Usuario o contraseña incorrectos")
    token = create_access_token(sub=user.email, rol=user.rol)
    return TokenOut(access_token=token, rol=user.rol, nombre=user.nombre)


@router.get("/me", response_model=MeOut)
def me(user: User = Depends(get_current_user)):
    return MeOut(email=user.email, nombre=user.nombre, rol=user.rol)
