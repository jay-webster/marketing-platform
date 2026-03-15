# API Contracts: RAG-Powered Chat Interface

**Phase 1 output for `005-rag-chat`**
**Date**: 2026-03-14

All endpoints are authenticated via the BFF proxy. Frontend calls `/api/v1/...` (Next.js proxy); the proxy adds `Authorization: Bearer <token>` from the `auth-token` httpOnly cookie.

---

## Existing Endpoints (no changes to signatures)

### `POST /api/v1/chat/sessions`
Create a new chat session.

**Request**
```json
{ "title": null }
```

**Response 201**
```json
{
  "data": {
    "id": "uuid",
    "title": null,
    "created_at": "2026-03-14T12:00:00Z",
    "last_active_at": "2026-03-14T12:00:00Z"
  },
  "request_id": "string"
}
```

---

### `GET /api/v1/chat/sessions`
List the current user's active sessions, ordered by `last_active_at` desc.

**Query params**: `limit` (default 20, max 100), `offset` (default 0)

**Response 200**
```json
{
  "data": [
    {
      "id": "uuid",
      "title": "What were the key messages in Q3?",
      "created_at": "2026-03-14T12:00:00Z",
      "last_active_at": "2026-03-14T12:05:00Z"
    }
  ],
  "request_id": "string"
}
```

---

### `GET /api/v1/chat/sessions/{session_id}`
Get session metadata + full message history.

**Response 200**
```json
{
  "data": {
    "id": "uuid",
    "title": "string or null",
    "created_at": "ISO8601",
    "last_active_at": "ISO8601",
    "messages": [
      {
        "id": "uuid",
        "role": "user",
        "content": "string",
        "is_generated_content": false,
        "source_documents": null,
        "created_at": "ISO8601"
      },
      {
        "id": "uuid",
        "role": "assistant",
        "content": "string",
        "is_generated_content": false,
        "source_documents": [
          {
            "id": "uuid",
            "title": "Document Title",
            "source_file": "content/assets/documents/file.md",
            "similarity": 0.87
          }
        ],
        "created_at": "ISO8601"
      }
    ]
  },
  "request_id": "string"
}
```

**Response 404** — session not found or belongs to another user.

---

### `DELETE /api/v1/chat/sessions/{session_id}`
Soft-delete a session. Returns 204 No Content.

---

## Modified Endpoint

### `POST /api/v1/chat/sessions/{session_id}/messages`
Send a message and receive a streaming SSE response.

**Request**
```json
{ "message": "string (max 4000 characters)" }
```

**Validation errors**:
- 422 if `message` is empty/whitespace
- 422 if `message` exceeds 4000 characters

**Response**: `text/event-stream` (SSE)

---

## SSE Event Contract

The `POST /messages` endpoint returns a `text/event-stream`. Events are emitted in this sequence:

### Happy path (content found)

```
event: chunk
data: {"text": "Here is what I found...", "is_generated_content": false}

event: chunk
data: {"text": " The Q3 report highlighted...", "is_generated_content": false}

... (more chunks) ...

event: done
data: {
  "message_id": "uuid",
  "session_id": "uuid",
  "source_documents": [
    {
      "id": "uuid",
      "title": "Document Title",
      "source_file": "content/assets/documents/file.md",
      "similarity": 0.87
    }
  ]
}
```

### No content path (no relevant KB content)

```
event: no_content
data: {"message": "I don't have enough information in the knowledge base to answer that question."}

event: done
data: {"message_id": "uuid", "session_id": "uuid", "source_documents": []}
```

### Error path

```
event: error
data: {"message": "An error occurred processing your request."}
```

**Notes**:
- The `sources` event type used in the original scaffolding is replaced by embedding source_documents in the `done` event.
- The frontend must handle `no_content` by displaying the provided message as an assistant bubble and ending the streaming state.
- All events are complete JSON objects on the `data:` line.

---

## Auto-Title Behaviour

When a new message is sent and `session.title IS NULL`, the backend sets `session.title` to the first 60 characters of the user's message (stripped of leading/trailing whitespace). This happens synchronously before the SSE stream begins.
