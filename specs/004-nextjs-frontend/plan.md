# Implementation Plan: Next.js Marketing Platform Frontend

**Branch**: `005-nextjs-frontend`
**Spec**: [spec.md](./spec.md)
**Research**: [research.md](./research.md)

---

## Tech Stack

| Layer | Technology | Version |
|---|---|---|
| Framework | Next.js (App Router) | 15.x |
| Language | TypeScript | 5.x |
| Styling | Tailwind CSS | 3.x |
| UI Components | shadcn/ui (Radix primitives) | latest |
| Forms | React Hook Form + Zod | latest |
| Server state | TanStack Query v5 | 5.x |
| HTTP client | Native `fetch` (wrapped in `lib/api.ts`) | — |
| Auth | httpOnly cookies via Next.js Route Handlers | — |
| Deployment | Vercel | — |

---

## Architecture Overview

```
┌─────────────────────────────────────────┐
│  Vercel (Next.js 15 App Router)         │
│                                         │
│  middleware.ts ←── auth-token           │
│       │            (httpOnly cookie)    │
│       ▼                                 │
│  (dashboard)/ layout.tsx                │
│       │                                 │
│  Server Components ──► lib/dal.ts       │
│  Client Components ──► lib/api.ts       │
│       │                    │            │
│  app/api/auth/*            │            │
│  (cookie bridge)           │            │
└───────────────────┬────────┘            │
                    │                     │
                    ▼                     │
         api.activelab.com (FastAPI)      │
         /api/v1/*                        │
```

**Auth flow**:
1. Login form submits to `POST /api/auth/login` (Next.js Route Handler)
2. Route Handler calls FastAPI, receives JWT, sets httpOnly cookie
3. `middleware.ts` reads cookie on every request — redirect or pass through
4. `lib/dal.ts` validates token server-side on each data access
5. Client components call FastAPI directly with cookie (credentialed cross-origin)

---

## File Structure

```
frontend/
├── app/
│   ├── (auth)/
│   │   └── login/
│   │       └── page.tsx
│   ├── (dashboard)/
│   │   ├── layout.tsx               # Sidebar + auth context
│   │   ├── page.tsx                 # Dashboard
│   │   ├── chat/
│   │   │   ├── page.tsx             # Session list
│   │   │   └── [sessionId]/
│   │   │       └── page.tsx         # Chat interface
│   │   ├── content/
│   │   │   ├── page.tsx             # Content browser
│   │   │   └── [id]/
│   │   │       └── page.tsx         # Content detail
│   │   ├── ingestion/
│   │   │   └── page.tsx             # Upload + job list
│   │   ├── github/
│   │   │   └── page.tsx             # GitHub connection (admin)
│   │   └── users/
│   │       └── page.tsx             # User management (admin)
│   ├── api/
│   │   ├── auth/
│   │   │   ├── login/route.ts       # POST: set httpOnly cookie
│   │   │   └── logout/route.ts      # POST: clear cookie
│   │   └── me/route.ts              # GET: current user
│   ├── layout.tsx                   # Root layout + providers
│   └── providers.tsx                # TanStack Query provider
├── components/
│   ├── ui/                          # shadcn/ui components
│   ├── layout/
│   │   ├── Sidebar.tsx
│   │   ├── TopBar.tsx
│   │   └── EmptyState.tsx
│   ├── chat/
│   │   ├── ChatWindow.tsx
│   │   ├── MessageBubble.tsx
│   │   ├── SourceDocs.tsx
│   │   └── SessionList.tsx
│   ├── content/
│   │   ├── ContentTable.tsx
│   │   ├── ContentFilters.tsx
│   │   └── ContentDetail.tsx
│   ├── ingestion/
│   │   ├── UploadZone.tsx
│   │   └── JobTable.tsx
│   ├── users/
│   │   ├── UserTable.tsx
│   │   └── InviteDialog.tsx
│   └── github/
│       └── ConnectionCard.tsx
├── hooks/
│   ├── useChat.ts                   # fetch ReadableStream SSE
│   ├── useIngestionPoll.ts          # refetchInterval polling
│   └── useCurrentUser.ts            # client-side auth user
├── lib/
│   ├── api.ts                       # fetch wrapper (base URL + credentials)
│   ├── dal.ts                       # server-only: verifySession, getUser, requireRole
│   ├── session.ts                   # server-only JWT decode from cookie
│   ├── types.ts                     # all TypeScript interfaces
│   └── utils.ts                     # cn() + misc helpers
├── middleware.ts
├── next.config.ts
├── tailwind.config.ts
├── components.json                  # shadcn/ui config
├── package.json
├── tsconfig.json
├── .env.example
└── vercel.json
```

---

## Constitution Compliance

| Principle | Applicability | Status |
|---|---|---|
| AUTH_SAFE | Every page under `(dashboard)/` guarded by middleware + DAL | COMPLIANT |
| DRY | Single `lib/api.ts` fetch client used everywhere | COMPLIANT |
| NON_BLOCKING | Vercel is stateless; no local file state | COMPLIANT |
| Stateless Services | No localStorage tokens; cookies managed server-side | COMPLIANT |
| Error Handling | All API errors surfaced as user-readable messages via `lib/api.ts` | COMPLIANT |
| Admin Security | `/users` and `/github` gated by `requireRole('admin')` in DAL | COMPLIANT |

---

## Implementation Phases

### Phase 1 — Project Scaffold

**Goal**: Working Next.js app with auth, routing shell, and Vercel deploy

1. Create `frontend/` directory and scaffold with `pnpm create next-app`
2. Install: `@tanstack/react-query`, `react-hook-form`, `zod`, `@hookform/resolvers`
3. Init shadcn/ui; add Button, Card, Input, Form, Dialog, Table, Badge, Skeleton, Separator, Toast
4. Create `lib/types.ts` — all interfaces from data-model.md
5. Create `lib/api.ts` — fetch wrapper with base URL + `credentials: 'include'`
6. Create `lib/session.ts` — server-only JWT decode from cookie (`server-only` import)
7. Create `lib/dal.ts` — `verifySession()`, `getUser()`, `requireRole()`
8. Create `middleware.ts` — protect `/(dashboard)/*`, redirect to `/login`
9. Create `app/api/auth/login/route.ts` — call FastAPI, set httpOnly cookie
10. Create `app/api/auth/logout/route.ts` — clear cookie, redirect to `/login`
11. Create `app/api/me/route.ts` — return current user from cookie
12. Create `app/(auth)/login/page.tsx` — login form with RHF + Zod validation
13. Create `app/(dashboard)/layout.tsx` — sidebar shell with stub nav links
14. Create `app/providers.tsx` — TanStack Query `QueryClientProvider`
15. Create `app/layout.tsx` — root layout wrapping providers
16. Create `vercel.json` — `{ "framework": "nextjs" }`
17. Create `.env.example` — `NEXT_PUBLIC_API_URL`, `AUTH_SECRET`

**Milestone**: `/login` works; authenticated users reach dashboard shell; Vercel preview deploy succeeds.

---

### Phase 2 — Dashboard + Navigation

**Goal**: Role-aware sidebar and summary dashboard cards

1. Create `components/layout/Sidebar.tsx` — nav links filtered by user role
2. Create `components/layout/TopBar.tsx` — user display name + logout
3. Create `components/layout/EmptyState.tsx` — reusable empty state
4. Create `app/(dashboard)/page.tsx` — summary cards via TanStack Query
5. Add dashboard aggregate queries (content count, pending jobs, recent sessions)

**Milestone**: Admin sees full nav (Content, Chat, Ingestion, GitHub, Users); marketer sees subset; dashboard cards render.

---

### Phase 3 — RAG Chat Interface

**Goal**: SSE streaming chat with session management

1. Create `hooks/useChat.ts` — `fetch` ReadableStream; parse SSE frames; accumulate streamed text; handle `chunk` and `done` events
2. Create `components/chat/MessageBubble.tsx` — user/assistant styling; `is_generated_content` badge
3. Create `components/chat/SourceDocs.tsx` — collapsible source citations
4. Create `components/chat/ChatWindow.tsx` — message list, input form, streaming indicator, disabled send during stream
5. Create `components/chat/SessionList.tsx` — TanStack Query session list with new-chat button
6. Create `app/(dashboard)/chat/page.tsx`
7. Create `app/(dashboard)/chat/[sessionId]/page.tsx`

**Milestone**: User sends a message; response streams token-by-token; generated content is badged; session switching works.

---

### Phase 4 — Content Browser

**Goal**: Paginated, filterable content list with detail view

1. Create `components/content/ContentFilters.tsx` — status filter
2. Create `components/content/ContentTable.tsx` — paginated TanStack Query table
3. Create `app/(dashboard)/content/page.tsx`
4. Create `components/content/ContentDetail.tsx` — body + metadata display
5. Create `app/(dashboard)/content/[id]/page.tsx`

**Milestone**: Content list renders with status filtering; detail view shows full document.

---

### Phase 5 — Document Ingestion

**Goal**: File upload with live job status polling

1. Create `hooks/useIngestionPoll.ts` — `refetchInterval: 3000` while any job is `queued | processing`; disabled at terminal state
2. Create `components/ingestion/UploadZone.tsx` — drag-and-drop; client-side file type check; `POST /api/v1/ingestion/upload`
3. Create `components/ingestion/JobTable.tsx` — status badges; failure reason; auto-updates from poll
4. Create `app/(dashboard)/ingestion/page.tsx`

**Milestone**: Upload a PDF; see queued → processing → complete without page refresh.

---

### Phase 6 — GitHub Connection

**Goal**: Admin connects/disconnects GitHub repo

1. Create `components/github/ConnectionCard.tsx` — status, connect form, disconnect confirm
2. Create `app/(dashboard)/github/page.tsx` — `requireRole('admin')` in server component

**Milestone**: Admin connects a repo; non-admin is redirected; status shows correctly.

---

### Phase 7 — User Management

**Goal**: Admin views users and invites new members

1. Create `components/users/UserTable.tsx` — active users + pending invitations (tabbed)
2. Create `components/users/InviteDialog.tsx` — email + role form; `POST /api/v1/users/invite`
3. Create `app/(dashboard)/users/page.tsx` — `requireRole('admin')` in server component

**Milestone**: Admin sees user list; sends invitation; invitation appears as pending.

---

### Phase 9 — Ingestion Approval Queue

**Goal**: Non-admin uploads enter a pending state; admins approve or reject before processing begins

**Backend**:
1. Modify `src/api/ingestion.py` — gate initial `processing_status` on `current_user.role` (`"queued"` for admin, `"pending_approval"` for everyone else)
2. Add `GET /api/v1/ingestion/pending` — admin-only; returns `pending_approval` documents joined with submitter `display_name`
3. Add `POST /api/v1/ingestion/documents/{doc_id}/approve` — admin-only; transitions to `"queued"`, writes audit
4. Add `POST /api/v1/ingestion/documents/{doc_id}/reject` — admin-only; deletes GCS file, transitions to `"rejected"`, writes audit

**Frontend**:
1. Update `lib/types.ts` — add `pending_approval` and `rejected` to `JobStatus`; fix `"complete"` → `"completed"` enum mismatch
2. Update `hooks/useIngestionPoll.ts` — include `pending_approval` in `hasActiveJobs` check
3. Update `components/ingestion/UploadZone.tsx` — accept `userRole` prop; show "Submit for Review" label and review-pending toast for non-admin
4. Create `components/ingestion/PendingApprovalTable.tsx` — admin-only; `GET /api/v1/ingestion/pending`; Approve/Reject action buttons per row
5. Update `components/ingestion/JobTable.tsx` — add amber badge for `pending_approval`, muted badge for `rejected`
6. Update `app/(dashboard)/ingestion/page.tsx` — pass user role to components; render `<PendingApprovalTable>` for admin

**Milestone**: Non-admin uploads file → sees "Submitted for review" → admin sees item in Pending Approvals → approves → document enters processing queue.

---

### Phase 8 — Polish

**Goal**: Error states, loading skeletons, CORS, production deploy

1. Add `error.tsx` to each route segment — user-friendly error boundaries
2. Add `loading.tsx` with Skeleton components to each route segment
3. Add `not-found.tsx` root 404 page
4. Update FastAPI `src/main.py` CORS `allow_origins` to include Vercel domain
5. Set Vercel production environment variables
6. End-to-end smoke test: login → chat → ingestion → logout

**Milestone**: All screens have loading + error states; production deploy live at Vercel URL.

---

## API Dependency Map

| Screen | FastAPI endpoints |
|---|---|
| Login | `POST /api/v1/auth/login` |
| Dashboard | `GET /api/v1/ingestion/documents`, `GET /api/v1/ingestion/batches`, `GET /api/v1/chat/sessions` |
| Chat | `GET /api/v1/chat/sessions`, `POST /api/v1/chat/sessions`, `GET /api/v1/chat/sessions/{id}/messages`, `POST /api/v1/chat/sessions/{id}/messages` (SSE) |
| Content | `GET /api/v1/ingestion/documents`, `GET /api/v1/ingestion/documents/{id}` |
| Ingestion (all users) | `POST /api/v1/ingestion/upload`, `GET /api/v1/ingestion/batches` |
| Ingestion (admin only) | `GET /api/v1/ingestion/pending`, `POST /api/v1/ingestion/documents/{id}/approve`, `POST /api/v1/ingestion/documents/{id}/reject` |
| GitHub | `GET /api/v1/github/connection`, `POST /api/v1/github/connect`, `DELETE /api/v1/github/connection` |
| Users | `GET /api/v1/users`, `POST /api/v1/users/invite`, `GET /api/v1/users/invitations` |

### New Ingestion Approval Endpoints (to be added to FastAPI)

| Method | Path | Auth | Description |
|---|---|---|---|
| `GET` | `/api/v1/ingestion/pending` | admin | List all documents with `processing_status = "pending_approval"` joined with submitter `display_name` |
| `POST` | `/api/v1/ingestion/documents/{doc_id}/approve` | admin | Set `processing_status = "queued"`, reset `queued_at`; write audit log |
| `POST` | `/api/v1/ingestion/documents/{doc_id}/reject` | admin | Delete GCS file, set `processing_status = "rejected"`; write audit log |

### Approval Queue Role Logic (upload endpoint change)

The existing `POST /api/v1/ingestion/upload` must be modified to gate the initial document status on role:

```python
# src/api/ingestion.py — batch submission
initial_status = "queued" if current_user.role == "admin" else "pending_approval"
# Each IngestionDocument created with processing_status = initial_status
```

The queue worker (`utils/queue.py`) is unchanged — it already only claims documents where `processing_status = "queued"`, so `pending_approval` documents are automatically skipped.

---

## Pre-Implementation Requirement

Before the frontend can make credentialed cross-origin requests, FastAPI CORS must be updated to allow the Vercel domain. This is a one-line change to `src/main.py` once the Vercel preview URL is known.
