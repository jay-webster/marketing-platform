# Implementation Plan: AI-Powered Marketing Content Generation

**Branch**: `007-content-generation` | **Date**: 2026-03-15 | **Spec**: [spec.md](./spec.md)
**Input**: Feature specification from `specs/007-content-generation/spec.md`

---

## Summary

This feature adds three marketing content output types (Email, LinkedIn Post, PDF) generated from a chat-style prompt grounded in the knowledge base via RAG. PDFs embed brand imagery selected from a library populated by two sources: the existing GitHub sync pipeline (extended) and direct admin UI uploads.

New work required:
- 2 new API routers (`generate.py`, `images.py`)
- 2 new utility modules (`utils/generator.py`, `utils/pdf_renderer.py`) + Jinja2 HTML templates
- 2 new database tables (`brand_images`, `generation_requests`) + Alembic migration
- Extensions to `utils/gcs.py` (bytes upload + signed URL) and `utils/sync.py` (image detection)
- 1 new Dockerfile dependency (WeasyPrint system libraries)
- Full frontend: generation form, image picker, result display, history page

---

## Technical Context

**Language/Version**: Python 3.11 (backend), TypeScript / Next.js 15 App Router (frontend)
**New Dependencies**: `weasyprint>=62.0` (PDF), `jinja2` (already present via existing templates)
**Storage**: PostgreSQL 16 (brand_images, generation_requests), GCS (image binaries, generated PDFs)
**Testing**: pytest (backend), TypeScript type checking (frontend)
**Target Platform**: GCP GKE (backend), Vercel (frontend)
**Performance Goals**: Email/LinkedIn < 15s (SC-001), PDF < 30s (SC-002)
**Constraints**: Prompt max 2000 chars; generation is synchronous HTTP POST (no job queue); all files in GCS (no local disk); admin-only image upload
**Scale/Scope**: Single-tenant; ~20 concurrent users per client installation

---

## Constitution Check

| Principle | Status | Notes |
|-----------|--------|-------|
| **AUTH_SAFE** | PASS | All generation endpoints use `get_current_user`. Image upload/delete use `require_role(Role.ADMIN)`. History GET scoped to `user_id`. |
| **DRY** | PASS | Reuses `utils/rag.py` (RAG retrieval), `utils/embeddings.py` (query embedding), `utils/gcs.py` (extended, not replaced), `utils/auth.py` (`require_role`), `utils/db.py`. |
| **NON_BLOCKING** | PASS | WeasyPrint renders to `bytes` in-memory via `asyncio.to_thread`. GCS upload/download via `asyncio.to_thread`. No writes to container filesystem. |
| **ERROR_HANDLING** | PASS | Global exception handler on all routers. Generation failures stored as `status=failed` records rather than propagating unhandled exceptions. |
| **IDEMPOTENT** | PASS | GitHub image sync uses SHA comparison + UPSERT (same pattern as document sync). Admin uploads are non-idempotent by design (each upload is a distinct asset). |
| **ADMIN_SECURITY** | PASS | Image upload/delete use `require_role(Role.ADMIN)` — consistent with established project pattern in `src/api/sync.py` and `src/api/knowledge_base.py`. Note: Constitution specifies `X-Admin-Token` but the BFF proxy does not forward that header; `require_role` is the project's established pattern. |

---

## Project Structure

### Documentation (this feature)

```text
specs/007-content-generation/
├── plan.md              ← This file
├── spec.md              ← Feature specification
├── research.md          ← Phase 0: technology decisions
├── data-model.md        ← Phase 1: schema
├── contracts/
│   └── api.md           ← Phase 1: endpoint contracts
└── tasks.md             ← Phase 2 output (/speckit.tasks — not created here)
```

### New Backend Files

```text
src/
├── api/
│   ├── generate.py              ← Generation request CRUD + trigger endpoints
│   └── images.py                ← Brand image list/upload/delete endpoints
├── models/
│   ├── brand_image.py           ← BrandImage SQLAlchemy model
│   └── generation_request.py   ← GenerationRequest SQLAlchemy model
migrations/
└── versions/
    └── xxxx_add_content_generation_tables.py  ← brand_images + generation_requests
utils/
├── generator.py                 ← RAG-grounded content generation (email/linkedin/pdf text)
└── pdf_renderer.py              ← WeasyPrint HTML→PDF renderer
    pdf_templates/
    ├── base.css                 ← Shared brand styles
    ├── one_pager.html           ← Jinja2 One-Pager template
    └── campaign_brief.html      ← Jinja2 Campaign Brief template
tests/
├── api/
│   ├── test_generate.py         ← Generation API tests
│   └── test_images.py           ← Brand image API tests
```

### Modified Backend Files

```text
utils/gcs.py          ← Add upload_bytes_to_gcs() + generate_signed_url()
utils/sync.py         ← Add image file detection + brand_images upsert
src/main.py           ← Register generate and images routers
Dockerfile            ← Add WeasyPrint system library dependencies
requirements.txt      ← Add weasyprint>=62.0
```

### New Frontend Files

```text
frontend/
├── app/(dashboard)/
│   └── generate/
│       └── page.tsx                          ← Generation page (form + history)
└── components/
    └── generate/
        ├── GenerationForm.tsx               ← Prompt input + output type selector + template picker
        ├── ImagePicker.tsx                  ← Brand image browser (PDF only)
        ├── GenerationResult.tsx             ← Display result, copy/download actions, regenerate
        └── GenerationHistory.tsx            ← Past generation list with re-use actions
```

### Modified Frontend Files

```text
frontend/lib/types.ts                        ← Add GenerationRequest, BrandImage, GenerationResult types
frontend/app/(dashboard)/layout.tsx          ← Add "Generate" nav link (or equivalent nav component)
```

---

## Work Items

### Backend — `utils/gcs.py` (extend, do not replace)

**GCS-001: Add `upload_bytes_to_gcs`**
```python
async def upload_bytes_to_gcs(
    data: bytes,
    bucket_name: str,
    object_name: str,
    content_type: str,
) -> str:
    """Upload raw bytes to GCS. Returns object_name. No local disk write."""
```
- Runs via `asyncio.to_thread`
- Used by: image upload endpoint, PDF post-render upload

**GCS-002: Add `generate_signed_url`**
```python
async def generate_signed_url(
    bucket_name: str,
    object_name: str,
    expiry_seconds: int,
) -> str:
    """Generate a V4 signed URL for direct client download."""
```
- Runs via `asyncio.to_thread`
- Used by: image picker thumbnails, PDF download link, history GET

---

### Backend — `utils/sync.py` (extend)

**SYNC-001: Add image file detection**
- Define `_IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp", ".gif"}`
- Define `_IMAGES_PREFIX = "content/assets/images/"`
- In `_execute_sync`: after the existing markdown pass, run a second pass over tree items that match `_IMAGES_PREFIX` + `_IMAGE_EXTENSIONS`
- For each new/changed image: download binary via `get_file_content`, upload to GCS via `upload_bytes_to_gcs`, upsert `brand_images` row
- For removed images: set `brand_images.is_active = False` (soft delete)
- Idempotent: SHA comparison prevents redundant GCS uploads for unchanged images

---

### Backend — `src/models/brand_image.py`

**MODEL-001: BrandImage model**
- SQLAlchemy model for `brand_images` table per data-model.md
- Fields: `id`, `filename`, `gcs_object_name`, `content_type`, `display_title`, `source`, `file_size_bytes`, `is_active`, `created_at`, `updated_at`

---

### Backend — `src/models/generation_request.py`

**MODEL-002: GenerationRequest model**
- SQLAlchemy model for `generation_requests` table per data-model.md
- Fields: `id`, `user_id`, `output_type`, `prompt`, `pdf_template`, `selected_image_ids`, `status`, `result_text`, `result_pdf_gcs_name`, `failure_reason`, `created_at`, `updated_at`
- `selected_image_ids` stored as JSONB or PostgreSQL UUID array

---

### Backend — `utils/generator.py`

**GEN-001: RAG-grounded text generation**

Core function:
```python
async def generate_content(
    db: AsyncSession,
    output_type: str,  # "email" | "linkedin" | "pdf_body"
    prompt: str,
) -> dict[str, Any]:
    """
    Retrieve KB chunks for prompt, assemble type-specific system prompt,
    call Claude, parse structured output.

    Returns:
      - email: {"subject": str, "body": str}
      - linkedin: {"post_text": str, "hashtags": list[str]}
      - pdf_body: {"title": str, "sections": list[{"heading": str, "content": str}]}

    Raises NoKBContentError if retrieval returns no chunks.
    """
```

- Reuses `utils/embeddings.py` (`embed_text`) and `utils/rag.py` (`retrieve_chunks`, `build_prompt`)
- Does NOT use `rag_stream_generator` — uses a direct `client.messages.create()` call (non-streaming, synchronous response)
- System prompt is output-type-specific with delimited output format instructions
- Parsing: lightweight string splitting on known delimiters with graceful fallback

**Output type prompts**:
- **Email**: Instructs model to output `SUBJECT: <text>\n\nBODY: <text>`. Parse on `SUBJECT:` / `BODY:` prefixes.
- **LinkedIn**: Instructs model to output post text followed by `HASHTAGS: #tag1 #tag2 ...`. Parse on `HASHTAGS:` prefix.
- **PDF body**: Instructs model to output structured sections in `SECTION: <heading>\n<content>` format for template injection.

---

### Backend — `utils/pdf_renderer.py`

**PDF-001: WeasyPrint HTML→PDF renderer**

```python
async def render_pdf(
    template_name: str,  # "one_pager" | "campaign_brief"
    content: dict[str, Any],
    images: list[dict[str, Any]],  # [{"gcs_object_name": str, "display_title": str}]
    bucket_name: str,
) -> bytes:
    """
    Download selected images from GCS, inject content + images into Jinja2 template,
    render to PDF bytes via WeasyPrint.
    """
```

- Downloads image binaries from GCS as `BytesIO`, converts to base64 data URIs for embedding in HTML
- Jinja2 renders HTML string; WeasyPrint renders HTML → `bytes` in `asyncio.to_thread`
- No temp files written

**PDF-002: Jinja2 templates**

`utils/pdf_templates/one_pager.html`:
- Sections: title, tagline, body paragraphs, key points list, optional image, source citation footer

`utils/pdf_templates/campaign_brief.html`:
- Sections: title, objective, target audience, messaging pillars, optional image, content outline

`utils/pdf_templates/base.css`:
- Brand typography (clean sans-serif), color scheme, page margins, WeasyPrint-compatible styles

---

### Backend — `src/api/generate.py`

**API-GEN-001: `POST /api/v1/generate`**
- Validate request (prompt length, output_type, pdf_template required for PDF, image_ids exist)
- Create `GenerationRequest` with `status=pending`, commit
- Call `generator.generate_content()` for text, then `pdf_renderer.render_pdf()` for PDF
- On `NoKBContentError`: update request to `status=failed, failure_reason=no_kb_content`, return 200 with failure shape
- On success: update request to `status=completed`, store result, return 200 with full result shape
- On unexpected error: update request to `status=failed`, re-raise (global exception handler returns 500)

**API-GEN-002: `GET /api/v1/generate`**
- Query `generation_requests` where `user_id = current_user.id`, ordered by `created_at DESC`
- For PDF items: generate fresh signed URLs on each response
- Paginated (limit/offset)

**API-GEN-003: `GET /api/v1/generate/{id}`**
- Verify ownership; return full detail with fresh signed URL for PDF

**API-GEN-004: `DELETE /api/v1/generate/{id}`**
- Verify ownership; delete GCS PDF if present; delete DB row; return 204

---

### Backend — `src/api/images.py`

**API-IMG-001: `GET /api/v1/images`**
- Query `brand_images` where `is_active = TRUE`, ordered by `created_at DESC`
- Return list with signed URL thumbnails; paginated

**API-IMG-002: `POST /api/v1/images`**
- `require_role(Role.ADMIN)`
- Validate file type (PNG/JPG/JPEG/WEBP/GIF) and size (max 10MB)
- Upload to GCS via `upload_bytes_to_gcs`
- Insert `brand_images` row with `source=admin_upload`
- Return created image with signed URL

**API-IMG-003: `DELETE /api/v1/images/{id}`**
- `require_role(Role.ADMIN)`
- Delete from GCS; delete DB row (hard delete — admin-uploaded images have no `is_active` soft-delete workflow)

---

### Backend — `src/main.py`

Register two new routers:
```python
from src.api.generate import router as generate_router
from src.api.images import router as images_router

app.include_router(generate_router, prefix="/api/v1")
app.include_router(images_router, prefix="/api/v1")
```

---

### Backend — Tests

**TEST-001: `tests/api/test_generate.py`**
- `test_generate_email_success`: mock `embed_text`, `retrieve_chunks`, Anthropic client; verify `status=completed`, `result.subject` present
- `test_generate_no_kb_content`: mock retrieval to return empty; verify `status=failed`, `failure_reason=no_kb_content`
- `test_generate_empty_prompt`: POST empty prompt; expect 422
- `test_generate_prompt_too_long`: POST 2001-char prompt; expect 422
- `test_generate_pdf_no_template`: POST PDF type without `pdf_template`; expect 422
- `test_generate_history_scoped`: user A cannot see user B's history
- `test_generate_delete_own`: user deletes own request; 204 returned
- `test_generate_delete_other`: user tries to delete other user's request; 404

**TEST-002: `tests/api/test_images.py`**
- `test_list_images_authenticated`: marketer can list images
- `test_upload_image_admin_only`: marketer POST → 403
- `test_upload_image_admin_success`: admin POST valid PNG → 201 with image data
- `test_upload_image_invalid_type`: admin POST PDF file → 422
- `test_delete_image_admin_only`: marketer DELETE → 403
- `test_delete_image_not_found`: admin DELETE non-existent → 404

---

### Frontend — `frontend/lib/types.ts` (extend)

Add types:
```typescript
export type OutputType = "email" | "linkedin" | "pdf"

export interface BrandImage {
  id: string
  filename: string
  display_title: string
  content_type: string
  source: "github_sync" | "admin_upload"
  thumbnail_url: string
  created_at: string
}

export interface GenerationResult {
  subject?: string           // email
  body?: string              // email
  post_text?: string         // linkedin
  hashtags?: string[]        // linkedin
  pdf_url?: string           // pdf
  pdf_filename?: string      // pdf
}

export interface GenerationRequest {
  id: string
  output_type: OutputType
  status: "completed" | "failed"
  prompt: string
  result?: GenerationResult
  failure_reason?: string
  pdf_url?: string           // list view: signed URL (pdf only)
  created_at: string
}
```

---

### Frontend — Components

**FE-001: `GenerationForm.tsx`**
- Output type selector (Email / LinkedIn Post / PDF)
- Prompt textarea with character counter (max 2000, warn at 1800)
- PDF options (template picker + image picker) rendered conditionally when `output_type=pdf`
- Submit button disabled while generating; loading state
- On submit: POST to `/api/v1/generate`, show `GenerationResult` on response

**FE-002: `ImagePicker.tsx`**
- Fetches `GET /api/v1/images` on mount
- Grid of thumbnails; click to toggle selection
- Displays selected count and image titles
- Empty state: "No brand images available" with context-appropriate message

**FE-003: `GenerationResult.tsx`**
- Email: renders subject and body in labeled sections; "Copy All" button (subject + body)
- LinkedIn: renders post text and hashtags; "Copy Post" button
- PDF: "Download PDF" button (opens `pdf_url` in new tab); filename displayed
- "Regenerate" button: re-submits with same prompt and output type
- "Start Over" button: clears form

**FE-004: `GenerationHistory.tsx`**
- Fetches `GET /api/v1/generate` (paginated)
- List items show: output type badge, prompt truncated to 80 chars, date, status
- Actions per item: "View" (re-render GenerationResult), "Download" (PDF only), "Regenerate", "Delete"
- Delete calls `DELETE /api/v1/generate/{id}` with confirmation

**FE-005: `generate/page.tsx`**
- Left panel: `GenerationForm` + `GenerationResult`
- Right panel: `GenerationHistory`
- On mobile: tabbed view (Generate / History)

---

## Implementation Order

Dependencies are listed. Backend and frontend can run in parallel after the migration lands.

### Phase 1 — Foundation (serial, blocking)
1. Alembic migration — `brand_images` + `generation_requests` tables
2. `src/models/brand_image.py` + `src/models/generation_request.py`
3. `utils/gcs.py` extensions (GCS-001, GCS-002)

### Phase 2 — US1 + US2: Email and LinkedIn (can parallel after Phase 1)
4. `utils/generator.py` (GEN-001) — email + linkedin generation
5. `src/api/generate.py` — POST, GET list, GET detail, DELETE (API-GEN-001 through 004)
6. `src/main.py` — register generate router
7. Frontend: types.ts → GenerationForm → GenerationResult → page.tsx
8. Tests: `test_generate.py`

### Phase 3 — US3: PDF (depends on Phase 2 generate router)
9. `utils/pdf_renderer.py` + templates (PDF-001, PDF-002)
10. `utils/generator.py` — add `pdf_body` output type
11. `src/api/images.py` — all three image endpoints
12. `src/main.py` — register images router
13. `utils/sync.py` extension (SYNC-001) — image detection in GitHub sync
14. Frontend: ImagePicker.tsx, extend GenerationForm for PDF options
15. Tests: `test_images.py`

### Phase 4 — US4: History (depends on Phase 2 generate router)
16. Frontend: `GenerationHistory.tsx` — list, view, download, regenerate, delete

### Phase 5 — Polish
17. Dockerfile + requirements.txt — WeasyPrint system libraries
18. Navigation update — add Generate link
19. Environment variable documentation (`BRAND_IMAGES_BUCKET`, `PDF_SIGNED_URL_EXPIRY_SECONDS`)
20. CLAUDE.md update — new technologies

---

## New Environment Variables

| Variable | Purpose | Required |
|----------|---------|----------|
| `BRAND_IMAGES_BUCKET` | GCS bucket for brand images and generated PDFs | Yes |
| `PDF_SIGNED_URL_EXPIRY_SECONDS` | Signed URL TTL in seconds (default 86400) | No |

---

## Complexity Notes

- **WeasyPrint Docker dependencies**: Most likely blocker for CI. System libraries must be added to the Dockerfile before any PDF rendering tests can pass. Do this in Phase 5 but verify locally in Phase 3.
- **GCS service account permissions**: The existing GCS service account must have Storage Object Admin on `BRAND_IMAGES_BUCKET`. Verify this is configured before Phase 2.
- **Signed URL authentication**: V4 signed URLs require the service account key or Workload Identity. Verify the GKE workload identity setup supports `generate_signed_url` in production.
