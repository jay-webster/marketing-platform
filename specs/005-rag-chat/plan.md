# Implementation Plan: RAG-Powered Chat Interface

**Branch**: `005-rag-chat` | **Date**: 2026-03-14 | **Spec**: [spec.md](./spec.md)
**Input**: Feature specification from `specs/005-rag-chat/spec.md`

---

## Summary

The RAG chat feature is largely already scaffolded — backend endpoints, RAG pipeline, SSE stream generator, and all frontend UI components exist. The remaining work is fixing seven contract mismatches between the frontend and backend that prevent the feature from working end-to-end, plus adding three missing capabilities (session auto-title, delete session UI, message length enforcement).

No new database migrations are required. No new utility modules are required.

---

## Technical Context

**Language/Version**: Python 3.11 (backend), TypeScript / Next.js 15 App Router (frontend)
**Primary Dependencies**: FastAPI + SQLAlchemy async (backend); React + TanStack Query (frontend); Anthropic SDK; Voyage AI embeddings; pgvector
**Storage**: PostgreSQL 16 + pgvector (`chat_sessions`, `chat_messages`, `content_chunks`)
**Testing**: pytest (backend), TypeScript type checking (frontend)
**Target Platform**: GCP GKE (backend), Vercel (frontend)
**Project Type**: Web application — full-stack
**Performance Goals**: First SSE token delivered within 3 seconds of message send (SC-001)
**Constraints**: Messages capped at 4000 characters; streaming must pass through NGINX with `proxy-buffering: off` (already configured in ingress.yaml)
**Scale/Scope**: Single-tenant deployment; ~20 concurrent users per client installation

---

## Constitution Check

| Principle | Status | Notes |
|-----------|--------|-------|
| **AUTH_SAFE** | PASS | All chat endpoints use `get_current_user` dependency. `_get_owned_session` enforces user ownership on every session access. |
| **DRY** | PASS | Reuses `utils/rag.py`, `utils/embeddings.py`, `utils/auth.py`, `utils/db.py`. No new utility modules required. |
| **NON_BLOCKING** | PASS | No local state. Sessions and messages stored in PostgreSQL. SSE streaming is stateless per-request. |
| **ERROR_HANDLING** | PASS | Global exception handler exists. SSE stream catches all exceptions and emits `error` event. |
| **IDEMPOTENT** | N/A | Chat messages are append-only; no sync operations in this feature. |
| **ADMIN_SECURITY** | N/A | No admin-only endpoints in this feature. |

---

## Project Structure

### Documentation (this feature)

```text
specs/005-rag-chat/
├── plan.md              ← This file
├── spec.md              ← Feature specification
├── research.md          ← Phase 0: bug audit + decisions
├── data-model.md        ← Phase 1: schema reference
├── contracts/
│   └── api.md           ← Phase 1: endpoint + SSE event contracts
└── tasks.md             ← Phase 2 output (/speckit.tasks — not created here)
```

### Source Code (files to be modified)

```text
src/api/chat.py                                    ← Backend: 3 bug fixes + 2 new behaviours
utils/rag.py                                       ← Backend: add similarity to source_docs
frontend/hooks/useChat.ts                          ← Frontend: 3 bug fixes
frontend/app/(dashboard)/chat/[sessionId]/page.tsx ← Frontend: 1 bug fix
frontend/components/chat/SessionList.tsx           ← Frontend: add delete UI
frontend/lib/types.ts                              ← Frontend: update SourceDoc type
tests/api/test_chat.py                             ← Backend: new + updated tests
```

---

## Work Items

### Backend — `src/api/chat.py`

**B-001: Embed sources + message_id in `done` SSE event**
- In `_sse_stream`, accumulate `source_documents` from the `sources` event emitted by `rag_stream_generator`
- On `done`, yield: `_sse_event("done", {"message_id": str(assistant_msg.id), "session_id": str(session.id), "source_documents": source_documents or []})`
- Remove the separate `yield _sse_event("sources", ...)` line (the sources are now in `done`)

**B-002: Fix `no_content` SSE sequence**
- After persisting the no-content assistant message, yield `no_content` event then `done` event with `message_id` and `session_id`
- Currently `done` is yielded with `{}` — update to include message_id/session_id here too

**B-003: Add message length validation**
- In `send_message`: after the empty-check, add `if len(body.message) > 4000: raise HTTPException(422, ...)`

**B-004: Auto-set session title from first user message**
- In `send_message`, after persisting `user_msg`: if `session.title is None`, set `session.title = body.message[:60].strip()` and commit

### Backend — `utils/rag.py`

**B-005: Add `similarity` field to emitted source_docs**
- In `rag_stream_generator`, the `source_docs` list currently omits `similarity`
- Add `"similarity": round(c["similarity"], 4)` to each source doc dict

### Frontend — `frontend/hooks/useChat.ts`

**F-001: Route SSE fetch through BFF proxy**
- Change `fetch(\`${API_URL}/api/v1/chat/sessions/${sessionId}/messages\`, ...)` to `fetch(\`/api/v1/chat/sessions/${sessionId}/messages\`, ...)`
- Remove `credentials: "include"` (BFF handles auth via server-side cookie read)

**F-002: Fix request body field name**
- Change `body: JSON.stringify({ content: text })` to `body: JSON.stringify({ message: text })`

**F-003: Handle `no_content` SSE event**
- Add `else if (eventType === "no_content")` branch: extract `payload.message`, add it as an assistant `ChatMessage` to state, set `isStreaming(false)`

**F-004: Handle `done` event with new payload**
- `doneEvent` now has `{ message_id, session_id, source_documents }` — existing code already reads these fields; will work once B-001 is implemented
- Verify `source_documents` are correctly applied to the assistant message

### Frontend — `frontend/app/(dashboard)/chat/[sessionId]/page.tsx`

**F-005: Fix initial message load endpoint**
- Change `/chat/sessions/${sessionId}/messages` to `/chat/sessions/${sessionId}`
- Update extraction: `data.data.messages ?? []` → already matches backend `get_session` response shape

### Frontend — `frontend/components/chat/SessionList.tsx`

**F-006: Add delete session button**
- Add a trash icon button per session row (visible on hover)
- On click, confirm with `window.confirm()`, call `apiDelete('/api/v1/chat/sessions/${session.id}')`, invalidate `["chat-sessions"]` query
- If deleted session is the active session, redirect to `/chat`

### Frontend — `frontend/lib/types.ts`

**F-007: Update `SourceDoc` and `SSEDoneEvent` interfaces**
- `SourceDoc`: replace `chunk_text: string` with `source_file: string`; keep `title: string` and `similarity: number`
- `SSEDoneEvent`: verify fields match `{ message_id, session_id, source_documents: SourceDoc[] }`

### Tests — `tests/api/test_chat.py`

**T-001: Happy-path send message test** — mock `embed_text` and `rag_stream_generator`; verify SSE events include `done` with `message_id`
**T-002: No-content path test** — mock `rag_stream_generator` to yield `no_content`; verify correct SSE sequence
**T-003: Empty message validation** — POST empty string; expect 422
**T-004: Message too long validation** — POST 4001-char string; expect 422
**T-005: Auth isolation** — attempt to read/send to another user's session; expect 404
**T-006: Session auto-title** — send first message to untitled session; verify `session.title` is set

---

## Implementation Order

These items have no dependencies between backend and frontend groups and can be implemented in parallel, but within each group follow the order below:

**Backend (in order)**:
1. B-005 (`utils/rag.py` — add similarity) — no dependencies
2. B-001 (embed sources in `done`) — depends on B-005
3. B-002 (fix `no_content` sequence) — independent
4. B-003 (message length validation) — independent
5. B-004 (auto-title) — independent

**Frontend (in order)**:
1. F-007 (update types) — must be first; other frontend changes depend on correct types
2. F-001 + F-002 + F-003 + F-004 (fix useChat) — after types
3. F-005 (fix page endpoint) — independent
4. F-006 (delete session UI) — independent

**Tests**: After all backend items complete.

---

## Complexity Tracking

No constitution violations. All work is within existing modules.
