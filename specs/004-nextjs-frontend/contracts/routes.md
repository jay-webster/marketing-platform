# Route Contracts: Next.js Frontend

## App Router File Structure

```
frontend/
└── app/
    ├── (auth)/
    │   └── login/
    │       └── page.tsx                    # Public: login form
    ├── (dashboard)/
    │   ├── layout.tsx                      # Auth guard + sidebar nav
    │   ├── page.tsx                        # Dashboard / home
    │   ├── chat/
    │   │   ├── page.tsx                    # Session list + new chat CTA
    │   │   └── [sessionId]/
    │   │       └── page.tsx                # Chat interface (SSE streaming)
    │   ├── content/
    │   │   ├── page.tsx                    # Content browser (paginated, filtered)
    │   │   └── [id]/
    │   │       └── page.tsx                # Content detail view
    │   ├── ingestion/
    │   │   └── page.tsx                    # Upload + job status list
    │   ├── github/
    │   │   └── page.tsx                    # GitHub connection setup (admin)
    │   └── users/
    │       └── page.tsx                    # User management (admin only)
    └── api/
        ├── auth/
        │   ├── login/route.ts              # POST: set httpOnly cookie
        │   └── logout/route.ts             # POST: clear cookie
        └── me/route.ts                     # GET: current user from cookie
```

---

## Page Route Contracts

### `/login`
- **Access**: Public (unauthenticated)
- **Redirects**: Authenticated users → `/`
- **Actions**: Submit credentials → `POST /api/auth/login`
- **On success**: Redirect to `/`
- **On failure**: Inline error message

### `/` (Dashboard)
- **Access**: Any authenticated role
- **Data**: Summary counts (content items, pending jobs, recent sessions)
- **Navigation**: Sidebar shows role-appropriate links

### `/chat`
- **Access**: Any authenticated role
- **Data**: `GET /api/v1/chat/sessions` (paginated)
- **Actions**: Create new session → navigate to `/chat/[sessionId]`

### `/chat/[sessionId]`
- **Access**: Any authenticated role; own sessions only
- **Data**: `GET /api/v1/chat/sessions/{id}/messages`
- **Actions**: Send message → `POST /api/v1/chat/sessions/{id}/messages` (SSE stream)
- **Streaming**: `fetch` + `ReadableStream` consuming `text/event-stream`

### `/content`
- **Access**: Any authenticated role
- **Data**: `GET /api/v1/ingestion/documents` with status filter + pagination
- **Filters**: Status dropdown (all / processed / pending / failed)
- **Actions**: Click row → `/content/[id]`

### `/content/[id]`
- **Access**: Any authenticated role
- **Data**: `GET /api/v1/ingestion/documents/{id}`
- **Display**: Structured body + metadata table; read-only

### `/ingestion`
- **Access**: Any authenticated role
- **Data**: `GET /api/v1/ingestion/batches` (polled every 3s while active jobs exist)
- **Actions**: File upload → `POST /api/v1/ingestion/upload` (multipart/form-data)
- **Real-time**: TanStack Query `refetchInterval: 3000` while any job is non-terminal

### `/github`
- **Access**: Admin only (redirect non-admin to `/`)
- **Data**: `GET /api/v1/github/connection`
- **Actions**: Connect → `POST /api/v1/github/connect`; Disconnect → `DELETE /api/v1/github/connection`

### `/users`
- **Access**: Admin only (redirect non-admin to `/`)
- **Data**: `GET /api/v1/users` + `GET /api/v1/users/invitations`
- **Actions**: Invite → `POST /api/v1/users/invite`; Change role → `PATCH /api/v1/users/{id}/role`

---

## Internal API Route Contracts

### `POST /api/auth/login`
- **Request**: `{ email: string, password: string }`
- **Behaviour**: Calls `POST https://api.activelab.com/api/v1/auth/login`; on success sets `auth-token` httpOnly cookie; returns `{ ok: true }`
- **On failure**: Returns `{ error: string }` with appropriate HTTP status

### `POST /api/auth/logout`
- **Request**: (empty)
- **Behaviour**: Clears `auth-token` cookie; returns redirect to `/login`

### `GET /api/me`
- **Request**: (reads cookie automatically)
- **Response**: `AuthUser` object or `401`
- **Used by**: Client components that need current user role for conditional rendering

---

## Middleware Contract

**File**: `frontend/middleware.ts`

```
Protected path prefix: /(dashboard)/*  → all routes under (dashboard) group
Public paths: /login, /api/auth/*, /_next/*, /favicon.ico

Logic:
  IF path is protected AND no valid auth-token cookie THEN
    redirect to /login?next={original_path}
  ELSE IF path is /login AND valid cookie EXISTS THEN
    redirect to /
  ELSE
    pass through
```

Role checks (admin-only pages) are enforced in the page's server component via DAL, not middleware.

---

## CORS Requirement for Backend

The FastAPI backend must allow the Vercel deployment domain:

```
Access-Control-Allow-Origin: https://app.activelab.com  (Vercel frontend domain)
Access-Control-Allow-Credentials: true
```

This is required for the auth cookie to be sent on cross-origin requests from client components that call the backend directly (e.g., chat streaming).
