import logging
import uuid
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

from src.config import settings

logger = logging.getLogger(__name__)


# -----------------------------------------------------------------
# Middleware
# -----------------------------------------------------------------

class RequestIDMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        request_id = request.headers.get("X-Request-ID") or str(uuid.uuid4())
        request.state.request_id = request_id
        response = await call_next(request)
        response.headers["X-Request-ID"] = request_id
        return response


# -----------------------------------------------------------------
# App factory
# -----------------------------------------------------------------

@asynccontextmanager
async def _lifespan(application: FastAPI):
    from sqlalchemy import select
    from utils.db import AsyncSessionLocal
    from src.models.user import User, Role
    from src.models.repo_structure_config import RepoStructureConfig
    from utils.queue import (
        startup_recovery,
        start_queue_workers,
        stop_queue_workers,
        start_indexing_workers,
        stop_indexing_workers,
        start_sync_scheduler,
        stop_sync_scheduler,
    )
    from utils.sync import recover_interrupted_syncs

    # Warn if initial admin token is still set after an admin exists
    if settings.INITIAL_ADMIN_TOKEN:
        async with AsyncSessionLocal() as db:
            try:
                result = await db.execute(
                    select(User).where(User.role == Role.ADMIN.value).limit(1)
                )
                if result.scalar_one_or_none():
                    logger.warning(
                        "SECURITY WARNING: INITIAL_ADMIN_TOKEN is still set but an admin "
                        "already exists. Remove it from .env immediately."
                    )
            except Exception:
                pass

    # Seed default repo structure config if none exists.
    # Uses INSERT ... ON CONFLICT DO NOTHING to avoid duplicate rows when
    # multiple pods start simultaneously (race condition with replicas > 1).
    async with AsyncSessionLocal() as db:
        try:
            from sqlalchemy.dialects.postgresql import insert as pg_insert  # noqa: PLC0415
            stmt = (
                pg_insert(RepoStructureConfig)
                .values(
                    id=uuid.UUID("00000000-0000-0000-0000-000000000001"),
                    folders={
                        "folders": [
                            "content/campaigns",
                            "content/assets/images",
                            "content/assets/documents",
                            "content/templates",
                            "content/drafts",
                            "content/published",
                        ]
                    },
                    is_default=True,
                    created_by=None,
                )
                .on_conflict_do_nothing(index_elements=["id"])
            )
            await db.execute(stmt)
            await db.commit()
            logger.info("Default repository structure config ensured.")
        except Exception:
            logger.exception("Failed to seed default repo structure config.")

    # Reset any documents stuck in "processing" from a prior crash
    await startup_recovery()

    # Mark any sync runs left in-progress from a prior crash as INTERRUPTED
    await recover_interrupted_syncs()

    # Start queue workers
    await start_queue_workers(concurrency=settings.WORKER_CONCURRENCY)
    await start_indexing_workers(concurrency=settings.KB_INDEX_CONCURRENCY)
    await start_sync_scheduler(interval_minutes=settings.SYNC_INTERVAL_HOURS * 60)

    yield

    # Graceful shutdown
    await stop_queue_workers()
    await stop_indexing_workers()
    await stop_sync_scheduler()


def create_app() -> FastAPI:
    application = FastAPI(
        title="Marketing Platform API",
        version=settings.APP_VERSION,
        docs_url="/docs",
        redoc_url="/redoc",
        lifespan=_lifespan,
    )

    # CORS
    # Note: allow_credentials=True requires explicit origins (no wildcard).
    # Add new Vercel preview/production URLs here as the frontend grows.
    _cors_origins = [
        "http://localhost:3000",  # local Next.js dev
        "https://app.activelab.com",  # production frontend
    ]
    # Accept any Vercel preview deploy URL for the project
    application.add_middleware(
        CORSMiddleware,
        allow_origins=_cors_origins,
        allow_origin_regex=r"https://.*\.vercel\.app",
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Request ID injection
    application.add_middleware(RequestIDMiddleware)

    # Global exception handler
    @application.exception_handler(Exception)
    async def unhandled_exception_handler(request: Request, exc: Exception):
        request_id = getattr(request.state, "request_id", "unknown")
        logger.exception(
            "Unhandled exception [request_id=%s]", request_id, exc_info=exc
        )
        return JSONResponse(
            status_code=500,
            content={
                "error": "An unexpected error occurred",
                "code": "INTERNAL_ERROR",
                "request_id": request_id,
            },
        )

    # Routers — mounted after import to avoid circular dependencies
    from src.api.health import router as health_router
    from src.api.auth import router as auth_router
    from src.api.users import router as users_router
    from src.api.routes.tenant import router as tenant_router
    from src.api.github import router as github_router
    from src.api.sync import router as sync_router
    from src.api.ingestion import router as ingestion_router
    from src.api.chat import router as chat_router
    from src.api.knowledge_base import router as kb_router
    from src.api.content import router as content_router
    from src.api.generate import router as generate_router
    from src.api.images import router as images_router

    application.include_router(health_router, prefix="/api/v1")
    application.include_router(auth_router, prefix="/api/v1")
    application.include_router(users_router, prefix="/api/v1")
    application.include_router(tenant_router, prefix="/api/v1")
    application.include_router(github_router, prefix="/api/v1")
    application.include_router(sync_router, prefix="/api/v1")
    application.include_router(ingestion_router, prefix="/api/v1")
    application.include_router(chat_router, prefix="/api/v1")
    application.include_router(kb_router, prefix="/api/v1")
    application.include_router(content_router, prefix="/api/v1")
    application.include_router(generate_router, prefix="/api/v1")
    application.include_router(images_router, prefix="/api/v1")

    return application


app = create_app()
