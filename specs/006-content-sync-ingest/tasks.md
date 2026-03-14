# Tasks: Content Sync & Ingestion Pipeline

**Input**: Design documents from `/specs/006-content-sync-ingest/`
**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/, quickstart.md

**Organization**: Tasks grouped by user story — each story is independently completable and testable.

---

## Phase 1: Setup

**Purpose**: Type definitions and shared frontend types needed by all stories.

- [ ] T001 Update frontend/lib/types.ts: add SyncRun, SyncedContent, PRItem, FolderConfig interfaces (SyncRun: run_id/trigger_type/outcome/files_indexed/files_removed/files_unchanged/started_at/finished_at/error_detail; SyncedContent: id/title/repo_path/folder/index_status/last_synced_at/chunk_count; PRItem: id/original_filename/destination_folder/github_branch/github_pr_number/github_pr_url/submitted_by_name/queued_at; FolderConfig extends GitHubConnection with folders array)

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Database migrations, model changes, and GitHub API utility extensions shared across all user stories.

**⚠️ CRITICAL**: No user story work can begin until all migrations are applied and models are updated.

- [ ] T002 Create Alembic migration 006a: add synced_documents table (id UUID PK, connection_id FK→github_connections CASCADE, repo_path TEXT, title TEXT nullable, raw_content TEXT, content_sha TEXT, folder TEXT, is_active BOOL default true, last_synced_at TIMESTAMPTZ, created_at TIMESTAMPTZ, updated_at TIMESTAMPTZ; UNIQUE(connection_id, repo_path); indexes on (connection_id, is_active) and content_sha) in migrations/versions/006a_add_sync_tables.py
- [ ] T003 Create Alembic migration 006b: add sync_runs table (id UUID PK, connection_id FK→github_connections CASCADE, triggered_by UUID FK→users nullable, trigger_type TEXT, started_at TIMESTAMPTZ, finished_at TIMESTAMPTZ nullable, outcome TEXT default 'in_progress', files_indexed INT default 0, files_removed INT default 0, files_unchanged INT default 0, error_detail TEXT nullable; index on (connection_id, started_at DESC); partial index on (connection_id, outcome) WHERE outcome='in_progress') in migrations/versions/006b_add_sync_runs.py
- [ ] T004 Create Alembic migration 006c: ALTER knowledge_base_documents — ALTER COLUMN processed_document_id DROP NOT NULL; ADD COLUMN synced_document_id UUID REFERENCES synced_documents(id) ON DELETE CASCADE; ADD CONSTRAINT kb_doc_source_xor CHECK ((processed_document_id IS NOT NULL) != (synced_document_id IS NOT NULL)); CREATE UNIQUE INDEX on synced_document_id WHERE synced_document_id IS NOT NULL in migrations/versions/006c_extend_kb_documents.py
- [ ] T005 Create Alembic migration 006d: ALTER ingestion_documents — ADD COLUMN destination_folder TEXT, ADD COLUMN github_branch TEXT, ADD COLUMN github_pr_number INTEGER, ADD COLUMN github_pr_url TEXT in migrations/versions/006d_extend_ingestion_documents.py
- [ ] T006 Create Alembic migration 006e: ALTER github_connections — ADD COLUMN last_synced_at TIMESTAMPTZ, ADD COLUMN default_branch TEXT in migrations/versions/006e_extend_github_connections.py
- [ ] T007 [P] Create SyncedDocument SQLAlchemy model with all columns, UNIQUE constraint, and indexes in src/models/synced_document.py
- [ ] T008 [P] Create SyncRun SQLAlchemy model with all columns, outcome enum values (in_progress/success/partial/failed/interrupted), and indexes in src/models/sync_run.py
- [ ] T009 Extend IngestionDocument model: add destination_folder, github_branch, github_pr_number, github_pr_url Mapped columns; add PR_OPEN = "pr_open" and MERGED = "merged" to ProcessingStatus enum in src/models/ingestion_document.py
- [ ] T010 Extend KnowledgeBaseDocument model: change processed_document_id to Mapped[uuid.UUID | None] (nullable); add synced_document_id Mapped[uuid.UUID | None] as FK to synced_documents with ON DELETE CASCADE in src/models/knowledge_base_document.py
- [ ] T011 Extend GitHubConnection model: add last_synced_at Mapped[datetime | None] and default_branch Mapped[str | None] columns in src/models/github_connection.py
- [ ] T012 Update src/models/__init__.py: import and export SyncedDocument, SyncRun
- [ ] T013 Extend utils/github_api.py: add get_default_branch(repository_url, token) → str and get_repo_tree(repository_url, token, ref) → list[dict] (calls GET /repos/{o}/{r} then GET /repos/{o}/{r}/git/trees/{ref}?recursive=1, returns list of {path, sha, type} filtered to blobs); raise GitHubUnavailableError on timeout/5xx
- [ ] T014 Extend utils/github_api.py: add get_file_content(repository_url, token, path, ref=None) → dict with {content: str, sha: str} (calls GET /repos/{o}/{r}/contents/{path} with Accept: application/vnd.github.v3.raw, base64-decodes response); add create_branch(repository_url, token, branch_name, from_sha) → None (POST /repos/{o}/{r}/git/refs)
- [ ] T015 Extend utils/github_api.py: add commit_file(repository_url, token, path, content, message, branch, file_sha=None) → str (PUT /repos/{o}/{r}/contents/{path}); add delete_file(repository_url, token, path, file_sha, message, branch) → None (DELETE /repos/{o}/{r}/contents/{path}); add create_pr(repository_url, token, title, head, base, body="") → dict {number, url} (POST /repos/{o}/{r}/pulls); add merge_pr(repository_url, token, pr_number, merge_method="merge") → None (PUT /repos/{o}/{r}/pulls/{n}/merge); add close_pr(repository_url, token, pr_number) → None (PATCH /repos/{o}/{r}/pulls/{n} state=closed)

**Checkpoint**: Migrations applied, models updated, GitHub API utilities extended — all user story work can now begin.

---

## Phase 3: User Story 1 — GitHub Repository Sync (Priority: P1) 🎯 MVP

**Goal**: Admin can trigger on-demand sync; system walks configured repo folders, upserts synced_documents, queues KB indexing for changed files, and shows results in content browser.

**Independent Test**: Connect a repo with .md files in a configured folder → POST /github/sync → poll status until success → GET /content → verify files appear.

- [ ] T016 [US1] Create utils/sync.py: implement run_sync(connection_id, triggered_by, trigger_type) — (1) check for in_progress SyncRun and raise if found; (2) create SyncRun(outcome="in_progress"); (3) decrypt token from GitHubConnection via utils/crypto; (4) call get_default_branch, cache in connection.default_branch; (5) call get_repo_tree(ref=default_branch); (6) filter tree to .md blobs whose path starts with any configured folder; (7) load existing synced_documents for this connection; (8) for each tree file compare content_sha — if unchanged increment files_unchanged, if new/changed call get_file_content, upsert SyncedDocument, upsert KnowledgeBaseDocument with synced_document_id set and queue for indexing; (9) for each active DB doc missing from tree set is_active=False and mark KnowledgeBaseDocument as REMOVED; (10) update SyncRun(outcome="success", finished_at, counts); (11) update connection.last_synced_at in utils/sync.py
- [ ] T017 [US1] Extend utils/indexer.py index_document(): after loading kb_doc check if synced_document_id is set — if so load SyncedDocument.raw_content as markdown and build metadata dict {title, repo_path, folder}; otherwise use existing ProcessedDocument path; both paths feed into chunk_markdown + embed_batch + ContentChunk insert in utils/indexer.py
- [ ] T018 [US1] Create src/api/sync.py router (prefix="/github", tags=["sync"]): implement POST /sync — check active connection, call asyncio.create_task(run_sync(...)), return 201 with run_id and outcome="in_progress"; implement GET /sync/status — query latest SyncRun for active connection, return run fields; implement GET /sync/runs — paginated list of SyncRun rows with triggered_by user name join; all endpoints require require_role(Role.ADMIN) in src/api/sync.py
- [ ] T019 [US1] Extend utils/queue.py: add _scheduled_sync_loop() async function that sleeps SYNC_INTERVAL_HOURS * 3600 (from env, default 24) then calls run_sync with trigger_type="scheduled"; add start_sync_scheduler() that creates the asyncio task; extend startup_recovery() to also reset SyncRun rows with outcome="in_progress" older than 30 minutes to outcome="interrupted" in utils/queue.py
- [ ] T020 [US1] Register sync and update lifespan in src/main.py: import sync_router from src.api.sync, add application.include_router(sync_router, prefix="/api/v1"); import start_sync_scheduler and call it in _lifespan after start_indexing_workers; add graceful cancel for sync scheduler task on shutdown in src/main.py
- [ ] T021 [P] [US1] Create frontend/hooks/useSync.ts: implement useSyncStatus() hook (useQuery on GET /api/v1/github/sync/status, refetch every 3s when outcome="in_progress", stale 0); implement useTriggerSync() hook (useMutation POST /api/v1/github/sync, invalidates sync-status and github-connection query keys on success) in frontend/hooks/useSync.ts
- [ ] T022 [P] [US1] Create frontend/hooks/useSyncRuns.ts: useQuery on GET /api/v1/github/sync/runs?limit=5, returns SyncRun[] for history display in frontend/hooks/useSyncRuns.ts
- [X] T023 [US1] Create frontend/components/github/SyncCard.tsx: client component with "Sync Now" button (calls useTriggerSync, disabled while in_progress); shows last sync outcome badge (success=green, failed=red, in_progress=yellow spinner), last sync time, files_indexed/removed counts from useSyncStatus; collapsible "Recent Runs" section showing last 5 runs from useSyncRuns with outcome, file counts, and timestamps in frontend/components/github/SyncCard.tsx
- [X] T024 [US1] Update frontend/app/(dashboard)/github/page.tsx: import and render SyncCard below ConnectionCard; SyncCard only renders if connection is non-null in frontend/app/(dashboard)/github/page.tsx

**Checkpoint**: US1 complete — admin can trigger sync, see status, and indexed files appear in database. Content browser endpoint needed in US3 to surface them in the UI.

---

## Phase 4: User Story 2 — File Upload & PR Ingestion Workflow (Priority: P2)

**Goal**: Users upload documents; worker generates Markdown, creates a GitHub PR; admin reviews in-app and merges or rejects; on merge a re-sync is triggered automatically.

**Independent Test**: Upload PDF as non-admin → approve with destination_folder → worker creates PR → admin GET /ingestion/documents/{id}/pr → POST .../pr/merge → verify processing_status=merged and sync triggered.

- [X] T025 [US2] Extend utils/queue.py process_document(): after structure_document_with_retry succeeds, add new phase — (1) get active GitHubConnection and decrypt token; (2) get doc.destination_folder; (3) sanitize filename for branch: slugify original_filename (lowercase, replace non-alnum with hyphen, strip, max 40 chars); (4) branch_name = f"ingest/{slug}-{int(time.time())}"; (5) get_default_branch → cache; (6) get current HEAD SHA via get_repo_tree ref; (7) create_branch(branch_name, from HEAD SHA); (8) commit_file to f"{destination_folder}/{slug}.md" on branch; (9) create_pr(title=original_filename, head=branch_name, base=default_branch); (10) update doc fields: github_branch, github_pr_number, github_pr_url, processing_status="pr_open"; (11) delete GCS file after successful PR creation (moved from post-markdown); on GitHubUnavailableError set processing_status="failed" with error detail in utils/queue.py
- [X] T026 [US2] Modify POST /ingestion/documents/{doc_id}/approve in src/api/ingestion.py: add ApproveRequest Pydantic model with destination_folder: str field; validate destination_folder is in active RepoStructureConfig.folders list (raise 422 FOLDER_NOT_CONFIGURED if not); store doc.destination_folder = body.destination_folder before setting status to "queued"; add audit metadata with destination_folder in src/api/ingestion.py
- [X] T027 [US2] Add GET /ingestion/prs endpoint in src/api/ingestion.py: admin-only; query IngestionDocument JOIN IngestionBatch JOIN User where processing_status="pr_open" ORDER BY queued_at DESC with limit/offset pagination; return list with id, original_filename, destination_folder, github_branch, github_pr_number, github_pr_url, submitted_by_name, submitted_by_email, queued_at; return total count in src/api/ingestion.py
- [X] T028 [US2] Add GET /ingestion/documents/{doc_id}/pr endpoint in src/api/ingestion.py: admin-only; verify doc.processing_status == "pr_open" (409 DOCUMENT_NOT_PR_OPEN if not); load ProcessedDocument for markdown_content; load active RepoStructureConfig for configured_folders list; return id, original_filename, destination_folder, github_branch, github_pr_number, github_pr_url, markdown_content, current_folder=doc.destination_folder, configured_folders in src/api/ingestion.py
- [X] T029 [US2] Add POST /ingestion/documents/{doc_id}/pr/merge endpoint in src/api/ingestion.py: admin-only; verify processing_status="pr_open"; accept optional PRMergeRequest body with destination_folder; if destination_folder provided and differs from doc.destination_folder: get_file_content(old_path, ref=branch) to get file SHA, delete_file(old_path), commit_file(new_path) on branch; call merge_pr(pr_number, merge_method from GITHUB_MERGE_METHOD env var default "merge"); update doc: processing_status="merged", destination_folder=final_folder; write_audit("ingestion_pr_merged"); asyncio.create_task(run_sync(...)) to trigger immediate re-sync; call send_pr_merged_notification (best-effort, catch and log); return 200 with processing_status, merged_to_folder, sync_triggered=True; handle GitHubUnavailableError as 503 in src/api/ingestion.py
- [X] T030 [US2] Add POST /ingestion/documents/{doc_id}/pr/close endpoint in src/api/ingestion.py: admin-only; verify processing_status="pr_open" (409 if not); call close_pr(pr_number); update doc.processing_status="rejected"; write_audit("ingestion_pr_closed"); call send_pr_rejected_notification (best-effort, catch and log); return 200 with processing_status="rejected"; handle GitHubUnavailableError as 503 in src/api/ingestion.py
- [X] T031 [P] [US2] Create frontend/components/ingestion/PRList.tsx: client component showing table of open PRs (from GET /api/v1/ingestion/prs); columns: filename, submitter, destination folder, PR number (linked to github_pr_url), queued date, Review button linking to /ingestion/pr/[id]; shows empty state when no open PRs; used on admin ingestion page in frontend/components/ingestion/PRList.tsx
- [X] T032 [US2] Create frontend/app/(dashboard)/ingestion/pr/[docId]/page.tsx: async server component; requireRole("admin"); fetch GET /api/v1/ingestion/documents/{docId}/pr server-side; render PRReviewCard with fetched data in frontend/app/(dashboard)/ingestion/pr/[docId]/page.tsx
- [X] T033 [US2] Create frontend/components/ingestion/PRReviewCard.tsx: client component; props: PRReviewData (markdown_content, configured_folders, current_folder, original_filename, github_pr_url, id); left panel shows filename, submitter info, GitHub PR link; main panel renders markdown_content using react-markdown (add dependency if not present); right panel has folder Select (shadcn Select populated from configured_folders, defaulting to current_folder), Merge button (primary, calls POST .../pr/merge with selected folder, toast success + redirect /ingestion), Reject button (destructive, confirmation AlertDialog, calls POST .../pr/close, toast success + redirect /ingestion); loading and error states for both actions in frontend/components/ingestion/PRReviewCard.tsx
- [X] T034 [US2] Update frontend/app/(dashboard)/ingestion/page.tsx: add PRList component (admin-only, conditional on role); use useQueryClient to invalidate pr-list on batch updates; ensure document status display handles pr_open and merged states alongside existing states in frontend/app/(dashboard)/ingestion/page.tsx

**Checkpoint**: US2 complete — full upload → approval → PR → in-app merge/reject workflow functional.

---

## Phase 5: User Story 3 — Content Browser (Priority: P3)

**Goal**: All authenticated users can browse indexed .md files from the connected repo with search and folder filter; role-based visibility for ingestion queue.

**Independent Test**: After US1 sync indexes files, GET /content returns list with titles and repo paths; non-admin cannot see other users' submissions in queue.

- [X] T035 [US3] Create src/api/content.py router (prefix="/content", tags=["content"]): GET /content — authenticated (any role); query SyncedDocument JOIN KnowledgeBaseDocument WHERE synced_docs.is_active=True; support ?search= (ilike filter on title + repo_path), ?folder= (exact folder match), ?limit= (default 50, max 100), ?offset= (default 0); return data list with id, title, repo_path, folder, index_status, last_synced_at, chunk_count; return total count; GET /content/{id} — load SyncedDocument by id (404 if not found or is_active=False); return full record including raw_content in src/api/content.py
- [X] T036 [US3] Register content router in src/main.py: import content_router from src.api.content, add application.include_router(content_router, prefix="/api/v1") in src/main.py
- [X] T037 [US3] Update frontend/components/content/ContentTable.tsx: replace existing stub/empty implementation with react-query useQuery on GET /api/v1/content; add search text input (debounced 300ms) and folder filter Select (populated from configured folders or derived from data); table columns: title (linked to repo_path for external GitHub link), folder, index_status badge, last synced date, chunk count; pagination with 50 per page; empty state shows "No content synced yet — run a sync from the GitHub settings page" in frontend/components/content/ContentTable.tsx
- [X] T038 [US3] Update frontend/app/(dashboard)/content/page.tsx: ensure page is accessible to all authenticated roles (not admin-only); render updated ContentTable; add page heading and description in frontend/app/(dashboard)/content/page.tsx

**Checkpoint**: US3 complete — all users can browse indexed content; search and filter work.

---

## Phase 6: User Story 4 — Folder Management (Priority: P4)

**Goal**: Admin can add new folders (creates in repo via scaffold) and remove folders from the configured list, all from the GitHub settings page.

**Independent Test**: POST /github/config/folders {folder: "content/test"} → verify folder appears in GET /github/config and .gitkeep committed in repo → DELETE /github/config/folders/content%2Ftest → verify removed from config but repo unchanged.

- [X] T039 [US4] Extend src/api/github.py: add POST /config/folders endpoint — require_role(ADMIN); request body {folder: str}; validate folder with existing _validate_config_folders([folder]); load active RepoStructureConfig; check if folder already in config.folders["folders"] list (409 FOLDER_ALREADY_EXISTS if so); add folder to list; update config; call scaffold_repository with single-folder list (best-effort, capture error); write_audit("github_folder_added"); return 201 with folder, full folders list, scaffold outcome in src/api/github.py
- [X] T040 [US4] Extend src/api/github.py: add DELETE /config/folders/{folder_name} endpoint — require_role(ADMIN); URL-decode folder_name path param; load active RepoStructureConfig; check folder exists in list (404 FOLDER_NOT_FOUND if not); remove from list; update config; write_audit("github_folder_removed"); return 200 with removed folder name and remaining folders list; note: does NOT touch the repo in src/api/github.py
- [X] T041 [P] [US4] Create frontend/hooks/useConfigFolders.ts: useQuery on GET /api/v1/github/config returns folders list (type string[]); useAddFolder mutation calling POST /api/v1/github/config/folders; useRemoveFolder mutation calling DELETE /api/v1/github/config/folders/{encodeURIComponent(name)}; both mutations invalidate ["github-config"] and ["github-connection"] query keys on success in frontend/hooks/useConfigFolders.ts
- [X] T042 [US4] Create frontend/components/github/FolderManager.tsx: client component; shows current configured folders as list rows each with folder path and Remove button (calls useRemoveFolder, confirmation toast); "Add Folder" form with text input (validated: no leading/trailing slash, no "..", non-empty) and Add button (calls useAddFolder, shows scaffold outcome in toast — success or warning if scaffold failed); shows loading spinner during mutations; empty state when no folders configured in frontend/components/github/FolderManager.tsx
- [X] T043 [US4] Update frontend/app/(dashboard)/github/page.tsx: import and render FolderManager below SyncCard; FolderManager only renders if connection is non-null; pass connection as prop if needed in frontend/app/(dashboard)/github/page.tsx

**Checkpoint**: US4 complete — admin can manage repo folders from within the app.

---

## Phase 7: User Story 5 — Submission Notifications (Priority: P5)

**Goal**: Submitters receive email when their PR is merged or rejected in-app.

**Independent Test**: Merge a PR for a doc submitted by a test user → verify send_pr_merged_notification called → submitter receives approval email; close a PR → submitter receives rejection email.

- [ ] T044 [US5] Extend utils/email.py: add send_pr_merged_notification(to_email: str, document_title: str, submitter_name: str) — HTML email with subject "Your submission was approved", body confirms document_title was accepted and is available in the knowledge base; add send_pr_rejected_notification(to_email: str, document_title: str, submitter_name: str) — HTML email with subject "Your submission was not accepted"; both functions follow existing pattern: async, aiosmtplib.send, catch all exceptions and log at WARNING level (never re-raise) in utils/email.py
- [ ] T045 [US5] Wire merge notification in src/api/ingestion.py POST .../pr/merge endpoint: after successful merge, load submitter email and display_name via IngestionBatch.submitted_by → User join; call await send_pr_merged_notification(to_email, document_title, submitter_name) wrapped in try/except (best-effort — do not fail the merge if notification fails); similarly wire send_pr_rejected_notification in POST .../pr/close endpoint in src/api/ingestion.py

**Checkpoint**: US5 complete — submitters notified on merge or rejection.

---

## Phase 8: Polish & Cross-Cutting Concerns

**Purpose**: Audit coverage, frontend error handling, integration validation.

- [ ] T046 [P] Verify audit logging: confirm write_audit() is called in all new endpoints — github_sync_triggered (POST /sync), github_folder_added (POST /config/folders), github_folder_removed (DELETE /config/folders/{name}), ingestion_pr_merged (PR merge), ingestion_pr_closed (PR close); check no write_audit calls use non-user UUIDs as target_id in src/api/sync.py, src/api/github.py, src/api/ingestion.py
- [ ] T047 [P] Add SYNC_INTERVAL_HOURS and GITHUB_MERGE_METHOD to src/config.py Settings class with defaults ("24" and "merge" respectively) and update CLAUDE.md env vars table in src/config.py
- [ ] T048 Run quickstart.md US1 sync scenario: connect repo, trigger sync, verify content appears in GET /content; confirm idempotent re-sync produces files_unchanged count and no duplicates
- [ ] T049 Run quickstart.md US2 PR workflow: upload file as non-admin, approve with folder, verify PR created, review in-app, merge, verify sync triggered and file appears in content browser
- [ ] T050 Frontend: add error.tsx boundary for frontend/app/(dashboard)/ingestion/pr/[docId]/ route to handle 404/403 gracefully in frontend/app/(dashboard)/ingestion/pr/[docId]/error.tsx

---

## Dependencies & Execution Order

### Phase Dependencies

- **Phase 1 (Setup)**: No dependencies — start immediately
- **Phase 2 (Foundational)**: Depends on Phase 1 — BLOCKS all user stories
- **Phase 3 (US1)**: Depends on Phase 2 — migrations + models + GitHub API utils must be complete
- **Phase 4 (US2)**: Depends on Phase 2 — PR workflow uses same GitHub API utils; can run in parallel with US1
- **Phase 5 (US3)**: Depends on Phase 3 (US1) — content browser surfaces synced_documents; needs run_sync to exist
- **Phase 6 (US4)**: Depends on Phase 2 — folder endpoints extend existing github.py; independent of US1/US2
- **Phase 7 (US5)**: Depends on Phase 4 (US2) — notifications wired into PR merge/close endpoints
- **Phase 8 (Polish)**: Depends on all user stories being complete

### User Story Dependencies

- **US1 (sync)**: Depends on Foundational only — no other story dependencies
- **US2 (PR workflow)**: Depends on Foundational only — runs in parallel with US1
- **US3 (content browser)**: Depends on US1 (needs synced_documents and run_sync)
- **US4 (folder management)**: Depends on Foundational only — independent of US1/US2/US3
- **US5 (notifications)**: Depends on US2 (email hooks into PR endpoints)

### Within Each User Story

- Backend models/migrations → utility layer → API endpoints → frontend hooks → frontend components
- T016 (sync.py) must complete before T017 (indexer) — indexer loads SyncedDocument
- T025 (process_document PR phase) must complete before T026 (approve endpoint) — approval queues the doc
- T035 (content endpoint) before T037 (frontend ContentTable)

### Parallel Opportunities

Within Phase 2: T007 and T008 (new models) can run in parallel — different files.
Within Phase 3: T021 and T022 (frontend hooks) can run in parallel — different files.
Within Phase 4 US2: T031 (PRList) can run in parallel with T025/T026 backend work — different files.
Within Phase 6 US4: T041 (hook) can run in parallel with T039/T040 (backend) — different files.

---

## Parallel Example: Phase 2 Foundational

```bash
# These can run in parallel (different files):
Task T007: Create SyncedDocument model in src/models/synced_document.py
Task T008: Create SyncRun model in src/models/sync_run.py

# Migrations must be sequential (Alembic depends chain):
T002 → T003 → T004 → T005 → T006
```

## Parallel Example: US1 Sync

```bash
# Frontend hooks in parallel:
Task T021: Create frontend/hooks/useSync.ts
Task T022: Create frontend/hooks/useSyncRuns.ts

# Then SyncCard (depends on both hooks):
Task T023: Create frontend/components/github/SyncCard.tsx
```

---

## Implementation Strategy

### MVP (US1 only — GitHub Sync)

1. Complete Phase 1 (Setup) — 1 task
2. Complete Phase 2 (Foundational) — 13 tasks
3. Complete Phase 3 (US1) — 9 tasks
4. **STOP and VALIDATE**: Trigger sync, verify files indexed, check GET /content
5. Deploy/demo — content browser is usable, RAG chat now has indexed content from repo

### Incremental Delivery

1. **MVP**: Setup + Foundational + US1 → admin can sync repo, content appears in browser
2. **+US2**: Upload pipeline → PR workflow → in-app merge → documents enter repo and get indexed
3. **+US3**: Full content browser with search and filter
4. **+US4**: Admin can add/remove folders in-app (quick win, ~5 tasks)
5. **+US5**: Email notifications close the feedback loop for non-admin users

### Recommended First Session Scope

Complete T001–T024 (all of Setup, Foundational, and US1). This delivers the core sync engine — the feature's most valuable capability — and unblocks RAG chat with real repo content.
