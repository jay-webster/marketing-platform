"""
GitHub repository sync orchestration.

Walks all configured folders in the connected repo, detects new/changed/removed
.md files by blob SHA comparison, and upserts SyncedDocument rows + queues KB
indexing for each change.

Design decisions (see specs/006-content-sync-ingest/research.md):
  - REST API tree endpoint (no git clone) — stateless, K8s-safe.
  - Blob SHA comparison for change detection — no full content download unless changed.
  - SKIP LOCKED guard via SyncRun.outcome = "in_progress" — prevents concurrent runs.
  - Incremental commits — one commit per file so partial progress survives pod restarts.
"""
from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from src.models.github_connection import GitHubConnection
from src.models.knowledge_base_document import KBIndexStatus, KnowledgeBaseDocument
from src.models.repo_structure_config import RepoStructureConfig
from src.models.sync_run import SyncOutcome, SyncRun, SyncTriggerType
from src.models.synced_document import SyncedDocument
from utils.crypto import decrypt_token
from utils.db import AsyncSessionLocal
from utils.github_api import (
    GitHubUnavailableError,
    GitHubValidationError,
    get_default_branch,
    get_file_content,
    get_repo_tree,
)

logger = logging.getLogger(__name__)

_MD_SUFFIX = ".md"


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

async def run_sync(
    connection_id: uuid.UUID,
    triggered_by: uuid.UUID | None = None,
    trigger_type: str = SyncTriggerType.MANUAL.value,
) -> uuid.UUID:
    """Execute a full sync for a GitHub connection.

    Creates a SyncRun audit record, walks the repo tree, and upserts
    SyncedDocument + KnowledgeBaseDocument rows for every change.

    Args:
        connection_id: PK of the GitHubConnection to sync.
        triggered_by: User UUID for manual syncs; None for scheduled.
        trigger_type: "manual" or "scheduled".

    Returns:
        The SyncRun UUID.

    Raises:
        ValueError: If a sync is already in progress or the connection is missing.
        GitHubValidationError / GitHubUnavailableError: On GitHub API failures.
    """
    async with AsyncSessionLocal() as db:
        # Concurrent sync guard — check for in-progress run
        existing = await db.execute(
            select(SyncRun)
            .where(
                SyncRun.connection_id == connection_id,
                SyncRun.outcome == SyncOutcome.IN_PROGRESS.value,
            )
            .limit(1)
        )
        if existing.scalar_one_or_none() is not None:
            raise ValueError("A sync is already in progress for this connection.")

        connection = await db.get(GitHubConnection, connection_id)
        if connection is None:
            raise ValueError(f"GitHubConnection {connection_id} not found.")

        run = SyncRun(
            connection_id=connection_id,
            triggered_by=triggered_by,
            trigger_type=trigger_type,
        )
        db.add(run)
        await db.commit()
        await db.refresh(run)
        run_id = run.id

    # Execute in a fresh session — errors handled below
    try:
        async with AsyncSessionLocal() as db:
            connection = await db.get(GitHubConnection, connection_id)
            token = decrypt_token(connection.encrypted_token)
            await _execute_sync(db, connection, token, run_id)
    except (GitHubValidationError, GitHubUnavailableError, ValueError) as exc:
        logger.error("Sync run %s failed: %s", run_id, exc)
        async with AsyncSessionLocal() as err_db:
            await _finish_run(err_db, run_id, SyncOutcome.FAILED, error_detail=str(exc)[:2000])
        raise
    except Exception as exc:
        logger.exception("Sync run %s unexpected failure", run_id)
        async with AsyncSessionLocal() as err_db:
            await _finish_run(err_db, run_id, SyncOutcome.FAILED, error_detail=str(exc)[:2000])
        raise

    return run_id


# ---------------------------------------------------------------------------
# Core sync logic
# ---------------------------------------------------------------------------

async def _execute_sync(
    db: AsyncSession,
    connection: GitHubConnection,
    token: str,
    run_id: uuid.UUID,
) -> None:
    """Inner sync execution. Commits incrementally."""
    repository_url = connection.repository_url

    # Resolve default branch (cache it on the connection)
    branch = connection.default_branch or await get_default_branch(repository_url, token)

    # Load configured sync folders
    folders = await _get_active_folders(db)
    if not folders:
        logger.warning("Sync run %s: no configured folders — skipping", run_id)
        await _finish_run(db, run_id, SyncOutcome.SUCCESS)
        return

    folder_prefixes = {f.rstrip("/") + "/" for f in folders}

    # Fetch full flat tree from GitHub (one API call)
    tree = await get_repo_tree(repository_url, token, branch)

    # Keep only .md blobs within configured folders
    relevant = [
        item for item in tree
        if item["path"].endswith(_MD_SUFFIX)
        and any(item["path"].startswith(prefix) for prefix in folder_prefixes)
    ]

    # Index current active synced docs by repo_path for O(1) lookup
    existing_result = await db.execute(
        select(SyncedDocument).where(
            SyncedDocument.connection_id == connection.id,
            SyncedDocument.is_active == True,  # noqa: E712
        )
    )
    existing_by_path: dict[str, SyncedDocument] = {
        d.repo_path: d for d in existing_result.scalars().all()
    }
    repo_paths_in_tree = {item["path"] for item in relevant}

    files_indexed = 0
    files_removed = 0
    files_unchanged = 0

    # --- New and changed files ---
    for item in relevant:
        repo_path: str = item["path"]
        tree_sha: str = item["sha"]
        existing = existing_by_path.get(repo_path)

        if existing and existing.content_sha == tree_sha:
            files_unchanged += 1
            continue

        # Content changed or new — fetch from GitHub
        content, blob_sha = await get_file_content(repository_url, token, repo_path, branch)
        now = datetime.now(timezone.utc)
        folder = _folder_for_path(repo_path, folders)
        title = _extract_title(content)

        if existing:
            # Update in-place
            existing.raw_content = content
            existing.content_sha = blob_sha
            existing.title = title
            existing.folder = folder
            existing.last_synced_at = now
            existing.updated_at = now
            await db.flush()
            await _requeue_kb_document(db, existing.id)
        else:
            # Insert new SyncedDocument
            synced_doc = SyncedDocument(
                connection_id=connection.id,
                repo_path=repo_path,
                title=title,
                raw_content=content,
                content_sha=blob_sha,
                folder=folder,
                is_active=True,
                last_synced_at=now,
            )
            db.add(synced_doc)
            await db.flush()
            kb_doc = KnowledgeBaseDocument(
                synced_document_id=synced_doc.id,
                index_status=KBIndexStatus.QUEUED.value,
            )
            db.add(kb_doc)

        files_indexed += 1
        await db.commit()  # Incremental commit — progress survives pod restart

    # --- Removed files (present in DB but absent from tree) ---
    for repo_path, existing in existing_by_path.items():
        if repo_path not in repo_paths_in_tree:
            existing.is_active = False
            existing.updated_at = datetime.now(timezone.utc)
            await db.flush()
            await _mark_kb_removed(db, existing.id)
            files_removed += 1

    # Update connection metadata
    connection.last_synced_at = datetime.now(timezone.utc)
    connection.default_branch = branch
    await db.commit()

    await _finish_run(
        db,
        run_id,
        SyncOutcome.SUCCESS,
        files_indexed=files_indexed,
        files_removed=files_removed,
        files_unchanged=files_unchanged,
    )
    logger.info(
        "Sync run %s complete: indexed=%d removed=%d unchanged=%d",
        run_id, files_indexed, files_removed, files_unchanged,
    )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

async def _get_active_folders(db: AsyncSession) -> list[str]:
    """Return the configured folder paths from RepoStructureConfig."""
    result = await db.execute(
        select(RepoStructureConfig)
        .order_by(
            RepoStructureConfig.is_default.asc(),
            RepoStructureConfig.updated_at.desc(),
        )
        .limit(1)
    )
    config = result.scalar_one_or_none()
    if config is None:
        return []
    return config.folders.get("folders", [])


def _folder_for_path(repo_path: str, folders: list[str]) -> str:
    """Return the configured folder that contains repo_path."""
    for folder in folders:
        prefix = folder.rstrip("/") + "/"
        if repo_path.startswith(prefix):
            return folder
    # Fallback: immediate parent directory
    parts = repo_path.rsplit("/", 1)
    return parts[0] if len(parts) > 1 else ""


def _extract_title(content: str) -> str | None:
    """Extract the first H1 heading from Markdown content."""
    for line in content.splitlines():
        stripped = line.strip()
        if stripped.startswith("# "):
            candidate = stripped[2:].strip()
            return candidate if candidate else None
    return None


async def _requeue_kb_document(db: AsyncSession, synced_document_id: uuid.UUID) -> None:
    """Reset an existing KB document to QUEUED for re-indexing, or create one."""
    result = await db.execute(
        select(KnowledgeBaseDocument).where(
            KnowledgeBaseDocument.synced_document_id == synced_document_id
        )
    )
    kb_doc = result.scalar_one_or_none()
    if kb_doc:
        kb_doc.index_status = KBIndexStatus.QUEUED.value
        kb_doc.failure_reason = None
        kb_doc.updated_at = datetime.now(timezone.utc)
    else:
        db.add(KnowledgeBaseDocument(
            synced_document_id=synced_document_id,
            index_status=KBIndexStatus.QUEUED.value,
        ))


async def _mark_kb_removed(db: AsyncSession, synced_document_id: uuid.UUID) -> None:
    """Delete chunks and mark the associated KB document as REMOVED."""
    from utils.indexer import remove_document  # noqa: PLC0415

    result = await db.execute(
        select(KnowledgeBaseDocument).where(
            KnowledgeBaseDocument.synced_document_id == synced_document_id
        )
    )
    kb_doc = result.scalar_one_or_none()
    if kb_doc:
        await remove_document(db, kb_doc.id)


async def _finish_run(
    db: AsyncSession,
    run_id: uuid.UUID,
    outcome: SyncOutcome,
    files_indexed: int = 0,
    files_removed: int = 0,
    files_unchanged: int = 0,
    error_detail: str | None = None,
) -> None:
    await db.execute(
        update(SyncRun)
        .where(SyncRun.id == run_id)
        .values(
            outcome=outcome.value,
            finished_at=datetime.now(timezone.utc),
            files_indexed=files_indexed,
            files_removed=files_removed,
            files_unchanged=files_unchanged,
            error_detail=error_detail,
        )
    )
    await db.commit()


# ---------------------------------------------------------------------------
# Startup recovery for interrupted syncs
# ---------------------------------------------------------------------------

async def recover_interrupted_syncs() -> None:
    """Mark any SyncRun left IN_PROGRESS from a prior crash as INTERRUPTED."""
    async with AsyncSessionLocal() as db:
        result = await db.execute(
            update(SyncRun)
            .where(SyncRun.outcome == SyncOutcome.IN_PROGRESS.value)
            .values(
                outcome=SyncOutcome.INTERRUPTED.value,
                finished_at=datetime.now(timezone.utc),
                error_detail="Interrupted by server restart.",
            )
            .returning(SyncRun.id)
        )
        recovered = result.fetchall()
        await db.commit()
        if recovered:
            logger.info(
                "Sync startup recovery: marked %d interrupted sync run(s)", len(recovered)
            )
