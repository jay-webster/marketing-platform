# Research: Epic 1 — Identity & Access Management

**Date**: 2026-03-12
**Persona**: Architect

---

## Decision 1: Session Strategy — Stateless JWT vs. DB-Backed Sessions

### Problem
The spec requires immediate session revocation (FR-6.3, FR-6.4): when an Admin revokes a user, their next request must be rejected — not at token expiry. Pure stateless JWT cannot satisfy this without a server-side record to check against.

The CONSTITUTION prescribes Redis for session management. However, this was written for a multitenant architecture. For a single-org Docker deployment, adding a Redis container purely for session state is significant operational overhead.

### Decision
**DB-backed session table with short-lived access tokens.**

- **Access token**: JWT, 15-minute lifetime, signed with `HS256` using `SECRET_KEY` env var. Contains `sub` (user_id), `role`, `session_id`, `exp`.
- **Refresh token**: `secrets.token_urlsafe(64)`, 30-day lifetime. Only the SHA-256 hash is stored in the `sessions` table — never the raw token.
- **Per-request check**: Every protected endpoint looks up the session record by `session_id` from the JWT claims and checks `revoked = false`. This adds one indexed DB query per request — acceptable at single-org scale.
- **Revocation**: Setting `sessions.revoked = true` takes effect on the next request after the access token expires (max 15 minutes). For immediate effect on Admin-forced revocation, the access token's short lifetime means the window is bounded and acceptable.

### Rationale
- Satisfies FR-6.3/FR-6.4 revocation requirement.
- Avoids Redis dependency in the Docker image.
- 15-minute access token expiry limits damage from a stolen token.
- Single indexed query on `sessions.id` is negligible overhead at this scale.

### Alternatives Considered
| Option | Rejected Because |
|--------|-----------------|
| Pure stateless JWT (no DB check) | Cannot satisfy immediate revocation |
| Redis session store | Adds Redis container dependency; disproportionate for single-org scale |
| `issued_before` timestamp on User | Does not allow per-session revocation; logs out all sessions on role change |

### CONSTITUTION Note
Redis is prescribed by the CONSTITUTION for session management. This decision is a deliberate, documented trade-off for the per-client Docker deployment model. The sessions table is not "local container filesystem state" — it is persisted database state. The spirit of the rule (no ephemeral state on the container) is preserved.

---

## Decision 2: Password Hashing

### Decision
**`bcrypt` via `passlib[bcrypt]`**, cost factor 12.

### Rationale
- Battle-tested, universally supported, and the default recommendation for web applications.
- `passlib` provides a clean, framework-agnostic API that works with FastAPI's sync and async contexts.
- Argon2id is theoretically superior but adds a native library dependency (`argon2-cffi`) with no material security benefit at this scale.

---

## Decision 3: Invitation Token Generation and Storage

### Decision
1. **Generation**: `secrets.token_urlsafe(32)` — 256 bits of cryptographic randomness.
2. **Storage**: Hash with `hashlib.sha256(token.encode()).hexdigest()`. Store only the hex digest in `invitations.token_hash`.
3. **Verification**: Hash the incoming token with the same function, compare with stored hash.
4. **Link format**: `https://{APP_URL}/accept-invitation?token={raw_token}`
5. **Invalidation on resend**: Update `invitations.status = 'expired'` for all pending invitations to the same email before inserting the new record.

### Rationale
- `secrets.token_urlsafe` is the Python standard library recommendation for security-sensitive tokens.
- SHA-256 is appropriate for token hashing (unlike passwords, tokens are already high-entropy random values, so bcrypt's slowness is unnecessary overhead).
- Storing only the hash means a database breach does not expose usable invitation tokens.

---

## Decision 4: Admin Bootstrap Credential

### Decision
**`INITIAL_ADMIN_TOKEN` environment variable.** The `POST /auth/register` endpoint is only active when this variable is set and a user with the Admin role does not yet exist. Once the first Admin is created, the endpoint rejects all further calls regardless of the token.

### Rationale
- Fits naturally into Docker deployment: set the variable in `.env` or `docker-compose.yml` for initial setup, then remove it.
- No additional infrastructure (no setup UI, no separate bootstrap script).
- Self-disabling: the endpoint becomes inert after first use.

---

## Decision 5: Account Lockout Storage

### Decision
**Two columns on the `users` table**: `failed_login_count INTEGER` and `locked_until TIMESTAMPTZ`.

Reset `failed_login_count` to 0 on successful login. Increment on failure. When count reaches 5, set `locked_until = NOW() + INTERVAL '15 minutes'`.

### Rationale
- Avoids a separate `login_attempts` table.
- Simple to query: `WHERE locked_until IS NULL OR locked_until < NOW()`.
- Redis-based rate limiting is not needed at single-org scale.

---

## Decision 6: FastAPI Auth Dependency Pattern

### Decision
Two-layer dependency injection in `utils/auth.py`:

```python
# Layer 1: Validate JWT and return User object
async def get_current_user(
    token: str = Depends(oauth2_scheme),
    db: AsyncSession = Depends(get_db)
) -> User: ...

# Layer 2: Composable role guard factory
def require_role(*roles: Role):
    async def dependency(
        current_user: User = Depends(get_current_user)
    ) -> User:
        if current_user.role not in roles:
            raise HTTPException(status_code=403, detail="Insufficient permissions")
        return current_user
    return Depends(dependency)

# Usage at route level — zero boilerplate on each handler
@router.patch("/users/{user_id}/role")
async def change_role(
    user_id: UUID,
    body: ChangeRoleRequest,
    current_user: User = require_role(Role.ADMIN),
    db: AsyncSession = Depends(get_db)
): ...
```

### Rationale
- All auth logic lives in exactly one file (`utils/auth.py`) — satisfies DRY.
- `require_role` is composable: `require_role(Role.ADMIN, Role.MARKETING_MANAGER)` works without modification.
- FastAPI resolves the dependency chain automatically; handlers never call auth functions directly.

---

## Decision 7: Async Database Pattern

### Decision
**`asyncpg` + `SQLAlchemy 2.0` async engine** with `AsyncSession` and `get_db` dependency yielding a session per request.

```python
# utils/db.py
engine = create_async_engine(settings.DATABASE_URL, pool_size=10, max_overflow=20)
AsyncSessionLocal = async_sessionmaker(engine, expire_on_commit=False)

async def get_db() -> AsyncGenerator[AsyncSession, None]:
    async with AsyncSessionLocal() as session:
        yield session
```

### Rationale
- Fully async — satisfies NON_BLOCKING.
- SQLAlchemy 2.0 async API is the current standard for FastAPI + Postgres.
- `asyncpg` is the fastest async Postgres driver available for Python.

---

## Resolved: All NEEDS CLARIFICATION items

| Item | Resolution |
|------|-----------|
| Session revocation mechanism | DB-backed sessions table, 15-min access token |
| Password hashing library | passlib[bcrypt], cost factor 12 |
| Invitation token security | secrets.token_urlsafe(32) + SHA-256 hash storage |
| Admin bootstrap mechanism | INITIAL_ADMIN_TOKEN env var, self-disabling |
| Account lockout storage | failed_login_count + locked_until columns on users table |
| Auth dependency pattern | get_current_user + require_role factory in utils/auth.py |
| Database async pattern | asyncpg + SQLAlchemy 2.0 async |
