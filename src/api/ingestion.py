"""Ingestion & Markdown Pipeline API endpoints."""
import io
import os
import uuid
import zipfile
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.config import settings
from src.models.ingestion_batch import BatchStatus, IngestionBatch
from src.models.ingestion_document import IngestionDocument, ProcessingStatus
from src.models.knowledge_base_document import KBIndexStatus, KnowledgeBaseDocument
from src.models.processed_document import ProcessedDocument, ReviewStatus
from src.models.repo_structure_config import RepoStructureConfig
from utils.audit import write_audit
from src.models.user import Role, User
from utils.auth import get_current_user, require_role
from utils.db import get_db
from utils.extractors import SUPPORTED_EXTENSIONS
from utils.gcs import delete_from_gcs, upload_to_gcs

router = APIRouter(prefix="/ingestion", tags=["ingestion"])

MAX_FILE_SIZE_BYTES = 50 * 1024 * 1024  # 50 MB


def _recompute_batch_status(batch: IngestionBatch) -> None:
    terminal = batch.completed_count + batch.failed_count
    if terminal >= batch.total_documents:
        if batch.failed_count == 0:
            batch.status = BatchStatus.COMPLETED.value
        else:
            batch.status = BatchStatus.COMPLETED_WITH_FAILURES.value
    else:
        batch.status = BatchStatus.IN_PROGRESS.value


# -----------------------------------------------------------------
# Helpers
# -----------------------------------------------------------------

def _request_id(request: Request) -> str:
    return getattr(request.state, "request_id", "unknown")


def _doc_response(doc: IngestionDocument, review_status: str | None = None) -> dict:
    return {
        "id": str(doc.id),
        "original_filename": doc.original_filename,
        "original_file_type": doc.original_file_type,
        "relative_path": doc.relative_path,
        "file_size_bytes": doc.file_size_bytes,
        "processing_status": doc.processing_status,
        "failure_reason": doc.failure_reason,
        "retry_count": doc.retry_count,
        "queued_at": doc.queued_at.isoformat() if doc.queued_at else None,
        "processing_started_at": doc.processing_started_at.isoformat() if doc.processing_started_at else None,
        "processing_completed_at": doc.processing_completed_at.isoformat() if doc.processing_completed_at else None,
        "review_status": review_status,
    }


def _batch_summary(batch: IngestionBatch) -> dict:
    return {
        "batch_id": str(batch.id),
        "source_folder_name": batch.source_folder_name,
        "status": batch.status,
        "total_documents": batch.total_documents,
        "completed_count": batch.completed_count,
        "failed_count": batch.failed_count,
        "submitted_at": batch.submitted_at.isoformat() if batch.submitted_at else None,
    }


async def _get_owned_batch(batch_id: uuid.UUID, user_id: uuid.UUID, db: AsyncSession) -> IngestionBatch:
    batch = await db.get(IngestionBatch, batch_id)
    if batch is None or batch.submitted_by != user_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"error": "Batch not found", "code": "BATCH_NOT_FOUND"},
        )
    return batch


async def _get_document_in_batch(
    doc_id: uuid.UUID, batch_id: uuid.UUID, db: AsyncSession
) -> IngestionDocument:
    doc = await db.get(IngestionDocument, doc_id)
    if doc is None or doc.batch_id != batch_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"error": "Document not found", "code": "DOCUMENT_NOT_FOUND"},
        )
    return doc


# -----------------------------------------------------------------
# POST /batches — Submit a new ingestion batch
# -----------------------------------------------------------------

@router.post("/batches", status_code=status.HTTP_201_CREATED)
async def submit_batch(
    request: Request,
    folder_name: str = Form(...),
    files: list[UploadFile] = File(...),
    current_user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    if not files:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"error": "No files selected", "code": "NO_FILES_SELECTED", "request_id": _request_id(request)},
        )

    # Validate all files before creating any DB rows
    for f in files:
        ext = os.path.splitext(f.filename or "")[1].lower()
        if ext not in SUPPORTED_EXTENSIONS:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={
                    "error": f"Unsupported file type: {ext or '(no extension)'}",
                    "code": "UNSUPPORTED_FILE_TYPE",
                    "filename": f.filename,
                    "request_id": _request_id(request),
                },
            )
        # Read size from Content-Length or by reading the spool
        size = f.size or 0
        if size == 0:
            # FastAPI may not populate .size — check content-length header
            content_length = request.headers.get("content-length")
            # As a fallback, size check happens post-upload; rely on server-side check
        if size > MAX_FILE_SIZE_BYTES:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={
                    "error": f"File '{f.filename}' exceeds the 50 MB size limit",
                    "code": "FILE_TOO_LARGE",
                    "filename": f.filename,
                    "request_id": _request_id(request),
                },
            )

    # Admins bypass approval; all other roles submit for review
    initial_status = (
        ProcessingStatus.QUEUED.value
        if current_user.role == Role.ADMIN.value
        else ProcessingStatus.PENDING_APPROVAL.value
    )

    # Create batch
    batch = IngestionBatch(
        submitted_by=current_user.id,
        source_folder_name=folder_name,
        total_documents=len(files),
    )
    db.add(batch)
    await db.flush()

    # Upload each file to GCS and create document rows
    documents: list[IngestionDocument] = []
    for f in files:
        doc_id = uuid.uuid4()
        ext = os.path.splitext(f.filename or "")[1].lower()

        try:
            gcs_path = await upload_to_gcs(f, settings.GCS_BUCKET_NAME, str(batch.id), str(doc_id))
        except Exception as exc:
            await db.rollback()
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail={"error": "File upload failed", "code": "GCS_UNAVAILABLE", "request_id": _request_id(request)},
            ) from exc

        doc = IngestionDocument(
            id=doc_id,
            batch_id=batch.id,
            original_filename=f.filename or "file",
            original_file_type=ext,
            relative_path=f.filename or "file",
            file_size_bytes=f.size or 0,
            gcs_object_path=gcs_path,
            processing_status=initial_status,
        )
        db.add(doc)
        documents.append(doc)

    await write_audit(
        db,
        "ingestion_batch_submitted",
        actor_id=current_user.id,
        target_id=batch.id,
        metadata={
            "total_documents": len(files),
            "source_folder_name": folder_name,
            "initial_status": initial_status,
        },
    )
    await db.commit()

    return {
        "data": {
            **_batch_summary(batch),
            "documents": [_doc_response(d) for d in documents],
        },
        "request_id": _request_id(request),
    }


# -----------------------------------------------------------------
# GET /batches — List user's batches
# -----------------------------------------------------------------

@router.get("/batches")
async def list_batches(
    request: Request,
    batch_status: str | None = None,
    current_user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    stmt = (
        select(IngestionBatch)
        .where(IngestionBatch.submitted_by == current_user.id)
        .order_by(IngestionBatch.submitted_at.desc())
    )
    if batch_status:
        stmt = stmt.where(IngestionBatch.status == batch_status)

    result = await db.execute(stmt)
    batches = result.scalars().all()

    return {
        "data": [_batch_summary(b) for b in batches],
        "request_id": _request_id(request),
    }


# -----------------------------------------------------------------
# GET /batches/{batch_id} — Batch status + document list
# -----------------------------------------------------------------

@router.get("/batches/{batch_id}")
async def get_batch(
    request: Request,
    batch_id: uuid.UUID,
    current_user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    batch = await _get_owned_batch(batch_id, current_user.id, db)

    docs_result = await db.execute(
        select(IngestionDocument)
        .where(IngestionDocument.batch_id == batch_id)
        .order_by(IngestionDocument.queued_at)
    )
    docs = docs_result.scalars().all()

    # Fetch review statuses for completed documents
    completed_ids = [d.id for d in docs if d.processing_status == ProcessingStatus.COMPLETED.value]
    review_map: dict[uuid.UUID, str] = {}
    if completed_ids:
        pd_result = await db.execute(
            select(ProcessedDocument).where(ProcessedDocument.ingestion_document_id.in_(completed_ids))
        )
        for pd in pd_result.scalars().all():
            review_map[pd.ingestion_document_id] = pd.review_status

    return {
        "data": {
            **_batch_summary(batch),
            "documents": [_doc_response(d, review_map.get(d.id)) for d in docs],
        },
        "request_id": _request_id(request),
    }


# -----------------------------------------------------------------
# POST /batches/{batch_id}/documents/{doc_id}/retry
# -----------------------------------------------------------------

@router.post("/batches/{batch_id}/documents/{doc_id}/retry")
async def retry_document(
    request: Request,
    batch_id: uuid.UUID,
    doc_id: uuid.UUID,
    current_user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    await _get_owned_batch(batch_id, current_user.id, db)
    doc = await _get_document_in_batch(doc_id, batch_id, db)

    if doc.processing_status != ProcessingStatus.FAILED.value:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"error": "Document is not in failed status", "code": "DOCUMENT_NOT_FAILED", "request_id": _request_id(request)},
        )

    doc.processing_status = ProcessingStatus.QUEUED.value
    doc.failure_reason = None
    doc.processing_started_at = None
    doc.processing_completed_at = None
    doc.retry_count += 1

    # Update batch counters
    batch = await db.get(IngestionBatch, batch_id)
    if batch:
        batch.failed_count = max(0, batch.failed_count - 1)
        batch.status = BatchStatus.IN_PROGRESS.value

    await write_audit(
        db,
        "ingestion_document_retried",
        actor_id=current_user.id,
        target_id=doc_id,
        metadata={"batch_id": str(batch_id), "filename": doc.original_filename, "retry_count": doc.retry_count},
    )
    await db.commit()

    return {
        "data": {"id": str(doc.id), "processing_status": doc.processing_status, "retry_count": doc.retry_count},
        "request_id": _request_id(request),
    }


# -----------------------------------------------------------------
# GET /batches/{batch_id}/documents/{doc_id}/preview
# -----------------------------------------------------------------

@router.get("/batches/{batch_id}/documents/{doc_id}/preview")
async def preview_document(
    request: Request,
    batch_id: uuid.UUID,
    doc_id: uuid.UUID,
    current_user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    await _get_owned_batch(batch_id, current_user.id, db)
    doc = await _get_document_in_batch(doc_id, batch_id, db)

    if doc.processing_status != ProcessingStatus.COMPLETED.value:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"error": "Document is not completed", "code": "DOCUMENT_NOT_COMPLETED", "request_id": _request_id(request)},
        )

    pd_result = await db.execute(
        select(ProcessedDocument).where(ProcessedDocument.ingestion_document_id == doc_id)
    )
    pd = pd_result.scalar_one_or_none()
    if pd is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail={"error": "Processed document not found", "code": "DOCUMENT_NOT_FOUND"})

    return {
        "data": {
            "id": str(doc.id),
            "original_filename": doc.original_filename,
            "review_status": pd.review_status,
            "extracted_title": pd.extracted_title,
            "extracted_author": pd.extracted_author,
            "extracted_date": pd.extracted_date,
            "markdown_content": pd.markdown_content,
        },
        "request_id": _request_id(request),
    }


# -----------------------------------------------------------------
# PATCH /batches/{batch_id}/documents/{doc_id}/review
# -----------------------------------------------------------------

class ReviewRequest(BaseModel):
    review_status: str
    reprocessing_note: Optional[str] = None


@router.patch("/batches/{batch_id}/documents/{doc_id}/review")
async def review_document(
    request: Request,
    batch_id: uuid.UUID,
    doc_id: uuid.UUID,
    body: ReviewRequest,
    current_user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    valid_statuses = {ReviewStatus.APPROVED.value, ReviewStatus.FLAGGED_FOR_REPROCESSING.value}
    if body.review_status not in valid_statuses:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail={"error": f"Invalid review status: {body.review_status}", "code": "INVALID_REVIEW_STATUS", "request_id": _request_id(request)},
        )

    await _get_owned_batch(batch_id, current_user.id, db)
    doc = await _get_document_in_batch(doc_id, batch_id, db)

    if doc.processing_status != ProcessingStatus.COMPLETED.value:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"error": "Document is not completed", "code": "DOCUMENT_NOT_COMPLETED", "request_id": _request_id(request)},
        )

    pd_result = await db.execute(
        select(ProcessedDocument).where(ProcessedDocument.ingestion_document_id == doc_id)
    )
    pd = pd_result.scalar_one_or_none()

    if body.review_status == ReviewStatus.APPROVED.value:
        if pd:
            pd.review_status = ReviewStatus.APPROVED.value
            pd.reviewed_by = current_user.id
            pd.reviewed_at = datetime.now(timezone.utc)

            # Queue KB indexing — upsert KnowledgeBaseDocument
            existing_kb = await db.execute(
                select(KnowledgeBaseDocument).where(
                    KnowledgeBaseDocument.processed_document_id == pd.id
                )
            )
            kb_doc = existing_kb.scalar_one_or_none()
            if kb_doc is None:
                kb_doc = KnowledgeBaseDocument(processed_document_id=pd.id)
                db.add(kb_doc)
            else:
                kb_doc.index_status = KBIndexStatus.QUEUED.value
                kb_doc.failure_reason = None

        await write_audit(db, "ingestion_document_approved", actor_id=current_user.id, target_id=doc_id, metadata={"batch_id": str(batch_id)})
        await db.commit()
        return {
            "data": {"id": str(doc.id), "review_status": ReviewStatus.APPROVED.value, "processing_status": doc.processing_status},
            "request_id": _request_id(request),
        }

    # flagged_for_reprocessing — remove from KB if previously indexed
    if pd:
        # Remove KB document (cascades to content_chunks)
        existing_kb = await db.execute(
            select(KnowledgeBaseDocument).where(
                KnowledgeBaseDocument.processed_document_id == pd.id
            )
        )
        kb_doc = existing_kb.scalar_one_or_none()
        if kb_doc is not None:
            await db.delete(kb_doc)

        await db.delete(pd)
        await db.flush()

    doc.reprocessing_note = body.reprocessing_note
    doc.processing_status = ProcessingStatus.QUEUED.value
    doc.processing_started_at = None
    doc.processing_completed_at = None
    doc.failure_reason = None

    batch = await db.get(IngestionBatch, batch_id)
    if batch:
        batch.completed_count = max(0, batch.completed_count - 1)
        batch.status = BatchStatus.IN_PROGRESS.value

    await write_audit(
        db,
        "ingestion_document_flagged",
        actor_id=current_user.id,
        target_id=doc_id,
        metadata={"batch_id": str(batch_id), "reprocessing_note": body.reprocessing_note},
    )
    await db.commit()

    return {
        "data": {
            "id": str(doc.id),
            "review_status": ReviewStatus.FLAGGED_FOR_REPROCESSING.value,
            "processing_status": ProcessingStatus.QUEUED.value,
        },
        "request_id": _request_id(request),
    }


# -----------------------------------------------------------------
# POST /batches/{batch_id}/export — ZIP download
# -----------------------------------------------------------------

class ExportRequest(BaseModel):
    document_ids: list[uuid.UUID] = []


@router.post("/batches/{batch_id}/export")
async def export_batch(
    request: Request,
    batch_id: uuid.UUID,
    body: ExportRequest,
    current_user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    await _get_owned_batch(batch_id, current_user.id, db)

    # Fetch completed documents with their processed output
    stmt = (
        select(IngestionDocument, ProcessedDocument)
        .join(ProcessedDocument, ProcessedDocument.ingestion_document_id == IngestionDocument.id)
        .where(
            IngestionDocument.batch_id == batch_id,
            IngestionDocument.processing_status == ProcessingStatus.COMPLETED.value,
        )
    )
    if body.document_ids:
        stmt = stmt.where(IngestionDocument.id.in_(body.document_ids))

    result = await db.execute(stmt)
    rows = result.all()

    if not rows:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"error": "No exportable documents found", "code": "NO_EXPORTABLE_DOCUMENTS", "request_id": _request_id(request)},
        )

    # Build ZIP in memory
    buf = io.BytesIO()
    exported_ids: list[str] = []
    with zipfile.ZipFile(buf, mode="w", compression=zipfile.ZIP_DEFLATED) as zf:
        for doc, pd in rows:
            base, _ = os.path.splitext(doc.relative_path)
            arcname = f"{base}.md"
            zf.writestr(arcname, pd.markdown_content)
            exported_ids.append(str(doc.id))
    buf.seek(0)

    await write_audit(
        db,
        "ingestion_export_downloaded",
        actor_id=current_user.id,
        target_id=batch_id,
        metadata={"document_ids": exported_ids, "file_count": len(exported_ids)},
    )
    await db.commit()

    return StreamingResponse(
        buf,
        media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="batch_{batch_id}.zip"'},
    )


# -----------------------------------------------------------------
# GET /pending — Admin: list all documents awaiting approval
# -----------------------------------------------------------------

@router.get("/pending", dependencies=[require_role(Role.ADMIN)])
async def list_pending_documents(
    request: Request,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    stmt = (
        select(
            IngestionDocument,
            User.display_name,
        )
        .join(IngestionBatch, IngestionBatch.id == IngestionDocument.batch_id)
        .join(User, User.id == IngestionBatch.submitted_by)
        .where(IngestionDocument.processing_status == ProcessingStatus.PENDING_APPROVAL.value)
        .order_by(IngestionDocument.queued_at)
    )
    result = await db.execute(stmt)
    rows = result.all()

    data = [
        {
            **_doc_response(doc),
            "batch_id": str(doc.batch_id),
            "submitted_by_name": display_name,
        }
        for doc, display_name in rows
    ]

    return {
        "data": data,
        "total": len(data),
        "request_id": _request_id(request),
    }


# -----------------------------------------------------------------
# POST /documents/{doc_id}/approve — Admin: approve pending document
# -----------------------------------------------------------------

class ApproveRequest(BaseModel):
    destination_folder: str


@router.post("/documents/{doc_id}/approve", dependencies=[require_role(Role.ADMIN)])
async def approve_document(
    request: Request,
    doc_id: uuid.UUID,
    body: ApproveRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    doc = await db.get(IngestionDocument, doc_id)
    if doc is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"error": "Document not found", "code": "DOCUMENT_NOT_FOUND", "request_id": _request_id(request)},
        )
    if doc.processing_status != ProcessingStatus.PENDING_APPROVAL.value:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"error": "Document is not pending approval", "code": "DOCUMENT_NOT_PENDING", "request_id": _request_id(request)},
        )

    # Validate destination_folder against active repo config
    config_result = await db.execute(
        select(RepoStructureConfig).where(RepoStructureConfig.is_default == True).limit(1)  # noqa: E712
    )
    repo_config = config_result.scalar_one_or_none()
    configured_folders: list[str] = (repo_config.folders.get("folders", []) if repo_config else [])
    if body.destination_folder not in configured_folders:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={"error": f"Folder '{body.destination_folder}' is not configured", "code": "FOLDER_NOT_CONFIGURED", "request_id": _request_id(request)},
        )

    doc.destination_folder = body.destination_folder
    doc.processing_status = ProcessingStatus.QUEUED.value
    doc.queued_at = datetime.now(timezone.utc)

    await write_audit(
        db,
        "ingestion_document_approved",
        actor_id=current_user.id,
        target_id=doc_id,
        metadata={"batch_id": str(doc.batch_id), "filename": doc.original_filename, "destination_folder": body.destination_folder},
    )
    await db.commit()

    return {
        "data": {"id": str(doc.id), "processing_status": doc.processing_status, "destination_folder": doc.destination_folder},
        "request_id": _request_id(request),
    }


# -----------------------------------------------------------------
# GET /prs — Admin: list all open PRs
# -----------------------------------------------------------------

@router.get("/prs", dependencies=[require_role(Role.ADMIN)])
async def list_open_prs(
    request: Request,
    limit: int = 50,
    offset: int = 0,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    stmt = (
        select(IngestionDocument, User.display_name, User.email)
        .join(IngestionBatch, IngestionBatch.id == IngestionDocument.batch_id)
        .join(User, User.id == IngestionBatch.submitted_by)
        .where(IngestionDocument.processing_status == ProcessingStatus.PR_OPEN.value)
        .order_by(IngestionDocument.queued_at.desc())
    )
    count_result = await db.execute(
        select(IngestionDocument).where(IngestionDocument.processing_status == ProcessingStatus.PR_OPEN.value)
    )
    total = len(count_result.scalars().all())

    result = await db.execute(stmt.limit(limit).offset(offset))
    rows = result.all()

    data = [
        {
            "id": str(doc.id),
            "original_filename": doc.original_filename,
            "destination_folder": doc.destination_folder,
            "github_branch": doc.github_branch,
            "github_pr_number": doc.github_pr_number,
            "github_pr_url": doc.github_pr_url,
            "submitted_by_name": display_name,
            "submitted_by_email": email,
            "queued_at": doc.queued_at.isoformat() if doc.queued_at else None,
        }
        for doc, display_name, email in rows
    ]

    return {
        "data": data,
        "total": total,
        "request_id": _request_id(request),
    }


# -----------------------------------------------------------------
# GET /documents/{doc_id}/pr — Admin: PR review data
# -----------------------------------------------------------------

@router.get("/documents/{doc_id}/pr", dependencies=[require_role(Role.ADMIN)])
async def get_pr_review(
    request: Request,
    doc_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
):
    doc = await db.get(IngestionDocument, doc_id)
    if doc is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail={"error": "Document not found", "code": "DOCUMENT_NOT_FOUND"})
    if doc.processing_status != ProcessingStatus.PR_OPEN.value:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"error": "Document does not have an open PR", "code": "DOCUMENT_NOT_PR_OPEN"},
        )

    pd_result = await db.execute(
        select(ProcessedDocument).where(ProcessedDocument.ingestion_document_id == doc_id)
    )
    pd = pd_result.scalar_one_or_none()

    config_result = await db.execute(
        select(RepoStructureConfig).where(RepoStructureConfig.is_default == True).limit(1)  # noqa: E712
    )
    repo_config = config_result.scalar_one_or_none()
    configured_folders: list[str] = (repo_config.folders.get("folders", []) if repo_config else [])

    return {
        "data": {
            "id": str(doc.id),
            "original_filename": doc.original_filename,
            "destination_folder": doc.destination_folder,
            "github_branch": doc.github_branch,
            "github_pr_number": doc.github_pr_number,
            "github_pr_url": doc.github_pr_url,
            "markdown_content": pd.markdown_content if pd else "",
            "current_folder": doc.destination_folder,
            "configured_folders": configured_folders,
        },
        "request_id": _request_id(request),
    }


# -----------------------------------------------------------------
# POST /documents/{doc_id}/pr/merge — Admin: merge PR
# -----------------------------------------------------------------

class PRMergeRequest(BaseModel):
    destination_folder: Optional[str] = None


@router.post("/documents/{doc_id}/pr/merge", dependencies=[require_role(Role.ADMIN)])
async def merge_pr_endpoint(
    request: Request,
    doc_id: uuid.UUID,
    body: PRMergeRequest = PRMergeRequest(),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    from src.models.github_connection import GitHubConnection  # noqa: PLC0415
    from utils.crypto import decrypt_token  # noqa: PLC0415
    from utils.github_api import (  # noqa: PLC0415
        merge_pr as _merge_pr,
        get_file_content,
        delete_file,
        commit_file,
        GitHubUnavailableError,
    )
    from utils.sync import run_sync  # noqa: PLC0415
    from src.models.sync_run import SyncTriggerType  # noqa: PLC0415

    doc = await db.get(IngestionDocument, doc_id)
    if doc is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail={"error": "Document not found", "code": "DOCUMENT_NOT_FOUND"})
    if doc.processing_status != ProcessingStatus.PR_OPEN.value:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"error": "Document does not have an open PR", "code": "DOCUMENT_NOT_PR_OPEN"},
        )

    conn_result = await db.execute(
        select(GitHubConnection).where(GitHubConnection.status == "active").limit(1)
    )
    conn = conn_result.scalar_one_or_none()
    if conn is None:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail={"error": "No active GitHub connection", "code": "GITHUB_UNAVAILABLE"})

    try:
        token = decrypt_token(conn.encrypted_token)
        final_folder = doc.destination_folder

        # Optionally move file to a different folder before merging
        if body.destination_folder and body.destination_folder != doc.destination_folder:
            import re as _re  # noqa: PLC0415
            import os as _os  # noqa: PLC0415
            base_name = _os.path.splitext(doc.original_filename)[0]
            slug = _re.sub(r"[^a-z0-9]+", "-", base_name.lower()).strip("-")[:40]

            old_path = f"{doc.destination_folder}/{slug}.md"
            new_path = f"{body.destination_folder}/{slug}.md"

            _, old_sha = await get_file_content(conn.repository_url, token, old_path, ref=doc.github_branch)
            await delete_file(conn.repository_url, token, old_path, old_sha,
                              f"ingest: move to {body.destination_folder}", doc.github_branch)
            pd_result = await db.execute(
                select(ProcessedDocument).where(ProcessedDocument.ingestion_document_id == doc_id)
            )
            pd = pd_result.scalar_one_or_none()
            await commit_file(conn.repository_url, token,
                              branch=doc.github_branch, path=new_path,
                              content=(pd.markdown_content if pd else ""),
                              message=f"ingest: add to {body.destination_folder}")
            final_folder = body.destination_folder

        await _merge_pr(conn.repository_url, token, doc.github_pr_number, merge_method=settings.GITHUB_MERGE_METHOD)

    except GitHubUnavailableError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={"error": str(exc), "code": "GITHUB_UNAVAILABLE", "request_id": _request_id(request)},
        ) from exc

    doc.processing_status = ProcessingStatus.MERGED.value
    doc.destination_folder = final_folder

    # Update batch completed counter
    batch = await db.get(IngestionBatch, doc.batch_id)
    if batch:
        batch.completed_count += 1
        _recompute_batch_status(batch)

    await write_audit(db, "ingestion_pr_merged", actor_id=current_user.id, target_id=doc_id,
                      metadata={"batch_id": str(doc.batch_id), "pr_number": doc.github_pr_number, "merged_to_folder": final_folder})
    await db.commit()

    # Trigger re-sync (fire-and-forget)
    import asyncio  # noqa: PLC0415
    asyncio.create_task(run_sync(connection_id=conn.id, triggered_by=current_user.id, trigger_type=SyncTriggerType.MANUAL.value))

    # Notify submitter (best-effort)
    try:
        from utils.email import send_pr_merged_notification  # noqa: PLC0415
        batch_result = await db.get(IngestionBatch, doc.batch_id)
        if batch_result:
            user_result = await db.get(User, batch_result.submitted_by)
            if user_result:
                await send_pr_merged_notification(user_result.email, doc.original_filename, user_result.display_name)
    except Exception:
        pass

    return {
        "data": {
            "id": str(doc.id),
            "processing_status": doc.processing_status,
            "merged_to_folder": final_folder,
            "sync_triggered": True,
        },
        "request_id": _request_id(request),
    }


# -----------------------------------------------------------------
# POST /documents/{doc_id}/pr/close — Admin: close (reject) PR
# -----------------------------------------------------------------

@router.post("/documents/{doc_id}/pr/close", dependencies=[require_role(Role.ADMIN)])
async def close_pr_endpoint(
    request: Request,
    doc_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    from src.models.github_connection import GitHubConnection  # noqa: PLC0415
    from utils.crypto import decrypt_token  # noqa: PLC0415
    from utils.github_api import close_pr as _close_pr, GitHubUnavailableError  # noqa: PLC0415

    doc = await db.get(IngestionDocument, doc_id)
    if doc is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail={"error": "Document not found", "code": "DOCUMENT_NOT_FOUND"})
    if doc.processing_status != ProcessingStatus.PR_OPEN.value:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"error": "Document does not have an open PR", "code": "DOCUMENT_NOT_PR_OPEN"},
        )

    conn_result = await db.execute(
        select(GitHubConnection).where(GitHubConnection.status == "active").limit(1)
    )
    conn = conn_result.scalar_one_or_none()
    if conn is None:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail={"error": "No active GitHub connection", "code": "GITHUB_UNAVAILABLE"})

    try:
        token = decrypt_token(conn.encrypted_token)
        await _close_pr(conn.repository_url, token, doc.github_pr_number)
    except GitHubUnavailableError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={"error": str(exc), "code": "GITHUB_UNAVAILABLE", "request_id": _request_id(request)},
        ) from exc

    doc.processing_status = ProcessingStatus.REJECTED.value

    # Update batch failure counter
    batch = await db.get(IngestionBatch, doc.batch_id)
    if batch:
        batch.failed_count += 1
        _recompute_batch_status(batch)

    await write_audit(db, "ingestion_pr_closed", actor_id=current_user.id, target_id=doc_id,
                      metadata={"batch_id": str(doc.batch_id), "pr_number": doc.github_pr_number})
    await db.commit()

    # Notify submitter (best-effort)
    try:
        from utils.email import send_pr_rejected_notification  # noqa: PLC0415
        batch_result = await db.get(IngestionBatch, doc.batch_id)
        if batch_result:
            user_result = await db.get(User, batch_result.submitted_by)
            if user_result:
                await send_pr_rejected_notification(user_result.email, doc.original_filename, user_result.display_name)
    except Exception:
        pass

    return {
        "data": {"id": str(doc.id), "processing_status": doc.processing_status},
        "request_id": _request_id(request),
    }


# -----------------------------------------------------------------
# POST /documents/{doc_id}/reject — Admin: reject and delete pending document
# -----------------------------------------------------------------

@router.post("/documents/{doc_id}/reject", dependencies=[require_role(Role.ADMIN)])
async def reject_document(
    request: Request,
    doc_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    doc = await db.get(IngestionDocument, doc_id)
    if doc is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"error": "Document not found", "code": "DOCUMENT_NOT_FOUND", "request_id": _request_id(request)},
        )
    if doc.processing_status != ProcessingStatus.PENDING_APPROVAL.value:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"error": "Document is not pending approval", "code": "DOCUMENT_NOT_PENDING", "request_id": _request_id(request)},
        )

    gcs_path = doc.gcs_object_path
    doc.processing_status = ProcessingStatus.REJECTED.value

    await write_audit(
        db,
        "ingestion_document_rejected",
        actor_id=current_user.id,
        target_id=doc_id,
        metadata={"batch_id": str(doc.batch_id), "filename": doc.original_filename},
    )
    await db.commit()

    # Delete staged GCS file after committing status (best-effort)
    try:
        await delete_from_gcs(settings.GCS_BUCKET_NAME, gcs_path)
    except Exception:
        pass  # GCS cleanup failure does not affect the rejection result

    return {
        "data": {"id": str(doc.id), "processing_status": doc.processing_status},
        "request_id": _request_id(request),
    }
