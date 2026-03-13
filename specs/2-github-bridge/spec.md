# Epic 2: The GitHub Bridge

**Branch**: `2-github-bridge`
**Status**: Draft
**Created**: 2026-03-12

---

## Overview

The marketing content-as-code model depends entirely on a live connection to a GitHub repository. Without that connection, the platform has nowhere to read from or write to. This epic establishes the bridge: the workflow by which an Administrator securely links the organization's GitHub repository to the platform, verifies the connection works, and initializes the repository with a predictable folder structure that all subsequent content operations will depend on.

This epic is the platform's second critical foundation layer. Epic 1 established *who* can act. This epic establishes *where* content lives.

---

## Goals

1. Allow Admins to connect a GitHub repository to the platform by providing a repository address and a personal access token, with the platform verifying the connection before accepting and storing the credential.
2. Ensure that stored credentials are protected: never visible in logs, error messages, or system responses, and never retained in an unprotected form.
3. Give Admins actionable, specific error messages when a connection attempt fails, so they can resolve the issue without guesswork.
4. Automatically initialize the connected repository with a standard folder structure, driven by a configuration file, so that all content operations have a consistent, predictable layout to work within.
5. Keep scaffolding safe to re-run: applying it to an already-initialized repository must never overwrite or destroy existing content.

---

## User Scenarios & Testing

### Scenario 1: Admin Connects a Repository for the First Time

**Actor**: Admin
**Precondition**: Admin is logged in. No GitHub repository is currently connected.

1. Admin navigates to the repository connection screen.
2. Admin provides the repository address and a personal access token with appropriate permissions.
3. The platform contacts GitHub to verify the token is valid and has the required level of access to the specified repository.
4. Validation succeeds. The platform stores the credential securely and displays a confirmed connection status.
5. The platform reads the repository structure configuration and creates the defined folder layout in the connected repository.
6. The Admin sees a summary of what was created (folders added) and the connection is marked active.

**Acceptance**:
- The connection is only stored after validation succeeds. A failed validation stores nothing.
- The token provided by the Admin is not visible in any response, log, or confirmation message after submission.
- The repository's folder structure matches the configuration after scaffolding completes.

---

### Scenario 2: Connection Attempt with an Invalid Token

**Actor**: Admin
**Precondition**: Admin is logged in.

1. Admin provides a repository address and a token that does not exist or has been revoked.
2. The platform attempts to validate the token against GitHub.
3. Validation fails. The platform returns an error indicating the token is not recognized.
4. Nothing is stored. The Admin is prompted to check the token and try again.

**Acceptance**: The error message identifies the nature of the problem (unrecognized token) without exposing the token value itself or any internal system detail.

---

### Scenario 3: Connection Attempt with Insufficient Permissions

**Actor**: Admin
**Precondition**: Admin is logged in.

1. Admin provides a repository address and a valid token, but the token does not grant sufficient access to the specified repository.
2. The platform validates the token successfully but determines permissions are inadequate.
3. The platform returns an error that names the specific permission(s) the token is missing.
4. Nothing is stored. The Admin is directed to update the token's permissions and retry.

**Acceptance**: The error clearly differentiates "token not recognized" (Scenario 2) from "token recognized but insufficient permissions" (this scenario). The missing permissions are named specifically enough for the Admin to act without additional research.

---

### Scenario 4: Connection Attempt with an Inaccessible Repository

**Actor**: Admin
**Precondition**: Admin is logged in.

1. Admin provides a repository address that either does not exist or is not accessible under the provided token.
2. Validation returns that the repository cannot be found or accessed.
3. The platform returns an error explaining the repository could not be reached.
4. Nothing is stored.

**Acceptance**: Error distinguishes between "repository does not exist" and "repository exists but token owner has no access" where GitHub's API permits this distinction.

---

### Scenario 5: GitHub Is Temporarily Unreachable

**Actor**: Admin
**Precondition**: Admin is logged in. GitHub API is unavailable.

1. Admin submits a connection attempt.
2. The platform's validation request to GitHub times out or receives a service error.
3. The platform returns a transient error indicating GitHub could not be reached and advises the Admin to try again shortly.
4. Nothing is stored.

**Acceptance**: The error is clearly marked as transient (not the Admin's fault). No credentials are stored. The Admin is not required to re-enter the token — the form retains their input (minus the token, which is cleared for security).

---

### Scenario 6: Admin Views Connection Status

**Actor**: Admin
**Precondition**: Admin is logged in.

1. Admin navigates to the connection status screen.
2. The platform displays: whether a repository is connected, the repository address, when the connection was established, and when scaffolding last ran.
3. The token itself is never displayed — only a masked indicator confirming one is on file.

**Acceptance**: The token value is never shown, even partially. A visual indicator (e.g., "Token on file — last validated [date]") is sufficient.

---

### Scenario 7: Admin Rotates the Access Token

**Actor**: Admin
**Precondition**: A repository is currently connected.

1. Admin initiates a token rotation.
2. Admin provides the new token.
3. The platform validates the new token against the same repository currently connected.
4. Validation succeeds. The old token is replaced with the new one. Connection status remains active.
5. No re-scaffolding occurs — the repository structure is not modified.

**Acceptance**:
- The old token is fully replaced and no longer retained in any form.
- A failed validation during rotation leaves the existing token in place and unchanged.
- Rotation is logged with the Admin's identity and a timestamp. The token values are not logged.

---

### Scenario 8: Admin Disconnects the Repository

**Actor**: Admin
**Precondition**: A repository is currently connected.

1. Admin initiates disconnection.
2. The platform removes the stored credential and marks the repository connection as inactive.
3. The repository itself (on GitHub) is not modified. No folders are deleted.
4. Content sync operations are suspended until a new connection is established.

**Acceptance**: After disconnection, any attempt to sync content returns a clear error indicating no repository is connected, rather than a silent failure.

---

### Scenario 9: Scaffolding Is Re-Run on an Already-Initialized Repository

**Actor**: Admin or System
**Precondition**: A repository is connected and has already been scaffolded.

1. Admin triggers re-scaffolding (or the platform triggers it automatically after a configuration update).
2. The platform reads the current structure configuration.
3. Any folders already present in the repository are left untouched.
4. Any folders defined in the configuration that are absent from the repository are created.
5. No existing content is deleted or moved.

**Acceptance**: The repository's state after re-scaffolding is identical to what it would be if scaffolded fresh — minus any content that existed before. Specifically: no duplicate folders, no deleted folders, no modified files.

---

## Functional Requirements

### FR-1: Repository Connection

| ID | Requirement |
|----|-------------|
| FR-1.1 | Only users with the Admin role can initiate, modify, or remove a repository connection. |
| FR-1.2 | The application may have at most one active repository connection at a time. |
| FR-1.3 | To connect a repository, the Admin must provide a repository address and a personal access token. |
| FR-1.4 | The platform must validate the token and repository before storing any credential. |
| FR-1.5 | The repository must already exist — this feature does not create repositories on GitHub. |
| FR-1.6 | Connection status (active, inactive, validation pending) is visible to Admins at all times. |

---

### FR-2: Credential Security

| ID | Requirement |
|----|-------------|
| FR-2.1 | Access tokens must never be stored in plaintext. They must be encrypted before being written to any persistent store. |
| FR-2.2 | Access tokens must never appear in application logs, error messages, API responses, or audit log entries — not even partially or masked beyond the last 4 characters. |
| FR-2.3 | The UI must not redisplay the token after it has been submitted, including in form fields. |
| FR-2.4 | Encryption keys used to protect tokens must not be stored alongside the tokens they protect. |
| FR-2.5 | Token rotation replaces the stored credential atomically — the old token must not be readable after the new one is confirmed stored. |

---

### FR-3: Validation & Error Handling

| ID | Requirement |
|----|-------------|
| FR-3.1 | The platform must check that the provided token is recognized by GitHub before accepting it. |
| FR-3.2 | The platform must check that the token grants the required minimum permissions on the specified repository. |
| FR-3.3 | If the token is unrecognized or revoked, the error message must identify this as a credential problem without exposing the token. |
| FR-3.4 | If the token is valid but permissions are insufficient, the error must identify which specific permissions are missing. |
| FR-3.5 | If the repository is not found or not accessible under the provided token, the error must indicate this distinctly from a credential failure. |
| FR-3.6 | If GitHub is temporarily unreachable, the error must be marked as transient, distinguish itself from a credential or permission error, and advise the Admin to retry. |
| FR-3.7 | A validation attempt that times out after a reasonable wait (default: 10 seconds) is treated as a transient failure under FR-3.6. |
| FR-3.8 | No connection attempt that results in an error may leave any partial or temporary credential data in any store. |

---

### FR-4: Repository Structure Configuration

| ID | Requirement |
|----|-------------|
| FR-4.1 | The platform ships with a default repository structure configuration defining a standard folder layout for marketing content repositories. |
| FR-4.2 | Admins may replace or modify the repository structure configuration before or after scaffolding. |
| FR-4.3 | The configuration must define a hierarchy of folder names. Nesting is supported. |
| FR-4.4 | Upon successful connection, the platform reads the structure configuration and creates any defined folders absent from the repository. |
| FR-4.5 | Scaffolding is additive only: it creates missing folders and does not rename, move, or delete any existing folder or file. |
| FR-4.6 | Scaffolding is idempotent: running it any number of times on any combination of new and existing content produces the same result. |
| FR-4.7 | The Admin receives a summary after scaffolding: how many folders were created, how many were already present and skipped. |
| FR-4.8 | A configuration file that is malformed or empty must be rejected before scaffolding begins, with a clear error indicating what is wrong. |

---

### FR-5: Connection Lifecycle

| ID | Requirement |
|----|-------------|
| FR-5.1 | Admins can view the current connection status, connected repository address, connection date, and last scaffolding date. The token is never shown. |
| FR-5.2 | Admins can rotate the access token. The platform must re-validate the new token before replacing the old one. |
| FR-5.3 | A failed rotation attempt leaves the existing credential unchanged. |
| FR-5.4 | Admins can disconnect a repository. Disconnection removes the stored credential and suspends all sync operations. |
| FR-5.5 | Disconnection does not modify or delete any content in the GitHub repository. |
| FR-5.6 | Every connection event (connected, token rotated, disconnected, scaffolding run) is written to the audit log with the acting Admin's identity and a timestamp. Token values are never logged. |

---

## Success Criteria

| # | Criterion |
|---|-----------|
| SC-1 | An Admin can complete a successful repository connection and see scaffolding results in under 3 minutes from start to confirmation. |
| SC-2 | Invalid credentials are identified and a specific, actionable error is shown within 10 seconds of submission. |
| SC-3 | Scaffolding completes within 30 seconds for a configuration defining up to 50 folders. |
| SC-4 | 100% of access tokens in the system are verifiably encrypted at rest — confirmed by inspection of the data store showing no plaintext token values. |
| SC-5 | Zero instances of a token value appearing in any application log, audit record, or API response across automated security tests. |
| SC-6 | Re-running scaffolding on a fully initialized repository results in zero new folders created, zero existing folders modified, and zero errors. |
| SC-7 | A failed validation attempt (any error type) leaves zero partial or orphaned records in any data store. |
| SC-8 | Every connection lifecycle event (connect, rotate, disconnect, scaffold) has a corresponding audit log entry — zero gaps across automated event tests. |

---

## Key Entities

### GitHubConnection
Represents the active link to the organization's GitHub repository.

| Attribute | Description |
|-----------|-------------|
| id | Unique identifier |
| repository_address | The full address of the connected repository |
| encrypted_token | The access token, encrypted at rest. Never exposed. |
| status | One of: Active, Inactive |
| connected_by | Admin who established the connection |
| connected_at | Timestamp of successful connection |
| last_validated_at | Timestamp of most recent successful validation |
| last_scaffolded_at | Timestamp of most recent scaffolding run (nullable) |

---

### RepositoryStructureConfiguration
Defines the folder hierarchy to be created in the connected repository.

| Attribute | Description |
|-----------|-------------|
| id | Unique identifier |
| content | The folder hierarchy definition (hierarchical list of named paths) |
| is_default | Whether this is the platform-provided default configuration |
| created_by | Admin who created or last modified this configuration |
| updated_at | Last modification timestamp |

**Default structure** (platform-provided, can be overridden):
```
content/
  campaigns/
  assets/
    images/
    documents/
  templates/
  drafts/
  published/
```

---

### ScaffoldingRun
An immutable record of a single scaffolding execution.

| Attribute | Description |
|-----------|-------------|
| id | Unique identifier |
| connection_id | The GitHubConnection that was scaffolded |
| triggered_by | Admin who triggered the run (nullable if system-triggered) |
| ran_at | Timestamp of execution |
| folders_created | Count of folders created in this run |
| folders_skipped | Count of folders already present and skipped |
| outcome | Success or Failed |
| error_detail | Human-readable error description if outcome is Failed (nullable) |

---

### Audit Log Entry (GitHub Events)
Extends the audit log defined in Epic 1 with GitHub Bridge-specific event types.

| Action Value | Triggered By |
|---|---|
| `github_connected` | Admin completes a successful connection |
| `github_token_rotated` | Admin successfully rotates the token |
| `github_disconnected` | Admin disconnects the repository |
| `github_scaffolded` | Scaffolding run completes (success or failure) |
| `github_validation_failed` | Any failed validation attempt |

---

## Dependencies & Assumptions

### Dependencies

- **Epic 1 (IAM)**: Admin role and session enforcement must be in place. The GitHub Bridge enforces Admin-only access to all connection operations.
- **Encryption key management**: A secure, externally managed key must be available for token encryption. The mechanism for key storage and rotation is out of scope for this epic but must be resolved before this epic ships to production.
- **GitHub API availability**: Validation and scaffolding depend on GitHub's API being reachable. The platform does not control this.
- **Transactional email** (optional): If a future requirement to notify Admins of connection events is added, the email service from Epic 4 (Invitations) would be required.

### Assumptions

| # | Assumption | Rationale |
|---|-----------|-----------|
| A-1 | One active repository connection per installation for MVP. | Simplifies connection management. Multiple repositories can be a post-MVP feature. |
| A-2 | The GitHub repository must already exist before connecting. | Repository creation in GitHub is out of scope. Admins are expected to create repos first. |
| A-3 | The minimum required token permission is read/write access to repository contents (to both read structure and create folders). Read-only tokens are insufficient. | Scaffolding writes to the repository; read-only tokens would cause scaffolding to fail. |
| A-4 | Scaffolding creates an empty `.gitkeep` file inside each folder to establish the folder path. GitHub does not support empty directories — a file must exist for a folder to appear in the repository. `.gitkeep` files are the universal convention for this purpose. No other file content (READMEs, templates, etc.) is created. | Required by GitHub's data model. File templates remain a future feature. |
| A-5 | Token rotation does not trigger re-scaffolding. | The repository structure is already initialized. Re-scaffolding on rotation would be unexpected behavior. |
| A-6 | A malformed or empty repository structure configuration blocks scaffolding entirely. The Admin must fix the configuration before scaffolding can proceed. | Partial scaffolding with an invalid config would produce an unpredictable state. |
| A-7 | The validation timeout is 10 seconds. | Balances responsiveness with allowing for slow network conditions. |
| A-8 | Disconnection is immediate and does not require a confirmation delay or grace period. | Content sync suspension is immediate. Admins should be deliberate about disconnecting. |
| A-9 | The platform does not cache GitHub API responses. Each validation is a live check. | Cached results could mask a revoked or expired token. |

---

## Out of Scope

- Creating, renaming, or deleting repositories on GitHub
- GitHub OAuth App or GitHub App authentication flows (only PAT-based connection in MVP)
- Connecting repositories from platforms other than GitHub (GitLab, Bitbucket, etc.)
- Fine-grained permission scoping beyond minimum required access
- Automated token expiry detection and proactive rotation reminders (planned for a future epic)
- File creation during scaffolding beyond `.gitkeep` placeholders (READMEs, templates, etc.)
- Multiple simultaneous repository connections per installation
- Branch-level connection configuration (the connection targets the repository's default branch)
- Webhook registration or event-driven sync triggered from GitHub (covered in a future content sync epic)
- Encryption key management and rotation (infrastructure concern, out of scope for this epic)
