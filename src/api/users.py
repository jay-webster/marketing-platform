import hashlib
import secrets
import uuid
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, EmailStr
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from src.config import settings
from src.models.invitation import Invitation, InvitationStatus
from src.models.session import Session
from src.models.user import Role, User, UserStatus
from utils.audit import write_audit
from utils.auth import get_current_user, require_role
from utils.db import get_db
from utils.email import send_invitation_email

router = APIRouter(prefix="/users", tags=["users"])


# -----------------------------------------------------------------
# Helpers
# -----------------------------------------------------------------

def _request_id(request: Request) -> str:
    return getattr(request.state, "request_id", "unknown")


def _hash_token(raw: str) -> str:
    return hashlib.sha256(raw.encode()).hexdigest()


def _user_dict(user: User) -> dict:
    return {
        "id": str(user.id),
        "email": user.email,
        "display_name": user.display_name,
        "role": user.role,
        "status": user.status,
        "created_at": user.created_at.isoformat() if user.created_at else None,
    }


async def _admin_count(db: AsyncSession) -> int:
    result = await db.execute(
        select(User).where(
            User.role == Role.ADMIN.value,
            User.status == UserStatus.ACTIVE.value,
        )
    )
    return len(result.scalars().all())


# -----------------------------------------------------------------
# Schemas
# -----------------------------------------------------------------

class InviteRequest(BaseModel):
    email: EmailStr
    role: str


class ChangeRoleRequest(BaseModel):
    role: str


# -----------------------------------------------------------------
# GET /users/me  (must be before /{user_id} routes)
# -----------------------------------------------------------------

@router.get("/me")
async def get_me(
    request: Request,
    current_user: User = Depends(get_current_user),
):
    return {"data": _user_dict(current_user), "request_id": _request_id(request)}


# -----------------------------------------------------------------
# GET /users
# -----------------------------------------------------------------

@router.get("")
async def list_users(
    request: Request,
    status_filter: str = "active",
    role: str | None = None,
    current_user: User = require_role(Role.ADMIN, Role.MARKETING_MANAGER),
    db: AsyncSession = Depends(get_db),
):
    stmt = select(User)
    if status_filter != "all":
        stmt = stmt.where(User.status == status_filter)
    if role:
        stmt = stmt.where(User.role == role)

    result = await db.execute(stmt)
    users = result.scalars().all()
    return {
        "data": [_user_dict(u) for u in users],
        "request_id": _request_id(request),
    }


# -----------------------------------------------------------------
# POST /users/invite
# -----------------------------------------------------------------

@router.post("/invite", status_code=status.HTTP_201_CREATED)
async def invite_user(
    body: InviteRequest,
    request: Request,
    current_user: User = require_role(Role.ADMIN),
    db: AsyncSession = Depends(get_db),
):
    if body.role == Role.ADMIN.value:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"error": "Cannot invite a user with the admin role", "code": "INVALID_ROLE"},
        )
    if body.role not in [Role.MARKETING_MANAGER.value, Role.MARKETER.value]:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"error": "Invalid role", "code": "INVALID_ROLE"},
        )

    # Check for existing user
    existing = await db.execute(
        select(User).where(User.email == body.email.lower())
    )
    if existing.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"error": "A user with this email already exists", "code": "USER_ALREADY_EXISTS"},
        )

    # Expire any pending invitations for this email
    await db.execute(
        update(Invitation)
        .where(
            Invitation.invited_email == body.email.lower(),
            Invitation.status == InvitationStatus.PENDING.value,
        )
        .values(status=InvitationStatus.EXPIRED.value)
    )

    now = datetime.now(timezone.utc)
    raw_token = secrets.token_urlsafe(32)
    token_hash = _hash_token(raw_token)

    invitation = Invitation(
        invited_email=body.email.lower(),
        assigned_role=body.role,
        issued_by=current_user.id,
        token_hash=token_hash,
        expires_at=now + timedelta(hours=72),
        status=InvitationStatus.PENDING.value,
    )
    db.add(invitation)
    await db.flush()

    link = f"{settings.APP_URL}/accept-invitation?token={raw_token}"
    await send_invitation_email(body.email, body.role, link)

    await write_audit(
        db, "invitation_sent",
        actor_id=current_user.id,
        metadata={"invited_email": body.email, "assigned_role": body.role},
    )
    await db.commit()
    await db.refresh(invitation)

    return {
        "data": {
            "id": str(invitation.id),
            "invited_email": invitation.invited_email,
            "assigned_role": invitation.assigned_role,
            "expires_at": invitation.expires_at.isoformat(),
            "status": invitation.status,
        },
        "request_id": _request_id(request),
    }


# -----------------------------------------------------------------
# POST /users/invitations/{invitation_id}/resend
# -----------------------------------------------------------------

@router.post("/invitations/{invitation_id}/resend")
async def resend_invitation(
    invitation_id: uuid.UUID,
    request: Request,
    current_user: User = require_role(Role.ADMIN),
    db: AsyncSession = Depends(get_db),
):
    invitation = await db.get(Invitation, invitation_id)
    if not invitation:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"error": "Invitation not found", "code": "INVITATION_NOT_FOUND"},
        )
    if invitation.status == InvitationStatus.ACCEPTED.value:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"error": "Invitation has already been accepted", "code": "INVITATION_ALREADY_ACCEPTED"},
        )

    # Expire current invitation
    invitation.status = InvitationStatus.EXPIRED.value

    now = datetime.now(timezone.utc)
    raw_token = secrets.token_urlsafe(32)
    token_hash = _hash_token(raw_token)

    new_invitation = Invitation(
        invited_email=invitation.invited_email,
        assigned_role=invitation.assigned_role,
        issued_by=current_user.id,
        token_hash=token_hash,
        expires_at=now + timedelta(hours=72),
        status=InvitationStatus.PENDING.value,
    )
    db.add(new_invitation)
    await db.flush()

    link = f"{settings.APP_URL}/accept-invitation?token={raw_token}"
    await send_invitation_email(invitation.invited_email, invitation.assigned_role, link)

    await write_audit(
        db, "invitation_resent",
        actor_id=current_user.id,
        metadata={"invited_email": invitation.invited_email},
    )
    await db.commit()
    await db.refresh(new_invitation)

    return {
        "data": {
            "id": str(new_invitation.id),
            "invited_email": new_invitation.invited_email,
            "assigned_role": new_invitation.assigned_role,
            "expires_at": new_invitation.expires_at.isoformat(),
            "status": new_invitation.status,
        },
        "request_id": _request_id(request),
    }


# -----------------------------------------------------------------
# PATCH /users/{user_id}/role
# -----------------------------------------------------------------

@router.patch("/{user_id}/role")
async def change_role(
    user_id: uuid.UUID,
    body: ChangeRoleRequest,
    request: Request,
    current_user: User = require_role(Role.ADMIN),
    db: AsyncSession = Depends(get_db),
):
    if user_id == current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={"error": "Cannot change your own role", "code": "CANNOT_CHANGE_OWN_ROLE"},
        )

    valid_roles = [r.value for r in Role]
    if body.role not in valid_roles:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"error": "Invalid role", "code": "INVALID_ROLE"},
        )

    user = await db.get(User, user_id)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"error": "User not found", "code": "USER_NOT_FOUND"},
        )

    # Last admin guard — if changing away from admin
    if user.role == Role.ADMIN.value and body.role != Role.ADMIN.value:
        if await _admin_count(db) <= 1:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail={"error": "Cannot demote the last admin", "code": "LAST_ADMIN"},
            )

    old_role = user.role
    user.role = body.role

    await write_audit(
        db, "role_changed",
        actor_id=current_user.id,
        target_id=user.id,
        metadata={"old_role": old_role, "new_role": body.role},
    )
    await db.commit()
    await db.refresh(user)

    return {
        "data": {
            "id": str(user.id),
            "email": user.email,
            "display_name": user.display_name,
            "role": user.role,
            "status": user.status,
        },
        "request_id": _request_id(request),
    }


# -----------------------------------------------------------------
# POST /users/{user_id}/revoke
# -----------------------------------------------------------------

@router.post("/{user_id}/revoke")
async def revoke_user(
    user_id: uuid.UUID,
    request: Request,
    current_user: User = require_role(Role.ADMIN),
    db: AsyncSession = Depends(get_db),
):
    if user_id == current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={"error": "Cannot revoke your own access", "code": "CANNOT_REVOKE_SELF"},
        )

    user = await db.get(User, user_id)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"error": "User not found", "code": "USER_NOT_FOUND"},
        )
    if user.status == UserStatus.DEACTIVATED.value:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"error": "User is already deactivated", "code": "USER_ALREADY_DEACTIVATED"},
        )

    # Last admin guard
    if user.role == Role.ADMIN.value:
        if await _admin_count(db) <= 1:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail={"error": "Cannot revoke the last admin", "code": "LAST_ADMIN"},
            )

    now = datetime.now(timezone.utc)
    user.status = UserStatus.DEACTIVATED.value
    user.deactivated_at = now

    # Revoke all active sessions for this user
    await db.execute(
        update(Session)
        .where(Session.user_id == user_id, Session.revoked == False)
        .values(revoked=True, revoked_at=now)
    )

    await write_audit(
        db, "access_revoked",
        actor_id=current_user.id,
        target_id=user.id,
    )
    await db.commit()

    return {
        "data": {
            "id": str(user.id),
            "status": user.status,
            "deactivated_at": user.deactivated_at.isoformat(),
        },
        "request_id": _request_id(request),
    }


# -----------------------------------------------------------------
# POST /users/{user_id}/reactivate
# -----------------------------------------------------------------

@router.post("/{user_id}/reactivate")
async def reactivate_user(
    user_id: uuid.UUID,
    request: Request,
    current_user: User = require_role(Role.ADMIN),
    db: AsyncSession = Depends(get_db),
):
    user = await db.get(User, user_id)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"error": "User not found", "code": "USER_NOT_FOUND"},
        )
    if user.status == UserStatus.ACTIVE.value:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"error": "User is already active", "code": "USER_ALREADY_ACTIVE"},
        )

    user.status = UserStatus.ACTIVE.value
    user.deactivated_at = None

    await write_audit(
        db, "user_reactivated",
        actor_id=current_user.id,
        target_id=user.id,
    )
    await db.commit()

    return {
        "data": {"id": str(user.id), "status": user.status},
        "request_id": _request_id(request),
    }
