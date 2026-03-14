# Feature Specification: Next.js Marketing Platform Frontend

**Feature Branch**: `005-nextjs-frontend`
**Created**: 2026-03-13
**Status**: Draft

## User Scenarios & Testing *(mandatory)*

### User Story 1 — Secure Login and Session Management (Priority: P1)

A marketing team member navigates to the platform, enters their email and password, and gains access to their role-appropriate dashboard. Their session persists across page refreshes. When idle too long, they are automatically signed out and redirected to login.

**Why this priority**: All other functionality is gated behind authentication. Without login, nothing else can be tested or used.

**Independent Test**: A user can visit the login page, authenticate with valid credentials, land on the dashboard, and be redirected back to login after session expiry.

**Acceptance Scenarios**:

1. **Given** a registered user, **When** they enter valid credentials and submit, **Then** they are redirected to the dashboard and their role-appropriate navigation is shown.
2. **Given** a user who enters incorrect credentials, **When** they submit, **Then** an error message is displayed and they remain on the login page.
3. **Given** an authenticated user, **When** their session expires, **Then** they are redirected to login with a "session expired" message.
4. **Given** an unauthenticated visitor, **When** they navigate to any protected route, **Then** they are redirected to the login page.

---

### User Story 2 — Dashboard and Navigation (Priority: P2)

After login, a user lands on a dashboard showing a summary of platform activity: recent content syncs, ingestion queue status, and a quick-access chat entry point. Navigation gives access to all sections appropriate to their role.

**Why this priority**: The dashboard orients users within the platform and determines what they can access. Establishes the shell for all other screens.

**Independent Test**: An authenticated user can log in, see the dashboard summary cards, and navigate to at least one other section.

**Acceptance Scenarios**:

1. **Given** an authenticated admin, **When** they view the dashboard, **Then** they see navigation links for Content, Ingestion, Chat, Users, and GitHub Connection.
2. **Given** an authenticated regular user, **When** they view the dashboard, **Then** they see navigation links for Content, Ingestion, and Chat but not Users or KB admin controls.
3. **Given** any authenticated user, **When** they view the dashboard, **Then** they see summary metrics (content item count, pending ingestion jobs, recent chat sessions).

---

### User Story 3 — RAG Chat Interface (Priority: P2)

A user opens the chat interface, types a question about marketing content, and receives a streamed response drawn from the knowledge base. They can continue the conversation, start a new session, and browse prior conversation history.

**Why this priority**: Chat is the primary value-delivery mechanism of the platform — the surface through which AI-assisted content insight is accessed.

**Independent Test**: A user can send a message and see the response stream in character-by-character, start a new session, and load a previous session from history.

**Acceptance Scenarios**:

1. **Given** an authenticated user on the chat screen, **When** they type a message and submit, **Then** the assistant response streams in incrementally (visible token-by-token).
2. **Given** a streaming response in progress, **When** the user views the UI, **Then** a loading indicator is shown and the send button is disabled until streaming completes.
3. **Given** content flagged as generated, **When** it appears in the chat, **Then** it is visually distinguished (e.g., labeled "AI-generated content").
4. **Given** a user with prior sessions, **When** they open the session list, **Then** previous conversations are listed with title and date, and clicking one loads the full history.
5. **Given** a user on any session, **When** they click "New Chat", **Then** a fresh session begins.

---

### User Story 4 — Content Browser (Priority: P3)

A user browses synced content from connected GitHub repositories. They can view a list of content items, filter by type or status, and open a detail view showing the structured content and metadata.

**Why this priority**: Core content visibility feature. Valuable but usable independently of ingestion and chat.

**Independent Test**: A user can navigate to the Content section, see a paginated list of synced documents, and open a detail view for one item.

**Acceptance Scenarios**:

1. **Given** an authenticated user, **When** they navigate to Content, **Then** they see a list of synced documents with title, type, status, and last-updated date.
2. **Given** a content list, **When** the user filters by status (e.g., "processed"), **Then** only matching items are shown.
3. **Given** a content item in the list, **When** the user clicks it, **Then** a detail view opens showing structured content and frontmatter metadata.

---

### User Story 5 — Document Ingestion (Priority: P3)

A user uploads one or more files (PDF, DOCX, PPTX, CSV, TXT/MD) to trigger the ingestion pipeline. They can monitor the status of queued and processing jobs and see when documents have been processed into the knowledge base.

**Why this priority**: Enables the content pipeline to be driven from the UI rather than via API calls directly.

**Independent Test**: A user can upload a file, see it appear as a queued job, and watch its status update to processed.

**Acceptance Scenarios**:

1. **Given** an authenticated user on the Ingestion screen, **When** they drag-and-drop or select a file, **Then** the file is uploaded and appears in the job list with status "queued".
2. **Given** a queued ingestion job, **When** the pipeline processes it, **Then** the status updates to "processing" then "complete" without requiring a page refresh.
3. **Given** a user who uploads an unsupported file type, **When** they submit, **Then** an inline error explains the supported formats.
4. **Given** a failed ingestion job, **When** the user views it in the list, **Then** a failure reason is shown.

---

### User Story 6 — GitHub Connection Setup (Priority: P3)

An admin connects a GitHub repository by entering a personal access token and repo URL. The platform validates the connection and shows the repo's sync status. Admins can disconnect a repo.

**Why this priority**: Prerequisite for content sync but handled infrequently; set-and-forget configuration screen.

**Independent Test**: An admin can navigate to GitHub Connection, enter a valid token and repo URL, and see confirmation that the connection is active.

**Acceptance Scenarios**:

1. **Given** an admin with no GitHub connection, **When** they enter a valid token and repo URL and submit, **Then** the connection is created and repo status is shown as "connected".
2. **Given** an invalid token, **When** submitted, **Then** an error message explains the token could not be validated.
3. **Given** an active connection, **When** the admin clicks "Disconnect", **Then** the connection is removed after confirmation.

---

### User Story 7 — User Management (Priority: P4)

An admin views all platform users, invites new members by email, and can change a user's role. Invited users receive an email with a link to complete registration.

**Why this priority**: Admin-only capability, lower frequency of use than core content workflows.

**Independent Test**: An admin can view the user list, send an invitation to a new email address, and see the invitation appear as pending.

**Acceptance Scenarios**:

1. **Given** an admin on the Users screen, **When** they view the list, **Then** all users are shown with name, email, role, and status (active/pending).
2. **Given** an admin, **When** they enter an email and select a role and click Invite, **Then** an invitation is sent and the user appears as "pending" in the list.
3. **Given** a regular user, **When** they attempt to navigate to User Management, **Then** they see a 403 / access denied screen.

---

### Edge Cases

- What happens when the backend is unreachable? Display a connection error banner; do not expose raw API errors.
- What happens when a chat stream is interrupted mid-response? Show partial response with a "response interrupted" notice.
- What happens when a user's token expires mid-session? Intercept the 401, clear local state, and redirect to login.
- What happens when a file upload exceeds the size limit? Show an inline error before upload is attempted.
- What happens when there are no content items or sessions yet? Show empty states with instructional copy, not blank pages.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: The platform MUST require authentication before any content is accessible.
- **FR-002**: Session tokens MUST be stored in httpOnly cookies (not localStorage) to prevent XSS access.
- **FR-003**: The UI MUST derive visible navigation and feature access from the authenticated user's role.
- **FR-004**: Admin-only screens (User Management, KB Admin controls) MUST be inaccessible to non-admin roles, enforced both visually and via route guard.
- **FR-005**: The chat interface MUST render streamed responses incrementally using server-sent events.
- **FR-006**: The chat interface MUST visually distinguish AI-generated content from retrieved knowledge base content.
- **FR-007**: Conversation sessions MUST be listed with title and timestamp; users MUST be able to switch between sessions.
- **FR-008**: The ingestion screen MUST accept file uploads for PDF, DOCX, PPTX, CSV, TXT, and MD formats.
- **FR-009**: Ingestion job status MUST update in near-real-time without requiring a manual page refresh (polling or SSE).
- **FR-010**: The content browser MUST support pagination and filtering by status.
- **FR-011**: The GitHub connection screen MUST validate the token and repo URL before saving.
- **FR-012**: The user invitation flow MUST allow an admin to specify email and role before sending.
- **FR-013**: All API errors MUST be surfaced as user-readable messages; raw error objects MUST NOT be shown.
- **FR-014**: The application MUST be deployable to Vercel and communicate with the FastAPI backend at `api.activelab.com`.

### Key Entities

- **User Session**: Authenticated identity, role, and token — drives all access decisions.
- **Content Item**: Synced document from GitHub with title, type, status, and structured body.
- **Ingestion Job**: Upload record tracking file name, status (queued/processing/complete/failed), and failure reason.
- **Chat Session**: Conversation container with title, created date, and ordered message history.
- **Chat Message**: Individual turn (user or assistant) with content, timestamp, and generated-content flag.
- **GitHub Connection**: Linked repository with connection status and sync metadata.
- **Invitation**: Pending user registration record with email, role, and expiry.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: A user can log in, navigate to chat, send a message, and see a streamed response within 30 seconds of opening the application for the first time.
- **SC-002**: Chat responses begin streaming within 3 seconds of submitting a message under normal network conditions.
- **SC-003**: All protected routes redirect unauthenticated users to login within one navigation event — no content flashes before redirect.
- **SC-004**: Ingestion job status reflects backend state within 5 seconds of a status change without a page refresh.
- **SC-005**: A non-admin user cannot reach User Management or KB Admin screens through any navigation path available in the UI.
- **SC-006**: The application renders correctly and is fully functional on the latest versions of Chrome, Safari, and Firefox.
- **SC-007**: Empty states are present for all list views so no screen appears broken on a fresh install.

## Assumptions

- The FastAPI backend at `api.activelab.com` is the sole data source; no separate BFF layer is introduced.
- Authentication uses the existing JWT-based login endpoint; the frontend exchanges credentials for a token stored in an httpOnly cookie via a Next.js server route (to avoid exposing the token to client JavaScript).
- Role values from the API are `admin` and `user`; no additional roles are anticipated for this MVP.
- Email delivery for invitations is handled entirely by the backend; the frontend only triggers the invite API call.
- No offline mode or service worker caching is required for this MVP.
- The content browser is read-only in this epic; editing content directly in the UI is out of scope.
- Internationalization (i18n) is out of scope for MVP.
