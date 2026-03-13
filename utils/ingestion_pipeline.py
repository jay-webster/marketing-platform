"""Claude-powered document structuring pipeline.

Converts raw extracted text into Markdown with YAML frontmatter using two
concurrent Claude API calls: tool_use for metadata, free-text for the body.
"""
import asyncio
import logging
from datetime import datetime, timezone
from typing import Optional

import yaml

logger = logging.getLogger(__name__)

MODEL = "claude-haiku-4-5-20251001"
MAX_SINGLE_PASS_TOKENS = 90_000  # ~360K chars; leave headroom below 200K context window
CHUNK_OVERLAP_CHARS = 200

METADATA_TOOL = {
    "name": "extract_document_metadata",
    "description": "Extract structured metadata fields from document text.",
    "input_schema": {
        "type": "object",
        "properties": {
            "title": {
                "type": "string",
                "description": "The document's primary heading or a title derived from the filename.",
            },
            "author": {
                "type": ["string", "null"],
                "description": "Author name from bylines, 'Prepared by', 'Author:' patterns. Null if not found.",
            },
            "source_date": {
                "type": ["string", "null"],
                "description": "ISO 8601 date (YYYY-MM-DD) from document headers, footers, or date fields. Null if not found.",
            },
        },
        "required": ["title"],
    },
}

METADATA_SYSTEM = (
    "You are a document metadata extractor. Extract metadata fields using the "
    "extract_document_metadata tool.\n"
    "- title: The document's primary heading or filename-derived title. Never null.\n"
    "- author: From bylines, 'Prepared by', 'Author:' patterns. Null if not found.\n"
    "- source_date: ISO 8601 (YYYY-MM-DD). Null if not found.\n"
    "Do not invent values. Return null for fields you cannot find evidence for."
)

BODY_SYSTEM = (
    "You are a document formatter. Convert raw extracted text into well-structured Markdown.\n"
    "Rules:\n"
    "- Use # for the document title (H1), ## for major sections (H2), ### for subsections (H3).\n"
    "- Infer heading levels from ALL CAPS lines, underscored lines, numbered section patterns "
    "(1., 1.1, 1.1.1), or short lines preceding body paragraphs.\n"
    "- Convert tabular data (aligned columns, tab-separated, or pipe-separated) to GFM tables.\n"
    "- Preserve bullet lists as Markdown unordered lists (- item). Preserve numbered lists.\n"
    "- Apply **bold** for ALL CAPS inline labels followed by colon. Apply *italic* sparingly.\n"
    "- Normalize whitespace: max 1 blank line between paragraphs.\n"
    "- Output only the Markdown body. No frontmatter. No commentary."
)

CONTINUATION_SYSTEM = (
    "You are a document formatter. Structure the following continuation of a document as Markdown body only. "
    "No frontmatter. Continue heading hierarchy from the prior section. No commentary."
)


def _estimate_tokens(text: str) -> int:
    return len(text) // 4


def _split_into_chunks(text: str, max_chars: int) -> list[str]:
    """Split text on structural boundaries (double newlines) into chunks."""
    if len(text) <= max_chars:
        return [text]

    paragraphs = text.split("\n\n")
    chunks: list[str] = []
    current: list[str] = []
    current_len = 0

    for para in paragraphs:
        para_len = len(para) + 2  # +2 for the \n\n
        if current_len + para_len > max_chars and current:
            chunks.append("\n\n".join(current))
            current = [para]
            current_len = para_len
        else:
            current.append(para)
            current_len += para_len

    if current:
        chunks.append("\n\n".join(current))

    return chunks


async def structure_document(
    client,  # anthropic.AsyncAnthropic
    extracted_text: str,
    source_file: str,
    source_type: str,
    ingested_by: str,
    reprocessing_note: Optional[str] = None,
    model: str = MODEL,
) -> str:
    """Convert raw extracted text to complete Markdown with YAML frontmatter."""
    note_block = f"\nReprocessing note from user: {reprocessing_note}\n" if reprocessing_note else ""
    max_chars = MAX_SINGLE_PASS_TOKENS * 4

    chunks = _split_into_chunks(extracted_text, max_chars)

    # --- Chunk 0: metadata extraction + body structuring ---
    chunk0 = chunks[0]
    doc_context = (
        f"Source file: {source_file}\nSource type: {source_type}\n{note_block}\n"
        f"--- BEGIN DOCUMENT TEXT ---\n{chunk0}\n--- END DOCUMENT TEXT ---"
    )

    metadata_coro = client.messages.create(
        model=model,
        max_tokens=512,
        system=METADATA_SYSTEM,
        tools=[METADATA_TOOL],
        tool_choice={"type": "tool", "name": "extract_document_metadata"},
        messages=[{"role": "user", "content": f"Extract metadata from the following document text.\n\n{doc_context}"}],
    )
    body_coro = client.messages.create(
        model=model,
        max_tokens=8192,
        system=BODY_SYSTEM,
        messages=[{
            "role": "user",
            "content": (
                f"Convert the following extracted document text to Markdown.{note_block}\n\n"
                f"--- BEGIN DOCUMENT TEXT ---\n{chunk0}\n--- END DOCUMENT TEXT ---"
            ),
        }],
    )

    metadata_response, body_response = await asyncio.gather(metadata_coro, body_coro)

    # Extract tool result
    tool_block = next(
        (b for b in metadata_response.content if b.type == "tool_use"), None
    )
    meta: dict = tool_block.input if tool_block else {}

    # Server-controlled frontmatter fields — never from Claude
    frontmatter: dict = {
        "title": meta.get("title") or source_file,
        "source_file": source_file,
        "source_type": source_type,
        "ingested_at": datetime.now(timezone.utc).isoformat(),
        "ingested_by": ingested_by,
        "review_status": "pending_review",
    }
    if meta.get("author"):
        frontmatter["author"] = meta["author"]
    if meta.get("source_date"):
        frontmatter["source_date"] = meta["source_date"]
    if reprocessing_note:
        frontmatter["reprocessing_note"] = reprocessing_note

    body_parts: list[str] = [body_response.content[0].text]

    # --- Continuation chunks (if any) ---
    for chunk in chunks[1:]:
        cont_response = await client.messages.create(
            model=model,
            max_tokens=8192,
            system=CONTINUATION_SYSTEM,
            messages=[{
                "role": "user",
                "content": (
                    f"Continue structuring the following document section as Markdown body only.\n\n"
                    f"--- BEGIN CONTINUATION ---\n{chunk}\n--- END CONTINUATION ---"
                ),
            }],
        )
        body_parts.append(cont_response.content[0].text)

    yaml_block = yaml.dump(frontmatter, default_flow_style=False, allow_unicode=True, sort_keys=False)
    body_text = "\n\n".join(body_parts)

    return f"---\n{yaml_block}---\n\n{body_text}"


async def structure_document_with_retry(
    client,
    extracted_text: str,
    source_file: str,
    source_type: str,
    ingested_by: str,
    reprocessing_note: Optional[str] = None,
    model: str = MODEL,
    max_retries: int = 3,
) -> str:
    """Wrap structure_document with retry logic for transient API errors."""
    from anthropic import APIConnectionError, APIStatusError, RateLimitError  # noqa: PLC0415

    for attempt in range(max_retries):
        try:
            return await structure_document(
                client=client,
                extracted_text=extracted_text,
                source_file=source_file,
                source_type=source_type,
                ingested_by=ingested_by,
                reprocessing_note=reprocessing_note,
                model=model,
            )
        except RateLimitError as exc:
            if attempt == max_retries - 1:
                raise
            retry_after = int(getattr(exc.response.headers, "get", lambda k, d: d)("retry-after", 2 ** (attempt + 1)))
            logger.warning("Rate limited; retrying in %ds (attempt %d)", retry_after, attempt + 1)
            await asyncio.sleep(retry_after)
        except APIStatusError as exc:
            if exc.status_code == 529:
                if attempt == max_retries - 1:
                    raise
                wait = 2 ** (attempt + 1)
                logger.warning("API overloaded (529); retrying in %ds", wait)
                await asyncio.sleep(wait)
            elif exc.status_code == 401:
                raise  # fatal — do not retry
            else:
                if attempt == max_retries - 1:
                    raise
                await asyncio.sleep(2 ** (attempt + 1))
        except APIConnectionError:
            if attempt == max_retries - 1:
                raise
            wait = 2 ** (attempt + 1)
            logger.warning("Connection error; retrying in %ds", wait)
            await asyncio.sleep(wait)

    raise RuntimeError("structure_document_with_retry exhausted retries without raising")
