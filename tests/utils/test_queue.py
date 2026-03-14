"""Unit tests for utils/queue.py — worker pool and watchdog logic."""
import uuid
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

_async = pytest.mark.asyncio(loop_scope="function")


# ---------------------------------------------------------------------------
# startup_recovery
# ---------------------------------------------------------------------------

@_async
async def test_startup_recovery_resets_stuck_processing_docs():
    """startup_recovery() should reset 'processing' → 'queued' in the DB."""
    mock_result = MagicMock()
    mock_result.fetchall.return_value = [(uuid.uuid4(),), (uuid.uuid4(),)]

    mock_db = AsyncMock()
    mock_db.execute = AsyncMock(return_value=mock_result)
    mock_db.commit = AsyncMock()
    mock_db.__aenter__ = AsyncMock(return_value=mock_db)
    mock_db.__aexit__ = AsyncMock(return_value=False)

    with patch("utils.queue.AsyncSessionLocal", return_value=mock_db):
        from utils.queue import startup_recovery
        await startup_recovery()

    mock_db.execute.assert_called_once()
    mock_db.commit.assert_called_once()


@_async
async def test_startup_recovery_no_stuck_docs():
    """startup_recovery() with no stuck docs — commit still called."""
    mock_result = MagicMock()
    mock_result.fetchall.return_value = []

    mock_db = AsyncMock()
    mock_db.execute = AsyncMock(return_value=mock_result)
    mock_db.commit = AsyncMock()
    mock_db.__aenter__ = AsyncMock(return_value=mock_db)
    mock_db.__aexit__ = AsyncMock(return_value=False)

    with patch("utils.queue.AsyncSessionLocal", return_value=mock_db):
        from utils.queue import startup_recovery
        await startup_recovery()

    mock_db.commit.assert_called_once()


# ---------------------------------------------------------------------------
# _recompute_batch_status
# ---------------------------------------------------------------------------

def test_recompute_batch_status_all_completed():
    from utils.queue import _recompute_batch_status
    from src.models.ingestion_batch import BatchStatus

    batch = MagicMock()
    batch.total_documents = 3
    batch.completed_count = 3
    batch.failed_count = 0
    _recompute_batch_status(batch)
    assert batch.status == BatchStatus.COMPLETED.value


def test_recompute_batch_status_some_failed():
    from utils.queue import _recompute_batch_status
    from src.models.ingestion_batch import BatchStatus

    batch = MagicMock()
    batch.total_documents = 3
    batch.completed_count = 2
    batch.failed_count = 1
    _recompute_batch_status(batch)
    assert batch.status == BatchStatus.COMPLETED_WITH_FAILURES.value


def test_recompute_batch_status_in_progress():
    from utils.queue import _recompute_batch_status

    batch = MagicMock()
    batch.total_documents = 5
    batch.completed_count = 2
    batch.failed_count = 1
    _recompute_batch_status(batch)
    assert batch.status == "in_progress"


# ---------------------------------------------------------------------------
# _map_exception_to_reason
# ---------------------------------------------------------------------------

def test_map_exception_timeout():
    from utils.queue import _map_exception_to_reason
    exc = Exception("Connection timed out after 300s")
    reason = _map_exception_to_reason(exc)
    assert "timed out" in reason.lower()


def test_map_exception_known_reason():
    from utils.queue import _map_exception_to_reason
    from utils.extractors import REASON_EMPTY
    exc = Exception(REASON_EMPTY)
    assert _map_exception_to_reason(exc) == REASON_EMPTY


def test_map_exception_generic():
    from utils.queue import _map_exception_to_reason
    exc = Exception("some random failure")
    reason = _map_exception_to_reason(exc)
    assert "Processing failed:" in reason
    assert "some random failure" in reason


# ---------------------------------------------------------------------------
# _parse_frontmatter_field (tested here as well as in test_pipeline.py)
# ---------------------------------------------------------------------------

def test_parse_frontmatter_field_title():
    from utils.queue import _parse_frontmatter_field
    md = "---\ntitle: My Report\n---\n\n# Content"
    assert _parse_frontmatter_field(md, "title") == "My Report"


def test_parse_frontmatter_field_no_frontmatter():
    from utils.queue import _parse_frontmatter_field
    md = "# No frontmatter"
    assert _parse_frontmatter_field(md, "title") is None


# ---------------------------------------------------------------------------
# start/stop_queue_workers
# ---------------------------------------------------------------------------

@_async
async def test_start_and_stop_queue_workers():
    """Start workers and verify they can be cancelled cleanly."""
    import asyncio
    from utils.queue import start_queue_workers, stop_queue_workers

    # Override _worker to avoid real DB connections
    async def _fake_worker(worker_id: int):
        await asyncio.sleep(9999)

    with patch("utils.queue._worker", side_effect=_fake_worker):
        await start_queue_workers(concurrency=2)
        # Brief yield to let tasks start
        await asyncio.sleep(0)
        await stop_queue_workers()

    # After stopping, the module-level list should be empty
    from utils import queue as queue_module
    assert queue_module._worker_tasks == []


# ---------------------------------------------------------------------------
# process_document — mocked end-to-end
# ---------------------------------------------------------------------------

@_async
async def test_process_document_marks_completed_on_success():
    """process_document() should set status='completed' and create ProcessedDocument."""
    import uuid as _uuid
    doc_id = _uuid.uuid4()
    batch_id = _uuid.uuid4()
    now = datetime.now(timezone.utc)

    # Build mock doc
    mock_doc = MagicMock()
    mock_doc.id = doc_id
    mock_doc.batch_id = batch_id
    mock_doc.gcs_object_path = "batches/x/y/file.pdf"
    mock_doc.original_file_type = ".pdf"
    mock_doc.original_filename = "file.pdf"
    mock_doc.reprocessing_note = None
    mock_doc.processing_status = "processing"
    mock_doc.destination_folder = None  # no PR workflow; test the standard completion path

    # Build mock batch
    mock_batch = MagicMock()
    mock_batch.completed_count = 0
    mock_batch.failed_count = 0
    mock_batch.total_documents = 1

    mock_db = AsyncMock()
    mock_db.get = AsyncMock(side_effect=lambda model, pk: mock_doc if pk == doc_id else mock_batch)
    mock_db.execute = AsyncMock(return_value=MagicMock(scalar_one_or_none=MagicMock(return_value=None)))
    mock_db.add = MagicMock()
    mock_db.flush = AsyncMock()
    mock_db.commit = AsyncMock()
    mock_db.__aenter__ = AsyncMock(return_value=mock_db)
    mock_db.__aexit__ = AsyncMock(return_value=False)

    markdown_output = "---\ntitle: Test\n---\n\n# Test"

    with (
        patch("utils.queue.AsyncSessionLocal", return_value=mock_db),
        patch("utils.gcs.download_stream_from_gcs", new_callable=AsyncMock, return_value=b"stream"),
        patch("utils.extractors.extract_text_async", new_callable=AsyncMock, return_value="raw text"),
        patch("utils.ingestion_pipeline.structure_document_with_retry", new_callable=AsyncMock, return_value=markdown_output),
        patch("utils.gcs.delete_from_gcs", new_callable=AsyncMock),
        patch("utils.audit.write_audit", new_callable=AsyncMock),
        patch("utils.queue._get_anthropic_client", return_value=MagicMock()),
        patch("src.config.settings", GCS_BUCKET_NAME="test-bucket"),
    ):
        from utils.queue import process_document
        await process_document(doc_id)

    assert mock_doc.processing_status == "completed"
    assert mock_doc.failure_reason is None
    mock_db.commit.assert_called()


@_async
async def test_process_document_marks_failed_on_error():
    """process_document() should set status='failed' when an exception occurs."""
    import uuid as _uuid
    doc_id = _uuid.uuid4()
    batch_id = _uuid.uuid4()

    mock_doc = MagicMock()
    mock_doc.id = doc_id
    mock_doc.batch_id = batch_id
    mock_doc.gcs_object_path = "batches/x/y/file.pdf"
    mock_doc.original_file_type = ".pdf"
    mock_doc.original_filename = "file.pdf"
    mock_doc.reprocessing_note = None

    mock_batch = MagicMock()
    mock_batch.failed_count = 0
    mock_batch.completed_count = 0
    mock_batch.total_documents = 1

    mock_db = AsyncMock()
    mock_db.get = AsyncMock(side_effect=lambda model, pk: mock_doc if pk == doc_id else mock_batch)
    mock_db.commit = AsyncMock()
    mock_db.__aenter__ = AsyncMock(return_value=mock_db)
    mock_db.__aexit__ = AsyncMock(return_value=False)

    with (
        patch("utils.queue.AsyncSessionLocal", return_value=mock_db),
        patch("utils.gcs.download_stream_from_gcs", new_callable=AsyncMock, side_effect=RuntimeError("GCS error")),
        patch("utils.audit.write_audit", new_callable=AsyncMock),
        patch("src.config.settings", GCS_BUCKET_NAME="test-bucket"),
    ):
        from utils.queue import process_document
        await process_document(doc_id)

    assert mock_doc.processing_status == "failed"
    assert mock_doc.failure_reason is not None
