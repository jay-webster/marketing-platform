"""KB indexing pipeline — chunk, embed, and upsert to content_chunks."""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import delete, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from src.models.content_chunk import ContentChunk
from src.models.knowledge_base_document import KBIndexStatus, KnowledgeBaseDocument
from src.models.processed_document import ProcessedDocument
from src.models.synced_document import SyncedDocument
from utils.chunker import chunk_markdown
from utils.embeddings import embed_batch


async def index_document(db: AsyncSession, kb_doc_id: uuid.UUID) -> None:
    """Chunk, embed, and store all content_chunks for a KnowledgeBaseDocument.

    Supports two content sources:
      - processed_document_id set → upload pipeline (ProcessedDocument.structured_content)
      - synced_document_id set    → GitHub sync pipeline (SyncedDocument.raw_content)

    Marks the KB doc as INDEXING before starting, then INDEXED on success,
    or FAILED with a failure_reason on error.  Existing chunks are deleted
    before inserting new ones so re-indexing is safe to run multiple times.

    Args:
        db: Async database session (caller manages commit/rollback).
        kb_doc_id: PK of the KnowledgeBaseDocument row to process.
    """
    # Mark as indexing
    await db.execute(
        update(KnowledgeBaseDocument)
        .where(KnowledgeBaseDocument.id == kb_doc_id)
        .values(
            index_status=KBIndexStatus.INDEXING.value,
            updated_at=datetime.now(timezone.utc),
        )
    )
    await db.commit()

    try:
        # Load KB doc to determine source type
        kb_doc_result = await db.execute(
            select(KnowledgeBaseDocument).where(KnowledgeBaseDocument.id == kb_doc_id)
        )
        kb_doc = kb_doc_result.scalar_one_or_none()
        if kb_doc is None:
            raise ValueError(f"KnowledgeBaseDocument {kb_doc_id} not found")

        # Dispatch on source type
        if kb_doc.synced_document_id is not None:
            # GitHub sync pipeline
            synced_result = await db.execute(
                select(SyncedDocument).where(SyncedDocument.id == kb_doc.synced_document_id)
            )
            synced_doc = synced_result.scalar_one_or_none()
            if synced_doc is None:
                raise ValueError(
                    f"SyncedDocument {kb_doc.synced_document_id} not found for KB doc {kb_doc_id}"
                )
            markdown = synced_doc.raw_content or ""
            metadata: dict = {
                "source": "github_sync",
                "repo_path": synced_doc.repo_path,
                "folder": synced_doc.folder,
                "title": synced_doc.title or "",
            }
        else:
            # Upload pipeline (original path)
            result = await db.execute(
                select(KnowledgeBaseDocument, ProcessedDocument)
                .join(ProcessedDocument, ProcessedDocument.id == KnowledgeBaseDocument.processed_document_id)
                .where(KnowledgeBaseDocument.id == kb_doc_id)
            )
            row = result.one_or_none()
            if row is None:
                raise ValueError(f"KnowledgeBaseDocument {kb_doc_id} not found")

            kb_doc, proc_doc = row

            markdown = proc_doc.structured_content or ""
            metadata = proc_doc.metadata or {}

        # Remove existing chunks (safe re-index)
        await db.execute(
            delete(ContentChunk).where(ContentChunk.knowledge_base_document_id == kb_doc_id)
        )

        # Chunk the document
        chunk_texts = chunk_markdown(markdown, metadata=metadata)

        if not chunk_texts:
            # No content — mark indexed with 0 chunks
            await db.execute(
                update(KnowledgeBaseDocument)
                .where(KnowledgeBaseDocument.id == kb_doc_id)
                .values(
                    index_status=KBIndexStatus.INDEXED.value,
                    chunk_count=0,
                    indexed_at=datetime.now(timezone.utc),
                    updated_at=datetime.now(timezone.utc),
                )
            )
            await db.commit()
            return

        # Embed all chunks in batches of 100
        _BATCH_SIZE = 100
        all_embeddings: list[list[float]] = []
        for i in range(0, len(chunk_texts), _BATCH_SIZE):
            batch = chunk_texts[i : i + _BATCH_SIZE]
            embeddings = await embed_batch(batch)
            all_embeddings.extend(embeddings)

        # Insert ContentChunk rows
        for idx, (text, embedding) in enumerate(zip(chunk_texts, all_embeddings)):
            chunk = ContentChunk(
                knowledge_base_document_id=kb_doc_id,
                chunk_index=idx,
                content_text=text,
                embedding=embedding,
                doc_metadata=metadata,
            )
            db.add(chunk)

        # Mark indexed
        await db.execute(
            update(KnowledgeBaseDocument)
            .where(KnowledgeBaseDocument.id == kb_doc_id)
            .values(
                index_status=KBIndexStatus.INDEXED.value,
                chunk_count=len(chunk_texts),
                indexed_at=datetime.now(timezone.utc),
                updated_at=datetime.now(timezone.utc),
                failure_reason=None,
            )
        )
        await db.commit()

    except Exception as exc:
        await db.rollback()
        await db.execute(
            update(KnowledgeBaseDocument)
            .where(KnowledgeBaseDocument.id == kb_doc_id)
            .values(
                index_status=KBIndexStatus.FAILED.value,
                failure_reason=str(exc)[:1000],
                updated_at=datetime.now(timezone.utc),
            )
        )
        await db.commit()
        raise


async def remove_document(db: AsyncSession, kb_doc_id: uuid.UUID) -> None:
    """Delete all chunks and mark a KnowledgeBaseDocument as REMOVED.

    Args:
        db: Async database session.
        kb_doc_id: PK of the KnowledgeBaseDocument row.
    """
    await db.execute(
        delete(ContentChunk).where(ContentChunk.knowledge_base_document_id == kb_doc_id)
    )
    await db.execute(
        update(KnowledgeBaseDocument)
        .where(KnowledgeBaseDocument.id == kb_doc_id)
        .values(
            index_status=KBIndexStatus.REMOVED.value,
            removed_at=datetime.now(timezone.utc),
            chunk_count=0,
            updated_at=datetime.now(timezone.utc),
        )
    )
    await db.commit()
