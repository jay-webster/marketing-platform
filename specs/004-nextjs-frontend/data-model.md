# Data Model: Next.js Frontend Types

The frontend has no database. This document defines the TypeScript interfaces that mirror the backend API responses and drive all client-side state.

---

## Auth

```typescript
interface AuthUser {
  id: string           // UUID
  email: string
  display_name: string
  role: 'admin' | 'marketer' | 'marketing_manager'
  status: 'active' | 'pending' | 'inactive'
}

interface SessionPayload {
  sub: string          // user UUID
  email: string
  role: string
  session_id: string
  exp: number
}
```

---

## Content

```typescript
interface ContentItem {
  id: string
  title: string
  content_type: string    // 'blog_post' | 'campaign' | 'asset' | etc.
  status: 'pending' | 'processing' | 'processed' | 'failed'
  source_path: string     // GitHub file path
  updated_at: string      // ISO 8601
  created_at: string
}

interface ContentDetail extends ContentItem {
  body: string            // Structured markdown content
  metadata: Record<string, unknown>  // Frontmatter key/value pairs
}

interface ContentListResponse {
  data: ContentItem[]
  total: number
  limit: number
  offset: number
}
```

---

## Ingestion

```typescript
// 'pending_approval' — non-admin upload awaiting admin approval before processing
// 'queued'           — approved/admin upload, waiting for worker
// 'processing'       — actively being processed by a worker
// 'completed'        — successfully processed (note: backend uses 'completed', not 'complete')
// 'failed'           — processing failed; failure_reason populated
// 'rejected'         — admin rejected the upload; GCS file deleted
type JobStatus = 'pending_approval' | 'queued' | 'processing' | 'completed' | 'failed' | 'rejected'

interface IngestionJob {
  id: string
  file_name: string
  status: JobStatus
  failure_reason: string | null
  created_at: string
  updated_at: string
}

// Extended shape returned by GET /api/v1/ingestion/pending (admin only)
interface PendingDocument extends IngestionJob {
  batch_id: string
  submitted_by_name: string   // display_name of the submitting user
  submitted_by_id: string
}

interface IngestionListResponse {
  data: IngestionJob[]
  total: number
}

interface PendingDocumentListResponse {
  data: PendingDocument[]
  total: number
}
```

---

## Chat

```typescript
type MessageRole = 'user' | 'assistant'

interface ChatSession {
  id: string
  title: string | null
  created_at: string
  last_active_at: string
}

interface ChatMessage {
  id: string
  session_id: string
  role: MessageRole
  content: string
  is_generated_content: boolean   // true = AI-generated marketing copy
  source_documents: SourceDoc[] | null
  created_at: string
}

interface SourceDoc {
  title: string
  chunk_text: string
  similarity: number
}

interface ChatSessionListResponse {
  data: ChatSession[]
  total: number
  limit: number
  offset: number
}

// SSE event shapes from the streaming endpoint
interface SSEChunkEvent {
  text: string
  is_generated_content: boolean
}

interface SSEDoneEvent {
  message_id: string
  session_id: string
  source_documents: SourceDoc[]
}
```

---

## Users & Invitations

```typescript
type UserRole = 'admin' | 'marketer' | 'marketing_manager'
type UserStatus = 'active' | 'pending' | 'inactive'
type InvitationStatus = 'pending' | 'accepted' | 'expired' | 'revoked'

interface User {
  id: string
  email: string
  display_name: string
  role: UserRole
  status: UserStatus
  created_at: string
}

interface Invitation {
  id: string
  invited_email: string
  assigned_role: UserRole
  status: InvitationStatus
  expires_at: string
  created_at: string
}

interface UserListResponse {
  data: User[]
  total: number
}
```

---

## GitHub Connection

```typescript
type ConnectionStatus = 'connected' | 'disconnected' | 'error'

interface GitHubConnection {
  id: string
  repo_url: string
  default_branch: string
  status: ConnectionStatus
  last_synced_at: string | null
  created_at: string
}
```

---

## Shared / API Envelope

```typescript
// Standard API error shape from FastAPI backend
interface APIError {
  detail: string
  request_id: string
}

// Pagination params used across list endpoints
interface PaginationParams {
  limit?: number    // default 20
  offset?: number   // default 0
}
```

---

## State Transitions

### Ingestion Job
```
[non-admin upload]
pending_approval ──► queued (admin approves) ──► processing ──► completed
                 ↘ rejected (admin rejects)                  ↘ failed

[admin upload — bypasses approval]
queued ──► processing ──► completed
                       ↘ failed
```

### Chat Session (client-side streaming state)
```
idle → sending → streaming → complete
                           ↘ error
```

### GitHub Connection
```
disconnected → connected ↔ error
```
