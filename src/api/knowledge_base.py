"""Admin Knowledge Base management endpoints."""
import uuid

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.config import settings
from src.models.knowledge_base_document import KBIndexStatus, KnowledgeBaseDocument
from src.models.processed_document import ProcessedDocument, ReviewStatus
from utils.auth import get_current_user
from utils.db import get_db

router = APIRouter(prefix="/admin/knowledge-base", tags=["knowledge-base"])

_ADMIN_TOKEN_HEADER = "X-Admin-Token"


def _verify_admin(request: Request) -> None:
    token = request.headers.get(_ADMIN_TOKEN_HEADER)
    if not token or token != settings.ADMIN_TOKEN:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={"error": "Invalid or missing admin token", "code": "FORBIDDEN"},
        )


def _request_id(request: Request) -> str:
    return getattr(request.state, "request_id", "unknown")


# -----------------------------------------------------------------
# GET /admin/knowledge-base/status — KB indexing summary
# -----------------------------------------------------------------

@router.get("/status")
async def kb_status(
    request: Request,
    current_user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    _verify_admin(request)

    result = await db.execute(select(KnowledgeBaseDocument))
    kb_docs = result.scalars().all()

    counts: dict[str, int] = {s.value: 0 for s in KBIndexStatus}
    for doc in kb_docs:
        counts[doc.index_status] = counts.get(doc.index_status, 0) + 1

    return {
        "data": {
            "total": len(kb_docs),
            "by_status": counts,
        },
        "request_id": _request_id(request),
    }


# -----------------------------------------------------------------
# POST /admin/knowledge-base/reindex — Re-queue failed/removed docs
# -----------------------------------------------------------------

@router.post("/reindex")
async def reindex_failed(
    request: Request,
    current_user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    _verify_admin(request)

    # Find all approved ProcessedDocuments without an indexed KB doc
    result = await db.execute(
        select(KnowledgeBaseDocument).where(
            KnowledgeBaseDocument.index_status.in_([
                KBIndexStatus.FAILED.value,
                KBIndexStatus.REMOVED.value,
            ])
        )
    )
    kb_docs = result.scalars().all()

    requeued_ids: list[str] = []
    for kb_doc in kb_docs:
        kb_doc.index_status = KBIndexStatus.QUEUED.value
        kb_doc.failure_reason = None
        requeued_ids.append(str(kb_doc.id))

    await db.commit()

    return {
        "data": {
            "requeued_count": len(requeued_ids),
            "requeued_ids": requeued_ids,
        },
        "request_id": _request_id(request),
    }
