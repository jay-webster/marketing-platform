# Research: Epic 2 — GitHub Bridge

**Date**: 2026-03-13
**Status**: Complete — all questions resolved

---

## Decision 1: Token Encryption

**Decision**: Use `cryptography.fernet.Fernet` (AES-128-CBC + HMAC-SHA256).

**Rationale**:
- `cryptography` is already a project dependency (pulled in by `python-jose[cryptography]`).
- Fernet handles nonce generation automatically — eliminates nonce-reuse bugs that plague manual AES-GCM implementations.
- Built-in HMAC prevents ciphertext tampering; decrypt raises `InvalidToken` on any modification.
- Produces a single URL-safe base64 string — trivially stored in a `TEXT` column.

**Implementation**:
- Encryption key stored in env var `GITHUB_TOKEN_ENCRYPTION_KEY` (base64-encoded 32-byte key).
- Encrypted value prefixed with version tag (`v1:<fernet_ciphertext>`) to support future key rotation without a hard cutover.
- Key is never stored in the database. If the key is absent at startup, the app refuses to start (fail-closed).

**Alternatives considered**:
- AES-256-GCM (hazmat layer): more control, but requires manual nonce management — unnecessary risk for this use case.
- GCP Secret Manager for the key: correct long-term solution; deferred to infrastructure setup. For MVP, env var is acceptable.

**Key rotation path** (documented, not implemented in this epic):
- On rotation, add `GITHUB_TOKEN_ENCRYPTION_KEY_V2` to env.
- Background task re-encrypts all `v1:` tokens to `v2:`.
- Remove `v1` key and env var once migration is confirmed complete.

---

## Decision 2: GitHub API Client

**Decision**: Build a thin async client in `utils/github_api.py` using `httpx` (already a project dependency via test suite).

**Rationale**:
- `httpx` is already present and used for async HTTP in tests — no new dependency.
- The existing `utils/github_client.py` uses `subprocess git` for clone/sync operations, which is a separate concern (content ingestion, Epic 3). The REST API validation + scaffolding concern belongs in its own module.
- A thin client avoids the heavyweight `PyGitHub` SDK and keeps the code auditable.

**Validation flow**:
1. `GET https://api.github.com/user` — confirms token is recognized (200) vs. invalid/revoked (401).
2. `GET https://api.github.com/repos/{owner}/{repo}` — confirms repo is accessible (200/403/404) and checks `permissions.push == true` for write access.
3. These are two separate HTTP calls, with distinct error codes mapped to distinct user-facing error codes.

**Status code → error code mapping**:

| Call | HTTP Status | Error Code |
|------|-------------|------------|
| GET /user | 401 | `TOKEN_INVALID` |
| GET /user | 5xx / timeout | `GITHUB_UNAVAILABLE` |
| GET /repos/{owner}/{repo} | 404 | `REPO_NOT_FOUND` |
| GET /repos/{owner}/{repo} | 403 | `REPO_ACCESS_DENIED` |
| GET /repos/{owner}/{repo} | 200 + push=false | `INSUFFICIENT_PERMISSIONS` |
| GET /repos/{owner}/{repo} | 5xx / timeout | `GITHUB_UNAVAILABLE` |

**Timeout**: 10 seconds (matches FR-3.7 and A-7). Implemented as `httpx.Timeout(10.0, connect=5.0)`.

**Missing permissions detail**: When `push=false`, the error response includes `missing_permissions: ["contents:write"]` to satisfy FR-3.4.

---

## Decision 3: Folder Scaffolding Mechanism

**Decision**: Create `.gitkeep` placeholder files to establish folder paths. This supersedes spec Assumption A-4.

**Rationale**:
- GitHub does not track empty directories. A Git repository has no concept of an empty folder — only files at paths.
- Creating a folder on GitHub requires creating at least one file within it. The universal convention for this is an empty `.gitkeep` file.
- A-4 was written without awareness of this Git/GitHub constraint and cannot be satisfied as stated.

**Impact on A-4**: Scaffolding creates `.gitkeep` files as a necessary implementation detail of folder creation. From the user's perspective, the folders exist and are ready for content. The `.gitkeep` files are invisible to marketing workflows.

**Scaffolding algorithm**:
```
for each folder_path in config.folders (flattened from hierarchy):
    path = f"{folder_path}/.gitkeep"
    GET /repos/{owner}/{repo}/contents/{path}
    if 404:   → create file (PUT), count as "created"
    if 200:   → skip, count as "skipped"
    if error: → abort run, record as Failed
```

**Idempotency**: Checking for existence before creating ensures re-runs are safe. A 422 on PUT (already exists due to race) is treated as "skipped."

---

## Decision 4: Repository Structure Configuration Format

**Decision**: Store configuration as a JSONB column in the database. Format is a flat list of folder paths.

**Rationale**:
- FR-4.2 requires Admins to modify the configuration — database storage is simpler than managing config files.
- A flat list of paths (e.g., `["content/campaigns", "content/assets/images"]`) is easier to validate, diff, and process than a nested tree structure.
- Nesting is implicit in path strings (`content/assets/images` creates `content/`, `content/assets/`, `content/assets/images/`).

**Default configuration** (seeded on first startup):
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

**Validation rules**:
- `folders` key must be present and non-empty array.
- Each entry must be a non-empty string with no leading/trailing slashes.
- No path traversal sequences (`..`).
- Max 200 folder entries (prevents abuse).

---

## Decision 5: Single Active Connection Enforcement

**Decision**: Enforce via a partial unique index: `CREATE UNIQUE INDEX ON github_connections (status) WHERE status = 'active'`.

**Rationale**:
- Only one row can have `status = 'active'` at a time — enforced at the database level, not just the application layer.
- Inactive/disconnected connections are preserved as history (no delete on disconnect — status transitions to `inactive`).
- This satisfies A-1 without requiring application-level locking.

---

## Constitution Compliance Pre-Check

| Label | Status | Notes |
|-------|--------|-------|
| **AUTH_SAFE** | PASS | All GitHub endpoints require `Admin` role via `require_role(Role.ADMIN)` from Epic 1. |
| **DRY** | PASS | Token encryption in `utils/crypto.py`. GitHub API in `utils/github_api.py`. DB via `utils/db.py`. Audit via `utils/audit.py`. |
| **NON_BLOCKING** | PASS | `httpx.AsyncClient` for all GitHub calls. SQLAlchemy async for all DB operations. No blocking I/O. |
