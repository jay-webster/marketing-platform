"""Markdown section-primary chunker with frontmatter prepend.

Strategy:
1. Split on `##` (H2) headings — each section becomes a candidate chunk.
2. If a section exceeds MAX_TOKENS, split further at paragraph boundaries
   with OVERLAP_TOKENS overlap between successive sub-chunks.
3. Prepend YAML frontmatter extracted from the source document to every
   chunk so retrieval results carry document-level metadata.

Token counts use a simple word-based approximation (4 chars ≈ 1 token)
to avoid a tiktoken dependency.  This is accurate enough for the 512-token
budget; exact counts are not needed.
"""
from __future__ import annotations

import re
from typing import Any

MAX_TOKENS = 512
OVERLAP_TOKENS = 50

# approximate: 1 token ≈ 4 characters
_CHARS_PER_TOKEN = 4


def _approx_tokens(text: str) -> int:
    return max(1, len(text) // _CHARS_PER_TOKEN)


def _frontmatter_str(metadata: dict[str, Any]) -> str:
    """Render a dict as minimal YAML frontmatter block."""
    if not metadata:
        return ""
    lines = ["---"]
    for key, value in metadata.items():
        lines.append(f"{key}: {value}")
    lines.append("---\n")
    return "\n".join(lines)


def _split_into_sections(markdown: str) -> list[str]:
    """Split on H2 headings, keeping the heading with its body."""
    parts = re.split(r"(?=^## )", markdown, flags=re.MULTILINE)
    return [p.strip() for p in parts if p.strip()]


def _split_by_paragraphs(text: str, max_tokens: int, overlap_tokens: int) -> list[str]:
    """Break *text* at paragraph boundaries; add overlap between chunks."""
    paragraphs = [p.strip() for p in re.split(r"\n{2,}", text) if p.strip()]
    chunks: list[str] = []
    current_parts: list[str] = []
    current_tokens = 0
    overlap_buffer: list[str] = []

    for para in paragraphs:
        para_tokens = _approx_tokens(para)

        if current_tokens + para_tokens > max_tokens and current_parts:
            chunks.append("\n\n".join(current_parts))
            # build overlap from tail of current chunk
            overlap_parts: list[str] = []
            overlap_count = 0
            for part in reversed(current_parts):
                t = _approx_tokens(part)
                if overlap_count + t > overlap_tokens:
                    break
                overlap_parts.insert(0, part)
                overlap_count += t
            overlap_buffer = overlap_parts
            current_parts = list(overlap_buffer)
            current_tokens = sum(_approx_tokens(p) for p in current_parts)

        current_parts.append(para)
        current_tokens += para_tokens

    if current_parts:
        chunks.append("\n\n".join(current_parts))

    return chunks if chunks else [text]


def chunk_markdown(
    markdown: str,
    metadata: dict[str, Any] | None = None,
    max_tokens: int = MAX_TOKENS,
    overlap_tokens: int = OVERLAP_TOKENS,
) -> list[str]:
    """Return a list of chunk strings ready for embedding.

    Each chunk has the document frontmatter prepended so the embedding
    captures both the section content and document-level context.

    Args:
        markdown: Full document markdown (may include a YAML frontmatter block).
        metadata: Parsed frontmatter dict to prepend to every chunk.
        max_tokens: Soft token budget per chunk (default 512).
        overlap_tokens: Tokens of overlap between successive sub-chunks (default 50).

    Returns:
        Ordered list of chunk strings (index corresponds to chunk_index in DB).
    """
    meta = metadata or {}
    fm_prefix = _frontmatter_str(meta)

    sections = _split_into_sections(markdown)
    chunks: list[str] = []

    for section in sections:
        if _approx_tokens(section) <= max_tokens:
            chunks.append(fm_prefix + section)
        else:
            sub_chunks = _split_by_paragraphs(section, max_tokens, overlap_tokens)
            for sub in sub_chunks:
                chunks.append(fm_prefix + sub)

    return chunks if chunks else [fm_prefix + markdown]
