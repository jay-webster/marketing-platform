# API Contracts: Content Browser

**Router prefix**: `/api/v1/content`
**Authorization**: Any authenticated role.
**Response envelope**: `{ "data": ..., "request_id": "..." }`

---

## GET /content

List indexed content from the GitHub repository. All roles can access. Returns only `is_active=true` documents.

**Query params**:
- `search` — text search across `title` and `repo_path` (optional)
- `folder` — filter by folder path (optional)
- `limit` — default 50, max 100
- `offset` — default 0

**Response**:

```json
200 OK
{
  "data": [
    {
      "id": "uuid",
      "title": "Q4 Campaign Brief",
      "repo_path": "content/campaigns/q4-brief.md",
      "folder": "content/campaigns",
      "index_status": "indexed" | "queued" | "indexing" | "failed",
      "last_synced_at": "ISO-8601",
      "chunk_count": 12
    }
  ],
  "total": 87
}
```

---

## GET /content/{id}

Get the full content of a single indexed document.

**Authorization**: Any authenticated role.

**Response**:

```json
200 OK
{
  "data": {
    "id": "uuid",
    "title": "Q4 Campaign Brief",
    "repo_path": "content/campaigns/q4-brief.md",
    "folder": "content/campaigns",
    "raw_content": "---\ntitle: Q4 Campaign Brief\n...",
    "index_status": "indexed",
    "last_synced_at": "ISO-8601",
    "chunk_count": 12
  }
}
```

```json
404 Not Found
{ "detail": { "code": "CONTENT_NOT_FOUND", "message": "Content item not found." } }
```
