# Feature Specification: Content Sync & Ingestion Pipeline

**Feature Branch**: `006-content-sync-ingest`
**Created**: 2026-03-14
**Status**: Draft

## User Scenarios & Testing *(mandatory)*

### User Story 1 - GitHub Repository Sync (Priority: P1)

An admin triggers a sync of the connected GitHub repository. The system walks all configured folders for Markdown files, extracts their content, and indexes them into the knowledge base for use in RAG-powered chat. Sync can be triggered on demand via a "Sync Now" button or runs automatically on a schedule. The content browser reflects the indexed content.

**Why this priority**: This is the foundational ingestion path. All other features depend on content being indexed. Without sync, the content browser is empty and RAG chat has no material to retrieve from.

**Independent Test**: Can be fully tested by connecting a repo containing `.md` files in a configured folder, pressing "Sync Now," and verifying the files appear in the content browser and are retrievable in chat.

**Acceptance Scenarios**:

1. **Given** a connected repo with configured folders containing `.md` files, **When** an admin presses "Sync Now," **Then** all `.md` files in those folders are indexed and appear in the content browser within 30 seconds.
2. **Given** a scheduled sync interval is configured, **When** the interval elapses, **Then** the sync runs automatically without any manual action.
3. **Given** a sync is already in progress, **When** an admin presses "Sync Now" again, **Then** the duplicate request is rejected with a clear status message.
4. **Given** the connected repo is unreachable during a sync, **When** the sync runs, **Then** the error is logged, the sync is marked as failed, and no partial updates corrupt the index.
5. **Given** a `.md` file is deleted from the repo between syncs, **When** the next sync runs, **Then** the corresponding entry is removed from the content browser.

---

### User Story 2 - File Upload & PR Ingestion Workflow (Priority: P2)

A user (admin or non-admin) uploads a document (PDF, DOCX, PPTX, CSV, or TXT/MD) with a purpose description and optional notes. The system converts the document to structured Markdown, commits it to a branch in the connected repo, and opens a pull request. An admin reviews the generated Markdown in-app, assigns a destination folder from the configured list, and merges or rejects the PR — all without leaving the application. On merge, the next sync picks up the new file and indexes it. The original uploaded file is deleted from temporary storage after the PR is opened.

**Why this priority**: This enables non-technical marketing team members to contribute content to the knowledge base without needing to know Git or Markdown. It is the primary way new documents enter the system.

**Independent Test**: Can be fully tested by uploading a PDF, watching the PR be created, reviewing the generated Markdown in-app, merging the PR, and verifying the document appears in the content browser after the next sync.

**Acceptance Scenarios**:

1. **Given** a non-admin user uploads a PDF with a purpose note, **When** the upload completes, **Then** the document enters a pending approval queue and the user sees a confirmation with a pending status.
2. **Given** a document is in the pending queue, **When** an admin approves it and selects a destination folder, **Then** a worker extracts the text, generates structured Markdown with frontmatter (purpose, source filename, submitter name, date), commits to a branch named `ingest/<filename>-<timestamp>`, and opens a PR in the connected repo.
3. **Given** a PR has been created, **When** an admin opens the PR review view in-app, **Then** they can read the generated Markdown content and see a folder selector populated with configured repo folders.
4. **Given** an admin selects a destination folder and merges the PR in-app, **Then** the branch is merged into the default branch, the PR is closed, the original uploaded file is deleted from temporary storage, and the document status updates to "merged."
5. **Given** an admin rejects a PR in-app, **Then** the PR is closed without merging, the original file is deleted from temporary storage, and the document status updates to "rejected."
6. **Given** an admin uploads a document directly (no approval step), **When** the upload completes, **Then** processing begins immediately without entering the pending queue.
7. **Given** the text extraction fails for an uploaded document, **When** the worker encounters the error, **Then** the document status is set to "failed" with a descriptive reason, and the PR is not created.

---

### User Story 3 - Content Browser (Priority: P3)

Users browse the Markdown files that have been indexed from the connected repository. Admins see all content and the full ingestion queue (pending approvals, open PRs, processing status). Non-admin users see only the content they submitted and the general content browser. Content can be searched and filtered.

**Why this priority**: The content browser provides visibility into what is in the knowledge base. It is needed to verify that sync and ingestion are working correctly, and is used by all roles.

**Independent Test**: Can be fully tested after indexing at least one document — verifying files appear, are filterable, and that role-based visibility rules are enforced.

**Acceptance Scenarios**:

1. **Given** files have been indexed via sync, **When** a user opens the content browser, **Then** all indexed `.md` files from configured folders are listed with title, source path, and last indexed date.
2. **Given** a non-admin user opens the content browser, **When** they view the ingestion queue, **Then** they see only submissions they personally uploaded — not other users' submissions.
3. **Given** an admin opens the ingestion queue, **When** they view the queue, **Then** they see all pending approvals, all open PRs, and all processing jobs across all users.
4. **Given** more than 50 items exist in the content browser, **When** a user scrolls or paginates, **Then** content loads in pages without crashing the page.
5. **Given** no content has been indexed yet, **When** a user opens the content browser, **Then** an empty state with guidance to connect a repo and run sync is displayed.

---

### User Story 4 - Folder Management (Priority: P4)

An admin manages the list of configured repository folders directly from the GitHub settings page in the application. They can add new folders (which immediately creates them as empty directories in the connected repo via scaffolding), view existing folders, and remove folders from the configured list. Removing a folder from the configuration does not delete the folder from the repo.

**Why this priority**: Folder configuration is a prerequisite for sync and ingestion routing, but it is a one-time setup that can be done at any point. It extends the already-built GitHub settings page.

**Independent Test**: Can be fully tested by adding a new folder name in-app and verifying the folder appears in the connected GitHub repo.

**Acceptance Scenarios**:

1. **Given** an admin enters a new folder name on the GitHub settings page, **When** they click "Add Folder," **Then** the folder is added to the configured list and created as an empty directory (with a `.gitkeep`) in the connected repo.
2. **Given** a folder is in the configured list, **When** an admin removes it, **Then** the folder is removed from the configured list but remains in the repo unchanged.
3. **Given** an admin tries to add a folder with a path traversal sequence (`..`) or leading/trailing slash, **When** they submit, **Then** the input is rejected with a validation error.
4. **Given** a folder name already exists in the configured list, **When** an admin tries to add it again, **Then** the duplicate is rejected with a message that the folder already exists.
5. **Given** the configured folder list is displayed, **When** an admin views the page, **Then** each folder shows its name and a remove button.

---

### User Story 5 - Submission Notifications (Priority: P5)

When an admin merges or closes a PR created from a user's uploaded document, the submitting user receives an email notification. The email states whether their submission was approved (merged) or rejected, and includes the document title and relevant context.

**Why this priority**: Notifications close the feedback loop for non-admin users who cannot see the admin queue. They are a courtesy feature that does not block any other story.

**Independent Test**: Can be fully tested by submitting a document as a non-admin, approving or rejecting the PR as an admin, and verifying the submitter receives the appropriate email.

**Acceptance Scenarios**:

1. **Given** an admin merges a PR for a submitted document, **When** the merge completes, **Then** an email is sent to the original submitter with subject "Your submission was approved" and the document title.
2. **Given** an admin closes (rejects) a PR for a submitted document, **When** the rejection completes, **Then** an email is sent to the original submitter with subject "Your submission was not accepted" and the document title.
3. **Given** the SMTP service is unreachable at notification time, **When** the notification fails, **Then** the failure is logged but the merge/rejection operation completes successfully — email delivery is best-effort.

---

### Edge Cases

- What happens when a `.md` file in the repo has no readable content (empty file)?
- How does the system handle a repo folder containing thousands of `.md` files?
- What happens if the GitHub token expires mid-sync?
- What happens if the branch `ingest/<filename>-<timestamp>` already exists when a worker tries to create it?
- How does the system handle an uploaded file that is password-protected or corrupted?
- What happens when a PR is merged or closed directly on GitHub (outside the app)?
- What happens if the same `.md` file is modified between two syncs — does re-indexing overwrite the old content?
- What happens when folder management changes the configured list while a sync is in progress?

## Requirements *(mandatory)*

### Functional Requirements

**GitHub Sync**

- **FR-001**: The system MUST provide an on-demand "Sync Now" trigger that an admin can invoke from the GitHub settings page.
- **FR-002**: The system MUST support a configurable automatic sync schedule (e.g., every N hours).
- **FR-003**: The sync process MUST walk all configured repository folders and index all `.md` files found.
- **FR-004**: The sync MUST use upsert semantics — re-syncing the same file is safe and idempotent.
- **FR-005**: The sync MUST remove index entries for `.md` files that have been deleted from the repo since the last sync.
- **FR-006**: The sync MUST record the start time, end time, outcome (success/partial/failed), and count of files indexed per run.
- **FR-007**: The system MUST prevent concurrent syncs for the same repository connection.
- **FR-008**: The content browser MUST reflect the state of the index after each sync completes.

**File Upload Ingestion**

- **FR-009**: The system MUST accept file uploads in PDF, DOCX, PPTX, CSV, and TXT/MD formats.
- **FR-010**: Users MUST provide a purpose/notes field when uploading a file.
- **FR-011**: Non-admin uploads MUST be held in a pending approval queue until an admin acts on them.
- **FR-012**: Admin uploads MUST bypass the approval queue and enter processing immediately.
- **FR-013**: When approving a document, an admin MUST select a destination folder from the list of configured repo folders.
- **FR-014**: The worker MUST extract text from the uploaded document and generate a structured Markdown file with frontmatter including: purpose/notes, source filename, submitter display name, and submission date.
- **FR-015**: The worker MUST commit the generated Markdown file to a new branch named `ingest/<sanitized-filename>-<unix-timestamp>` in the connected repo.
- **FR-016**: The worker MUST open a pull request on the connected repo targeting the default branch.
- **FR-017**: The admin MUST be able to read the full generated Markdown content of a PR in-app before acting on it.
- **FR-018**: The admin MUST be able to select the final destination folder from configured folders when reviewing a PR, overriding the folder chosen at approval.
- **FR-019**: The admin MUST be able to merge or close the PR without leaving the application.
- **FR-020**: On merge, the system MUST move the file to the selected destination folder path within the PR before merging.
- **FR-021**: The original uploaded file MUST be deleted from temporary storage after the PR is created (regardless of merge outcome).
- **FR-022**: On merge, the system MUST trigger an immediate re-sync so the new file is indexed without waiting for the scheduled sync.

**Content Browser**

- **FR-023**: The content browser MUST list all `.md` files currently indexed from configured repo folders.
- **FR-024**: Each content item MUST display: title (derived from frontmatter or filename), source folder path, and last indexed date.
- **FR-025**: The content browser MUST support text search across titles and file paths.
- **FR-026**: The admin ingestion queue view MUST show pending approvals, open PRs, and processing jobs for all users.
- **FR-027**: Non-admin users MUST only see their own submissions in the queue view.
- **FR-028**: The content browser MUST paginate results (50 items per page).

**Folder Management**

- **FR-029**: Admins MUST be able to add new folder names on the GitHub settings page; adding a folder MUST trigger scaffolding to create the folder in the connected repo.
- **FR-030**: Admins MUST be able to remove a folder from the configured list; removal MUST NOT delete the folder from the repo.
- **FR-031**: Folder names MUST be validated: no path traversal sequences, no leading or trailing slashes, no duplicates in the configured list.
- **FR-032**: The configured folder list MUST be displayed on the GitHub settings page with each folder's name and a remove action.

**Notifications**

- **FR-033**: When a PR for a submitted document is merged in-app, the system MUST send an email to the original submitter notifying them of the approval.
- **FR-034**: When a PR for a submitted document is closed (rejected) in-app, the system MUST send an email to the original submitter notifying them of the rejection.
- **FR-035**: Email notification failures MUST be logged but MUST NOT cause the merge/reject operation to fail.

### Key Entities

- **SyncRun**: A record of a single GitHub sync execution — which connection triggered it, start/end timestamps, outcome, files indexed count, files removed count, and any error detail.
- **IngestionJob**: A submitted document awaiting or undergoing processing — file reference, submitter, purpose/notes, status (pending_approval, queued, processing, pr_open, merged, rejected, failed), destination folder, generated branch name, PR number, and failure reason.
- **ContentItem**: An indexed Markdown document — source repo path, title, raw content, embedding reference, and last indexed timestamp.
- **RepoStructureConfig**: The ordered list of configured folder paths — already exists, extended by folder management.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: An admin can trigger a sync of a repo with 100 `.md` files and see all files in the content browser within 60 seconds.
- **SC-002**: A non-admin user can upload a document, see it approved and processed, and see it available in the content browser — completing the full workflow within 5 minutes of admin action.
- **SC-003**: Sync runs are idempotent: running sync twice on an unchanged repo produces no changes to the index and does not create duplicate entries.
- **SC-004**: The content browser correctly enforces role-based visibility: non-admin users cannot see other users' submissions in the queue.
- **SC-005**: Email notifications are dispatched within 30 seconds of a PR being merged or closed in-app.
- **SC-006**: Folder scaffolding completes (folder created in repo) within 10 seconds of an admin adding a folder in-app.
- **SC-007**: The ingestion pipeline handles at least 10 concurrent document processing jobs without errors or data corruption.
- **SC-008**: Deleting an uploaded file from temporary storage after PR creation is confirmed — no orphaned files remain in GCS after 24 hours.

## Assumptions

- The GitHub connection and PAT management (Epic 2) are already implemented and stable.
- The folder scaffold mechanism (creating folders in GitHub via API) is already implemented in `utils/github_api.py`.
- Text extraction utilities for PDF, DOCX, PPTX, CSV, TXT/MD are already implemented in `utils/extractors.py`.
- The GCS bucket for transient file storage is already configured and available.
- The existing `utils/queue.py` worker pool can be extended for ingestion processing tasks.
- The SMTP configuration is already present via environment variables; `utils/email.py` provides the sending utility and only needs extension for the new notification templates.
- "Scheduled sync" means a periodic background task (e.g., cron-style) with the interval configurable via environment variable; the exact UI for setting the interval is out of scope for this feature.
- Removing a folder from configuration does not archive or delete indexed content from that folder — existing index entries persist until the next full sync, at which point orphaned entries are cleaned up.
- The PR merge operation uses the GitHub API squash-or-merge strategy; the exact merge strategy can be configured as an environment variable (default: merge commit).
- The "destination folder" for a PR review can differ from the folder selected at approval time; the in-app review step is the final authority on folder placement.
