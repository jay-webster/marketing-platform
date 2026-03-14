# Data Model: Content Sync & Ingestion Pipeline

**Feature**: 006-content-sync-ingest
**Date**: 2026-03-14

---

## New Tables

### synced_documents

Represents a single `.md` file discovered in the connected GitHub repository via sync. One row per unique file path per connection.

| Column | Type | Nullable | Notes |
|---|---|---|---|
| `id` | UUID PK | No | |
| `connection_id` | UUID FK → github_connections | No | ON DELETE CASCADE |
| `repo_path` | TEXT | No | Full path within repo, e.g. `content/blog/article.md` |
| `title` | TEXT | Yes | Extracted from YAML frontmatter `title` field, or filename |
| `raw_content` | TEXT | No | Full file content (Markdown) |
| `content_sha` | TEXT | No | Git blob SHA — used for change detection between syncs |
| `folder` | TEXT | No | Configured folder this file belongs to, e.g. `content/blog` |
| `is_active` | BOOLEAN | No | False when file no longer exists in repo (soft delete) |
| `last_synced_at` | TIMESTAMP WITH TZ | No | Timestamp of most recent successful sync of this file |
| `created_at` | TIMESTAMP WITH TZ | No | First time this file was discovered |
| `updated_at` | TIMESTAMP WITH TZ | No | Last time content was updated |

**Constraints**:
- Unique: `(connection_id, repo_path)`
- Index on `(connection_id, is_active)` for content browser queries
- Index on `content_sha` for change detection

---

### sync_runs

Audit record of each GitHub sync execution (manual or scheduled).

| Column | Type | Nullable | Notes |
|---|---|---|---|
| `id` | UUID PK | No | |
| `connection_id` | UUID FK → github_connections | No | ON DELETE CASCADE |
| `triggered_by` | UUID FK → users | Yes | Null for scheduled runs |
| `trigger_type` | TEXT | No | `"manual"` \| `"scheduled"` |
| `started_at` | TIMESTAMP WITH TZ | No | |
| `finished_at` | TIMESTAMP WITH TZ | Yes | Null while running |
| `outcome` | TEXT | No | `"in_progress"` \| `"success"` \| `"partial"` \| `"failed"` \| `"interrupted"` |
| `files_indexed` | INTEGER | No | New + updated files indexed in this run |
| `files_removed` | INTEGER | No | Files soft-deleted (no longer in repo) |
| `files_unchanged` | INTEGER | No | Files skipped (SHA unchanged) |
| `error_detail` | TEXT | Yes | Set on `"failed"` outcome |

**Index on** `(connection_id, started_at DESC)` for sync history queries.
**Index on** `(connection_id, outcome)` WHERE `outcome = 'in_progress'` for concurrent-sync prevention check.

---

## Modified Tables

### ingestion_documents — new columns

The existing upload pipeline is extended to track the GitHub PR workflow.

| Column | Type | Nullable | Notes |
|---|---|---|---|
| `destination_folder` | TEXT | Yes | Set by admin at approval time; the target repo folder |
| `github_branch` | TEXT | Yes | e.g. `ingest/report-2026-1741962000` |
| `github_pr_number` | INTEGER | Yes | GitHub PR number |
| `github_pr_url` | TEXT | Yes | Full GitHub PR URL for linking |

**New `ProcessingStatus` values** added to the existing enum:
- `PR_OPEN = "pr_open"` — worker created branch, committed file, opened PR
- `MERGED = "merged"` — admin merged PR in-app; post-merge sync triggered

**Status transition diagram** for the PR workflow:
```
pending_approval → queued → processing → pr_open → merged
                                       ↘ failed
pending_approval → rejected  (admin rejects before processing)
pr_open → rejected            (admin closes PR in-app)
```

**Note**: `submitted_by` is on `ingestion_batch`, not on `ingestion_document`. Email notifications look up the submitter via `batch.submitted_by`. No change needed.

---

### knowledge_base_documents — new column + FK change

| Column | Type | Nullable | Notes |
|---|---|---|---|
| `processed_document_id` | UUID FK → processed_documents | **Yes** (was NOT NULL) | Source for file upload pipeline |
| `synced_document_id` | UUID FK → synced_documents | Yes (new) | Source for GitHub sync pipeline |

**Constraint**: Exactly one of `processed_document_id` or `synced_document_id` must be non-null (CHECK constraint).

**Migration note**: `processed_document_id` is changed from `NOT NULL` to `NULLABLE`. Existing rows are unaffected (they all have a value). New rows from sync have `synced_document_id` set.

---

### github_connections — new columns

| Column | Type | Nullable | Notes |
|---|---|---|---|
| `last_synced_at` | TIMESTAMP WITH TZ | Yes | Updated on each successful sync run finish |
| `default_branch` | TEXT | Yes | Cached default branch name (e.g. `main`), populated on first sync |

---

## Entity Relationships

```
github_connections
  ├── sync_runs (many) — one per sync execution
  ├── synced_documents (many) — one per indexed .md file
  └── scaffolding_run (many) — existing

synced_documents
  └── knowledge_base_documents (one) — indexing state

knowledge_base_documents
  ├── processed_document_id → processed_documents (upload pipeline)
  ├── synced_document_id → synced_documents (sync pipeline)
  └── content_chunks (many, via indexer)

ingestion_documents (upload pipeline)
  ├── ingestion_batch → ingestion_batch (submitter via batch.submitted_by)
  └── processed_documents (one, after text extraction)
```

---

## Migration Plan

### Migration 006a — Add synced_documents + sync_runs tables
- CREATE TABLE `synced_documents`
- CREATE TABLE `sync_runs`
- CREATE indexes

### Migration 006b — Extend knowledge_base_documents
- ALTER TABLE `knowledge_base_documents` ALTER COLUMN `processed_document_id` DROP NOT NULL
- ALTER TABLE `knowledge_base_documents` ADD COLUMN `synced_document_id` UUID REFERENCES `synced_documents(id)` ON DELETE CASCADE
- ADD CHECK constraint: `(processed_document_id IS NOT NULL) != (synced_document_id IS NOT NULL)` (XOR)
- CREATE UNIQUE INDEX on `synced_document_id` (when non-null, one KB doc per synced doc)

### Migration 006c — Extend ingestion_documents
- ADD COLUMN `destination_folder` TEXT
- ADD COLUMN `github_branch` TEXT
- ADD COLUMN `github_pr_number` INTEGER
- ADD COLUMN `github_pr_url` TEXT

### Migration 006d — Extend github_connections
- ADD COLUMN `last_synced_at` TIMESTAMP WITH TZ
- ADD COLUMN `default_branch` TEXT
