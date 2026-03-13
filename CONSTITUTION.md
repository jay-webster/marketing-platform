# Marketing Platform — Constitution

Immutable principles. All code and infrastructure decisions must comply. Never violate these rules.

---

## Authentication Safety

Every API endpoint that accesses application data must verify an authenticated session. No data operation may proceed without a valid, authenticated user context. Authentication middleware runs before any business logic — no exceptions.

---

## Environment Discipline

All infrastructure parameters must be managed via `infra/` manifests (Kubernetes YAML + Kustomize overlays). No manual GCP console changes; every resource must be reproducible from the repo.

---

## The "DRY" Principle

If a connection, auth, or sync utility already exists in `utils/`, do not rewrite it — extend it. Check `utils/` before creating any new module.

---

## Stateless Services

All API services must be stateless. No user session data, temporary files, or cached state shall be stored on the local container filesystem.

- **Sessions**: JWT-based, backed by the `sessions` table in PostgreSQL. No Redis dependency.
- **Transient files**: Use GCS for ingestion source files. Delete from GCS after successful processing.
- **No local volumes**: Kubernetes pods must not mount writable local volumes for application state.

---

## Error Handling

Every API endpoint must include a global exception handler. All unhandled errors must be logged with a unique `request_id` to allow for rapid debugging in production logs. Never expose internal stack traces to API consumers.

---

## Idempotent Operations

All data sync operations must be idempotent. Running an operation twice must not create duplicate records. Use `INSERT ... ON CONFLICT DO UPDATE` (UPSERT) by default for all sync writes.

---

## Administrative Security

- **ADMIN_TOKEN Protocol**: Any administrative endpoint must be protected by an environment-variable-defined `ADMIN_TOKEN`.
- **Header Requirement**: Administrative routes must verify the `X-Admin-Token` header. If missing or invalid, return `403 Forbidden` immediately.
- **Audit Logging**: Every administrative action must log `actor_id` and `timestamp` to the `audit_log` table.
- **Credential Rotation**: The `ADMIN_TOKEN` must be rotated every 90 days. The system must support a dual-token overlap period (old and new token both valid for 24 hours) to ensure zero-downtime rotation.
- **Exposure Prevention**: Never log the `ADMIN_TOKEN` in application logs, even on error.

---

## Deployment Architecture

The platform deploys as a **per-client isolated installation**. Each client gets:
- One GKE Deployment (this repository's container image)
- One Cloud SQL PostgreSQL instance (single-tenant — no RLS, no tenant scoping)
- One GCS bucket (transient ingestion file storage)

There is no shared multi-tenant infrastructure. Cross-client data isolation is guaranteed at the infrastructure level, not the application layer.

**Production stack:**
| Layer | Technology |
|---|---|
| Compute | GCP GKE (Google Kubernetes Engine) |
| Container registry | GCP Artifact Registry (`us-central1-docker.pkg.dev`) |
| Database | GCP Cloud SQL — PostgreSQL 16 with pgvector extension |
| File storage | GCP Cloud Storage (GCS) |
| Domain | `api.activelab.com` (subdomain of activelab.com) |
| CI/CD | GitHub Actions — deploy on merge to `main` |

---

## Agent Compliance Checklist

Before outputting any code, evaluate against:
- [ ] **AUTH_SAFE** — Does this endpoint verify an authenticated session before accessing data?
- [ ] **DRY** — Does this reuse existing `utils/` managers?
- [ ] **NON_BLOCKING** — Is this logic stateless and cloud-ready?
