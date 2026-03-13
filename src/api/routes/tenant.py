"""
Tenant onboarding router — admin-only.

Auth:
  Every request must supply an X-Admin-Token header. The value is validated
  against the ADMIN_TOKEN environment variable using constant-time comparison
  (hmac.compare_digest) to prevent timing attacks.

Credential Rotation (CONSTITUTION §Administrative Security):
  During a 90-day rotation cycle the server also accepts the previous token
  via ADMIN_TOKEN_PREVIOUS for a 24-hour overlap window. Set that env var
  during the overlap period and clear it once rotation is complete.
  The token value is NEVER written to application logs.

Audit:
  Every call to /register-repo — success, conflict, or error — is written to
  the system_audit table in its own independent connection so the audit record
  always commits regardless of the primary operation's outcome.

CONSTITUTION compliance:
  - TENANT_SAFE  : Targets platform-owned tables (tenants, system_audit).
                   Neither table is RLS-scoped; no tenant_id filter is needed.
  - DRY          : All DB access via postgres_manager.get_db_cursor().
  - NON_BLOCKING : Stateless handler; all persistence is in Postgres.
"""

import hmac
import logging
import os

import psycopg2
from fastapi import APIRouter, Depends, Header, HTTPException, status
from pydantic import BaseModel, HttpUrl

from ..utils import postgres_manager

logger = logging.getLogger(__name__)

router = APIRouter(tags=["tenant-admin"])

# ---------------------------------------------------------------------------
# DDL — idempotent, safe to run on every cold-start
# ---------------------------------------------------------------------------

_CREATE_TENANTS_TABLE = """
CREATE TABLE IF NOT EXISTS tenants (
    tenant_id   UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_name TEXT        NOT NULL UNIQUE,
    github_url  TEXT        NOT NULL,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);
"""

_CREATE_AUDIT_TABLE = """
CREATE TABLE IF NOT EXISTS system_audit (
    audit_id    UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    action      TEXT        NOT NULL,
    tenant_name TEXT,
    status      TEXT        NOT NULL,   -- 'success' | 'conflict' | 'error'
    detail      TEXT,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);
"""


def _ensure_schema() -> None:
    """Create platform tables if they do not yet exist (IF NOT EXISTS — safe to repeat)."""
    with postgres_manager.get_db_cursor() as cur:
        cur.execute(_CREATE_TENANTS_TABLE)
    with postgres_manager.get_db_cursor() as cur:
        cur.execute(_CREATE_AUDIT_TABLE)


# ---------------------------------------------------------------------------
# Auth dependency
# ---------------------------------------------------------------------------

def _require_admin(x_admin_token: str = Header(..., alias="X-Admin-Token")) -> None:
    """
    Validate the X-Admin-Token header.

    Accepts ADMIN_TOKEN (current) and ADMIN_TOKEN_PREVIOUS (rotation overlap).
    Uses hmac.compare_digest for all comparisons to prevent timing attacks.
    Raises 503 if ADMIN_TOKEN is unconfigured (fail-closed).
    Raises 403 on any token mismatch — never revealing the expected value.
    """
    primary = os.environ.get("ADMIN_TOKEN", "")
    previous = os.environ.get("ADMIN_TOKEN_PREVIOUS", "")

    if not primary:
        # Misconfigured server — fail closed rather than open.
        logger.error("ADMIN_TOKEN environment variable is not set.")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Admin authentication is not configured on this server.",
        )

    valid_tokens = [t for t in (primary, previous) if t]

    # constant-time comparison for every candidate to prevent timing oracle
    token_accepted = any(
        hmac.compare_digest(x_admin_token, candidate) for candidate in valid_tokens
    )

    if not token_accepted:
        # Do NOT log x_admin_token — CONSTITUTION: Exposure Prevention
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Invalid or missing X-Admin-Token.",
        )


# ---------------------------------------------------------------------------
# Audit helper
# ---------------------------------------------------------------------------

def _write_audit(
    action: str,
    tenant_name: str,
    audit_status: str,
    detail: str | None = None,
) -> None:
    """
    Append one row to system_audit.

    Runs in its own get_db_cursor() call so it opens a fresh connection and
    commits independently. An audit failure must not mask the primary result,
    so exceptions are swallowed after logging.
    """
    try:
        with postgres_manager.get_db_cursor() as cur:
            cur.execute(
                """
                INSERT INTO system_audit (action, tenant_name, status, detail)
                VALUES (%(action)s, %(tenant_name)s, %(status)s, %(detail)s);
                """,
                {
                    "action": action,
                    "tenant_name": tenant_name,
                    "status": audit_status,
                    "detail": detail,
                },
            )
    except Exception:
        logger.exception(
            "Failed to write audit log for action=%r tenant=%r status=%r.",
            action,
            tenant_name,
            audit_status,
        )


# ---------------------------------------------------------------------------
# Request / Response schemas
# ---------------------------------------------------------------------------

class RegisterRepoRequest(BaseModel):
    github_url: HttpUrl
    tenant_name: str


class RegisterRepoResponse(BaseModel):
    tenant_id: str
    tenant_name: str
    github_url: str
    created_at: str


# ---------------------------------------------------------------------------
# Endpoint
# ---------------------------------------------------------------------------

_INSERT_TENANT = """
    INSERT INTO tenants (tenant_name, github_url)
    VALUES (%(tenant_name)s, %(github_url)s)
    ON CONFLICT (tenant_name) DO NOTHING
    RETURNING tenant_id::text, tenant_name, github_url, created_at::text;
"""


@router.post(
    "/register-repo",
    response_model=RegisterRepoResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(_require_admin)],
)
async def register_repo(body: RegisterRepoRequest) -> RegisterRepoResponse:
    """
    Onboard a new tenant by registering their GitHub repository.

    - Creates `tenants` and `system_audit` tables on first call (idempotent DDL).
    - Inserts a new tenant row and returns the generated `tenant_id`.
    - Returns **409 Conflict** without crashing if `tenant_name` is already taken.
    - Every outcome (success, conflict, error) is recorded in `system_audit`.

    The returned `tenant_id` must be stored by the caller — it is required as
    the `X-Tenant-ID` header on all subsequent tenant-scoped API requests.

    **Auth**: `X-Admin-Token: <ADMIN_TOKEN>`
    """
    _ensure_schema()

    try:
        with postgres_manager.get_db_cursor() as cur:
            cur.execute(
                _INSERT_TENANT,
                {
                    "tenant_name": body.tenant_name,
                    "github_url": str(body.github_url),
                },
            )
            row = cur.fetchone()

    except psycopg2.Error:
        logger.exception("DB error while registering tenant '%s'.", body.tenant_name)
        _write_audit("register_repo", body.tenant_name, "error", "Database error during registration.")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="A database error occurred during tenant registration.",
        )

    # ON CONFLICT DO NOTHING returns no row — tenant already exists.
    if row is None:
        _write_audit("register_repo", body.tenant_name, "conflict", "Tenant name already registered.")
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"A tenant named '{body.tenant_name}' is already registered.",
        )

    _write_audit("register_repo", body.tenant_name, "success")
    logger.info(
        "Tenant registered successfully: id=%s name=%s",
        row["tenant_id"],
        row["tenant_name"],
    )
    return RegisterRepoResponse(**row)
