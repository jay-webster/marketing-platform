# Data Model: Epic 4 — Agentic Chat Interface (RAG)

**Date**: 2026-03-13
**Depends on**: Epic 3 `processed_documents` table

---

## Tables

### chat_sessions

One conversation thread per user. Soft-deleted (retained 90 days per FR-1.7).

```sql
CREATE TABLE chat_sessions (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id         UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    title           TEXT,               -- Auto-set from first user message (first 80 chars)
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    last_active_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    deleted_at      TIMESTAMPTZ                          -- Soft-delete; NULL = active
);

CREATE INDEX idx_chat_sessions_user_id        ON chat_sessions (user_id);
CREATE INDEX idx_chat_sessions_user_active    ON chat_sessions (user_id, last_active_at DESC)
    WHERE deleted_at IS NULL;
```

**State transitions**:
- Active → soft-deleted: `DELETE /chat/sessions/{id}` sets `deleted_at = now()`
- Soft-deleted sessions excluded from all list queries via `WHERE deleted_at IS NULL`
- Hard-delete eligible after 90 days (out-of-scope cleanup job)

---

### chat_messages

Individual turns within a session. Immutable after insert — no updates.

```sql
CREATE TABLE chat_messages (
    id                   UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    session_id           UUID NOT NULL REFERENCES chat_sessions(id) ON DELETE CASCADE,
    role                 TEXT NOT NULL CHECK (role IN ('user', 'assistant')),
    content              TEXT NOT NULL,
    is_generated_content BOOLEAN NOT NULL DEFAULT FALSE,
    -- JSONB array: [{"id": "uuid", "title": "Q1 Brief", "chunk_index": 2}, ...]
    source_documents     JSONB,
    created_at           TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_chat_messages_session_id ON chat_messages (session_id, created_at ASC);
```

**Field notes**:
- `role`: `user` for human input, `assistant` for AI responses
- `is_generated_content`: `TRUE` when the AI response contains generated marketing material (Scenarios 3, 5, 6) as opposed to a retrieval answer or a "no content" response
- `source_documents`: populated for all assistant messages that drew on retrieved chunks; `NULL` for user messages and "no content" responses; stored as JSONB for flexible querying

---

### knowledge_base_documents

Tracks indexing state for each approved document. One row per `ProcessedDocument`.

```sql
CREATE TYPE kb_index_status AS ENUM ('queued', 'indexing', 'indexed', 'failed', 'removed');

CREATE TABLE knowledge_base_documents (
    id                    UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    processed_document_id UUID NOT NULL UNIQUE REFERENCES processed_documents(id) ON DELETE CASCADE,
    index_status          kb_index_status NOT NULL DEFAULT 'queued',
    failure_reason        TEXT,
    chunk_count           INT,            -- Populated after successful indexing
    indexed_at            TIMESTAMPTZ,
    removed_at            TIMESTAMPTZ,
    created_at            TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at            TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_kb_documents_status ON knowledge_base_documents (index_status)
    WHERE index_status = 'queued';       -- Partial index for queue worker
CREATE INDEX idx_kb_documents_indexed  ON knowledge_base_documents (indexed_at DESC)
    WHERE index_status = 'indexed';
```

**State machine**:
```
queued → indexing → indexed
                  ↓
               failed     (retryable — Admin re-index resets to queued)
indexed → removed         (when document is un-approved or flagged for reprocessing)
removed → queued          (when document is re-approved after re-processing)
```

---

### content_chunks

Vector store. One row per chunk of an indexed document. Deleted and re-created on re-index.

```sql
-- Requires pgvector extension (migration 005 enables it)
CREATE TABLE content_chunks (
    id                      UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    knowledge_base_document_id UUID NOT NULL REFERENCES knowledge_base_documents(id) ON DELETE CASCADE,
    chunk_index             INT NOT NULL,       -- 0-based position within the document
    content_text            TEXT NOT NULL,      -- Frontmatter + section text (embedded)
    embedding               vector(1536) NOT NULL,  -- OpenAI text-embedding-3-small
    metadata                JSONB NOT NULL DEFAULT '{}',  -- Parsed frontmatter fields
    created_at              TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- HNSW index for approximate nearest-neighbour search (cosine similarity)
CREATE INDEX idx_content_chunks_embedding
    ON content_chunks
    USING hnsw (embedding vector_cosine_ops)
    WITH (m = 24, ef_construction = 64);

CREATE INDEX idx_content_chunks_kb_doc_id ON content_chunks (knowledge_base_document_id);
```

**HNSW query pattern**:
```sql
SET hnsw.ef_search = 100;
SELECT id, content_text, metadata, 1 - (embedding <=> $1) AS similarity
FROM content_chunks
ORDER BY embedding <=> $1
LIMIT 6;
```

**metadata JSONB structure** (indexed from frontmatter):
```json
{
  "document_id": "uuid",
  "title": "Q1 Enterprise Launch Key Messages",
  "source_file": "q1-launch-brief.pdf",
  "source_type": ".pdf",
  "author": "Jane Smith",
  "source_date": "2026-01-15",
  "ingested_by": "jane@example.com",
  "chunk_index": 2,
  "total_chunks": 7
}
```

---

## Relationships

```
users (Epic 1)
  └─► chat_sessions (user_id FK)
        └─► chat_messages (session_id FK)

processed_documents (Epic 3)
  └─► knowledge_base_documents (processed_document_id UNIQUE FK)
        └─► content_chunks (knowledge_base_document_id FK)
                            embedding vector(1536)
```

---

## Migration

**005_create_rag_tables.py** — upgrade order:
1. `CREATE EXTENSION IF NOT EXISTS vector;`
2. `CREATE TYPE kb_index_status AS ENUM ...`
3. `CREATE TABLE chat_sessions`
4. `CREATE TABLE chat_messages`
5. `CREATE TABLE knowledge_base_documents`
6. `CREATE TABLE content_chunks` + HNSW index

Downgrade order: drop tables in reverse, drop type, drop extension.

---

## Audit Events

| Action | Trigger | Fields |
|--------|---------|--------|
| `kb_document_queued` | Document approved in Epic 3 review | `processed_document_id` |
| `kb_document_indexed` | Indexing worker completes | `processed_document_id`, `chunk_count` |
| `kb_document_failed` | Indexing worker fails | `processed_document_id`, `failure_reason` |
| `kb_document_removed` | Document un-approved / flagged for reprocessing | `processed_document_id` |
| `kb_full_reindex_triggered` | Admin triggers full re-index | `actor_id`, `documents_reset` |
| `chat_session_created` | User creates a new session | `session_id`, `user_id` |
| `chat_session_deleted` | User soft-deletes a session | `session_id`, `user_id` |
