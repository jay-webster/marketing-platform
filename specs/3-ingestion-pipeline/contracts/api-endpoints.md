# API Contract: Epic 3 — Ingestion & Markdown Pipeline

**Router prefix**: `/api/v1/ingestion`
**Auth**: All endpoints require a valid JWT (`Authorization: Bearer <token>`). Any authenticated role (admin, marketing_manager, marketer) may use all endpoints.
**Generated**: 2026-03-13

---

## POST /api/v1/ingestion/batches

Create a new ingestion batch. Uploads files to GCS and enqueues them for processing.

**Auth**: Any authenticated role
**Content-Type**: `multipart/form-data`

**Form fields**:

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `folder_name` | string | Yes | Display name of the source folder |
| `files` | file[] | Yes | One or more files. Min: 1, Max: 100 |

**Pre-submission validation** (returns 400 before creating any DB rows):
- At least one file must be included
- Each file must be ≤ 50 MB (`Content-Length` or streamed size). Response: `400 FILE_TOO_LARGE`
- Each file's extension must be in: `.docx`, `.pdf`, `.txt`, `.md`, `.pptx`, `.csv`. Response: `400 UNSUPPORTED_FILE_TYPE`
- Files of unsupported type that sneak through must be excluded silently (defence-in-depth; FR-1.4 is enforced client-side first)

**Response 201**:
```json
{
  "data": {
    "batch_id": "uuid",
    "status": "in_progress",
    "total_documents": 3,
    "submitted_at": "2026-03-13T14:22:00Z",
    "documents": [
      {
        "id": "uuid",
        "original_filename": "Q1-Report.docx",
        "original_file_type": ".docx",
        "relative_path": "reports/Q1-Report.docx",
        "file_size_bytes": 204800,
        "processing_status": "queued",
        "queued_at": "2026-03-13T14:22:00Z"
      }
    ]
  },
  "request_id": "uuid"
}
```

**Error responses**:
| Status | Code | Condition |
|--------|------|-----------|
| 400 | `NO_FILES_SELECTED` | No files provided |
| 400 | `FILE_TOO_LARGE` | File exceeds 50 MB |
| 400 | `UNSUPPORTED_FILE_TYPE` | Extension not in supported list |
| 401 | `UNAUTHENTICATED` | No/invalid JWT |
| 503 | `GCS_UNAVAILABLE` | GCS upload failed |

---

## GET /api/v1/ingestion/batches

List the authenticated user's batches, newest first.

**Auth**: Any authenticated role
**Query params**: `status` (optional): `in_progress` | `completed` | `completed_with_failures`

**Response 200**:
```json
{
  "data": [
    {
      "batch_id": "uuid",
      "source_folder_name": "Q1 Reports",
      "status": "in_progress",
      "total_documents": 5,
      "completed_count": 3,
      "failed_count": 1,
      "submitted_at": "2026-03-13T14:22:00Z"
    }
  ],
  "request_id": "uuid"
}
```

---

## GET /api/v1/ingestion/batches/{batch_id}

Get a batch with full document status list. Used for polling (SC-8: accurate within 5s).

**Auth**: Any authenticated role
**Path**: `batch_id` (UUID)

**Response 200**:
```json
{
  "data": {
    "batch_id": "uuid",
    "source_folder_name": "Q1 Reports",
    "status": "in_progress",
    "total_documents": 5,
    "completed_count": 3,
    "failed_count": 1,
    "submitted_at": "2026-03-13T14:22:00Z",
    "documents": [
      {
        "id": "uuid",
        "original_filename": "Q1-Report.docx",
        "original_file_type": ".docx",
        "relative_path": "reports/Q1-Report.docx",
        "file_size_bytes": 204800,
        "processing_status": "completed",
        "failure_reason": null,
        "retry_count": 0,
        "queued_at": "2026-03-13T14:22:00Z",
        "processing_started_at": "2026-03-13T14:22:05Z",
        "processing_completed_at": "2026-03-13T14:22:18Z",
        "review_status": "pending_review"
      },
      {
        "id": "uuid",
        "original_filename": "Corrupted.pdf",
        "original_file_type": ".pdf",
        "relative_path": "Corrupted.pdf",
        "file_size_bytes": 1024,
        "processing_status": "failed",
        "failure_reason": "File could not be read — it may be corrupted.",
        "retry_count": 1,
        "queued_at": "2026-03-13T14:22:00Z",
        "processing_started_at": "2026-03-13T14:22:06Z",
        "processing_completed_at": "2026-03-13T14:22:07Z",
        "review_status": null
      }
    ]
  },
  "request_id": "uuid"
}
```

**Error responses**:
| Status | Code | Condition |
|--------|------|-----------|
| 404 | `BATCH_NOT_FOUND` | No batch with this ID belonging to the requesting user |

---

## POST /api/v1/ingestion/batches/{batch_id}/documents/{doc_id}/retry

Re-queue a failed document for reprocessing.

**Auth**: Any authenticated role
**Path**: `batch_id`, `doc_id` (UUIDs)
**Body**: None required

**Behaviour**:
- `processing_status` must be `failed`. Raises `409 DOCUMENT_NOT_FAILED` otherwise.
- Resets: `processing_status = queued`, `failure_reason = null`, `processing_started_at = null`, `processing_completed_at = null`, increments `retry_count`
- Does **not** reset `reprocessing_note` (retained from any prior flag action)
- Writes `ingestion_document_retried` audit entry
- Worker picks up the document within ≤ 1 second

**Response 200**:
```json
{
  "data": {
    "id": "uuid",
    "processing_status": "queued",
    "retry_count": 2
  },
  "request_id": "uuid"
}
```

**Error responses**:
| Status | Code | Condition |
|--------|------|-----------|
| 404 | `DOCUMENT_NOT_FOUND` | Doc not found in this batch |
| 409 | `DOCUMENT_NOT_FAILED` | Document is not in `failed` status |

---

## GET /api/v1/ingestion/batches/{batch_id}/documents/{doc_id}/preview

Get the processed Markdown content for a completed document.

**Auth**: Any authenticated role
**Path**: `batch_id`, `doc_id` (UUIDs)

**Response 200**:
```json
{
  "data": {
    "id": "uuid",
    "original_filename": "Q1-Report.docx",
    "review_status": "pending_review",
    "extracted_title": "Q1 Marketing Report",
    "extracted_author": "Jane Smith",
    "extracted_date": "2026-01-15",
    "markdown_content": "---\ntitle: Q1 Marketing Report\n...\n---\n\n# Q1 Marketing Report\n\n..."
  },
  "request_id": "uuid"
}
```

The `markdown_content` field contains the complete Markdown string including YAML frontmatter. Clients may render it as-is or split on the closing `---` fence to separate raw frontmatter from the body.

**Error responses**:
| Status | Code | Condition |
|--------|------|-----------|
| 404 | `DOCUMENT_NOT_FOUND` | Doc not found in this batch |
| 409 | `DOCUMENT_NOT_COMPLETED` | Document is not in `completed` status |

---

## PATCH /api/v1/ingestion/batches/{batch_id}/documents/{doc_id}/review

Set the review status of a completed document.

**Auth**: Any authenticated role
**Path**: `batch_id`, `doc_id` (UUIDs)

**Request body**:
```json
{
  "review_status": "approved",
  "reprocessing_note": null
}
```

| Field | Type | Required | Values |
|-------|------|----------|--------|
| `review_status` | string | Yes | `approved` \| `flagged_for_reprocessing` |
| `reprocessing_note` | string\|null | No | Free-text note (max 1000 chars). Required when `review_status = flagged_for_reprocessing`. |

**Behaviour**:
- Document must be in `completed` processing status. Raises `409 DOCUMENT_NOT_COMPLETED` otherwise.
- If `review_status = flagged_for_reprocessing`: updates `review_status`, saves `reprocessing_note` on `ingestion_documents`, then immediately transitions `processing_status = queued` (re-enters processing queue). Deletes existing `processed_documents` row.
- If `review_status = approved`: updates `review_status` and `reviewed_by` / `reviewed_at` on `processed_documents`.
- Writes appropriate audit entry.

**Response 200**:
```json
{
  "data": {
    "id": "uuid",
    "review_status": "flagged_for_reprocessing",
    "processing_status": "queued"
  },
  "request_id": "uuid"
}
```

**Error responses**:
| Status | Code | Condition |
|--------|------|-----------|
| 400 | `REPROCESSING_NOTE_REQUIRED` | `flagged_for_reprocessing` with no note (note is optional per spec but included as advisory) |
| 404 | `DOCUMENT_NOT_FOUND` | Doc not found in this batch |
| 409 | `DOCUMENT_NOT_COMPLETED` | Document `processing_status != completed` |
| 422 | `INVALID_REVIEW_STATUS` | Value not in allowed enum |

---

## POST /api/v1/ingestion/batches/{batch_id}/export

Download a ZIP archive of selected completed documents.

**Auth**: Any authenticated role
**Path**: `batch_id` (UUID)

**Request body**:
```json
{
  "document_ids": ["uuid1", "uuid2"]
}
```

If `document_ids` is an empty array: exports all `completed` documents in the batch.

**Behaviour**:
- Filters to only documents with `processing_status = completed`. Failed documents are excluded.
- Reads `markdown_content` from `processed_documents` table (no GCS read needed for export).
- Builds ZIP in-memory: each file at its `relative_path` with `.md` extension replacing any original extension (e.g., `reports/Q1-Report.md`).
- Streams ZIP as `StreamingResponse`.
- Writes `ingestion_export_downloaded` audit entry with list of exported `document_ids`.
- If no completed documents match the requested IDs: returns `400 NO_EXPORTABLE_DOCUMENTS`.

**Response 200**:
- `Content-Type: application/zip`
- `Content-Disposition: attachment; filename="batch_{batch_id}.zip"`
- Body: ZIP binary stream

**Error responses**:
| Status | Code | Condition |
|--------|------|-----------|
| 400 | `NO_EXPORTABLE_DOCUMENTS` | No completed documents in the selection |
| 404 | `BATCH_NOT_FOUND` | Batch not found |
