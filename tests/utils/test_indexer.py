"""Tests for utils/indexer.py"""
import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.models.knowledge_base_document import KBIndexStatus


@pytest.fixture
def kb_doc_id():
    return uuid.uuid4()


@pytest.fixture
def proc_doc_id():
    return uuid.uuid4()


def _make_mock_db():
    db = AsyncMock()
    db.execute = AsyncMock()
    db.commit = AsyncMock()
    db.rollback = AsyncMock()
    db.add = MagicMock()
    return db


def _make_kb_doc(kb_doc_id, proc_doc_id):
    kb_doc = MagicMock()
    kb_doc.id = kb_doc_id
    kb_doc.processed_document_id = proc_doc_id
    kb_doc.index_status = KBIndexStatus.QUEUED.value
    kb_doc.synced_document_id = None  # upload path; prevents GitHub sync branch
    return kb_doc


def _make_proc_doc(content="## Section\n\nSome content.", meta=None):
    pd = MagicMock()
    pd.structured_content = content
    pd.metadata = meta or {"title": "Test Doc"}
    return pd


@pytest.mark.asyncio
async def test_index_document_happy_path(kb_doc_id, proc_doc_id):
    kb_doc = _make_kb_doc(kb_doc_id, proc_doc_id)
    proc_doc = _make_proc_doc()
    db = _make_mock_db()

    # Mock the DB query returning (kb_doc, proc_doc)
    result_mock = MagicMock()
    result_mock.scalar_one_or_none = MagicMock(return_value=kb_doc)
    result_mock.one_or_none = MagicMock(return_value=(kb_doc, proc_doc))

    db.execute.return_value = result_mock

    fake_embedding = [0.1] * 1536

    with patch("utils.indexer.embed_batch", new=AsyncMock(return_value=[fake_embedding])):
        from utils.indexer import index_document
        await index_document(db, kb_doc_id)

    # Should have committed twice: once to mark indexing, once to mark indexed
    assert db.commit.call_count >= 2


@pytest.mark.asyncio
async def test_index_document_not_found(kb_doc_id):
    db = _make_mock_db()
    result_mock = MagicMock()
    result_mock.one_or_none = MagicMock(return_value=None)
    db.execute.return_value = result_mock

    from utils.indexer import index_document

    with pytest.raises(Exception):
        await index_document(db, kb_doc_id)

    # Should have rolled back and committed failure status
    assert db.rollback.called


@pytest.mark.asyncio
async def test_index_document_empty_content(kb_doc_id, proc_doc_id):
    kb_doc = _make_kb_doc(kb_doc_id, proc_doc_id)
    proc_doc = _make_proc_doc(content="")
    db = _make_mock_db()

    result_mock = MagicMock()
    result_mock.scalar_one_or_none = MagicMock(return_value=kb_doc)
    result_mock.one_or_none = MagicMock(return_value=(kb_doc, proc_doc))
    db.execute.return_value = result_mock

    with patch("utils.indexer.embed_batch", new=AsyncMock(return_value=[])):
        from utils.indexer import index_document
        await index_document(db, kb_doc_id)

    # Committed twice (once for indexing, once for empty indexed)
    assert db.commit.call_count >= 2


@pytest.mark.asyncio
async def test_remove_document(kb_doc_id):
    db = _make_mock_db()

    from utils.indexer import remove_document
    await remove_document(db, kb_doc_id)

    # Should have executed delete + update + commit
    assert db.execute.call_count == 2
    assert db.commit.called


@pytest.mark.asyncio
async def test_index_document_embed_failure(kb_doc_id, proc_doc_id):
    kb_doc = _make_kb_doc(kb_doc_id, proc_doc_id)
    proc_doc = _make_proc_doc()
    db = _make_mock_db()

    result_mock = MagicMock()
    result_mock.scalar_one_or_none = MagicMock(return_value=kb_doc)
    result_mock.one_or_none = MagicMock(return_value=(kb_doc, proc_doc))
    db.execute.return_value = result_mock

    with patch("utils.indexer.embed_batch", new=AsyncMock(side_effect=RuntimeError("OpenAI down"))):
        from utils.indexer import index_document

        with pytest.raises(RuntimeError, match="OpenAI down"):
            await index_document(db, kb_doc_id)

    # Failure path: rollback then commit failure status
    assert db.rollback.called
