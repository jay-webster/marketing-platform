# Data Model: Epic 1 — Identity & Access Management

**Branch**: `1-epic-1-iam-plan`
**Date**: 2026-03-12

---

## Entity Relationship Overview

```
users ──────────────────── sessions
  │  1                  0..*
  │
  │ 1                  0..*
  ├─────────────────────── invitations (issued_by)
  │
  │ 0..1               0..*
  └─────────────────────── audit_log (actor_id, target_id)
```

---

## Table: `users`

Primary user record. One row per registered person.

```sql
CREATE TABLE users (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    email               VARCHAR(255) UNIQUE NOT NULL,
    display_name        VARCHAR(255) NOT NULL,
    password_hash       VARCHAR(255) NOT NULL,
    role                VARCHAR(50) NOT NULL
                            CHECK (role IN ('admin', 'marketing_manager', 'marketer')),
    status              VARCHAR(50) NOT NULL DEFAULT 'active'
                            CHECK (status IN ('active', 'deactivated')),
    failed_login_count  INTEGER NOT NULL DEFAULT 0,
    locked_until        TIMESTAMPTZ,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    deactivated_at      TIMESTAMPTZ
);

CREATE INDEX idx_users_email ON users (email);
CREATE INDEX idx_users_role_status ON users (role, status);
```

### Field Notes
| Field | Constraint | Reason |
|-------|-----------|--------|
| `email` | UNIQUE NOT NULL | Login identifier; duplicate check at app layer too |
| `password_hash` | NOT NULL | bcrypt hash via passlib, never plaintext |
| `role` | CHECK enum | Enforced at DB and app layer |
| `failed_login_count` | DEFAULT 0 | Reset to 0 on successful login |
| `locked_until` | Nullable | NULL = not locked; value in past = lock expired |
| `deactivated_at` | Nullable | Populated when status → 'deactivated' |

### State Transitions: `status`
```
active ──[Admin revokes]──► deactivated
deactivated ──[Admin reactivates]──► active
```

### State Transitions: `role`
```
Any role ──[Admin changes role, target ≠ self]──► Any other role
Admin ──[Cannot change own role]──► (blocked)
```

### Validation Rules
- `email`: Valid email format, max 255 chars, lowercase-normalised on write.
- `display_name`: Non-empty, max 255 chars.
- `password`: Min 10 chars, ≥1 uppercase, ≥1 number, ≥1 special character (validated before hashing, not stored).
- **Last Admin guard**: Before `role` change away from `admin` OR `status` → `deactivated` for an admin: assert `SELECT COUNT(*) FROM users WHERE role = 'admin' AND status = 'active'` > 1.

---

## Table: `sessions`

One row per active refresh token. Access tokens are short-lived JWTs validated against this table.

```sql
CREATE TABLE sessions (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id             UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    refresh_token_hash  VARCHAR(64) NOT NULL,   -- SHA-256 hex digest of raw refresh token
    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    last_active_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    expires_at          TIMESTAMPTZ NOT NULL,   -- created_at + 30 days
    revoked             BOOLEAN NOT NULL DEFAULT FALSE,
    revoked_at          TIMESTAMPTZ
);

CREATE INDEX idx_sessions_user_id ON sessions (user_id);
CREATE INDEX idx_sessions_token_hash ON sessions (refresh_token_hash);
```

### Field Notes
| Field | Detail |
|-------|--------|
| `refresh_token_hash` | SHA-256 hex of raw token. Raw token never stored. |
| `expires_at` | `NOW() + INTERVAL '30 days'` at creation |
| `revoked` | Set TRUE by logout (self) or revocation (Admin) |

### Token Lifecycle
```
Login ──► create session row, issue JWT (session_id in claims) + refresh token
         │
         ▼
Each request ──► validate JWT signature → check sessions WHERE id = session_id
                 AND revoked = false AND expires_at > NOW()
         │
         ├── Logout ──► SET revoked = true, revoked_at = NOW()
         ├── Token refresh ──► validate refresh token hash, issue new JWT
         └── Admin revoke user ──► SET revoked = true WHERE user_id = target_user_id
```

### JWT Access Token Payload
```json
{
  "sub":        "user-uuid",
  "email":      "user@example.com",
  "role":       "admin",
  "session_id": "session-uuid",
  "iat":        1234567890,
  "exp":        1234567890
}
```
- Lifetime: **15 minutes**.
- Algorithm: `HS256`, key from `SECRET_KEY` environment variable.
- `session_id` enables per-request session lookup for revocation check.

---

## Table: `invitations`

One row per issued invitation. Tokens are single-use and time-limited.

```sql
CREATE TABLE invitations (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    invited_email   VARCHAR(255) NOT NULL,
    assigned_role   VARCHAR(50) NOT NULL
                        CHECK (assigned_role IN ('marketing_manager', 'marketer')),
    issued_by       UUID NOT NULL REFERENCES users(id),
    token_hash      VARCHAR(64) NOT NULL,   -- SHA-256 hex digest of raw token
    issued_at       TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    expires_at      TIMESTAMPTZ NOT NULL,   -- issued_at + 72 hours
    status          VARCHAR(50) NOT NULL DEFAULT 'pending'
                        CHECK (status IN ('pending', 'accepted', 'expired'))
);

CREATE INDEX idx_invitations_email_status ON invitations (invited_email, status);
CREATE INDEX idx_invitations_token_hash ON invitations (token_hash);
```

### Field Notes
| Field | Detail |
|-------|--------|
| `assigned_role` | Only `marketing_manager` or `marketer` — Admins cannot be invited |
| `token_hash` | SHA-256 hex of the raw token sent in the invitation email |
| `expires_at` | `issued_at + INTERVAL '72 hours'` |

### Token Generation
```python
import secrets, hashlib

raw_token = secrets.token_urlsafe(32)   # 256-bit URL-safe random token
token_hash = hashlib.sha256(raw_token.encode()).hexdigest()

# Store token_hash in DB; send raw_token in email link
link = f"{settings.APP_URL}/accept-invitation?token={raw_token}"
```

### Resend Logic
Before issuing a new invitation to the same email:
```sql
UPDATE invitations
SET status = 'expired'
WHERE invited_email = :email AND status = 'pending';
-- Then INSERT new invitation row
```

### Validation Rules
- Cannot invite an email that already has an active `users` record.
- Cannot invite with role `admin`.
- Token expires if `NOW() > expires_at` OR `status != 'pending'`.

---

## Table: `audit_log`

Immutable append-only event log. No updates or deletes.

```sql
CREATE TABLE audit_log (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    action      VARCHAR(100) NOT NULL,
    actor_id    UUID REFERENCES users(id) ON DELETE SET NULL,
    target_id   UUID REFERENCES users(id) ON DELETE SET NULL,
    metadata    JSONB,
    timestamp   TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_audit_log_actor ON audit_log (actor_id);
CREATE INDEX idx_audit_log_timestamp ON audit_log (timestamp DESC);
```

### Defined Action Values
| Action | Actor | Target | Metadata |
|--------|-------|--------|----------|
| `user_registered` | new user | null | `{role}` |
| `user_login` | user | null | `{ip_address?}` |
| `user_login_failed` | null | null | `{email, reason}` |
| `user_logout` | user | null | `{session_id}` |
| `user_locked` | null | user | `{locked_until}` |
| `invitation_sent` | admin | null | `{invited_email, assigned_role}` |
| `invitation_resent` | admin | null | `{invited_email}` |
| `invitation_accepted` | new user | null | `{invited_email, role}` |
| `role_changed` | admin | user | `{old_role, new_role}` |
| `access_revoked` | admin | user | `{}` |
| `user_reactivated` | admin | user | `{}` |

### Immutability Enforcement
Application layer must never issue `UPDATE` or `DELETE` against `audit_log`. Enforce via a dedicated write-only utility function:
```python
# utils/audit.py
async def write_audit(db, action, actor_id=None, target_id=None, metadata=None):
    entry = AuditLog(action=action, actor_id=actor_id,
                     target_id=target_id, metadata=metadata)
    db.add(entry)
    # Caller commits the transaction
```

---

## Alembic Migration Plan

Single migration file: `migrations/versions/001_create_iam_tables.py`

**Upgrade order** (respects foreign key constraints):
1. `users`
2. `sessions` (FK → users)
3. `invitations` (FK → users)
4. `audit_log` (FK → users)

**Downgrade order** (reverse):
1. `audit_log`
2. `invitations`
3. `sessions`
4. `users`

Every migration must implement both `upgrade()` and `downgrade()`.

---

## SQLAlchemy Model File Structure

```
marketing-platform/src/models/
├── __init__.py        ← exports Base, all models
├── base.py            ← DeclarativeBase, common mixins
├── user.py            ← User model + Role enum + Status enum
├── session.py         ← Session model
├── invitation.py      ← Invitation model + InvitationStatus enum
└── audit_log.py       ← AuditLog model
```
