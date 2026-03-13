# API Contracts: Epic 2 — GitHub Bridge

All endpoints require `Authorization: Bearer <access_token>` and Admin role.
All responses follow the standard envelope: `{ "data": ..., "request_id": "..." }`.
All error responses follow: `{ "detail": { "code": "...", "message": "..." }, "request_id": "..." }`.

---

## POST /api/v1/github/connect

Connect a GitHub repository. Validates the token and repo before storing. Triggers scaffolding after successful connection.

**Auth**: Admin role required.

**Request**:
```json
{
  "repository_url": "https://github.com/org/repo",
  "token": "github_pat_..."
}
```

**Responses**:

| Status | Code | Description |
|--------|------|-------------|
| 201 | — | Connection established and scaffolding complete |
| 400 | `INVALID_REPOSITORY_URL` | URL format is not a valid GitHub HTTPS URL |
| 400 | `CONFIG_INVALID` | Active repo structure config is malformed (scaffolding blocked) |
| 401 | — | Caller not authenticated |
| 403 | — | Caller is not Admin |
| 409 | `CONNECTION_ALREADY_EXISTS` | An active connection already exists; disconnect first |
| 422 | `TOKEN_INVALID` | Token not recognized or revoked by GitHub |
| 422 | `REPO_NOT_FOUND` | Repository does not exist or is not accessible with this token |
| 422 | `REPO_ACCESS_DENIED` | Token recognized but has no access to this repository |
| 422 | `INSUFFICIENT_PERMISSIONS` | Token lacks write access (`contents:write` required) |
| 503 | `GITHUB_UNAVAILABLE` | GitHub API unreachable or timed out (transient) |

**201 Response body**:
```json
{
  "data": {
    "connection_id": "uuid",
    "repository_url": "https://github.com/org/repo",
    "status": "active",
    "connected_at": "2026-03-13T10:00:00Z",
    "scaffolding": {
      "run_id": "uuid",
      "folders_created": 6,
      "folders_skipped": 0,
      "outcome": "success"
    }
  },
  "request_id": "uuid"
}
```

**Notes**:
- `token` is never returned in any response.
- If scaffolding fails after a successful connection, the connection is stored but `last_scaffolded_at` remains null. The scaffolding error is included in the response.

---

## GET /api/v1/github/connection

Get the current connection status.

**Auth**: Admin role required.

**Responses**:

| Status | Code | Description |
|--------|------|-------------|
| 200 | — | Connection info returned |
| 404 | `NO_CONNECTION` | No repository is connected |

**200 Response body**:
```json
{
  "data": {
    "connection_id": "uuid",
    "repository_url": "https://github.com/org/repo",
    "status": "active",
    "connected_at": "2026-03-13T10:00:00Z",
    "last_validated_at": "2026-03-13T10:00:00Z",
    "last_scaffolded_at": "2026-03-13T10:00:05Z",
    "token_on_file": true
  },
  "request_id": "uuid"
}
```

**Notes**:
- `token_on_file: true` confirms a token is stored. The token value is never returned.

---

## PATCH /api/v1/github/connection/token

Rotate the access token. Validates the new token before replacing the old one.

**Auth**: Admin role required.

**Request**:
```json
{
  "token": "github_pat_new..."
}
```

**Responses**:

| Status | Code | Description |
|--------|------|-------------|
| 200 | — | Token rotated successfully |
| 404 | `NO_CONNECTION` | No active connection to rotate token for |
| 422 | `TOKEN_INVALID` | New token not recognized by GitHub |
| 422 | `REPO_NOT_FOUND` | Repository no longer accessible with new token |
| 422 | `INSUFFICIENT_PERMISSIONS` | New token lacks required write permissions |
| 503 | `GITHUB_UNAVAILABLE` | GitHub unreachable during validation |

**200 Response body**:
```json
{
  "data": {
    "connection_id": "uuid",
    "last_validated_at": "2026-03-13T12:00:00Z"
  },
  "request_id": "uuid"
}
```

**Notes**:
- On any validation failure, the existing token is left unchanged.
- Old token is fully overwritten (not retained anywhere) on success.

---

## DELETE /api/v1/github/connection

Disconnect the repository. Removes stored credentials and suspends sync operations.

**Auth**: Admin role required.

**Responses**:

| Status | Code | Description |
|--------|------|-------------|
| 204 | — | Disconnected successfully |
| 404 | `NO_CONNECTION` | No active connection to disconnect |

**Notes**:
- The GitHub repository itself is not modified.
- The `github_connections` row transitions to `status = inactive`. It is not deleted.
- Any subsequent sync attempt returns `NO_CONNECTION`.

---

## POST /api/v1/github/scaffold

Trigger a scaffolding run on the currently connected repository.

**Auth**: Admin role required.

**Request**: No body required.

**Responses**:

| Status | Code | Description |
|--------|------|-------------|
| 200 | — | Scaffolding complete |
| 400 | `CONFIG_INVALID` | Repo structure config is malformed |
| 404 | `NO_CONNECTION` | No active repository connection |
| 503 | `GITHUB_UNAVAILABLE` | GitHub unreachable during scaffolding |

**200 Response body**:
```json
{
  "data": {
    "run_id": "uuid",
    "folders_created": 2,
    "folders_skipped": 4,
    "outcome": "success",
    "ran_at": "2026-03-13T10:05:00Z"
  },
  "request_id": "uuid"
}
```

---

## GET /api/v1/github/config

Get the current repository structure configuration.

**Auth**: Admin role required.

**Responses**:

| Status | Code | Description |
|--------|------|-------------|
| 200 | — | Config returned |

**200 Response body**:
```json
{
  "data": {
    "config_id": "uuid",
    "folders": [
      "content/campaigns",
      "content/assets/images",
      "content/assets/documents",
      "content/templates",
      "content/drafts",
      "content/published"
    ],
    "is_default": true,
    "updated_at": "2026-03-13T10:00:00Z"
  },
  "request_id": "uuid"
}
```

---

## PUT /api/v1/github/config

Replace the repository structure configuration.

**Auth**: Admin role required.

**Request**:
```json
{
  "folders": [
    "content/campaigns",
    "content/assets/images",
    "content/assets/documents",
    "content/templates"
  ]
}
```

**Responses**:

| Status | Code | Description |
|--------|------|-------------|
| 200 | — | Config updated |
| 400 | `CONFIG_INVALID` | Validation failed (empty, malformed, path traversal, etc.) |

**Validation error body**:
```json
{
  "detail": {
    "code": "CONFIG_INVALID",
    "message": "folders must be a non-empty list",
    "invalid_entries": []
  },
  "request_id": "uuid"
}
```
