"""Content browser API — synced Markdown files from the connected GitHub repo."""
import uuid

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.models.knowledge_base_document import KnowledgeBaseDocument
from src.models.synced_document import SyncedDocument
from utils.auth import get_current_user
from utils.db import get_db

router = APIRouter(prefix="/content", tags=["content"])

PAGE_SIZE_DEFAULT = 50
PAGE_SIZE_MAX = 100


def _request_id(request: Request) -> str:
    return getattr(request.state, "request_id", "unknown")


def _synced_doc_response(doc: SyncedDocument, kb: KnowledgeBaseDocument | None) -> dict:
    return {
        "id": str(doc.id),
        "title": doc.title,
        "repo_path": doc.repo_path,
        "folder": doc.folder,
        "index_status": kb.index_status if kb else "queued",
        "last_synced_at": doc.last_synced_at.isoformat(),
        "chunk_count": kb.chunk_count if kb else None,
    }


# -----------------------------------------------------------------
# GET /content
# -----------------------------------------------------------------

@router.get("")
async def list_content(
    request: Request,
    search: str | None = None,
    folder: str | None = None,
    limit: int = PAGE_SIZE_DEFAULT,
    offset: int = 0,
    _current_user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    limit = min(limit, PAGE_SIZE_MAX)

    base = (
        select(SyncedDocument, KnowledgeBaseDocument)
        .outerjoin(
            KnowledgeBaseDocument,
            KnowledgeBaseDocument.synced_document_id == SyncedDocument.id,
        )
        .where(SyncedDocument.is_active == True)  # noqa: E712
    )

    if search:
        pattern = f"%{search}%"
        base = base.where(
            or_(
                SyncedDocument.title.ilike(pattern),
                SyncedDocument.repo_path.ilike(pattern),
            )
        )

    if folder:
        base = base.where(SyncedDocument.folder == folder)

    total_result = await db.execute(
        select(func.count()).select_from(base.subquery())
    )
    total = total_result.scalar_one()

    rows_result = await db.execute(
        base.order_by(SyncedDocument.last_synced_at.desc()).limit(limit).offset(offset)
    )
    rows = rows_result.all()

    return {
        "data": {
            "items": [_synced_doc_response(doc, kb) for doc, kb in rows],
            "total": total,
        },
        "request_id": _request_id(request),
    }


# -----------------------------------------------------------------
# GET /content/{content_id}
# -----------------------------------------------------------------

@router.get("/{content_id}")
async def get_content_item(
    request: Request,
    content_id: uuid.UUID,
    _current_user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(SyncedDocument, KnowledgeBaseDocument)
        .outerjoin(
            KnowledgeBaseDocument,
            KnowledgeBaseDocument.synced_document_id == SyncedDocument.id,
        )
        .where(SyncedDocument.id == content_id, SyncedDocument.is_active == True)  # noqa: E712
    )
    row = result.one_or_none()

    if row is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"error": "Content item not found", "code": "CONTENT_NOT_FOUND"},
        )

    doc, kb = row
    return {
        "data": {
            **_synced_doc_response(doc, kb),
            "raw_content": doc.raw_content,
        },
        "request_id": _request_id(request),
    }
