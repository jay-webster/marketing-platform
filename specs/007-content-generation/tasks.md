# Tasks: AI-Powered Marketing Content Generation

**Feature**: `007-content-generation` | **Date**: 2026-03-15
**Plan**: [plan.md](./plan.md) | **Spec**: [spec.md](./spec.md)

---

## Implementation Strategy

Build incrementally by user story priority. Each phase is independently testable before the next begins.

- **MVP (Phase 3 only)**: Email copy generation end-to-end — validates the full RAG → generation → API → UI pipeline before adding LinkedIn, PDF, or history
- **P1 complete (Phases 3–4)**: Email + LinkedIn — all copy generation done; no image handling
- **P2 complete (Phase 5)**: PDF with brand imagery — most complex phase; depends on P1 infrastructure
- **P3 complete (Phase 6)**: Generation history — reuse and re-download past items

**Parallel opportunities**: Models (T004, T005), PDF templates (T020, T021), and frontend type definitions (T011) have no inter-dependencies and can run concurrently.

---

## Phase 1: Setup

Project infrastructure prerequisites. Must complete before Phase 2.

- [x] T001 Add WeasyPrint system library dependencies to Dockerfile: `libpango1.0-0 libcairo2 libffi8 fonts-liberation` via `apt-get install --no-install-recommends` in the builder stage
- [x] T002 Add `weasyprint>=60.0` to requirements.txt
- [x] T003 Add `BRAND_IMAGES_BUCKET: str` and `PDF_SIGNED_URL_EXPIRY_SECONDS: int = 86400` fields to the `Settings` class in src/config.py

---

## Phase 2: Foundation

Blocking prerequisites for all user story phases. Must complete before Phase 3.

- [x] T004 [P] Create SQLAlchemy model `BrandImage` in src/models/brand_image.py with fields: `id` (UUID PK), `filename` (VARCHAR 255), `gcs_object_name` (VARCHAR 500, UNIQUE), `content_type` (VARCHAR 100), `display_title` (VARCHAR 255, nullable), `source` (VARCHAR 50: `github_sync` or `admin_upload`), `file_size_bytes` (INTEGER, nullable), `is_active` (BOOLEAN default TRUE), `created_at` (TIMESTAMPTZ), `updated_at` (TIMESTAMPTZ)
- [x] T005 [P] Create SQLAlchemy model `GenerationRequest` in src/models/generation_request.py with fields: `id` (UUID PK), `user_id` (UUID FK → users.id), `output_type` (VARCHAR 50: `email`, `linkedin`, `pdf`), `prompt` (TEXT), `pdf_template` (VARCHAR 100, nullable), `selected_image_ids` (JSONB, nullable — array of UUID strings), `status` (VARCHAR 50: `pending`, `completed`, `failed`; default `pending`), `result_text` (TEXT, nullable), `result_pdf_gcs_name` (VARCHAR 500, nullable), `failure_reason` (TEXT, nullable), `created_at` (TIMESTAMPTZ), `updated_at` (TIMESTAMPTZ)
- [x] T006 Create Alembic migration in migrations/versions/xxxx_add_content_generation_tables.py: `upgrade()` creates `brand_images` (with `idx_brand_images_active` partial index on `is_active=TRUE` and `idx_brand_images_source`) and `generation_requests` (with `idx_generation_requests_user_id` and `idx_generation_requests_user_created` on `(user_id, created_at DESC)`); `downgrade()` drops both tables
- [x] T007 Extend utils/gcs.py with two new async functions: `upload_bytes_to_gcs(data: bytes, bucket_name: str, object_name: str, content_type: str) -> str` (upload raw bytes, return object_name, run via `asyncio.to_thread`) and `generate_signed_url(bucket_name: str, object_name: str, expiry_seconds: int) -> str` (generate V4 signed URL, run via `asyncio.to_thread`)

---

## Phase 3: User Story 1 — Generate Email Copy

**Story goal**: Authenticated user enters a prompt, selects Email output type, receives a structured subject + body draft grounded in KB content, and can copy it to clipboard.

**Independent test criteria**: With at least one document indexed, POST `/api/v1/generate` with `output_type=email` and a valid prompt returns `status=completed` with non-empty `result.subject` and `result.body`. Posting an empty prompt returns 422. Posting when no relevant KB content exists returns `status=failed` with `failure_reason=no_kb_content`.

- [x] T008 [US1] Create utils/generator.py with: (1) `NoKBContentError` exception class; (2) `generate_content(db, output_type, prompt) -> dict` that calls `embed_text(prompt)`, calls `retrieve_chunks(db, embedding)`, raises `NoKBContentError` if chunks is empty, calls `build_prompt(chunks)` from utils/rag.py, constructs an output-type-specific system prompt instructing the model to return `SUBJECT: <text>\n\nBODY: <text>` for email, calls `AsyncAnthropic().messages.create()` (non-streaming), parses delimiters, returns `{"subject": str, "body": str}` — with graceful fallback if delimiters are absent (full response as body, empty subject)
- [x] T009 [US1] Create src/api/generate.py with FastAPI router prefix `/generate`, tag `generation`, and four endpoints: (1) `POST /` — validate prompt not empty/whitespace (422) and ≤2000 chars (422), create `GenerationRequest(status=pending)`, call `generate_content()`, on `NoKBContentError` set `status=failed, failure_reason=no_kb_content`, on success set `status=completed, result_text=<json-serialised result>`, return response per contracts/api.md; (2) `GET /` — list caller's requests ordered by `created_at DESC`, paginated (limit/offset), return list items with fresh `pdf_url` for PDF items; (3) `GET /{id}` — verify ownership (404 if missing or not owned), return full detail; (4) `DELETE /{id}` — verify ownership, delete GCS PDF if `result_pdf_gcs_name` set, delete DB row, return 204
- [x] T010 [US1] Register generate router in src/main.py: import `from src.api.generate import router as generate_router` and add `application.include_router(generate_router, prefix="/api/v1")` following the existing router registration pattern
- [x] T011 [P] [US1] Add TypeScript types to frontend/lib/types.ts: `OutputType = "email" | "linkedin" | "pdf"`, `GenerationResult { subject?: string; body?: string; post_text?: string; hashtags?: string[]; pdf_url?: string; pdf_filename?: string }`, `GenerationRequest { id: string; output_type: OutputType; status: "completed" | "failed"; prompt: string; result?: GenerationResult; failure_reason?: string; pdf_url?: string; created_at: string }`, `BrandImage { id: string; filename: string; display_title: string; content_type: string; source: "github_sync" | "admin_upload"; thumbnail_url: string; created_at: string }`
- [x] T012 [US1] Create frontend/components/generate/GenerationForm.tsx: segmented output type selector showing Email, LinkedIn Post, PDF tabs; prompt `<textarea>` with `maxLength={2000}`, character counter showing current/2000 (warn styling at 1800+); submit button that POSTs to `/api/v1/generate` with `{ output_type, prompt }`, shows loading spinner while pending; displays inline error on 422 or `status=failed` with `failure_reason=no_kb_content`; accepts optional `onResult(result: GenerationRequest)` callback prop; PDF-specific controls hidden until Phase 5
- [x] T013 [US1] Create frontend/components/generate/GenerationResult.tsx: renders based on `result.output_type`; for email: labelled "Subject" and "Body" sections; "Copy All" button that writes `Subject: {subject}\n\n{body}` to clipboard via `navigator.clipboard.writeText`; "Start Over" button that calls an `onReset()` prop; accepts `request: GenerationRequest` prop
- [x] T014 [US1] Create frontend/app/(dashboard)/generate/page.tsx: renders `<GenerationForm>` and conditionally `<GenerationResult>` below it when a result is available; manages `currentResult` state; passes `onResult` to form and `onReset` to result; page title "Generate Content"
- [x] T015 [US1] Write tests/api/test_generate.py: `test_generate_email_success` (mock `embed_text` + `retrieve_chunks` + Anthropic client, verify 200 + `status=completed` + `result.subject` present); `test_generate_no_kb_content` (mock `retrieve_chunks` to return `[]`, verify `status=failed` + `failure_reason=no_kb_content`); `test_generate_empty_prompt` (expect 422); `test_generate_prompt_too_long` (2001-char prompt, expect 422); `test_generate_unauthenticated` (no auth header, expect 401); `test_generate_history_user_scoped` (user A cannot see user B's request); `test_generate_delete_own` (204); `test_generate_delete_other_user` (404)

---

## Phase 4: User Story 2 — Generate a LinkedIn Post

**Story goal**: User selects LinkedIn Post, enters a prompt, receives a post with body, call to action, and hashtag suggestions. Can copy the full post and regenerate a new variation without re-entering the prompt.

**Independent test criteria**: POST `/api/v1/generate` with `output_type=linkedin` returns `status=completed` with non-empty `result.post_text` and a non-empty `result.hashtags` array. The Regenerate button in the UI submits the same prompt again and replaces the displayed result.

- [x] T016 [US2] Extend utils/generator.py `generate_content()` to handle `output_type=linkedin`: construct a LinkedIn-specific system prompt instructing the model to output the post text (under 3000 chars, including a call to action) followed by `HASHTAGS: #tag1 #tag2 ...`; parse on `HASHTAGS:` delimiter; return `{"post_text": str, "hashtags": list[str]}`; fallback: full response as `post_text`, empty hashtags array
- [x] T017 [US2] Extend frontend/components/generate/GenerationResult.tsx: add LinkedIn branch rendering `post_text` in a single text block and `hashtags` as a pill list below; "Copy Post" button writes `{post_text}\n\n{hashtags.join(" ")}` to clipboard
- [x] T018 [US2] Add "Regenerate" button to frontend/components/generate/GenerationResult.tsx: calls `onRegenerate()` prop (which re-submits same `{ output_type, prompt }` to `/api/v1/generate`); shown for all output types; shows loading state while regenerating; replaces displayed result when new result arrives

---

## Phase 5: User Story 3 — Generate a PDF with Brand Imagery

**Story goal**: User selects PDF, chooses a template (One-Pager or Campaign Brief), optionally picks brand images, submits, and receives a downloadable formatted PDF. Admin users can upload images directly via the UI. The GitHub sync pipeline also populates the image library from `content/assets/images/`.

**Independent test criteria**: With at least one template and one image in GCS, POST `/api/v1/generate` with `output_type=pdf`, a valid `pdf_template`, and no `image_ids` returns `status=completed` with a non-null `result.pdf_url`. GET `/api/v1/images` returns the image list. Admin POST `/api/v1/images` with a valid PNG creates a brand image record.

- [x] T019 [US3] Create utils/pdf_templates/base.css: clean sans-serif brand typography (system font stack), neutral color scheme, WeasyPrint-compatible `@page` rule (A4, 20mm margins), heading styles (h1–h3), body paragraph styles, utility classes for image placement (full-width, half-width); avoid CSS filters, position:fixed, and box-shadow blur (not supported by WeasyPrint)
- [x] T020 [P] [US3] Create utils/pdf_templates/one_pager.html: Jinja2 template extending base.css; sections: `{{ title }}` (h1), `{{ tagline }}` (subtitle), body paragraphs from `{{ sections }}` list (each with `heading` and `content`), optional `{% if images %}` image block (first image full-width), source citation footer; `<html>` wraps `<head>` (link base.css, set charset) and `<body>`
- [x] T021 [P] [US3] Create utils/pdf_templates/campaign_brief.html: Jinja2 template extending base.css; sections: `{{ title }}`, Objective, Target Audience, Messaging Pillars (bulleted list from `{{ sections }}`), optional image block, Content Outline; same head/body structure as one_pager.html
- [x] T022 [US3] Create utils/pdf_renderer.py with `render_pdf(template_name: str, content: dict, image_ids: list[str], db: AsyncSession, bucket_name: str) -> bytes`: (1) load brand images from DB by `image_ids`; (2) for each image, call `download_stream_from_gcs(bucket_name, gcs_object_name)` and base64-encode to data URI; (3) load Jinja2 template from `utils/pdf_templates/{template_name}.html` using `FileSystemLoader`; (4) render HTML string with `template.render(images=image_data_uris, **content)`; (5) run `HTML(string=html_string).write_pdf()` via `asyncio.to_thread`; return bytes
- [x] T023 [US3] Extend utils/generator.py `generate_content()` to handle `output_type=pdf_body`: construct a PDF-body system prompt instructing the model to output structured sections as `SECTION: <heading>\n<content>`, with a title line `TITLE: <text>`; parse into `{"title": str, "sections": [{"heading": str, "content": str}]}`; fallback: single section with full response as content
- [x] T024 [US3] Extend src/api/generate.py `POST /` handler: when `output_type=pdf`, validate `pdf_template` is present (422 if missing), validate any `image_ids` exist and are active in `brand_images` (422 if invalid); call `generate_content(db, "pdf_body", prompt)`; call `render_pdf(template_name, content, image_ids, db, bucket_name)`; upload PDF bytes to GCS via `upload_bytes_to_gcs(pdf_bytes, bucket, f"generated-pdfs/{request_id}/{slug}.pdf", "application/pdf")`; generate signed URL via `generate_signed_url(bucket, object_name, expiry_seconds)`; update `GenerationRequest` with `result_pdf_gcs_name` and return response with `pdf_url` and `pdf_filename`
- [x] T025 [US3] Create src/api/images.py with FastAPI router prefix `/images`, tag `images`: (1) `GET /` — query `brand_images WHERE is_active=TRUE ORDER BY created_at DESC`, paginated, generate signed URL per image via `generate_signed_url`, return list per contracts/api.md; (2) `POST /` — `require_role(Role.ADMIN)`, validate file MIME type in `{image/png, image/jpeg, image/webp, image/gif}` (422 otherwise) and size ≤10MB (422 otherwise), upload via `upload_bytes_to_gcs(await file.read(), bucket, f"brand-images/{new_id}/{file.filename}", content_type)`, insert `BrandImage` row with `source=admin_upload`, return 201 with image data + signed URL; (3) `DELETE /{id}` — `require_role(Role.ADMIN)`, fetch image (404 if missing), delete from GCS via `delete_from_gcs`, delete DB row, return 204
- [x] T026 [US3] Register images router in src/main.py: import `from src.api.images import router as images_router` and add `application.include_router(images_router, prefix="/api/v1")`
- [x] T027 [US3] Extend utils/sync.py: add `_IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp", ".gif"}` and `_IMAGES_PREFIX = "content/assets/images/"`; in `_execute_sync()`, after the existing markdown loop, add an image loop that (1) filters tree items matching `_IMAGES_PREFIX` and `_IMAGE_EXTENSIONS`, (2) compares SHA against existing `brand_images.gcs_object_name` (use filename+sha as change signal), (3) on new/changed: calls `get_file_content()` to get raw bytes, `upload_bytes_to_gcs()` to store in GCS at `brand-images/{image_id}/{filename}`, upserts `BrandImage` row with `source=github_sync, is_active=True`; (4) on removed (in DB but absent from tree): sets `brand_images.is_active=False` (soft delete)
- [x] T028 [US3] Create frontend/components/generate/ImagePicker.tsx: fetches `GET /api/v1/images` on mount using TanStack Query with key `["brand-images"]`; renders thumbnail grid using `thumbnail_url` for each image; clicking a thumbnail toggles selection (stores selected IDs in state); shows selected count badge; empty state message "No brand images available — images will appear here after the next GitHub sync or an admin upload"; accepts `selectedIds: string[]` and `onSelectionChange(ids: string[])` props
- [x] T029 [US3] Extend frontend/components/generate/GenerationForm.tsx: when `output_type=pdf`, show a template picker (segmented control or dropdown with "One-Pager" and "Campaign Brief" options mapping to `one_pager` and `campaign_brief`); show `<ImagePicker>` below the template picker; include `pdf_template` and `image_ids` in the POST body when submitting PDF requests
- [x] T030 [US3] Extend frontend/components/generate/GenerationResult.tsx: add PDF branch rendering a "Download PDF" button (renders as `<a href={result.pdf_url} download={result.pdf_filename} target="_blank">`) and the `pdf_filename` label below it
- [x] T031 [US3] Write tests/api/test_images.py: `test_list_images_authenticated` (marketer can GET, returns list); `test_list_images_unauthenticated` (401); `test_upload_image_admin_only` (marketer POST → 403); `test_upload_image_admin_success` (admin POST valid PNG → 201 + image data); `test_upload_image_invalid_type` (admin POST with content_type=application/pdf → 422); `test_upload_image_too_large` (admin POST >10MB → 422); `test_delete_image_admin_only` (marketer DELETE → 403); `test_delete_image_not_found` (admin DELETE non-existent ID → 404)

---

## Phase 6: User Story 4 — Browse and Reuse Past Generated Content

**Story goal**: User can view all previously generated content, re-download PDFs, re-copy text outputs, and regenerate any item from its original prompt without re-entering it.

**Independent test criteria**: After generating two items, navigating to the Generate page shows both in the history panel. Clicking Download on a PDF item initiates a download. Clicking Regenerate on any item pre-fills the form with the original prompt and output type.

- [x] T032 [US4] Create frontend/components/generate/GenerationHistory.tsx: fetches `GET /api/v1/generate` using TanStack Query with key `["generation-history"]`, paginated (load-more button); each list item shows: output type badge (color-coded), prompt text truncated to 80 chars with title tooltip, formatted `created_at` date, status indicator; action buttons per item: "View" (calls `onSelect(request)` prop to load result into GenerationResult), "Download" (PDF only — opens `pdf_url` in new tab), "Regenerate" (calls `onRegenerate({ output_type, prompt })` prop), "Delete" (calls `DELETE /api/v1/generate/{id}` with `window.confirm`, invalidates query on success); empty state: "No generated content yet"
- [x] T033 [US4] Extend frontend/app/(dashboard)/generate/page.tsx: add `<GenerationHistory>` panel; on desktop render split layout (left: form+result, right: history); on mobile render tabbed layout (Generate tab / History tab) using local `activeTab` state; wire `onSelect` to load the selected past request into `currentResult`; wire `onRegenerate` to pre-fill GenerationForm and trigger submission
- [x] T034 [US4] Write additional tests in tests/api/test_generate.py: `test_generate_history_pagination` (limit/offset params respected); `test_generate_pdf_no_template` (POST pdf type without pdf_template → 422); `test_generate_delete_removes_gcs` (mock `delete_from_gcs`, verify it is called when deleting a PDF request); `test_generate_get_detail_not_owned` (user B cannot GET user A's request → 404)

---

## Phase 7: Polish

- [x] T035 Add Generate nav link to frontend/components/layout/Sidebar.tsx: insert `{ href: "/generate", label: "Generate", icon: Sparkles, exact: false }` into both the admin and marketer `navItems` arrays (import `Sparkles` from `lucide-react`)
- [x] T036 Add `BRAND_IMAGES_BUCKET` and `PDF_SIGNED_URL_EXPIRY_SECONDS` to infra/k8s/ environment configuration: add both variables to the backend deployment env section (reference the existing pattern for `GCS_BUCKET_NAME` and `CHAT_MAX_TOKENS`) and document in the backend Kubernetes Secret or ConfigMap as appropriate
- [x] T037 Update marketing-platform/CLAUDE.md: add `utils/generator.py` (RAG-grounded structured content generation), `utils/pdf_renderer.py` (WeasyPrint HTML→PDF renderer), `src/api/generate.py` (generation CRUD), and `src/api/images.py` (brand image management) to the `utils/ Inventory` and API sections

---

## Dependencies

```
Phase 1 (Setup)
    └── Phase 2 (Foundation: models, migration, gcs extensions)
            ├── Phase 3 (US1: Email — core backend + UI)
            │       └── Phase 4 (US2: LinkedIn — extends US1 generator + UI)
            │               └── Phase 5 (US3: PDF — extends US1/US2 generator + adds images)
            │                       └── Phase 6 (US4: History — UI only, depends on API from US1)
            └── Phase 7 (Polish — can run in parallel with Phases 3–6)
```

Story independence:
- **US1 is the critical path** — all other stories depend on the foundation it establishes
- **US2** depends on US1 (same API endpoint, extends generator and UI)
- **US3** depends on US1 (extends the same POST endpoint and generator utility)
- **US4** depends on US1 (history API uses the same `generation_requests` table and GET endpoints created in US1)

---

## Parallel Execution Opportunities

Within each phase, tasks marked `[P]` can run simultaneously:

**Phase 2**:
- T004 (BrandImage model) ‖ T005 (GenerationRequest model) → then T006 (migration, requires both models)

**Phase 3**:
- T011 (TypeScript types) can run in parallel with T008–T010 (backend)

**Phase 5**:
- T020 (one_pager template) ‖ T021 (campaign_brief template) — after T019 (base.css)
- T025 (images API) can run in parallel with T022–T024 (pdf renderer + generator extension)

---

## Task Count Summary

| Phase | Story | Tasks |
|-------|-------|-------|
| Phase 1: Setup | — | 3 |
| Phase 2: Foundation | — | 4 |
| Phase 3: US1 Email | P1 | 8 |
| Phase 4: US2 LinkedIn | P1 | 3 |
| Phase 5: US3 PDF | P2 | 13 |
| Phase 6: US4 History | P3 | 3 |
| Phase 7: Polish | — | 3 |
| **Total** | | **37** |
