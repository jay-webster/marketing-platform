# Tasks: Epic 3 — Ingestion & Markdown Pipeline

**Feature**: Ingestion & Markdown Pipeline
**Branch**: `3-ingestion-pipeline`
**Plan**: `specs/3-ingestion-pipeline/plan.md`
**Spec**: `specs/3-ingestion-pipeline/spec.md`
**Generated**: 2026-03-13

---

## User Story Index

| Story | Scenarios | Description | Priority |
|-------|-----------|-------------|----------|
| US1 | Scenarios 1, 9 | File Submission & Catalog | P1 |
| US2 | Scenario 2 | Async Processing & Status Monitoring | P1 |
| US3 | Scenarios 3, 4 | Document Processing Pipeline | P1 |
| US4 | Scenarios 4, 5 | Failure Handling & Retry | P2 |
| US5 | Scenarios 6, 8 | Output Review (Preview, Approve, Flag) | P2 |
| US6 | Scenario 7 | Export (ZIP Download) | P2 |

---

## Phase 1: Setup

*Project initialization. No dependencies. All tasks parallelizable.*

- [X] T001 [P] Add `pymupdf>=1.24.0`, `python-docx>=1.1.0`, `python-pptx>=1.0.0`, `google-cloud-storage>=2.10.0` to `marketing-platform/requirements.txt`
- [X] T002 [P] Add `GCS_BUCKET_NAME: str` and `WORKER_CONCURRENCY: int = 5` fields to `Settings` class in `marketing-platform/src/config.py`
- [X] T003 [P] Add `GCS_BUCKET_NAME=` and `WORKER_CONCURRENCY=5` entries to `marketing-platform/.env.example` with comments per `specs/3-ingestion-pipeline/quickstart.md`

---

## Phase 2: Foundation — Models & Migration

*Blocking prerequisite for all user stories. T004–T006 parallelizable.*

- [X] T004 [P] Create `marketing-platform/src/models/ingestion_batch.py` — `IngestionBatch` model with all columns from `data-model.md` (`id UUID PK`, `submitted_by FK→users`, `submitted_at`, `source_folder_name`, `status`, `total_documents`, `completed_count`, `failed_count`); `BatchStatus` enum (`in_progress`, `completed`, `completed_with_failures`); indexes on `submitted_by` and `submitted_at DESC`
- [X] T005 [P] Create `marketing-platform/src/models/ingestion_document.py` — `IngestionDocument` model with all columns from `data-model.md` (`id UUID PK`, `batch_id FK→ingestion_batches`, `original_filename`, `original_file_type`, `relative_path`, `file_size_bytes`, `gcs_object_path`, `processing_status`, `failure_reason`, `retry_count`, `queued_at`, `processing_started_at`, `processing_completed_at`, `reprocessing_note`); `ProcessingStatus` enum (`queued`, `processing`, `completed`, `failed`); partial index `WHERE processing_status = 'queued'` for queue worker performance
- [X] T006 [P] Create `marketing-platform/src/models/processed_document.py` — `ProcessedDocument` model with all columns from `data-model.md` (`id UUID PK`, `ingestion_document_id FK→ingestion_documents UNIQUE`, `markdown_content`, `extracted_title`, `extracted_author`, `extracted_date`, `review_status`, `reviewed_by FK→users NULL`, `reviewed_at`, `created_at`); `ReviewStatus` enum (`pending_review`, `approved`, `flagged_for_reprocessing`); index on `review_status`
- [X] T007 Update `marketing-platform/src/models/__init__.py` to export `IngestionBatch`, `BatchStatus`, `IngestionDocument`, `ProcessingStatus`, `ProcessedDocument`, `ReviewStatus`
- [X] T008 Create `marketing-platform/migrations/versions/004_create_ingestion_tables.py` — `upgrade()` creates tables in order: `ingestion_batches` → `ingestion_documents` (with FK + partial index) → `processed_documents` (with UNIQUE FK); all indexes per `data-model.md`; `downgrade()` drops in reverse order

---

## Phase 3: Foundation — Utilities

*Depends on Phase 2. T009–T011 parallelizable. T012 depends on T009+T010+T011.*

- [X] T009 [P] Create `marketing-platform/utils/gcs.py` — implement: `upload_to_gcs(file: UploadFile, bucket: str, batch_id: str, doc_id: str) -> str` (streams `file.file` directly to GCS via `blob.upload_from_file`; wraps with `asyncio.to_thread`; returns `object_name`); `download_stream_from_gcs(bucket: str, object_name: str) -> io.BytesIO` (downloads blob to BytesIO; wraps with `asyncio.to_thread`); `delete_from_gcs(bucket: str, object_name: str) -> None` (idempotent — silences `NotFound`; wraps with `asyncio.to_thread`); module-level `storage.Client()` singleton resolved via ADC

- [X] T010 [P] Create `marketing-platform/utils/extractors.py` — implement: `preflight_check(stream: io.BytesIO, filename: str, size_bytes: int) -> None` (raises `ValueError` for 0-byte or >50 MB files); `extract_text(stream: io.BytesIO, file_type: str) -> str` (dispatcher by extension calling format-specific handlers); `_extract_pdf(stream)` (pymupdf; image-only detection: `get_text()` empty + `get_images()` non-empty → raises `ValueError("No readable text content found")`; catches `fitz.FileDataError`); `_extract_docx(stream)` (python-docx; maps style names Heading1/2/3 → `#`/`##`/`###`, List → `-`; catches `BadZipFile`); `_extract_pptx(stream)` (python-pptx; per-slide `## Slide N` sections + text frames + speaker notes; catches `BadZipFile`); `_extract_csv(stream)` (stdlib csv; emits GFM table with header row + separator + data rows); `_extract_text(stream)` (stdlib open; raises on empty); all sync functions documented for wrapping with `asyncio.to_thread` at call sites; map all library exceptions to human-readable `ValueError` per `data-model.md` failure reasons

- [X] T011 [P] Create `marketing-platform/utils/ingestion_pipeline.py` — implement: `structure_document(client: AsyncAnthropic, extracted_text: str, source_file: str, source_type: str, ingested_by: str, reprocessing_note: str | None = None, model: str = "claude-haiku-4-5-20251001") -> str`; two concurrent API calls via `asyncio.gather`: (1) `tool_use` forced call with `METADATA_TOOL` schema `{title, author?, source_date?, review_status}` + system prompt per `research.md` Decision 3; (2) free-text body structuring call with formatting system prompt; server sets `ingested_at`, `ingested_by`, `source_file`, `source_type` in Python — never from Claude output; assembles YAML frontmatter with `yaml.dump()`; prepends frontmatter to body text; chunking: if `len(extracted_text) / 4 > 90_000` split on structural boundaries and process continuation chunks with body-only prompt; retry wrapper `structure_document_with_retry()` — max 3 attempts on `RateLimitError` (read `Retry-After`), `APIStatusError 529`, `APIConnectionError`; fatal on `APIStatusError 401`

- [X] T012 Create `marketing-platform/utils/queue.py` — implement: `start_queue_workers() -> None` (spawns `settings.WORKER_CONCURRENCY` asyncio tasks via `asyncio.create_task(_worker(i))` + one `asyncio.create_task(_timeout_watchdog())`); `stop_queue_workers() -> None` (cancels all tasks; `asyncio.gather(..., return_exceptions=True)`); `_worker(worker_id: int)` (poll loop: `async with AsyncSessionLocal() as db: SELECT IngestionDocument WHERE processing_status=queued ORDER BY queued_at LIMIT 1 FOR UPDATE SKIP LOCKED`; marks `processing_status=processing`, `processing_started_at=now()`; calls `await process_document(doc_id)`; sleeps `POLL_INTERVAL_SECONDS=1` when queue empty; catches and logs all exceptions — never exits loop); `process_document(doc_id: UUID)` (new `AsyncSessionLocal`; download GCS object → `io.BytesIO`; `asyncio.to_thread(extract_text, stream, file_type)`; `structure_document_with_retry(client, text, ...)`; upsert `ProcessedDocument` row — delete existing if re-processing; mark `processing_status=completed`, `processing_completed_at=now()`; increment `completed_count` on batch; recompute batch `status`; `delete_from_gcs`; `write_audit("ingestion_document_completed", ...)`; on any `Exception`: mark `processing_status=failed`, `failure_reason=human_readable_message`; increment `failed_count` on batch; `write_audit("ingestion_document_failed", ...)`); `_timeout_watchdog()` (every 60s: `UPDATE ingestion_documents SET processing_status='failed', failure_reason='Processing timed out.' WHERE processing_status='processing' AND processing_started_at < now()-5min`)

---

## Phase 4: US1 — File Submission & Catalog

*Goal*: Any authenticated user can submit a folder selection (file list + sizes), receive confirmation with batch ID and per-document status, and list their active batches.

*Independent test*: `POST /api/v1/ingestion/batches` with 2 valid files returns 201 with `batch_id`, `total_documents=2`, documents with `processing_status=queued`. `POST /batches` with no files returns 400 `NO_FILES_SELECTED`. `GET /batches` returns the created batch.

- [X] T013 [US1] Create `marketing-platform/src/api/ingestion.py` with `APIRouter(prefix="/ingestion", tags=["ingestion"])` and implement `POST /batches`: `Depends(get_current_user)`; accept `folder_name: str = Form(...)` and `files: list[UploadFile] = File(...)`; validate: at least one file (400 `NO_FILES_SELECTED`), each file ≤ 50 MB (400 `FILE_TOO_LARGE` with filename), each extension in `{.docx, .pdf, .txt, .md, .pptx, .csv}` (400 `UNSUPPORTED_FILE_TYPE`); create `IngestionBatch(submitted_by=user.id, source_folder_name=folder_name, total_documents=len(files))`; flush to get batch ID; for each file: call `upload_to_gcs(file, settings.GCS_BUCKET_NAME, batch_id, doc_id)` (wrap in try/except → 503 `GCS_UNAVAILABLE`); create `IngestionDocument(batch_id, original_filename, original_file_type, relative_path=file.filename, file_size_bytes, gcs_object_path, processing_status=queued)`; commit; `write_audit("ingestion_batch_submitted", actor_id=user.id, target_id=batch.id, metadata={total_documents, source_folder_name})`; return 201 with batch + document list per `contracts/api-endpoints.md`

- [X] T014 [US1] Add `GET /batches` to `marketing-platform/src/api/ingestion.py`: `Depends(get_current_user)`; query `ingestion_batches WHERE submitted_by = user.id ORDER BY submitted_at DESC`; optional `status` query param filter; return list per `contracts/api-endpoints.md`

- [X] T015 [US1] Mount `ingestion_router` in `marketing-platform/src/main.py` `create_app()` with `app.include_router(ingestion_router, prefix="/api/v1")`

- [X] T016 [P] [US1] Create `marketing-platform/tests/utils/test_extractors.py` with: `test_extract_docx_headings` (fixture DOCX bytes with Heading1/2 styles → output contains `# `); `test_extract_pdf_text` (fixture single-page text PDF → non-empty string); `test_extract_pdf_image_only` (fixture image-only PDF → raises `ValueError` containing "No readable text"); `test_extract_pptx_slides` (fixture 2-slide PPTX → output contains `## Slide 1` and `## Slide 2`); `test_extract_csv_gfm_table` (fixture 3-row CSV → output contains ` | ` separator row); `test_extract_txt` (fixture plaintext bytes → content returned); `test_extract_md_passthrough` (fixture Markdown bytes → content returned unchanged); `test_preflight_empty_raises` (0-byte stream → `ValueError`); `test_preflight_oversized_raises` (stream > 50 MB → `ValueError`); `test_extract_corrupt_docx_raises` (random bytes as .docx → `ValueError`); `test_extract_corrupt_pdf_raises` (random bytes as .pdf → `ValueError`); `test_extract_unknown_type_raises` (.xyz extension → `ValueError`)

- [X] T017 [P] [US1] Create `marketing-platform/tests/api/test_ingestion.py` with test fixtures (mock GCS client via `unittest.mock.patch("utils.gcs.storage.Client")`; mock `structure_document_with_retry` to return stub Markdown): `test_submit_batch_happy_path` (2 valid files → 201, `total_documents=2`, documents with `processing_status=queued`); `test_submit_batch_unauthenticated` (no token → 401); `test_submit_batch_no_files` → 400 `NO_FILES_SELECTED`; `test_submit_batch_file_too_large` (Content-Length > 50 MB → 400 `FILE_TOO_LARGE`); `test_submit_batch_unsupported_type` (.exe file → 400 `UNSUPPORTED_FILE_TYPE`); `test_list_batches_returns_own_batches` (2 batches for user A, 1 for user B → user A sees 2); `test_list_batches_unauthenticated` → 401; `test_list_batches_status_filter` (`?status=in_progress` filters correctly)

---

## Phase 5: US2 — Async Processing & Status Monitoring

*Goal*: After submission, each document updates its status independently. User can navigate away and return; status reflects accurate real-time state within 5 seconds.

*Independent test*: `GET /api/v1/ingestion/batches/{batch_id}` returns batch with per-document `processing_status`. Batch belonging to a different user returns 404.

- [X] T018 [US2] Add `GET /batches/{batch_id}` to `marketing-platform/src/api/ingestion.py`: `Depends(get_current_user)`; query `ingestion_batches WHERE id = batch_id AND submitted_by = user.id`; 404 `BATCH_NOT_FOUND` if not found; join `ingestion_documents` for this batch; join `processed_documents` for review_status where `processing_status = completed`; return full response per `contracts/api-endpoints.md` including per-document `review_status` (null for non-completed docs)

- [X] T019 [US2] Wire queue workers into `_lifespan()` in `marketing-platform/src/main.py`: import `start_queue_workers`, `stop_queue_workers` from `utils.queue`; before `yield`: run startup recovery (`UPDATE ingestion_documents SET processing_status='queued', processing_started_at=null WHERE processing_status='processing'`); call `await start_queue_workers()`; after `yield`: call `await stop_queue_workers()`

- [X] T020 [P] [US2] Create `marketing-platform/tests/utils/test_pipeline.py` — mock `AsyncAnthropic` using `unittest.mock.AsyncMock`: `test_structure_document_returns_valid_markdown` (mock both Claude calls → returned string starts with `---\n`); `test_frontmatter_contains_server_fields` (`ingested_at`, `ingested_by`, `source_file` present, sourced from args not Claude); `test_frontmatter_omits_null_fields` (mock metadata with `author=null` → `author` key absent from YAML); `test_structure_document_rate_limit_retry` (mock 429 then 200 → succeeds after 1 retry); `test_structure_document_overloaded_retry` (mock 529 then 200 → succeeds after 1 retry); `test_structure_document_auth_error_raises_immediately` (mock 401 → raised without retry); `test_structure_document_max_retries_exceeded` (mock 3× 429 → raises)

- [X] T021 [P] [US2] Add to `marketing-platform/tests/api/test_ingestion.py`: `test_get_batch_status_happy_path` (batch with 2 queued docs → 200, both docs in response); `test_get_batch_status_not_found` (wrong batch_id → 404 `BATCH_NOT_FOUND`); `test_get_batch_status_other_user_returns_404` (batch owned by user B, accessed by user A → 404); `test_get_batch_status_unauthenticated` → 401; `test_get_batch_shows_review_status_for_completed_doc` (batch with a completed doc that has a `processed_documents` row → `review_status` present in response)

---

## Phase 6: US3 — Document Processing Pipeline

*Goal*: The queue worker processes a queued document end-to-end — extracts text, structures it via Claude, writes a `ProcessedDocument` row, and transitions the document to `completed`. Failures produce human-readable reasons and do not affect batch peers.

*Independent test*: Insert a `queued` document, start worker, poll until `processing_status = completed`; verify `processed_documents` row exists with valid YAML frontmatter. Insert a corrupt-file document; worker marks it `failed` with specific reason; other documents in same batch unaffected.

- [X] T022 [US3] Create `marketing-platform/tests/utils/test_queue.py` — mock GCS, extractors, and Claude pipeline: `test_process_document_happy_path` (queued doc → after `process_document()`, status=completed, ProcessedDocument row exists, GCS delete called); `test_process_document_creates_correct_processed_doc` (verify `markdown_content` starts with `---`; `extracted_title` populated); `test_process_document_extraction_failure_marks_failed` (extractor raises `ValueError("File is empty.")` → status=failed, `failure_reason="File is empty."`, no ProcessedDocument row); `test_process_document_claude_failure_marks_failed` (pipeline raises → status=failed, human-readable reason); `test_process_document_failure_does_not_affect_sibling` (2 docs in batch; first fails; second processes successfully); `test_batch_status_updated_to_completed` (all docs complete → batch status=completed); `test_batch_status_completed_with_failures` (1 complete, 1 failed → `completed_with_failures`); `test_timeout_watchdog_marks_stale_processing` (doc with `processing_started_at = now()-6min`, status=processing → watchdog marks failed with timeout reason); `test_startup_recovery_resets_processing_to_queued` (doc with status=processing at startup → reset to queued before workers start)

---

## Phase 7: US4 — Failure Handling & Retry

*Goal*: Failed documents surface a specific, human-readable reason. Users can retry individual failed documents without re-submitting the batch.

*Independent test*: `POST /retry` on a failed document returns 200 with `processing_status=queued`, `retry_count` incremented. `POST /retry` on a completed document returns 409.

- [X] T023 [US4] Add `POST /batches/{batch_id}/documents/{doc_id}/retry` to `marketing-platform/src/api/ingestion.py`: `Depends(get_current_user)`; verify batch owned by user (404 `BATCH_NOT_FOUND`); fetch document in batch (404 `DOCUMENT_NOT_FOUND`); verify `processing_status = failed` (409 `DOCUMENT_NOT_FAILED`); reset: `processing_status=queued`, `failure_reason=null`, `processing_started_at=null`, `processing_completed_at=null`; increment `retry_count`; update batch `failed_count -= 1`; recompute batch status; commit; `write_audit("ingestion_document_retried", actor_id=user.id, target_id=doc.id, metadata={batch_id, filename, retry_count})`; return 200 per `contracts/api-endpoints.md`

- [X] T024 [P] [US4] Add to `marketing-platform/tests/api/test_ingestion.py`: `test_retry_failed_document_happy_path` (failed doc → 200, status=queued, retry_count=1); `test_retry_non_failed_document` (completed doc → 409 `DOCUMENT_NOT_FAILED`); `test_retry_queued_document` (queued doc → 409 `DOCUMENT_NOT_FAILED`); `test_retry_document_not_found` → 404 `DOCUMENT_NOT_FOUND`; `test_retry_other_user_batch` → 404 `BATCH_NOT_FOUND`; `test_retry_unauthenticated` → 401

---

## Phase 8: US5 — Output Review

*Goal*: Users can preview the generated Markdown for a completed document, approve it, or flag it for re-processing with an optional note. Flagging immediately re-queues the document.

*Independent test*: `GET /preview` returns `markdown_content` with YAML frontmatter for a completed document. `PATCH /review` with `review_status=approved` returns 200 with updated review status. `PATCH /review` with `flagged_for_reprocessing` transitions `processing_status=queued` and deletes the old `processed_documents` row.

- [X] T025 [US5] Add `GET /batches/{batch_id}/documents/{doc_id}/preview` to `marketing-platform/src/api/ingestion.py`: `Depends(get_current_user)`; verify batch ownership (404); fetch document (404 `DOCUMENT_NOT_FOUND`); verify `processing_status = completed` (409 `DOCUMENT_NOT_COMPLETED`); fetch `processed_documents` row; return per `contracts/api-endpoints.md` with `markdown_content`, `extracted_title`, `extracted_author`, `extracted_date`, `review_status`

- [X] T026 [US5] Add `PATCH /batches/{batch_id}/documents/{doc_id}/review` to `marketing-platform/src/api/ingestion.py`: `Depends(get_current_user)`; request body: `{review_status: "approved" | "flagged_for_reprocessing", reprocessing_note: str | null}`; verify batch ownership + document existence + `processing_status = completed` (409 `DOCUMENT_NOT_COMPLETED`); validate `review_status` enum (422 `INVALID_REVIEW_STATUS`); if `approved`: update `processed_documents.review_status=approved`, `reviewed_by=user.id`, `reviewed_at=now()`; `write_audit("ingestion_document_approved", ...)`; if `flagged_for_reprocessing`: save `reprocessing_note` on `ingestion_documents`; delete existing `processed_documents` row; set `ingestion_documents.processing_status=queued`, `processing_started_at=null`, `processing_completed_at=null`; update batch `completed_count -= 1`; recompute batch status; `write_audit("ingestion_document_flagged", ...)`; commit; return 200 per `contracts/api-endpoints.md`

- [X] T027 [P] [US5] Add to `marketing-platform/tests/api/test_ingestion.py`: `test_preview_completed_document` (completed doc → 200, `markdown_content` present, `review_status=pending_review`); `test_preview_non_completed_document` (queued doc → 409 `DOCUMENT_NOT_COMPLETED`); `test_preview_document_not_found` → 404; `test_preview_unauthenticated` → 401; `test_approve_document` (completed doc → 200, `review_status=approved`); `test_flag_for_reprocessing` (completed doc → 200, `processing_status=queued`, `review_status=flagged_for_reprocessing`); `test_flag_clears_processed_document_row` (verify ProcessedDocument row deleted after flag); `test_review_invalid_status` → 422 `INVALID_REVIEW_STATUS`; `test_review_non_completed_document` → 409 `DOCUMENT_NOT_COMPLETED`; `test_review_unauthenticated` → 401

---

## Phase 9: US6 — Export

*Goal*: Users can download a ZIP archive of selected completed documents as `.md` files with YAML frontmatter, preserving folder hierarchy. Failed documents are excluded.

*Independent test*: `POST /export` with 2 completed docs → 200 `Content-Type: application/zip`. Archive contains 2 `.md` files at the correct relative paths. `POST /export` with only failed docs → 400 `NO_EXPORTABLE_DOCUMENTS`.

- [X] T028 [US6] Add `POST /batches/{batch_id}/export` to `marketing-platform/src/api/ingestion.py`: `Depends(get_current_user)`; request body: `{document_ids: list[UUID]}` (empty list = export all completed); verify batch ownership (404); fetch `processed_documents` joined to `ingestion_documents` WHERE `processing_status = completed` AND (id in `document_ids` OR `document_ids` empty); if no rows: 400 `NO_EXPORTABLE_DOCUMENTS`; build ZIP in-memory: `buf = io.BytesIO(); zipfile.ZipFile(buf, "w", ZIP_DEFLATED)`; for each doc: `arcname = {relative_path_without_original_ext}.md`; `zf.writestr(arcname, processed_doc.markdown_content)`; `buf.seek(0)`; `write_audit("ingestion_export_downloaded", actor_id=user.id, target_id=batch.id, metadata={document_ids: [...], file_count})`; commit audit; return `StreamingResponse(buf, media_type="application/zip", headers={"Content-Disposition": f'attachment; filename="batch_{batch_id}.zip"'})`

- [X] T029 [P] [US6] Add to `marketing-platform/tests/api/test_ingestion.py`: `test_export_all_completed_docs` (batch with 2 completed docs → 200, content-type=application/zip); `test_export_selected_docs` (batch with 3 completed docs, export 2 by ID → ZIP contains exactly 2 files); `test_export_excludes_failed_docs` (selection includes 1 failed + 1 completed → only completed exported, no 400); `test_export_no_completed_docs` → 400 `NO_EXPORTABLE_DOCUMENTS`; `test_export_preserves_folder_hierarchy` (doc with `relative_path=reports/Q1.docx` → ZIP contains `reports/Q1.md`); `test_export_batch_not_found` → 404; `test_export_unauthenticated` → 401

---

## Phase 10: Polish & Cross-Cutting Concerns

*Applies to all user stories. Complete after all story phases pass their independent tests.*

- [X] T030 Verify audit log entry written for all 7 ingestion audit actions (`ingestion_batch_submitted`, `ingestion_document_completed`, `ingestion_document_failed`, `ingestion_document_retried`, `ingestion_document_approved`, `ingestion_document_flagged`, `ingestion_export_downloaded`) — add assertions in relevant test functions in `tests/api/test_ingestion.py` and `tests/utils/test_queue.py`
- [X] T031 Verify `request_id` present on all error responses from ingestion endpoints — add parametrized assertion across all error-case tests in `tests/api/test_ingestion.py`
- [X] T032 Add parametrized test `test_all_ingestion_endpoints_require_auth` in `tests/api/test_ingestion.py` — verifies all 7 endpoints return 401 when called without `Authorization` header
- [X] T033 Add `alembic upgrade head` step to `.github/workflows/ci.yml` to apply migration `004_create_ingestion_tables.py` against test Postgres before running pytest

---

## Dependency Graph

```
T001–T003 (Setup — all parallel)
    │
    ▼
T004–T006 (Models — parallel)
    │
    ▼
T007 → T008 (Export models, migration)
    │
    ├──► T009 (utils/gcs.py)             ─┐
    ├──► T010 (utils/extractors.py)      ─┤
    └──► T011 (utils/ingestion_pipeline.py) ─┤
                                           ▼
                                          T012 (utils/queue.py)
                                           │
                       ┌───────────────────┤
                       ▼                   │
         Phase 4: US1 (T013–T017)          │
         T013 → T014 → T015               │
         T016 [P]                          │
         T017 [P]                          │
                       │                   │
                       ▼                   │
         Phase 5: US2 (T018–T021)          │
         T018, T019                        │
         T020 [P], T021 [P]               │
                       │                   │
                       ▼                   │
         Phase 6: US3 (T022)  ◄────────────┘
         T022
                       │
              ┌────────┼────────┐
              ▼        ▼        ▼
    Phase 7: US4   Phase 8: US5  Phase 9: US6
    T023–T024      T025–T027     T028–T029
              │        │         │
              └────────┴─────────┘
                       │
                       ▼
               Phase 10: Polish
               T030–T033
```

---

## Parallel Execution Opportunities

### Phase 2 (Foundation — Models)
- T004, T005, T006 — three model files, no inter-dependencies

### Phase 3 (Foundation — Utilities)
- T009, T010, T011 — three utility files, no inter-dependencies

### Within Each User Story Phase
- Test tasks `[P]` can be written while implementation tasks are in progress (mock the same interfaces)

### Across Phases 7, 8, 9 (once Phase 6 complete)
- US4 (retry endpoint), US5 (review endpoints), US6 (export endpoint) are all additive changes to `src/api/ingestion.py` and can be implemented in parallel by different agents or sequentially in any order

---

## Implementation Strategy

### MVP Scope (US1 + US2 only)
Complete Phases 1–5 (T001–T021). This delivers:
- `POST /batches` — file upload + GCS + queue
- `GET /batches` + `GET /batches/{id}` — status polling
- Queue worker processing documents end-to-end with Claude
- Per-document status visible to user

This proves the core pipeline before adding review, retry, and export.

### Incremental Delivery Order
1. **Phases 1–3** (T001–T012): Models, migration, all utilities — no HTTP yet
2. **Phase 4** (T013–T017): First running endpoint: `POST /batches` — files accepted, uploaded to GCS, queued
3. **Phase 5** (T018–T021): Status polling live — user can see documents processing
4. **Phase 6** (T022): Processing pipeline end-to-end — documents reach `completed`
5. **Phase 7** (T023–T024): Retry — failed documents recoverable
6. **Phase 8** (T025–T027): Review gate — approve / flag for reprocessing
7. **Phase 9** (T028–T029): Export — ZIP download
8. **Phase 10** (T030–T033): Polish — audit assertions, auth coverage, CI step

---

## Summary

| Metric | Count |
|--------|-------|
| Total tasks | 33 |
| Setup (Phase 1) | 3 |
| Foundation — Models (Phase 2) | 5 |
| Foundation — Utilities (Phase 3) | 4 |
| US1 — File Submission (Phase 4) | 5 |
| US2 — Status Monitoring (Phase 5) | 4 |
| US3 — Processing Pipeline (Phase 6) | 1 |
| US4 — Failure & Retry (Phase 7) | 2 |
| US5 — Output Review (Phase 8) | 3 |
| US6 — Export (Phase 9) | 2 |
| Polish (Phase 10) | 4 |
| Parallelizable [P] tasks | 16 |
| Test tasks | 9 |
