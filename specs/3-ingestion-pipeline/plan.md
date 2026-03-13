# Implementation Plan: Epic 3 — Ingestion & Markdown Pipeline

**Branch**: `3-ingestion-pipeline` | **Date**: 2026-03-13 | **Spec**: `specs/3-ingestion-pipeline/spec.md`

---

## Summary

Users submit local files for AI-powered conversion to structured Markdown. A PostgreSQL-backed worker pool processes documents asynchronously — extracting text with format-specific parsers, structuring it via two concurrent Claude API calls, and producing Markdown files with YAML frontmatter. Users review output in-platform or export a ZIP archive for external tools like Obsidian. Re-processing and per-document retry are supported without affecting batch peers.

---

## Technical Context

**Language/Version**: Python 3.13
**Framework**: FastAPI 0.115+
**Primary Dependencies**: SQLAlchemy 2.0 async / asyncpg, pymupdf, python-docx, python-pptx, google-cloud-storage, anthropic SDK, pyyaml (already present)
**Storage**: PostgreSQL (application state + Markdown output), GCS (transient source files during processing)
**Queue**: PostgreSQL `SELECT FOR UPDATE SKIP LOCKED` — `ingestion_documents` table doubles as queue
**Testing**: pytest + pytest-asyncio, respx for HTTP mocks
**Target Platform**: GCP GKE (single container per client), local Docker Compose for dev
**Performance Goals**: Single document < 60s (SC-3), batch of 20 < 5 minutes (SC-4), catalog display < 2 minutes (SC-1)
**Constraints**: No local container filesystem writes (CONSTITUTION); files go to GCS on upload, workers download to `io.BytesIO`; 50 MB per-file limit; 5-minute per-document processing timeout (FR-2.7)

---

## Constitution Check

*Gate: Must pass before implementation. Re-verified post-design below.*

| Principle | Status | Notes |
|-----------|--------|-------|
| **Authentication Safety** | ✅ PASS | All 7 endpoints depend on `get_current_user` via `require_role` or direct dependency |
| **Environment Discipline** | ✅ PASS | `GCS_BUCKET_NAME`, `WORKER_CONCURRENCY` added to `Settings`; no hardcoded values |
| **DRY** | ✅ PASS | `utils/db.py` reused in `utils/queue.py`; `utils/audit.py` used for all 7 audit events |
| **Stateless Services** | ✅ PASS | Source files streamed to GCS on upload; workers download to `io.BytesIO` (no local disk); worker state is DB-backed |
| **Error Handling** | ✅ PASS | Global exception handler already in `src/main.py`; all failure reasons are human-readable (FR-6.2) |
| **Idempotent Operations** | ✅ PASS | Re-process deletes and re-inserts `processed_documents` (no duplicates); retry resets status idempotently |
| **Admin Security** | N/A | No admin-only endpoints in this epic; all roles can ingest |
| **Audit Logging** | ✅ PASS | 7 audit events defined in `data-model.md`; all state changes write to `audit_log` |

---

## Architecture

### Processing Pipeline Flow

```
HTTP POST /batches (multipart)
  │
  ├── validate files (size, type)
  ├── create IngestionBatch row
  ├── for each file:
  │     ├── create IngestionDocument row (status=queued)
  │     └── stream UploadFile → GCS (no local disk)
  ├── commit
  └── return 201

  [Worker pool — 5 concurrent asyncio tasks]
  │
  ├── SELECT FOR UPDATE SKIP LOCKED (queued docs)
  ├── mark status=processing
  └── process_document(doc_id):
        ├── download GCS object → io.BytesIO
        ├── extract_text(BytesIO, file_type)  → raw_text
        │     (format-specific: pymupdf / python-docx / python-pptx / csv / txt)
        ├── asyncio.gather(
        │     claude_extract_metadata(raw_text),   [tool_use, forced]
        │     claude_structure_body(raw_text)       [free-text]
        │   )
        ├── assemble YAML frontmatter (Python yaml.dump)
        ├── upsert ProcessedDocument row
        ├── mark IngestionDocument status=completed
        ├── recompute + update IngestionBatch counters
        ├── delete GCS object
        └── write audit

  [Timeout watchdog — every 60s]
  └── UPDATE processing_status=failed WHERE processing_started_at < now()-5min AND status=processing
```

### Source Layout

```
marketing-platform/
├── src/
│   ├── api/
│   │   └── ingestion.py             ← APIRouter, 7 endpoints
│   └── models/
│       ├── ingestion_batch.py        ← IngestionBatch + BatchStatus enum
│       ├── ingestion_document.py     ← IngestionDocument + ProcessingStatus enum
│       └── processed_document.py    ← ProcessedDocument + ReviewStatus enum
├── utils/
│   ├── gcs.py                        ← upload_to_gcs, download_stream_from_gcs, delete_from_gcs
│   ├── extractors.py                 ← extract_text(stream, file_type) dispatcher + format handlers
│   ├── ingestion_pipeline.py         ← structure_document() — Claude two-call pattern
│   └── queue.py                      ← start/stop_queue_workers, _worker, _timeout_watchdog
├── migrations/versions/
│   └── 004_create_ingestion_tables.py
└── tests/
    ├── api/
    │   └── test_ingestion.py
    └── utils/
        ├── test_extractors.py
        └── test_pipeline.py
```

---

## Phase 1: Setup

*No dependencies. All tasks parallelizable.*

- [ ] T001 [P] Add new dependencies to `requirements.txt`: `pymupdf>=1.24.0`, `python-docx>=1.1.0`, `python-pptx>=1.0.0`, `google-cloud-storage>=2.10.0`
- [ ] T002 [P] Add `GCS_BUCKET_NAME: str` and `WORKER_CONCURRENCY: int = 5` to `Settings` class in `src/config.py`
- [ ] T003 [P] Add `GCS_BUCKET_NAME` and `WORKER_CONCURRENCY` entries to `marketing-platform/.env.example`

---

## Phase 2: Foundation — Models & Migration

*Blocking prerequisite for all phases. T004–T006 parallelizable.*

- [ ] T004 [P] Create `src/models/ingestion_batch.py` — `IngestionBatch` model + `BatchStatus` enum (`in_progress`, `completed`, `completed_with_failures`) per `data-model.md`
- [ ] T005 [P] Create `src/models/ingestion_document.py` — `IngestionDocument` model + `ProcessingStatus` enum (`queued`, `processing`, `completed`, `failed`) per `data-model.md`; include partial index on `processing_status = 'queued'`
- [ ] T006 [P] Create `src/models/processed_document.py` — `ProcessedDocument` model + `ReviewStatus` enum (`pending_review`, `approved`, `flagged_for_reprocessing`) per `data-model.md`
- [ ] T007 Update `src/models/__init__.py` to export `IngestionBatch`, `BatchStatus`, `IngestionDocument`, `ProcessingStatus`, `ProcessedDocument`, `ReviewStatus`
- [ ] T008 Create `migrations/versions/004_create_ingestion_tables.py` — `upgrade()` creates tables in order: `ingestion_batches` → `ingestion_documents` → `processed_documents` with all indexes per `data-model.md`; `downgrade()` drops in reverse order

---

## Phase 3: Foundation — Utilities

*T009, T010, T011 are parallelizable after Phase 2. T012 depends on T009+T010+T011.*

- [ ] T009 [P] Create `utils/gcs.py` — implement:
  - `upload_to_gcs(file: UploadFile, bucket: str, batch_id: str, doc_id: str) -> str` — streams `file.file` to GCS, returns `object_name`; wraps GCS client in `asyncio.to_thread`
  - `download_stream_from_gcs(bucket: str, object_name: str) -> io.BytesIO` — downloads blob to `BytesIO`; wraps in `asyncio.to_thread`
  - `delete_from_gcs(bucket: str, object_name: str) -> None` — idempotent delete (silences `NotFound`); wraps in `asyncio.to_thread`
  - Module-level singleton `storage.Client()` instantiated once; ADC resolves auth

- [ ] T010 [P] Create `utils/extractors.py` — implement:
  - `preflight_check(stream: io.BytesIO, filename: str, size_bytes: int) -> None` — raises `ValueError` for empty (0 bytes) or oversized (> 50 MB) files
  - `extract_text(stream: io.BytesIO, file_type: str) -> str` — dispatcher by extension
  - `_extract_pdf(stream)` — pymupdf; image-only detection; raises on corrupt
  - `_extract_docx(stream)` — python-docx; heading style → Markdown prefix mapping; raises on corrupt
  - `_extract_pptx(stream)` — python-pptx; per-slide extraction with speaker notes; raises on corrupt
  - `_extract_csv(stream)` — stdlib csv; emits GFM table; raises on empty
  - `_extract_text(stream)` — stdlib; raises on empty
  - All sync functions wrapped with `asyncio.to_thread` at call sites in pipeline
  - Map all library-specific exceptions to `ValueError` with human-readable messages matching FR-6.2

- [ ] T011 [P] Create `utils/ingestion_pipeline.py` — implement:
  - `structure_document(client: AsyncAnthropic, extracted_text: str, source_file: str, source_type: str, ingested_by: str, reprocessing_note: str | None) -> str`
  - Two concurrent API calls via `asyncio.gather`: `tool_use` forced call for metadata + free-text call for Markdown body
  - Model: `claude-haiku-4-5-20251001`; token ceiling: 90K (chunking for overflow)
  - Assembles YAML frontmatter with `yaml.dump()` (server sets `ingested_at`, `ingested_by`, `source_file`, `source_type`); prepends to body
  - Retry on `RateLimitError` / `APIStatusError 529` / `APIConnectionError` — max 3 attempts, exponential backoff
  - METADATA_TOOL schema: `{title, author?, source_date?, review_status}`

- [ ] T012 Create `utils/queue.py` — implement:
  - `start_queue_workers() -> None` — spawns `WORKER_CONCURRENCY` asyncio tasks (`_worker(i)`) + one `_timeout_watchdog()` task; called from lifespan
  - `stop_queue_workers() -> None` — cancels all tasks; called from lifespan teardown
  - `_worker(worker_id)` — poll loop: `SELECT FOR UPDATE SKIP LOCKED WHERE processing_status = 'queued' ORDER BY queued_at LIMIT 1`; claims doc; calls `process_document(db, doc_id)`; sleeps 1s when queue empty
  - `process_document(db, doc_id)` — download from GCS → extract text → structure via Claude → upsert `ProcessedDocument` → update `IngestionDocument` status + batch counters → delete GCS object → write audit
  - `_timeout_watchdog()` — every 60s: `UPDATE ingestion_documents SET processing_status='failed', failure_reason='Processing timed out.' WHERE processing_status='processing' AND processing_started_at < now()-5min`
  - Startup recovery (called before `start_queue_workers` in lifespan): reset `processing` → `queued` for any rows left from prior crash

---

## Phase 4: API Endpoints

*Depends on Phase 2 + Phase 3 complete.*

- [ ] T013 Create `src/api/ingestion.py` with `APIRouter(prefix="/ingestion", tags=["ingestion"])` and implement all 7 endpoints per `contracts/api-endpoints.md`:

  - **POST `/batches`** — `require_role(Role.ADMIN, Role.MARKETING_MANAGER, Role.MARKETER)` or `get_current_user`; validate files (size + type); create `IngestionBatch`; for each file `upload_to_gcs()` + create `IngestionDocument(status=queued)`; commit; return 201

  - **GET `/batches`** — `get_current_user`; query `ingestion_batches WHERE submitted_by = user.id`; optional `status` filter; return list

  - **GET `/batches/{batch_id}`** — `get_current_user`; fetch batch + documents; 404 if not found or not owned by user; return full status

  - **POST `/batches/{batch_id}/documents/{doc_id}/retry`** — `get_current_user`; verify ownership; `processing_status` must be `failed` (409 otherwise); reset to `queued`; increment `retry_count`; write `ingestion_document_retried` audit; return 200

  - **GET `/batches/{batch_id}/documents/{doc_id}/preview`** — `get_current_user`; verify ownership; `processing_status` must be `completed` (409 otherwise); fetch `processed_documents` row; return `markdown_content` + metadata fields

  - **PATCH `/batches/{batch_id}/documents/{doc_id}/review`** — `get_current_user`; verify ownership; validate `review_status` enum; for `flagged_for_reprocessing`: save `reprocessing_note` on `ingestion_documents`, delete `processed_documents` row, set `processing_status = queued`; for `approved`: update `review_status`, `reviewed_by`, `reviewed_at`; write audit; return 200

  - **POST `/batches/{batch_id}/export`** — `get_current_user`; fetch `processed_documents` for requested IDs (or all completed in batch); build ZIP in-memory (`zipfile.ZipFile` + `io.BytesIO`); each file at `{relative_path_without_ext}.md`; write `ingestion_export_downloaded` audit; return `StreamingResponse(application/zip)`

- [ ] T014 Mount `ingestion_router` in `src/main.py` `create_app()` with prefix `/api/v1`
- [ ] T015 Wire queue workers into `_lifespan()` in `src/main.py`: add startup recovery block → `await start_queue_workers()` before `yield` → `await stop_queue_workers()` after `yield`

---

## Phase 5: Tests

*Parallelizable after Phase 4. T016–T018 independent of each other.*

- [ ] T016 [P] Create `tests/utils/test_extractors.py`:
  - `test_extract_docx_happy_path` — fixture DOCX with headings/lists → extracted text contains `# Heading`
  - `test_extract_pdf_happy_path` — fixture PDF with text → non-empty string
  - `test_extract_pdf_image_only` — fixture image-only PDF → raises `ValueError` with `No readable text`
  - `test_extract_pptx_happy_path` — fixture PPTX → per-slide sections present
  - `test_extract_csv_happy_path` — CSV fixture → GFM table format
  - `test_extract_txt_happy_path` — plaintext fixture → content returned
  - `test_extract_empty_file_raises` — empty BytesIO → `ValueError`
  - `test_extract_corrupt_docx_raises` — invalid bytes as DOCX → `ValueError`
  - `test_extract_corrupt_pdf_raises` — invalid bytes as PDF → `ValueError`
  - `test_preflight_empty_raises` / `test_preflight_oversized_raises`

- [ ] T017 [P] Create `tests/utils/test_pipeline.py` — mock `AsyncAnthropic` with `respx` or `unittest.mock.AsyncMock`:
  - `test_structure_document_happy_path` — mock both Claude calls; verify returned Markdown has YAML frontmatter + body
  - `test_frontmatter_server_fields_set_by_server` — `ingested_at`, `ingested_by`, `source_file` come from server args, not Claude tool output
  - `test_structure_document_rate_limit_retry` — mock 429 then 200; verify 1 retry
  - `test_structure_document_overloaded_retry` — mock 529 then 200; verify retry
  - `test_structure_document_auth_error_no_retry` — mock 401; verify raised immediately

- [ ] T018 [P] Create `tests/api/test_ingestion.py` — using existing `async_client`, `admin_user`, `admin_token` fixtures; mock GCS and Claude:
  - `test_submit_batch_happy_path` — valid files → 201, batch_id present, documents with status=queued
  - `test_submit_batch_unauthenticated` → 401
  - `test_submit_batch_no_files` → 400 NO_FILES_SELECTED
  - `test_submit_batch_file_too_large` → 400 FILE_TOO_LARGE
  - `test_submit_batch_unsupported_type` → 400 UNSUPPORTED_FILE_TYPE
  - `test_get_batch_status` — created batch → 200 with document list
  - `test_get_batch_not_found` → 404
  - `test_get_batch_other_user_not_found` — batch belongs to different user → 404
  - `test_retry_failed_document` — document in failed state → 200, status=queued
  - `test_retry_non_failed_document` → 409 DOCUMENT_NOT_FAILED
  - `test_preview_completed_document` — completed doc → 200 with markdown_content
  - `test_preview_non_completed_document` → 409 DOCUMENT_NOT_COMPLETED
  - `test_approve_document` — completed doc → review_status=approved
  - `test_flag_for_reprocessing` — completed doc → processing_status=queued, review_status=flagged
  - `test_export_happy_path` — completed docs → 200, Content-Type: application/zip
  - `test_export_no_completable_documents` → 400 NO_EXPORTABLE_DOCUMENTS
  - `test_export_excludes_failed_documents` — selection contains failed docs → only completed included
  - `test_all_endpoints_require_auth` — parametrized: all 7 endpoints return 401 without token

---

## Phase 6: Polish

- [ ] T019 Verify audit log entry written for all 7 ingestion audit actions in test suite
- [ ] T020 Verify `request_id` present on all error responses from ingestion endpoints
- [ ] T021 Add `alembic upgrade head` step for new migration in CI workflow

---

## Risk Table

| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|------------|
| Claude API rate limiting under batch load | Medium | Processing delays | Exponential backoff with 3 retries; per-document failure does not affect batch peers |
| pymupdf AGPL licence concern if deployment model changes | Low | Legal | Isolated in `utils/extractors.py`; swap to pypdf+pdfminer.six without API changes |
| GCS latency on upload for large files (50 MB) | Low | Slow POST /batches response | `blob.upload_from_file` uses resumable upload for >8 MB; acceptable for batch submission |
| Worker pool starvation on busy batches | Low | Queue delay | `WORKER_CONCURRENCY` is env-configurable; can be raised without code change |
| Image-only PDFs silently producing empty Markdown | Medium | Poor UX | pymupdf image detection is reliable; `Failed: No readable text content found` surfaced to user |

---

## Environment Variables

| Variable | Purpose | Required | Default |
|----------|---------|----------|---------|
| `GCS_BUCKET_NAME` | GCS bucket for ingestion source files | Yes | — |
| `WORKER_CONCURRENCY` | Concurrent queue worker count | No | `5` |
| `GOOGLE_APPLICATION_CREDENTIALS` | SA key path (local dev only) | No | ADC |
| `ANTHROPIC_API_KEY` | Claude API access (already in stack) | Yes | — |

---

## Dependency Graph

```
T001–T003 (Setup — parallel)
    │
    ▼
T004–T006 (Models — parallel)
    │
    ▼
T007 → T008 (Export models, migration)
    │
    ├──► T009 (GCS utils)    ─┐
    ├──► T010 (Extractors)   ─┤
    └──► T011 (Pipeline)     ─┤
                               ▼
                              T012 (Queue worker) ──► T013 (API endpoints)
                                                            │
                                                       T014 → T015
                                                            │
                                          ┌────────────────┤
                                          ▼                ▼
                                        T016            T017    T018
                                          │
                                          ▼
                                    T019 → T020 → T021
```

---

## Constitution Check (Post-Design Re-verification)

- [x] **AUTH_SAFE** — Every endpoint in `src/api/ingestion.py` depends on `get_current_user`. The queue worker runs as an internal process with no HTTP surface.
- [x] **DRY** — `utils/db.py` (AsyncSessionLocal) used in `utils/queue.py`. `utils/audit.py` (write_audit) used for all 7 audit events. No new DB or audit primitives written.
- [x] **NON_BLOCKING** — All workers are asyncio tasks. GCS and extractor calls wrapped in `asyncio.to_thread`. Claude calls use `AsyncAnthropic`. No blocking I/O on the event loop.
