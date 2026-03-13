# Tasks: Epic 1 — Identity & Access Management

**Feature**: Identity & Access Management (IAM)
**Branch**: `1-epic-1-iam-plan`
**Plan**: `specs/1-epic-1-iam/plan.md`
**Spec**: `specs/1-epic-1-iam/spec.md`
**Generated**: 2026-03-12

---

## User Story Index

| Story | Scenario | Description | Priority |
|-------|----------|-------------|----------|
| US1 | Scenario 1 | First-Time Admin Registration | P1 |
| US2 | Scenarios 2 & 6 | Authentication, Sessions & Logout | P1 |
| US3 | Scenarios 3 & 4 | User Invitations (send, accept, resend) | P2 |
| US4 | Scenario 5 | Role Management | P2 |
| US5 | Scenario 7 | Access Revocation & Reactivation | P2 |

---

## Phase 1: Setup

*Project scaffolding. No dependencies. All tasks in this phase can run in parallel.*

- [X] T001 [P] Add all dependencies to `marketing-platform/requirements.txt` (fastapi>=0.115, uvicorn[standard], sqlalchemy[asyncio]>=2.0, asyncpg, alembic, passlib[bcrypt], python-jose[cryptography], pydantic-settings, aiosmtplib, pytest, pytest-asyncio, httpx)
- [X] T002 [P] Create `marketing-platform/src/__init__.py` (empty)
- [X] T003 [P] Create `marketing-platform/src/api/__init__.py` (empty)
- [X] T004 [P] Create `marketing-platform/src/models/__init__.py` exporting Base and all models (stub — fill after T010–T014)
- [X] T005 [P] Create `marketing-platform/utils/__init__.py` (empty)
- [X] T006 [P] Create `marketing-platform/migrations/env.py` with async Alembic env setup pointing to `src.models.base.Base.metadata` and `DATABASE_URL` from config
- [X] T007 [P] Create `marketing-platform/migrations/alembic.ini` with `script_location = migrations` and `sqlalchemy.url` left blank (overridden in env.py)
- [X] T008 [P] Create `marketing-platform/.env.example` with all required variables as documented in `specs/1-epic-1-iam/quickstart.md`

---

## Phase 2: Foundation

*Blocking prerequisites. Must complete before any user story phase begins.*

### Database & Config

- [X] T009 Create `marketing-platform/src/config.py` using `pydantic-settings` `BaseSettings` loading all env vars from table in `specs/1-epic-1-iam/plan.md` — include `DATABASE_URL`, `SECRET_KEY`, `INITIAL_ADMIN_TOKEN` (optional), `APP_URL`, `SMTP_*`, `ACCESS_TOKEN_EXPIRE_MINUTES=15`, `REFRESH_TOKEN_EXPIRE_DAYS=30`, `SESSION_INACTIVITY_HOURS=8`, `APP_VERSION="1.0.0"`
- [X] T010 Create `marketing-platform/utils/db.py` — async engine via `create_async_engine(settings.DATABASE_URL, pool_size=10, max_overflow=20)`, `async_sessionmaker` as `AsyncSessionLocal`, `get_db` async generator dependency per `specs/1-epic-1-iam/research.md` Decision 7
- [X] T011 Create `marketing-platform/src/models/base.py` — `DeclarativeBase` subclass named `Base` with shared `metadata`

### SQLAlchemy Models

- [X] T012 [P] Create `marketing-platform/src/models/user.py` — `User` model with all columns from `specs/1-epic-1-iam/data-model.md` (`id UUID PK`, `email`, `display_name`, `password_hash`, `role`, `status`, `failed_login_count`, `locked_until`, `created_at`, `deactivated_at`); `Role` enum (`admin`, `marketing_manager`, `marketer`); `UserStatus` enum (`active`, `deactivated`)
- [X] T013 [P] Create `marketing-platform/src/models/session.py` — `Session` model (`id UUID PK`, `user_id FK→users`, `refresh_token_hash VARCHAR(64)`, `created_at`, `last_active_at`, `expires_at`, `revoked BOOLEAN DEFAULT FALSE`, `revoked_at`)
- [X] T014 [P] Create `marketing-platform/src/models/invitation.py` — `Invitation` model (`id UUID PK`, `invited_email`, `assigned_role`, `issued_by FK→users`, `token_hash VARCHAR(64)`, `issued_at`, `expires_at`, `status`); `InvitationStatus` enum (`pending`, `accepted`, `expired`)
- [X] T015 [P] Create `marketing-platform/src/models/audit_log.py` — `AuditLog` model (`id UUID PK`, `action VARCHAR(100)`, `actor_id FK→users ON DELETE SET NULL`, `target_id FK→users ON DELETE SET NULL`, `metadata JSONB`, `timestamp`); add all indexes per `specs/1-epic-1-iam/data-model.md`
- [X] T016 Update `marketing-platform/src/models/__init__.py` to export `Base`, `User`, `Role`, `UserStatus`, `Session`, `Invitation`, `InvitationStatus`, `AuditLog`

### Migration

- [X] T017 Create `marketing-platform/migrations/versions/001_create_iam_tables.py` — `upgrade()` creates tables in order: users → sessions → invitations → audit_log with all indexes; `downgrade()` drops in reverse order; full SQL per `specs/1-epic-1-iam/data-model.md`

### Auth Utilities

- [X] T018 Create `marketing-platform/utils/auth.py` — implement:
  - `hash_password(plain: str) -> str` using `passlib.context.CryptContext(schemes=["bcrypt"], bcrypt__rounds=12)`
  - `verify_password(plain: str, hashed: str) -> bool`
  - `validate_password_complexity(password: str) -> None` — raises `HTTPException 422` if < 10 chars or missing uppercase, digit, or special char (per spec A-7)
  - `create_access_token(data: dict) -> str` — HS256 JWT, includes `sub`, `email`, `role`, `session_id`, signed with `settings.SECRET_KEY`, expires in `settings.ACCESS_TOKEN_EXPIRE_MINUTES`
  - `decode_access_token(token: str) -> dict` — raises `HTTPException 401 UNAUTHENTICATED` on invalid/expired
  - `get_current_user(token, db) -> User` — validates JWT, queries session by `session_id`, checks `revoked=false` and `expires_at > now`, returns User; raises `401` if any check fails
  - `require_role(*roles: Role) -> Depends(...)` — factory returning a FastAPI dependency that calls `get_current_user`, then raises `403` if user's role not in `roles`

- [X] T019 Create `marketing-platform/utils/audit.py` — `write_audit(db: AsyncSession, action: str, actor_id=None, target_id=None, metadata=None)` appends `AuditLog` row; caller commits; never issues UPDATE/DELETE on audit_log

### App Factory & Middleware

- [X] T020 Create `marketing-platform/src/main.py` — FastAPI app factory with:
  - `RequestIDMiddleware`: echoes `X-Request-ID` header if present, else generates UUID; attaches to `request.state.request_id`; sets `X-Request-ID` on response
  - Global exception handler catching all unhandled exceptions, logging traceback with `request_id`, returning `{"error": "An unexpected error occurred", "code": "INTERNAL_ERROR", "request_id": "..."}` (500)
  - CORS config (allow origins from settings)
  - Router mounts at `/api/v1` (stub routers for now — filled in subsequent phases)
  - Startup warning: log `WARNING` if `settings.INITIAL_ADMIN_TOKEN` is set and an Admin user already exists in the DB

### Test Infrastructure

- [X] T021 Create `marketing-platform/tests/__init__.py` (empty)
- [X] T022 Create `marketing-platform/tests/api/__init__.py` (empty)
- [X] T023 Create `marketing-platform/tests/utils/__init__.py` (empty)
- [X] T024 Create `marketing-platform/tests/conftest.py` — pytest-asyncio fixtures:
  - `event_loop` (session-scoped)
  - `db_session` — in-memory or test Postgres using `AsyncSessionLocal`; applies Alembic migrations; rolls back after each test
  - `async_client` — `httpx.AsyncClient` with `ASGITransport(app=app)`
  - `admin_user` — creates User(role=admin, status=active) in `db_session`
  - `marketer_user` — creates User(role=marketer, status=active) in `db_session`
  - `admin_token` — valid JWT for `admin_user`
  - `marketer_token` — valid JWT for `marketer_user`
  - `pending_invitation` — Invitation(status=pending, expires_at=+72h) in `db_session`

---

## Phase 3: US1 — Admin Registration

*Goal*: The designated administrator can register as the first Admin using a platform-issued credential.

*Independent test*: `POST /auth/register` with valid setup token creates the first Admin and returns 201. The same request with missing/wrong token returns 403.

### Health Endpoint

- [X] T025 [P] [US1] Create `marketing-platform/src/api/health.py` — `GET /health` (no auth), returns `{"status": "ok", "version": settings.APP_VERSION}`

### Registration Endpoint

- [X] T026 [US1] Create `marketing-platform/src/api/auth.py` with `APIRouter(prefix="/auth")` and implement `POST /auth/register`:
  - Verify `X-Setup-Token` header == `settings.INITIAL_ADMIN_TOKEN`; raise `403 SETUP_TOKEN_INVALID` if missing/wrong
  - Query `users WHERE role = 'admin'`; raise `409 ADMIN_ALREADY_EXISTS` if row found
  - Call `validate_password_complexity(body.password)`
  - Call `hash_password`, create `User(role=admin, status=active)`
  - Call `write_audit(db, "user_registered", actor_id=new_user.id, metadata={"role": "admin"})`
  - Commit, return `201` with user object and `request_id`

- [X] T027 [US1] Mount `health_router` and `auth_router` (stub for remaining routes) in `marketing-platform/src/main.py`

### Tests

- [X] T028 [P] [US1] Create `marketing-platform/tests/api/test_auth.py` with:
  - `test_register_happy_path` — valid token, no existing admin → 201, role=admin in response
  - `test_register_invalid_token` — wrong token → 403 SETUP_TOKEN_INVALID
  - `test_register_missing_token` — no header → 403 SETUP_TOKEN_INVALID
  - `test_register_admin_already_exists` — second call with valid token → 409 ADMIN_ALREADY_EXISTS
  - `test_register_weak_password` — password fails complexity → 422
  - `test_register_request_id_in_response` — `request_id` field present in all responses

---

## Phase 4: US2 — Authentication, Sessions & Logout

*Goal*: Users can log in with email + password, receive a JWT + refresh cookie, use the refresh endpoint to get new access tokens, and log out to immediately terminate their session.

*Independent test*: `POST /auth/login` with valid credentials returns a JWT. Using that JWT on a protected endpoint returns 200. After `POST /auth/logout`, the same JWT on a protected endpoint returns 401.

### Login

- [X] T029 [US2] Add `POST /auth/login` to `marketing-platform/src/api/auth.py`:
  - Lookup User by email; raise `401 INVALID_CREDENTIALS` (generic — never reveal which field failed)
  - Check `status == active`; raise `401 ACCOUNT_DEACTIVATED` if not
  - Check `locked_until IS NULL OR locked_until < NOW()`; raise `429 ACCOUNT_LOCKED` with `locked_until` if locked
  - `verify_password`; on failure: increment `failed_login_count`; if count >= 5 set `locked_until = now + 15min`, write `user_locked` audit, raise `429 ACCOUNT_LOCKED`; on failure < 5 write `user_login_failed` audit, raise `401 INVALID_CREDENTIALS`
  - On success: reset `failed_login_count = 0`, create `Session` row (`refresh_token_hash = sha256(raw_token)`, `expires_at = now + 30 days`), issue JWT via `create_access_token`, write `user_login` audit
  - Set httpOnly cookie `refresh_token` per contract (`Path=/api/v1/auth/refresh`, `Max-Age=2592000`, `Secure`, `SameSite=Strict`)
  - Return `200` with access token and user object

### Refresh

- [X] T030 [US2] Add `POST /auth/refresh` to `marketing-platform/src/api/auth.py`:
  - Read `refresh_token` cookie; raise `401 REFRESH_TOKEN_INVALID` if absent
  - Hash incoming token with `hashlib.sha256`; query `sessions WHERE refresh_token_hash = hash`
  - Check session exists, `revoked = false`, `expires_at > now`, user `status = active`; raise appropriate 401 errors
  - Issue new JWT, update `session.last_active_at = now`
  - Return `200` with new access token

### Logout

- [X] T031 [US2] Add `POST /auth/logout` to `marketing-platform/src/api/auth.py`:
  - Depends on `get_current_user` (requires valid JWT)
  - Set `session.revoked = true`, `session.revoked_at = now`
  - Clear `refresh_token` cookie
  - Write `user_logout` audit with `session_id`
  - Return `204`

### Tests

- [X] T032 [P] [US2] Add to `marketing-platform/tests/api/test_auth.py`:
  - `test_login_happy_path` — valid credentials → 200, access_token present, refresh_token cookie set
  - `test_login_wrong_password` → 401 INVALID_CREDENTIALS
  - `test_login_unknown_email` → 401 INVALID_CREDENTIALS
  - `test_login_deactivated_account` → 401 ACCOUNT_DEACTIVATED
  - `test_login_lockout_on_5th_failure` — 5th consecutive wrong password → 429 ACCOUNT_LOCKED (same request that triggers 5th)
  - `test_login_locked_account` — locked_until in future → 429 ACCOUNT_LOCKED
  - `test_logout_happy_path` — logout with valid token → 204, refresh cookie cleared
  - `test_logout_revoked_session_rejected` — after logout, protected request with same token → 401
  - `test_refresh_happy_path` — valid refresh cookie → 200 with new access_token
  - `test_refresh_expired_token` → 401 REFRESH_TOKEN_INVALID
  - `test_refresh_revoked_session` → 401 SESSION_REVOKED

---

## Phase 5: US3 — User Invitations

*Goal*: Admins can invite new team members via email. Invitees can accept the invitation to create their account.

*Independent test*: `POST /users/invite` as Admin returns 201 with invitation data. `POST /auth/accept-invitation` with the valid token creates the user and returns 201. Non-Admin invite attempt returns 403.

### Email Utility

- [X] T033 [US3] Create `marketing-platform/utils/email.py` — async SMTP client using `aiosmtplib`:
  - `send_invitation_email(to_email: str, role: str, link: str) -> None`
  - HTML email template with invitation link and role
  - Try/except: log SMTP failure with `logger.error`; do NOT re-raise (invitation endpoint returns success even if email fails per `specs/1-epic-1-iam/plan.md` Risk table)

### Users Router

- [X] T034 [US3] Create `marketing-platform/src/api/users.py` with `APIRouter(prefix="/users")` and implement `POST /users/invite`:
  - Depends on `require_role(Role.ADMIN)`
  - Validate `body.role != admin`; raise `400 INVALID_ROLE` if admin role requested
  - Check no active User with `body.email`; raise `409 USER_ALREADY_EXISTS` if found
  - Expire pending invitations: `UPDATE invitations SET status='expired' WHERE invited_email=email AND status='pending'`
  - Generate `raw_token = secrets.token_urlsafe(32)`, `token_hash = sha256(raw_token)`
  - Insert `Invitation` row (`expires_at = now + 72h`)
  - Call `send_invitation_email(body.email, role, link)` — link = `{settings.APP_URL}/accept-invitation?token={raw_token}`
  - Write `invitation_sent` audit
  - Return `201` with invitation object

- [X] T035 [US3] Add `POST /auth/accept-invitation` to `marketing-platform/src/api/auth.py`:
  - Hash `body.token` with SHA-256; query `invitations WHERE token_hash = hash`
  - Raise `404 INVITATION_NOT_FOUND` if not found
  - Raise `410 INVITATION_EXPIRED` if `status = expired` or `expires_at < now`
  - Raise `409 INVITATION_ALREADY_USED` if `status = accepted`
  - Call `validate_password_complexity(body.password)`
  - Create User with `invitation.assigned_role`; set `invitation.status = accepted`
  - Write `invitation_accepted` audit
  - Return `201` with user object

- [X] T036 [US3] Add `POST /users/invitations/{invitation_id}/resend` to `marketing-platform/src/api/users.py`:
  - Depends on `require_role(Role.ADMIN)`
  - Fetch invitation by ID; raise `404 INVITATION_NOT_FOUND` if not found
  - Raise `409 INVITATION_ALREADY_ACCEPTED` if `status = accepted`
  - Set existing invitation `status = expired`
  - Generate new token, insert new `Invitation` row for same email + role
  - Resend invitation email
  - Write `invitation_resent` audit
  - Return `200` with new invitation object

- [X] T037 [US3] Mount `users_router` in `marketing-platform/src/main.py`

### Tests

- [X] T038 [P] [US3] Create `marketing-platform/tests/api/test_users.py` with:
  - `test_invite_happy_path` — Admin invites marketer → 201, invitation data returned
  - `test_invite_non_admin_rejected` — marketer token → 403
  - `test_invite_admin_role_rejected` — role=admin in body → 400 INVALID_ROLE
  - `test_invite_duplicate_email` — email already has active user → 409 USER_ALREADY_EXISTS
  - `test_accept_invitation_happy_path` — valid token → 201, user created with correct role
  - `test_accept_invitation_expired` → 410 INVITATION_EXPIRED
  - `test_accept_invitation_already_used` → 409 INVITATION_ALREADY_USED
  - `test_accept_invitation_invalid_token` → 404 INVITATION_NOT_FOUND
  - `test_resend_invitation_happy_path` — prior invite expired, new invite issued → 200

---

## Phase 6: US4 — Role Management

*Goal*: Admins can change any team member's role (except their own). Role changes are audited.

*Independent test*: Admin changes a Marketer's role to Marketing Manager → 200 with updated role. Admin attempts to change own role → 403 CANNOT_CHANGE_OWN_ROLE.

- [X] T039 [US4] Add `GET /users` to `marketing-platform/src/api/users.py`:
  - Depends on `require_role(Role.ADMIN, Role.MARKETING_MANAGER)`
  - Accept optional query params `status` (`active`|`deactivated`|`all`, default `active`) and `role`
  - Query users with filters, return list

- [X] T040 [US4] Add `GET /users/me` to `marketing-platform/src/api/users.py`:
  - Depends on `get_current_user`
  - Return user from dependency — no additional DB query

- [X] T041 [US4] Add `PATCH /users/{user_id}/role` to `marketing-platform/src/api/users.py`:
  - Depends on `require_role(Role.ADMIN)`
  - Raise `403 CANNOT_CHANGE_OWN_ROLE` if `user_id == current_user.id`
  - Fetch target user; raise `404 USER_NOT_FOUND` if not found
  - Validate `body.role` in `Role` enum; raise `400 INVALID_ROLE` if not
  - If target is currently admin: check `COUNT(users WHERE role='admin' AND status='active') > 1`; raise `403 LAST_ADMIN` if count <= 1
  - Update `user.role`, write `role_changed` audit with `{old_role, new_role}`
  - Return `200` with updated user

### Tests

- [X] T042 [P] [US4] Add to `marketing-platform/tests/api/test_users.py`:
  - `test_list_users_as_admin` — Admin sees all users → 200
  - `test_list_users_as_marketing_manager` → 200
  - `test_list_users_as_marketer` → 403
  - `test_get_me_authenticated` → 200 with correct user data
  - `test_get_me_unauthenticated` → 401
  - `test_change_role_happy_path` — Admin changes marketer → marketing_manager → 200
  - `test_change_own_role_blocked` → 403 CANNOT_CHANGE_OWN_ROLE
  - `test_change_role_last_admin_blocked` — only one admin, demote attempt → 403 LAST_ADMIN
  - `test_change_role_invalid_value` → 400 INVALID_ROLE
  - `test_change_role_user_not_found` → 404

---

## Phase 7: US5 — Access Revocation & Reactivation

*Goal*: Admins can revoke a user's access (immediately terminating all sessions) and reactivate a previously deactivated account.

*Independent test*: Admin revokes a user → 200; revoked user's next authenticated request → 401. Admin reactivates the user → 200; user can log in again.

- [X] T043 [US5] Add `POST /users/{user_id}/revoke` to `marketing-platform/src/api/users.py`:
  - Depends on `require_role(Role.ADMIN)`
  - Raise `403 CANNOT_REVOKE_SELF` if `user_id == current_user.id`
  - Fetch target user; raise `404 USER_NOT_FOUND` if not found
  - Raise `409 USER_ALREADY_DEACTIVATED` if `user.status == deactivated`
  - If target is admin: check admin count > 1; raise `403 LAST_ADMIN` if only admin
  - Set `user.status = deactivated`, `user.deactivated_at = now`
  - `UPDATE sessions SET revoked=true WHERE user_id = user_id` (all sessions)
  - Write `access_revoked` audit
  - Return `200` with `{id, status, deactivated_at}`

- [X] T044 [US5] Add `POST /users/{user_id}/reactivate` to `marketing-platform/src/api/users.py`:
  - Depends on `require_role(Role.ADMIN)`
  - Fetch target user; raise `404 USER_NOT_FOUND` if not found
  - Raise `409 USER_ALREADY_ACTIVE` if `user.status == active`
  - Set `user.status = active`, clear `user.deactivated_at`
  - Write `user_reactivated` audit
  - Return `200` with `{id, status}`

### Tests

- [X] T045 [P] [US5] Add to `marketing-platform/tests/api/test_users.py`:
  - `test_revoke_happy_path` — Admin revokes marketer → 200, status=deactivated
  - `test_revoke_immediate_session_invalidation` — after revoke, marketer's token → 401
  - `test_revoke_self_blocked` → 403 CANNOT_REVOKE_SELF
  - `test_revoke_last_admin_blocked` → 403 LAST_ADMIN
  - `test_revoke_already_deactivated` → 409 USER_ALREADY_DEACTIVATED
  - `test_revoke_user_not_found` → 404
  - `test_reactivate_happy_path` → 200, status=active
  - `test_reactivate_already_active` → 409 USER_ALREADY_ACTIVE

---

## Phase 8: Polish & Cross-Cutting Concerns

*Applies to all stories. Address after all user story phases pass their independent tests.*

- [X] T046 Create `marketing-platform/tests/utils/test_auth_utils.py`:
  - `test_hash_and_verify_password` — round-trip bcrypt
  - `test_verify_wrong_password_returns_false`
  - `test_create_and_decode_access_token` — round-trip JWT
  - `test_decode_expired_token_raises_401`
  - `test_validate_password_complexity_passes` — valid passwords
  - `test_validate_password_complexity_fails_*` — too short, no uppercase, no digit, no special char (four parameterized cases)
  - `test_lockout_activates_on_5th_failure` — unit test of the counter logic

- [X] T047 Verify `request_id` header present on all error responses (add assertion helper to `conftest.py` or use per-test assertions in cross-cutting test)
- [X] T048 Verify audit log entry is written for every state-changing operation in the test suite (add helper that queries `audit_log` after each state-change test)
- [X] T049 Verify unauthenticated request → `401` and insufficient role → `403` for every protected endpoint (add parametrized cross-cutting tests covering all protected routes)
- [X] T050 Run `alembic upgrade head` in CI: add step to `marketing-platform/.github/workflows/ci.yml` (or update existing workflow) to apply migration against test Postgres before running pytest

---

## Dependency Graph

```
T001–T008 (Setup)
    │
    ▼
T009–T024 (Foundation — all must complete before Phase 3+)
    │
    ├──► Phase 3: US1 (T025–T028)  ←── prerequisite for Phase 4
    │         │
    │         ▼
    ├──► Phase 4: US2 (T029–T032)  ←── prerequisite for Phases 5, 6, 7
    │         │
    │    ┌────┼────┐
    │    ▼    ▼    ▼
    ├──► US3  US4  US5   (Phases 5, 6, 7 — independent of each other, all require US2)
    │
    ▼
Phase 8: Polish (T046–T050) — after all story phases pass
```

---

## Parallel Execution Opportunities

### Within Phase 2 (Foundation)
- T012, T013, T014, T015 — four model files, no dependencies on each other
- T018, T019 — auth utilities and audit utility are independent
- T021, T022, T023 — `__init__.py` files

### Within Phase 3 (US1)
- T025 (health endpoint) and T028 (tests) can begin once T026 is complete

### Across Phases 5, 6, 7
- Once Phase 4 (US2) is complete, phases 5, 6, and 7 can be implemented in parallel (different files: `api/users.py` already created in Phase 5, but tasks are additive)

---

## Implementation Strategy

### MVP Scope (US1 + US2 only)
Complete Phases 1–4 first. This gives you a working `POST /auth/register` + `POST /auth/login` + `POST /auth/logout` + `POST /auth/refresh` flow — enough to prove the auth stack end-to-end before adding invitation complexity.

### Incremental Delivery Order
1. **Phases 1–2**: Scaffold + foundation (no HTTP yet — just models, migration, utilities)
2. **Phase 3**: Health + admin registration → first running endpoint
3. **Phase 4**: Login / logout / refresh → complete auth session lifecycle
4. **Phases 5–7**: Invitation, role management, revocation (can be done in any order once Phase 4 passes)
5. **Phase 8**: Polish and cross-cutting test assertions

---

## Summary

| Metric | Count |
|--------|-------|
| Total tasks | 50 |
| Setup phase (Phase 1) | 8 |
| Foundation phase (Phase 2) | 16 |
| US1 — Admin Registration | 4 |
| US2 — Auth & Sessions | 4 |
| US3 — Invitations | 6 |
| US4 — Role Management | 4 |
| US5 — Revocation & Reactivation | 4 |
| Polish | 5 |
| Parallelizable [P] tasks | 22 |
| Test tasks | 12 |
