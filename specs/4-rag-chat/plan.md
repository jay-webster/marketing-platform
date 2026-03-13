# Implementation Plan: Epic 4 — Agentic Chat Interface (RAG)

**Branch**: `4-rag-chat` | **Date**: 2026-03-13 | **Spec**: `specs/4-rag-chat/spec.md`

---

## Summary

Users query the organization's approved content library in plain language and receive streaming, source-grounded answers. A vector knowledge base (pgvector + OpenAI embeddings) indexes approved `ProcessedDocument` records from Epic 3. When a document is approved, it is automatically chunked, embedded, and made searchable within 5 minutes. Chat sessions maintain full conversation context. Responses are streamed token-by-token via SSE. All generation is grounded in approved content; the AI declines when no relevant content exists.

---

## Technical Context

**Language/Version**: Python 3.13
**Framework**: FastAPI 0.115+
**New Dependencies**: `openai>=1.0` (text-embedding-3-small), `pgvector` (pgvector-python SQLAlchemy integration)
**Vector Store**: pgvector on existing PostgreSQL — HNSW index, cosine similarity, 1536-dim vectors
**Embedding Model**: OpenAI `text-embedding-3-small` ($0.02/1M tokens, 1536 dims)
**Generation Model**: `claude-opus-4-6` (chat completions + streaming)
**Chunking**: Section-primary (split on `##` headings), 512 token max, 50-token overlap, YAML frontmatter prepended to every chunk
**Streaming**: FastAPI `StreamingResponse` + `AsyncAnthropic.messages.stream()` SSE
**Queue**: Extend Epic 3's PostgreSQL SKIP LOCKED queue — add indexing workers
**New Tables**: `chat_sessions`, `chat_messages`, `knowledge_base_documents`, `content_chunks`
**New Utils**: `utils/embeddings.py`, `utils/chunker.py`, `utils/indexer.py`, `utils/rag.py`
**New APIs**: `src/api/chat.py`, `src/api/knowledge_base.py`
**Target Platform**: GCP GKE (single container, same Postgres instance)
**Performance Goals**: First token < 3s (SC-1), indexing < 5 minutes (SC-4), 100% no-fabrication (SC-3)

---

## Constitution Check

| Principle | Status | Notes |
|-----------|--------|-------|
| **Authentication Safety** | ✅ PASS | All 6 chat endpoints and 2 admin endpoints depend on `get_current_user`; admin endpoints additionally verify `X-Admin-Token` |
| **Environment Discipline** | ✅ PASS | `OPENAI_API_KEY`, `KB_SIMILARITY_THRESHOLD`, `KB_RETRIEVAL_TOP_K`, `CHAT_MODEL`, `CHAT_MAX_TOKENS`, `KB_INDEX_CONCURRENCY` added to `Settings` — no hardcoded values |
| **DRY** | ✅ PASS | `utils/db.py` reused for all DB access; `utils/audit.py` used for all 7 audit events; Epic 3's SKIP LOCKED queue pattern extended (not rewritten) for indexing workers |
| **Stateless Services** | ✅ PASS | No local filesystem writes — `ProcessedDocument.markdown_content` read from DB directly; embeddings generated in-memory; `io.BytesIO` not needed (no file download) |
| **Error Handling** | ✅ PASS | Global exception handler already in `src/main.py`; SSE stream emits `error` event type for in-stream failures rather than dropping the connection |
| **Idempotent Operations** | ✅ PASS | Indexing: existing `content_chunks` deleted before re-insert; `knowledge_base_documents` UPSERT on re-approval; re-index is idempotent (reset all to queued, worker re-processes) |
| **Admin Security** | ✅ PASS | `GET /admin/knowledge-base/status` and `POST /admin/knowledge-base/reindex` both verify `X-Admin-Token` header; return 403 immediately if missing or invalid |
| **Audit Logging** | ✅ PASS | 7 audit events defined in `data-model.md`; all KB state changes and session lifecycle events written to `audit_log` |

---

## Architecture

### RAG Request Flow

```
POST /chat/sessions/{id}/messages
  │
  ├── 1. Auth guard (get_current_user)
  ├── 2. Validate session ownership + message (1–2000 chars)
  ├── 3. Persist user message (chat_messages)
  │
  ├── 4. Embed query → OpenAI text-embedding-3-small → vector(1536)
  ├── 5. pgvector HNSW cosine search → top-K chunks (default K=6)
  │         SET hnsw.ef_search = 100
  │         WHERE similarity > KB_SIMILARITY_THRESHOLD (0.3)
  │
  ├── 6. [No results] → emit SSE no_content event → persist assistant message → done
  │
  ├── 7. [Results found] → build prompt:
  │         system_prompt (constrained — see research.md Decision 4)
  │         + conversation history (last N messages from session)
  │         + retrieved chunks (formatted with source attribution)
  │         + user message
  │
  ├── 8. AsyncAnthropic.messages.stream() → SSE delta events
  ├── 9. On stream complete → emit sources event + done event
  └── 10. Persist assistant message (content, source_documents JSONB, is_generated_content)
```

### Indexing Pipeline (Approval Trigger)

```
PATCH /ingestion/batches/{id}/documents/{id}/review (review_status=approved)
  │
  ├── [Existing Epic 3 logic: update ProcessedDocument.review_status = approved]
  │
  └── [New Epic 4 logic]:
        ├── UPSERT knowledge_base_documents (processed_document_id, status=queued)
        └── write_audit("kb_document_queued", ...)

  [Indexing Worker — asyncio task from _lifespan]
  │
  ├── SELECT knowledge_base_documents WHERE status=queued FOR UPDATE SKIP LOCKED LIMIT 1
  ├── Mark status=indexing
  ├── Load ProcessedDocument.markdown_content from DB
  ├── Chunk markdown → list[dict] (content_text, metadata)
  ├── Batch embed chunks → OpenAI embeddings API (batch of up to 100)
  ├── Delete existing content_chunks for this kb_document_id
  ├── Insert new content_chunks rows (content_text, embedding, metadata)
  ├── Update knowledge_base_documents: status=indexed, chunk_count, indexed_at
  └── write_audit("kb_document_indexed", ...)

  [Un-approval Trigger — in PATCH /review when flagging for reprocessing]
  ├── Delete content_chunks WHERE knowledge_base_document_id = kd.id
  ├── Update knowledge_base_documents: status=removed, removed_at
  └── write_audit("kb_document_removed", ...)
```

### Session Isolation

```
GET /chat/sessions          → WHERE user_id = current_user.id AND deleted_at IS NULL
GET /chat/sessions/{id}     → WHERE id = session_id AND user_id = current_user.id
POST /chat/sessions/{id}/messages → verify session.user_id == current_user.id
DELETE /chat/sessions/{id}  → verify session.user_id == current_user.id, set deleted_at
```

---

## New Files

| File | Purpose |
|------|---------|
| `src/models/chat_session.py` | `ChatSession` SQLAlchemy model |
| `src/models/chat_message.py` | `ChatMessage` SQLAlchemy model |
| `src/models/knowledge_base_document.py` | `KnowledgeBaseDocument` model + `KBIndexStatus` enum |
| `src/models/content_chunk.py` | `ContentChunk` model with pgvector `Vector(1536)` column |
| `migrations/versions/005_create_rag_tables.py` | pgvector extension + 4 new tables + HNSW index |
| `utils/embeddings.py` | OpenAI embedding client singleton, `embed_text()`, `embed_batch()` |
| `utils/chunker.py` | `chunk_markdown()` — section-primary + overflow splitting |
| `utils/indexer.py` | `index_document(kb_doc_id)`, `remove_document(kb_doc_id)` |
| `utils/rag.py` | `retrieve_chunks()` (pgvector), `build_prompt()`, `rag_stream_generator()` (SSE) |
| `src/api/chat.py` | 5 chat session/message endpoints |
| `src/api/knowledge_base.py` | 2 admin KB endpoints |

---

## Modifications to Existing Files

| File | Change |
|------|--------|
| `requirements.txt` | Add `openai>=1.0`, `pgvector` |
| `src/config.py` | Add `OPENAI_API_KEY`, `KB_SIMILARITY_THRESHOLD`, `KB_RETRIEVAL_TOP_K`, `CHAT_MODEL`, `CHAT_MAX_TOKENS`, `KB_INDEX_CONCURRENCY` |
| `.env.example` | Add above 6 variables with comments |
| `src/models/__init__.py` | Export `ChatSession`, `ChatMessage`, `KnowledgeBaseDocument`, `KBIndexStatus`, `ContentChunk` |
| `src/api/ingestion.py` | Add KB queue trigger in `review_document()`: UPSERT `knowledge_base_documents` on approval; delete chunks + mark removed on flag |
| `utils/queue.py` | Add `start_indexing_workers()`, `stop_indexing_workers()`, `_indexing_worker(worker_id)` |
| `src/main.py` | Mount `chat_router`, `kb_router`; add `start_indexing_workers` / `stop_indexing_workers` to `_lifespan()` |
| `infra/k8s/base/ingress.yaml` | Add `nginx.ingress.kubernetes.io/proxy-buffering: "off"` annotation (required for SSE) |
| `docker-compose.yml` | Change `postgres:16` → `pgvector/pgvector:pg16` |

---

## Constitution Compliance Labels (pre-implementation)

- [x] **AUTH_SAFE** — All 8 new endpoints include `Depends(get_current_user)`; admin endpoints additionally check `X-Admin-Token`
- [x] **DRY** — `utils/db.py`, `utils/audit.py`, `utils/queue.py` (extended, not duplicated)
- [x] **NON_BLOCKING** — `embed_text()` is async (OpenAI SDK async client); pgvector queries are async SQLAlchemy; `rag_stream_generator()` is an `async_generator`; no filesystem writes

---

## Risk Table

| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|-----------|
| pgvector HNSW build slow on large corpus | Low (< 100K chunks) | Medium | Build index `WITH (m=24, ef_construction=64)` during migration; subsequent inserts are incremental (no rebuild needed) |
| OpenAI embedding API rate limits | Low (batch mode) | Medium | Batch up to 100 chunks per API call; retry on 429 with exponential backoff in `utils/embeddings.py` |
| SSE buffering by GKE nginx ingress | High (default config) | High | `X-Accel-Buffering: no` header + ingress annotation `proxy-buffering: "off"` (documented in quickstart) |
| Similarity threshold too high → false negatives | Medium | Medium | Default 0.3 (permissive); configurable via `KB_SIMILARITY_THRESHOLD` env var; adjustable per installation without code change |
| Conversation history too long → context overflow | Low (MVP sessions short) | Medium | Limit history injection to last 10 messages; truncate at 4000 tokens |
| asyncpg + pgvector type registration | Medium | High | Register vector type at engine startup via `register_vector_async` (documented in research.md Decision 1) |

---

## Task Summary

33 tasks across 11 phases.

| Phase | Tasks | Description |
|-------|-------|-------------|
| 1 — Setup | T001–T003 | Dependencies, config, env |
| 2 — Models | T004–T008 | 4 models + `__init__.py` update |
| 3 — Migration | T009 | Migration 005 (pgvector + 4 tables) |
| 4 — Utilities | T010–T013 | embeddings, chunker, indexer, rag |
| 5 — Indexing Pipeline | T014–T016 | Queue worker extension, approval trigger, indexing tests |
| 6 — US1: Basic RAG | T017–T019 | Chat API, mount routers, basic RAG tests |
| 7 — US2 + US4: Context + No-Content | T020–T022 | Conversation history, no-content guard, tests |
| 8 — US3 + US5 + US7: Generation | T023–T025 | Generation mode, variations, content gen tests |
| 9 — US8: Named Doc Targeting | T026–T027 | Named document resolution, tests |
| 10 — US6 + US9: Sessions | T028–T030 | Session CRUD, history, session tests |
| 11 — Admin KB + Polish | T031–T033 | Admin endpoints, audit assertions, CI step |
