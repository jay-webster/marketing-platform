"""Admin Knowledge Base management endpoints."""
from fastapi import APIRouter, Depends, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.models.knowledge_base_document import KBIndexStatus, KnowledgeBaseDocument
from src.models.user import Role
from utils.auth import require_role
from utils.db import get_db

router = APIRouter(prefix="/admin/knowledge-base", tags=["knowledge-base"])


def _request_id(request: Request) -> str:
    return getattr(request.state, "request_id", "unknown")


# -----------------------------------------------------------------
# GET /admin/knowledge-base/status — KB indexing summary
# -----------------------------------------------------------------

@router.get("/status")
async def kb_status(
    request: Request,
    current_user=require_role(Role.ADMIN),
    db: AsyncSession = Depends(get_db),
):

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
    current_user=require_role(Role.ADMIN),
    db: AsyncSession = Depends(get_db),
):

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
