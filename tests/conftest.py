import asyncio
import hashlib
import os
import secrets
import uuid
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import pytest
import pytest_asyncio
from cryptography.fernet import Fernet
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text as sa_text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from src.config import settings
from src.models import Base, Invitation, InvitationStatus, Role, Session, User, UserStatus
from utils.auth import create_access_token, hash_password

# ---------------------------------------------------------------------------
# Test database — NullPool so each test gets a fresh connection
# ---------------------------------------------------------------------------

TEST_DB_URL = os.getenv("TEST_DATABASE_URL", settings.async_database_url)

_test_engine = create_async_engine(TEST_DB_URL, poolclass=NullPool, echo=False)
_TestSession = async_sessionmaker(_test_engine, expire_on_commit=False)


# ---------------------------------------------------------------------------
# Session-scoped: create tables once, drop after suite
# ---------------------------------------------------------------------------

@pytest.fixture(scope="session", autouse=True)
def create_tables():
    """Synchronous session-scoped fixture: create schema once, drop after suite."""
    async def _setup():
        # Phase 1: Try to enable pgvector in its own autocommit connection
        has_vector = False
        async with _test_engine.connect() as conn:
            await conn.execution_options(isolation_level="AUTOCOMMIT")
            try:
                await conn.execute(sa_text("CREATE EXTENSION IF NOT EXISTS vector"))
            except Exception:
                pass
            try:
                await conn.execute(sa_text("SELECT NULL::vector(1)"))
                has_vector = True
            except Exception:
                pass

        # Phase 2: Create schema tables
        async with _test_engine.begin() as conn:
            await conn.run_sync(Base.metadata.drop_all)

            if has_vector:
                await conn.run_sync(Base.metadata.create_all)
            else:
                # pgvector not available — skip content_chunks table
                skip_tables = {"content_chunks"}
                tables_to_create = [
                    t for t in Base.metadata.sorted_tables if t.name not in skip_tables
                ]
                await conn.run_sync(
                    lambda sync_conn: Base.metadata.create_all(sync_conn, tables=tables_to_create)
                )

    async def _teardown():
        async with _test_engine.begin() as conn:
            await conn.run_sync(Base.metadata.drop_all)

    asyncio.run(_setup())
    yield
    asyncio.run(_teardown())


# ---------------------------------------------------------------------------
# Function-scoped: fresh session per test, auto-rollback on teardown
# ---------------------------------------------------------------------------

@pytest_asyncio.fixture(autouse=True)
async def clean_db():
    """Truncate all tables before each test for a clean slate.

    Tables that were skipped at creation time (e.g. content_chunks when
    pgvector is unavailable) are silently ignored.
    """
    async with _test_engine.connect() as conn:
        for table in reversed(Base.metadata.sorted_tables):
            try:
                async with conn.begin_nested():
                    await conn.execute(table.delete())
            except Exception:
                pass  # table may not exist (e.g. content_chunks without pgvector)
        await conn.commit()
    yield


@pytest_asyncio.fixture
async def db_session() -> AsyncSession:
    async with _TestSession() as session:
        yield session
        await session.rollback()


# ---------------------------------------------------------------------------
# HTTP client with DB override
# ---------------------------------------------------------------------------

@pytest_asyncio.fixture
async def async_client(db_session: AsyncSession):
    from utils.db import get_db
    from src.main import app

    async def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db
    async with AsyncClient(transport=ASGITransport(app=app), base_url="https://test") as client:
        yield client
    app.dependency_overrides.clear()


# ---------------------------------------------------------------------------
# User fixtures
# ---------------------------------------------------------------------------

@pytest_asyncio.fixture
async def admin_user(db_session: AsyncSession) -> User:
    user = User(
        id=uuid.uuid4(),
        email="admin@example.com",
        display_name="Admin User",
        password_hash=hash_password("Str0ng!Pass1"),
        role=Role.ADMIN.value,
        status=UserStatus.ACTIVE.value,
    )
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    return user


@pytest_asyncio.fixture
async def marketer_user(db_session: AsyncSession) -> User:
    user = User(
        id=uuid.uuid4(),
        email="marketer@example.com",
        display_name="Marketer User",
        password_hash=hash_password("Str0ng!Pass1"),
        role=Role.MARKETER.value,
        status=UserStatus.ACTIVE.value,
    )
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    return user


@pytest_asyncio.fixture
async def marketing_manager_user(db_session: AsyncSession) -> User:
    user = User(
        id=uuid.uuid4(),
        email="manager@example.com",
        display_name="Manager User",
        password_hash=hash_password("Str0ng!Pass1"),
        role=Role.MARKETING_MANAGER.value,
        status=UserStatus.ACTIVE.value,
    )
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    return user


# ---------------------------------------------------------------------------
# Token / session fixtures
# ---------------------------------------------------------------------------

@pytest_asyncio.fixture
async def admin_token(admin_user: User, db_session: AsyncSession) -> str:
    now = datetime.now(timezone.utc)
    session = Session(
        id=uuid.uuid4(),
        user_id=admin_user.id,
        refresh_token_hash=hashlib.sha256(secrets.token_urlsafe(32).encode()).hexdigest(),
        expires_at=now + timedelta(days=30),
        last_active_at=now,
    )
    db_session.add(session)
    await db_session.commit()
    return create_access_token({
        "sub": str(admin_user.id),
        "email": admin_user.email,
        "role": admin_user.role,
        "session_id": str(session.id),
    })


@pytest_asyncio.fixture
async def marketer_token(marketer_user: User, db_session: AsyncSession) -> str:
    now = datetime.now(timezone.utc)
    session = Session(
        id=uuid.uuid4(),
        user_id=marketer_user.id,
        refresh_token_hash=hashlib.sha256(secrets.token_urlsafe(32).encode()).hexdigest(),
        expires_at=now + timedelta(days=30),
        last_active_at=now,
    )
    db_session.add(session)
    await db_session.commit()
    return create_access_token({
        "sub": str(marketer_user.id),
        "email": marketer_user.email,
        "role": marketer_user.role,
        "session_id": str(session.id),
    })


@pytest_asyncio.fixture
async def marketing_manager_token(marketing_manager_user: User, db_session: AsyncSession) -> str:
    now = datetime.now(timezone.utc)
    session = Session(
        id=uuid.uuid4(),
        user_id=marketing_manager_user.id,
        refresh_token_hash=hashlib.sha256(secrets.token_urlsafe(32).encode()).hexdigest(),
        expires_at=now + timedelta(days=30),
        last_active_at=now,
    )
    db_session.add(session)
    await db_session.commit()
    return create_access_token({
        "sub": str(marketing_manager_user.id),
        "email": marketing_manager_user.email,
        "role": marketing_manager_user.role,
        "session_id": str(session.id),
    })


# ---------------------------------------------------------------------------
# Invitation fixture
# ---------------------------------------------------------------------------

@pytest_asyncio.fixture
async def pending_invitation(admin_user: User, db_session: AsyncSession):
    raw_token = secrets.token_urlsafe(32)
    token_hash = hashlib.sha256(raw_token.encode()).hexdigest()
    invitation = Invitation(
        id=uuid.uuid4(),
        invited_email="invitee@example.com",
        assigned_role=Role.MARKETER.value,
        issued_by=admin_user.id,
        token_hash=token_hash,
        expires_at=datetime.now(timezone.utc) + timedelta(hours=72),
        status=InvitationStatus.PENDING.value,
    )
    db_session.add(invitation)
    await db_session.commit()
    await db_session.refresh(invitation)
    return invitation, raw_token


# ---------------------------------------------------------------------------
# GitHub Bridge fixtures
# ---------------------------------------------------------------------------

_TEST_FERNET_KEY = Fernet.generate_key().decode()


@pytest.fixture(autouse=True)
def patch_github_encryption_key():
    """Patch GITHUB_TOKEN_ENCRYPTION_KEY with a stable test Fernet key for all tests."""
    with patch.object(settings, "GITHUB_TOKEN_ENCRYPTION_KEY", _TEST_FERNET_KEY):
        yield


@pytest_asyncio.fixture(autouse=True)
async def seed_default_repo_config(clean_db):
    """
    Re-seed the default RepoStructureConfig after clean_db truncates all tables.
    Uses the test engine directly (same connection pool as clean_db).
    """
    from src.models.repo_structure_config import RepoStructureConfig
    async with _TestSession() as session:
        config = RepoStructureConfig(
            folders={
                "folders": [
                    "content/campaigns",
                    "content/assets/images",
                    "content/assets/documents",
                    "content/templates",
                    "content/drafts",
                    "content/published",
                ]
            },
            is_default=True,
            created_by=None,
        )
        session.add(config)
        await session.commit()
