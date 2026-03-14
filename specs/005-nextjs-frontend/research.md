# Research: Next.js Marketing Platform Frontend

## Router Strategy

**Decision**: Next.js 15 App Router
**Rationale**: Server Components keep JWT off the client entirely; `middleware.ts` enables global route guards with cookie access; native async/await in page components; required for Server Actions which simplify auth form handling.
**Alternatives considered**: Pages Router — legacy, no Server Components, manual auth plumbing, no middleware cookie access.

---

## Authentication Pattern

**Decision**: Next.js Route Handler as cookie bridge + middleware guard + DAL layer
**Rationale**: Two-layer pattern is the Next.js 15 recommended approach.
- Layer 1 — `middleware.ts`: reads httpOnly cookie on every request, redirects unauthenticated users before the page renders. Fast — no DB call.
- Layer 2 — DAL (`lib/dal.ts`): validates token signature and fetches user on data access. Protects Server Actions and Route Handlers that bypass middleware.

Flow: Login form → `app/api/auth/login/route.ts` → call FastAPI `/api/v1/auth/login` → receive JWT in body → set `auth-token` httpOnly, Secure, SameSite=Lax cookie → redirect to dashboard.

Logout: `app/api/auth/logout/route.ts` → clear cookie → redirect to login.

Client JS has zero access to the JWT at all times.
**Alternatives considered**: NextAuth.js (abstraction overhead, requires provider config for external JWT issuer); iron-session (valid but less native to App Router); localStorage bearer tokens (XSS risk).

---

## SSE Streaming (Chat)

**Decision**: `fetch` + `ReadableStream` (not `EventSource`)
**Rationale**: The chat endpoint requires a POST body (message text + session ID). `EventSource` only supports GET requests. `fetch` with `ReadableStream` handles POST SSE correctly and gives fine-grained control over cancellation.
**Alternatives considered**: `EventSource` — simpler API but GET-only; WebSockets — overkill, bidirectional overhead not needed.

---

## Ingestion Job Status

**Decision**: TanStack Query `refetchInterval` polling (3s while job is active)
**Rationale**: The ingestion SSE endpoint is fire-and-forget per document — jobs complete asynchronously. Polling at 3s intervals while `status === 'queued' | 'processing'` is simple, reliable, and requires no persistent connection. Stops polling automatically when status reaches terminal state.
**Alternatives considered**: SSE subscription per job — adds complexity; WebSocket — overkill for one-way status.

---

## Server State Management

**Decision**: TanStack Query v5
**Rationale**: `useMutation` + `queryClient.invalidateQueries` handles all CRUD flows cleanly. `refetchInterval` covers polling. Background refetch on window focus prevents stale lists. Devtools for debugging. Handles deduplication when multiple components request the same resource.
**Alternatives considered**: SWR — lighter but weaker mutation/invalidation ergonomics; manual `useEffect` + `useState` — error-prone.

---

## UI Components

**Decision**: shadcn/ui + Tailwind CSS
**Rationale**: Components live in the repo (copy-paste model) — no bundle lock-in, full customisation. Built on Radix primitives for accessibility. Tailwind utility classes are fast for internal tools with no external design system. Zero runtime overhead.
**Alternatives considered**: MUI — Material Design lock-in, ~95KB bundle; Chakra UI — similar overhead, less flexible internals.

---

## Form Handling

**Decision**: React Hook Form + Zod
**Rationale**: RHF integrates with shadcn/ui form components directly. Zod provides schema-based validation colocated with TypeScript types. Minimal re-renders.
**Alternatives considered**: Formik — heavier, older API; native HTML validation — insufficient for async server validation.

---

## Route Guard Architecture

**Decision**: `middleware.ts` (fast path) + `lib/dal.ts` (data path)
**Rationale**: Middleware redirects unauthenticated users before page renders — prevents content flash. DAL validates token on every data access — protects against middleware bypass via direct API calls. `React.cache()` memoises user fetch per request to avoid N+1.
**Role enforcement**: Admin-only pages call `requireRole('admin')` from DAL which throws; error boundary or `notFound()` handles gracefully.

---

## Deployment

**Decision**: Vercel (frontend) calling FastAPI at `api.activelab.com` directly
**Rationale**: No BFF proxy layer needed. Vercel environment variable `NEXT_PUBLIC_API_URL=https://api.activelab.com` configures all client fetches. Auth cookie bridge lives in Next.js Route Handlers. CORS on the FastAPI backend must allow the Vercel domain.
**Alternatives considered**: Separate BFF — unnecessary complexity for one frontend; same-origin proxy — adds latency for streaming.
