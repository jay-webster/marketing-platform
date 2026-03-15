# Data Model: AI-Powered Marketing Content Generation

**Branch**: `007-content-generation` | **Date**: 2026-03-15
**Spec**: [spec.md](./spec.md) | **Research**: [research.md](./research.md)

---

## New Entities

### `brand_images`

Stores metadata for brand images available for PDF generation. Binary assets are stored in GCS; this table holds queryable metadata only.

| Column | Type | Constraints | Notes |
|--------|------|-------------|-------|
| `id` | UUID | PK, default gen_random_uuid() | |
| `filename` | VARCHAR(255) | NOT NULL | Original filename (e.g. `hero-shot.png`) |
| `gcs_object_name` | VARCHAR(500) | NOT NULL, UNIQUE | GCS object path (e.g. `brand-images/{id}/hero-shot.png`) |
| `content_type` | VARCHAR(100) | NOT NULL | MIME type (`image/png`, `image/jpeg`, etc.) |
| `display_title` | VARCHAR(255) | | User-facing name; defaults to filename stem without extension |
| `source` | VARCHAR(50) | NOT NULL | `'github_sync'` or `'admin_upload'` |
| `file_size_bytes` | INTEGER | | Size in bytes |
| `is_active` | BOOLEAN | NOT NULL, default TRUE | FALSE when removed from GitHub repo (soft delete for sync-sourced images) |
| `created_at` | TIMESTAMPTZ | NOT NULL, default NOW() | |
| `updated_at` | TIMESTAMPTZ | NOT NULL, default NOW() | |

**Indexes**:
- `idx_brand_images_active` on `is_active` WHERE `is_active = TRUE`
- `idx_brand_images_source` on `source`

**Validation rules**:
- `source` must be one of `{'github_sync', 'admin_upload'}`
- `content_type` must match an allowed image MIME type

**State transitions**:
- GitHub-synced images: `is_active = TRUE` on creation/update; `is_active = FALSE` when removed from repo
- Admin-uploaded images: Always `is_active = TRUE` until explicitly deleted via API (hard delete)

---

### `generation_requests`

Records each content generation action. Persisted until explicitly deleted by the user.

| Column | Type | Constraints | Notes |
|--------|------|-------------|-------|
| `id` | UUID | PK, default gen_random_uuid() | |
| `user_id` | UUID | NOT NULL, FK → `users.id` | Owner of the request |
| `output_type` | VARCHAR(50) | NOT NULL | `'email'`, `'linkedin'`, or `'pdf'` |
| `prompt` | TEXT | NOT NULL | User's generation prompt (max 2000 chars enforced at API layer) |
| `pdf_template` | VARCHAR(100) | | Template name for PDF type (e.g. `'one_pager'`, `'campaign_brief'`); NULL for text types |
| `selected_image_ids` | UUID[] | | Array of `brand_images.id` selected for PDF; NULL or empty for text types |
| `status` | VARCHAR(50) | NOT NULL, default `'pending'` | `'pending'`, `'completed'`, `'failed'` |
| `result_text` | TEXT | | Full generated text for email/LinkedIn; NULL for PDF type |
| `result_pdf_gcs_name` | VARCHAR(500) | | GCS object name of the generated PDF; NULL for text types |
| `failure_reason` | TEXT | | Error detail if `status = 'failed'`; NULL otherwise |
| `created_at` | TIMESTAMPTZ | NOT NULL, default NOW() | |
| `updated_at` | TIMESTAMPTZ | NOT NULL, default NOW() | |

**Indexes**:
- `idx_generation_requests_user_id` on `user_id`
- `idx_generation_requests_user_created` on `(user_id, created_at DESC)` — supports paginated history queries

**Validation rules**:
- `output_type` must be one of `{'email', 'linkedin', 'pdf'}`
- `status` must be one of `{'pending', 'completed', 'failed'}`
- `pdf_template` required when `output_type = 'pdf'`
- `selected_image_ids` only valid when `output_type = 'pdf'`

**State machine**:
```
pending → completed  (successful generation)
pending → failed     (API error, RAG no-content, rendering failure)
```

---

## Entity Relationships

```
users (existing)
  └── generation_requests (user_id FK)
          └── [selected_image_ids] → brand_images (array FK, no cascaded constraint)

brand_images (standalone — no FK to other tables)
```

`selected_image_ids` is stored as a UUID array rather than a join table. This preserves a snapshot of which images were selected at generation time, even if an image is later deleted. The relationship is informational, not enforced at the DB level.

---

## Alembic Migration

Single migration file: `migrations/versions/xxxx_add_content_generation_tables.py`

**Upgrade**: CREATE TABLE `brand_images`, CREATE TABLE `generation_requests`, CREATE INDEXes

**Downgrade**: DROP TABLE `generation_requests`, DROP TABLE `brand_images`

---

## Existing Entities (unchanged)

No changes to existing tables. The generation feature is additive only.

| Table | Usage in this feature |
|-------|----------------------|
| `users` | `generation_requests.user_id` FK; `require_role(Role.ADMIN)` for image upload |
| `content_chunks` | RAG retrieval via `utils/rag.py` — unchanged |
| `knowledge_base_documents` | RAG retrieval — unchanged |
