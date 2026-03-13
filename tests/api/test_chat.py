"""API tests for src/api/chat.py — RAG chat endpoints.

All AI calls (embed_text, rag_stream_generator) are mocked.
"""
import json
import uuid
from collections.abc import AsyncGenerator
from datetime import datetime, timezone
from unittest.mock import AsyncMock, patch

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from src.models.chat_message import ChatMessage
from src.models.chat_session import ChatSession

_async = pytest.mark.asyncio(loop_scope="function")

FAKE_EMBEDDING = [0.0] * 1536


# ---------------------------------------------------------------------------
# Mock helpers
# ---------------------------------------------------------------------------

def _patch_workers():
    """Prevent real workers from starting inside lifespan."""
    return patch.multiple(
        "utils.queue",
        startup_recovery=AsyncMock(),
        start_queue_workers=AsyncMock(),
        stop_queue_workers=AsyncMock(),
        start_indexing_workers=AsyncMock(),
        stop_indexing_workers=AsyncMock(),
    )


def _patch_embed():
    return patch("src.api.chat.embed_text", new=AsyncMock(return_value=FAKE_EMBEDDING))


async def _rag_chunks_generator(*args, **kwargs) -> AsyncGenerator:
    """Simulates a RAG stream that returns two chunks + sources + done."""
    yield ("chunk", {"text": "Hello ", "is_generated_content": False})
    yield ("chunk", {"text": "world.", "is_generated_content": False})
    yield ("sources", {"documents": [{"id": str(uuid.uuid4()), "title": "Test Doc", "source_file": "doc.md"}]})
    yield ("done", {})


async def _rag_no_content_generator(*args, **kwargs) -> AsyncGenerator:
    yield ("no_content", {})


async def _rag_generation_generator(*args, **kwargs) -> AsyncGenerator:
    yield ("chunk", {"text": "Draft email copy.", "is_generated_content": True})
    yield ("sources", {"documents": []})
    yield ("done", {})


def _patch_rag(generator_fn=None):
    gen = generator_fn or _rag_chunks_generator
    return patch("src.api.chat.rag_stream_generator", side_effect=gen)


# ---------------------------------------------------------------------------
# DB helpers
# ---------------------------------------------------------------------------

async def _create_session(db: AsyncSession, user_id: uuid.UUID, title="Test Session") -> ChatSession:
    s = ChatSession(user_id=user_id, title=title)
    db.add(s)
    await db.commit()
    await db.refresh(s)
    return s


async def _add_message(db: AsyncSession, session_id: uuid.UUID, role: str, content: str) -> ChatMessage:
    m = ChatMessage(session_id=session_id, role=role, content=content)
    db.add(m)
    await db.commit()
    await db.refresh(m)
    return m


def _parse_sse(body: str) -> list[dict]:
    """Parse SSE text body into list of {event, data} dicts."""
    events = []
    event_type = None
    for line in body.splitlines():
        if line.startswith("event:"):
            event_type = line[len("event:"):].strip()
        elif line.startswith("data:"):
            data = json.loads(line[len("data:"):].strip())
            events.append({"event": event_type, "data": data})
            event_type = None
    return events


# ---------------------------------------------------------------------------
# POST /chat/sessions — Create session
# ---------------------------------------------------------------------------

@_async
async def test_create_session_unauthenticated(async_client: AsyncClient):
    with _patch_workers():
        response = await async_client.post("/api/v1/chat/sessions", json={"title": "My Chat"})
    assert response.status_code == 401


@_async
async def test_create_session_happy_path(async_client: AsyncClient, marketer_token: str):
    with _patch_workers():
        response = await async_client.post(
            "/api/v1/chat/sessions",
            headers={"Authorization": f"Bearer {marketer_token}"},
            json={"title": "Campaign Chat"},
        )
    assert response.status_code == 201
    data = response.json()["data"]
    assert data["title"] == "Campaign Chat"
    assert "id" in data
    assert "created_at" in data


# ---------------------------------------------------------------------------
# GET /chat/sessions
# ---------------------------------------------------------------------------

@_async
async def test_list_sessions_empty(async_client: AsyncClient, marketer_token: str):
    with _patch_workers():
        response = await async_client.get(
            "/api/v1/chat/sessions",
            headers={"Authorization": f"Bearer {marketer_token}"},
        )
    assert response.status_code == 200
    assert response.json()["data"] == []


@_async
async def test_list_sessions_returns_only_own(
    async_client: AsyncClient,
    marketer_token: str,
    marketer_user,
    marketing_manager_user,
    db_session: AsyncSession,
):
    await _create_session(db_session, marketer_user.id, "My Session")
    await _create_session(db_session, marketing_manager_user.id, "Other Session")

    with _patch_workers():
        response = await async_client.get(
            "/api/v1/chat/sessions",
            headers={"Authorization": f"Bearer {marketer_token}"},
        )
    assert response.status_code == 200
    sessions = response.json()["data"]
    assert len(sessions) == 1
    assert sessions[0]["title"] == "My Session"


@_async
async def test_list_sessions_excludes_deleted(
    async_client: AsyncClient,
    marketer_token: str,
    marketer_user,
    db_session: AsyncSession,
):
    s = await _create_session(db_session, marketer_user.id)
    s.deleted_at = datetime.now(timezone.utc)
    await db_session.commit()

    with _patch_workers():
        response = await async_client.get(
            "/api/v1/chat/sessions",
            headers={"Authorization": f"Bearer {marketer_token}"},
        )
    assert response.json()["data"] == []


# ---------------------------------------------------------------------------
# GET /chat/sessions/{session_id} — Session history (US9 / T030)
# ---------------------------------------------------------------------------

@_async
async def test_get_session_history(
    async_client: AsyncClient,
    marketer_token: str,
    marketer_user,
    db_session: AsyncSession,
):
    s = await _create_session(db_session, marketer_user.id, "History Test")
    await _add_message(db_session, s.id, "user", "What is our brand voice?")
    await _add_message(db_session, s.id, "assistant", "Confident and approachable.")

    with _patch_workers():
        response = await async_client.get(
            f"/api/v1/chat/sessions/{s.id}",
            headers={"Authorization": f"Bearer {marketer_token}"},
        )
    assert response.status_code == 200
    data = response.json()["data"]
    assert data["id"] == str(s.id)
    assert len(data["messages"]) == 2
    assert data["messages"][0]["role"] == "user"
    assert data["messages"][1]["role"] == "assistant"


@_async
async def test_get_session_not_found(async_client: AsyncClient, marketer_token: str):
    with _patch_workers():
        response = await async_client.get(
            f"/api/v1/chat/sessions/{uuid.uuid4()}",
            headers={"Authorization": f"Bearer {marketer_token}"},
        )
    assert response.status_code == 404


# ---------------------------------------------------------------------------
# DELETE /chat/sessions/{session_id} (US9 / T030)
# ---------------------------------------------------------------------------

@_async
async def test_delete_session(
    async_client: AsyncClient,
    marketer_token: str,
    marketer_user,
    db_session: AsyncSession,
):
    s = await _create_session(db_session, marketer_user.id)

    with _patch_workers():
        response = await async_client.delete(
            f"/api/v1/chat/sessions/{s.id}",
            headers={"Authorization": f"Bearer {marketer_token}"},
        )
    assert response.status_code == 204

    # Should no longer appear in list
    with _patch_workers():
        list_response = await async_client.get(
            "/api/v1/chat/sessions",
            headers={"Authorization": f"Bearer {marketer_token}"},
        )
    assert list_response.json()["data"] == []


@_async
async def test_delete_session_wrong_user(
    async_client: AsyncClient,
    marketer_token: str,
    marketing_manager_user,
    db_session: AsyncSession,
):
    s = await _create_session(db_session, marketing_manager_user.id)
    with _patch_workers():
        response = await async_client.delete(
            f"/api/v1/chat/sessions/{s.id}",
            headers={"Authorization": f"Bearer {marketer_token}"},
        )
    assert response.status_code == 404


# ---------------------------------------------------------------------------
# POST /chat/sessions/{session_id}/messages — Basic RAG (US1 / T022)
# ---------------------------------------------------------------------------

@_async
async def test_send_message_unauthenticated(
    async_client: AsyncClient,
    marketer_user,
    db_session: AsyncSession,
):
    s = await _create_session(db_session, marketer_user.id)
    with _patch_workers():
        response = await async_client.post(
            f"/api/v1/chat/sessions/{s.id}/messages",
            json={"message": "Hello"},
        )
    assert response.status_code == 401


@_async
async def test_send_message_basic_rag(
    async_client: AsyncClient,
    marketer_token: str,
    marketer_user,
    db_session: AsyncSession,
):
    s = await _create_session(db_session, marketer_user.id)

    with _patch_workers(), _patch_embed(), _patch_rag():
        response = await async_client.post(
            f"/api/v1/chat/sessions/{s.id}/messages",
            headers={"Authorization": f"Bearer {marketer_token}"},
            json={"message": "Tell me about our Q1 campaign."},
        )

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/event-stream")

    events = _parse_sse(response.text)
    event_types = [e["event"] for e in events]
    assert "chunk" in event_types
    assert "done" in event_types

    # Combined chunks should form the full response
    chunks = [e["data"]["text"] for e in events if e["event"] == "chunk"]
    assert "".join(chunks) == "Hello world."


@_async
async def test_send_message_empty_raises(
    async_client: AsyncClient,
    marketer_token: str,
    marketer_user,
    db_session: AsyncSession,
):
    s = await _create_session(db_session, marketer_user.id)
    with _patch_workers():
        response = await async_client.post(
            f"/api/v1/chat/sessions/{s.id}/messages",
            headers={"Authorization": f"Bearer {marketer_token}"},
            json={"message": "   "},
        )
    assert response.status_code == 422


# ---------------------------------------------------------------------------
# No-content path (US4 / T023)
# ---------------------------------------------------------------------------

@_async
async def test_send_message_no_kb_content(
    async_client: AsyncClient,
    marketer_token: str,
    marketer_user,
    db_session: AsyncSession,
):
    s = await _create_session(db_session, marketer_user.id)

    with _patch_workers(), _patch_embed(), _patch_rag(_rag_no_content_generator):
        response = await async_client.post(
            f"/api/v1/chat/sessions/{s.id}/messages",
            headers={"Authorization": f"Bearer {marketer_token}"},
            json={"message": "What is the weather?"},
        )

    assert response.status_code == 200
    events = _parse_sse(response.text)
    event_types = [e["event"] for e in events]
    assert "no_content" in event_types
    assert "done" in event_types

    no_content_event = next(e for e in events if e["event"] == "no_content")
    assert "don't have enough information" in no_content_event["data"]["message"].lower()


# ---------------------------------------------------------------------------
# Follow-up with conversation history (US2 / T025)
# ---------------------------------------------------------------------------

@_async
async def test_send_message_with_history(
    async_client: AsyncClient,
    marketer_token: str,
    marketer_user,
    db_session: AsyncSession,
):
    s = await _create_session(db_session, marketer_user.id)
    # Seed prior turn
    await _add_message(db_session, s.id, "user", "What is our brand voice?")
    await _add_message(db_session, s.id, "assistant", "Confident and approachable.")

    captured_history = []

    async def _capturing_generator(*args, history=None, **kwargs):
        captured_history.extend(history or [])
        yield ("chunk", {"text": "Follow-up answer.", "is_generated_content": False})
        yield ("sources", {"documents": []})
        yield ("done", {})

    with _patch_workers(), _patch_embed(), patch("src.api.chat.rag_stream_generator", side_effect=_capturing_generator):
        response = await async_client.post(
            f"/api/v1/chat/sessions/{s.id}/messages",
            headers={"Authorization": f"Bearer {marketer_token}"},
            json={"message": "Can you elaborate?"},
        )

    assert response.status_code == 200
    # Prior turns should have been passed as history
    assert any(m["role"] == "user" and "brand voice" in m["content"] for m in captured_history)
    assert any(m["role"] == "assistant" for m in captured_history)


# ---------------------------------------------------------------------------
# Generation intent detection (US3 / T027)
# ---------------------------------------------------------------------------

@_async
async def test_send_message_generation_flagged(
    async_client: AsyncClient,
    marketer_token: str,
    marketer_user,
    db_session: AsyncSession,
):
    s = await _create_session(db_session, marketer_user.id)

    with _patch_workers(), _patch_embed(), _patch_rag(_rag_generation_generator):
        response = await async_client.post(
            f"/api/v1/chat/sessions/{s.id}/messages",
            headers={"Authorization": f"Bearer {marketer_token}"},
            json={"message": "Write an email for our Q1 campaign."},
        )

    assert response.status_code == 200
    events = _parse_sse(response.text)
    chunk_events = [e for e in events if e["event"] == "chunk"]
    assert any(e["data"].get("is_generated_content") for e in chunk_events)


# ---------------------------------------------------------------------------
# Content variation (US5 / T028)
# ---------------------------------------------------------------------------

@_async
async def test_send_message_content_variation_returns_chunks(
    async_client: AsyncClient,
    marketer_token: str,
    marketer_user,
    db_session: AsyncSession,
):
    """Requesting a variation still streams chunks and marks is_generated_content."""
    s = await _create_session(db_session, marketer_user.id)

    async def _variation_generator(*args, **kwargs):
        yield ("chunk", {"text": "Alternative version.", "is_generated_content": True})
        yield ("sources", {"documents": []})
        yield ("done", {})

    with _patch_workers(), _patch_embed(), _patch_rag(_variation_generator):
        response = await async_client.post(
            f"/api/v1/chat/sessions/{s.id}/messages",
            headers={"Authorization": f"Bearer {marketer_token}"},
            json={"message": "Create a variation of the campaign email."},
        )

    assert response.status_code == 200
    events = _parse_sse(response.text)
    chunk_events = [e for e in events if e["event"] == "chunk"]
    assert len(chunk_events) > 0
    assert chunk_events[0]["data"]["is_generated_content"] is True


# ---------------------------------------------------------------------------
# Named document targeting (US6 / T032)
# ---------------------------------------------------------------------------

@_async
async def test_send_message_with_document_title_filter(
    async_client: AsyncClient,
    marketer_token: str,
    marketer_user,
    db_session: AsyncSession,
):
    """document_title param should be forwarded to rag_stream_generator."""
    s = await _create_session(db_session, marketer_user.id)

    captured_doc_title = []

    async def _capturing_generator(*args, document_title=None, **kwargs):
        captured_doc_title.append(document_title)
        yield ("chunk", {"text": "Targeted answer.", "is_generated_content": False})
        yield ("sources", {"documents": []})
        yield ("done", {})

    with _patch_workers(), _patch_embed(), patch("src.api.chat.rag_stream_generator", side_effect=_capturing_generator):
        response = await async_client.post(
            f"/api/v1/chat/sessions/{s.id}/messages",
            headers={"Authorization": f"Bearer {marketer_token}"},
            json={"message": "Summarize this doc.", "document_title": "Q1 Brand Guide"},
        )

    assert response.status_code == 200
    assert captured_doc_title == ["Q1 Brand Guide"]


# ---------------------------------------------------------------------------
# Sources returned in SSE stream
# ---------------------------------------------------------------------------

@_async
async def test_send_message_sources_in_stream(
    async_client: AsyncClient,
    marketer_token: str,
    marketer_user,
    db_session: AsyncSession,
):
    s = await _create_session(db_session, marketer_user.id)

    with _patch_workers(), _patch_embed(), _patch_rag():
        response = await async_client.post(
            f"/api/v1/chat/sessions/{s.id}/messages",
            headers={"Authorization": f"Bearer {marketer_token}"},
            json={"message": "What does the brand guide say?"},
        )

    events = _parse_sse(response.text)
    source_events = [e for e in events if e["event"] == "sources"]
    assert len(source_events) == 1
    assert "documents" in source_events[0]["data"]
    assert source_events[0]["data"]["documents"][0]["title"] == "Test Doc"
