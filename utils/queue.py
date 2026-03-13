"""PostgreSQL-backed async queue workers for ingestion and KB indexing.

Uses SELECT FOR UPDATE SKIP LOCKED to claim work — no external broker needed.
Workers are asyncio tasks — fully non-blocking.
"""
import asyncio
import logging
import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import select, update

from utils.db import AsyncSessionLocal

logger = logging.getLogger(__name__)

POLL_INTERVAL_SECONDS = 1
PROCESSING_TIMEOUT_MINUTES = 5
WATCHDOG_INTERVAL_SECONDS = 60

# Module-level task handles — ingestion workers
_worker_tasks: list[asyncio.Task] = []
_watchdog_task: asyncio.Task | None = None
_anthropic_client = None

# Module-level task handles — KB indexing workers
_indexing_worker_tasks: list[asyncio.Task] = []


def _get_anthropic_client():
    global _anthropic_client
    if _anthropic_client is None:
        from anthropic import AsyncAnthropic  # noqa: PLC0415
        _anthropic_client = AsyncAnthropic()
    return _anthropic_client


async def _claim_next_document(db):
    """Atomically claim one queued document. Returns the document or None."""
    from src.models.ingestion_document import IngestionDocument, ProcessingStatus  # noqa: PLC0415

    stmt = (
        select(IngestionDocument)
        .where(IngestionDocument.processing_status == ProcessingStatus.QUEUED.value)
        .order_by(IngestionDocument.queued_at)
        .limit(1)
        .with_for_update(skip_locked=True)
    )
    result = await db.execute(stmt)
    doc = result.scalar_one_or_none()

    if doc is None:
        return None

    doc.processing_status = "processing"
    doc.processing_started_at = datetime.now(timezone.utc)
    await db.commit()
    await db.refresh(doc)
    return doc


async def process_document(doc_id: uuid.UUID) -> None:
    """Process a single document end-to-end in its own DB session."""
    from src.models.ingestion_document import IngestionDocument  # noqa: PLC0415
    from src.models.ingestion_batch import IngestionBatch, BatchStatus  # noqa: PLC0415
    from src.models.processed_document import ProcessedDocument  # noqa: PLC0415
    from src.config import settings  # noqa: PLC0415
    from utils.gcs import download_stream_from_gcs, delete_from_gcs  # noqa: PLC0415
    from utils.extractors import extract_text_async  # noqa: PLC0415
    from utils.ingestion_pipeline import structure_document_with_retry  # noqa: PLC0415
    from utils.audit import write_audit  # noqa: PLC0415

    async with AsyncSessionLocal() as db:
        doc = await db.get(IngestionDocument, doc_id)
        if doc is None:
            logger.error("process_document: doc %s not found", doc_id)
            return

        try:
            # Download source file from GCS
            stream = await download_stream_from_gcs(settings.GCS_BUCKET_NAME, doc.gcs_object_path)

            # Extract text
            raw_text = await extract_text_async(stream, doc.original_file_type)

            # Structure via Claude
            client = _get_anthropic_client()
            markdown = await structure_document_with_retry(
                client=client,
                extracted_text=raw_text,
                source_file=doc.original_filename,
                source_type=doc.original_file_type,
                ingested_by="system",  # placeholder; enriched by API layer on reprocess
                reprocessing_note=doc.reprocessing_note,
            )

            # Extract metadata from frontmatter for DB columns
            extracted_title = _parse_frontmatter_field(markdown, "title")
            extracted_author = _parse_frontmatter_field(markdown, "author")
            extracted_date = _parse_frontmatter_field(markdown, "source_date")

            # Upsert ProcessedDocument (delete-then-insert for re-processing)
            existing = await db.execute(
                select(ProcessedDocument).where(
                    ProcessedDocument.ingestion_document_id == doc_id
                )
            )
            existing_row = existing.scalar_one_or_none()
            if existing_row:
                await db.delete(existing_row)
                await db.flush()

            processed = ProcessedDocument(
                ingestion_document_id=doc_id,
                markdown_content=markdown,
                extracted_title=extracted_title,
                extracted_author=extracted_author,
                extracted_date=extracted_date,
            )
            db.add(processed)

            # Update document status
            now = datetime.now(timezone.utc)
            doc.processing_status = "completed"
            doc.processing_completed_at = now
            doc.failure_reason = None

            # Update batch counters and status
            batch = await db.get(IngestionBatch, doc.batch_id)
            if batch:
                batch.completed_count += 1
                _recompute_batch_status(batch)

            await write_audit(db, "ingestion_document_completed", target_id=doc_id,
                              metadata={"batch_id": str(doc.batch_id), "filename": doc.original_filename})

            await db.commit()

            # Delete source file from GCS after successful processing
            try:
                await delete_from_gcs(settings.GCS_BUCKET_NAME, doc.gcs_object_path)
            except Exception:
                logger.warning("GCS cleanup failed for %s (non-fatal)", doc.gcs_object_path)

        except Exception as exc:
            failure_reason = _map_exception_to_reason(exc)
            logger.exception("process_document failed for %s: %s", doc_id, failure_reason)

            try:
                now = datetime.now(timezone.utc)
                doc.processing_status = "failed"
                doc.processing_completed_at = now
                doc.failure_reason = failure_reason

                batch = await db.get(IngestionBatch, doc.batch_id)
                if batch:
                    batch.failed_count += 1
                    _recompute_batch_status(batch)

                await write_audit(db, "ingestion_document_failed", target_id=doc_id,
                                  metadata={"batch_id": str(doc.batch_id), "filename": doc.original_filename, "reason": failure_reason})
                await db.commit()
            except Exception:
                logger.exception("Failed to mark document %s as failed", doc_id)


def _map_exception_to_reason(exc: Exception) -> str:
    from utils.extractors import REASON_EMPTY, REASON_CORRUPT, REASON_NO_TEXT, REASON_OVERSIZED  # noqa: PLC0415
    msg = str(exc)
    if msg in (REASON_EMPTY, REASON_CORRUPT, REASON_NO_TEXT, REASON_OVERSIZED):
        return msg
    if "timed out" in msg.lower():
        return "Processing timed out — the file may be too large or complex."
    return f"Processing failed: {msg}"


def _parse_frontmatter_field(markdown: str, field: str) -> str | None:
    """Extract a field value from YAML frontmatter block."""
    try:
        if not markdown.startswith("---"):
            return None
        end = markdown.find("\n---", 3)
        if end == -1:
            return None
        import yaml  # noqa: PLC0415
        front = yaml.safe_load(markdown[3:end])
        return front.get(field) if isinstance(front, dict) else None
    except Exception:
        return None


def _recompute_batch_status(batch) -> None:
    from src.models.ingestion_batch import BatchStatus  # noqa: PLC0415
    terminal = batch.completed_count + batch.failed_count
    if terminal >= batch.total_documents:
        if batch.failed_count == 0:
            batch.status = BatchStatus.COMPLETED.value
        else:
            batch.status = BatchStatus.COMPLETED_WITH_FAILURES.value
    else:
        batch.status = "in_progress"


async def _worker(worker_id: int) -> None:
    """Single worker coroutine. Polls for queued documents and processes them."""
    logger.info("Queue worker %d started", worker_id)
    while True:
        try:
            async with AsyncSessionLocal() as db:
                doc = await _claim_next_document(db)

            if doc is None:
                await asyncio.sleep(POLL_INTERVAL_SECONDS)
                continue

            await process_document(doc.id)

        except asyncio.CancelledError:
            logger.info("Queue worker %d shutting down", worker_id)
            return
        except Exception:
            logger.exception("Queue worker %d unhandled error — continuing", worker_id)
            await asyncio.sleep(POLL_INTERVAL_SECONDS)


async def _timeout_watchdog() -> None:
    """Marks documents stuck in 'processing' for > PROCESSING_TIMEOUT_MINUTES as failed."""
    from src.models.ingestion_document import IngestionDocument  # noqa: PLC0415

    while True:
        try:
            cutoff = datetime.now(timezone.utc) - timedelta(minutes=PROCESSING_TIMEOUT_MINUTES)
            async with AsyncSessionLocal() as db:
                await db.execute(
                    update(IngestionDocument)
                    .where(
                        IngestionDocument.processing_status == "processing",
                        IngestionDocument.processing_started_at < cutoff,
                    )
                    .values(
                        processing_status="failed",
                        failure_reason="Processing timed out.",
                        processing_completed_at=datetime.now(timezone.utc),
                    )
                )
                await db.commit()
        except asyncio.CancelledError:
            return
        except Exception:
            logger.exception("Timeout watchdog error")

        await asyncio.sleep(WATCHDOG_INTERVAL_SECONDS)


async def startup_recovery() -> None:
    """Reset any documents left in 'processing' from a prior crash back to 'queued'."""
    from src.models.ingestion_document import IngestionDocument  # noqa: PLC0415

    async with AsyncSessionLocal() as db:
        result = await db.execute(
            update(IngestionDocument)
            .where(IngestionDocument.processing_status == "processing")
            .values(processing_status="queued", processing_started_at=None)
            .returning(IngestionDocument.id)
        )
        recovered = result.fetchall()
        await db.commit()
        if recovered:
            logger.info("Startup recovery: reset %d stuck processing documents to queued", len(recovered))


async def start_queue_workers(concurrency: int = 5) -> None:
    """Start worker pool and watchdog. Call from app lifespan."""
    global _worker_tasks, _watchdog_task
    for i in range(concurrency):
        _worker_tasks.append(asyncio.create_task(_worker(i)))
    _watchdog_task = asyncio.create_task(_timeout_watchdog())
    logger.info("Started %d queue workers + timeout watchdog", concurrency)


async def stop_queue_workers() -> None:
    """Gracefully stop all ingestion worker tasks."""
    for task in _worker_tasks:
        task.cancel()
    if _watchdog_task:
        _watchdog_task.cancel()
    all_tasks = _worker_tasks + ([_watchdog_task] if _watchdog_task else [])
    await asyncio.gather(*all_tasks, return_exceptions=True)
    _worker_tasks.clear()
    logger.info("Queue workers stopped")


# ---------------------------------------------------------------------------
# KB Indexing workers
# ---------------------------------------------------------------------------

async def _claim_next_kb_document(db):
    """Atomically claim one queued KB document for indexing."""
    from src.models.knowledge_base_document import KnowledgeBaseDocument, KBIndexStatus  # noqa: PLC0415

    stmt = (
        select(KnowledgeBaseDocument)
        .where(KnowledgeBaseDocument.index_status == KBIndexStatus.QUEUED.value)
        .order_by(KnowledgeBaseDocument.created_at)
        .limit(1)
        .with_for_update(skip_locked=True)
    )
    result = await db.execute(stmt)
    kb_doc = result.scalar_one_or_none()

    if kb_doc is None:
        return None

    kb_doc.index_status = KBIndexStatus.INDEXING.value
    kb_doc.updated_at = datetime.now(timezone.utc)
    await db.commit()
    await db.refresh(kb_doc)
    return kb_doc


async def _indexing_worker(worker_id: int) -> None:
    """Single KB indexing worker. Polls for queued KB documents and indexes them."""
    from utils.indexer import index_document  # noqa: PLC0415

    logger.info("KB indexing worker %d started", worker_id)
    while True:
        try:
            async with AsyncSessionLocal() as db:
                kb_doc = await _claim_next_kb_document(db)

            if kb_doc is None:
                await asyncio.sleep(POLL_INTERVAL_SECONDS)
                continue

            async with AsyncSessionLocal() as db:
                await index_document(db, kb_doc.id)
                logger.info("KB indexing worker %d: indexed kb_doc %s", worker_id, kb_doc.id)

        except asyncio.CancelledError:
            logger.info("KB indexing worker %d shutting down", worker_id)
            return
        except Exception:
            logger.exception("KB indexing worker %d unhandled error — continuing", worker_id)
            await asyncio.sleep(POLL_INTERVAL_SECONDS)


async def start_indexing_workers(concurrency: int = 2) -> None:
    """Start KB indexing worker pool. Call from app lifespan."""
    global _indexing_worker_tasks
    for i in range(concurrency):
        _indexing_worker_tasks.append(asyncio.create_task(_indexing_worker(i)))
    logger.info("Started %d KB indexing workers", concurrency)


async def stop_indexing_workers() -> None:
    """Gracefully stop all KB indexing worker tasks."""
    for task in _indexing_worker_tasks:
        task.cancel()
    await asyncio.gather(*_indexing_worker_tasks, return_exceptions=True)
    _indexing_worker_tasks.clear()
    logger.info("KB indexing workers stopped")
