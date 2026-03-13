# Epic 3: Ingestion & Markdown Pipeline

**Branch**: `3-ingestion-pipeline`
**Status**: Draft
**Created**: 2026-03-12

---

## Overview

Marketing teams accumulate content in many forms — Word documents, PDFs, presentations, spreadsheets, and plain text files — scattered across local machines and shared drives. This content is valuable, but it is stranded: incompatible with version control, inconsistently formatted, and impossible to query or distribute programmatically.

This epic builds the pipeline that transforms that stranded content into structured, version-control-ready Markdown. A user selects a folder or set of files, the platform discovers and catalogs what is there, an intelligent processing pipeline extracts meaning and applies consistent formatting to each document, and the user receives a set of reviewable Markdown files they can inspect in external tools before approving them for the repository.

This epic turns existing content into platform-native content. It is the primary on-ramp for the organization's content library.

---

## Goals

1. Allow any authenticated user to point the platform at a local folder and receive a complete catalog of the documents found within it, with enough information to make an informed selection of what to ingest.
2. Submit selected documents to an asynchronous processing pipeline so that large batches can be ingested without requiring the user to wait — and so that a failure on one document does not block the others.
3. Apply intelligent extraction and formatting to each document: not just format conversion, but structural analysis — identifying titles, sections, metadata, and meaningful content — to produce well-formed, consistently structured Markdown files.
4. Give users a review gate before any processed content enters the repository: in-platform preview and an export that can be opened in external tools like Obsidian, so the output is fully inspectable before it is committed.
5. Make individual processing failures visible, actionable, and retryable without requiring a full re-ingestion of the batch.

---

## User Scenarios & Testing

### Scenario 1: User Selects a Source Folder and Reviews the File Catalog

**Actor**: Any authenticated user
**Precondition**: User is logged in.

1. User initiates a new ingestion session and selects a folder from their device.
2. The platform traverses the folder and any sub-folders, identifying all files it can process.
3. The platform presents a catalog: file name, file type, file size, and last-modified date for each discovered file.
4. Files whose type is not supported are listed separately with a clear indication that they will be skipped.
5. User reviews the catalog and selects the subset of files they want to ingest (or selects all).
6. User confirms and submits the selection for processing.

**Acceptance**:
- Every file in the folder tree appears in the catalog — none are silently omitted.
- Unsupported file types are surfaced, not hidden.
- The user can deselect individual files before submitting.
- Submitting an empty selection (no files checked) is blocked with a clear message.

---

### Scenario 2: Processing Runs Asynchronously and the User Monitors Progress

**Actor**: Any authenticated user
**Precondition**: User has submitted a selection of files for ingestion.

1. Immediately after submission, the platform confirms the batch has been queued and displays a processing status screen.
2. The status screen shows each document's current state: Queued, Processing, Completed, or Failed.
3. Documents are processed concurrently where possible; each updates its status independently.
4. The user can leave the page and return — the batch continues processing and the status is preserved.
5. When all documents have reached a terminal state (Completed or Failed), the user is notified.

**Acceptance**:
- Status reflects the real state of each document — not a summary estimate.
- Navigating away and returning shows the same accurate status.
- A batch with mixed outcomes (some Completed, some Failed) is not marked "Done" until all items have reached a terminal state.

---

### Scenario 3: A Document Is Processed Successfully

**Actor**: System (processing pipeline)
**Precondition**: A document is in the queue.

1. The pipeline receives the document.
2. It extracts the document's content, identifies its structure (title, sections, headings, body), and identifies any extractable metadata (author, date, source filename).
3. It produces a Markdown file with:
   - A structured metadata block at the top (title, source, date, author if available, ingest timestamp)
   - Content formatted in standard Markdown (headings, lists, bold/italic, tables where applicable)
   - Consistent heading hierarchy regardless of the source document's native formatting
4. The document's status is updated to Completed.
5. The generated Markdown is available for review.

**Acceptance**:
- Every Completed document has a corresponding Markdown file.
- The Markdown file is valid (renders correctly in a standard Markdown viewer).
- The metadata block is present and populated at minimum with: source filename, file type, and ingest timestamp.
- The content preserves the meaning and structure of the source — headings in the source become headings in the output; lists remain lists; tables remain tables.

---

### Scenario 4: A Document Fails Processing

**Actor**: System (processing pipeline)
**Precondition**: A document is in the queue.

1. The pipeline encounters a document it cannot process (corrupted file, empty file, processing timeout, or an unrecoverable error during extraction).
2. The document's status is updated to Failed.
3. The failure reason is recorded and shown to the user in plain language.
4. The rest of the batch continues unaffected.

**Acceptance**:
- A failed document does not affect any other document in the batch.
- The failure reason is specific enough for the user to act (e.g., "File appears to be empty", "File could not be read — it may be corrupted", "Processing timed out — the file may be too large").
- The failed document can be retried individually without re-submitting the whole batch.

---

### Scenario 5: User Retries a Failed Document

**Actor**: Any authenticated user
**Precondition**: At least one document in a batch has status Failed.

1. User selects one or more Failed documents and requests a retry.
2. The selected documents re-enter the processing queue.
3. Their status resets to Queued and then progresses normally.
4. If the retry succeeds, status becomes Completed and the output is available.
5. If the retry fails again, the failure reason is updated.

**Acceptance**:
- Retrying does not affect documents that have already Completed.
- There is no limit on the number of retries the user may attempt.
- A retry that succeeds replaces any previous (failed) output with the new result.

---

### Scenario 6: User Reviews a Processed Document In-Platform

**Actor**: Any authenticated user
**Precondition**: At least one document has status Completed.

1. User selects a Completed document to preview.
2. The platform renders the generated Markdown in a readable preview.
3. User can see both the rendered output and the raw Markdown source.
4. User marks the document as Approved or flags it for Re-processing with an optional note.

**Acceptance**:
- The preview renders standard Markdown correctly (headings, lists, bold, tables, code blocks).
- The raw Markdown view shows the exact text that would be exported.
- Marking a document Approved or flagging it for Re-processing does not alter the Markdown content — it only changes the document's review status.

---

### Scenario 7: User Exports Processed Documents for External Review

**Actor**: Any authenticated user
**Precondition**: At least one document has status Completed.

1. User selects one or more Completed documents (or selects all Completed documents in the batch).
2. User requests an export.
3. The platform produces a downloadable package containing the selected Markdown files.
4. User opens the package in Obsidian (or any Markdown-compatible tool) to review the output.
5. The Markdown files open and render correctly in Obsidian without modification.

**Acceptance**:
- Exported files are valid `.md` files.
- The metadata block in each file is formatted as YAML frontmatter (the standard Obsidian-compatible format).
- Folder structure in the export mirrors any sub-folder hierarchy from the original source selection.
- Only Completed documents can be exported. Failed documents are excluded from export with a notification.

---

### Scenario 8: User Re-Processes a Document with Guidance

**Actor**: Any authenticated user
**Precondition**: A document has status Completed but the user is unsatisfied with the output.

1. User flags the document for Re-processing and provides an optional note (e.g., "The section headings were not identified correctly — this is a financial report with a specific structure").
2. The document re-enters the processing queue. Its status resets to Queued.
3. The pipeline processes it again. The optional note is passed to the processing pipeline as additional context.
4. The new output replaces the previous output.

**Acceptance**:
- Re-processing is available for any Completed document, not just Failed ones.
- The previous output is not retained after re-processing — there is no version history of processed outputs in MVP.
- The re-processing note is visible in the document's processing history.

---

### Scenario 9: Batch Contains an Unsupported File Type

**Actor**: Any authenticated user
**Precondition**: User has selected a folder containing at least one unsupported file type.

1. During catalog discovery (Scenario 1), the unsupported files are listed separately.
2. If the user proceeds with a selection that includes unsupported files (e.g., by selecting all), those files are excluded automatically before the batch is submitted.
3. The user is shown a clear pre-submission summary: "X files will be processed; Y files were excluded (unsupported format)."
4. The batch is submitted with only the supported files.

**Acceptance**:
- Unsupported files are never submitted to the processing queue.
- The exclusion is transparent — the user always knows what was excluded and why.
- The user may not override the exclusion for an unsupported format in MVP.

---

## Functional Requirements

### FR-1: Source Selection & File Discovery

| ID | Requirement |
|----|-------------|
| FR-1.1 | Any authenticated user can initiate a new ingestion session by selecting a folder from their local device. |
| FR-1.2 | The platform traverses the selected folder recursively, cataloging all files in it and any sub-folders. |
| FR-1.3 | The catalog presents, for each discovered file: name, file type, file size, relative path within the source folder, and last-modified date. |
| FR-1.4 | Files of unsupported types are included in the catalog but clearly marked as ineligible for processing. They cannot be submitted for ingestion. |
| FR-1.5 | The user can select any combination of eligible files for ingestion, including selecting all. |
| FR-1.6 | Submitting an empty selection is blocked. The user must select at least one eligible file. |
| FR-1.7 | The supported input formats for MVP are: `.docx`, `.pdf`, `.txt`, `.md`, `.pptx`, `.csv`. |

---

### FR-2: Processing Queue

| ID | Requirement |
|----|-------------|
| FR-2.1 | Submitted documents enter a processing queue and are processed asynchronously — the user is not required to remain on the page for processing to continue. |
| FR-2.2 | Documents within a batch are processed concurrently where the system allows. Each document progresses independently. |
| FR-2.3 | Each document has a processing status visible to the user: Queued, Processing, Completed, or Failed. |
| FR-2.4 | A failure on one document must not affect the processing of any other document in the batch. |
| FR-2.5 | A batch is considered complete when all documents have reached a terminal status (Completed or Failed). |
| FR-2.6 | The user is notified when their batch reaches completion. |
| FR-2.7 | A document that has not reached a terminal status within 5 minutes is automatically marked Failed with the reason "Processing timed out." |

---

### FR-3: Intelligent Processing Pipeline

| ID | Requirement |
|----|-------------|
| FR-3.1 | Each document is passed through an intelligent processing pipeline that extracts content, identifies document structure, and generates a standardized Markdown file. |
| FR-3.2 | The pipeline must identify and preserve document structure: titles, section headings, body paragraphs, lists, tables, and emphasis (bold, italic). |
| FR-3.3 | The pipeline must produce a consistent heading hierarchy in the output regardless of inconsistent or absent heading structure in the source document. |
| FR-3.4 | The pipeline must extract and populate a metadata block for each output document containing at minimum: original filename, original file type, ingest timestamp, and the identity of the user who submitted the ingestion. |
| FR-3.5 | The pipeline must make a best-effort extraction of: document title, author (if present in the source), and creation or last-modified date (if present in the source). |
| FR-3.6 | Content that cannot be meaningfully extracted (e.g., image-only PDFs with no readable text) must result in a Failed status with the reason "No readable text content found." |
| FR-3.7 | Processing must not modify the original source file in any way. |
| FR-3.8 | Processing must not modify the original source files in any way. All outputs are written only to the platform's own data store. |

---

### FR-4: Output Review

| ID | Requirement |
|----|-------------|
| FR-4.1 | Users can preview any Completed document's generated Markdown in both rendered and raw-source views. |
| FR-4.2 | Users can mark any Completed document as Approved. |
| FR-4.3 | Users can flag any Completed document for Re-processing, with an optional free-text note providing additional context for the pipeline. |
| FR-4.4 | Re-processing replaces the previous output. No version history of processed outputs is retained in MVP. |
| FR-4.5 | Review status (Pending Review, Approved, Flagged for Re-processing) is visible in the batch status screen alongside processing status. |
| FR-4.6 | Review actions (Approve, Flag for Re-processing) are recorded in the audit log with the acting user's identity and timestamp. |

---

### FR-5: Export

| ID | Requirement |
|----|-------------|
| FR-5.1 | Users can export any selection of Completed documents as a downloadable package of `.md` files. |
| FR-5.2 | Exported Markdown files must include a YAML frontmatter block at the top of each file containing the metadata defined in FR-3.4 and FR-3.5. |
| FR-5.3 | The folder structure of the exported package must mirror the relative sub-folder structure of the original source selection. |
| FR-5.4 | Exported files must be valid, standards-compliant Markdown that renders correctly in Obsidian and other standard Markdown tools without modification. |
| FR-5.5 | Failed documents are excluded from export automatically. The export summary must inform the user how many documents were excluded and why. |
| FR-5.6 | The export does not push content to the GitHub repository. That action is handled by a subsequent content sync epic. |

---

### FR-6: Error Handling & Observability

| ID | Requirement |
|----|-------------|
| FR-6.1 | Every document failure must surface a human-readable reason to the user. Generic "processing error" messages are not acceptable. |
| FR-6.2 | The recognized failure reasons include at minimum: file is empty, file is corrupted or unreadable, no readable text content found, processing timed out, and unsupported file type. |
| FR-6.3 | Failed documents can be retried individually without re-submitting any other document in the batch. |
| FR-6.4 | There is no limit on the number of times a user may retry a failed document. |
| FR-6.5 | All ingestion events (batch submitted, document completed, document failed, document retried, document approved, export downloaded) are recorded in the audit log. |
| FR-6.6 | The processing pipeline must handle documents up to 50 MB in size. Documents exceeding this limit are rejected at submission time with a clear message, not failed during processing. |

---

## Success Criteria

| # | Criterion |
|---|-----------|
| SC-1 | A user can select a folder, review the catalog, and submit a batch for processing in under 2 minutes regardless of the number of files cataloged. |
| SC-2 | 95% of submitted documents across supported formats reach Completed status without manual intervention. |
| SC-3 | A single document's processing completes within 60 seconds under normal system load. |
| SC-4 | A batch of 20 documents completes end-to-end within 5 minutes under normal system load. |
| SC-5 | Every failed document surfaces a specific, human-readable failure reason — zero instances of a generic or empty error message. |
| SC-6 | 100% of exported Markdown files open and render correctly in Obsidian without modification. |
| SC-7 | Re-running ingestion on a document that has already been processed does not produce duplicate outputs or corrupt the existing output — it replaces it cleanly. |
| SC-8 | The user experience during a running batch (status visibility, navigation away and back) reflects accurate document states within 5 seconds of a state change. |

---

## Key Entities

### IngestionBatch
A user-submitted collection of documents for processing within a single ingestion session.

| Attribute | Description |
|-----------|-------------|
| id | Unique identifier |
| submitted_by | User who initiated the batch |
| submitted_at | Timestamp of batch submission |
| source_path | The root folder path the user selected |
| status | One of: In Progress, Completed, Completed with Failures |
| total_documents | Count of documents submitted |
| completed_count | Count of documents with status Completed |
| failed_count | Count of documents with status Failed |

---

### IngestionDocument
An individual file within an IngestionBatch, tracking its processing lifecycle.

| Attribute | Description |
|-----------|-------------|
| id | Unique identifier |
| batch_id | The IngestionBatch this document belongs to |
| original_filename | Source file name |
| original_file_type | Source file extension / MIME type |
| relative_path | Path relative to the batch's source root |
| file_size_bytes | File size at time of submission |
| processing_status | One of: Queued, Processing, Completed, Failed |
| failure_reason | Human-readable failure description (nullable) |
| retry_count | Number of times processing has been attempted |
| queued_at | Timestamp when the document entered the queue |
| processing_started_at | Timestamp when processing began (nullable) |
| processing_completed_at | Timestamp when processing finished (nullable) |
| reprocessing_note | Optional user-provided context for re-processing (nullable) |

---

### ProcessedDocument
The Markdown output produced by the processing pipeline for a successfully completed IngestionDocument.

| Attribute | Description |
|-----------|-------------|
| id | Unique identifier |
| ingestion_document_id | The IngestionDocument that produced this output |
| markdown_content | The full generated Markdown including YAML frontmatter |
| extracted_title | Title identified by the pipeline (nullable) |
| extracted_author | Author identified by the pipeline (nullable) |
| extracted_date | Date identified from source document (nullable) |
| review_status | One of: Pending Review, Approved, Flagged for Re-processing |
| reviewed_by | User who last set the review status (nullable) |
| reviewed_at | Timestamp of last review action (nullable) |
| created_at | Timestamp when this output was generated |

---

### Standard YAML Frontmatter Schema
Every exported Markdown file must open with a frontmatter block in this structure:

```
---
title: [extracted or derived from filename]
source_file: [original filename]
source_type: [original file extension]
author: [extracted if available, otherwise omitted]
source_date: [extracted if available, otherwise omitted]
ingested_at: [ISO 8601 timestamp]
ingested_by: [display name of submitting user]
review_status: [Pending Review | Approved]
---
```

---

## Dependencies & Assumptions

### Dependencies

- **Epic 1 (IAM)**: User authentication is required. All ingestion operations require an authenticated session.
- **Epic 2 (GitHub Bridge)**: Not required by this epic. Processed and approved documents are not pushed to the repository here — that is a future content sync epic. However, the folder structure produced by scaffolding in Epic 2 informs the folder layout of exports, providing a natural mapping when content sync is built.
- **AI Processing Service**: The intelligent processing pipeline depends on an external AI service. Availability, rate limits, and cost of that service are out of scope for this spec but must be addressed in the plan.

### Assumptions

| # | Assumption | Rationale |
|---|-----------|-----------|
| A-1 | All three roles (Admin, Marketing Manager, Marketer) can initiate ingestion. | Ingestion is a content operation, and all roles have content management rights per Epic 1's permission matrix. |
| A-2 | Supported input formats for MVP: `.docx`, `.pdf`, `.txt`, `.md`, `.pptx`, `.csv`. | Covers the most common marketing document types. Additional formats can be added post-MVP without architectural changes. |
| A-3 | Maximum file size is 50 MB per document. Files exceeding this are rejected at submission. | Balances handling of real-world documents against processing resource constraints. |
| A-4 | Processing timeout per document is 5 minutes. | Allows for large, complex documents while preventing indefinitely stuck queue items. |
| A-5 | No version history of processed outputs is maintained in MVP. Re-processing replaces the previous output entirely. | Simplifies storage and review workflows. Versioning can be added in a future epic. |
| A-6 | Exports are downloaded by the user and are not stored long-term by the platform. The platform retains the ProcessedDocument record and Markdown content; it does not manage downloaded export packages. | Avoids storage complexity for export artifacts. |
| A-7 | The export package format is a ZIP archive of `.md` files. | ZIP is universally supported and preserves folder hierarchy. |
| A-8 | Image content within documents (embedded images, charts) is not included in the Markdown output for MVP. The pipeline extracts text only. | Image extraction and hosting is a separate concern. The pipeline can note where images were present in the source. |
| A-9 | The pipeline makes a best-effort extraction — it does not guarantee perfect fidelity for all source formats. Complex layouts (multi-column PDFs, heavily formatted presentations) may produce imperfect output. The review gate (FR-4) exists specifically to catch these cases. | Sets honest expectations for AI-assisted extraction quality. |
| A-10 | Ingestion sessions (batches) are scoped to a single folder selection. A user wanting to ingest from multiple disconnected folders must start separate ingestion sessions. | Simplifies the UX for MVP. Multi-source batching is a future enhancement. |

---

## Out of Scope

- Pushing processed content to the GitHub repository (handled by a future content sync epic)
- Version history or diff tracking of processed document outputs
- Automatic ingestion triggered by folder watching or scheduled sync (this epic is user-initiated only)
- Extraction or handling of embedded images, charts, or diagrams within source documents
- Multi-column or complex layout preservation for PDFs (best-effort text extraction only)
- Source formats beyond the six defined in FR-1.7 for MVP
- Collaborative review (multiple users reviewing the same document simultaneously)
- In-platform editing of the generated Markdown before export
- Natural language re-processing prompts beyond the free-text note in FR-4.3
- Processing of password-protected or encrypted source documents
- Ingestion from cloud storage providers (Google Drive, Dropbox, SharePoint) — local file system only in MVP
- Any deduplication logic (the platform does not detect if the same document has been ingested previously)
