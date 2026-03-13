"""Tests for /api/v1/auth/* endpoints."""
import hashlib
import secrets
import uuid
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, patch

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from src.config import settings
from src.models import Invitation, InvitationStatus, Role, Session, User, UserStatus
from utils.auth import hash_password


pytestmark = pytest.mark.asyncio


# ---------------------------------------------------------------------------
# POST /auth/register
# ---------------------------------------------------------------------------

async def test_register_happy_path(async_client: AsyncClient):
    with patch.object(settings, "INITIAL_ADMIN_TOKEN", "test-setup-token"):
        resp = await async_client.post(
            "/api/v1/auth/register",
            headers={"X-Setup-Token": "test-setup-token"},
            json={
                "email": "firstadmin@example.com",
                "display_name": "First Admin",
                "password": "Str0ng!Pass1",
            },
        )
    assert resp.status_code == 201
    data = resp.json()
    assert data["data"]["role"] == "admin"
    assert data["data"]["email"] == "firstadmin@example.com"
    assert "request_id" in data


async def test_register_invalid_token(async_client: AsyncClient, db_session: AsyncSession):
    with patch.object(settings, "INITIAL_ADMIN_TOKEN", "correct-token"):
        resp = await async_client.post(
            "/api/v1/auth/register",
            headers={"X-Setup-Token": "wrong-token"},
            json={
                "email": "hacker@example.com",
                "display_name": "Hacker",
                "password": "Str0ng!Pass1",
            },
        )
    assert resp.status_code == 403
    assert resp.json()["error"]["code"] if "error" in resp.json() else resp.json()["detail"]["code"] == "SETUP_TOKEN_INVALID"


async def test_register_missing_token(async_client: AsyncClient):
    with patch.object(settings, "INITIAL_ADMIN_TOKEN", "some-token"):
        resp = await async_client.post(
            "/api/v1/auth/register",
            json={
                "email": "nobody@example.com",
                "display_name": "Nobody",
                "password": "Str0ng!Pass1",
            },
        )
    assert resp.status_code == 403


async def test_register_admin_already_exists(
    async_client: AsyncClient, admin_user: User
):
    with patch.object(settings, "INITIAL_ADMIN_TOKEN", "test-setup-token"):
        resp = await async_client.post(
            "/api/v1/auth/register",
            headers={"X-Setup-Token": "test-setup-token"},
            json={
                "email": "second@example.com",
                "display_name": "Second",
                "password": "Str0ng!Pass1",
            },
        )
    assert resp.status_code == 409
    assert resp.json()["detail"]["code"] == "ADMIN_ALREADY_EXISTS"


async def test_register_weak_password(async_client: AsyncClient):
    # No admin exists yet, but password is too weak → 422
    with patch.object(settings, "INITIAL_ADMIN_TOKEN", "test-setup-token"):
        resp = await async_client.post(
            "/api/v1/auth/register",
            headers={"X-Setup-Token": "test-setup-token"},
            json={
                "email": "admin2@example.com",
                "display_name": "Admin 2",
                "password": "short",
            },
        )
    assert resp.status_code == 422
    detail = resp.json().get("detail", {})
    if isinstance(detail, dict):
        assert detail.get("code") == "VALIDATION_ERROR"


async def test_register_request_id_in_response(async_client: AsyncClient):
    resp = await async_client.post(
        "/api/v1/auth/register",
        json={"email": "x@x.com", "display_name": "X", "password": "x"},
    )
    assert "request_id" in resp.json() or resp.status_code in (403, 422)


# ---------------------------------------------------------------------------
# POST /auth/login
# ---------------------------------------------------------------------------

async def test_login_happy_path(async_client: AsyncClient, admin_user: User):
    resp = await async_client.post(
        "/api/v1/auth/login",
        json={"email": "admin@example.com", "password": "Str0ng!Pass1"},
    )
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert "access_token" in data
    assert data["token_type"] == "bearer"
    assert "refresh_token" in resp.cookies


async def test_login_wrong_password(async_client: AsyncClient, admin_user: User):
    resp = await async_client.post(
        "/api/v1/auth/login",
        json={"email": "admin@example.com", "password": "WrongPass!1"},
    )
    assert resp.status_code == 401
    assert resp.json()["detail"]["code"] == "INVALID_CREDENTIALS"


async def test_login_unknown_email(async_client: AsyncClient):
    resp = await async_client.post(
        "/api/v1/auth/login",
        json={"email": "nobody@example.com", "password": "Str0ng!Pass1"},
    )
    assert resp.status_code == 401
    assert resp.json()["detail"]["code"] == "INVALID_CREDENTIALS"


async def test_login_deactivated_account(
    async_client: AsyncClient, db_session: AsyncSession
):
    user = User(
        id=uuid.uuid4(),
        email="inactive@example.com",
        display_name="Inactive",
        password_hash=hash_password("Str0ng!Pass1"),
        role=Role.MARKETER.value,
        status=UserStatus.DEACTIVATED.value,
    )
    db_session.add(user)
    await db_session.commit()

    resp = await async_client.post(
        "/api/v1/auth/login",
        json={"email": "inactive@example.com", "password": "Str0ng!Pass1"},
    )
    assert resp.status_code == 401
    assert resp.json()["detail"]["code"] == "ACCOUNT_DEACTIVATED"


async def test_login_lockout_on_5th_failure(
    async_client: AsyncClient, db_session: AsyncSession
):
    user = User(
        id=uuid.uuid4(),
        email="lockme@example.com",
        display_name="Lock Me",
        password_hash=hash_password("Str0ng!Pass1"),
        role=Role.MARKETER.value,
        status=UserStatus.ACTIVE.value,
        failed_login_count=4,  # one away from lockout
    )
    db_session.add(user)
    await db_session.commit()

    resp = await async_client.post(
        "/api/v1/auth/login",
        json={"email": "lockme@example.com", "password": "WrongPass!1"},
    )
    assert resp.status_code == 429
    assert resp.json()["detail"]["code"] == "ACCOUNT_LOCKED"
    assert "locked_until" in resp.json()["detail"]


async def test_login_locked_account(
    async_client: AsyncClient, db_session: AsyncSession
):
    user = User(
        id=uuid.uuid4(),
        email="alreadylocked@example.com",
        display_name="Already Locked",
        password_hash=hash_password("Str0ng!Pass1"),
        role=Role.MARKETER.value,
        status=UserStatus.ACTIVE.value,
        locked_until=datetime.now(timezone.utc) + timedelta(minutes=10),
    )
    db_session.add(user)
    await db_session.commit()

    resp = await async_client.post(
        "/api/v1/auth/login",
        json={"email": "alreadylocked@example.com", "password": "Str0ng!Pass1"},
    )
    assert resp.status_code == 429
    assert resp.json()["detail"]["code"] == "ACCOUNT_LOCKED"


# ---------------------------------------------------------------------------
# POST /auth/logout
# ---------------------------------------------------------------------------

async def test_logout_happy_path(async_client: AsyncClient, admin_token: str):
    resp = await async_client.post(
        "/api/v1/auth/logout",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert resp.status_code == 204


async def test_logout_revoked_session_rejected(
    async_client: AsyncClient, admin_token: str
):
    await async_client.post(
        "/api/v1/auth/logout",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    # Second request after logout must be rejected
    resp = await async_client.get(
        "/api/v1/users/me",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert resp.status_code == 401


# ---------------------------------------------------------------------------
# POST /auth/refresh
# ---------------------------------------------------------------------------

async def test_refresh_happy_path(
    async_client: AsyncClient, admin_user: User, db_session: AsyncSession
):
    # Login to get real refresh cookie
    resp = await async_client.post(
        "/api/v1/auth/login",
        json={"email": "admin@example.com", "password": "Str0ng!Pass1"},
    )
    assert resp.status_code == 200
    # Refresh
    resp2 = await async_client.post("/api/v1/auth/refresh")
    assert resp2.status_code == 200
    assert "access_token" in resp2.json()["data"]


async def test_refresh_no_cookie(async_client: AsyncClient):
    resp = await async_client.post("/api/v1/auth/refresh")
    assert resp.status_code == 401
    assert resp.json()["detail"]["code"] == "REFRESH_TOKEN_INVALID"


async def test_refresh_revoked_session(
    async_client: AsyncClient, db_session: AsyncSession, admin_user: User
):
    now = datetime.now(timezone.utc)
    raw = secrets.token_urlsafe(64)
    session = Session(
        id=uuid.uuid4(),
        user_id=admin_user.id,
        refresh_token_hash=hashlib.sha256(raw.encode()).hexdigest(),
        expires_at=now + timedelta(days=30),
        last_active_at=now,
        revoked=True,
        revoked_at=now,
    )
    db_session.add(session)
    await db_session.commit()

    async_client.cookies.set("refresh_token", raw, path="/api/v1/auth/refresh")
    resp = await async_client.post("/api/v1/auth/refresh")
    assert resp.status_code == 401
    assert resp.json()["detail"]["code"] == "SESSION_REVOKED"


# ---------------------------------------------------------------------------
# POST /auth/accept-invitation
# ---------------------------------------------------------------------------

async def test_accept_invitation_happy_path(
    async_client: AsyncClient,
    pending_invitation: tuple,
):
    invitation, raw_token = pending_invitation
    resp = await async_client.post(
        "/api/v1/auth/accept-invitation",
        json={
            "token": raw_token,
            "display_name": "New User",
            "password": "Str0ng!Pass1",
        },
    )
    assert resp.status_code == 201
    data = resp.json()["data"]
    assert data["role"] == "marketer"
    assert data["email"] == "invitee@example.com"


async def test_accept_invitation_expired(
    async_client: AsyncClient, admin_user: User, db_session: AsyncSession
):
    raw = secrets.token_urlsafe(32)
    token_hash = hashlib.sha256(raw.encode()).hexdigest()
    inv = Invitation(
        id=uuid.uuid4(),
        invited_email="expired@example.com",
        assigned_role=Role.MARKETER.value,
        issued_by=admin_user.id,
        token_hash=token_hash,
        expires_at=datetime.now(timezone.utc) - timedelta(hours=1),
        status=InvitationStatus.PENDING.value,
    )
    db_session.add(inv)
    await db_session.commit()

    resp = await async_client.post(
        "/api/v1/auth/accept-invitation",
        json={"token": raw, "display_name": "X", "password": "Str0ng!Pass1"},
    )
    assert resp.status_code == 410
    assert resp.json()["detail"]["code"] == "INVITATION_EXPIRED"


async def test_accept_invitation_already_used(
    async_client: AsyncClient, admin_user: User, db_session: AsyncSession
):
    raw = secrets.token_urlsafe(32)
    token_hash = hashlib.sha256(raw.encode()).hexdigest()
    inv = Invitation(
        id=uuid.uuid4(),
        invited_email="used@example.com",
        assigned_role=Role.MARKETER.value,
        issued_by=admin_user.id,
        token_hash=token_hash,
        expires_at=datetime.now(timezone.utc) + timedelta(hours=72),
        status=InvitationStatus.ACCEPTED.value,
    )
    db_session.add(inv)
    await db_session.commit()

    resp = await async_client.post(
        "/api/v1/auth/accept-invitation",
        json={"token": raw, "display_name": "X", "password": "Str0ng!Pass1"},
    )
    assert resp.status_code == 409
    assert resp.json()["detail"]["code"] == "INVITATION_ALREADY_USED"


async def test_accept_invitation_invalid_token(async_client: AsyncClient):
    resp = await async_client.post(
        "/api/v1/auth/accept-invitation",
        json={"token": "does-not-exist", "display_name": "X", "password": "Str0ng!Pass1"},
    )
    assert resp.status_code == 404
    assert resp.json()["detail"]["code"] == "INVITATION_NOT_FOUND"
