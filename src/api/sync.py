"""
GitHub Sync API — endpoints for triggering and monitoring content sync.

CONSTITUTION compliance:
  - AUTH_SAFE   : All routes depend on get_current_user; admin-only routes
                  additionally use require_role(Role.ADMIN).
  - DRY         : Sync orchestration via utils/sync.py, GitHub calls via
                  utils/github_api.py, DB via utils/db.py.
  - NON_BLOCKING: All handlers are async; sync is dispatched as a background task.
"""

import asyncio
import logging
import uuid

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.models.github_connection import GitHubConnection
from src.models.sync_run import SyncOutcome, SyncRun, SyncTriggerType
from src.models.synced_document import SyncedDocument
from src.models.user import Role, User
from utils.audit import write_audit
from utils.auth import get_current_user, require_role
from utils.db import get_db
from utils.github_api import GitHubUnavailableError, GitHubValidationError
from utils.sync import run_sync

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/github", tags=["sync"])


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

async def _get_active_connection(db: AsyncSession) -> GitHubConnection:
    conn = await db.scalar(
        select(GitHubConnection).where(GitHubConnection.status == "active")
    )
    if conn is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "NO_CONNECTION", "message": "No repository is currently connected."},
        )
    return conn


async def _run_sync_background(
    connection_id: uuid.UUID,
    triggered_by: uuid.UUID,
) -> None:
    """Fire-and-forget wrapper for run_sync called from BackgroundTasks."""
    try:
        await run_sync(
            connection_id=connection_id,
            triggered_by=triggered_by,
            trigger_type=SyncTriggerType.MANUAL.value,
        )
    except ValueError as exc:
        logger.warning("Background sync skipped: %s", exc)
    except (GitHubValidationError, GitHubUnavailableError) as exc:
        logger.error("Background sync GitHub error: %s", exc)
    except Exception:
        logger.exception("Background sync unexpected error for connection %s", connection_id)


# ---------------------------------------------------------------------------
# POST /github/sync  — trigger on-demand sync (admin only)
# ---------------------------------------------------------------------------

@router.post(
    "/sync",
    status_code=status.HTTP_202_ACCEPTED,
    dependencies=[require_role(Role.ADMIN)],
)
async def trigger_sync(
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Trigger an on-demand GitHub sync. Returns immediately; sync runs in background."""
    connection = await _get_active_connection(db)

    # Quick check — prevent double-trigger
    in_progress = await db.scalar(
        select(SyncRun)
        .where(
            SyncRun.connection_id == connection.id,
            SyncRun.outcome == SyncOutcome.IN_PROGRESS.value,
        )
        .limit(1)
    )
    if in_progress is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"code": "SYNC_IN_PROGRESS", "message": "A sync is already in progress."},
        )

    await write_audit(
        db,
        action="github_sync_triggered",
        actor_id=current_user.id,
        metadata={"connection_id": str(connection.id)},
    )
    await db.commit()

    background_tasks.add_task(
        _run_sync_background,
        connection_id=connection.id,
        triggered_by=current_user.id,
    )

    return {"status": "accepted", "message": "Sync started."}


# ---------------------------------------------------------------------------
# GET /github/sync/status  — current sync state (all authenticated users)
# ---------------------------------------------------------------------------

@router.get(
    "/sync/status",
    dependencies=[Depends(get_current_user)],
)
async def get_sync_status(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Return the most recent sync run and aggregate counts."""
    connection = await _get_active_connection(db)

    # Latest sync run
    latest_run = await db.scalar(
        select(SyncRun)
        .where(SyncRun.connection_id == connection.id)
        .order_by(SyncRun.started_at.desc())
        .limit(1)
    )

    # Active synced document count
    active_count_result = await db.execute(
        select(SyncedDocument.id).where(
            SyncedDocument.connection_id == connection.id,
            SyncedDocument.is_active == True,  # noqa: E712
        )
    )
    active_count = len(active_count_result.all())

    run_data = None
    if latest_run:
        run_data = {
            "id": str(latest_run.id),
            "outcome": latest_run.outcome,
            "trigger_type": latest_run.trigger_type,
            "started_at": latest_run.started_at.isoformat(),
            "finished_at": latest_run.finished_at.isoformat() if latest_run.finished_at else None,
            "files_indexed": latest_run.files_indexed,
            "files_removed": latest_run.files_removed,
            "files_unchanged": latest_run.files_unchanged,
            "error_detail": latest_run.error_detail,
        }

    return {
        "connection_id": str(connection.id),
        "last_synced_at": connection.last_synced_at.isoformat() if connection.last_synced_at else None,
        "active_document_count": active_count,
        "latest_run": run_data,
    }


# ---------------------------------------------------------------------------
# GET /github/sync/runs  — sync run history (admin only)
# ---------------------------------------------------------------------------

@router.get(
    "/sync/runs",
    dependencies=[require_role(Role.ADMIN)],
)
async def list_sync_runs(
    limit: int = 20,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Return recent sync run history for the active connection."""
    connection = await _get_active_connection(db)

    limit = min(limit, 100)
    runs = await db.scalars(
        select(SyncRun)
        .where(SyncRun.connection_id == connection.id)
        .order_by(SyncRun.started_at.desc())
        .limit(limit)
    )

    return {
        "runs": [
            {
                "id": str(run.id),
                "outcome": run.outcome,
                "trigger_type": run.trigger_type,
                "triggered_by": str(run.triggered_by) if run.triggered_by else None,
                "started_at": run.started_at.isoformat(),
                "finished_at": run.finished_at.isoformat() if run.finished_at else None,
                "files_indexed": run.files_indexed,
                "files_removed": run.files_removed,
                "files_unchanged": run.files_unchanged,
                "error_detail": run.error_detail,
            }
            for run in runs.all()
        ]
    }
