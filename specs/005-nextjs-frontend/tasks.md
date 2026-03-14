# Tasks: Next.js Marketing Platform Frontend

**Input**: Design documents from `/specs/005-nextjs-frontend/`
**Branch**: `005-nextjs-frontend`
**Prerequisites**: plan.md ✓, spec.md ✓, research.md ✓, data-model.md ✓, contracts/routes.md ✓, quickstart.md ✓

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies on incomplete tasks)
- **[Story]**: User story this task belongs to (US1–US7)
- Exact file paths are relative to `frontend/`

---

## Phase 1: Setup (Project Scaffold)

**Purpose**: Initialize the Next.js project, install all dependencies, configure tooling.

- [ ] T001 Scaffold Next.js 15 App Router project: `pnpm create next-app frontend --typescript --tailwind --app --src-dir=false --import-alias "@/*"`
- [ ] T002 Install runtime dependencies: `@tanstack/react-query @tanstack/react-query-devtools react-hook-form zod @hookform/resolvers server-only`
- [ ] T003 Initialize shadcn/ui: `npx shadcn-ui@latest init` (style: default, base color: slate, CSS variables: yes)
- [ ] T004 [P] Add shadcn/ui components: Button, Card, Input, Label, Form, Dialog, Table, Badge, Skeleton, Separator, Sonner (toast)
- [ ] T005 [P] Create `vercel.json` with `{ "framework": "nextjs" }` at `vercel.json`
- [ ] T006 [P] Create `.env.example` with `NEXT_PUBLIC_API_URL=http://localhost:8000` and `AUTH_SECRET=` at `.env.example`
- [ ] T007 [P] Configure `next.config.ts` — set `output: 'standalone'` for Vercel; add `NEXT_PUBLIC_API_URL` to env at `next.config.ts`
- [ ] T008 [P] Create `lib/utils.ts` — export `cn()` helper using `clsx` + `tailwind-merge` at `lib/utils.ts`

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Auth infrastructure, API client, and routing shell that ALL user stories depend on. Must be complete before any story phase.

- [ ] T009 Create `lib/types.ts` — export all TypeScript interfaces from data-model.md: `AuthUser`, `SessionPayload`, `ContentItem`, `ContentDetail`, `ContentListResponse`, `IngestionJob`, `JobStatus`, `ChatSession`, `ChatMessage`, `SourceDoc`, `SSEChunkEvent`, `SSEDoneEvent`, `User`, `Invitation`, `GitHubConnection`, `APIError`, `PaginationParams` at `lib/types.ts`
- [ ] T010 Create `lib/session.ts` — server-only module (`import 'server-only'`): decode and verify `auth-token` httpOnly cookie using `jose` JWT library; export `getSessionFromCookie(): Promise<SessionPayload | null>` at `lib/session.ts`
- [ ] T011 Create `lib/dal.ts` — server-only data access layer: `verifySession()` throws if no valid cookie; `getUser()` calls `GET /api/v1/users/me` with token; `requireRole(role)` throws if role mismatch; all wrapped in `React.cache()` at `lib/dal.ts`
- [ ] T012 Create `app/api/auth/login/route.ts` — POST handler: receive `{ email, password }`, call `POST ${API_URL}/api/v1/auth/login`, on success set `auth-token` httpOnly Secure SameSite=Lax cookie with JWT, return `{ ok: true }` or error at `app/api/auth/login/route.ts`
- [ ] T013 Create `app/api/auth/logout/route.ts` — POST handler: delete `auth-token` cookie, return redirect to `/login` at `app/api/auth/logout/route.ts`
- [ ] T014 Create `app/api/me/route.ts` — GET handler: read cookie via `getSessionFromCookie()`, call `GET /api/v1/users/me`, return `AuthUser` or 401 at `app/api/me/route.ts`
- [ ] T015 Create `middleware.ts` — protect all `/(dashboard)/*` paths: read `auth-token` cookie, redirect unauthenticated to `/login?next={path}`; redirect authenticated users away from `/login`; matcher excludes `_next/static`, `_next/image`, `favicon.ico`, `api/auth/*` at `middleware.ts`
- [ ] T016 Create `lib/api.ts` — fetch wrapper: `apiFetch(path, options)` prepends `NEXT_PUBLIC_API_URL`, sets `credentials: 'include'`, forwards auth cookie from server-side requests, throws typed `APIError` on non-2xx; export typed helpers `apiGet`, `apiPost`, `apiPatch`, `apiDelete` at `lib/api.ts`
- [ ] T017 Create `app/providers.tsx` — client component: wrap children in `QueryClientProvider` with default `staleTime: 30_000`; include `ReactQueryDevtools` in dev at `app/providers.tsx`
- [ ] T018 Create `app/layout.tsx` — root layout: import `providers.tsx`, set `<html lang="en">`, include `Toaster` from sonner at `app/layout.tsx`
- [ ] T019 Create `components/layout/EmptyState.tsx` — reusable component: accepts `title`, `description`, optional `action` (button label + onClick); centered card layout at `components/layout/EmptyState.tsx`
- [ ] T020 Create `hooks/useCurrentUser.ts` — client hook: `useQuery({ queryKey: ['me'], queryFn: () => apiGet('/api/me') })`; returns `AuthUser | undefined` and loading state at `hooks/useCurrentUser.ts`

---

## Phase 3: US1 — Login & Session Management

**Story goal**: User can authenticate, reach dashboard, and be redirected on session expiry.
**Independent test**: Visit `/login`, submit valid credentials, land on dashboard shell; submit invalid credentials, see error; navigate to `/content` while logged out, get redirected to `/login`.

- [ ] T021 [US1] Create `app/(auth)/login/page.tsx` — login page: `useForm` with Zod schema `{ email: z.string().email(), password: z.string().min(1) }`; submit calls `POST /api/auth/login`; on success `router.push('/')` or `next` param; on error display inline message; redirect authenticated users to `/` at `app/(auth)/login/page.tsx`
- [ ] T022 [US1] Create `app/(auth)/layout.tsx` — unauthenticated layout: centered card, platform name/logo at `app/(auth)/layout.tsx`
- [ ] T023 [US1] Add 401 interception to `lib/api.ts` — if any API call returns 401, clear cookie state and redirect to `/login`; update `apiFetch` to handle this globally at `lib/api.ts`

---

## Phase 4: US2 — Dashboard & Navigation

**Story goal**: Authenticated user lands on dashboard with role-appropriate nav and summary cards.
**Independent test**: Log in as admin → see all nav links + summary cards. Log in as marketer → no Users or GitHub links.

- [ ] T024 [US2] Create `components/layout/Sidebar.tsx` — client component: nav links array filtered by `user.role`; admin sees Content, Chat, Ingestion, GitHub, Users; marketer sees Content, Chat, Ingestion; active link highlighted; logo/brand at top; logout button calls `POST /api/auth/logout` at `components/layout/Sidebar.tsx`
- [ ] T025 [US2] Create `components/layout/TopBar.tsx` — displays `user.display_name` and role badge; mobile menu toggle at `components/layout/TopBar.tsx`
- [ ] T026 [US2] Create `app/(dashboard)/layout.tsx` — server component: call `getUser()` from DAL (redirects if unauthenticated); pass user to client layout shell with `<Sidebar>` and `<TopBar>`; serialize user to client via props at `app/(dashboard)/layout.tsx`
- [ ] T027 [US2] [P] Create `app/(dashboard)/page.tsx` — dashboard: three summary cards using TanStack Query: content item count (`GET /api/v1/ingestion/documents?limit=1`), pending ingestion jobs count, recent chat sessions count; each card links to its section at `app/(dashboard)/page.tsx`
- [ ] T028 [US2] [P] Add `loading.tsx` to `app/(dashboard)/` — Skeleton cards matching dashboard layout at `app/(dashboard)/loading.tsx`
- [ ] T029 [US2] [P] Add `error.tsx` to `app/(dashboard)/` — user-friendly error with retry button at `app/(dashboard)/error.tsx`

---

## Phase 5: US3 — RAG Chat Interface

**Story goal**: User sends a message and sees streamed SSE response; can switch sessions; generated content is visually distinguished.
**Independent test**: Open `/chat`, create new session, type a message, see tokens stream in; open session list, click prior session, see history.

- [ ] T030 [US3] Create `hooks/useChat.ts` — manages full chat SSE flow: `sendMessage(sessionId, text)` opens `fetch(POST .../messages)` with `ReadableStream`; parses SSE frames (`event: chunk` → append text, `event: done` → set source docs, `event: error` → set error); tracks `isStreaming`, `streamingText`, `sourceDocs` state; returns `{ messages, sendMessage, isStreaming, error }` at `hooks/useChat.ts`
- [ ] T031 [US3] Create `components/chat/MessageBubble.tsx` — renders single message: user messages right-aligned slate bg; assistant messages left-aligned white bg; `is_generated_content: true` shows amber "AI-generated" badge; markdown-safe text rendering at `components/chat/MessageBubble.tsx`
- [ ] T032 [US3] Create `components/chat/SourceDocs.tsx` — collapsible accordion: shows list of `SourceDoc` with title and similarity score; hidden by default; "N sources" toggle label at `components/chat/SourceDocs.tsx`
- [ ] T033 [US3] Create `components/chat/ChatWindow.tsx` — main chat UI: scrollable message list rendering `<MessageBubble>` per message; streaming text appended live; typing indicator (3-dot animation) while `isStreaming`; textarea input (Enter submits, Shift+Enter newline); send button disabled while streaming; `<SourceDocs>` shown after assistant turn completes at `components/chat/ChatWindow.tsx`
- [ ] T034 [US3] Create `components/chat/SessionList.tsx` — sidebar panel: TanStack Query `GET /api/v1/chat/sessions`; lists sessions with title (or "New conversation") and `last_active_at` date; "New Chat" button calls `POST /api/v1/chat/sessions` then navigates to new session; active session highlighted at `components/chat/SessionList.tsx`
- [ ] T035 [US3] Create `app/(dashboard)/chat/page.tsx` — redirects to most recent session or shows empty state with "Start your first conversation" CTA at `app/(dashboard)/chat/page.tsx`
- [ ] T036 [US3] Create `app/(dashboard)/chat/[sessionId]/page.tsx` — server component loads initial messages (`GET /api/v1/chat/sessions/{id}/messages`); renders `<ChatWindow>` with `<SessionList>` in sidebar at `app/(dashboard)/chat/[sessionId]/page.tsx`
- [ ] T037 [US3] [P] Add `loading.tsx` to `app/(dashboard)/chat/[sessionId]/` — skeleton chat bubbles at `app/(dashboard)/chat/[sessionId]/loading.tsx`
- [ ] T038 [US3] [P] Add `error.tsx` to `app/(dashboard)/chat/[sessionId]/` — "Could not load conversation" with back link at `app/(dashboard)/chat/[sessionId]/error.tsx`

---

## Phase 6: US4 — Content Browser

**Story goal**: User browses paginated, filterable content list and opens detail view.
**Independent test**: Navigate to `/content`, see list with status filter; change filter to "processed", list updates; click a row, see detail view with body and metadata.

- [ ] T039 [US4] Create `components/content/ContentFilters.tsx` — status filter select (All / Processed / Pending / Failed); updates URL search param `?status=` on change at `components/content/ContentFilters.tsx`
- [ ] T040 [US4] Create `components/content/ContentTable.tsx` — TanStack Query `GET /api/v1/ingestion/documents` with `status` and `offset`/`limit` params from URL; renders Table with columns: Title, Type, Status (Badge), Last Updated; clickable rows navigate to `/content/{id}`; pagination controls (prev/next) update URL params at `components/content/ContentTable.tsx`
- [ ] T041 [US4] Create `app/(dashboard)/content/page.tsx` — reads `status` and `offset` from `searchParams`; renders `<ContentFilters>` + `<ContentTable>`; empty state when no results at `app/(dashboard)/content/page.tsx`
- [ ] T042 [US4] Create `components/content/ContentDetail.tsx` — displays `ContentDetail`: title heading, status badge, metadata key/value table from `metadata` JSONB, prose body (rendered as preformatted markdown) at `components/content/ContentDetail.tsx`
- [ ] T043 [US4] Create `app/(dashboard)/content/[id]/page.tsx` — server component fetches `GET /api/v1/ingestion/documents/{id}`; renders `<ContentDetail>`; back link to `/content` at `app/(dashboard)/content/[id]/page.tsx`
- [ ] T044 [US4] [P] Add `loading.tsx` files to content routes — skeleton table rows and skeleton detail at `app/(dashboard)/content/loading.tsx`, `app/(dashboard)/content/[id]/loading.tsx`

---

## Phase 7: US5 — Document Ingestion

**Story goal**: User uploads a file, sees it queued, watches status update without refresh.
**Independent test**: Upload a PDF; job appears with status "queued"; without refreshing, status changes to "processing" then "complete".

- [ ] T045 [US5] Create `hooks/useIngestionPoll.ts` — TanStack Query `GET /api/v1/ingestion/batches`; `refetchInterval: (data) => hasActiveJobs(data) ? 3000 : false`; `hasActiveJobs` returns true if any job has status `queued` or `processing`; export `{ jobs, isLoading }` at `hooks/useIngestionPoll.ts`
- [ ] T046 [US5] Create `components/ingestion/UploadZone.tsx` — drag-and-drop area using HTML5 drag events + `<input type="file">`; accepts `.pdf,.docx,.pptx,.csv,.txt,.md`; client-side type validation before upload; on valid file calls `POST /api/v1/ingestion/upload` as `multipart/form-data`; shows upload progress; on success invalidates `ingestion-batches` TanStack query; inline error for unsupported types or oversized files at `components/ingestion/UploadZone.tsx`
- [ ] T047 [US5] Create `components/ingestion/JobTable.tsx` — renders job list from `useIngestionPoll`; columns: File Name, Status (colored Badge: queued=slate, processing=blue, complete=green, failed=red), Created At; failed rows show failure reason in tooltip/popover at `components/ingestion/JobTable.tsx`
- [ ] T048 [US5] Create `app/(dashboard)/ingestion/page.tsx` — renders `<UploadZone>` above `<JobTable>`; empty state when no jobs at `app/(dashboard)/ingestion/page.tsx`
- [ ] T049 [US5] [P] Add `loading.tsx` to ingestion route — skeleton job table at `app/(dashboard)/ingestion/loading.tsx`

---

## Phase 8: US6 — GitHub Connection

**Story goal**: Admin connects/disconnects GitHub repo; non-admins are blocked.
**Independent test**: Log in as admin, navigate to `/github`, connect a repo with valid token, see "connected" status; log in as marketer, navigate to `/github`, be redirected.

- [ ] T050 [US6] Create `components/github/ConnectionCard.tsx` — if no connection: form with repo URL + PAT inputs (PAT masked), Zod validation, submit calls `POST /api/v1/github/connect`, invalidates query on success; if connected: shows repo URL, status badge, last synced date, "Disconnect" button with confirmation Dialog calling `DELETE /api/v1/github/connection` at `components/github/ConnectionCard.tsx`
- [ ] T051 [US6] Create `app/(dashboard)/github/page.tsx` — server component: calls `requireRole('admin')` (redirects non-admin to `/`); fetches `GET /api/v1/github/connection`; renders `<ConnectionCard>` with initial data at `app/(dashboard)/github/page.tsx`

---

## Phase 9: US7 — User Management

**Story goal**: Admin views all users and pending invitations; can invite new users by email + role.
**Independent test**: Log in as admin, navigate to `/users`, see user list with roles and statuses; click Invite, fill email + role, submit; new invitation appears as pending. Log in as marketer, navigate to `/users`, be redirected.

- [ ] T052 [US7] Create `components/users/InviteDialog.tsx` — Dialog with form: email (Zod email), role select (marketer / marketing_manager); submit calls `POST /api/v1/users/invite`; on success closes dialog, shows toast, invalidates users query at `components/users/InviteDialog.tsx`
- [ ] T053 [US7] Create `components/users/UserTable.tsx` — two tabs: "Active Users" and "Pending Invitations"; Active tab: Table with Display Name, Email, Role (Badge), Status, Created At; Invitations tab: Table with Email, Assigned Role, Expires At, Status; TanStack Query for both; "Invite User" button opens `<InviteDialog>` at `components/users/UserTable.tsx`
- [ ] T054 [US7] Create `app/(dashboard)/users/page.tsx` — server component: calls `requireRole('admin')` (redirects non-admin to `/`); renders `<UserTable>` at `app/(dashboard)/users/page.tsx`

---

## Phase 10: Polish & Cross-Cutting

**Purpose**: Error boundaries, loading states, CORS, 404, production deploy.

- [ ] T055 Add `not-found.tsx` at app root — friendly 404 page with link back to dashboard at `app/not-found.tsx`
- [ ] T056 [P] Add `error.tsx` to all remaining route segments missing one — ingestion, content/[id], github, users at `app/(dashboard)/ingestion/error.tsx`, `app/(dashboard)/content/[id]/error.tsx`, `app/(dashboard)/github/error.tsx`, `app/(dashboard)/users/error.tsx`
- [ ] T057 Update FastAPI `src/main.py` CORS `allow_origins` — add Vercel preview domain and production domain (`https://app.activelab.com`) to `CORSMiddleware` origins list; set `allow_credentials=True` at `../src/main.py`
- [ ] T058 Set Vercel environment variables — `NEXT_PUBLIC_API_URL=https://api.activelab.com` and `AUTH_SECRET=<strong-random>` in Vercel project dashboard
- [ ] T059 Connect Vercel project — link `frontend/` subdirectory as Vercel project root; enable preview deploys on PR; production deploy on merge to `main`
- [ ] T060 [P] End-to-end smoke test — login → dashboard → chat (send message, verify stream) → ingestion (upload file, verify poll) → logout; document any issues

---

## Dependencies

```
Phase 1 (Setup) → Phase 2 (Foundational) → All user story phases
Phase 2 (T009–T020) → Phase 3 (US1) → Phase 4 (US2)
Phase 4 (US2) → Phases 5–9 (US3–US7) [can run in parallel once US2 layout is done]
All phases → Phase 10 (Polish)
```

**Story dependency order**:
```
US1 (Login) ──► US2 (Dashboard) ──► US3 (Chat)     ┐
                                 ├─► US4 (Content)  ├─► Polish
                                 ├─► US5 (Ingestion)│
                                 ├─► US6 (GitHub)   │
                                 └─► US7 (Users)    ┘
```

US3–US7 can be developed in parallel once US2 layout shell is complete, since they are separate route segments with no shared component dependencies.

---

## Parallel Execution Examples

**Within Phase 2** (after T009 types are done):
- T010 (session.ts) and T016 (api.ts) can run in parallel
- T012 (login route) and T013 (logout route) and T014 (me route) can run in parallel
- T019 (EmptyState) and T020 (useCurrentUser) can run in parallel

**Within Phase 5 (US2)**:
- T027 (dashboard page) and T028 (loading.tsx) and T029 (error.tsx) can run in parallel once T026 (layout) is done

**Stories US3–US7** — once Phase 4 (US2 layout) is complete:
- All of Phase 5 (US3), Phase 6 (US4), Phase 7 (US5), Phase 8 (US6), Phase 9 (US7) can run in parallel across engineers or sessions

---

## Implementation Strategy

**MVP scope** (login + dashboard + chat): Complete Phases 1–5 (T001–T038). This delivers the core value: authenticated access and streaming AI chat.

**Increment 2**: Phase 6 (Content browser) — read-only content visibility.

**Increment 3**: Phase 7 (Ingestion) — self-service document upload.

**Increment 4**: Phases 8–9 (GitHub + Users) — admin configuration screens.

**Full release**: Phase 10 (Polish) — error states, CORS, Vercel production.

---

## Task Summary

| Phase | Story | Tasks | Parallel opportunities |
|---|---|---|---|
| Phase 1: Setup | — | T001–T008 | T004–T008 |
| Phase 2: Foundational | — | T009–T020 | T010, T012–T014, T019–T020 |
| Phase 3 | US1 Login | T021–T023 | — |
| Phase 4 | US2 Dashboard | T024–T029 | T027–T029 |
| Phase 5 | US3 Chat | T030–T038 | T037–T038 |
| Phase 6 | US4 Content | T039–T044 | T044 |
| Phase 7 | US5 Ingestion | T045–T049 | T049 |
| Phase 8 | US6 GitHub | T050–T051 | — |
| Phase 9 | US7 Users | T052–T054 | — |
| Phase 10 | Polish | T055–T060 | T056, T060 |
| **Total** | | **60 tasks** | **~15 parallel** |
