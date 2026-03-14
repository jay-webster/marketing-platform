# Marketing Platform — Claude Code Configuration

Inherits from: `../CLAUDE.md` and `~/.claude/CLAUDE.md`

---

## Project Identity
**Marketing Content-as-Code Platform (MVP)**
Single-organization platform where marketing teams manage content via version control. Deployed as a per-client Docker image. AI agent assists in content distribution and data interrogation.

---

## Source Layout

```
marketing-platform/
├── src/
│   └── api/            ← FastAPI routers (one file per domain)
├── utils/              ← Shared managers (DB, Snowflake, auth)
├── specs/              ← Architecture and plan documents
├── infra/
│   └── k8s/            ← Kubernetes manifests
├── tests/              ← Pytest test suite
├── CONSTITUTION.md     ← Immutable principles (read before every code output)
└── SPECIFICATION.md    ← Current feature scope
```

---

## Authentication Rules (Critical)

Every route that accesses application data MUST verify an authenticated session before executing any logic. Authentication middleware runs first — no exceptions.

```python
# Every protected router depends on the auth guard
@router.get("/content", dependencies=[Depends(require_authenticated_user)])
```

- Never access the database from an endpoint that has not verified a session.
- Role checks come after authentication — never instead of it.

---

## utils/ Inventory — Check Before Writing

| Module | Purpose |
|---|---|
| `utils/db.py` | Async SQLAlchemy engine + `get_db` session dependency |
| `utils/auth.py` | JWT creation/decode, `get_current_user`, `require_role()` |
| `utils/audit.py` | `write_audit()` — append-only audit log entries |
| `utils/email.py` | `send_invitation_email()` via aiosmtplib |
| `utils/github_client.py` | Subprocess git clone/update for content sync (Epic 3+) |
| `utils/github_api.py` | Async httpx GitHub REST API client — validation + scaffolding (Epic 2) |
| `utils/crypto.py` | Fernet encrypt/decrypt for GitHub PATs (Epic 2) |
| `utils/gcs.py` | GCS upload/download/delete via google-cloud-storage (Epic 3) |
| `utils/extractors.py` | Format-specific text extraction — PDF, DOCX, PPTX, CSV, TXT/MD (Epic 3) |
| `utils/ingestion_pipeline.py` | Claude-powered Markdown structuring pipeline (Epic 3) |
| `utils/queue.py` | PostgreSQL SKIP LOCKED async worker pool — document processing + KB indexing (Epic 3+4) |
| `utils/embeddings.py` | OpenAI text-embedding-3-small client — `embed_text()`, `embed_batch()` (Epic 4) |
| `utils/chunker.py` | Markdown section-primary chunker with frontmatter prepend (Epic 4) |
| `utils/indexer.py` | KB indexing pipeline — chunk + embed + upsert to content_chunks (Epic 4) |
| `utils/rag.py` | pgvector retrieval, prompt assembly, SSE stream generator (Epic 4) |

Before writing any new utility, check if one exists here. If it partially covers the need, extend it.

---

## API Conventions

- All routes live in `src/api/`. One router file per domain (e.g., `content.py`, `tenant.py`, `agent.py`).
- Every router must include the global exception handler middleware.
- Authentication middleware must run before any business logic.
- Admin routes must verify `X-Admin-Token`. Return 403 immediately if invalid.
- All responses use consistent shape: `{ "data": ..., "request_id": ... }`

---

## Database Conventions

- Migrations managed via Alembic.
- All migrations must be reversible (include `downgrade()`).
- Use `INSERT ... ON CONFLICT DO UPDATE` (UPSERT) for all sync operations.
- Audit trail: admin actions must log `actor_id` + `timestamp` to `system_audit` table.

---

## Test Requirements

- Every new API endpoint requires at least one happy-path test and one auth-failure test.
- Role boundary must be tested: a lower-privilege role must not successfully perform a higher-privilege action.
- Test file mirrors source file: `src/api/content.py` → `tests/api/test_content.py`.

---

## CONSTITUTION Compliance Checklist

Before outputting any code, verify:
- [ ] **AUTH_SAFE** — Endpoint verifies an authenticated session before accessing data
- [ ] **DRY** — Reuses existing `utils/` managers
- [ ] **NON_BLOCKING** — Stateless, no local container state

---

## Environment Variables (Never Hardcode)

| Variable | Purpose |
|---|---|
| `DATABASE_URL` | Postgres connection string |
| `SECRET_KEY` | JWT signing key |
| `INITIAL_ADMIN_TOKEN` | One-time admin bootstrap token |
| `ADMIN_TOKEN` | Admin endpoint authentication |
| `GITHUB_TOKEN_ENCRYPTION_KEY` | Fernet key for encrypting stored GitHub PATs |
| `SNOW_ACCOUNT` | Snowflake account identifier |
| `SNOW_USER` | Snowflake username |
| `SNOW_PASS` | Snowflake password |
| `ANTHROPIC_API_KEY` | Claude API access (document processing + chat generation) |
| `GCS_BUCKET_NAME` | GCS bucket for transient ingestion source files (Epic 3) |
| `WORKER_CONCURRENCY` | Number of ingestion processing workers (default 5) (Epic 3) |
| `VOYAGE_API_KEY` | Voyage AI embeddings API — voyage-3-lite (Epic 4) |
| `KB_SIMILARITY_THRESHOLD` | Cosine similarity floor for RAG retrieval (default 0.3) (Epic 4) |
| `KB_RETRIEVAL_TOP_K` | Chunks returned per query (default 6) (Epic 4) |
| `CHAT_MODEL` | Claude model for chat generation (default claude-opus-4-6) (Epic 4) |
| `CHAT_MAX_TOKENS` | Max tokens per chat response (default 1024) (Epic 4) |
| `KB_INDEX_CONCURRENCY` | Indexing worker count (default 2) (Epic 4) |
| `SYNC_INTERVAL_HOURS` | Scheduled sync interval in hours (default 24) (Epic 6) |
| `GITHUB_MERGE_METHOD` | GitHub PR merge strategy: merge/squash/rebase (default merge) (Epic 6) |
| `APP_URL` | Public base URL |
| `SMTP_HOST` / `SMTP_PORT` / `SMTP_FROM` | Email delivery |

## Active Technologies
- Python 3.11 / FastAPI (backend), Next.js 15 App Router (frontend) + SQLAlchemy async, httpx, Alembic, aiosmtplib, Anthropic SDK, Voyage AI (all existing) (006-content-sync-ingest)
- PostgreSQL 16 + pgvector (primary), GCS (transient file staging) (006-content-sync-ingest)

## Recent Changes
- 006-content-sync-ingest: Added Python 3.11 / FastAPI (backend), Next.js 15 App Router (frontend) + SQLAlchemy async, httpx, Alembic, aiosmtplib, Anthropic SDK, Voyage AI (all existing)
