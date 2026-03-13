# Implementation Plan: Epic 1 — Identity & Access Management

**Branch**: `1-epic-1-iam-plan`
**Spec**: `specs/1-epic-1-iam/spec.md`
**Status**: Ready for `/speckit.tasks`
**Date**: 2026-03-12

---

## Constitution Compliance Check

| Label | Status | How It Is Satisfied |
|-------|--------|-------------------|
| **AUTH_SAFE** | PASS | Every endpoint except `/auth/*` and `/health` is wrapped with `Depends(get_current_user)`. No route accesses the DB without a validated session. |
| **DRY** | PASS | All auth logic lives exclusively in `utils/auth.py`. All DB access goes through `utils/db.py`. No duplication across routers. |
| **NON_BLOCKING** | PASS | Full async stack: `asyncpg` + SQLAlchemy 2.0 async + FastAPI async handlers. No blocking I/O anywhere. |

---

## Architecture Overview

```
React Frontend
     │
     │  HTTPS
     ▼
FastAPI Application (src/main.py)
     │
     ├── Middleware: RequestID injection, global exception handler
     │
     ├── /auth/*     ← Public endpoints (no auth required)
     ├── /users/*    ← Protected endpoints (auth + role guards)
     └── /health     ← Public liveness probe
     │
     ├── utils/auth.py     ← JWT, password hashing, FastAPI deps
     ├── utils/db.py       ← Async DB connection pool
     └── utils/email.py    ← SMTP invitation delivery
     │
     ▼
PostgreSQL Database
     ├── users
     ├── sessions
     ├── invitations
     └── audit_log
```

**Token Flow**:
```
Login ──► JWT (15 min, in response body) + refresh_token (30 days, httpOnly cookie)
         │
Each request ──► Bearer JWT ──► validate sig ──► lookup session (revocation check)
         │
Refresh ──► POST /auth/refresh with cookie ──► new JWT
         │
Logout / Revocation ──► sessions.revoked = true ──► subsequent requests rejected
```

---

## File Structure

```
marketing-platform/
├── src/
│   ├── main.py                   ← FastAPI app factory, middleware, router mounts
│   ├── config.py                 ← Settings via pydantic-settings (reads .env)
│   ├── api/
│   │   ├── __init__.py
│   │   ├── auth.py               ← /auth/* routes
│   │   ├── users.py              ← /users/* routes
│   │   └── health.py             ← /health
│   └── models/
│       ├── __init__.py
│       ├── base.py               ← DeclarativeBase
│       ├── user.py               ← User, Role enum, UserStatus enum
│       ├── session.py            ← Session model
│       ├── invitation.py         ← Invitation model, InvitationStatus enum
│       └── audit_log.py          ← AuditLog model
├── utils/
│   ├── __init__.py
│   ├── auth.py                   ← JWT create/decode, password hash/verify,
│   │                               get_current_user, require_role factory
│   ├── db.py                     ← async engine, AsyncSessionLocal, get_db
│   ├── email.py                  ← SMTP send, invitation email template
│   └── audit.py                  ← write_audit() helper
├── migrations/
│   ├── env.py
│   ├── alembic.ini
│   └── versions/
│       └── 001_create_iam_tables.py
└── tests/
    ├── conftest.py               ← test DB, async client fixtures
    ├── api/
    │   ├── test_auth.py
    │   └── test_users.py
    └── utils/
        └── test_auth_utils.py
```

---

## Environment Variables

| Variable | Required | Description |
|----------|----------|-------------|
| `DATABASE_URL` | Yes | `postgresql+asyncpg://user:pass@host:5432/db` |
| `SECRET_KEY` | Yes | JWT signing key. Min 32 chars. Rotate to invalidate all sessions. |
| `INITIAL_ADMIN_TOKEN` | Setup only | Bootstrap credential. Remove after first Admin registers. |
| `APP_URL` | Yes | Base URL for invitation links (e.g., `https://app.example.com`) |
| `SMTP_HOST` | Yes | SMTP server hostname |
| `SMTP_PORT` | Yes | SMTP port (typically 587 for TLS) |
| `SMTP_USER` | Yes | SMTP authentication username |
| `SMTP_PASS` | Yes | SMTP authentication password |
| `SMTP_FROM` | Yes | From address for invitation emails |
| `ACCESS_TOKEN_EXPIRE_MINUTES` | No | Default: `15` |
| `REFRESH_TOKEN_EXPIRE_DAYS` | No | Default: `30` |
| `SESSION_INACTIVITY_HOURS` | No | Default: `8` |

---

## Implementation Phases

### Phase 1 — Foundation (blocks everything)
*Must be complete before any route can be written.*

**P1.1 — Project scaffolding**
- Add dependencies to `requirements.txt`:
  ```
  fastapi>=0.115
  uvicorn[standard]
  sqlalchemy[asyncio]>=2.0
  asyncpg
  alembic
  passlib[bcrypt]
  python-jose[cryptography]
  pydantic-settings
  aiosmtplib
  ```
- Create `src/config.py` using `pydantic-settings` to load all env vars with validation.
- Create `src/main.py` with app factory, CORS config, and router mounts (empty routers).

**P1.2 — Database layer**
- Create `utils/db.py`: async engine from `DATABASE_URL`, `AsyncSessionLocal`, `get_db` dependency.
- Create `src/models/base.py`: `DeclarativeBase` with `metadata`.
- Create all four SQLAlchemy models: `User`, `Session`, `Invitation`, `AuditLog`.
- Write `migrations/versions/001_create_iam_tables.py` with full `upgrade()` and `downgrade()`.

**P1.3 — Auth utilities**
- Create `utils/auth.py`:
  - `hash_password(plain: str) -> str` — bcrypt via passlib
  - `verify_password(plain: str, hashed: str) -> bool`
  - `create_access_token(data: dict) -> str` — HS256 JWT
  - `decode_access_token(token: str) -> dict` — raises `401` on invalid/expired
  - `get_current_user(token, db) -> User` — validates JWT, checks session not revoked
  - `require_role(*roles) -> Depends(...)` — role guard factory
- Create `utils/audit.py`: `write_audit(db, action, actor_id, target_id, metadata)`.

**P1.4 — Middleware**
- Add `RequestIDMiddleware` to `src/main.py`: generates UUID per request, attaches to `request.state.request_id`, sets `X-Request-ID` response header.
- Add global exception handler: catches all unhandled exceptions, logs with `request_id`, returns `500` JSON.

---

### Phase 2 — Admin Registration & Login
*Requires Phase 1.*

**P2.1 — Register endpoint** (`POST /auth/register`)
- Verify `X-Setup-Token` header against `INITIAL_ADMIN_TOKEN`.
- Assert no admin user exists.
- Hash password, create User row (role=admin), write audit log.
- Returns user object (no session — user must log in separately).

**P2.2 — Login endpoint** (`POST /auth/login`)
- Look up user by email. Check `status = active`. Check `locked_until`.
- `verify_password`. On failure: increment `failed_login_count`, lock at 5, write audit.
- On success: reset `failed_login_count`, create Session row, issue JWT + set refresh cookie, write audit.

**P2.3 — Logout endpoint** (`POST /auth/logout`)
- Requires `get_current_user`.
- Set `sessions.revoked = true` for current `session_id`.
- Clear `refresh_token` cookie.
- Write audit log.

**P2.4 — Refresh endpoint** (`POST /auth/refresh`)
- Read `refresh_token` cookie. Hash it, look up session.
- Check: not revoked, not expired, user is active.
- Issue new JWT. Update `last_active_at`.

---

### Phase 3 — Invitation System
*Requires Phase 1 + email utility.*

**P3.1 — Email utility**
- Create `utils/email.py` using `aiosmtplib`.
- `send_invitation_email(to_email, role, link)` — async SMTP send with HTML template.
- Graceful error handling: log failure, do not crash the invitation endpoint.

**P3.2 — Send invitation** (`POST /users/invite`)
- Requires `require_role(Role.ADMIN)`.
- Validate: email not already a user, role is not admin.
- Expire any existing pending invitations for the email.
- Generate token (`secrets.token_urlsafe(32)`), hash with SHA-256.
- Insert Invitation row. Send email. Write audit log.

**P3.3 — Accept invitation** (`POST /auth/accept-invitation`)
- Hash incoming token, look up by `token_hash`. Check status = pending, not expired.
- Validate password complexity.
- Create User row with `assigned_role`. Set invitation `status = accepted`.
- Write audit log.

**P3.4 — Resend invitation** (`POST /users/invitations/{id}/resend`)
- Requires `require_role(Role.ADMIN)`.
- Fetch invitation, verify it's not already accepted.
- Expire it, generate new token, insert new Invitation row.
- Resend email. Write audit log.

---

### Phase 4 — Role & Access Management
*Requires Phase 1 + Phase 2.*

**P4.1 — List users** (`GET /users`)
- Requires `require_role(Role.ADMIN, Role.MARKETING_MANAGER)`.
- Query with optional `status` and `role` filters.

**P4.2 — Change role** (`PATCH /users/{user_id}/role`)
- Requires `require_role(Role.ADMIN)`.
- Assert `user_id != current_user.id` (cannot change own role).
- Assert new role is valid.
- If changing an admin's role away from admin: assert admin count > 1 (Last Admin guard).
- Update role. Write audit log.

**P4.3 — Revoke access** (`POST /users/{user_id}/revoke`)
- Requires `require_role(Role.ADMIN)`.
- Assert `user_id != current_user.id`.
- If target is admin: assert admin count > 1 (Last Admin guard).
- Set `users.status = deactivated`, `deactivated_at = NOW()`.
- Set `sessions.revoked = true WHERE user_id = target_user_id`.
- Write audit log.

**P4.4 — Reactivate user** (`POST /users/{user_id}/reactivate`)
- Requires `require_role(Role.ADMIN)`.
- Set `users.status = active`, clear `deactivated_at`.
- Write audit log.

**P4.5 — Own profile** (`GET /users/me`)
- Requires `get_current_user`.
- Return user from the already-resolved dependency — no additional DB query.

---

### Phase 5 — Security Hardening & Health
*Requires Phase 2.*

**P5.1 — Account lockout** (integrated into P2.2 login)
- Already accounted for in P2.2. Verify the `locked_until` check and `failed_login_count` reset are correct.
- Unit test: assert lockout activates on exactly the 5th failure within the same request.

**P5.2 — Health endpoint** (`GET /health`)
- No auth. Returns `{"status": "ok", "version": settings.APP_VERSION}`.
- Used by Docker `HEALTHCHECK` and future K8s liveness probe.

**P5.3 — Password validation utility**
- Extracted regex or rules function used by both register and accept-invitation.
- Min 10 chars, ≥1 uppercase, ≥1 digit, ≥1 special character.
- Lives in `utils/auth.py`.

---

## Testing Strategy

### Test Infrastructure (`tests/conftest.py`)
- Spin up a test PostgreSQL database (or use SQLite async for speed — decision for implementation).
- `pytest-asyncio` for async test cases.
- `httpx.AsyncClient` with FastAPI `TestClient` or `ASGITransport`.
- Fixtures: `db_session`, `async_client`, `admin_user`, `marketer_user`, `pending_invitation`.

### Required Test Coverage

| Endpoint | Tests Required |
|----------|---------------|
| `POST /auth/register` | Happy path; invalid setup token; admin already exists |
| `POST /auth/login` | Happy path; wrong password; deactivated account; lockout on 5th failure; locked account |
| `POST /auth/logout` | Happy path; revoked session rejected on next request |
| `POST /auth/refresh` | Happy path; expired token; revoked session |
| `POST /auth/accept-invitation` | Happy path; expired token; already accepted; invalid token |
| `POST /users/invite` | Happy path; non-admin rejected (403); duplicate email; admin role rejected |
| `GET /users` | Admin sees all; marketing manager sees all; marketer gets 403 |
| `PATCH /users/{id}/role` | Happy path; cannot change own role; last admin guard |
| `POST /users/{id}/revoke` | Happy path; immediate session invalidation; last admin guard |
| `POST /users/{id}/reactivate` | Happy path; already active |
| `GET /users/me` | Happy path; unauthenticated returns 401 |

### Cross-Cutting Assertions (apply to every protected endpoint)
- Unauthenticated request → `401`
- Authenticated request with insufficient role → `403`
- `request_id` present in all responses
- Audit log entry written for all state-changing operations

---

## Risks & Open Items

| Risk | Severity | Mitigation |
|------|----------|-----------|
| `INITIAL_ADMIN_TOKEN` left in production `.env` | High | Add startup warning log if env var is set after admin already exists. Document removal in deployment guide. |
| `SECRET_KEY` rotation invalidates all sessions | Medium | Acceptable: all users re-login. Document this behaviour. |
| SMTP misconfiguration blocks invitations | Medium | Invitation endpoint returns success even if email fails (token is created). Log SMTP failure. Users can check pending invitations and resend. |
| Refresh token cookie blocked by browser (3rd-party context) | Low | App is first-party only per deployment model — not a risk. |
| Test DB migration state drift | Low | Use Alembic in test setup; never use `metadata.create_all()` in tests. |
