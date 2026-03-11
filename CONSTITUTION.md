Tenant Safety: Any agent function that queries the database must first be verified for the inclusion of a tenant_id filter.

Environment Discipline: All infrastructure parameters must be managed via infra/ manifests. No manual GCP CLI commands are allowed; everything must be reproducible via Terraform or K8s YAML.

The "DRY" Principle: If a connection, auth, or sync utility already exists in utils/, we do not rewrite it—we extend it.

Stateless Services: All API services must be stateless. No user session data, temporary files, or cached state shall be stored on the local container filesystem. Use Redis for session management and GCP Cloud Storage for transient file processing.

Error Handling: Every API endpoint must include a global exception handler. All database connection errors must be logged with a unique request_id to allow for rapid debugging in production logs.

Idempotent Operations: All data sync operations must be idempotent. If a script is run twice, it must not create duplicate records. Use UPSERT logic (or INSERT ... ON CONFLICT) by default.

## Administrative Security

- **ADMIN_TOKEN Protocol:** Any administrative endpoint (e.g., `/register-repo`, `/system-health`) must be protected by an environment-variable-defined `ADMIN_TOKEN`. 
- **Header Requirement:** Administrative routes must verify the `X-Admin-Token` header. If missing or invalid, the request must return a `403 Forbidden` immediately.
- **Audit Logging:** Every administrative action (tenant creation, database schema modifications) must log the `tenant_name` and `timestamp` to a dedicated `system_audit` table.
- **Credential Rotation:** The `ADMIN_TOKEN` must be rotated every 90 days. The system shall support a dual-token overlap period (allowing both the old and new token to work for 24 hours) to ensure zero-downtime during rotation.
- **Exposure Prevention:** Never log the `ADMIN_TOKEN` in application logs, even on error.

## Agent Compliance Protocol
Before outputting any code, the agent must evaluate the response against these labels:
- [ ] **TENANT_SAFE**: Does this query enforce `tenant_id` scoping?
- [ ] **DRY**: Does this reuse existing `utils/` managers?
- [ ] **NON_BLOCKING**: Is this logic stateless and cloud-ready?