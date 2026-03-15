# Data Model: RAG-Powered Chat Interface

**Phase 1 output for `005-rag-chat`**
**Date**: 2026-03-14

---

## Existing Models (no schema changes required)

Both database tables are already created and correct. No new migrations needed for this feature.

### `chat_sessions`

| Column | Type | Notes |
|--------|------|-------|
| `id` | UUID PK | Auto-generated |
| `user_id` | UUID FK → `users.id` | CASCADE delete |
| `title` | TEXT nullable | Auto-set from first message (60 char truncation) — currently null until first message sent |
| `created_at` | TIMESTAMPTZ | Immutable |
| `last_active_at` | TIMESTAMPTZ | Updated on every message send |
| `deleted_at` | TIMESTAMPTZ nullable | Soft-delete; NULL = active |

**State machine**: Active (deleted_at IS NULL) → Deleted (deleted_at IS NOT NULL)

**Indexes**:
- `idx_chat_sessions_user_id`
- `idx_chat_sessions_user_active` (user_id, last_active_at WHERE deleted_at IS NULL)

### `chat_messages`

| Column | Type | Notes |
|--------|------|-------|
| `id` | UUID PK | Auto-generated |
| `session_id` | UUID FK → `chat_sessions.id` | CASCADE delete |
| `role` | TEXT | `"user"` or `"assistant"` |
| `content` | TEXT | Full message text |
| `is_generated_content` | BOOLEAN | True when assistant response contains AI-generated marketing copy |
| `source_documents` | JSONB nullable | Array of `{id, title, source_file, similarity}` for assistant messages |
| `created_at` | TIMESTAMPTZ | Immutable |

**Index**: `idx_chat_messages_session_id` (session_id, created_at)

### `source_documents` JSONB schema (stored in `chat_messages.source_documents`)

```json
[
  {
    "id": "uuid-string",
    "title": "Document Title",
    "source_file": "content/assets/documents/filename.md",
    "similarity": 0.87
  }
]
```

Note: `similarity` field is being added in this feature (was missing from initial implementation).

---

## Read-Only Dependencies (no changes)

| Table | Used for |
|-------|----------|
| `content_chunks` | pgvector similarity search in `utils/rag.py` |
| `knowledge_base_documents` | Filter to `index_status = 'indexed'` |
| `processed_documents` | Join for document title metadata |

---

## No New Migrations Required

All schema changes in this feature are:
- Adding `similarity` to the JSONB payload stored in `chat_messages.source_documents` — this is a data change, not a schema change; JSONB is schemaless.
- Auto-populating `chat_sessions.title` — the column already exists and is nullable.
