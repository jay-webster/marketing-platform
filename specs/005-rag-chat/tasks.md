# Tasks: RAG-Powered Chat Interface

**Input**: Design documents from `/specs/005-rag-chat/`
**Prerequisites**: plan.md ✅ spec.md ✅ research.md ✅ data-model.md ✅ contracts/api.md ✅

**Context**: The feature is ~80% scaffolded. No new migrations, no new utility modules. All work is bug fixes and gap-filling in existing files. Tasks are organized so each user story can be validated independently.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: Which user story this task belongs to (US1–US4)

---

## Phase 1: Setup

**Purpose**: No new scaffolding required — codebase already has all models, utilities, routes, and UI components. This phase confirms readiness and resolves the naming conflict.

- [ ] T001 Rename `specs/005-nextjs-frontend` to `specs/004-nextjs-frontend` (or next available prefix) to resolve the duplicate-005 prefix warning from setup scripts

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Two bugs completely block all user stories. Must fix these before any story can be validated end-to-end.

**⚠️ CRITICAL**: Both tasks must be complete before any user story testing can begin.

- [ ] T002 Update `SourceDoc` interface in `frontend/lib/types.ts`: replace `chunk_text: string` with `source_file: string`; keep `title: string` and `similarity: number`
- [ ] T003 Update `SSEDoneEvent` interface in `frontend/lib/types.ts` to match contract: `{ message_id: string; session_id: string; source_documents: SourceDoc[] }`
- [ ] T004 Fix `useChat` BFF bypass in `frontend/hooks/useChat.ts`: change `fetch(\`${API_URL}/api/v1/chat/sessions/${sessionId}/messages\`, ...)` to `fetch(\`/api/v1/chat/sessions/${sessionId}/messages\`, ...)` and remove `credentials: "include"`
- [ ] T005 Fix `useChat` request body in `frontend/hooks/useChat.ts`: change `body: JSON.stringify({ content: text })` to `body: JSON.stringify({ message: text })`

**Checkpoint**: After T002–T005, the SSE fetch pipeline is correctly routed and typed. User story work can begin.

---

## Phase 3: User Story 1 — Ask a Question, Get a Grounded Answer (Priority: P1) 🎯 MVP

**Goal**: A logged-in user sends a question, receives a progressive streaming response drawn from the knowledge base, and sees the source documents that grounded the answer.

**Independent Test**: With one document indexed, open `/chat`, create a new session, type a question about that document's content, press Enter. Verify text streams in progressively and source references appear when streaming completes.

- [ ] T006 [P] [US1] Add `similarity` field to source_docs in `utils/rag.py` in `rag_stream_generator`: add `"similarity": round(c["similarity"], 4)` to each dict in the `source_docs` list
- [ ] T007 [P] [US1] Update `_sse_stream` in `src/api/chat.py` to accumulate `source_documents` from the `sources` event yielded by `rag_stream_generator`, then embed them in the `done` event payload: `_sse_event("done", {"message_id": str(assistant_msg.id), "session_id": str(session.id), "source_documents": source_documents or []})`
- [ ] T008 [US1] Remove the now-redundant standalone `yield _sse_event("sources", ...)` line from `_sse_stream` in `src/api/chat.py` (sources are now carried in the `done` payload per contracts/api.md)
- [ ] T009 [US1] Update `useChat` in `frontend/hooks/useChat.ts` to correctly handle the updated `done` event: verify `doneEvent.source_documents` is applied to the assistant `ChatMessage`; ensure `isStreaming` is set to `false` after this event

**Checkpoint**: User can send a message, watch it stream in, and see collapsed source references. Core value proposition works end-to-end.

---

## Phase 4: User Story 2 — Continue a Conversation Across Multiple Turns (Priority: P2)

**Goal**: A user asks a follow-up question and the response is coherent with prior context. Returning to a session shows full message history.

**Independent Test**: In an existing session with at least two prior turns, ask "can you elaborate on that?" — the response should reference the prior context. Reload the page and verify history is intact.

- [ ] T010 [US2] Fix `chat/[sessionId]/page.tsx`: change the server-side fetch from the non-existent `/chat/sessions/${sessionId}/messages` to `/chat/sessions/${sessionId}`, and extract `data.data.messages ?? []` for `initialMessages`

**Checkpoint**: Navigating to `/chat/{sessionId}` correctly loads prior history. Multi-turn context is already handled by the backend (last 20 messages passed to `rag_stream_generator`).

---

## Phase 5: User Story 4 — Handle Unanswerable Queries Gracefully (Priority: P2)

**Goal**: When no relevant knowledge base content exists for a query, the user sees an honest "no information found" message rather than a hanging stream or a hallucinated response.

**Independent Test**: Ask a question about a topic with no indexed documents (e.g., "what is the capital of France?"). Verify a clear "no information" message appears as an assistant bubble — not a blank screen, not a fabricated answer.

- [ ] T011 [P] [US4] Update `_sse_stream` in `src/api/chat.py` to include `message_id` and `session_id` in the `done` event that follows `no_content`: change `yield _sse_event("done", {})` in the `no_content` branch to `yield _sse_event("done", {"message_id": str(assistant_msg.id), "session_id": str(session.id), "source_documents": []})`
- [ ] T012 [US4] Add `no_content` SSE event handler to `useChat` in `frontend/hooks/useChat.ts`: on `eventType === "no_content"`, add an assistant `ChatMessage` to state with `content: payload.message`, set `isStreaming(false)`, and set `streamingText("")`

**Checkpoint**: Unanswerable queries produce a visible, honest response message. Stream never hangs.

---

## Phase 6: User Story 3 — Manage Chat Sessions (Priority: P3)

**Goal**: Users can see all their sessions in the sidebar, navigate between them, have sessions titled automatically from the first message, and delete sessions they no longer need.

**Independent Test**: Create two sessions with different first messages — verify each gets a distinct title in the sidebar. Delete one session; verify it disappears from the list and the other session is unaffected.

- [ ] T013 [P] [US3] Add session auto-title logic to `send_message` in `src/api/chat.py`: after persisting `user_msg`, if `session.title is None`, set `session.title = body.message[:60].strip()` and include it in the `db.commit()`
- [ ] T014 [P] [US3] Add `apiDelete` helper to `frontend/lib/api.ts` if not already present (check first): `export async function apiDelete(path: string)` that calls `apiFetch(path, { method: "DELETE" })`
- [ ] T015 [US3] Add per-session delete button to `SessionList` in `frontend/components/chat/SessionList.tsx`: show a trash icon (lucide `Trash2`) on hover for each session item; on click, call `window.confirm("Delete this conversation?")`, then `apiDelete(\`/api/v1/chat/sessions/${session.id}\`)`, invalidate `["chat-sessions"]` query, and if `activeSessionId === session.id` redirect to `/chat`

**Checkpoint**: Session sidebar shows auto-derived titles and a working delete control. Users can manage conversation history.

---

## Phase 7: Polish & Cross-Cutting Concerns

**Purpose**: Message length enforcement (FR-011) and backend tests spanning all stories.

- [ ] T016 [P] Add message length validation to `send_message` in `src/api/chat.py`: after the empty-message check, add `if len(body.message) > 4000: raise HTTPException(status_code=422, detail={"error": "Message exceeds 4000 character limit", "code": "MESSAGE_TOO_LONG"})`
- [ ] T017 [P] Add client-side message length guard to `ChatWindow` in `frontend/components/chat/ChatWindow.tsx`: disable the send button when `input.length > 4000`; show a character counter `text-destructive` below the textarea when within 200 characters of the limit
- [ ] T018 [P] Write backend test T-001 in `tests/api/test_chat.py`: happy-path send message — mock `embed_text` and `rag_stream_generator`; POST to `/chat/sessions/{id}/messages`; assert SSE stream includes `chunk` events and a `done` event with `message_id` and non-empty `source_documents`
- [ ] T019 [P] Write backend test T-002 in `tests/api/test_chat.py`: no-content path — mock `rag_stream_generator` to yield `("no_content", {})`; assert SSE includes `no_content` event followed by `done` with `message_id`
- [ ] T020 [P] Write backend test T-003 in `tests/api/test_chat.py`: empty message — POST `{"message": "   "}`; assert 422 response
- [ ] T021 [P] Write backend test T-004 in `tests/api/test_chat.py`: message too long — POST message of 4001 characters; assert 422 response with code `MESSAGE_TOO_LONG`
- [ ] T022 [P] Write backend test T-005 in `tests/api/test_chat.py`: auth isolation — create session as user A; attempt GET and POST as user B; assert 404 on both
- [ ] T023 [P] Write backend test T-006 in `tests/api/test_chat.py`: session auto-title — create untitled session; send first message with text "Hello, what is the Q3 report?"; assert `session.title == "Hello, what is the Q3 report?"`

---

## Dependencies & Execution Order

### Phase Dependencies

- **Phase 1 (Setup)**: No dependencies — can start immediately
- **Phase 2 (Foundational)**: Depends on Phase 1 — **BLOCKS all user stories**
- **Phase 3 (US1 — P1)**: Depends on Phase 2
- **Phase 4 (US2 — P2)**: Depends on Phase 2; independent of Phase 3
- **Phase 5 (US4 — P2)**: Depends on Phase 2; independent of Phases 3 and 4
- **Phase 6 (US3 — P3)**: Depends on Phase 2; independent of Phases 3–5
- **Phase 7 (Polish)**: Depends on all prior phases for full test coverage; T016/T017 can start after Phase 2

### User Story Dependencies

- **US1 (P1)**: Start after Phase 2 — no dependency on other stories
- **US2 (P2)**: Start after Phase 2 — no dependency on US1 (T010 is a standalone fix)
- **US4 (P2)**: Start after Phase 2 — no dependency on US1 or US2
- **US3 (P3)**: Start after Phase 2 — no dependency on any other story

### Parallel Opportunities Within Each Phase

- **Phase 2**: T002 and T003 are in the same file (`types.ts`) — sequential. T004 and T005 are both in `useChat.ts` — sequential. But `types.ts` changes (T002/T003) and `useChat.ts` changes (T004/T005) are in different files — parallel.
- **Phase 3**: T006 (`utils/rag.py`) and T007/T008 (`src/api/chat.py`) are in different files — T006 and T007 can start in parallel. T009 (`useChat.ts`) can start in parallel with T006/T007.
- **Phase 6**: T013 (`src/api/chat.py`) and T014/T015 (`frontend/`) — all in different files, fully parallel.
- **Phase 7**: All test tasks (T018–T023) are independent of each other — fully parallel.

---

## Parallel Example: Phase 3 (US1)

```text
# Can run simultaneously:
T006: Add similarity to utils/rag.py
T007+T008: Fix done event in src/api/chat.py
T009: Update done handler in frontend/hooks/useChat.ts
```

---

## Implementation Strategy

### MVP Scope (User Story 1 only)

1. Complete Phase 1: Setup (T001)
2. Complete Phase 2: Foundational (T002–T005) — **required before anything works**
3. Complete Phase 3: US1 (T006–T009)
4. **STOP and validate**: Send a question in chat, watch it stream, verify sources appear
5. Ship MVP — the core value proposition is live

### Incremental Delivery

1. Phase 2 complete → chat no longer sends 422 errors
2. Phase 3 complete → streaming works with source references ← **MVP milestone**
3. Phase 4 complete → session history loads correctly on page refresh
4. Phase 5 complete → unanswerable queries produce visible honest responses
5. Phase 6 complete → sessions have titles + delete button in sidebar
6. Phase 7 complete → message length guardrails + full test coverage

---

## Notes

- **No migrations required** — all schema changes are data-only (JSONB `similarity` field, session title population)
- **No new utility files** — all changes are in existing `src/api/chat.py`, `utils/rag.py`, and `frontend/` files
- **SourceDocs display**: After F-007 (T002), `SourceDocs.tsx` will render `doc.source_file` instead of `doc.chunk_text`. Verify the existing `SourceDocs` component renders correctly with the `source_file` field (the component currently reads `doc.chunk_text` on line 42 — update that reference too as part of T002)
