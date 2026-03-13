"""Voyage AI embeddings client for KB indexing."""
import asyncio
from functools import lru_cache

import voyageai

from src.config import get_settings

_EMBEDDING_MODEL = "voyage-3-lite"
_EMBED_DIMENSIONS = 512
_MAX_BATCH = 128  # Voyage AI limit per request
_RETRY_ATTEMPTS = 3
_RETRY_DELAY = 1.0  # seconds, doubles each attempt


@lru_cache(maxsize=1)
def _get_client() -> voyageai.AsyncClient:
    settings = get_settings()
    return voyageai.AsyncClient(api_key=settings.VOYAGE_API_KEY)


async def embed_text(text: str) -> list[float]:
    """Embed a single text string. Returns a 512-dimensional vector."""
    results = await embed_batch([text])
    return results[0]


async def embed_batch(texts: list[str]) -> list[list[float]]:
    """Embed a list of texts in one API call (max 128 per call).

    Returns embeddings in the same order as input texts.
    Retries up to 3 times with exponential back-off on transient errors.
    """
    if not texts:
        return []

    client = _get_client()
    delay = _RETRY_DELAY

    for attempt in range(_RETRY_ATTEMPTS):
        try:
            result = await client.embed(texts, model=_EMBEDDING_MODEL, input_type="document")
            return result.embeddings
        except Exception:
            if attempt == _RETRY_ATTEMPTS - 1:
                raise
            await asyncio.sleep(delay)
            delay *= 2

    # unreachable — loop always raises on final attempt
    raise RuntimeError("embed_batch: retry loop exhausted")
