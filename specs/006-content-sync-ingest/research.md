# Research: Content Sync & Ingestion Pipeline

**Feature**: 006-content-sync-ingest
**Date**: 2026-03-14

---

## Decision 1: GitHub Sync Mechanism — REST API Tree Endpoint

**Decision**: Use the GitHub REST API `GET /repos/{owner}/{repo}/git/trees/{sha}?recursive=1` endpoint to discover all files, then `GET /repos/{owner}/{repo}/contents/{path}` to fetch individual file content.

**Rationale**: The recursive tree endpoint returns the full repo tree (all paths + blob SHAs) in a single API call, making it extremely efficient for change detection. Individual file content fetches are only needed for files whose blob SHA has changed since last sync. This eliminates redundant API calls and embedding work for unchanged files.

**Alternatives considered**:
- `git clone` via `utils/github_client.py`: Violates CONSTITUTION §Stateless Services ("no writable local volumes"). The existing `TENANT_DATA_DIR` approach is unsuitable for a stateless K8s deployment. Ruled out.
- Per-folder `GET /repos/{owner}/{repo}/contents/{folder}` listing: Requires one API call per folder, not recursive. Inefficient for repos with many folders. Ruled out.

**Implementation sequence for sync**:
1. `GET /repos/{owner}/{repo}` → get `default_branch` name
2. `GET /repos/{owner}/{repo}/git/ref/heads/{default_branch}` → get HEAD commit SHA
3. `GET /repos/{owner}/{repo}/git/trees/{commit_sha}?recursive=1` → get full tree (filter `type=blob`, extension=`.md`, paths matching configured folders)
4. For each `.md` file in configured folders: compare `blob.sha` against stored `synced_documents.content_sha`
5. Fetch content only for new/changed files: `GET /repos/{owner}/{repo}/contents/{path}` (returns base64 content + sha)
6. Upsert `synced_documents` and queue KB indexing for changed files
7. Mark removed files: files previously in DB but absent from tree → set `is_active=false`

**Rate limits**: 5,000 requests/hour for authenticated users. A single tree fetch covers all files; individual content fetches are bounded by changed files only. No rate limit concern for normal sync volumes.

---

## Decision 2: Scheduled Sync — Asyncio Sleep Loop

**Decision**: Implement the scheduled sync as an asyncio background task with a configurable sleep interval (`SYNC_INTERVAL_HOURS` env var, default `24`), consistent with the existing `queue.py` worker pattern. No external scheduler library (APScheduler) needed.

**Rationale**: The project already uses asyncio background tasks (`start_queue_workers`, `start_indexing_workers`) in `utils/queue.py`. Adding a sync scheduler as the same pattern maintains consistency, avoids a new dependency, and integrates cleanly with FastAPI's lifespan context manager. APScheduler would be overkill for a single periodic task.

**Concurrent sync prevention**: Before starting a sync run, query `sync_runs` for any row with `outcome = "in_progress"` for the active connection. If found, skip and log a warning. This prevents both scheduled + manual runs from overlapping, and handles multi-pod scenarios where the check is done atomically with INSERT using `SELECT FOR UPDATE SKIP LOCKED` on a synthetic lock row (or a simple status check — acceptable given sync is infrequent).

**Startup recovery**: On app startup, any `sync_run` with `outcome = "in_progress"` older than 30 minutes is reset to `outcome = "interrupted"`. The next scheduled/manual sync will start fresh.

**Alternatives considered**:
- APScheduler: Adds a dependency, requires configuration for asyncio mode, adds no benefit over a sleep loop for a single periodic task. Ruled out.
- External cron (Kubernetes CronJob): Would require a separate container/job, complicating deployment. All logic is self-contained in the app. Ruled out.

---

## Decision 3: Ingest PR Workflow — GitHub Contents API for Commit + PR

**Decision**: The file upload → commit → PR workflow uses the GitHub Contents API (no local git required). Worker creates a branch, commits the generated Markdown, and opens a PR entirely via REST API calls.

**Branch + PR creation sequence**:
1. `GET /repos/{owner}/{repo}` → get `default_branch`
2. `GET /repos/{owner}/{repo}/git/ref/heads/{default_branch}` → get HEAD SHA
3. `POST /repos/{owner}/{repo}/git/refs` with `ref=refs/heads/ingest/{sanitized_name}-{unix_ts}` → create branch
4. `PUT /repos/{owner}/{repo}/contents/{destination_folder}/{sanitized_name}.md` with `branch=ingest/...` → commit file (content = base64-encoded Markdown)
5. `POST /repos/{owner}/{repo}/pulls` with `head=ingest/...`, `base={default_branch}` → create PR

**Move file (folder override at review)**:
When the admin selects a different destination folder during PR review, before merging:
1. `GET /repos/{owner}/{repo}/contents/{old_path}?ref={branch}` → get current file SHA
2. `DELETE /repos/{owner}/{repo}/contents/{old_path}` with `branch=...` and `sha=...` → delete from old path
3. `PUT /repos/{owner}/{repo}/contents/{new_path}` with `branch=...` → create at new path
4. Then `PUT /repos/{owner}/{repo}/pulls/{number}/merge` → merge

**PR merge**: `PUT /repos/{owner}/{repo}/pulls/{pr_number}/merge` with `merge_method=merge` (configurable via `GITHUB_MERGE_METHOD` env var, default `merge`).

**PR close (reject)**: `PATCH /repos/{owner}/{repo}/pulls/{pr_number}` with `state=closed`.

**Alternatives considered**:
- Accepting only a single destination path at commit time (no override): Simpler, but spec requires admin to be able to change destination at review. Ruled out.
- Using `git push` from local clone: Requires local filesystem. Ruled out.

---

## Decision 4: Content Indexing — Dual Source KnowledgeBaseDocument

**Decision**: `KnowledgeBaseDocument` is extended to support two content sources: (a) the existing `ProcessedDocument` (file upload pipeline) and (b) a new `SyncedDocument` (GitHub sync pipeline). Both `processed_document_id` and `synced_document_id` become nullable FKs; exactly one must be non-null.

**Rationale**: The existing indexer (`utils/indexer.py`) loads content from `ProcessedDocument.structured_content`. For synced documents, content comes directly from the repo file. Making the indexer source-agnostic avoids duplicating chunk/embed logic. A simple check — which FK is set — determines which source to load.

**Alternatives considered**:
- Separate `SyncedKnowledgeBaseDocument` table: Duplicates indexing logic. Ruled out.
- Store synced content directly in `ProcessedDocument`: Incorrect coupling — synced docs have no approval step. Ruled out.

---

## Decision 5: Email Notifications — Extend utils/email.py

**Decision**: Add `send_pr_merged_notification()` and `send_pr_rejected_notification()` functions to the existing `utils/email.py`. Pattern matches `send_invitation_email()`: async, best-effort (log on failure, do not raise).

**Rationale**: The SMTP configuration and aiosmtplib sending pattern are already established. Adding two functions follows the existing pattern precisely without any new dependencies.

---

## Decision 6: Folder Management — Extend Existing GitHub Config Endpoints

**Decision**: Add `POST /github/config/folders` and `DELETE /github/config/folders/{folder_name}` endpoints to `src/api/github.py`. These modify the `RepoStructureConfig.folders` JSON array and trigger scaffold for new folders.

**Rationale**: The `PUT /github/config` endpoint already replaces the entire folder list. Granular add/delete endpoints provide better UX (admin can add one folder at a time without resending the entire list). The scaffold utility (`utils/github_api.scaffold_repository`) already handles creating individual folders — it can be called with a single-element list.

---

## Decision 7: Content Browser — New /content Endpoint

**Decision**: Add `GET /api/v1/content` to a new `src/api/content.py` router. Returns a paginated list of `SyncedDocument` records with `index_status` join from `KnowledgeBaseDocument`. Accessible to all authenticated roles (not admin-only).

**Rationale**: The existing `/admin/knowledge-base/status` endpoint is admin-only and returns summary counts. A new endpoint exposes the per-document list needed by the content browser, and is role-accessible per spec (FR-023).
