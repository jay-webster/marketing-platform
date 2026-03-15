"""Chat API endpoints — RAG-powered conversation interface."""
import json
import logging
import uuid
from datetime import datetime, timezone

logger = logging.getLogger(__name__)

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.models.chat_message import ChatMessage
from src.models.chat_session import ChatSession
from utils.auth import get_current_user
from utils.db import get_db
from utils.embeddings import embed_text
from utils.rag import rag_stream_generator

router = APIRouter(prefix="/chat", tags=["chat"])


def _request_id(request: Request) -> str:
    return getattr(request.state, "request_id", "unknown")


# -----------------------------------------------------------------
# POST /chat/sessions — Create a new chat session
# -----------------------------------------------------------------

class CreateSessionRequest(BaseModel):
    title: str | None = None


@router.post("/sessions", status_code=status.HTTP_201_CREATED)
async def create_session(
    request: Request,
    body: CreateSessionRequest,
    current_user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    session = ChatSession(user_id=current_user.id, title=body.title)
    db.add(session)
    await db.commit()
    await db.refresh(session)
    return {
        "data": {
            "id": str(session.id),
            "title": session.title,
            "created_at": session.created_at.isoformat(),
            "last_active_at": session.last_active_at.isoformat(),
        },
        "request_id": _request_id(request),
    }


# -----------------------------------------------------------------
# GET /chat/sessions — List user's active sessions
# -----------------------------------------------------------------

@router.get("/sessions")
async def list_sessions(
    request: Request,
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    current_user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    stmt = (
        select(ChatSession)
        .where(
            ChatSession.user_id == current_user.id,
            ChatSession.deleted_at.is_(None),
        )
        .order_by(ChatSession.last_active_at.desc())
        .offset(offset)
        .limit(limit)
    )
    result = await db.execute(stmt)
    sessions = result.scalars().all()
    return {
        "data": [
            {
                "id": str(s.id),
                "title": s.title,
                "created_at": s.created_at.isoformat(),
                "last_active_at": s.last_active_at.isoformat(),
            }
            for s in sessions
        ],
        "request_id": _request_id(request),
    }


# -----------------------------------------------------------------
# GET /chat/sessions/{session_id} — Session detail + message history
# -----------------------------------------------------------------

@router.get("/sessions/{session_id}")
async def get_session(
    request: Request,
    session_id: uuid.UUID,
    current_user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    session = await _get_owned_session(session_id, current_user.id, db)

    msgs_result = await db.execute(
        select(ChatMessage)
        .where(ChatMessage.session_id == session_id)
        .order_by(ChatMessage.created_at)
    )
    messages = msgs_result.scalars().all()

    return {
        "data": {
            "id": str(session.id),
            "title": session.title,
            "created_at": session.created_at.isoformat(),
            "last_active_at": session.last_active_at.isoformat(),
            "messages": [
                {
                    "id": str(m.id),
                    "role": m.role,
                    "content": m.content,
                    "is_generated_content": m.is_generated_content,
                    "source_documents": m.source_documents,
                    "created_at": m.created_at.isoformat(),
                }
                for m in messages
            ],
        },
        "request_id": _request_id(request),
    }


# -----------------------------------------------------------------
# DELETE /chat/sessions/{session_id} — Soft-delete session
# -----------------------------------------------------------------

@router.delete("/sessions/{session_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_session(
    session_id: uuid.UUID,
    current_user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    session = await _get_owned_session(session_id, current_user.id, db)
    session.deleted_at = datetime.now(timezone.utc)
    await db.commit()


# -----------------------------------------------------------------
# POST /chat/sessions/{session_id}/messages — Send message (SSE stream)
# -----------------------------------------------------------------

class SendMessageRequest(BaseModel):
    message: str
    document_title: str | None = None


@router.post("/sessions/{session_id}/messages")
async def send_message(
    request: Request,
    session_id: uuid.UUID,
    body: SendMessageRequest,
    current_user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    if not body.message.strip():
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={"error": "Message cannot be empty", "code": "EMPTY_MESSAGE"},
        )
    if len(body.message) > 4000:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={"error": "Message exceeds 4000 character limit", "code": "MESSAGE_TOO_LONG"},
        )

    session = await _get_owned_session(session_id, current_user.id, db)

    # Load conversation history (last 20 turns)
    history_result = await db.execute(
        select(ChatMessage)
        .where(ChatMessage.session_id == session_id)
        .order_by(ChatMessage.created_at.desc())
        .limit(20)
    )
    history_rows = list(reversed(history_result.scalars().all()))
    history = [{"role": m.role, "content": m.content} for m in history_rows]

    # Persist user message
    user_msg = ChatMessage(
        session_id=session_id,
        role="user",
        content=body.message,
    )
    db.add(user_msg)
    session.last_active_at = datetime.now(timezone.utc)
    if session.title is None:
        session.title = body.message.strip()[:60]
    await db.commit()

    return StreamingResponse(
        _sse_stream(db, session, body.message, history, body.document_title),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
            "X-Request-ID": _request_id(request),
        },
    )


async def _sse_stream(db, session, user_message, history, document_title):
    """Async generator that drives the SSE response."""
    assistant_content_parts: list[str] = []
    is_generated = False
    source_documents = None

    try:
        query_embedding = await embed_text(user_message)

        async for event_type, data in rag_stream_generator(
            db=db,
            user_message=user_message,
            query_embedding=query_embedding,
            history=history,
            document_title=document_title,
        ):
            if event_type == "no_content":
                no_content_msg = (
                    "I don't have enough information in the knowledge base to answer that question."
                )
                assistant_msg = ChatMessage(
                    session_id=session.id,
                    role="assistant",
                    content=no_content_msg,
                    is_generated_content=False,
                )
                db.add(assistant_msg)
                session.last_active_at = datetime.now(timezone.utc)
                await db.commit()
                yield _sse_event("no_content", {"message": no_content_msg})
                yield _sse_event("done", {
                    "message_id": str(assistant_msg.id),
                    "session_id": str(session.id),
                    "source_documents": [],
                })
                return

            elif event_type == "chunk":
                text = data.get("text", "")
                assistant_content_parts.append(text)
                is_generated = data.get("is_generated_content", False)
                yield _sse_event("chunk", {"text": text, "is_generated_content": is_generated})

            elif event_type == "sources":
                source_documents = data.get("documents", [])

            elif event_type == "done":
                # Persist assistant message
                full_content = "".join(assistant_content_parts)
                assistant_msg = ChatMessage(
                    session_id=session.id,
                    role="assistant",
                    content=full_content,
                    is_generated_content=is_generated,
                    source_documents=source_documents,
                )
                db.add(assistant_msg)
                session.last_active_at = datetime.now(timezone.utc)
                await db.commit()
                yield _sse_event("done", {
                    "message_id": str(assistant_msg.id),
                    "session_id": str(session.id),
                    "source_documents": source_documents or [],
                })

    except Exception as exc:
        logger.exception("SSE stream error for session %s: %s", session.id, exc)
        yield _sse_event("error", {"message": "An error occurred processing your request."})


def _sse_event(event: str, data: dict) -> str:
    return f"event: {event}\ndata: {json.dumps(data)}\n\n"


# -----------------------------------------------------------------
# Internal helpers
# -----------------------------------------------------------------

async def _get_owned_session(
    session_id: uuid.UUID, user_id: uuid.UUID, db: AsyncSession
) -> ChatSession:
    session = await db.get(ChatSession, session_id)
    if session is None or session.user_id != user_id or session.deleted_at is not None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"error": "Session not found", "code": "SESSION_NOT_FOUND"},
        )
    return session
