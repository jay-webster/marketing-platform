# Data Model: Epic 2 — GitHub Bridge

**Branch**: `2-github-bridge`
**Date**: 2026-03-13

---

## Entity Overview

```
users (Epic 1)
    │
    ├──< github_connections (one active at a time)
    │         │
    │         └──< scaffolding_runs
    │
    └──< repo_structure_configs (one default, replaceable)
```

---

## Entity: `github_connections`

Represents the platform's link to a GitHub repository. At most one row may have `status = 'active'` at any time (enforced by partial unique index).

| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| `id` | UUID | PK, default gen_random_uuid() | |
| `repository_url` | TEXT | NOT NULL | Full HTTPS URL, e.g. `https://github.com/org/repo` |
| `encrypted_token` | TEXT | NOT NULL | Fernet-encrypted PAT, prefixed `v1:<ciphertext>`. Never plaintext. |
| `status` | VARCHAR(20) | NOT NULL, default `'active'` | `active` or `inactive` |
| `connected_by` | UUID | FK → users.id, NOT NULL | Admin who created this connection |
| `connected_at` | TIMESTAMPTZ | NOT NULL, default now() | |
| `last_validated_at` | TIMESTAMPTZ | NOT NULL | Updated on each successful validation |
| `last_scaffolded_at` | TIMESTAMPTZ | NULL | Null until first scaffolding run completes |

**Indexes**:
- `UNIQUE INDEX ON github_connections (status) WHERE status = 'active'` — enforces single active connection
- `INDEX ON github_connections (connected_by)`

**State transitions**:
```
[new] → active   (on successful connect)
active → inactive (on disconnect or new connection replacing it)
```

**Notes**:
- On disconnect: status transitions to `inactive`. Row is never deleted (audit history).
- On token rotation: `encrypted_token` and `last_validated_at` are updated in-place on the existing `active` row.
- Token is decrypted only at the moment it is needed for a GitHub API call. Never returned in any API response.

---

## Entity: `repo_structure_configs`

Defines the folder hierarchy to be created during scaffolding. One config is active at a time; the platform ships with a default that Admins can replace.

| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| `id` | UUID | PK, default gen_random_uuid() | |
| `folders` | JSONB | NOT NULL | Flat array of folder path strings |
| `is_default` | BOOLEAN | NOT NULL, default false | True for the platform-seeded default config |
| `created_by` | UUID | FK → users.id, NULL | Null for the seeded default |
| `updated_at` | TIMESTAMPTZ | NOT NULL, default now() | |

**Indexes**:
- `INDEX ON repo_structure_configs (is_default)`

**JSONB schema** (validated at application layer):
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

**Validation rules** (enforced in service layer):
- `folders` must be a non-empty array.
- Each entry: non-empty string, no leading/trailing slashes, no `..` sequences.
- Maximum 200 entries.

**Notes**:
- Only one `repo_structure_config` exists at a time for MVP. The default is seeded on first startup if no config exists.
- `PUT /api/v1/github/config` replaces the current config entirely (upsert on `is_default = false`).

---

## Entity: `scaffolding_runs`

Immutable record of each scaffolding execution. Never updated after creation.

| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| `id` | UUID | PK, default gen_random_uuid() | |
| `connection_id` | UUID | FK → github_connections.id, NOT NULL | |
| `triggered_by` | UUID | FK → users.id, NULL | Null if system-triggered |
| `ran_at` | TIMESTAMPTZ | NOT NULL, default now() | |
| `folders_created` | INTEGER | NOT NULL, default 0 | Count of folders created in this run |
| `folders_skipped` | INTEGER | NOT NULL, default 0 | Count of folders already present |
| `outcome` | VARCHAR(20) | NOT NULL | `success` or `failed` |
| `error_detail` | TEXT | NULL | Human-readable error if outcome is `failed` |

**Indexes**:
- `INDEX ON scaffolding_runs (connection_id, ran_at DESC)`

**Notes**:
- Rows are append-only. No UPDATE or DELETE.
- `error_detail` must never contain the GitHub token value.

---

## Audit Log Events (extends Epic 1)

Uses the existing `audit_log` table from Epic 1. New `action` values for this epic:

| `action` value | `target_id` | `metadata` keys |
|----------------|-------------|-----------------|
| `github_connected` | github_connections.id | `{ "repository_url": "..." }` |
| `github_token_rotated` | github_connections.id | `{ "repository_url": "..." }` |
| `github_disconnected` | github_connections.id | `{ "repository_url": "..." }` |
| `github_scaffolded` | scaffolding_runs.id | `{ "outcome": "success/failed", "folders_created": N, "folders_skipped": N }` |
| `github_validation_failed` | null | `{ "reason": "TOKEN_INVALID/REPO_NOT_FOUND/etc", "repository_url": "..." }` |

**Security note**: `repository_url` is safe to log. The token value is never included in any `metadata` field.

---

## New Environment Variables

| Variable | Purpose | Required |
|----------|---------|----------|
| `GITHUB_TOKEN_ENCRYPTION_KEY` | Fernet key for encrypting/decrypting stored PATs | Yes |

Generated once via:
```bash
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```
