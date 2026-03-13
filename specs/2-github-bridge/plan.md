# Implementation Plan: Epic 2 — GitHub Bridge

**Branch**: `2-github-bridge`
**Spec**: `specs/2-github-bridge/spec.md`
**Status**: Ready for `/speckit.tasks`
**Date**: 2026-03-13

---

## Constitution Compliance Check

| Label | Status | How It Is Satisfied |
|-------|--------|---------------------|
| **AUTH_SAFE** | PASS | All 7 endpoints use `Depends(require_role(Role.ADMIN))` from Epic 1. No endpoint accesses the DB or GitHub API without a validated Admin session. |
| **DRY** | PASS | Token encryption in `utils/crypto.py`. GitHub REST API client in `utils/github_api.py`. DB via `utils/db.py`. Audit via `utils/audit.py`. No logic duplicated across modules. |
| **NON_BLOCKING** | PASS | `httpx.AsyncClient` for GitHub API calls. SQLAlchemy 2.0 async for all DB operations. FastAPI async handlers throughout. No blocking I/O. |

---

## Architecture Overview

```
Admin (JWT Bearer)
     │
     ▼
FastAPI — src/api/github.py (Admin-only router)
     │
     ├── utils/github_api.py     ← async httpx GitHub REST API client
     │       ├── validate_token()       GET /user
     │       ├── check_repo_access()    GET /repos/{owner}/{repo}
     │       └── scaffold_folders()     GET + PUT /repos/{owner}/{repo}/contents/
     │
     ├── utils/crypto.py         ← Fernet token encryption/decryption
     │
     ├── utils/db.py             ← async SQLAlchemy session (Epic 1, reused)
     ├── utils/auth.py           ← require_role() (Epic 1, reused)
     └── utils/audit.py          ← write_audit() (Epic 1, reused)
          │
          ▼
     PostgreSQL
          ├── github_connections
          ├── repo_structure_configs
          └── scaffolding_runs
          └── audit_log (Epic 1, extended)
```

---

## Tech Stack

### Existing (reused from Epic 1)
| Component | Library |
|-----------|---------|
| Web framework | FastAPI |
| Async HTTP client | `httpx` (already in deps via test suite) |
| ORM | SQLAlchemy 2.0 async |
| DB driver | asyncpg |
| Migrations | Alembic |
| Auth | JWT via `utils/auth.py` |
| Audit | `utils/audit.py` |

### New Dependencies
| Library | Version | Purpose |
|---------|---------|---------|
| `cryptography` | already installed (via `python-jose[cryptography]`) | Fernet encryption for GitHub tokens |
| `respx` | latest | Mock `httpx` calls in tests |

Add to `requirements.txt`:
```
respx
```

---

## File Structure

```
src/
  models/
    github_connection.py       ← GitHubConnection model
    repo_structure_config.py   ← RepoStructureConfig model
    scaffolding_run.py         ← ScaffoldingRun model
  api/
    github.py                  ← All GitHub Bridge endpoints (7 routes)

utils/
  crypto.py                    ← Fernet encrypt/decrypt for PATs
  github_api.py                ← Async GitHub REST API client

migrations/
  versions/
    003_create_github_tables.py

tests/
  api/
    test_github.py             ← Integration tests for all 7 endpoints
  utils/
    test_crypto.py             ← Unit tests for crypto utilities
    test_github_api.py         ← Unit tests for GitHub API client (mocked with respx)
```

---

## Module Designs

### `utils/crypto.py`

```python
# Fernet symmetric encryption for PAT storage.
# Key loaded from GITHUB_TOKEN_ENCRYPTION_KEY env var.
# Encrypted values are prefixed: "v1:<fernet_ciphertext>"

def encrypt_token(plaintext: str) -> str: ...
def decrypt_token(ciphertext: str) -> str: ...
```

- Raises `EnvironmentError` at import if `GITHUB_TOKEN_ENCRYPTION_KEY` is not set.
- Raises `ValueError` if version prefix is unsupported (future-proofs key rotation).
- Fernet raises `cryptography.fernet.InvalidToken` if ciphertext is tampered.

---

### `utils/github_api.py`

```python
class GitHubValidationError(Exception):
    def __init__(self, code: str, message: str, missing_permissions: list[str] | None = None): ...

class GitHubUnavailableError(Exception): ...

async def validate_and_check_access(repository_url: str, token: str) -> None:
    """
    Two-step validation:
    1. GET /user — confirms token is valid
    2. GET /repos/{owner}/{repo} — confirms repo exists and push=true

    Raises GitHubValidationError with appropriate error code on failure.
    Raises GitHubUnavailableError on timeout or 5xx.
    Timeout: httpx.Timeout(10.0, connect=5.0)
    """

async def scaffold_repository(
    repository_url: str,
    token: str,
    folders: list[str],
) -> tuple[int, int]:
    """
    For each folder path, check existence and create .gitkeep if missing.
    Returns (folders_created, folders_skipped).
    """
```

**Error code mapping**:
```
GET /user 401          → GitHubValidationError("TOKEN_INVALID")
GET /repos 404         → GitHubValidationError("REPO_NOT_FOUND")
GET /repos 403         → GitHubValidationError("REPO_ACCESS_DENIED")
GET /repos push=false  → GitHubValidationError("INSUFFICIENT_PERMISSIONS", missing=["contents:write"])
any 5xx / timeout      → GitHubUnavailableError
```

---

### `src/api/github.py`

```python
router = APIRouter(prefix="/github", tags=["github"])

# All routes use: dependencies=[Depends(require_role(Role.ADMIN))]

POST   /connect              → connect_repository()
GET    /connection           → get_connection()
PATCH  /connection/token     → rotate_token()
DELETE /connection           → disconnect()
POST   /scaffold             → run_scaffold()
GET    /config               → get_config()
PUT    /config               → update_config()
```

**Connect flow** (`POST /connect`):
1. Check no active connection exists → 409 if one does.
2. Validate `repository_url` format.
3. Call `validate_and_check_access(url, token)` — raises on failure, nothing stored.
4. Encrypt token via `crypto.encrypt_token()`.
5. Insert `GitHubConnection` row with `status=active`.
6. `await db.flush()` to get `connection.id`.
7. Load active `RepoStructureConfig`, validate it.
8. Call `scaffold_repository()`, capture `(created, skipped)`.
9. Insert `ScaffoldingRun` record.
10. Update `connection.last_scaffolded_at`.
11. `write_audit(db, action="github_connected", ...)`.
12. `await db.commit()`.
13. Return 201 with connection + scaffolding summary.

**Token rotation flow** (`PATCH /connection/token`):
1. Fetch active connection → 404 if none.
2. Call `validate_and_check_access(connection.repository_url, new_token)` — on failure, return error, connection unchanged.
3. Update `connection.encrypted_token = crypto.encrypt_token(new_token)`.
4. Update `connection.last_validated_at = now()`.
5. `write_audit(db, action="github_token_rotated", ...)`.
6. `await db.commit()`.
7. Return 200.

**Disconnect flow** (`DELETE /connection`):
1. Fetch active connection → 404 if none.
2. Set `connection.status = "inactive"`.
3. `write_audit(db, action="github_disconnected", ...)`.
4. `await db.commit()`.
5. Return 204.

---

## Database Migrations

### `003_create_github_tables.py`

```sql
-- github_connections
CREATE TABLE github_connections (
    id               UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    repository_url   TEXT NOT NULL,
    encrypted_token  TEXT NOT NULL,
    status           VARCHAR(20) NOT NULL DEFAULT 'active',
    connected_by     UUID NOT NULL REFERENCES users(id),
    connected_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
    last_validated_at TIMESTAMPTZ NOT NULL,
    last_scaffolded_at TIMESTAMPTZ
);
CREATE UNIQUE INDEX ix_github_connections_one_active
    ON github_connections (status) WHERE status = 'active';
CREATE INDEX ix_github_connections_connected_by
    ON github_connections (connected_by);

-- repo_structure_configs
CREATE TABLE repo_structure_configs (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    folders     JSONB NOT NULL,
    is_default  BOOLEAN NOT NULL DEFAULT false,
    created_by  UUID REFERENCES users(id),
    updated_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX ix_repo_structure_configs_is_default
    ON repo_structure_configs (is_default);

-- scaffolding_runs
CREATE TABLE scaffolding_runs (
    id               UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    connection_id    UUID NOT NULL REFERENCES github_connections(id),
    triggered_by     UUID REFERENCES users(id),
    ran_at           TIMESTAMPTZ NOT NULL DEFAULT now(),
    folders_created  INTEGER NOT NULL DEFAULT 0,
    folders_skipped  INTEGER NOT NULL DEFAULT 0,
    outcome          VARCHAR(20) NOT NULL,
    error_detail     TEXT
);
CREATE INDEX ix_scaffolding_runs_connection_id
    ON scaffolding_runs (connection_id, ran_at DESC);
```

---

## Default Config Seeding

On application startup (in `_lifespan`), if no `repo_structure_configs` row exists, insert the default:

```json
{
  "folders": [
    "content/campaigns",
    "content/assets/images",
    "content/assets/documents",
    "content/templates",
    "content/drafts",
    "content/published"
  ]
}
```

---

## Test Strategy

### Unit Tests (`tests/utils/test_crypto.py`)
- Encrypt → decrypt roundtrip produces original value
- Wrong key raises `InvalidToken`
- Missing env var raises at import/init time
- Version prefix is present in ciphertext

### Unit Tests (`tests/utils/test_github_api.py`)
- Mock with `respx`. Test each error code mapping.
- `TOKEN_INVALID` on `GET /user → 401`
- `REPO_NOT_FOUND` on `GET /repos → 404`
- `INSUFFICIENT_PERMISSIONS` on `push=false`
- `GITHUB_UNAVAILABLE` on timeout
- Scaffold: creates folders that don't exist, skips those that do

### Integration Tests (`tests/api/test_github.py`)
- Happy path: connect → check status → re-scaffold (idempotent)
- Invalid token rejected, nothing stored
- Insufficient permissions rejected, nothing stored
- Token rotation success and failure paths
- Disconnect + reconnect
- Config update → connect uses new config
- Non-admin cannot access any endpoint (403)
- Token value never appears in any response body

---

## Key Technical Constraints

1. **Token security**: `decrypt_token()` is called only inside `validate_and_check_access()` and `scaffold_repository()`. The plaintext token must never be assigned to a variable that is logged, returned in a response, or stored in any exception message.

2. **Atomic validation**: No DB write occurs until `validate_and_check_access()` returns without raising. If validation raises, no connection row is created, no audit entry is written, and no exception propagates upward with token data.

3. **Scaffolding on connect**: Scaffolding failure after a successful connection does not roll back the connection. The connection is stored, `last_scaffolded_at` remains null, and the response includes the scaffolding error. The Admin can re-run scaffolding manually.

4. **Config validation at scaffold time**: The config is validated immediately before scaffolding begins, not when it is saved. This means a bad config blocks scaffolding but does not prevent saving the config.

5. **Assumption A-4 override**: `.gitkeep` files are created to establish folders (see `research.md` Decision 3). This is a necessary implementation detail — GitHub does not support empty directories.
