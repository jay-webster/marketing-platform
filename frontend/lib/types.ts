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

export interface ContentListResponse {
  data: ContentItem[];
  total: number;
  limit: number;
  offset: number;
}

// Ingestion
export type JobStatus = "queued" | "processing" | "complete" | "failed";

export interface IngestionJob {
  id: string;
  file_name: string;
  status: JobStatus;
  failure_reason: string | null;
  created_at: string;
  updated_at: string;
}

export interface IngestionListResponse {
  data: IngestionJob[];
  total: number;
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
  chunk_text: string;
  similarity: number;
}

export interface ChatSessionListResponse {
  data: ChatSession[];
  total: number;
  limit: number;
  offset: number;
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

export interface UserListResponse {
  data: User[];
  total: number;
}

// GitHub Connection
export type ConnectionStatus = "connected" | "disconnected" | "error";

export interface GitHubConnection {
  id: string;
  repo_url: string;
  default_branch: string;
  status: ConnectionStatus;
  last_synced_at: string | null;
  created_at: string;
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
