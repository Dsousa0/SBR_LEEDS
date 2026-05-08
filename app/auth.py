from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import Cookie, Depends
from jose import JWTError, jwt
from passlib.context import CryptContext
from sqlalchemy import text
from sqlalchemy.orm import Session

from config import settings
from database import get_db

ALGORITHM = "HS256"
TOKEN_EXPIRE_HOURS = 8

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


class NotAuthenticatedException(Exception):
    pass


class NotAdminException(Exception):
    pass


def hash_senha(senha: str) -> str:
    return pwd_context.hash(senha)


def verificar_senha(senha: str, hash_: str) -> bool:
    return pwd_context.verify(senha, hash_)


def criar_token(email: str, role: str) -> str:
    expire = datetime.now(timezone.utc) + timedelta(hours=TOKEN_EXPIRE_HOURS)
    return jwt.encode(
        {"sub": email, "role": role, "exp": expire},
        settings.secret_key,
        algorithm=ALGORITHM,
    )


def get_current_user(
    access_token: Optional[str] = Cookie(default=None),
    db: Session = Depends(get_db),
) -> Optional[dict]:
    if not access_token:
        return None
    try:
        payload = jwt.decode(access_token, settings.secret_key, algorithms=[ALGORITHM])
    except JWTError:
        return None
    email = payload.get("sub")
    if not email:
        return None
    row = db.execute(
        text("SELECT id, email, nome, role, ativo FROM usuario WHERE email = :email"),
        {"email": email},
    ).fetchone()
    if not row or not row.ativo:
        return None
    return {"id": str(row.id), "email": row.email, "nome": row.nome, "role": row.role}


def require_login(user: Optional[dict] = Depends(get_current_user)) -> dict:
    if user is None:
        raise NotAuthenticatedException()
    return user


def require_admin(user: dict = Depends(require_login)) -> dict:
    if user["role"] != "admin":
        raise NotAdminException()
    return user
