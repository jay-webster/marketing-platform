# Research: AI-Powered Marketing Content Generation

**Branch**: `007-content-generation` | **Date**: 2026-03-15
**Phase**: 0 — All unknowns resolved before design begins

---

## Decision 1: PDF Generation Library

**Decision**: WeasyPrint (HTML/CSS/Jinja2 → PDF bytes, rendered in-memory)

**Rationale**:
- Pure Python — no subprocess dependencies, no headless browser, no local filesystem writes
- Renders directly to `bytes` via `weasyprint.HTML(string=html).write_pdf()` — satisfies the `NON_BLOCKING` / Stateless Services principle (no temp files written to container filesystem)
- Jinja2 HTML templates allow full control over layout, brand typography, and image placement without a bespoke layout engine
- Active maintenance, Python 3.11 compatible

**Alternatives considered**:
- **PDFKit** (wkhtmltopdf wrapper): Requires a subprocess binary (`wkhtmltopdf`) installed in the container. Adds container build complexity and is no longer actively maintained.
- **ReportLab**: Low-level programmatic PDF creation. Requires significant boilerplate to achieve styled, image-bearing layouts. Overkill for template-based documents.
- **fpdf2**: Simpler but limited CSS support — font handling and image placement are manual, making it hard to maintain brand consistency across templates.

---

## Decision 2: Brand Image Storage Architecture

**Decision**: GCS binary storage + `brand_images` PostgreSQL metadata table

**Rationale**:
- Binary blobs are too large for PostgreSQL storage; GCS is the established project pattern for file assets (DRY — reuse `utils/gcs.py`)
- PostgreSQL metadata row enables fast queries for the image picker without making GCS API calls per-image
- Same dual-source architecture used by `SyncedDocument` pattern: source-of-truth is external (GitHub or upload), PostgreSQL holds queryable metadata
- Image picker only needs `id`, `display_title`, `content_type`, `thumbnail_url` — all derivable from the metadata table + a GCS signed URL

**GCS path scheme**: `brand-images/{image_id}/{filename}`
- One folder per image UUID: clean, collision-free, supports future multi-file-per-image scenarios

**Signed URL expiry**: 24 hours for picker thumbnails and download links

**Alternatives considered**:
- Storing images as base64 in PostgreSQL BYTEA: Bloats the DB, violates Stateless Services principle.
- Serving images via a dedicated backend proxy endpoint: Adds unnecessary latency and backend load for every image request; signed URLs let the client fetch directly from GCS.

---

## Decision 3: Generation Flow — Synchronous vs. Async Job Queue

**Decision**: Synchronous HTTP POST for all output types (email, LinkedIn, PDF)

**Rationale**:
- WeasyPrint PDF rendering: ~1–3 seconds for a standard one-pager. Well within the 30-second SC-002 target.
- Claude API response with streaming: 5–15 seconds for typical marketing content. Within the 15-second SC-001 target for text outputs.
- Synchronous streaming (SSE) already exists for chat. For generation we use a synchronous non-streaming POST because the output is a complete structured artifact, not a progressive conversation turn.
- A job queue (Redis/Celery/PostgreSQL SKIP LOCKED) adds significant infrastructure complexity for a latency target that synchronous execution meets comfortably.
- If PDF generation latency degrades with longer documents, the endpoint can switch to SSE progress events without changing the client contract significantly.

**Revisit trigger**: If PDF generation routinely exceeds 20 seconds in production, add a job queue with a polling/webhook mechanism.

**Alternatives considered**:
- PostgreSQL SKIP LOCKED queue (same pattern as Epic 3/4): Appropriate if generation took 30+ seconds or needed retry logic. Unnecessary at current scale.

---

## Decision 4: Generated PDF Storage and Download

**Decision**: Store generated PDFs in GCS; return a signed URL (valid 7 days) in the API response

**Rationale**:
- Constitution Stateless Services: PDFs must not be written to container filesystem
- 7-day retention satisfies spec Assumption: "Generated PDFs are stored temporarily (at least 7 days)"
- Signed URL allows the client to download directly from GCS without backend proxying
- `generation_requests.result_pdf_gcs_name` stores the object name; a fresh signed URL is generated on each GET request to the history endpoint, ensuring the URL is always valid when the user accesses their history

**GCS path scheme**: `generated-pdfs/{request_id}/{filename}.pdf`

---

## Decision 5: Image Sync Extension Strategy

**Decision**: Extend `utils/sync.py` with `_IMAGE_EXTENSIONS` detection; download image binary to GCS; upsert `brand_images` row

**Rationale**:
- DRY: sync.py already walks the full repo tree in one API call and handles new/changed/removed file detection via SHA comparison
- Extending sync rather than a separate pipeline avoids running two tree-walk operations per sync
- Image binary must be downloaded from GitHub and uploaded to GCS (images cannot be streamed to clients from GitHub without token exposure)
- `is_active` flag on `brand_images` mirrors the `SyncedDocument.is_active` pattern for handling image removal from the repo

**Image path filter**: Only files under `content/assets/images/` with extensions `.png`, `.jpg`, `.jpeg`, `.webp`, `.gif`

**Alternatives considered**:
- Separate scheduled image sync job: More complex orchestration, duplicates tree-walk logic.
- Store GitHub raw image URLs: Exposes GitHub token in frontend or requires backend proxying.

---

## Decision 6: Structured Output Parsing for Text Generation

**Decision**: Output-type-specific system prompts instruct the model to return content in a delimited format; parse with lightweight string splitting (no JSON function calling)

**Rationale**:
- Email output: System prompt requests `SUBJECT: <text>\n\nBODY: <text>` format — trivial to parse reliably
- LinkedIn output: System prompt requests post body followed by `HASHTAGS: <space-separated hashtags>` — trivial to parse
- Claude follows delimited format instructions consistently for short structured outputs
- JSON function calling adds latency and complexity not warranted for two simple output types

**Fallback**: If delimiters are missing in the model response, return the full response text as the body and leave subject/hashtags empty — never fail silently.

---

## Decision 7: Admin Image Upload Authentication

**Decision**: Use `require_role(Role.ADMIN)` (JWT-based) for image upload and delete endpoints, matching the established pattern in `src/api/sync.py` and `src/api/knowledge_base.py`

**Rationale**:
- The project has established `require_role(Role.ADMIN)` as the admin auth pattern for endpoints that flow through the BFF proxy. The `X-Admin-Token` pattern in the Constitution is not forwarded by the BFF and has been superseded in practice.
- Consistent with all other admin endpoints already implemented.

---

## New Environment Variable Required

| Variable | Purpose | Default |
|----------|---------|---------|
| `BRAND_IMAGES_BUCKET` | GCS bucket for brand images and generated PDFs | (required, no default) |
| `PDF_SIGNED_URL_EXPIRY_SECONDS` | Signed URL TTL for PDFs and image thumbnails | `86400` (24h) |

---

## GCS Utility Extensions Required

`utils/gcs.py` needs two new functions (DRY extension, not a new module):

1. `upload_bytes_to_gcs(data: bytes, bucket_name: str, object_name: str, content_type: str) -> str`
   — upload raw bytes (PDF output, downloaded image binary) without requiring an `UploadFile`

2. `generate_signed_url(bucket_name: str, object_name: str, expiry_seconds: int) -> str`
   — generate a V4 signed URL for direct client download

Both operations run via `asyncio.to_thread` to remain non-blocking, consistent with existing `gcs.py` pattern.

---

## Dependency: WeasyPrint System Libraries

WeasyPrint requires system-level font and rendering libraries (`pango`, `cairo`, `gdk-pixbuf`) in the Docker image.

**Action**: Add to `Dockerfile` builder stage:
```dockerfile
RUN apt-get update && apt-get install -y --no-install-recommends \
    libpango1.0-0 \
    libcairo2 \
    libffi8 \
    fonts-liberation \
    && rm -rf /var/lib/apt/lists/*
```

**Python package**: `weasyprint>=60.0`

**Notes from validation**:
- Images must be embedded as base64 data URIs in the Jinja2 template context — do not pass file paths or HTTP URLs to WeasyPrint (disk I/O or network dependency)
- CSS filters, `position: fixed/sticky`, and JS are not supported — Flexbox and Grid work fully
- `asyncio.to_thread` is required since `HTML.write_pdf()` is synchronous and CPU-bound
- Font packages must be present in the container; omitting them causes PDF text to render with fallback fonts or fail silently
