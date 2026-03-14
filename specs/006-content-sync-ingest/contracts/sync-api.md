# API Contracts: GitHub Sync

**Router prefix**: `/api/v1/github`
**Authorization**: All endpoints require `require_role(Role.ADMIN)`
**Response envelope**: `{ "data": ..., "request_id": "..." }`

---

## POST /github/sync

Trigger an on-demand sync of the connected repository.

**Request**: No body.

**Responses**:

```json
201 Created
{
  "data": {
    "run_id": "uuid",
    "trigger_type": "manual",
    "started_at": "ISO-8601",
    "outcome": "in_progress"
  }
}
```

```json
409 Conflict  — sync already running
{
  "detail": {
    "code": "SYNC_ALREADY_RUNNING",
    "message": "A sync is already in progress.",
    "run_id": "uuid"
  }
}
```

```json
404 Not Found  — no active connection
{
  "detail": { "code": "NO_CONNECTION", "message": "No repository is currently connected." }
}
```

---

## GET /github/sync/status

Returns the current sync status (latest run).

**Response**:

```json
200 OK
{
  "data": {
    "run_id": "uuid",
    "trigger_type": "manual" | "scheduled",
    "started_at": "ISO-8601",
    "finished_at": "ISO-8601 | null",
    "outcome": "in_progress" | "success" | "partial" | "failed" | "interrupted",
    "files_indexed": 42,
    "files_removed": 2,
    "files_unchanged": 98,
    "error_detail": "string | null"
  }
}
```

Returns `null` data if no sync has ever run.

---

## GET /github/sync/runs

Paginated sync history.

**Query params**: `limit` (default 20, max 100), `offset` (default 0)

**Response**:

```json
200 OK
{
  "data": [
    {
      "run_id": "uuid",
      "trigger_type": "manual" | "scheduled",
      "triggered_by_name": "string | null",
      "started_at": "ISO-8601",
      "finished_at": "ISO-8601 | null",
      "outcome": "string",
      "files_indexed": 42,
      "files_removed": 2,
      "files_unchanged": 98,
      "error_detail": "string | null"
    }
  ],
  "total": 15
}
```

---

## POST /github/config/folders

Add a single folder to the configured list and scaffold it in the repo.

**Request**:

```json
{
  "folder": "content/new-section"
}
```

**Validation**: Same rules as `PUT /github/config` — no path traversal, no leading/trailing slash, no duplicates.

**Responses**:

```json
201 Created
{
  "data": {
    "folder": "content/new-section",
    "folders": ["content/blog", "content/new-section"],
    "scaffold": {
      "outcome": "success" | "failed",
      "error": "string | null"
    }
  }
}
```

```json
409 Conflict  — folder already configured
{
  "detail": { "code": "FOLDER_ALREADY_EXISTS", "message": "Folder 'content/new-section' is already configured." }
}
```

```json
422 Unprocessable
{
  "detail": { "code": "CONFIG_INVALID", "message": "...", "invalid_entries": ["..."] }
}
```

---

## DELETE /github/config/folders/{folder_name}

Remove a folder from the configured list. Does NOT delete from the repo.

**Path param**: `folder_name` — URL-encoded folder path (e.g. `content%2Fblog`)

**Responses**:

```json
200 OK
{
  "data": {
    "removed": "content/blog",
    "folders": ["content/other"]
  }
}
```

```json
404 Not Found
{
  "detail": { "code": "FOLDER_NOT_FOUND", "message": "Folder 'content/blog' is not in the configured list." }
}
```
