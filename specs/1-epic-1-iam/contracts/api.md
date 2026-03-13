# API Contracts: Epic 1 — Identity & Access Management

**Base URL**: `/api/v1`
**Content-Type**: `application/json`
**Auth scheme**: Bearer token (JWT access token in `Authorization: Bearer <token>` header)

---

## Standard Response Envelope

All responses use a consistent shape:

```json
{
  "data": { ... },
  "request_id": "uuid"
}
```

Error responses:
```json
{
  "error": "human-readable message",
  "code": "ERROR_CODE",
  "request_id": "uuid"
}
```

`request_id` is generated per-request by middleware and included in all response bodies and application logs.

---

## Auth Endpoints

### `POST /auth/register`
Bootstrap the first Admin. Only succeeds if:
- `X-Setup-Token` header matches `INITIAL_ADMIN_TOKEN` env var.
- No user with role `admin` exists yet.

**Headers**
```
X-Setup-Token: <INITIAL_ADMIN_TOKEN value>
```

**Request**
```json
{
  "email": "admin@example.com",
  "display_name": "Jane Smith",
  "password": "Str0ng!Pass"
}
```

**Response `201`**
```json
{
  "data": {
    "id": "uuid",
    "email": "admin@example.com",
    "display_name": "Jane Smith",
    "role": "admin"
  },
  "request_id": "uuid"
}
```

**Errors**
| Status | Code | Condition |
|--------|------|-----------|
| 403 | `SETUP_TOKEN_INVALID` | Missing or incorrect setup token |
| 409 | `ADMIN_ALREADY_EXISTS` | An admin user already exists |
| 422 | `VALIDATION_ERROR` | Password complexity, email format |

---

### `POST /auth/login`
Authenticate with email and password. Returns access token + sets refresh token cookie.

**Request**
```json
{
  "email": "user@example.com",
  "password": "Str0ng!Pass"
}
```

**Response `200`**
```json
{
  "data": {
    "access_token": "<JWT>",
    "token_type": "bearer",
    "expires_in": 900,
    "user": {
      "id": "uuid",
      "email": "user@example.com",
      "display_name": "Jane Smith",
      "role": "admin"
    }
  },
  "request_id": "uuid"
}
```

**Set-Cookie header on 200**:
```
Set-Cookie: refresh_token=<raw_token>; HttpOnly; Secure; SameSite=Strict; Path=/api/v1/auth/refresh; Max-Age=2592000
```

**Errors**
| Status | Code | Condition |
|--------|------|-----------|
| 401 | `INVALID_CREDENTIALS` | Email not found or password incorrect |
| 401 | `ACCOUNT_DEACTIVATED` | Account has been revoked |
| 429 | `ACCOUNT_LOCKED` | 5+ failed attempts; includes `locked_until` in response |

---

### `POST /auth/refresh`
Exchange a valid refresh token (from httpOnly cookie) for a new access token.

**Cookie required**: `refresh_token`

**Response `200`**
```json
{
  "data": {
    "access_token": "<new JWT>",
    "token_type": "bearer",
    "expires_in": 900
  },
  "request_id": "uuid"
}
```

**Errors**
| Status | Code | Condition |
|--------|------|-----------|
| 401 | `REFRESH_TOKEN_INVALID` | Token not found, expired, or revoked |
| 401 | `SESSION_REVOKED` | Session was revoked by Admin |

---

### `POST /auth/logout`
Revoke the current session. Requires valid access token.

**Auth**: Required

**Response `204`** (no body)

**Clears** `refresh_token` cookie.

---

### `POST /auth/accept-invitation`
Accept an invitation and create a new user account.

**Request**
```json
{
  "token": "<raw_invitation_token>",
  "display_name": "Alex Johnson",
  "password": "Str0ng!Pass"
}
```

**Response `201`**
```json
{
  "data": {
    "id": "uuid",
    "email": "alex@example.com",
    "display_name": "Alex Johnson",
    "role": "marketer"
  },
  "request_id": "uuid"
}
```

**Errors**
| Status | Code | Condition |
|--------|------|-----------|
| 404 | `INVITATION_NOT_FOUND` | Token does not match any invitation |
| 410 | `INVITATION_EXPIRED` | Invitation has expired or been superseded |
| 409 | `INVITATION_ALREADY_USED` | Invitation has already been accepted |
| 422 | `VALIDATION_ERROR` | Password complexity |

---

## User Management Endpoints

All endpoints below require authentication. Role requirements are noted per endpoint.

---

### `GET /users/me`
Return the current user's profile.

**Auth**: Any authenticated user

**Response `200`**
```json
{
  "data": {
    "id": "uuid",
    "email": "user@example.com",
    "display_name": "Jane Smith",
    "role": "admin",
    "status": "active",
    "created_at": "2026-03-12T00:00:00Z"
  },
  "request_id": "uuid"
}
```

---

### `GET /users`
List all users in the system.

**Auth**: Admin, Marketing Manager

**Query params**
| Param | Type | Default | Description |
|-------|------|---------|-------------|
| `status` | `active` \| `deactivated` \| `all` | `active` | Filter by status |
| `role` | `admin` \| `marketing_manager` \| `marketer` | (none) | Filter by role |

**Response `200`**
```json
{
  "data": [
    {
      "id": "uuid",
      "email": "user@example.com",
      "display_name": "Jane Smith",
      "role": "admin",
      "status": "active",
      "created_at": "2026-03-12T00:00:00Z"
    }
  ],
  "request_id": "uuid"
}
```

---

### `POST /users/invite`
Send an invitation to a new team member.

**Auth**: Admin only

**Request**
```json
{
  "email": "newuser@example.com",
  "role": "marketer"
}
```

**Response `201`**
```json
{
  "data": {
    "id": "uuid",
    "invited_email": "newuser@example.com",
    "assigned_role": "marketer",
    "expires_at": "2026-03-15T00:00:00Z",
    "status": "pending"
  },
  "request_id": "uuid"
}
```

**Errors**
| Status | Code | Condition |
|--------|------|-----------|
| 409 | `USER_ALREADY_EXISTS` | Email already has an active account |
| 400 | `INVALID_ROLE` | Role `admin` cannot be assigned via invitation |
| 422 | `VALIDATION_ERROR` | Email format |

---

### `POST /users/invitations/{invitation_id}/resend`
Invalidate the existing invitation for an email and issue a new one.

**Auth**: Admin only

**Response `200`**
```json
{
  "data": {
    "id": "uuid",
    "invited_email": "newuser@example.com",
    "assigned_role": "marketer",
    "expires_at": "2026-03-15T00:00:00Z",
    "status": "pending"
  },
  "request_id": "uuid"
}
```

**Errors**
| Status | Code | Condition |
|--------|------|-----------|
| 404 | `INVITATION_NOT_FOUND` | Invitation ID does not exist |
| 409 | `INVITATION_ALREADY_ACCEPTED` | Cannot resend an accepted invitation |

---

### `PATCH /users/{user_id}/role`
Change a team member's role.

**Auth**: Admin only

**Request**
```json
{
  "role": "marketing_manager"
}
```

**Response `200`**
```json
{
  "data": {
    "id": "uuid",
    "email": "user@example.com",
    "display_name": "Jane Smith",
    "role": "marketing_manager",
    "status": "active"
  },
  "request_id": "uuid"
}
```

**Errors**
| Status | Code | Condition |
|--------|------|-----------|
| 403 | `CANNOT_CHANGE_OWN_ROLE` | Admin attempting to change their own role |
| 404 | `USER_NOT_FOUND` | User ID does not exist |
| 400 | `INVALID_ROLE` | Role value not in allowed set |

---

### `POST /users/{user_id}/revoke`
Deactivate a user and immediately terminate all their sessions.

**Auth**: Admin only

**Response `200`**
```json
{
  "data": {
    "id": "uuid",
    "status": "deactivated",
    "deactivated_at": "2026-03-12T12:00:00Z"
  },
  "request_id": "uuid"
}
```

**Errors**
| Status | Code | Condition |
|--------|------|-----------|
| 403 | `CANNOT_REVOKE_SELF` | Admin attempting to revoke themselves |
| 403 | `LAST_ADMIN` | Revoking this user would leave zero active admins |
| 404 | `USER_NOT_FOUND` | User ID does not exist |
| 409 | `USER_ALREADY_DEACTIVATED` | User is already deactivated |

---

### `POST /users/{user_id}/reactivate`
Reactivate a deactivated user.

**Auth**: Admin only

**Response `200`**
```json
{
  "data": {
    "id": "uuid",
    "status": "active"
  },
  "request_id": "uuid"
}
```

**Errors**
| Status | Code | Condition |
|--------|------|-----------|
| 404 | `USER_NOT_FOUND` | User ID does not exist |
| 409 | `USER_ALREADY_ACTIVE` | User is already active |

---

## System Endpoints

### `GET /health`
Liveness probe. No auth required.

**Response `200`**
```json
{
  "status": "ok",
  "version": "1.0.0"
}
```

---

## Middleware Behaviour

### Request ID
Every request receives a `X-Request-ID` header in the response. If the client sends `X-Request-ID`, that value is echoed back. Otherwise, a new UUID is generated. All application log lines for the request include this ID.

### Global Exception Handler
Unhandled exceptions return `500` with:
```json
{
  "error": "An unexpected error occurred",
  "code": "INTERNAL_ERROR",
  "request_id": "uuid"
}
```
The full traceback is logged with the `request_id` but never returned to the client.

### Auth Middleware
All routes except `/auth/register`, `/auth/login`, `/auth/accept-invitation`, and `/health` require a valid `Authorization: Bearer <token>` header. Missing or invalid tokens return:
```json
{
  "error": "Authentication required",
  "code": "UNAUTHENTICATED",
  "request_id": "uuid"
}
```
