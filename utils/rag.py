"""pgvector retrieval, prompt assembly, and SSE stream generator for RAG chat."""
from __future__ import annotations

import json
import uuid
from collections.abc import AsyncGenerator
from typing import Any

from anthropic import AsyncAnthropic
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from src.config import get_settings

CONSTRAINED_SYSTEM_PROMPT = """You are a marketing content assistant. You help users find and understand marketing materials.

RULES (non-negotiable):
1. Answer ONLY using the provided context passages below.
2. If the context does not contain enough information to answer the question, respond with exactly:
   "I don't have enough information in the knowledge base to answer that question."
3. Never fabricate facts, statistics, or claims not present in the context.
4. When generating or drafting marketing content (emails, social posts, ad copy, etc.), base it strictly on the approved source documents provided in context.
5. Cite the source document title when referencing specific information.

Context passages:
{context}"""

_GENERATION_KEYWORDS = {
    "write", "draft", "create", "generate", "compose", "produce",
    "suggest", "craft", "make", "come up with",
}

_anthropic_client: AsyncAnthropic | None = None


def _get_anthropic() -> AsyncAnthropic:
    global _anthropic_client
    if _anthropic_client is None:
        _anthropic_client = AsyncAnthropic()
    return _anthropic_client


def _is_generation_intent(user_message: str) -> bool:
    """Return True if the message appears to request content generation."""
    lower = user_message.lower()
    return any(kw in lower for kw in _GENERATION_KEYWORDS)


async def retrieve_chunks(
    db: AsyncSession,
    query_embedding: list[float],
    top_k: int | None = None,
    similarity_threshold: float | None = None,
    document_title: str | None = None,
) -> list[dict[str, Any]]:
    """Query content_chunks via pgvector cosine similarity.

    Args:
        db: Async database session.
        query_embedding: 512-dim embedding of the user query.
        top_k: Maximum chunks to return (defaults to settings.KB_RETRIEVAL_TOP_K).
        similarity_threshold: Minimum similarity floor (defaults to settings.KB_SIMILARITY_THRESHOLD).
        document_title: If set, restrict retrieval to chunks from docs matching this title.

    Returns:
        List of dicts with keys: id, content_text, metadata, similarity.
    """
    settings = get_settings()
    k = top_k or settings.KB_RETRIEVAL_TOP_K
    threshold = similarity_threshold if similarity_threshold is not None else settings.KB_SIMILARITY_THRESHOLD

    embedding_str = "[" + ",".join(str(x) for x in query_embedding) + "]"

    title_filter = ""
    params: dict[str, Any] = {
        "embedding": embedding_str,
        "threshold": threshold,
        "top_k": k,
    }

    if document_title:
        title_filter = """
            AND pd.title ILIKE :doc_title
        """
        params["doc_title"] = f"%{document_title}%"

    sql = text(
        f"""
        SELECT
            cc.id,
            cc.content_text,
            cc.metadata,
            1 - (cc.embedding <=> CAST(:embedding AS vector)) AS similarity
        FROM content_chunks cc
        JOIN knowledge_base_documents kbd ON kbd.id = cc.knowledge_base_document_id
        JOIN processed_documents pd ON pd.id = kbd.processed_document_id
        WHERE kbd.index_status = 'indexed'
          AND 1 - (cc.embedding <=> CAST(:embedding AS vector)) >= :threshold
          {title_filter}
        ORDER BY cc.embedding <=> CAST(:embedding AS vector)
        LIMIT :top_k
        """
    )

    result = await db.execute(sql, params)
    rows = result.fetchall()
    return [
        {
            "id": str(row.id),
            "content_text": row.content_text,
            "metadata": row.metadata or {},
            "similarity": float(row.similarity),
        }
        for row in rows
    ]


def build_prompt(chunks: list[dict[str, Any]]) -> str:
    """Format retrieved chunks into the constrained system prompt context block."""
    if not chunks:
        context = "(no relevant content found in knowledge base)"
    else:
        parts = []
        for i, chunk in enumerate(chunks, 1):
            title = chunk["metadata"].get("title", "Unknown Document")
            parts.append(f"[{i}] {title}\n{chunk['content_text']}")
        context = "\n\n---\n\n".join(parts)
    return CONSTRAINED_SYSTEM_PROMPT.format(context=context)


async def rag_stream_generator(
    db: AsyncSession,
    user_message: str,
    query_embedding: list[float],
    history: list[dict[str, str]] | None = None,
    document_title: str | None = None,
) -> AsyncGenerator[tuple[str, dict[str, Any]], None]:
    """SSE-compatible async generator for RAG chat responses.

    Yields (event_type, data) tuples:
        - ("chunk", {"text": "...", "is_generated_content": bool})
        - ("sources", {"documents": [...]})
        - ("done", {})
        - ("no_content", {}) — when KB has no relevant chunks

    Args:
        db: Async database session.
        user_message: The user's current message.
        query_embedding: Pre-computed embedding of user_message.
        history: Prior conversation turns [{"role": "user"|"assistant", "content": "..."}].
        document_title: Optional document name filter for targeted retrieval.
    """
    settings = get_settings()

    chunks = await retrieve_chunks(
        db,
        query_embedding,
        document_title=document_title,
    )

    if not chunks:
        yield ("no_content", {})
        return

    system_prompt = build_prompt(chunks)
    is_generated = _is_generation_intent(user_message)

    messages: list[dict[str, str]] = list(history or [])
    messages.append({"role": "user", "content": user_message})

    source_docs = [
        {
            "id": c["id"],
            "title": c["metadata"].get("title", "Unknown"),
            "source_file": c["metadata"].get("source_file", ""),
            "similarity": round(c["similarity"], 4),
        }
        for c in chunks
    ]

    client = _get_anthropic()
    async with client.messages.stream(
        model=settings.CHAT_MODEL,
        max_tokens=settings.CHAT_MAX_TOKENS,
        system=system_prompt,
        messages=messages,
    ) as stream:
        async for text_delta in stream.text_stream:
            yield ("chunk", {"text": text_delta, "is_generated_content": is_generated})

    yield ("sources", {"documents": source_docs})
    yield ("done", {})
