"""
GitHub Bridge API — Admin-only endpoints for repository connection and scaffolding.

All endpoints require Admin role (enforced via require_role from Epic 1).

CONSTITUTION compliance:
  - AUTH_SAFE   : All routes use Depends(require_role(Role.ADMIN)).
  - DRY         : Encryption via utils/crypto.py, GitHub calls via utils/github_api.py,
                  DB via utils/db.py, audit via utils/audit.py.
  - NON_BLOCKING: Async handlers throughout; httpx.AsyncClient for GitHub API.
"""

import logging
import re
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.models import GitHubConnection, RepoStructureConfig, ScaffoldingRun
from src.models.user import Role, User
from utils.audit import write_audit
from utils.crypto import decrypt_token, encrypt_token
from utils.db import get_db
from utils.auth import get_current_user, require_role
from utils.github_api import (
    GitHubUnavailableError,
    GitHubValidationError,
    scaffold_repository,
    validate_and_check_access,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/github", tags=["github"])

_FOLDER_SAFE_RE = re.compile(r"^[^/].*[^/]$|^[^/]$")  # no leading/trailing slash
_PATH_TRAVERSAL_RE = re.compile(r"\.\.")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _active_connection_query():
    return select(GitHubConnection).where(GitHubConnection.status == "active")


async def _get_active_connection(db: AsyncSession) -> GitHubConnection:
    conn = await db.scalar(_active_connection_query())
    if conn is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "NO_CONNECTION", "message": "No repository is currently connected."},
        )
    return conn


def _active_config_query():
    return select(RepoStructureConfig).order_by(
        RepoStructureConfig.is_default.asc(),  # custom config (is_default=False) first
        RepoStructureConfig.updated_at.desc(),
    )


async def _get_active_config(db: AsyncSession) -> RepoStructureConfig:
    return await db.scalar(_active_config_query())


def _validate_config_folders(folders: list) -> None:
    if not folders or not isinstance(folders, list):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"code": "CONFIG_INVALID", "message": "folders must be a non-empty list."},
        )
    if len(folders) > 200:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"code": "CONFIG_INVALID", "message": "folders must not exceed 200 entries."},
        )
    invalid = []
    for f in folders:
        if not isinstance(f, str) or not f.strip():
            invalid.append(f)
        elif _PATH_TRAVERSAL_RE.search(f):
            invalid.append(f)
        elif f.startswith("/") or f.endswith("/"):
            invalid.append(f)
    if invalid:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "code": "CONFIG_INVALID",
                "message": "One or more folder paths are invalid (empty, path traversal, or leading/trailing slash).",
                "invalid_entries": invalid,
            },
        )


def _map_github_error(exc: GitHubValidationError) -> HTTPException:
    detail = {"code": exc.code, "message": exc.message}
    if exc.missing_permissions:
        detail["missing_permissions"] = exc.missing_permissions
    return HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=detail)


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------

class ConnectRequest(BaseModel):
    repository_url: str
    token: str


class RotateTokenRequest(BaseModel):
    token: str


class UpdateConfigRequest(BaseModel):
    folders: list[str]


class AddFolderRequest(BaseModel):
    folder: str


# ---------------------------------------------------------------------------
# POST /connect
# ---------------------------------------------------------------------------

@router.post(
    "/connect",
    status_code=status.HTTP_201_CREATED,
    dependencies=[require_role(Role.ADMIN)],
)
async def connect_repository(
    body: ConnectRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    # 1. Check no active connection already exists
    existing = await db.scalar(_active_connection_query())
    if existing is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "code": "CONNECTION_ALREADY_EXISTS",
                "message": "An active repository connection already exists. Disconnect it before connecting a new one.",
            },
        )

    # 2. Validate token + repo access (nothing stored on failure)
    try:
        await validate_and_check_access(body.repository_url, body.token)
    except GitHubValidationError as exc:
        await write_audit(
            db,
            action="github_validation_failed",
            actor_id=current_user.id,
            metadata={"reason": exc.code, "repository_url": body.repository_url},
        )
        await db.commit()
        raise _map_github_error(exc)
    except GitHubUnavailableError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={
                "code": "GITHUB_UNAVAILABLE",
                "message": "GitHub could not be reached. This is a temporary issue — please try again shortly.",
            },
        )

    # 3. Encrypt and store connection
    now = datetime.now(timezone.utc)
    connection = GitHubConnection(
        repository_url=body.repository_url,
        encrypted_token=encrypt_token(body.token),
        status="active",
        connected_by=current_user.id,
        connected_at=now,
        last_validated_at=now,
    )
    db.add(connection)
    await db.flush()  # get connection.id before scaffolding

    # 4. Load and validate config
    config = await _get_active_config(db)
    folders = config.folders.get("folders", []) if config else []
    _validate_config_folders(folders)

    # 5. Scaffold — failure is non-fatal: connection is kept, run recorded
    scaffold_error: str | None = None
    folders_created = 0
    folders_skipped = 0
    try:
        folders_created, folders_skipped = await scaffold_repository(
            body.repository_url, body.token, folders
        )
        connection.last_scaffolded_at = datetime.now(timezone.utc)
        scaffold_outcome = "success"
    except GitHubUnavailableError as exc:
        scaffold_error = str(exc)
        scaffold_outcome = "failed"
        logger.warning("Scaffolding failed after successful connection: %s", scaffold_error)

    run = ScaffoldingRun(
        connection_id=connection.id,
        triggered_by=current_user.id,
        folders_created=folders_created,
        folders_skipped=folders_skipped,
        outcome=scaffold_outcome,
        error_detail=scaffold_error,
    )
    db.add(run)

    await write_audit(
        db,
        action="github_connected",
        actor_id=current_user.id,
        metadata={"repository_url": body.repository_url, "connection_id": str(connection.id)},
    )
    await db.commit()
    await db.refresh(connection)
    await db.refresh(run)

    response = {
        "data": {
            "connection_id": str(connection.id),
            "repository_url": connection.repository_url,
            "status": connection.status,
            "connected_at": connection.connected_at.isoformat(),
            "scaffolding": {
                "run_id": str(run.id),
                "folders_created": run.folders_created,
                "folders_skipped": run.folders_skipped,
                "outcome": run.outcome,
            },
        }
    }
    if scaffold_error:
        response["data"]["scaffolding"]["error"] = scaffold_error

    return response


# ---------------------------------------------------------------------------
# GET /connection
# ---------------------------------------------------------------------------

@router.get(
    "/connection",
    dependencies=[require_role(Role.ADMIN)],
)
async def get_connection(db: AsyncSession = Depends(get_db)):
    connection = await _get_active_connection(db)
    return {
        "data": {
            "connection_id": str(connection.id),
            "repository_url": connection.repository_url,
            "status": connection.status,
            "connected_at": connection.connected_at.isoformat(),
            "last_validated_at": connection.last_validated_at.isoformat(),
            "last_scaffolded_at": (
                connection.last_scaffolded_at.isoformat()
                if connection.last_scaffolded_at else None
            ),
            "token_on_file": True,
        }
    }


# ---------------------------------------------------------------------------
# PATCH /connection/token
# ---------------------------------------------------------------------------

@router.patch(
    "/connection/token",
    dependencies=[require_role(Role.ADMIN)],
)
async def rotate_token(
    body: RotateTokenRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    connection = await _get_active_connection(db)

    try:
        await validate_and_check_access(connection.repository_url, body.token)
    except GitHubValidationError as exc:
        raise _map_github_error(exc)
    except GitHubUnavailableError:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={
                "code": "GITHUB_UNAVAILABLE",
                "message": "GitHub could not be reached. This is a temporary issue — please try again shortly.",
            },
        )

    connection.encrypted_token = encrypt_token(body.token)
    connection.last_validated_at = datetime.now(timezone.utc)

    await write_audit(
        db,
        action="github_token_rotated",
        actor_id=current_user.id,
        metadata={"repository_url": connection.repository_url, "connection_id": str(connection.id)},
    )
    await db.commit()
    await db.refresh(connection)

    return {
        "data": {
            "connection_id": str(connection.id),
            "last_validated_at": connection.last_validated_at.isoformat(),
        }
    }


# ---------------------------------------------------------------------------
# DELETE /connection
# ---------------------------------------------------------------------------

@router.delete(
    "/connection",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[require_role(Role.ADMIN)],
)
async def disconnect(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    connection = await _get_active_connection(db)
    connection.status = "inactive"

    await write_audit(
        db,
        action="github_disconnected",
        actor_id=current_user.id,
        metadata={"repository_url": connection.repository_url, "connection_id": str(connection.id)},
    )
    await db.commit()


# ---------------------------------------------------------------------------
# POST /scaffold
# ---------------------------------------------------------------------------

@router.post(
    "/scaffold",
    dependencies=[require_role(Role.ADMIN)],
)
async def run_scaffold(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    connection = await _get_active_connection(db)

    config = await _get_active_config(db)
    folders = config.folders.get("folders", []) if config else []
    _validate_config_folders(folders)

    token = decrypt_token(connection.encrypted_token)

    try:
        folders_created, folders_skipped = await scaffold_repository(
            connection.repository_url, token, folders
        )
        outcome = "success"
        error_detail = None
    except GitHubUnavailableError as exc:
        folders_created, folders_skipped = 0, 0
        outcome = "failed"
        error_detail = str(exc)

    run = ScaffoldingRun(
        connection_id=connection.id,
        triggered_by=current_user.id,
        folders_created=folders_created,
        folders_skipped=folders_skipped,
        outcome=outcome,
        error_detail=error_detail,
    )
    db.add(run)

    if outcome == "success":
        connection.last_scaffolded_at = datetime.now(timezone.utc)

    await write_audit(
        db,
        action="github_scaffolded",
        actor_id=current_user.id,
        metadata={
            "outcome": outcome,
            "folders_created": folders_created,
            "folders_skipped": folders_skipped,
        },
    )
    await db.commit()
    await db.refresh(run)

    response = {
        "data": {
            "run_id": str(run.id),
            "folders_created": run.folders_created,
            "folders_skipped": run.folders_skipped,
            "outcome": run.outcome,
            "ran_at": run.ran_at.isoformat(),
        }
    }
    if error_detail:
        response["data"]["error"] = error_detail
    return response


# ---------------------------------------------------------------------------
# GET /config
# ---------------------------------------------------------------------------

@router.get(
    "/config",
    dependencies=[require_role(Role.ADMIN)],
)
async def get_config(db: AsyncSession = Depends(get_db)):
    config = await _get_active_config(db)
    return {
        "data": {
            "config_id": str(config.id),
            "folders": config.folders.get("folders", []),
            "is_default": config.is_default,
            "updated_at": config.updated_at.isoformat(),
        }
    }


# ---------------------------------------------------------------------------
# PUT /config
# ---------------------------------------------------------------------------

@router.put(
    "/config",
    dependencies=[require_role(Role.ADMIN)],
)
async def update_config(
    body: UpdateConfigRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    _validate_config_folders(body.folders)

    # Upsert the non-default custom config row
    custom_config = await db.scalar(
        select(RepoStructureConfig).where(RepoStructureConfig.is_default == False)  # noqa: E712
    )
    now = datetime.now(timezone.utc)
    if custom_config:
        custom_config.folders = {"folders": body.folders}
        custom_config.created_by = current_user.id
        custom_config.updated_at = now
    else:
        custom_config = RepoStructureConfig(
            folders={"folders": body.folders},
            is_default=False,
            created_by=current_user.id,
            updated_at=now,
        )
        db.add(custom_config)

    await db.commit()
    await db.refresh(custom_config)

    return {
        "data": {
            "config_id": str(custom_config.id),
            "folders": custom_config.folders.get("folders", []),
            "is_default": custom_config.is_default,
            "updated_at": custom_config.updated_at.isoformat(),
        }
    }


# ---------------------------------------------------------------------------
# POST /config/folders — add a single folder
# ---------------------------------------------------------------------------

@router.post(
    "/config/folders",
    status_code=status.HTTP_201_CREATED,
    dependencies=[require_role(Role.ADMIN)],
)
async def add_folder(
    body: AddFolderRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    _validate_config_folders([body.folder])

    config = await _get_active_config(db)
    current_folders: list[str] = config.folders.get("folders", []) if config else []

    if body.folder in current_folders:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"code": "FOLDER_ALREADY_EXISTS", "message": f"Folder '{body.folder}' is already configured."},
        )

    new_folders = current_folders + [body.folder]
    now = datetime.now(timezone.utc)

    # Upsert custom config
    custom_config = await db.scalar(
        select(RepoStructureConfig).where(RepoStructureConfig.is_default == False)  # noqa: E712
    )
    if custom_config:
        custom_config.folders = {"folders": new_folders}
        custom_config.created_by = current_user.id
        custom_config.updated_at = now
    else:
        custom_config = RepoStructureConfig(
            folders={"folders": new_folders},
            is_default=False,
            created_by=current_user.id,
            updated_at=now,
        )
        db.add(custom_config)

    # Scaffold new folder (best-effort — failure does not block the add)
    scaffold_outcome = "skipped"
    conn = await db.scalar(_active_connection_query())
    if conn:
        try:
            token = decrypt_token(conn.encrypted_token)
            await scaffold_repository(conn.repository_url, token, [body.folder])
            scaffold_outcome = "success"
        except GitHubUnavailableError as exc:
            scaffold_outcome = "failed"
            logger.warning("Scaffold failed for new folder '%s': %s", body.folder, exc)

    await write_audit(
        db,
        action="github_folder_added",
        actor_id=current_user.id,
        metadata={"folder": body.folder, "scaffold_outcome": scaffold_outcome},
    )
    await db.commit()

    return {
        "data": {
            "folder": body.folder,
            "folders": new_folders,
            "scaffold_outcome": scaffold_outcome,
        }
    }


# ---------------------------------------------------------------------------
# DELETE /config/folders/{folder_name} — remove a single folder
# ---------------------------------------------------------------------------

@router.delete(
    "/config/folders/{folder_name:path}",
    dependencies=[require_role(Role.ADMIN)],
)
async def remove_folder(
    folder_name: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    from urllib.parse import unquote  # noqa: PLC0415
    folder_name = unquote(folder_name)

    config = await _get_active_config(db)
    current_folders: list[str] = config.folders.get("folders", []) if config else []

    if folder_name not in current_folders:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "FOLDER_NOT_FOUND", "message": f"Folder '{folder_name}' is not in the configured list."},
        )

    new_folders = [f for f in current_folders if f != folder_name]
    now = datetime.now(timezone.utc)

    # Upsert custom config
    custom_config = await db.scalar(
        select(RepoStructureConfig).where(RepoStructureConfig.is_default == False)  # noqa: E712
    )
    if custom_config:
        custom_config.folders = {"folders": new_folders}
        custom_config.created_by = current_user.id
        custom_config.updated_at = now
    else:
        custom_config = RepoStructureConfig(
            folders={"folders": new_folders},
            is_default=False,
            created_by=current_user.id,
            updated_at=now,
        )
        db.add(custom_config)

    await write_audit(
        db,
        action="github_folder_removed",
        actor_id=current_user.id,
        metadata={"folder": folder_name},
    )
    await db.commit()

    return {
        "data": {
            "removed_folder": folder_name,
            "folders": new_folders,
        }
    }
