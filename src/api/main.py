from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware
from src.api.routes import tenant

# Import your utility after it is moved to src/api/utils/
from src.api.utils import postgres_manager


class TenantMiddleware(BaseHTTPMiddleware):
    EXEMPT_PATHS = ["/docs", "/openapi.json"]

    async def dispatch(self, request: Request, call_next):
        if request.url.path in self.EXEMPT_PATHS:
            return await call_next(request)

        tenant_id = request.headers.get("X-Tenant-ID", "").strip()
        if not tenant_id:
            return JSONResponse(
                status_code=400,
                content={"detail": "Missing required header: X-Tenant-ID"},
            )

        # Context management
        token = postgres_manager.set_tenant_context(tenant_id)
        try:
            response = await call_next(request)
        finally:
            postgres_manager.reset_tenant_context(token)

        return response


app = FastAPI()

# Add middleware once
app.add_middleware(TenantMiddleware)

# Include router once
app.include_router(tenant.router)
