# Research: RAG-Powered Chat Interface

**Phase 0 output for `005-rag-chat`**
**Date**: 2026-03-14

---

## Existing Implementation Audit

Most of this feature is already scaffolded. The work is gap-filling and bug-fixing rather than greenfield development.

### What is fully built and correct

| Component | File | Status |
|-----------|------|--------|
| Session CRUD endpoints | `src/api/chat.py` | Complete |
| RAG retrieval pipeline | `utils/rag.py` | Complete |
| SSE stream generator | `utils/rag.py::rag_stream_generator` | Complete |
| Embedding utility | `utils/embeddings.py::embed_text` | Complete |
| DB models | `src/models/chat_session.py`, `chat_message.py` | Complete |
| ChatWindow UI | `frontend/components/chat/ChatWindow.tsx` | Complete |
| MessageBubble UI | `frontend/components/chat/MessageBubble.tsx` | Complete |
| SourceDocs collapsible | `frontend/components/chat/SourceDocs.tsx` | Complete |
| SessionList sidebar | `frontend/components/chat/SessionList.tsx` | Complete |
| Chat session page | `frontend/app/(dashboard)/chat/[sessionId]/page.tsx` | Partially broken (see bugs) |
| Chat index redirect | `frontend/app/(dashboard)/chat/page.tsx` | BFF bypass bug |

---

## Bugs Found (must fix)

### BUG-001 — Frontend bypasses BFF proxy for SSE messages
**File**: `frontend/hooks/useChat.ts:37`
**What**: `useChat` calls `${NEXT_PUBLIC_API_URL}/api/v1/chat/...` directly — an internal cluster URL that is unreachable from the browser in production. The auth cookie (`auth-token`) is also not forwarded this way.
**Fix**: Change `fetch(${API_URL}/api/v1/...)` to `fetch('/api/v1/...')` to route through the Next.js BFF proxy at `app/api/v1/[...path]/route.ts`.

### BUG-002 — Frontend bypasses BFF proxy for server-side fetches
**Files**: `chat/page.tsx:17`, `chat/[sessionId]/page.tsx:25`
**What**: Both server components use `NEXT_PUBLIC_API_URL` directly. The BFF proxy reads the `auth-token` httpOnly cookie and adds `Authorization: Bearer`. Direct calls must manually pass the token via header — this pattern works today but is fragile.
**Fix**: Already works because the server components manually pass the cookie token as a header. This is acceptable for server-side fetches since the BFF proxy (`/api/v1/`) is only reachable internally from the Next.js server, and `NEXT_PUBLIC_API_URL` resolves to the internal service correctly server-side. **No change needed for server-side fetches.**

### BUG-003 — `[sessionId]/page.tsx` fetches a non-existent endpoint
**File**: `frontend/app/(dashboard)/chat/[sessionId]/page.tsx:25`
**What**: Calls `GET /api/v1/chat/sessions/${sessionId}/messages` — this endpoint does not exist. The actual endpoint is `GET /api/v1/chat/sessions/${sessionId}` which returns both session metadata and `messages`.
**Fix**: Change to `GET /chat/sessions/${sessionId}` and extract `data.data.messages`.

### BUG-004 — `useChat` sends wrong request body field
**File**: `frontend/hooks/useChat.ts:44`
**What**: `body: JSON.stringify({ content: text })` — but the backend `SendMessageRequest` model expects `{ message: string }`. This causes a 422 Unprocessable Entity on every send.
**Fix**: Change `content` to `message`.

### BUG-005 — `useChat` does not handle the `no_content` SSE event
**File**: `frontend/hooks/useChat.ts`
**What**: When the knowledge base has no relevant chunks, the backend emits `event: no_content` then `event: done`. The frontend only handles `chunk`, `done`, and `error`. The `no_content` event is silently skipped, but since the `done` that follows has empty payload, `isStreaming` stays `true` and no message is added — the UI hangs.
**Fix**: Handle `no_content` by adding the "no information found" message as an assistant message and ending the streaming state.

### BUG-006 — `useChat` expects `done` event to carry `message_id`, `session_id`, `source_documents`
**File**: `frontend/hooks/useChat.ts:83-95`, `lib/types.ts:107-111`
**What**: `useChat` reads `doneEvent.message_id`, `doneEvent.session_id`, `doneEvent.source_documents` from the `done` event. The backend currently sends `yield _sse_event("done", {})` with an empty payload. Source documents arrive in a preceding `sources` event (`event: sources`) that `useChat` never handles.
**Fix (two options, chose option A)**:
- **Option A (chosen)**: Update the backend `_sse_stream` to embed `message_id`, `session_id`, and `source_documents` in the `done` payload. Eliminates the separate `sources` event.
- Option B: Update the frontend to accumulate `sourceDocs` from the `sources` event and not rely on `done` for them.

**Decision**: Option A — a single `done` event carrying all terminal state is simpler and removes the ordering dependency between `sources` and `done`.

### BUG-007 — `SourceDocs` expects `chunk_text` and `similarity` fields not provided by backend
**File**: `frontend/components/chat/SourceDocs.tsx:39-42`, `frontend/lib/types.ts:95-99`
**What**: `SourceDoc` interface has `{ title, chunk_text, similarity }`. Backend `rag.py` emits `{ id, title, source_file }` — no `chunk_text`, no `similarity`.
**Fix**: Add `similarity` to the source_docs emitted by `rag.py`. Replace `chunk_text` with `source_file` in the `SourceDoc` type since we don't expose raw chunk text to the UI.

---

## Missing Features (must add)

### MISSING-001 — Session title auto-set from first user message
**Spec requirement**: FR from Assumption: "Session titles are automatically derived from the first user message"
**Current state**: Sessions are always created with `title=None` and display as "New conversation". No code ever updates the title.
**Fix**: In `send_message`, after persisting the first user message, update `session.title` to the first 60 characters of that message if `session.title` is null.

### MISSING-002 — Delete session UI
**Spec requirement**: FR-008
**Current state**: The `SessionList` component has no delete button. The `DELETE /chat/sessions/{id}` backend endpoint exists and works.
**Fix**: Add a delete icon/button per session item in `SessionList` with a confirmation step.

### MISSING-003 — Message length enforcement
**Spec requirement**: FR-011
**Current state**: No maximum message length is enforced on frontend or backend.
**Fix**: Enforce 4000 character maximum on both sides. Frontend: disable send + show counter warning. Backend: return 422 if `len(body.message) > 4000`.

---

## Decisions

| Decision | Choice | Rationale |
|----------|--------|-----------|
| SSE `done` event payload | Embed `message_id`, `session_id`, `source_documents` in `done` | Single terminal event, no ordering dependency |
| Source reference content | Show `source_file` path, not raw `chunk_text` | Chunk text is internal; file path gives provenance without leaking retrieval internals |
| Max message length | 4000 characters | Covers all realistic marketing queries; well under embedding model limits |
| Session auto-title length | First 60 characters of user message | Fits sidebar display; consistent with ChatGPT/Claude conventions |
| BFF bypass for server components | Keep current direct-backend pattern | Server components run server-side where `NEXT_PUBLIC_API_URL` is the internal URL — works correctly |
