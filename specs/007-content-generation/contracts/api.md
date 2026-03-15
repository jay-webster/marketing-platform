# API Contracts: AI-Powered Marketing Content Generation

**Branch**: `007-content-generation` | **Date**: 2026-03-15
**Spec**: [spec.md](../spec.md) | **Data Model**: [data-model.md](../data-model.md)

All endpoints are under the `/api/v1` prefix. All responses follow the standard envelope: `{ "data": ..., "request_id": "..." }`. All endpoints require authentication (`Authorization: Bearer <jwt>`).

---

## Content Generation Endpoints

### `POST /api/v1/generate`

Generates a marketing content item. Runs synchronously — response is returned when generation is complete.

**Auth**: Any authenticated user

**Request body**:
```json
{
  "output_type": "email" | "linkedin" | "pdf",
  "prompt": "string (1–2000 characters)",
  "pdf_template": "one_pager" | "campaign_brief",  // required when output_type=pdf
  "image_ids": ["uuid", ...]                         // optional, only for output_type=pdf
}
```

**Validation**:
- `prompt` must not be empty or whitespace-only → 422
- `prompt` length must not exceed 2000 characters → 422
- `pdf_template` is required when `output_type = "pdf"` → 422
- `image_ids` is ignored for non-PDF output types
- `image_ids` entries must reference existing active `brand_images` rows → 422 if any are invalid
- If RAG retrieval returns no relevant knowledge base content → `200` with `status: "failed"`, `failure_reason: "no_kb_content"`

**Response (success)**:
```json
{
  "data": {
    "id": "uuid",
    "output_type": "email",
    "status": "completed",
    "prompt": "...",
    "result": {
      "subject": "string",         // email only
      "body": "string",            // email only
      "post_text": "string",       // linkedin only
      "hashtags": ["string"],      // linkedin only
      "pdf_url": "https://...",    // pdf only, signed URL valid 24h
      "pdf_filename": "string"     // pdf only
    },
    "created_at": "ISO 8601"
  },
  "request_id": "string"
}
```

**Response (no KB content)**:
```json
{
  "data": {
    "id": "uuid",
    "output_type": "email",
    "status": "failed",
    "failure_reason": "no_kb_content",
    "prompt": "...",
    "created_at": "ISO 8601"
  },
  "request_id": "string"
}
```

**Error responses**:
- `401 Unauthorized` — missing or invalid JWT
- `422 Unprocessable Entity` — validation failure (prompt empty/too long, missing pdf_template, invalid image_ids)
- `500 Internal Server Error` — unexpected generation failure (PDF rendering error, Anthropic API error)

---

### `GET /api/v1/generate`

Returns the authenticated user's generation history, newest first.

**Auth**: Any authenticated user

**Query parameters**:
| Param | Type | Default | Description |
|-------|------|---------|-------------|
| `limit` | integer | 20 | Max items (1–100) |
| `offset` | integer | 0 | Pagination offset |

**Response**:
```json
{
  "data": [
    {
      "id": "uuid",
      "output_type": "email" | "linkedin" | "pdf",
      "status": "completed" | "failed",
      "prompt": "string",
      "pdf_url": "https://...",   // pdf only, fresh signed URL; null for text types
      "created_at": "ISO 8601"
    }
  ],
  "total": 42,
  "limit": 20,
  "offset": 0,
  "request_id": "string"
}
```

For text types (`email`, `linkedin`), the full `result` payload is omitted in the list view. Use `GET /api/v1/generate/{id}` to retrieve the full content.

---

### `GET /api/v1/generate/{id}`

Returns the full detail of a single generation request.

**Auth**: Authenticated user; must own the request (returns 404 if not found or not owned)

**Response**: Same shape as `POST /api/v1/generate` success response, with a freshly generated signed URL for PDF items.

**Error responses**:
- `404 Not Found` — request not found or not owned by caller

---

### `DELETE /api/v1/generate/{id}`

Deletes a generation request and associated GCS PDF (if any).

**Auth**: Authenticated user; must own the request

**Response**: `204 No Content`

**Error responses**:
- `404 Not Found` — request not found or not owned by caller

---

## Brand Image Endpoints

### `GET /api/v1/images`

Returns all active brand images. Used by the image picker component.

**Auth**: Any authenticated user

**Query parameters**:
| Param | Type | Default | Description |
|-------|------|---------|-------------|
| `limit` | integer | 50 | Max items (1–200) |
| `offset` | integer | 0 | Pagination offset |

**Response**:
```json
{
  "data": [
    {
      "id": "uuid",
      "filename": "hero-shot.png",
      "display_title": "Hero Shot",
      "content_type": "image/png",
      "source": "github_sync" | "admin_upload",
      "thumbnail_url": "https://...",   // signed URL valid 24h
      "created_at": "ISO 8601"
    }
  ],
  "total": 12,
  "limit": 50,
  "offset": 0,
  "request_id": "string"
}
```

---

### `POST /api/v1/images`

Upload a new brand image. Admin only.

**Auth**: Admin role required

**Request**: `multipart/form-data`
| Field | Type | Required | Notes |
|-------|------|----------|-------|
| `file` | file | Yes | PNG, JPG, JPEG, WEBP, GIF only; max 10MB |
| `display_title` | string | No | Defaults to filename stem |

**Response**:
```json
{
  "data": {
    "id": "uuid",
    "filename": "hero-shot.png",
    "display_title": "Hero Shot",
    "content_type": "image/png",
    "source": "admin_upload",
    "thumbnail_url": "https://...",
    "created_at": "ISO 8601"
  },
  "request_id": "string"
}
```

**Validation**:
- File must be an allowed image MIME type → 422
- File must not exceed 10MB → 422

**Error responses**:
- `403 Forbidden` — caller is not an admin
- `422 Unprocessable Entity` — invalid file type or size

---

### `DELETE /api/v1/images/{id}`

Deletes a brand image (GCS binary + database row). Admin only.

**Auth**: Admin role required

**Response**: `204 No Content`

**Error responses**:
- `403 Forbidden` — caller is not an admin
- `404 Not Found` — image not found

---

## PDF Template Reference

Two templates available at launch:

| Template key | Display name | Description |
|---|---|---|
| `one_pager` | One-Pager | Single-page marketing overview with title, summary, key points, and optional imagery |
| `campaign_brief` | Campaign Brief | Multi-section brief with objective, audience, messaging, and timeline sections |

---

## Output Type Reference

| `output_type` | Result fields | Max prompt length |
|---|---|---|
| `email` | `subject`, `body` | 2000 chars |
| `linkedin` | `post_text`, `hashtags` | 2000 chars |
| `pdf` | `pdf_url`, `pdf_filename` | 2000 chars |

---

## SSE Events (none — generation is synchronous)

Content generation uses a synchronous HTTP POST, not SSE. The connection remains open until generation is complete (max ~30 seconds for PDF). This differs from the chat feature which uses SSE for progressive streaming.

If future latency requires it, the POST can be replaced with a job-submission POST + polling GET pattern without breaking the data model.
