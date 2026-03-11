"""
FastAPI entry point for the marketing-platform.

Request lifecycle (tenant-scoped):
  1. TenantMiddleware extracts X-Tenant-ID from every incoming request.
  2. It calls postgres_manager.set_tenant_context() to bind the tenant to the
     current asyncio task context via a ContextVar.
  3. Any route handler that calls postgres_manager.execute_tenant_query() will
     operate within that tenant scope automatically.
  4. On response, the middleware resets the ContextVar so context never leaks.

Routes that do not touch tenant data (e.g. /health) are exempt from the
X-Tenant-ID requirement and are listed in TenantMiddleware.EXEMPT_PATHS.
"""

import os
from dotenv import load_dotenv

# Load the .env file explicitly
load_dotenv()

# Print for debugging (you can remove this after we confirm)
print(f"DEBUG: ADMIN_TOKEN loaded: {os.getenv('ADMIN_TOKEN')}")

import logging

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.types import ASGIApp

from utils import postgres_manager
from src.api.routes import tenant as tenant_router

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Middleware
# ---------------------------------------------------------------------------

class TenantMiddleware(BaseHTTPMiddleware):
    """
    Extracts the X-Tenant-ID request header and binds it to the per-request
    ContextVar in postgres_manager for the entire request lifecycle.

    - Requests to EXEMPT_PATHS are allowed through without a tenant header.
    - All other requests without X-Tenant-ID receive a 400 response immediately.
    """

    # Paths that bypass the X-Tenant-ID requirement.
    # /health    — liveness probe, no tenant context needed.
    # /register-repo — admin onboarding; auth is handled by its own bearer check.
    EXEMPT_PATHS: frozenset[str] = frozenset({"/health", "/register-repo"})

    def __init__(self, app: ASGIApp) -> None:
        super().__init__(app)

    async def dispatch(self, request: Request, call_next):
        if request.url.path in self.EXEMPT_PATHS:
            return await call_next(request)

        tenant_id = request.headers.get("X-Tenant-ID", "").strip()
        if not tenant_id:
            return JSONResponse(
                status_code=400,
                content={"detail": "Missing required header: X-Tenant-ID"},
            )

        # Bind tenant to this request's async context.
        token = postgres_manager.set_tenant_context(tenant_id)
        try:
            response = await call_next(request)
        finally:
            # Always reset — even if the handler raises — so context never leaks.
            postgres_manager.reset_tenant_context(token)

        return response


# ---------------------------------------------------------------------------
# Application
# ---------------------------------------------------------------------------

app = FastAPI(
    title="Marketing Platform API",
    description="Multitenant marketing content-as-code platform.",
    version="0.1.0",
)

app.add_middleware(TenantMiddleware)

app.include_router(tenant_router.router)


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@app.get("/health", tags=["ops"])
async def health_check():
    """
    Liveness probe — no tenant context required.
    Returns 200 when the application process is running.
    """
    return {"status": "ok"}
