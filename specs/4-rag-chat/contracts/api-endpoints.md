# API Contracts: Epic 4 — Agentic Chat Interface (RAG)

**Auth**: All endpoints require `Authorization: Bearer <token>` unless noted.
**Prefix**: `/api/v1`
**Router**: `src/api/chat.py` (chat endpoints), `src/api/knowledge_base.py` (admin KB endpoints)

---

## Chat Sessions

### POST /chat/sessions

Create a new chat session.

**Auth**: Any authenticated user.

**Request**: No body required.

**Response 201**:
```json
{
  "data": {
    "session_id": "uuid",
    "title": null,
    "created_at": "2026-03-13T10:00:00Z",
    "last_active_at": "2026-03-13T10:00:00Z"
  },
  "request_id": "uuid"
}
```

---

### GET /chat/sessions

List the current user's active (non-deleted) sessions, ordered by `last_active_at DESC`.

**Auth**: Any authenticated user.

**Query params**:
- `limit` (int, default 20, max 100)
- `offset` (int, default 0)

**Response 200**:
```json
{
  "data": [
    {
      "session_id": "uuid",
      "title": "What are our Q1 enterprise key messages?",
      "created_at": "2026-03-13T10:00:00Z",
      "last_active_at": "2026-03-13T10:30:00Z",
      "message_count": 6
    }
  ],
  "total": 12,
  "request_id": "uuid"
}
```

---

### GET /chat/sessions/{session_id}

Get a session with full message history.

**Auth**: Authenticated user who owns the session (404 if not owner or not found).

**Response 200**:
```json
{
  "data": {
    "session_id": "uuid",
    "title": "What are our Q1 enterprise key messages?",
    "created_at": "2026-03-13T10:00:00Z",
    "last_active_at": "2026-03-13T10:30:00Z",
    "messages": [
      {
        "message_id": "uuid",
        "role": "user",
        "content": "What are our approved key messages for enterprise?",
        "is_generated_content": false,
        "source_documents": null,
        "created_at": "2026-03-13T10:00:00Z"
      },
      {
        "message_id": "uuid",
        "role": "assistant",
        "content": "Based on your approved content, here are the key messages...",
        "is_generated_content": false,
        "source_documents": [
          {"id": "uuid", "title": "Q1 Enterprise Launch Brief", "source_file": "q1-launch.pdf"}
        ],
        "created_at": "2026-03-13T10:00:05Z"
      }
    ]
  },
  "request_id": "uuid"
}
```

**Errors**:
- `404 SESSION_NOT_FOUND` — session does not exist or belongs to another user

---

### DELETE /chat/sessions/{session_id}

Soft-delete a session (sets `deleted_at`, excluded from all future queries).

**Auth**: Authenticated user who owns the session.

**Response 200**:
```json
{
  "data": {"session_id": "uuid", "deleted": true},
  "request_id": "uuid"
}
```

**Errors**:
- `404 SESSION_NOT_FOUND`

---

## Chat Messages (RAG + Streaming)

### POST /chat/sessions/{session_id}/messages

Send a user message and receive a streaming AI response.

**Auth**: Authenticated user who owns the session.

**Request**:
```json
{
  "content": "What are our approved key messages for the enterprise segment?"
}
```

**Validation**:
- `content` required, 1–2000 characters (FR-1.2)
- `400 MESSAGE_TOO_LONG` if > 2000 chars
- `400 MESSAGE_EMPTY` if blank
- `404 SESSION_NOT_FOUND` if session does not belong to user or is deleted

**Response**: `200 text/event-stream` (SSE)

SSE event stream format:
```
data: {"type": "delta", "text": "Based on your "}\n\n
data: {"type": "delta", "text": "approved content, "}\n\n
...
data: {"type": "sources", "sources": [
  {"id": "uuid", "title": "Q1 Enterprise Launch Brief", "source_file": "q1-launch.pdf"},
  {"id": "uuid", "title": "Enterprise Messaging Guide", "source_file": "messaging.docx"}
]}\n\n
data: {"type": "done", "message_id": "uuid", "is_generated_content": false}\n\n
```

**SSE event types**:

| Type | Description | Fields |
|------|-------------|--------|
| `delta` | Text token fragment | `text: string` |
| `sources` | Source documents used | `sources: [{id, title, source_file}]` |
| `no_content` | No relevant approved content found | `suggestion: string` |
| `done` | Stream complete | `message_id: uuid`, `is_generated_content: bool` |
| `error` | Processing error | `code: string`, `message: string` |

**No-content flow** (Scenario 4 / FR-2.4):
When pgvector returns no results above the similarity threshold, the stream emits:
```
data: {"type": "no_content", "suggestion": "No approved content found on this topic. To enable this, approve documents covering enterprise messaging through the ingestion workflow."}\n\n
data: {"type": "done", "message_id": "uuid", "is_generated_content": false}\n\n
```

**Response headers**:
```
Content-Type: text/event-stream
Cache-Control: no-cache
X-Accel-Buffering: no
```

---

## Admin: Knowledge Base

All endpoints in this section require `X-Admin-Token` header in addition to bearer auth.

### GET /admin/knowledge-base/status

Returns knowledge base aggregate status (FR-5.6).

**Auth**: Admin bearer token + `X-Admin-Token` header.

**Response 200**:
```json
{
  "data": {
    "total_indexed_documents": 47,
    "documents_queued_for_indexing": 3,
    "documents_failed": 1,
    "last_indexed_at": "2026-03-13T09:45:00Z",
    "last_full_reindex_at": null
  },
  "request_id": "uuid"
}
```

---

### POST /admin/knowledge-base/reindex

Trigger a full re-index of all approved documents (FR-5.5).

Resets all `knowledge_base_documents` with `index_status IN ('indexed', 'failed', 'removed')` back to `queued` for approved documents, and deletes all existing `content_chunks`. Workers re-process them.

**Auth**: Admin bearer token + `X-Admin-Token` header.

**Request**: No body.

**Response 202**:
```json
{
  "data": {
    "documents_queued": 47,
    "message": "Full re-index triggered. Documents will be searchable within 5 minutes."
  },
  "request_id": "uuid"
}
```

**Errors**:
- `403` if `X-Admin-Token` is missing or invalid

---

## Error Codes

| Code | HTTP | Meaning |
|------|------|---------|
| `SESSION_NOT_FOUND` | 404 | Session does not exist or does not belong to the requesting user |
| `MESSAGE_TOO_LONG` | 400 | Message content exceeds 2000 characters |
| `MESSAGE_EMPTY` | 400 | Message content is blank |
| `RAG_UNAVAILABLE` | 503 | Vector search or embedding service is temporarily unavailable |
| `STREAM_ERROR` | 500 | Unexpected error during AI response generation |
