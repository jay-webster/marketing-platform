"""RAG-grounded structured content generation for email, LinkedIn, and PDF body."""
from __future__ import annotations

import logging
from typing import Any

from anthropic import AsyncAnthropic
from sqlalchemy.ext.asyncio import AsyncSession

from src.config import get_settings
from utils.embeddings import embed_text
from utils.rag import build_prompt, retrieve_chunks

logger = logging.getLogger(__name__)

_anthropic_client: AsyncAnthropic | None = None

VALID_OUTPUT_TYPES = {"email", "linkedin", "pdf_body"}

_EMAIL_SYSTEM_SUFFIX = """
OUTPUT FORMAT (required — do not deviate):
SUBJECT: <single line subject>

BODY: <email body paragraphs>

Return only the above format. Do not add any preamble or commentary."""

_LINKEDIN_SYSTEM_SUFFIX = """
OUTPUT FORMAT (required — do not deviate):
<post body — under 3000 characters, including a clear call to action>

HASHTAGS: #tag1 #tag2 #tag3

Return only the above format. Do not add any preamble or commentary."""

_PDF_BODY_SYSTEM_SUFFIX = """
OUTPUT FORMAT (required — do not deviate):
TITLE: <document title>

SECTION: <first section heading>
<section content paragraphs>

SECTION: <second section heading>
<section content paragraphs>

Continue with as many SECTION blocks as needed (2–5 sections). Do not add preamble."""


class NoKBContentError(Exception):
    """Raised when retrieval returns no relevant knowledge base chunks."""


def _get_anthropic() -> AsyncAnthropic:
    global _anthropic_client
    if _anthropic_client is None:
        _anthropic_client = AsyncAnthropic()
    return _anthropic_client


def _parse_email(text: str) -> dict[str, str]:
    """Parse SUBJECT/BODY delimited email response. Graceful fallback on missing delimiters."""
    subject = ""
    body = text.strip()

    if "SUBJECT:" in text:
        parts = text.split("SUBJECT:", 1)[1]
        if "BODY:" in parts:
            subject_part, body_part = parts.split("BODY:", 1)
            subject = subject_part.strip()
            body = body_part.strip()
        else:
            subject = parts.strip()
            body = ""

    return {"subject": subject, "body": body}


def _parse_linkedin(text: str) -> dict[str, Any]:
    """Parse post text and HASHTAGS delimiter. Graceful fallback."""
    post_text = text.strip()
    hashtags: list[str] = []

    if "HASHTAGS:" in text:
        parts = text.rsplit("HASHTAGS:", 1)
        post_text = parts[0].strip()
        raw_tags = parts[1].strip()
        hashtags = [t.strip() for t in raw_tags.split() if t.strip()]

    return {"post_text": post_text, "hashtags": hashtags}


def _parse_pdf_body(text: str) -> dict[str, Any]:
    """Parse TITLE and SECTION blocks. Graceful fallback to single section."""
    title = ""
    sections: list[dict[str, str]] = []

    lines = text.strip().splitlines()
    current_heading: str | None = None
    current_content: list[str] = []

    for line in lines:
        if line.startswith("TITLE:"):
            title = line[len("TITLE:"):].strip()
        elif line.startswith("SECTION:"):
            if current_heading is not None:
                sections.append({"heading": current_heading, "content": "\n".join(current_content).strip()})
            current_heading = line[len("SECTION:"):].strip()
            current_content = []
        else:
            if current_heading is not None:
                current_content.append(line)

    if current_heading is not None:
        sections.append({"heading": current_heading, "content": "\n".join(current_content).strip()})

    if not sections:
        sections = [{"heading": "Overview", "content": text.strip()}]
    if not title:
        title = sections[0]["heading"] if sections else "Document"

    return {"title": title, "sections": sections}


async def generate_content(
    db: AsyncSession,
    output_type: str,
    prompt: str,
) -> dict[str, Any]:
    """Generate structured marketing content grounded in the knowledge base.

    Args:
        db: Async database session for KB retrieval.
        output_type: One of "email", "linkedin", "pdf_body".
        prompt: User's generation prompt.

    Returns:
        - email: {"subject": str, "body": str}
        - linkedin: {"post_text": str, "hashtags": list[str]}
        - pdf_body: {"title": str, "sections": [{"heading": str, "content": str}]}

    Raises:
        NoKBContentError: If retrieval returns no relevant chunks.
        ValueError: If output_type is not valid.
    """
    if output_type not in VALID_OUTPUT_TYPES:
        raise ValueError(f"Invalid output_type: {output_type}. Must be one of {VALID_OUTPUT_TYPES}")

    settings = get_settings()

    query_embedding = await embed_text(prompt)
    chunks = await retrieve_chunks(db, query_embedding)

    if not chunks:
        raise NoKBContentError(f"No relevant knowledge base content found for prompt: {prompt[:80]}")

    rag_system_prompt = build_prompt(chunks)

    if output_type == "email":
        system_prompt = rag_system_prompt + _EMAIL_SYSTEM_SUFFIX
    elif output_type == "linkedin":
        system_prompt = rag_system_prompt + _LINKEDIN_SYSTEM_SUFFIX
    else:
        system_prompt = rag_system_prompt + _PDF_BODY_SYSTEM_SUFFIX

    client = _get_anthropic()
    response = await client.messages.create(
        model=settings.GENERATION_MODEL,
        max_tokens=settings.GENERATION_MAX_TOKENS,
        system=system_prompt,
        messages=[{"role": "user", "content": prompt}],
    )

    raw_text = response.content[0].text if response.content else ""

    if output_type == "email":
        return _parse_email(raw_text)
    elif output_type == "linkedin":
        return _parse_linkedin(raw_text)
    else:
        return _parse_pdf_body(raw_text)
