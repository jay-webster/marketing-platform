# Tasks: Epic 4 — Agentic Chat Interface (RAG)

**Feature**: Agentic Chat Interface (RAG)
**Branch**: `4-rag-chat`
**Plan**: `specs/4-rag-chat/plan.md`
**Spec**: `specs/4-rag-chat/spec.md`
**Generated**: 2026-03-13

---

## User Story Index

| Story | Scenario | Description | Priority |
|-------|----------|-------------|----------|
| US1 | Scenario 1 | Query Existing Content — basic RAG Q&A with source attribution | P1 |
| US2 | Scenario 2 | Follow-Up Questions — conversation history maintained within session | P1 |
| US3 | Scenario 3 | Content Generation — grounded new content (posts, copy, briefs) | P2 |
| US4 | Scenario 4 | No Relevant Content — graceful decline with actionable suggestion | P1 |
| US5 | Scenario 5 | Content Variation — refinements to generated content within session | P2 |
| US6 | Scenario 6 | Named Document Targeting — "based only on [document name]" | P3 |
| US7 | Scenario 7 | Copy Generated Content — clipboard copy (frontend only, no backend) | P3 |
| US8 | Scenario 8 | Knowledge Base Indexing — auto-index approved documents within 5 min | P1 |
| US9 | Scenario 9 | Session History — list, resume, and delete prior sessions | P2 |

> **US7 note**: Copy-to-clipboard (Scenario 7, FR-3.8) is a pure frontend concern. No backend endpoint is required — the response content is already delivered via SSE. No backend task generated.

---

## Phase 1: Setup

*Project initialization. No dependencies. All three tasks parallelizable.*

- [X] T001 [P] Add `openai>=1.0` (text-embedding-3-small) and `pgvector` (pgvector-python SQLAlchemy integration) to `marketing-platform/requirements.txt`
- [X] T002 [P] Add 6 new settings to `marketing-platform/src/config.py` `Settings` class: `OPENAI_API_KEY: str`, `KB_SIMILARITY_THRESHOLD: float = 0.3`, `KB_RETRIEVAL_TOP_K: int = 6`, `CHAT_MODEL: str = "claude-opus-4-6"`, `CHAT_MAX_TOKENS: int = 1024`, `KB_INDEX_CONCURRENCY: int = 2`
- [X] T003 [P] Add `OPENAI_API_KEY=`, `KB_SIMILARITY_THRESHOLD=0.3`, `KB_RETRIEVAL_TOP_K=6`, `CHAT_MODEL=claude-opus-4-6`, `CHAT_MAX_TOKENS=1024`, `KB_INDEX_CONCURRENCY=2` entries with comments to `marketing-platform/.env.example`

---

## Phase 2: Foundation — Models & Migration

*Blocking prerequisite for all user stories. T004–T007 are parallelizable. T008 depends on T004–T007. T009 depends on T008.*

- [X] T004 [P] Create `marketing-platform/src/models/chat_session.py` — `ChatSession` SQLAlchemy model with columns: `id UUID PK`, `user_id UUID FK→users ON DELETE CASCADE`, `title TEXT nullable` (auto-set from first message, max 80 chars), `created_at TIMESTAMPTZ DEFAULT now()`, `last_active_at TIMESTAMPTZ DEFAULT now()`, `deleted_at TIMESTAMPTZ nullable`; indexes: `idx_chat_sessions_user_id ON (user_id)`, partial `idx_chat_sessions_user_active ON (user_id, last_active_at DESC) WHERE deleted_at IS NULL`
- [X] T005 [P] Create `marketing-platform/src/models/chat_message.py` — `ChatMessage` SQLAlchemy model with columns: `id UUID PK`, `session_id UUID FK→chat_sessions ON DELETE CASCADE`, `role TEXT NOT NULL CHECK (role IN ('user', 'assistant'))`, `content TEXT NOT NULL`, `is_generated_content BOOLEAN NOT NULL DEFAULT FALSE`, `source_documents JSONB nullable` (array of `{id, title, source_file}` objects), `created_at TIMESTAMPTZ DEFAULT now()`; index: `idx_chat_messages_session_id ON (session_id, created_at ASC)`
- [X] T006 [P] Create `marketing-platform/src/models/knowledge_base_document.py` — `KBIndexStatus` string enum (`queued`, `indexing`, `indexed`, `failed`, `removed`); `KnowledgeBaseDocument` model: `id UUID PK`, `processed_document_id UUID UNIQUE FK→processed_documents ON DELETE CASCADE`, `index_status TEXT NOT NULL DEFAULT 'queued'`, `failure_reason TEXT nullable`, `chunk_count INT nullable`, `indexed_at TIMESTAMPTZ nullable`, `removed_at TIMESTAMPTZ nullable`, `created_at TIMESTAMPTZ DEFAULT now()`, `updated_at TIMESTAMPTZ DEFAULT now()`; partial index: `idx_kb_documents_status ON (index_status) WHERE index_status = 'queued'`; partial index: `idx_kb_documents_indexed ON (indexed_at DESC) WHERE index_status = 'indexed'`
- [X] T007 [P] Create `marketing-platform/src/models/content_chunk.py` — import `Vector` from `pgvector.sqlalchemy`; `ContentChunk` model: `id UUID PK`, `knowledge_base_document_id UUID FK→knowledge_base_documents ON DELETE CASCADE`, `chunk_index INT NOT NULL` (0-based position), `content_text TEXT NOT NULL` (frontmatter + section text), `embedding Vector(1536) NOT NULL`, `metadata JSONB NOT NULL DEFAULT '{}'` (parsed frontmatter dict), `created_at TIMESTAMPTZ DEFAULT now()`; indexes: `idx_content_chunks_kb_doc_id ON (knowledge_base_document_id)` plus HNSW vector index (created in migration via raw SQL, not ORM)
- [X] T008 Update `marketing-platform/src/models/__init__.py` to import and export `ChatSession`, `ChatMessage`, `KnowledgeBaseDocument`, `KBIndexStatus`, `ContentChunk`
- [X] T009 Create `marketing-platform/migrations/versions/005_create_rag_tables.py` — `upgrade()`: (1) `op.execute("CREATE EXTENSION IF NOT EXISTS vector")` (2) create `chat_sessions` table with all columns and indexes (3) create `chat_messages` table with all columns and index (4) create `knowledge_base_documents` table with all columns and partial indexes (5) create `content_chunks` table with all columns (6) `op.execute("CREATE INDEX idx_content_chunks_embedding ON content_chunks USING hnsw (embedding vector_cosine_ops) WITH (m=24, ef_construction=64)")` (7) `op.execute("CREATE INDEX idx_content_chunks_kb_doc_id ON content_chunks (knowledge_base_document_id)")`; `downgrade()`: drop tables in reverse order, `DROP EXTENSION IF EXISTS vector`

---

## Phase 3: Foundation — Utilities

*Depends on Phase 2. T010–T012 parallelizable. T013 depends on T010+T011. T014 depends on T013.*

- [X] T010 [P] Create `marketing-platform/utils/embeddings.py` — module-level `AsyncOpenAI` singleton (lazy-initialized, reads `settings.OPENAI_API_KEY`); `async def embed_text(text: str) -> list[float]`: call `client.embeddings.create(model="text-embedding-3-small", input=text)`, return `data[0].embedding`; `async def embed_batch(texts: list[str]) -> list[list[float]]`: call with `input=texts` (up to 100 per call); retry on `openai.RateLimitError` with exponential backoff (max 3 retries); log errors with `request_id`-style prefix
- [X] T011 [P] Create `marketing-platform/utils/chunker.py` — `def chunk_markdown(content: str, max_tokens: int = 512, overlap_tokens: int = 50) -> list[dict]`: (1) extract YAML frontmatter with `re.match(r'^---\n(.*?)\n---\n', content, re.DOTALL)` and `yaml.safe_load()`; store `frontmatter_raw` string and `frontmatter_dict`; (2) strip frontmatter from body; (3) split body on `\n(?=## )` regex to get sections; (4) for each non-empty section: prepend `frontmatter_raw` to get `chunk_text`; estimate tokens as `len(chunk_text) // 4`; if ≤ `max_tokens`: append `{"text": chunk_text, "metadata": frontmatter_dict, "chunk_index": i}`; if > `max_tokens`: sliding-window split at paragraph boundaries with `overlap_tokens` overlap, append each sub-chunk with incrementing `chunk_index`; (5) if no `##` sections found (flat document): treat entire body as one section and apply overflow splitting; return list of chunk dicts
- [X] T012 [P] Create `marketing-platform/utils/rag.py` — define `CONSTRAINED_SYSTEM_PROMPT` string constant (per research.md Decision 4: answer only from retrieved context, decline when insufficient, label generated content, never fabricate); define `GENERATION_KEYWORDS = {"write", "generate", "create", "draft", "compose", "produce"}`; `async def retrieve_chunks(query_embedding: list[float], db: AsyncSession, top_k: int, threshold: float) -> list[dict]`: execute pgvector query `SELECT id, content_text, metadata, 1-(embedding <=> :emb) AS similarity FROM content_chunks WHERE 1-(embedding <=> :emb) > :threshold ORDER BY embedding <=> :emb LIMIT :top_k` using `text()` with `SET LOCAL hnsw.ef_search = 100`; return list of `{id, content_text, metadata, similarity}`; `def build_prompt(query: str, chunks: list[dict], history: list[dict]) -> list[dict]`: assemble messages array with history (last 10 messages) + context block + user message; `async def rag_stream_generator(...)`: full SSE generator function (see architecture in plan.md) — embed query, retrieve, build prompt, stream with `AsyncAnthropic.messages.stream()`, emit delta/no_content/sources/done/error SSE events, detect generation intent from `GENERATION_KEYWORDS`
- [X] T013 Create `marketing-platform/utils/indexer.py` — `async def index_document(kb_doc_id: uuid.UUID) -> None`: (1) open `AsyncSessionLocal`; (2) load `KnowledgeBaseDocument` row, set `index_status = 'indexing'`, commit; (3) load `ProcessedDocument.markdown_content` via FK; (4) call `chunk_markdown(markdown_content)` from `utils/chunker.py`; (5) call `embed_batch([c["text"] for c in chunks])` from `utils/embeddings.py`; (6) delete existing `ContentChunk` rows for this `kb_doc_id`; (7) bulk insert new `ContentChunk` rows with `content_text`, `embedding`, `metadata`, `chunk_index`; (8) update `KnowledgeBaseDocument`: `index_status='indexed'`, `chunk_count=len(chunks)`, `indexed_at=now()`; (9) `write_audit("kb_document_indexed", target_id=kb_doc_id, metadata={"chunk_count": len(chunks)})`; (10) on any exception: set `index_status='failed'`, `failure_reason=str(exc)`, `write_audit("kb_document_failed", ...)`
- [X] T014 Extend `marketing-platform/utils/queue.py` — add `_indexing_worker(worker_id: int)`: poll `knowledge_base_documents WHERE index_status='queued' ORDER BY created_at LIMIT 1 FOR UPDATE SKIP LOCKED`; mark `indexing`; call `await index_document(doc.id)` from `utils/indexer.py`; sleep 2s when queue empty; catches and logs all exceptions without exiting loop; add `start_indexing_workers(concurrency: int)` and `stop_indexing_workers()` functions that follow the same pattern as the existing `start_queue_workers/stop_queue_workers`

---

## Phase 4: US8 — Knowledge Base Indexing

*Goal*: When a document is approved in Epic 3, it is automatically queued for indexing. Within 5 minutes it is searchable. When a document is flagged for reprocessing, it is immediately removed from the knowledge base.

*Independent test*: Approve a document → `knowledge_base_documents` row created with `index_status=queued`. After worker runs → `index_status=indexed`, `content_chunks` rows exist. Flag for reprocessing → `index_status=removed`, `content_chunks` deleted.

- [X] T015 [US8] Modify `marketing-platform/src/api/ingestion.py` `review_document()` endpoint — in the `approved` branch: after updating `ProcessedDocument.review_status`, UPSERT `KnowledgeBaseDocument` (INSERT if not exists, UPDATE `index_status='queued'`, `removed_at=null` if exists with status=removed; use `INSERT ... ON CONFLICT (processed_document_id) DO UPDATE`); call `await write_audit("kb_document_queued", target_id=doc_id, metadata={"processed_document_id": str(pd.id)})`; in the `flagged_for_reprocessing` branch: after deleting the `ProcessedDocument` row, also call `await remove_document(kb_doc_id)` from `utils/indexer.py` (add `remove_document` function to `utils/indexer.py`: delete all `ContentChunk` rows for the KB doc, update `KnowledgeBaseDocument.index_status='removed'`, `removed_at=now()`, `write_audit("kb_document_removed", ...)`)
- [X] T016 [US8] Modify `marketing-platform/src/main.py` `_lifespan()` — import `start_indexing_workers`, `stop_indexing_workers` from `utils.queue`; after `await start_queue_workers(...)`: call `await start_indexing_workers(concurrency=settings.KB_INDEX_CONCURRENCY)`; after `await stop_queue_workers()`: call `await stop_indexing_workers()`
- [X] T017 [P] [US8] Create `marketing-platform/tests/utils/test_chunker.py` — `test_chunk_flat_document` (no headings → single chunk returned); `test_chunk_with_sections` (two `##` sections → two chunks); `test_chunk_frontmatter_prepended` (frontmatter present → every chunk starts with `---`); `test_chunk_overflow_splits` (section > 512-token threshold → multiple sub-chunks); `test_chunk_empty_sections_skipped` (blank section between headings → not included in output); `test_chunk_metadata_extracted` (frontmatter with `title: Q1 Brief` → `chunk["metadata"]["title"] == "Q1 Brief"`)
- [X] T018 [P] [US8] Create `marketing-platform/tests/utils/test_indexer.py` — mock `utils.embeddings.embed_batch` to return fixed-length vectors; mock `utils.audit.write_audit`; `test_index_document_creates_chunks` (valid markdown → `index_status=indexed`, `content_chunks` rows present, `chunk_count` matches); `test_index_document_replaces_existing_chunks` (re-index same doc → old chunks deleted, new chunks inserted, no duplicates); `test_index_document_marks_failed_on_error` (embed_batch raises → `index_status=failed`, `failure_reason` set); `test_remove_document_deletes_chunks_and_marks_removed` (indexed doc → after remove_document: chunks gone, `index_status=removed`)

---

## Phase 5: US1 + US4 — Basic RAG Query & No-Content Handling

*Goal*: Authenticated users submit a question; the platform retrieves relevant approved chunks via pgvector and streams a source-grounded answer. When no relevant content exists, a clear decline response is streamed with an actionable suggestion.

*Independent test*: `POST /chat/sessions` → 201 with `session_id`. `POST /chat/sessions/{id}/messages` with a question → SSE stream with `delta` events followed by `sources` and `done`. Same endpoint with query matching no chunks → `no_content` SSE event (no `delta` events). Unauthenticated → 401.

- [X] T019 [US1] Create `marketing-platform/src/api/chat.py` — `APIRouter(prefix="/chat", tags=["chat"])`; implement `POST /sessions`: `Depends(get_current_user)`; create `ChatSession(user_id=user.id)`; commit; return 201 with `session_id`, `title=null`, `created_at`, `last_active_at`; implement `POST /sessions/{session_id}/messages`: `Depends(get_current_user)`; request body `{"content": str}` (Pydantic model, `min_length=1`, `max_length=2000`); verify session exists and `session.user_id == current_user.id` (404 `SESSION_NOT_FOUND` if not); validate content length (400 `MESSAGE_TOO_LONG` if > 2000, 400 `MESSAGE_EMPTY` if blank); persist user `ChatMessage`; if session has no title yet: set `session.title = content[:80]`; update `session.last_active_at = now()`; commit; call `rag_stream_generator(query=content, session_id=session_id, user_id=user.id, db=db, settings=settings)` from `utils.rag`; return `StreamingResponse(generator, media_type="text/event-stream", headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})`
- [X] T020 [US4] Add no-content SSE path to `marketing-platform/utils/rag.py` `rag_stream_generator()` — after `retrieve_chunks()` returns: if result list is empty OR all similarities below `settings.KB_SIMILARITY_THRESHOLD`: yield `data: {"type": "no_content", "suggestion": "No approved content found on this topic. To enable this, approve documents covering this subject through the ingestion workflow."}\n\n`; persist assistant `ChatMessage(content=suggestion, is_generated_content=False, source_documents=None)`; yield `data: {"type": "done", "message_id": str(msg.id), "is_generated_content": false}\n\n`; return (do not proceed to generation)
- [X] T021 [US1] Mount `chat_router` in `marketing-platform/src/main.py` `create_app()` — import `router as chat_router` from `src.api.chat`; `application.include_router(chat_router, prefix="/api/v1")`
- [X] T022 [P] [US1] Create `marketing-platform/tests/api/test_chat.py` — mock `utils.embeddings.embed_text` to return `[0.1] * 1536`; mock `utils.rag.retrieve_chunks` to return 2 stub chunks; mock `AsyncAnthropic.messages.stream` to yield stub text tokens; mock `utils.queue.start_indexing_workers/stop_indexing_workers` as AsyncMock; `test_create_session_happy_path` (POST /chat/sessions → 201, session_id present); `test_create_session_unauthenticated` → 401; `test_send_message_unauthenticated` → 401; `test_send_message_wrong_session_returns_404` (session owned by different user → 404); `test_send_message_deleted_session_returns_404` (soft-deleted session → 404); `test_send_message_too_long` (2001 chars → 400 `MESSAGE_TOO_LONG`); `test_send_message_streams_sse` (valid message → response content-type text/event-stream, contains `"type": "delta"` and `"type": "done"`); `test_session_title_set_from_first_message` (first message → session.title == content[:80])
- [X] T023 [P] [US4] Add `test_no_content_response` to `marketing-platform/tests/api/test_chat.py` — mock `retrieve_chunks` to return `[]`; send message → SSE stream contains event `{"type": "no_content"}` and does NOT contain `{"type": "delta"}`; verify assistant ChatMessage persisted with `source_documents=null`

---

## Phase 6: US2 — Follow-Up Questions / Conversation Context

*Goal*: Follow-up questions reference prior exchanges without the user restating context. The platform injects the session's conversation history into the prompt automatically.

*Independent test*: Session with 2 prior messages (user + assistant) → 3rd `POST /messages` call includes history in the Claude API invocation (captured via mock). The AI does not re-retrieve chunks when context is already available.

- [X] T024 [US2] Modify `marketing-platform/utils/rag.py` `rag_stream_generator()` — before calling `build_prompt()`: load the last 10 `ChatMessage` rows for `session_id` from DB (excluding the just-inserted user message), ordered by `created_at ASC`; pass as `history: list[dict]` to `build_prompt()`; in `build_prompt()`: prepend history messages as `[{"role": msg.role, "content": msg.content}, ...]` before the user message in the `messages` array sent to Claude — this lets Claude interpret follow-ups in context without re-retrieval; cap total history at 10 messages to bound context window
- [X] T025 [P] [US2] Add `test_follow_up_includes_history` to `marketing-platform/tests/api/test_chat.py` — seed a session with 1 prior user message + 1 assistant message in DB; mock `AsyncAnthropic.messages.stream` and capture the `messages` argument; send a 2nd user message; assert the captured messages array includes the prior user and assistant messages before the new user message

---

## Phase 7: US3 — Content Generation

*Goal*: Users request new marketing content (posts, email copy, briefs). The AI generates it grounded in retrieved approved content. Generated responses are labeled `is_generated_content=true`.

*Independent test*: Message starting with "Write a LinkedIn post..." → SSE `done` event has `is_generated_content=true`. Persisted `ChatMessage` has `is_generated_content=true` and `source_documents` populated.

- [X] T026 [US3] Modify `marketing-platform/utils/rag.py` — update `rag_stream_generator()`: after collecting the full streamed response text, detect generation intent by checking if any word in `GENERATION_KEYWORDS` appears (case-insensitive) in the user's query; set `is_generated = True` if detected; persist assistant `ChatMessage(content=full_response, is_generated_content=is_generated, source_documents=[...])`; update the `done` SSE event payload to include `"is_generated_content": is_generated`; update `CONSTRAINED_SYSTEM_PROMPT` to explicitly instruct Claude to label generated content in its response with a standard prefix (e.g. `[AI-GENERATED]`) when `is_generated` mode is active — keep the label in the content field
- [X] T027 [P] [US3] Add generation tests to `marketing-platform/tests/api/test_chat.py` — `test_generation_request_labeled` (message "Write a LinkedIn post about our product launch" → done event `is_generated_content=true`); `test_retrieval_answer_not_labeled` (message "What are our key messages?" → done event `is_generated_content=false`); `test_generated_message_persisted_with_flag` (verify DB `ChatMessage.is_generated_content=true` after generation request); `test_generated_message_includes_sources` (generation response → `source_documents` JSONB populated on persisted message)

---

## Phase 8: US5 — Content Variation

*Goal*: Users refine generated content within the same session ("make it shorter", "make it more formal"). The AI applies constraints using the conversation history already in scope — no new code required beyond US2 and US3.

*Independent test*: Session with prior generated response → follow-up "make it under 100 words" → response uses conversation history context; `is_generated_content=true`.

- [X] T028 [P] [US5] Add `test_content_variation_uses_history` to `marketing-platform/tests/api/test_chat.py` — seed session with a prior assistant message (simulating a generated LinkedIn post); send "Now make it shorter and more formal"; assert messages array passed to Claude includes the prior generated message; assert done event has `is_generated_content=true`

---

## Phase 9: US9 — Session History

*Goal*: Users can list all their active sessions (most recent first), open a prior session to view its full message history, resume it with a new message, or delete it.

*Independent test*: `GET /chat/sessions` returns user's active sessions only (not deleted, not other users'). `GET /chat/sessions/{id}` returns session with messages array. `DELETE /chat/sessions/{id}` soft-deletes → session disappears from list. Other user's session returns 404.

- [X] T029 [US9] Add `GET /sessions`, `GET /sessions/{session_id}`, and `DELETE /sessions/{session_id}` to `marketing-platform/src/api/chat.py` — `GET /sessions`: `Depends(get_current_user)`; query `chat_sessions WHERE user_id=user.id AND deleted_at IS NULL ORDER BY last_active_at DESC`; support `limit` (default 20, max 100) and `offset` (default 0) query params; join-count messages for `message_count`; return list response per `contracts/api-endpoints.md`; `GET /sessions/{session_id}`: verify ownership (404 `SESSION_NOT_FOUND`); load all `chat_messages` for session ordered by `created_at ASC`; return session + messages array; `DELETE /sessions/{session_id}`: verify ownership (404); set `session.deleted_at = now()`; commit; `write_audit("chat_session_deleted", actor_id=user.id, target_id=session_id)`; return 200 `{"data": {"session_id": ..., "deleted": true}}`
- [X] T030 [P] [US9] Add session history tests to `marketing-platform/tests/api/test_chat.py` — `test_list_sessions_returns_own_sessions_only` (2 sessions for user A, 1 for user B → user A sees 2); `test_list_sessions_excludes_deleted` (soft-deleted session → not in list); `test_list_sessions_unauthenticated` → 401; `test_get_session_with_messages` (session with 2 messages → messages array length 2, correct roles); `test_get_session_other_user_returns_404`; `test_delete_session_soft_deletes` (DELETE → 200, `deleted_at` set in DB); `test_delete_then_list_excludes_session`; `test_deleted_session_rejects_new_messages` (POST /messages to deleted session → 404)

---

## Phase 10: US6 — Named Document Targeting

*Goal*: Users can restrict generation to a specific named approved document ("based only on the Q3 Campaign Brief"). If the document is not found, the AI states this rather than substituting silently.

*Independent test*: Message "Based only on Q1 Launch Brief, write a summary" → `retrieve_chunks()` filters by `metadata->>'title' ILIKE '%Q1 Launch Brief%'`. If no match: no_content event with named-doc-specific message. If match: only chunks from that document used.

- [X] T031 [US6] Modify `marketing-platform/utils/rag.py` `rag_stream_generator()` — before calling `retrieve_chunks()`: detect named document pattern with `re.search(r'based only on[:\s]+["\']?(.+?)["\']?[\.,]', query, re.IGNORECASE)`; if detected: set `named_doc = match.group(1).strip()`; pass `named_doc` to `retrieve_chunks()`; in `retrieve_chunks()`: if `named_doc` provided: add `AND metadata->>'title' ILIKE :title_pattern` (using `%{named_doc}%`) to the pgvector query; if result is empty: emit `no_content` SSE event with `suggestion=f"Named document '{named_doc}' was not found in approved content. Check the document title or approve it through the ingestion workflow."` rather than the generic no-content message
- [X] T032 [P] [US6] Add `test_named_document_targeting` to `marketing-platform/tests/api/test_chat.py` — mock `retrieve_chunks` to capture the `named_doc` argument; `test_named_doc_pattern_detected` (message "Based only on Q1 Brief, write a summary" → retrieve_chunks called with `named_doc="Q1 Brief"`); `test_named_doc_not_found_emits_specific_message` (retrieve_chunks returns [] with named_doc set → no_content suggestion includes the document name); `test_message_without_pattern_uses_unrestricted_retrieval` (generic question → retrieve_chunks called with `named_doc=None`)

---

## Phase 11: Admin KB Management & Polish

*Cross-cutting. Complete after all user story phases pass their independent tests.*

- [X] T033 [P] Create `marketing-platform/src/api/knowledge_base.py` — `APIRouter(prefix="/admin/knowledge-base", tags=["knowledge-base"])`; helper `_verify_admin_token(request: Request)` that checks `request.headers.get("X-Admin-Token")` against `settings.ADMIN_TOKEN` and raises `HTTPException(403)` if missing or invalid; `GET /status`: `Depends(get_current_user)` + `Depends(_verify_admin_token)`; query `knowledge_base_documents` for aggregate counts (`total_indexed_documents`, `documents_queued_for_indexing`, `documents_failed`); query `MAX(indexed_at)` for `last_indexed_at`; return response per `contracts/api-endpoints.md`; `POST /reindex`: `Depends(get_current_user)` + `Depends(_verify_admin_token)`; in a transaction: (1) delete all `content_chunks` rows; (2) UPDATE `knowledge_base_documents SET index_status='queued', indexed_at=null, chunk_count=null, removed_at=null WHERE processed_document_id IN (SELECT id FROM processed_documents WHERE review_status='approved')`; commit; `write_audit("kb_full_reindex_triggered", actor_id=user.id, metadata={"documents_queued": count})`; return 202 with `documents_queued` count
- [X] T034 Mount `kb_router` in `marketing-platform/src/main.py` `create_app()` — import `router as kb_router` from `src.api.knowledge_base`; `application.include_router(kb_router, prefix="/api/v1")`
- [X] T035 [P] Create `marketing-platform/tests/api/test_knowledge_base.py` — mock `utils.queue.start_indexing_workers/stop_indexing_workers`; `test_kb_status_requires_auth` (no bearer token → 401); `test_kb_status_requires_admin_token` (valid auth, no X-Admin-Token → 403); `test_kb_status_happy_path` (admin auth + X-Admin-Token → 200, response contains `total_indexed_documents`); `test_reindex_requires_auth` → 401; `test_reindex_requires_admin_token` → 403; `test_reindex_happy_path` (seeded indexed KB doc → 202, `documents_queued=1`, `knowledge_base_documents.index_status=queued`); `test_reindex_deletes_existing_chunks` (seeded content_chunks → after reindex, `content_chunks` table empty)
- [X] T036 Add `nginx.ingress.kubernetes.io/proxy-buffering: "off"` annotation to `marketing-platform/infra/k8s/base/` ingress manifest (required for SSE streaming to work through GKE nginx ingress — without this, SSE responses are buffered until the stream closes, defeating real-time streaming)

---

## Dependency Graph

```
T001–T003 (Setup — parallel)
    │
    ▼
T004–T007 (Models — parallel)
    │
    ▼
T008 → T009 (Export models, migration)
    │
    ├──► T010 (utils/embeddings.py)   ─┐
    ├──► T011 (utils/chunker.py)      ─┤
    └──► T012 (utils/rag.py)          ─┤
                                       ▼
                                     T013 (utils/indexer.py)
                                       │
                                     T014 (queue.py extension)
                                       │
                      ┌────────────────┤
                      ▼                │
         Phase 4: US8 (T015–T018)      │
         T015, T016                    │
         T017 [P], T018 [P]           │
                      │                │
                      ▼                │
         Phase 5: US1+US4 (T019–T023)  │
         T019 → T020 → T021           │
         T022 [P], T023 [P]           │
                      │                │
              ┌───────┴──────┐         │
              ▼              ▼         │
    Phase 6: US2     Phase 7: US3     │
    T024, T025[P]    T026, T027[P]    │
              │              │         │
              └──────┬───────┘         │
                     ▼                 │
           Phase 8: US5 (T028[P])      │
                     │                 │
              ┌──────┴──────┐          │
              ▼             ▼          │
    Phase 9: US9   Phase 10: US6      │
    T029, T030[P]  T031, T032[P]      │
              │             │          │
              └──────┬──────┘          │
                     ▼                 │
            Phase 11: Admin+Polish ◄───┘
            T033[P], T034, T035[P], T036
```

---

## Parallel Execution Opportunities

### Phase 2 (Models)
- T004, T005, T006, T007 — four model files, no inter-dependencies

### Phase 3 (Utilities)
- T010, T011, T012 — three utility files, no inter-dependencies

### Within Phase 4 (US8)
- T017, T018 — test files can be written while T015/T016 implementation is in progress

### Across Phases 6, 7 (once Phase 5 complete)
- US2 (conversation context) and US3 (content generation) are both additive changes to `utils/rag.py` — sequential by file but logically independent

### Phase 11 (Polish)
- T033, T035 — `knowledge_base.py` and its tests can be developed in parallel (mock the DB)

---

## Implementation Strategy

### MVP Scope (US8 + US1 + US4 only — Phases 1–5)
Complete T001–T023. This delivers:
- pgvector knowledge base populated from approved content
- `POST /chat/sessions` — create a session
- `POST /chat/sessions/{id}/messages` — streaming RAG query with source attribution
- Graceful no-content response when knowledge base has nothing relevant
- Users can ask a question and get a grounded answer in < 3 seconds (first token)

### Incremental Delivery Order
1. **Phases 1–3** (T001–T014): All models, migration, and utilities — no HTTP yet
2. **Phase 4** (T015–T018): Indexing pipeline wired — approved documents become searchable
3. **Phase 5** (T019–T023): First working chat endpoint — MVP complete
4. **Phase 6** (T024–T025): Conversation context — follow-ups work naturally
5. **Phase 7** (T026–T027): Content generation mode — labeled generated output
6. **Phase 8** (T028): Variation — naturally follows from US2 + US3
7. **Phase 9** (T029–T030): Session history — persistence and navigation
8. **Phase 10** (T031–T032): Named document targeting — precision retrieval
9. **Phase 11** (T033–T036): Admin KB tools + nginx SSE annotation

---

## Summary

| Metric | Count |
|--------|-------|
| Total tasks | 36 |
| Setup (Phase 1) | 3 |
| Foundation — Models (Phase 2) | 6 |
| Foundation — Utilities (Phase 3) | 5 |
| US8 — KB Indexing (Phase 4) | 4 |
| US1 + US4 — Basic RAG + No-Content (Phase 5) | 5 |
| US2 — Conversation Context (Phase 6) | 2 |
| US3 — Content Generation (Phase 7) | 2 |
| US5 — Content Variation (Phase 8) | 1 |
| US9 — Session History (Phase 9) | 2 |
| US6 — Named Document (Phase 10) | 2 |
| Admin + Polish (Phase 11) | 4 |
| Parallelizable [P] tasks | 20 |
| Test tasks | 12 |
