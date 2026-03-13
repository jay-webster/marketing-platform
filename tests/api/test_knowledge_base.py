"""API tests for src/api/knowledge_base.py — admin KB endpoints."""
import uuid
from unittest.mock import AsyncMock, patch

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from src.config import settings
from src.models.knowledge_base_document import KBIndexStatus, KnowledgeBaseDocument
from src.models.ingestion_document import ProcessingStatus, IngestionDocument
from src.models.ingestion_batch import IngestionBatch
from src.models.processed_document import ProcessedDocument, ReviewStatus

_async = pytest.mark.asyncio(loop_scope="function")

VALID_ADMIN_TOKEN = "test-admin-token"


def _patch_workers():
    return patch.multiple(
        "utils.queue",
        startup_recovery=AsyncMock(),
        start_queue_workers=AsyncMock(),
        stop_queue_workers=AsyncMock(),
        start_indexing_workers=AsyncMock(),
        stop_indexing_workers=AsyncMock(),
    )


def _admin_headers(bearer: str) -> dict:
    return {
        "Authorization": f"Bearer {bearer}",
        "X-Admin-Token": VALID_ADMIN_TOKEN,
    }


async def _create_kb_doc(db: AsyncSession, status: str = KBIndexStatus.INDEXED.value) -> KnowledgeBaseDocument:
    """Create a minimal KnowledgeBaseDocument with a ProcessedDocument parent."""
    batch = IngestionBatch(
        submitted_by=uuid.uuid4(),
        source_folder_name="Test",
        total_documents=1,
    )
    db.add(batch)
    await db.flush()

    ing_doc = IngestionDocument(
        batch_id=batch.id,
        original_filename="test.pdf",
        original_file_type=".pdf",
        relative_path="test.pdf",
        file_size_bytes=100,
        gcs_object_path="test/path",
        processing_status=ProcessingStatus.COMPLETED.value,
    )
    db.add(ing_doc)
    await db.flush()

    pd = ProcessedDocument(
        ingestion_document_id=ing_doc.id,
        markdown_content="# Test",
        review_status=ReviewStatus.APPROVED.value,
    )
    db.add(pd)
    await db.flush()

    kb_doc = KnowledgeBaseDocument(
        processed_document_id=pd.id,
        index_status=status,
    )
    db.add(kb_doc)
    await db.commit()
    await db.refresh(kb_doc)
    return kb_doc


# ---------------------------------------------------------------------------
# GET /admin/knowledge-base/status
# ---------------------------------------------------------------------------

@_async
async def test_kb_status_unauthenticated(async_client: AsyncClient):
    """No bearer token → 401 (fails before admin token check)."""
    with _patch_workers():
        response = await async_client.get("/api/v1/admin/knowledge-base/status")
    assert response.status_code == 401


@_async
async def test_kb_status_requires_admin_token(async_client: AsyncClient, admin_token: str):
    """Valid bearer but no X-Admin-Token → 403."""
    with _patch_workers(), patch.object(settings, "ADMIN_TOKEN", VALID_ADMIN_TOKEN):
        response = await async_client.get(
            "/api/v1/admin/knowledge-base/status",
            headers={"Authorization": f"Bearer {admin_token}"},
        )
    assert response.status_code == 403


@_async
async def test_kb_status_wrong_admin_token(async_client: AsyncClient, admin_token: str):
    with _patch_workers(), patch.object(settings, "ADMIN_TOKEN", VALID_ADMIN_TOKEN):
        response = await async_client.get(
            "/api/v1/admin/knowledge-base/status",
            headers={
                "Authorization": f"Bearer {admin_token}",
                "X-Admin-Token": "wrong-token",
            },
        )
    assert response.status_code == 403


@_async
async def test_kb_status_empty(async_client: AsyncClient, admin_token: str):
    with _patch_workers(), patch.object(settings, "ADMIN_TOKEN", VALID_ADMIN_TOKEN):
        response = await async_client.get(
            "/api/v1/admin/knowledge-base/status",
            headers=_admin_headers(admin_token),
        )
    assert response.status_code == 200
    data = response.json()["data"]
    assert data["total"] == 0


@_async
async def test_kb_status_counts(async_client: AsyncClient, admin_token: str, db_session: AsyncSession):
    await _create_kb_doc(db_session, KBIndexStatus.INDEXED.value)
    await _create_kb_doc(db_session, KBIndexStatus.FAILED.value)

    with _patch_workers(), patch.object(settings, "ADMIN_TOKEN", VALID_ADMIN_TOKEN):
        response = await async_client.get(
            "/api/v1/admin/knowledge-base/status",
            headers=_admin_headers(admin_token),
        )
    assert response.status_code == 200
    data = response.json()["data"]
    assert data["total"] == 2
    assert data["by_status"]["indexed"] == 1
    assert data["by_status"]["failed"] == 1


# ---------------------------------------------------------------------------
# POST /admin/knowledge-base/reindex
# ---------------------------------------------------------------------------

@_async
async def test_reindex_unauthenticated(async_client: AsyncClient):
    """No bearer token → 401."""
    with _patch_workers():
        response = await async_client.post("/api/v1/admin/knowledge-base/reindex")
    assert response.status_code == 401


@_async
async def test_reindex_requires_admin_token(async_client: AsyncClient, admin_token: str):
    """Valid bearer but no X-Admin-Token → 403."""
    with _patch_workers(), patch.object(settings, "ADMIN_TOKEN", VALID_ADMIN_TOKEN):
        response = await async_client.post(
            "/api/v1/admin/knowledge-base/reindex",
            headers={"Authorization": f"Bearer {admin_token}"},
        )
    assert response.status_code == 403


@_async
async def test_reindex_failed_docs(async_client: AsyncClient, admin_token: str, db_session: AsyncSession):
    kb_doc = await _create_kb_doc(db_session, KBIndexStatus.FAILED.value)

    with _patch_workers(), patch.object(settings, "ADMIN_TOKEN", VALID_ADMIN_TOKEN):
        response = await async_client.post(
            "/api/v1/admin/knowledge-base/reindex",
            headers=_admin_headers(admin_token),
        )
    assert response.status_code == 200
    data = response.json()["data"]
    assert data["requeued_count"] == 1
    assert str(kb_doc.id) in data["requeued_ids"]

    await db_session.refresh(kb_doc)
    assert kb_doc.index_status == KBIndexStatus.QUEUED.value


@_async
async def test_reindex_removes_failure_reason(async_client: AsyncClient, admin_token: str, db_session: AsyncSession):
    kb_doc = await _create_kb_doc(db_session, KBIndexStatus.FAILED.value)
    kb_doc.failure_reason = "OpenAI timeout"
    await db_session.commit()

    with _patch_workers(), patch.object(settings, "ADMIN_TOKEN", VALID_ADMIN_TOKEN):
        await async_client.post(
            "/api/v1/admin/knowledge-base/reindex",
            headers=_admin_headers(admin_token),
        )

    await db_session.refresh(kb_doc)
    assert kb_doc.failure_reason is None


@_async
async def test_reindex_skips_indexed_docs(async_client: AsyncClient, admin_token: str, db_session: AsyncSession):
    await _create_kb_doc(db_session, KBIndexStatus.INDEXED.value)

    with _patch_workers(), patch.object(settings, "ADMIN_TOKEN", VALID_ADMIN_TOKEN):
        response = await async_client.post(
            "/api/v1/admin/knowledge-base/reindex",
            headers=_admin_headers(admin_token),
        )
    assert response.json()["data"]["requeued_count"] == 0


@_async
async def test_reindex_requeues_removed_docs(async_client: AsyncClient, admin_token: str, db_session: AsyncSession):
    await _create_kb_doc(db_session, KBIndexStatus.REMOVED.value)

    with _patch_workers(), patch.object(settings, "ADMIN_TOKEN", VALID_ADMIN_TOKEN):
        response = await async_client.post(
            "/api/v1/admin/knowledge-base/reindex",
            headers=_admin_headers(admin_token),
        )
    assert response.json()["data"]["requeued_count"] == 1
