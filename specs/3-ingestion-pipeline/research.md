# Research: Epic 3 — Ingestion & Markdown Pipeline

**Branch**: `3-ingestion-pipeline`
**Generated**: 2026-03-13
**Status**: All decisions resolved — no NEEDS CLARIFICATION remaining

---

## Decision 1: Async Processing Queue

**Decision**: PostgreSQL-backed job queue using `SELECT FOR UPDATE SKIP LOCKED`

**Rationale**:
- Zero new infrastructure — PostgreSQL is already running; `utils/db.py` async engine is reusable directly
- `ingestion_documents` table doubles as the queue table — `processing_status` column is the job state
- Fully restart-safe: all job state is durable in Postgres. On container restart, `Processing` rows are reset to `Queued` at lifespan startup
- `SKIP LOCKED` gives worker-to-worker isolation at the DB level — a slow document cannot block other workers (directly satisfies FR-2.4)
- Timeout enforcement is a simple 60s watchdog that marks rows with `processing_started_at < now() - 5min` and status still `Processing` as Failed (FR-2.7)
- Workers are asyncio tasks (`asyncio.create_task`) — fully non-blocking, NON_BLOCKING compliant
- Retry is trivially `UPDATE processing_status = 'queued'` (FR-6.3)

**Alternatives considered**:
- **ARQ (Async Redis Queue)**: Asyncio-native and well-suited, but requires Redis — a new infrastructure dependency not present in `docker-compose.yml` or K8s manifests. Unjustified for single-container-per-client deployment.
- **Celery**: Eliminated. Not asyncio-native; running Celery with asyncpg/SQLAlchemy async requires `asyncio.run()` wrappers that spin up new event loops per task — a known footgun with asyncpg connection pools.
- **FastAPI BackgroundTasks**: Eliminated. Not restart-safe — tasks live in process memory only. Directly violates FR-2.1 (processing must survive page navigation / container restart).
- **asyncio.Queue + Postgres hybrid**: Dominated by the pure Postgres approach — same infrastructure, more complex dual-state synchronization, more fragile.

**Implementation pattern**: 5 concurrent worker coroutines (`WORKER_CONCURRENCY=5` via env). Each polls for `Queued` rows with `SELECT ... FOR UPDATE SKIP LOCKED`, claims one, processes it, updates status. Poll interval: 1 second (negligible load for single-tenant). Watchdog coroutine runs every 60 seconds.

---

## Decision 2: Document Parsers

**Decision**: pymupdf (PDF), python-docx (DOCX), python-pptx (PPTX), stdlib csv + open (CSV/TXT/MD)

| Format | Library | pip name | License | Async |
|--------|---------|----------|---------|-------|
| .pdf | pymupdf | `pymupdf` | AGPL-3.0 | `asyncio.to_thread()` |
| .docx | python-docx | `python-docx` | MIT | `asyncio.to_thread()` |
| .pptx | python-pptx | `python-pptx` | MIT | `asyncio.to_thread()` |
| .csv | stdlib csv | (stdlib) | PSF | `asyncio.to_thread()` |
| .txt / .md | stdlib open | (stdlib) | PSF | `asyncio.to_thread()` |

**Rationale**:
- **pymupdf**: Best-in-class text + structure extraction. `page.get_text("text")` preserves reading order. `page.find_tables()` (v1.23+) enables table extraction. Image-only PDF detection: `get_text()` returns `""` AND `get_images()` returns non-empty list → `Failed: No readable text content found`. AGPL-3.0 is acceptable for internal single-org deployment.
- **python-docx**: Preserves paragraph styles (`Heading 1`/`2`/`3`, `List Bullet`) — directly mappable to Markdown `#`/`##`/`###`/`-`. Preferred over mammoth (which targets HTML output) because we need Markdown-ready structure.
- **python-pptx**: Only maintained pure-Python PPTX library. Text frame extraction per slide is sufficient for LLM input.
- **stdlib for CSV/TXT/MD**: No dependencies. CSV is emitted as a Markdown table for LLM consumption. `.md` files are passed directly to the structuring step without pre-processing.

**AGPL note**: pymupdf's AGPL-3.0 requires open-sourcing if you distribute as a SaaS to external users. This platform is an internal per-client deployment — AGPL is acceptable. If this changes, replace with pypdf (BSD-3) + pdfminer.six (MIT), accepting reduced table extraction quality.

**Corrupt/empty file detection**:

| Format | Exception |
|--------|-----------|
| PDF | `fitz.FileDataError` |
| DOCX | `zipfile.BadZipFile`, `docx.opc.exceptions.PackageNotFoundError` |
| PPTX | `zipfile.BadZipFile`, `pptx.exc.PackageNotFoundError` |
| CSV | `csv.Error`, `UnicodeDecodeError` |
| TXT/MD | `UnicodeDecodeError` |

All extractors are wrapped in a common `preflight_check(path, max_bytes=50MB)` that gates on file existence, zero size, and size limit.

---

## Decision 3: Claude API Integration Pattern

**Decision**: `claude-haiku-4-5-20251001`, two concurrent API calls — `tool_use` for metadata extraction + free-text for Markdown body

**Rationale**:
- Document structuring is a **formatting task, not a reasoning task** — Haiku quality is sufficient and ~4× cheaper than Sonnet at scale.
- Two concurrent calls (`asyncio.gather`) cuts wall-clock latency roughly in half vs sequential.
- `tool_use` with `tool_choice: forced` for frontmatter metadata gives schema-enforced JSON — eliminates fragile YAML fence parsing. Server-controlled fields (`ingested_at`, `ingested_by`, `source_file`, `source_type`) are set in Python after the tool call returns, never by Claude.
- Free-text mode for the Markdown body produces better Markdown than structured output mode.
- Frontmatter is assembled in Python with `yaml.dump()` and prepended to the body.

**Token limit strategy**:
- 200K context window. Documents up to ~90K tokens (estimated as `len(text) / 4`) processed in a single pass.
- Documents exceeding ~90K tokens are split on structural boundaries (double newlines, detected section headings) — chunk 0 gets the full prompt (metadata + body), chunks 1..N get a continuation-only body prompt. Merged: frontmatter from chunk 0 + bodies joined.
- This handles the 50 MB file size limit. A 50 MB plain text file would be ~12.5M characters / 4 = ~3.1M tokens — in practice, no real document contains 3.1M tokens of prose. Chunking is a safety net for edge cases.

**Error handling**:
- `RateLimitError` (429): retry with `Retry-After` header or exponential backoff, max 3 attempts
- `APIStatusError` 529 (overloaded): exponential backoff, max 3 attempts
- `APIStatusError` 400 context length: raise `ValueError` — caller must chunk
- `APIConnectionError` / `APITimeoutError`: retry with backoff, max 3 attempts
- Auth errors (401): fatal — do not retry

---

## Decision 4: File Storage — GCS

**Decision**: GCP Cloud Storage for all ingestion file artifacts. Files stream from `UploadFile` directly to GCS — no local disk write.

**Rationale**: CONSTITUTION explicitly requires "GCP Cloud Storage for transient file processing." Files must never touch the container filesystem.

**Object naming**: `batches/{batch_id}/{doc_id}/{filename}`

**Auth**: Workload Identity on GKE (no key files in production). `GOOGLE_APPLICATION_CREDENTIALS` env var for local dev. `google-cloud-storage` client resolves via ADC automatically.

**Worker flow**: Download to `io.BytesIO` stream → pass to extractor as file-like object → delete GCS object after successful processing (or retain for retry; delete on final terminal state).

**Upload**: `blob.upload_from_file(file.file, ...)` with `asyncio.to_thread` — streams multipart body directly to GCS, no buffering to local disk.

---

## Decision 5: ZIP Export

**Decision**: stdlib `zipfile` + `io.BytesIO` + FastAPI `StreamingResponse`

**Rationale**: No additional dependencies. In-memory buffer is appropriate for typical batch sizes (20 docs × avg 2 MB = ~40 MB uncompressed, smaller compressed). `ZIP_DEFLATED` compression used. `relative_path` from DB used as `arcname` in `ZipFile.writestr()` to preserve folder hierarchy. Markdown content is read from the `processed_documents` table — no GCS read needed for export (Markdown is stored in Postgres, not GCS).

---

## New Dependencies

```
# Add to requirements.txt
pymupdf>=1.24.0
python-docx>=1.1.0
python-pptx>=1.0.0
google-cloud-storage>=2.10.0
```

PyYAML is already present (`PyYAML==6.0.3`). `anthropic` is already present.

---

## Environment Variables — New

| Variable | Purpose | Required |
|----------|---------|----------|
| `GCS_BUCKET_NAME` | GCS bucket for ingestion file storage | Yes |
| `WORKER_CONCURRENCY` | Number of concurrent queue worker coroutines (default: `5`) | No |
| `GOOGLE_APPLICATION_CREDENTIALS` | Path to SA key JSON (local dev only; not used on GKE with Workload Identity) | No |
