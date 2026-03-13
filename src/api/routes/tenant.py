"""
Tenant onboarding router — admin-only.

Auth:
  Every request must supply an X-Admin-Token header validated against the
  ADMIN_TOKEN environment variable using constant-time comparison.

CONSTITUTION compliance:
  - AUTH_SAFE  : All endpoints gated behind _require_admin dependency.
  - DRY        : DB access via utils/db.py get_db; audit via utils/audit.py.
  - NON_BLOCKING: Async handler; stateless.
"""

import hmac
import logging
import os

from fastapi import APIRouter, Depends, Header, HTTPException, status
from pydantic import BaseModel, HttpUrl
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.models import Tenant
from utils.audit import write_audit
from utils.db import get_db

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/tenants", tags=["tenant-admin"])


# ---------------------------------------------------------------------------
# Auth dependency
# ---------------------------------------------------------------------------

def _require_admin(x_admin_token: str = Header(..., alias="X-Admin-Token")) -> None:
    primary = os.environ.get("ADMIN_TOKEN", "")
    previous = os.environ.get("ADMIN_TOKEN_PREVIOUS", "")

    if not primary:
        logger.error("ADMIN_TOKEN environment variable is not set.")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Admin authentication is not configured on this server.",
        )

    valid_tokens = [t for t in (primary, previous) if t]
    if not any(hmac.compare_digest(x_admin_token, t) for t in valid_tokens):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Invalid or missing X-Admin-Token.",
        )


# ---------------------------------------------------------------------------
# Schemas
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

@router.post(
    "/register-repo",
    response_model=RegisterRepoResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(_require_admin)],
)
async def register_repo(
    body: RegisterRepoRequest,
    db: AsyncSession = Depends(get_db),
) -> RegisterRepoResponse:
    """
    Onboard a new tenant by registering their GitHub repository.

    Returns 409 if tenant_name is already taken.
    Every outcome is written to audit_log.
    """
    github_url = str(body.github_url)

    existing = await db.scalar(
        select(Tenant).where(Tenant.tenant_name == body.tenant_name)
    )
    if existing:
        await write_audit(
            db,
            action="register_repo",
            target_id=existing.id,
            metadata={"tenant_name": body.tenant_name, "result": "conflict"},
        )
        await db.commit()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"A tenant named '{body.tenant_name}' is already registered.",
        )

    tenant = Tenant(tenant_name=body.tenant_name, github_url=github_url)
    db.add(tenant)
    await db.flush()  # populate tenant.id before audit

    await write_audit(
        db,
        action="register_repo",
        target_id=tenant.id,
        metadata={"tenant_name": body.tenant_name, "result": "success"},
    )
    await db.commit()
    await db.refresh(tenant)

    logger.info("Tenant registered: id=%s name=%s", tenant.id, tenant.tenant_name)
    return RegisterRepoResponse(
        tenant_id=str(tenant.id),
        tenant_name=tenant.tenant_name,
        github_url=tenant.github_url,
        created_at=tenant.created_at.isoformat(),
    )
