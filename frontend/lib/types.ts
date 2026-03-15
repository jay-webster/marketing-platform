// Auth
export interface AuthUser {
  id: string;
  email: string;
  display_name: string;
  role: "admin" | "marketer" | "marketing_manager";
  status: "active" | "pending" | "inactive";
}

export interface SessionPayload {
  sub: string; // user UUID
  email: string;
  role: string;
  session_id: string;
  exp: number;
}

// Content
export interface ContentItem {
  id: string;
  title: string;
  content_type: string;
  status: "pending" | "processing" | "processed" | "failed";
  source_path: string;
  updated_at: string;
  created_at: string;
}

export interface ContentDetail extends ContentItem {
  body: string;
  metadata: Record<string, unknown>;
}


// Ingestion
export type JobStatus =
  | "pending_approval"  // non-admin upload awaiting admin review
  | "queued"            // approved / admin upload, waiting for worker
  | "processing"
  | "completed"         // note: backend uses "completed", not "complete"
  | "failed"
  | "rejected"          // admin rejected; GCS file deleted
  | "pr_open"           // worker created branch + PR in GitHub
  | "merged";           // admin merged PR in-app

export interface IngestionJob {
  id: string;
  original_filename: string;
  processing_status: JobStatus;
  failure_reason: string | null;
  queued_at: string;
  batch_id?: string;
}

// Extended shape returned by GET /api/v1/ingestion/pending (admin only)
export interface PendingDocument extends IngestionJob {
  batch_id: string;
  submitted_by_name: string;
  submitted_by_id: string;
}

// Batch-level summary returned by GET /api/v1/ingestion/batches
export type BatchStatus = "in_progress" | "completed" | "completed_with_failures"

export interface BatchSummary {
  batch_id: string
  source_folder_name: string
  status: BatchStatus
  total_documents: number
  completed_count: number
  failed_count: number
  submitted_at: string
}

// Chat
export type MessageRole = "user" | "assistant";

export interface ChatSession {
  id: string;
  title: string | null;
  created_at: string;
  last_active_at: string;
}

export interface ChatMessage {
  id: string;
  session_id: string;
  role: MessageRole;
  content: string;
  is_generated_content: boolean;
  source_documents: SourceDoc[] | null;
  created_at: string;
}

export interface SourceDoc {
  title: string;
  source_file: string;
  similarity: number;
}


export interface SSEChunkEvent {
  text: string;
  is_generated_content: boolean;
}

export interface SSEDoneEvent {
  message_id: string;
  session_id: string;
  source_documents: SourceDoc[];
}

// Users & Invitations
export type UserRole = "admin" | "marketer" | "marketing_manager";
export type UserStatus = "active" | "pending" | "inactive";
export type InvitationStatus = "pending" | "accepted" | "expired" | "revoked";

export interface User {
  id: string;
  email: string;
  display_name: string;
  role: UserRole;
  status: UserStatus;
  created_at: string;
}

export interface Invitation {
  id: string;
  invited_email: string;
  assigned_role: UserRole;
  status: InvitationStatus;
  expires_at: string;
  created_at: string;
}


// GitHub Sync
export type SyncOutcome = "in_progress" | "success" | "partial" | "failed" | "interrupted";
export type SyncTriggerType = "manual" | "scheduled";

export interface SyncRun {
  id: string;
  trigger_type: SyncTriggerType;
  triggered_by: string | null;
  started_at: string;
  finished_at: string | null;
  outcome: SyncOutcome;
  files_indexed: number;
  files_removed: number;
  files_unchanged: number;
  error_detail: string | null;
}

export interface SyncStatus {
  connection_id: string;
  last_synced_at: string | null;
  active_document_count: number;
  latest_run: SyncRun | null;
}

// Synced content item from GET /content
export type KBIndexStatus = "queued" | "indexing" | "indexed" | "failed" | "removed";

export interface SyncedContent {
  id: string;
  title: string | null;
  repo_path: string;
  folder: string;
  index_status: KBIndexStatus;
  last_synced_at: string;
  chunk_count: number | null;
}

export interface SyncedContentDetail extends SyncedContent {
  raw_content: string;
}

// PR ingestion item from GET /ingestion/prs
export interface PRItem {
  id: string;
  original_filename: string;
  destination_folder: string;
  github_branch: string;
  github_pr_number: number;
  github_pr_url: string;
  submitted_by_name: string;
  submitted_by_email: string;
  queued_at: string;
}

export interface PRReviewData {
  id: string;
  original_filename: string;
  destination_folder: string;
  github_branch: string;
  github_pr_number: number;
  github_pr_url: string;
  markdown_content: string;
  current_folder: string;
  configured_folders: string[];
}

// GitHub Connection
export type ConnectionStatus = "active" | "inactive";

export interface GitHubConnection {
  connection_id: string;
  repository_url: string;
  status: ConnectionStatus;
  connected_at: string;
  last_validated_at: string;
  last_scaffolded_at: string | null;
  last_synced_at: string | null;
  token_on_file: boolean;
}

// Shared / API Envelope
export interface APIError {
  detail: string;
  request_id: string;
}

export interface PaginationParams {
  limit?: number;
  offset?: number;
}
