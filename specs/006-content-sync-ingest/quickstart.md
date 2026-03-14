# Quickstart: Content Sync & Ingestion Pipeline

**Feature**: 006-content-sync-ingest
**Date**: 2026-03-14

Integration scenarios for the five user stories.

---

## US1: GitHub Repository Sync

**Prerequisite**: Active GitHub connection, at least one configured folder containing `.md` files.

### Happy path — manual sync

```
1. Admin: POST /api/v1/github/sync
   → 201 { run_id, outcome: "in_progress" }

2. Poll: GET /api/v1/github/sync/status
   → 200 { outcome: "in_progress", files_indexed: 0, ... }

3. (After worker completes) Poll again:
   → 200 { outcome: "success", files_indexed: 12, files_removed: 0, files_unchanged: 0 }

4. GET /api/v1/content
   → 200 { data: [{ id, title, repo_path, index_status: "indexed", ... }] }
```

### Concurrent sync prevention

```
1. Admin: POST /api/v1/github/sync  → 201 in_progress
2. Admin (immediately): POST /api/v1/github/sync
   → 409 { code: "SYNC_ALREADY_RUNNING", run_id: "..." }
```

### Change detection on re-sync

```
1. First sync: 10 files indexed (all new)
2. One file updated in repo
3. POST /api/v1/github/sync
   → outcome: success, files_indexed: 1, files_unchanged: 9, files_removed: 0
```

### File deleted between syncs

```
1. First sync: 10 files indexed
2. One file deleted from repo
3. POST /api/v1/github/sync
   → outcome: success, files_indexed: 0, files_removed: 1, files_unchanged: 9
4. GET /api/v1/content
   → 9 items (deleted file no longer appears)
```

---

## US2: File Upload & PR Ingestion Workflow

**Prerequisite**: Active GitHub connection, at least one configured folder.

### Non-admin upload → admin approval → PR creation → merge

```
1. User (marketer): POST /api/v1/ingestion/batches
   { folder_name: "Uploads", files: [report.pdf], purpose: "Q4 analysis" }
   → 201 { processing_status: "pending_approval" }

2. Admin: GET /api/v1/ingestion/pending
   → [{ id, original_filename: "report.pdf", submitted_by_name: "Jane Smith" }]

3. Admin: POST /api/v1/ingestion/documents/{doc_id}/approve
   { destination_folder: "content/reports" }
   → 200 { processing_status: "queued", destination_folder: "content/reports" }

4. (Worker runs: extract → structure → commit → PR)
   doc.processing_status transitions: queued → processing → pr_open

5. Admin: GET /api/v1/ingestion/prs
   → [{ id, github_pr_number: 42, destination_folder: "content/reports" }]

6. Admin: GET /api/v1/ingestion/documents/{doc_id}/pr
   → { markdown_content: "---\ntitle: ...", configured_folders: [...] }

7. Admin (merges to different folder): POST /api/v1/ingestion/documents/{doc_id}/pr/merge
   { destination_folder: "content/guides" }
   → 200 { processing_status: "merged", merged_to_folder: "content/guides", sync_triggered: true }

8. (Sync runs automatically after merge — new .md file indexed)
   GET /api/v1/content → includes new document
```

### Admin upload → immediate processing

```
1. Admin: POST /api/v1/ingestion/batches
   { folder_name: "Direct", files: [whitepaper.docx], purpose: "Tech whitepaper" }
   → 201 { processing_status: "queued" }  (bypasses pending_approval)

2. (Worker picks up immediately)
   doc transitions: queued → processing → pr_open
```

### PR rejection

```
1. (PR is open for doc_id)
2. Admin: POST /api/v1/ingestion/documents/{doc_id}/pr/close
   → 200 { processing_status: "rejected" }
   (Submitter receives email: "Your submission was not accepted")
```

### Text extraction failure

```
1. Approved document queued for processing
2. Worker encounters corrupted PDF
   → doc.processing_status = "failed", failure_reason = "File appears to be corrupted..."
3. GET /api/v1/ingestion/documents/{doc_id} → shows failed status
```

---

## US3: Content Browser

### Admin views full queue

```
GET /api/v1/ingestion/pending       → all pending_approval docs across all users
GET /api/v1/ingestion/prs           → all pr_open docs
GET /api/v1/content                 → all indexed docs
```

### Non-admin views only their submissions

```
GET /api/v1/ingestion/batches       → only their own batches
GET /api/v1/content                 → all indexed docs (public to all authenticated users)
```

### Content search

```
GET /api/v1/content?search=campaign&folder=content/blog&limit=10
→ { data: [...], total: 4 }
```

### Empty state

```
GET /api/v1/content  (no sync run yet)
→ { data: [], total: 0 }
```

---

## US4: Folder Management

### Add a new folder

```
1. Admin: POST /api/v1/github/config/folders
   { folder: "content/guides" }
   → 201 { folder: "content/guides", folders: [..., "content/guides"], scaffold: { outcome: "success" } }

2. GitHub repo now contains content/guides/.gitkeep
3. GET /api/v1/github/config → folders includes "content/guides"
```

### Duplicate folder rejection

```
POST /api/v1/github/config/folders
{ folder: "content/blog" }   (already exists)
→ 409 { code: "FOLDER_ALREADY_EXISTS", message: "..." }
```

### Remove a folder

```
DELETE /api/v1/github/config/folders/content%2Fguides
→ 200 { removed: "content/guides", folders: ["content/blog"] }
(Folder remains in GitHub repo — only removed from configured list)
```

---

## US5: Email Notifications

### Merge notification

```
1. Admin merges PR for doc submitted by jane@example.com
2. send_pr_merged_notification(to="jane@example.com", document_title="Q4 Report")
   Subject: "Your submission was approved"
   Body: "Your document 'Q4 Report' has been approved and added to the knowledge base."
```

### Rejection notification

```
1. Admin closes PR for doc submitted by john@example.com
2. send_pr_rejected_notification(to="john@example.com", document_title="Draft Brief")
   Subject: "Your submission was not accepted"
   Body: "Your document 'Draft Brief' was not accepted."
```

### SMTP failure (best-effort)

```
1. SMTP server unreachable
2. send_pr_merged_notification() raises exception
3. Exception is caught, logged at WARNING level
4. Merge operation returns 200 OK regardless
```
