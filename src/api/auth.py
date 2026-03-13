import hashlib
import secrets
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from pydantic import BaseModel, EmailStr
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from src.config import settings
from src.models.invitation import Invitation, InvitationStatus
from src.models.session import Session
from src.models.user import Role, User, UserStatus
from utils.audit import write_audit
from utils.auth import (
    create_access_token,
    get_current_user,
    hash_password,
    validate_password_complexity,
    verify_password,
)
from utils.db import get_db

router = APIRouter(prefix="/auth", tags=["auth"])

REFRESH_COOKIE = "refresh_token"
REFRESH_COOKIE_PATH = "/api/v1/auth/refresh"


# -----------------------------------------------------------------
# Helpers
# -----------------------------------------------------------------

def _request_id(request: Request) -> str:
    return getattr(request.state, "request_id", "unknown")


def _hash_token(raw: str) -> str:
    return hashlib.sha256(raw.encode()).hexdigest()


def _set_refresh_cookie(response: Response, raw_token: str) -> None:
    response.set_cookie(
        key=REFRESH_COOKIE,
        value=raw_token,
        httponly=True,
        secure=True,
        samesite="strict",
        path=REFRESH_COOKIE_PATH,
        max_age=settings.REFRESH_TOKEN_EXPIRE_DAYS * 24 * 3600,
    )


def _clear_refresh_cookie(response: Response) -> None:
    response.delete_cookie(key=REFRESH_COOKIE, path=REFRESH_COOKIE_PATH)


def _user_dict(user: User) -> dict:
    return {
        "id": str(user.id),
        "email": user.email,
        "display_name": user.display_name,
        "role": user.role,
        "status": user.status,
        "created_at": user.created_at.isoformat() if user.created_at else None,
    }


# -----------------------------------------------------------------
# Request / Response schemas
# -----------------------------------------------------------------

class RegisterRequest(BaseModel):
    email: EmailStr
    display_name: str
    password: str


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class AcceptInvitationRequest(BaseModel):
    token: str
    display_name: str
    password: str


# -----------------------------------------------------------------
# POST /auth/register
# -----------------------------------------------------------------

@router.post("/register", status_code=status.HTTP_201_CREATED)
async def register(
    body: RegisterRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    setup_token = request.headers.get("X-Setup-Token", "")
    if not settings.INITIAL_ADMIN_TOKEN or setup_token != settings.INITIAL_ADMIN_TOKEN:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={"error": "Invalid or missing setup token", "code": "SETUP_TOKEN_INVALID"},
        )

    existing = await db.execute(
        select(User).where(User.role == Role.ADMIN.value).limit(1)
    )
    if existing.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"error": "An admin user already exists", "code": "ADMIN_ALREADY_EXISTS"},
        )

    validate_password_complexity(body.password)

    user = User(
        email=body.email.lower(),
        display_name=body.display_name,
        password_hash=hash_password(body.password),
        role=Role.ADMIN.value,
        status=UserStatus.ACTIVE.value,
    )
    db.add(user)
    await db.flush()  # get the generated id

    await write_audit(db, "user_registered", actor_id=user.id, metadata={"role": "admin"})
    await db.commit()
    await db.refresh(user)

    return {
        "data": {
            "id": str(user.id),
            "email": user.email,
            "display_name": user.display_name,
            "role": user.role,
        },
        "request_id": _request_id(request),
    }


# -----------------------------------------------------------------
# POST /auth/login
# -----------------------------------------------------------------

@router.post("/login")
async def login(
    body: LoginRequest,
    request: Request,
    response: Response,
    db: AsyncSession = Depends(get_db),
):
    now = datetime.now(timezone.utc)

    result = await db.execute(
        select(User).where(User.email == body.email.lower())
    )
    user = result.scalar_one_or_none()

    # Generic credential failure — same message for unknown email
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"error": "Invalid credentials", "code": "INVALID_CREDENTIALS"},
        )

    if user.status == UserStatus.DEACTIVATED.value:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"error": "Account has been deactivated", "code": "ACCOUNT_DEACTIVATED"},
        )

    # Lockout check
    if user.locked_until and user.locked_until.replace(tzinfo=timezone.utc) > now:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail={
                "error": "Account is temporarily locked",
                "code": "ACCOUNT_LOCKED",
                "locked_until": user.locked_until.isoformat(),
            },
        )

    if not verify_password(body.password, user.password_hash):
        user.failed_login_count += 1
        if user.failed_login_count >= 5:
            user.locked_until = now + timedelta(minutes=15)
            await write_audit(
                db, "user_locked", target_id=user.id,
                metadata={"locked_until": user.locked_until.isoformat()}
            )
            await db.commit()
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail={
                    "error": "Account is temporarily locked after too many failed attempts",
                    "code": "ACCOUNT_LOCKED",
                    "locked_until": user.locked_until.isoformat(),
                },
            )
        await write_audit(
            db, "user_login_failed",
            metadata={"email": user.email, "reason": "wrong_password"}
        )
        await db.commit()
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"error": "Invalid credentials", "code": "INVALID_CREDENTIALS"},
        )

    # Success — reset counter
    user.failed_login_count = 0
    user.locked_until = None

    raw_refresh = secrets.token_urlsafe(64)
    session = Session(
        user_id=user.id,
        refresh_token_hash=_hash_token(raw_refresh),
        expires_at=now + timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS),
        last_active_at=now,
    )
    db.add(session)
    await db.flush()

    access_token = create_access_token({
        "sub": str(user.id),
        "email": user.email,
        "role": user.role,
        "session_id": str(session.id),
    })

    await write_audit(db, "user_login", actor_id=user.id)
    await db.commit()

    _set_refresh_cookie(response, raw_refresh)

    return {
        "data": {
            "access_token": access_token,
            "token_type": "bearer",
            "expires_in": settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
            "user": _user_dict(user),
        },
        "request_id": _request_id(request),
    }


# -----------------------------------------------------------------
# POST /auth/logout
# -----------------------------------------------------------------

@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(
    request: Request,
    response: Response,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    from jose import jwt as _jwt
    from fastapi.security import OAuth2PasswordBearer
    auth_header = request.headers.get("Authorization", "")
    token = auth_header.removeprefix("Bearer ").strip()

    try:
        payload = _jwt.decode(token, settings.SECRET_KEY, algorithms=["HS256"])
        session_id = payload.get("session_id")
        if session_id:
            import uuid as _uuid
            session = await db.get(Session, _uuid.UUID(session_id))
            if session:
                now = datetime.now(timezone.utc)
                session.revoked = True
                session.revoked_at = now
                await write_audit(
                    db, "user_logout",
                    actor_id=current_user.id,
                    metadata={"session_id": session_id}
                )
                await db.commit()
    except Exception:
        pass

    _clear_refresh_cookie(response)


# -----------------------------------------------------------------
# POST /auth/refresh
# -----------------------------------------------------------------

@router.post("/refresh")
async def refresh_token(
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    raw_refresh = request.cookies.get(REFRESH_COOKIE)
    if not raw_refresh:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"error": "Refresh token missing", "code": "REFRESH_TOKEN_INVALID"},
        )

    token_hash = _hash_token(raw_refresh)
    result = await db.execute(
        select(Session).where(Session.refresh_token_hash == token_hash)
    )
    session = result.scalar_one_or_none()

    now = datetime.now(timezone.utc)
    if not session:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"error": "Invalid refresh token", "code": "REFRESH_TOKEN_INVALID"},
        )
    if session.revoked:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"error": "Session has been revoked", "code": "SESSION_REVOKED"},
        )
    if session.expires_at.replace(tzinfo=timezone.utc) < now:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"error": "Refresh token has expired", "code": "REFRESH_TOKEN_INVALID"},
        )

    user = await db.get(User, session.user_id)
    if not user or user.status != UserStatus.ACTIVE.value:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"error": "Account is not active", "code": "ACCOUNT_DEACTIVATED"},
        )

    session.last_active_at = now
    await db.commit()

    access_token = create_access_token({
        "sub": str(user.id),
        "email": user.email,
        "role": user.role,
        "session_id": str(session.id),
    })

    return {
        "data": {
            "access_token": access_token,
            "token_type": "bearer",
            "expires_in": settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        },
        "request_id": _request_id(request),
    }


# -----------------------------------------------------------------
# POST /auth/accept-invitation
# -----------------------------------------------------------------

@router.post("/accept-invitation", status_code=status.HTTP_201_CREATED)
async def accept_invitation(
    body: AcceptInvitationRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    token_hash = _hash_token(body.token)
    result = await db.execute(
        select(Invitation).where(Invitation.token_hash == token_hash)
    )
    invitation = result.scalar_one_or_none()

    if not invitation:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"error": "Invitation not found", "code": "INVITATION_NOT_FOUND"},
        )

    now = datetime.now(timezone.utc)

    if invitation.status == InvitationStatus.ACCEPTED.value:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"error": "Invitation has already been used", "code": "INVITATION_ALREADY_USED"},
        )

    if (
        invitation.status == InvitationStatus.EXPIRED.value
        or invitation.expires_at.replace(tzinfo=timezone.utc) < now
    ):
        raise HTTPException(
            status_code=status.HTTP_410_GONE,
            detail={"error": "Invitation has expired", "code": "INVITATION_EXPIRED"},
        )

    validate_password_complexity(body.password)

    user = User(
        email=invitation.invited_email.lower(),
        display_name=body.display_name,
        password_hash=hash_password(body.password),
        role=invitation.assigned_role,
        status=UserStatus.ACTIVE.value,
    )
    db.add(user)
    await db.flush()

    invitation.status = InvitationStatus.ACCEPTED.value

    await write_audit(
        db, "invitation_accepted",
        actor_id=user.id,
        metadata={"invited_email": invitation.invited_email, "role": invitation.assigned_role},
    )
    await db.commit()
    await db.refresh(user)

    return {
        "data": {
            "id": str(user.id),
            "email": user.email,
            "display_name": user.display_name,
            "role": user.role,
        },
        "request_id": _request_id(request),
    }
