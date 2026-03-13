# Data Model: Epic 3 — Ingestion & Markdown Pipeline

**Branch**: `3-ingestion-pipeline`
**Generated**: 2026-03-13

---

## Entity Overview

```
users (Epic 1)
  │
  ├──► ingestion_batches (1 per submission session)
  │         │
  │         └──► ingestion_documents (1 per submitted file)
  │                   │
  │                   └──► processed_documents (1 per Completed document, 1:1)
  │
  └──► processed_documents.reviewed_by (nullable FK)
```

---

## Table: `ingestion_batches`

| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| `id` | UUID | PK, DEFAULT gen_random_uuid() | Batch identifier |
| `submitted_by` | UUID | FK → users(id) NOT NULL | User who initiated the batch |
| `submitted_at` | TIMESTAMPTZ | NOT NULL, DEFAULT now() | Submission timestamp |
| `source_folder_name` | TEXT | NOT NULL | Display name of root folder selected |
| `status` | VARCHAR(30) | NOT NULL, DEFAULT 'in_progress' | `in_progress` \| `completed` \| `completed_with_failures` |
| `total_documents` | INTEGER | NOT NULL, DEFAULT 0 | Count of documents submitted |
| `completed_count` | INTEGER | NOT NULL, DEFAULT 0 | Count with `processing_status = completed` |
| `failed_count` | INTEGER | NOT NULL, DEFAULT 0 | Count with `processing_status = failed` |

**Indexes**:
- `idx_ingestion_batches_submitted_by` ON `(submitted_by)`
- `idx_ingestion_batches_submitted_at` ON `(submitted_at DESC)`

**Status transitions**:
```
in_progress → completed              (all docs Completed)
in_progress → completed_with_failures (all docs terminal, ≥1 Failed)
```
Batch status is recomputed on each document status update.

---

## Table: `ingestion_documents`

This table is also the **processing queue**. Workers claim rows using `SELECT FOR UPDATE SKIP LOCKED` on `processing_status = 'queued'`.

| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| `id` | UUID | PK, DEFAULT gen_random_uuid() | Document identifier |
| `batch_id` | UUID | FK → ingestion_batches(id) NOT NULL | Parent batch |
| `original_filename` | TEXT | NOT NULL | Source file name (e.g., `Q1-Report.docx`) |
| `original_file_type` | VARCHAR(10) | NOT NULL | Source extension (`.docx`, `.pdf`, `.pptx`, `.csv`, `.txt`, `.md`) |
| `relative_path` | TEXT | NOT NULL | Path relative to batch root (e.g., `reports/Q1-Report.docx`) |
| `file_size_bytes` | BIGINT | NOT NULL | File size at submission |
| `gcs_object_path` | TEXT | NOT NULL | GCS object name: `batches/{batch_id}/{doc_id}/{filename}` |
| `processing_status` | VARCHAR(20) | NOT NULL, DEFAULT 'queued' | `queued` \| `processing` \| `completed` \| `failed` |
| `failure_reason` | TEXT | NULL | Human-readable failure description (populated on `failed`) |
| `retry_count` | INTEGER | NOT NULL, DEFAULT 0 | Total processing attempts |
| `queued_at` | TIMESTAMPTZ | NOT NULL, DEFAULT now() | When document entered the queue |
| `processing_started_at` | TIMESTAMPTZ | NULL | When worker claimed the document |
| `processing_completed_at` | TIMESTAMPTZ | NULL | When processing reached terminal state |
| `reprocessing_note` | TEXT | NULL | Optional user context for re-processing |

**Indexes**:
- `idx_ingestion_documents_batch_id` ON `(batch_id)`
- `idx_ingestion_documents_processing_status` ON `(processing_status)` WHERE `processing_status = 'queued'` (partial — queue worker performance)
- `idx_ingestion_documents_queued_at` ON `(queued_at)` WHERE `processing_status = 'queued'` (partial — FIFO ordering)

**Processing status transitions**:
```
queued → processing           (worker claims)
processing → completed        (pipeline succeeds)
processing → failed           (pipeline error or timeout)
failed → queued               (user retries)
completed → queued            (user flags for re-processing)
```

**Failure reasons** (FR-6.2 — human-readable, no generic messages):
- `"File is empty."`
- `"File could not be read — it may be corrupted."`
- `"No readable text content found — the file may contain only images."`
- `"Processing timed out — the file may be too large or complex."`
- `"Unsupported file type: {ext}"` (should not occur post-submission validation)

---

## Table: `processed_documents`

One row per successfully completed `IngestionDocument`. Replaced (not versioned) on re-processing.

| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| `id` | UUID | PK, DEFAULT gen_random_uuid() | Output identifier |
| `ingestion_document_id` | UUID | FK → ingestion_documents(id) UNIQUE NOT NULL | Source document (1:1) |
| `markdown_content` | TEXT | NOT NULL | Full Markdown including YAML frontmatter |
| `extracted_title` | TEXT | NULL | Title identified by pipeline |
| `extracted_author` | TEXT | NULL | Author identified by pipeline |
| `extracted_date` | TEXT | NULL | Date from source document (ISO 8601 if parseable, else raw) |
| `review_status` | VARCHAR(30) | NOT NULL, DEFAULT 'pending_review' | `pending_review` \| `approved` \| `flagged_for_reprocessing` |
| `reviewed_by` | UUID | FK → users(id) NULL | User who last set review status |
| `reviewed_at` | TIMESTAMPTZ | NULL | Timestamp of last review action |
| `created_at` | TIMESTAMPTZ | NOT NULL, DEFAULT now() | When this output was generated |

**Indexes**:
- `idx_processed_documents_ingestion_document_id` ON `(ingestion_document_id)` (already UNIQUE, covers this)
- `idx_processed_documents_review_status` ON `(review_status)`

**Re-processing behaviour**: On re-process, the existing `processed_documents` row is deleted and a new one is inserted after the pipeline completes. No version history retained (Assumption A-5).

---

## Enums (Python SQLAlchemy)

```python
class BatchStatus(str, enum.Enum):
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    COMPLETED_WITH_FAILURES = "completed_with_failures"

class ProcessingStatus(str, enum.Enum):
    QUEUED = "queued"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"

class ReviewStatus(str, enum.Enum):
    PENDING_REVIEW = "pending_review"
    APPROVED = "approved"
    FLAGGED_FOR_REPROCESSING = "flagged_for_reprocessing"
```

---

## YAML Frontmatter Schema

Every `processed_documents.markdown_content` opens with this block:

```yaml
---
title: "Q1 Marketing Report"
source_file: "Q1-Report.docx"
source_type: ".docx"
author: "Jane Smith"           # omitted if not found
source_date: "2026-01-15"      # omitted if not found
ingested_at: "2026-03-13T14:22:00+00:00"
ingested_by: "Jane Smith"
review_status: "pending_review"
---
```

Fields `ingested_at`, `ingested_by`, `source_file`, `source_type` are always set by server code — never by Claude. Fields `author`, `source_date` are nullable and omitted from frontmatter if None.

---

## Supported File Types

| Extension | MIME type | Parser |
|-----------|-----------|--------|
| `.docx` | `application/vnd.openxmlformats-officedocument.wordprocessingml.document` | python-docx |
| `.pdf` | `application/pdf` | pymupdf |
| `.txt` | `text/plain` | stdlib |
| `.md` | `text/markdown` | stdlib |
| `.pptx` | `application/vnd.openxmlformats-officedocument.presentationml.presentation` | python-pptx |
| `.csv` | `text/csv` | stdlib csv |

---

## Batch Status Computation

Batch `status` is recomputed after every `ingestion_documents` status change:

```
if all documents are in {completed, failed}:
    if failed_count == 0:
        batch.status = "completed"
    else:
        batch.status = "completed_with_failures"
else:
    batch.status = "in_progress"
```

`completed_count` and `failed_count` are maintained as running counters (incremented/decremented on status transitions) to avoid full-table COUNT queries on every poll.

---

## Audit Log Events (FR-6.5)

All ingestion audit events use `utils/audit.py` `write_audit()`.

| Action | Actor | Target | Metadata |
|--------|-------|--------|----------|
| `ingestion_batch_submitted` | submitting user | batch_id | `{total_documents, source_folder_name}` |
| `ingestion_document_completed` | system (null) | doc_id | `{batch_id, filename}` |
| `ingestion_document_failed` | system (null) | doc_id | `{batch_id, filename, reason}` |
| `ingestion_document_retried` | requesting user | doc_id | `{batch_id, filename, retry_count}` |
| `ingestion_document_approved` | reviewing user | doc_id | `{batch_id}` |
| `ingestion_document_flagged` | reviewing user | doc_id | `{batch_id, reprocessing_note}` |
| `ingestion_export_downloaded` | requesting user | batch_id | `{document_ids, file_count}` |
