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
from utils.audit import write_audit
from utils.auth import get_current_user
from utils.db import get_db
from utils.extractors import SUPPORTED_EXTENSIONS
from utils.gcs import upload_to_gcs

router = APIRouter(prefix="/ingestion", tags=["ingestion"])

MAX_FILE_SIZE_BYTES = 50 * 1024 * 1024  # 50 MB


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
            processing_status=ProcessingStatus.QUEUED.value,
        )
        db.add(doc)
        documents.append(doc)

    await write_audit(
        db,
        "ingestion_batch_submitted",
        actor_id=current_user.id,
        target_id=batch.id,
        metadata={"total_documents": len(files), "source_folder_name": folder_name},
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
