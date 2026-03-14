# API Contracts: Ingestion PR Workflow

**Router prefix**: `/api/v1/ingestion`
**Authorization**: Role-based per endpoint.
**Response envelope**: `{ "data": ..., "request_id": "..." }`

---

## POST /ingestion/documents/{doc_id}/approve  (modified)

Approve a pending document. Now requires `destination_folder`.

**Authorization**: Admin only.

**Request** (modified — adds `destination_folder`):

```json
{
  "destination_folder": "content/blog"
}
```

`destination_folder` must be one of the currently configured repo folders.

**Responses**:

```json
200 OK
{
  "data": {
    "id": "uuid",
    "processing_status": "queued",
    "destination_folder": "content/blog"
  }
}
```

```json
422 Unprocessable  — folder not in configured list
{
  "detail": {
    "code": "FOLDER_NOT_CONFIGURED",
    "message": "Folder 'content/unknown' is not in the configured folder list."
  }
}
```

```json
409 Conflict  — already approved or not pending
{ "detail": { "code": "DOCUMENT_NOT_PENDING", "message": "..." } }
```

---

## GET /ingestion/prs

List all ingestion documents currently in `pr_open` status. Admin only.

**Authorization**: Admin only.

**Query params**: `limit` (default 50), `offset` (default 0)

**Response**:

```json
200 OK
{
  "data": [
    {
      "id": "uuid",
      "original_filename": "report.pdf",
      "destination_folder": "content/reports",
      "github_branch": "ingest/report-1741962000",
      "github_pr_number": 42,
      "github_pr_url": "https://github.com/org/repo/pull/42",
      "submitted_by_name": "Jane Smith",
      "submitted_by_email": "jane@example.com",
      "queued_at": "ISO-8601"
    }
  ],
  "total": 3
}
```

---

## GET /ingestion/documents/{doc_id}/pr

Get the generated Markdown content for PR review. Admin only.

**Authorization**: Admin only.

**Responses**:

```json
200 OK
{
  "data": {
    "id": "uuid",
    "original_filename": "report.pdf",
    "destination_folder": "content/reports",
    "github_branch": "ingest/report-1741962000",
    "github_pr_number": 42,
    "github_pr_url": "https://github.com/org/repo/pull/42",
    "markdown_content": "---\ntitle: ...\n---\n\n# Report\n...",
    "current_folder": "content/reports",
    "configured_folders": ["content/blog", "content/reports", "content/guides"]
  }
}
```

```json
409 Conflict  — document not in pr_open status
{ "detail": { "code": "DOCUMENT_NOT_PR_OPEN", "message": "..." } }
```

---

## POST /ingestion/documents/{doc_id}/pr/merge

Merge the PR in-app. Optionally moves the file to a different folder before merging.

**Authorization**: Admin only.

**Request**:

```json
{
  "destination_folder": "content/guides"
}
```

`destination_folder` is optional. If omitted, uses the folder from approval. If provided and different from the committed path, the file is moved on the branch before merging.

**Responses**:

```json
200 OK
{
  "data": {
    "id": "uuid",
    "processing_status": "merged",
    "github_pr_number": 42,
    "merged_to_folder": "content/guides",
    "sync_triggered": true
  }
}
```

```json
409 Conflict  — PR already merged or not open
{ "detail": { "code": "DOCUMENT_NOT_PR_OPEN", "message": "..." } }
```

```json
503 Service Unavailable  — GitHub unreachable
{ "detail": { "code": "GITHUB_UNAVAILABLE", "message": "..." } }
```

---

## POST /ingestion/documents/{doc_id}/pr/close

Close/reject the PR in-app without merging.

**Authorization**: Admin only.

**Request**: No body.

**Responses**:

```json
200 OK
{
  "data": {
    "id": "uuid",
    "processing_status": "rejected"
  }
}
```

```json
409 Conflict
{ "detail": { "code": "DOCUMENT_NOT_PR_OPEN", "message": "..." } }
```
