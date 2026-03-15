# Quickstart: Next.js Frontend

## Prerequisites

- Node.js 20+
- pnpm (recommended) or npm
- Backend running at `http://localhost:8000` (or `https://api.activelab.com` for prod)

---

## Local Development

```bash
# From repo root
cd frontend
pnpm install

# Copy environment template
cp .env.example .env.local

# Edit .env.local
# NEXT_PUBLIC_API_URL=http://localhost:8000

pnpm dev
# → http://localhost:3000
```

---

## Environment Variables

| Variable | Dev value | Prod value |
|---|---|---|
| `NEXT_PUBLIC_API_URL` | `http://localhost:8000` | `https://api.activelab.com` |
| `AUTH_SECRET` | any 32-char random string | strong random (for cookie signing) |

---

## First Login Flow

1. Navigate to `http://localhost:3000`
2. Middleware redirects to `/login`
3. Enter admin credentials (use `INITIAL_ADMIN_TOKEN` bootstrap flow from backend docs)
4. Dashboard loads with admin navigation

---

## Integration Scenarios

### Scenario 1: Authenticated chat with streaming

```
1. POST /api/auth/login  { email, password }
   → Sets auth-token cookie
2. GET /chat
   → Session list loads via TanStack Query
3. POST /api/v1/chat/sessions  { title: null }
   → New session created
4. Navigate to /chat/{sessionId}
5. User types message, submits
6. Client opens fetch() ReadableStream to:
   POST https://api.activelab.com/api/v1/chat/sessions/{id}/messages
   Authorization: Bearer {token from cookie bridge}
7. SSE chunks stream in → UI appends token-by-token
8. SSE 'done' event → source documents rendered below response
```

### Scenario 2: File ingestion with status polling

```
1. Navigate to /ingestion
2. Drag PDF onto upload zone
3. POST /api/v1/ingestion/upload (multipart/form-data)
   → Job appears in list with status: 'queued'
4. TanStack Query refetchInterval: 3000 begins
5. Status transitions: queued → processing → complete
6. refetchInterval stops when all jobs reach terminal state
```

### Scenario 3: Admin invites a new user

```
1. Navigate to /users (admin only; non-admin → redirect /)
2. Click "Invite User"
3. Modal: enter email, select role
4. POST /api/v1/users/invite  { email, role }
5. User appears in list with status: 'pending'
6. Invited user receives email with registration link
```

---

## Vercel Deployment

```bash
# Install Vercel CLI
pnpm add -g vercel

# From frontend/ directory
vercel

# Set environment variables in Vercel dashboard:
# NEXT_PUBLIC_API_URL = https://api.activelab.com
# AUTH_SECRET = <strong random string>
```

The frontend deploys as a standalone Vercel project. Connect the `frontend/` subdirectory as the Vercel project root.

---

## Key File Locations (after scaffolding)

| Purpose | Path |
|---|---|
| Auth middleware | `frontend/middleware.ts` |
| Login route handler | `frontend/app/api/auth/login/route.ts` |
| DAL (server auth validation) | `frontend/lib/dal.ts` |
| API fetch client | `frontend/lib/api.ts` |
| TypeScript types | `frontend/lib/types.ts` |
| TanStack Query provider | `frontend/app/providers.tsx` |
| Chat streaming hook | `frontend/hooks/useChat.ts` |
| shadcn components | `frontend/components/ui/` |
