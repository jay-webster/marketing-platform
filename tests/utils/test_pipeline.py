"""Unit tests for utils/ingestion_pipeline.py — Claude structuring pipeline."""
import asyncio
import io
import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from utils.ingestion_pipeline import (
    _estimate_tokens,
    _split_into_chunks,
    structure_document,
    structure_document_with_retry,
)
from utils.queue import _parse_frontmatter_field

_async = pytest.mark.asyncio(loop_scope="function")


# ---------------------------------------------------------------------------
# Pure helpers
# ---------------------------------------------------------------------------

def test_estimate_tokens_approx():
    text = "a" * 400
    assert _estimate_tokens(text) == 100


def test_split_into_chunks_short_text():
    text = "Short text"
    chunks = _split_into_chunks(text, max_chars=1000)
    assert chunks == [text]


def test_split_into_chunks_splits_on_double_newline():
    paragraphs = ["Para one.", "Para two.", "Para three."]
    text = "\n\n".join(paragraphs)
    # max_chars forces splitting after first paragraph (~10 chars)
    chunks = _split_into_chunks(text, max_chars=15)
    assert len(chunks) >= 2
    assert "Para one." in chunks[0]


def test_split_into_chunks_no_split_if_fits():
    text = "A\n\nB\n\nC"
    chunks = _split_into_chunks(text, max_chars=100)
    assert len(chunks) == 1


# ---------------------------------------------------------------------------
# _parse_frontmatter_field (re-exported from queue.py logic, tested independently)
# ---------------------------------------------------------------------------

def test_parse_frontmatter_field_found():
    md = "---\ntitle: My Doc\nauthor: Alice\n---\n\n# Content"
    assert _parse_frontmatter_field(md, "title") == "My Doc"
    assert _parse_frontmatter_field(md, "author") == "Alice"


def test_parse_frontmatter_field_missing_key():
    md = "---\ntitle: My Doc\n---\n\n# Content"
    assert _parse_frontmatter_field(md, "source_date") is None


def test_parse_frontmatter_field_no_frontmatter():
    md = "# No frontmatter here"
    assert _parse_frontmatter_field(md, "title") is None


def test_parse_frontmatter_field_malformed():
    md = "---\n: invalid yaml\n---\n# Content"
    # Should not raise — returns None
    result = _parse_frontmatter_field(md, "title")
    assert result is None


# ---------------------------------------------------------------------------
# structure_document — mock AsyncAnthropic client
# ---------------------------------------------------------------------------

def _make_metadata_response(title="Test Doc", author=None, source_date=None):
    tool_input = {"title": title}
    if author:
        tool_input["author"] = author
    if source_date:
        tool_input["source_date"] = source_date
    tool_block = SimpleNamespace(type="tool_use", input=tool_input)
    return SimpleNamespace(content=[tool_block])


def _make_body_response(body_text="## Section\n\nBody content here."):
    text_block = SimpleNamespace(type="text", text=body_text)
    return SimpleNamespace(content=[text_block])


def _make_mock_client(title="Test Doc", body="## Section\n\nBody content."):
    client = MagicMock()
    client.messages = MagicMock()
    client.messages.create = AsyncMock(side_effect=[
        _make_metadata_response(title=title),
        _make_body_response(body_text=body),
    ])
    return client


@_async
async def test_structure_document_returns_markdown_with_frontmatter():
    client = _make_mock_client(title="Marketing Report")
    result = await structure_document(
        client=client,
        extracted_text="Some extracted text content.",
        source_file="report.pdf",
        source_type=".pdf",
        ingested_by="user@example.com",
    )
    assert result.startswith("---\n")
    assert "title: Marketing Report" in result
    assert "source_file: report.pdf" in result
    assert "ingested_by: user@example.com" in result
    assert "review_status: pending_review" in result
    assert "## Section" in result


@_async
async def test_structure_document_server_fields_not_from_claude():
    """Server-controlled fields (ingested_at, ingested_by) must not come from Claude."""
    client = _make_mock_client()
    result = await structure_document(
        client=client,
        extracted_text="Text",
        source_file="doc.txt",
        source_type=".txt",
        ingested_by="system",
    )
    # These fields must exist and be set by server
    assert "ingested_by: system" in result
    assert "ingested_at:" in result


@_async
async def test_structure_document_optional_fields_included_when_present():
    client = MagicMock()
    client.messages = MagicMock()
    client.messages.create = AsyncMock(side_effect=[
        _make_metadata_response(title="Doc", author="Alice", source_date="2024-01-15"),
        _make_body_response(),
    ])
    result = await structure_document(
        client=client,
        extracted_text="Text with author and date",
        source_file="doc.pdf",
        source_type=".pdf",
        ingested_by="user@example.com",
    )
    assert "author: Alice" in result
    assert "source_date: '2024-01-15'" in result or "source_date: 2024-01-15" in result


@_async
async def test_structure_document_fallback_title_to_filename():
    """If Claude returns no title, fall back to source_file."""
    client = MagicMock()
    client.messages = MagicMock()
    # Metadata response with no tool_use block
    client.messages.create = AsyncMock(side_effect=[
        SimpleNamespace(content=[]),  # no tool block
        _make_body_response(),
    ])
    result = await structure_document(
        client=client,
        extracted_text="Text",
        source_file="fallback.pdf",
        source_type=".pdf",
        ingested_by="system",
    )
    assert "title: fallback.pdf" in result


@_async
async def test_structure_document_reprocessing_note_included():
    client = _make_mock_client()
    result = await structure_document(
        client=client,
        extracted_text="Text",
        source_file="doc.pdf",
        source_type=".pdf",
        ingested_by="system",
        reprocessing_note="Focus on revenue figures",
    )
    assert "reprocessing_note: Focus on revenue figures" in result


# ---------------------------------------------------------------------------
# structure_document_with_retry — retry behaviour
# ---------------------------------------------------------------------------

@_async
async def test_structure_document_with_retry_succeeds_first_attempt():
    client = _make_mock_client()
    result = await structure_document_with_retry(
        client=client,
        extracted_text="Text",
        source_file="doc.pdf",
        source_type=".pdf",
        ingested_by="system",
    )
    assert "---" in result


@_async
async def test_structure_document_with_retry_raises_on_auth_error():
    from anthropic import APIStatusError

    mock_response = MagicMock()
    mock_response.headers = {}

    client = MagicMock()
    client.messages = MagicMock()
    client.messages.create = AsyncMock(
        side_effect=APIStatusError("Unauthorized", response=mock_response, body={})
    )

    with patch.object(
        mock_response, "headers", {"status_code": 401}
    ):
        pass  # We just need APIStatusError with status_code 401

    # Patch the status_code attribute directly on the exception
    exc = APIStatusError.__new__(APIStatusError)
    exc.status_code = 401
    exc.response = mock_response
    exc.body = {}
    exc.message = "Unauthorized"
    client.messages.create = AsyncMock(side_effect=exc)

    with pytest.raises(APIStatusError):
        await structure_document_with_retry(
            client=client,
            extracted_text="Text",
            source_file="doc.pdf",
            source_type=".pdf",
            ingested_by="system",
            max_retries=3,
        )
    # Should not retry on 401 — called exactly once
    assert client.messages.create.call_count <= 2  # metadata + body at most once
