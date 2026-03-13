import re
import uuid
from datetime import datetime, timedelta, timezone
from typing import TYPE_CHECKING

import bcrypt
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from jose import JWTError, jwt
from sqlalchemy.ext.asyncio import AsyncSession

from src.config import settings
from src.models.session import Session
from src.models.user import Role, User, UserStatus
from utils.db import get_db

if TYPE_CHECKING:
    pass

_BCRYPT_ROUNDS = 12
_oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/login")

# -----------------------------------------------------------------
# Password utilities
# -----------------------------------------------------------------

def hash_password(plain: str) -> str:
    return bcrypt.hashpw(plain.encode(), bcrypt.gensalt(rounds=_BCRYPT_ROUNDS)).decode()


def verify_password(plain: str, hashed: str) -> bool:
    return bcrypt.checkpw(plain.encode(), hashed.encode())


def validate_password_complexity(password: str) -> None:
    errors = []
    if len(password) < 10:
        errors.append("at least 10 characters")
    if not re.search(r"[A-Z]", password):
        errors.append("at least one uppercase letter")
    if not re.search(r"\d", password):
        errors.append("at least one digit")
    if not re.search(r"[^A-Za-z0-9]", password):
        errors.append("at least one special character")
    if errors:
        raise HTTPException(
            status_code=422,
            detail={
                "error": f"Password must contain: {', '.join(errors)}",
                "code": "VALIDATION_ERROR",
            },
        )


# -----------------------------------------------------------------
# JWT utilities
# -----------------------------------------------------------------

def create_access_token(data: dict) -> str:
    payload = data.copy()
    expire = datetime.now(timezone.utc) + timedelta(
        minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES
    )
    payload["exp"] = expire
    payload["iat"] = datetime.now(timezone.utc)
    return jwt.encode(payload, settings.SECRET_KEY, algorithm="HS256")


def decode_access_token(token: str) -> dict:
    try:
        return jwt.decode(token, settings.SECRET_KEY, algorithms=["HS256"])
    except JWTError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"error": "Authentication required", "code": "UNAUTHENTICATED"},
            headers={"WWW-Authenticate": "Bearer"},
        )


# -----------------------------------------------------------------
# FastAPI dependencies
# -----------------------------------------------------------------

async def get_current_user(
    token: str = Depends(_oauth2_scheme),
    db: AsyncSession = Depends(get_db),
) -> User:
    payload = decode_access_token(token)

    user_id = payload.get("sub")
    session_id = payload.get("session_id")
    if not user_id or not session_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"error": "Authentication required", "code": "UNAUTHENTICATED"},
        )

    now = datetime.now(timezone.utc)

    session = await db.get(Session, uuid.UUID(session_id))
    if not session or session.revoked or session.expires_at.replace(tzinfo=timezone.utc) < now:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"error": "Session invalid or expired", "code": "SESSION_REVOKED"},
        )

    user = await db.get(User, uuid.UUID(user_id))
    if not user or user.status != UserStatus.ACTIVE:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"error": "Account is not active", "code": "ACCOUNT_DEACTIVATED"},
        )

    return user


def require_role(*roles: Role):
    async def dependency(
        current_user: User = Depends(get_current_user),
    ) -> User:
        if current_user.role not in [r.value for r in roles]:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail={"error": "Insufficient permissions", "code": "FORBIDDEN"},
            )
        return current_user

    return Depends(dependency)
