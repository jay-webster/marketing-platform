# Quickstart & Integration Scenarios: Epic 2 — GitHub Bridge

**Date**: 2026-03-13

---

## Environment Setup

Add to `.env`:
```bash
# Generate once — never commit this value
GITHUB_TOKEN_ENCRYPTION_KEY=<output of: python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())">
```

---

## Scenario 1: Happy Path — Connect, Scaffold, View Status

```python
# Step 1: Connect a repository
POST /api/v1/github/connect
Authorization: Bearer <admin_access_token>
{
  "repository_url": "https://github.com/acme/marketing-content",
  "token": "github_pat_..."
}

# Expected: 201
# - connection stored with status=active
# - scaffolding runs automatically
# - response includes folders_created count

# Step 2: View connection status
GET /api/v1/github/connection
Authorization: Bearer <admin_access_token>

# Expected: 200
# - status: active
# - token_on_file: true (never shows actual token)
# - last_scaffolded_at: populated

# Step 3: Re-run scaffolding (idempotent)
POST /api/v1/github/scaffold
Authorization: Bearer <admin_access_token>

# Expected: 200
# - folders_created: 0 (all already exist)
# - folders_skipped: 6 (all skipped)
```

---

## Scenario 2: Invalid Token

```python
POST /api/v1/github/connect
{
  "repository_url": "https://github.com/acme/marketing-content",
  "token": "github_pat_INVALID"
}

# Expected: 422
# { "detail": { "code": "TOKEN_INVALID", "message": "The token was not recognized by GitHub. Verify the token is valid and has not been revoked." } }
# Nothing is stored in the database.
```

---

## Scenario 3: Valid Token, Insufficient Permissions

```python
POST /api/v1/github/connect
{
  "repository_url": "https://github.com/acme/marketing-content",
  "token": "github_pat_READONLY"  # read-only token
}

# Expected: 422
# { "detail": { "code": "INSUFFICIENT_PERMISSIONS", "message": "The token is valid but does not have write access to this repository.", "missing_permissions": ["contents:write"] } }
```

---

## Scenario 4: Token Rotation

```python
# Rotate to a new token
PATCH /api/v1/github/connection/token
{
  "token": "github_pat_NEW..."
}

# Expected: 200
# Old token is fully replaced.

# Failed rotation (bad new token) leaves existing token intact:
PATCH /api/v1/github/connection/token
{
  "token": "github_pat_INVALID"
}

# Expected: 422, TOKEN_INVALID
# Existing token unchanged.
```

---

## Scenario 5: Disconnect and Reconnect

```python
# Disconnect
DELETE /api/v1/github/connection

# Expected: 204
# Connection row transitions to status=inactive.

# Attempt sync after disconnect
POST /api/v1/github/scaffold

# Expected: 404, NO_CONNECTION

# Reconnect
POST /api/v1/github/connect
{
  "repository_url": "https://github.com/acme/marketing-content",
  "token": "github_pat_..."
}

# Expected: 201
# New connection row created. Scaffolding runs.
# folders_skipped: 6 (folders already exist from first scaffolding)
```

---

## Scenario 6: Custom Structure Config

```python
# Update structure config before connecting
PUT /api/v1/github/config
{
  "folders": [
    "campaigns/q1",
    "campaigns/q2",
    "assets/logos",
    "assets/banners"
  ]
}

# Expected: 200

# Connect — will scaffold using the new config
POST /api/v1/github/connect
{
  "repository_url": "https://github.com/acme/marketing-content",
  "token": "github_pat_..."
}

# Expected: 201, folders_created: 4
```

---

## Scenario 7: GitHub Unavailable (Transient)

```python
POST /api/v1/github/connect
{ ... }

# GitHub API times out after 10 seconds

# Expected: 503
# { "detail": { "code": "GITHUB_UNAVAILABLE", "message": "GitHub could not be reached. This is a temporary issue — please try again shortly." } }
# Nothing stored. Admin can retry without re-entering token.
```

---

## Test Infrastructure Notes

- GitHub API calls must be mocked in tests using `respx` (httpx mock library) or `unittest.mock.patch`.
- Tests must verify that no plaintext token appears in DB after connect.
- Tests must verify that failed validation leaves `github_connections` table empty.
- Token encryption key for tests: use a test-specific Fernet key set in `TEST_GITHUB_TOKEN_ENCRYPTION_KEY` or patched via `monkeypatch`.
