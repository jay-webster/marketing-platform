"""Unit tests for utils/extractors.py — format-specific text extraction."""
import csv
import io
import zipfile

import pytest

from utils.extractors import (
    REASON_CORRUPT,
    REASON_EMPTY,
    REASON_NO_TEXT,
    REASON_OVERSIZED,
    SUPPORTED_EXTENSIONS,
    extract_text,
    extract_text_async,
    preflight_check,
)


# ---------------------------------------------------------------------------
# preflight_check
# ---------------------------------------------------------------------------

def test_preflight_empty_raises():
    with pytest.raises(ValueError, match=REASON_EMPTY):
        preflight_check(0, "file.pdf")


def test_preflight_oversized_raises():
    with pytest.raises(ValueError, match=REASON_OVERSIZED):
        preflight_check(50 * 1024 * 1024 + 1, "file.pdf")


def test_preflight_valid_passes():
    preflight_check(1024, "file.pdf")  # no exception


# ---------------------------------------------------------------------------
# Supported extensions
# ---------------------------------------------------------------------------

def test_supported_extensions_set():
    assert ".pdf" in SUPPORTED_EXTENSIONS
    assert ".docx" in SUPPORTED_EXTENSIONS
    assert ".pptx" in SUPPORTED_EXTENSIONS
    assert ".csv" in SUPPORTED_EXTENSIONS
    assert ".txt" in SUPPORTED_EXTENSIONS
    assert ".md" in SUPPORTED_EXTENSIONS


def test_unsupported_extension_raises():
    stream = io.BytesIO(b"content")
    with pytest.raises(ValueError, match="Unsupported file type"):
        extract_text(stream, ".xlsx")


# ---------------------------------------------------------------------------
# CSV extraction
# ---------------------------------------------------------------------------

def test_extract_csv_produces_gfm_table():
    content = "Name,Age,City\nAlice,30,NYC\nBob,25,LA"
    stream = io.BytesIO(content.encode())
    result = extract_text(stream, ".csv")
    assert "Name | Age | City" in result
    assert "--- | --- | ---" in result
    assert "Alice | 30 | NYC" in result


def test_extract_csv_empty_raises():
    stream = io.BytesIO(b"   \n  ")
    with pytest.raises(ValueError, match=REASON_EMPTY):
        extract_text(stream, ".csv")


# ---------------------------------------------------------------------------
# Plain text / Markdown extraction
# ---------------------------------------------------------------------------

def test_extract_txt_returns_content():
    stream = io.BytesIO(b"Hello, world!")
    result = extract_text(stream, ".txt")
    assert result == "Hello, world!"


def test_extract_md_returns_content():
    stream = io.BytesIO(b"# Title\n\nSome content.")
    result = extract_text(stream, ".md")
    assert "# Title" in result


def test_extract_txt_empty_raises():
    stream = io.BytesIO(b"   \n\t  ")
    with pytest.raises(ValueError, match=REASON_EMPTY):
        extract_text(stream, ".txt")


def test_extract_txt_replace_encoding_errors():
    # Non-UTF-8 byte should not raise — replaced with replacement char
    stream = io.BytesIO(b"Hello \xff world")
    result = extract_text(stream, ".txt")
    assert "Hello" in result
    assert "world" in result


# ---------------------------------------------------------------------------
# Async wrapper
# ---------------------------------------------------------------------------

_async = pytest.mark.asyncio(loop_scope="function")


@_async
async def test_extract_text_async_txt():
    stream = io.BytesIO(b"async content")
    result = await extract_text_async(stream, ".txt")
    assert result == "async content"


@_async
async def test_extract_text_async_unsupported():
    stream = io.BytesIO(b"data")
    with pytest.raises(ValueError, match="Unsupported file type"):
        await extract_text_async(stream, ".docx_unknown")


# ---------------------------------------------------------------------------
# PDF extraction (pymupdf) — skipped if fitz not installed
# ---------------------------------------------------------------------------

fitz = pytest.importorskip("fitz", reason="pymupdf not installed")


def test_extract_pdf_corrupt_raises():
    stream = io.BytesIO(b"not a pdf at all")
    with pytest.raises(ValueError, match=REASON_CORRUPT):
        extract_text(stream, ".pdf")


# ---------------------------------------------------------------------------
# DOCX extraction (python-docx) — corrupt input
# ---------------------------------------------------------------------------

def test_extract_docx_corrupt_raises():
    stream = io.BytesIO(b"not a docx")
    with pytest.raises(ValueError, match=REASON_CORRUPT):
        extract_text(stream, ".docx")


def test_extract_docx_empty_zip_raises():
    # A valid zip but with no Word document inside — results in PackageNotFoundError → corrupt
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("dummy.txt", "irrelevant")
    buf.seek(0)
    with pytest.raises(ValueError, match=REASON_CORRUPT):
        extract_text(stream=buf, file_type=".docx")


# ---------------------------------------------------------------------------
# PPTX extraction (python-pptx) — corrupt input
# ---------------------------------------------------------------------------

def test_extract_pptx_corrupt_raises():
    stream = io.BytesIO(b"not a pptx")
    with pytest.raises(ValueError, match=REASON_CORRUPT):
        extract_text(stream, ".pptx")
