# Epic 4: Agentic Chat Interface (RAG)

**Branch**: `4-rag-chat`
**Status**: Draft
**Created**: 2026-03-12

---

## Overview

Approved content in the repository represents a team's collective knowledge: their campaigns, messaging, tone of voice, product positioning, and brand decisions. Today, that knowledge is trapped inside files. A marketer wanting to know "what messaging did we approve for the enterprise segment last quarter?" must manually search and read through documents. A marketer wanting to write a new LinkedIn post that sounds on-brand must manually study existing materials before writing.

This epic replaces that manual process with a conversational interface. Users ask questions in plain language; the platform finds the relevant approved content and answers directly. Users ask for new content; the platform generates it grounded in the approved materials, so the output reflects the team's actual voice and decisions rather than generic AI output.

The result is a marketing team that can interrogate their own content library the way they would interrogate a knowledgeable colleague — and generate new material that is consistent with everything they have already approved.

---

## Goals

1. Allow any authenticated user to ask questions about the organization's approved content in plain language and receive accurate, source-grounded answers.
2. Allow users to request the generation of new marketing content — social posts, email copy, briefs, summaries — that is stylistically and substantively grounded in the team's approved materials.
3. Surface the source documents behind every answer so users can verify, trace, and build on the AI's responses.
4. Maintain conversational context within a session so users can ask follow-up questions naturally, without restating prior context.
5. Keep the knowledge base current: as content is approved and updated in the platform, the chat interface automatically reflects those changes.
6. Guarantee that the knowledge base reflects only the organization's own approved content and that no unapproved or external content can influence responses.

---

## User Scenarios & Testing

### Scenario 1: User Queries Existing Content

**Actor**: Any authenticated user
**Precondition**: User is logged in. At least some approved content exists in the knowledge base.

1. User opens the chat interface and types a question: *"What are our approved key messages for the enterprise product launch?"*
2. The platform searches the approved content knowledge base for relevant material.
3. The AI synthesizes the relevant material into a direct, readable answer.
4. Below or alongside the answer, the platform lists the source documents that were used, with links to their approved versions.
5. User reads the answer, clicks a source link to verify, and is satisfied.

**Acceptance**:
- The answer is derived from approved content, not invented.
- Source documents are listed and navigable.
- If no relevant content exists for the query, the AI clearly states this rather than fabricating an answer (see Scenario 4).

---

### Scenario 2: User Asks a Follow-Up Question

**Actor**: Any authenticated user
**Precondition**: An active chat session with at least one prior exchange.

1. Following Scenario 1, the user types: *"Can you make that into a one-paragraph summary for a slide deck?"*
2. The platform understands this as a follow-up referencing the prior answer — the user does not need to repeat the topic.
3. The AI produces the requested format using the content already retrieved.
4. The conversation continues naturally.

**Acceptance**:
- The AI correctly interprets follow-up questions in the context of the current session's conversation history.
- Follow-up questions do not trigger a fresh retrieval if the content context is already in scope — the AI uses what it has retrieved.
- Conversation context is maintained for the full duration of the session.

---

### Scenario 3: User Requests Generation of New Content

**Actor**: Any authenticated user
**Precondition**: User is logged in. Relevant approved content exists in the knowledge base.

1. User types: *"Write a LinkedIn post announcing the product launch. Use our approved tone of voice and key messages."*
2. The platform retrieves approved content relevant to the request: launch messaging, tone-of-voice guidelines, product descriptions.
3. The AI generates a LinkedIn post grounded in the retrieved material — using the team's actual language, claims, and style.
4. The generated post is presented with:
   - The full post text, ready to copy
   - The source documents that informed it
   - A label clearly identifying this as AI-generated content
5. User copies the post for use.

**Acceptance**:
- The generated content reflects the vocabulary, tone, and claims found in the approved source documents.
- The generated content does not introduce product claims, statistics, or brand language that is absent from the approved content.
- The AI-generated label is always visible and cannot be hidden by the user in MVP.
- Source attribution is present for generated content, not just query answers.

---

### Scenario 4: User Asks a Question With No Relevant Content

**Actor**: Any authenticated user
**Precondition**: The knowledge base does not contain content relevant to the user's query.

1. User asks: *"What is our messaging for the consumer segment?"*
2. The platform searches the knowledge base and finds no relevant approved content.
3. The AI responds honestly: it cannot find approved content on this topic, and it will not generate an answer from general knowledge.
4. The AI suggests what the user might do: upload relevant documents and approve them to make them queryable, or rephrase the question.

**Acceptance**:
- The AI does not fabricate an answer when no relevant approved content exists.
- The "no relevant content" response is specific to the query — not a generic error.
- The AI's suggestion is actionable (directs the user to the ingestion workflow or a rephrasing).

---

### Scenario 5: User Asks for a Content Variation

**Actor**: Any authenticated user
**Precondition**: An active session. A piece of generated content has been produced.

1. User has received a generated LinkedIn post (Scenario 3) and types: *"Now give me a shorter version, under 100 words, and make the tone more formal."*
2. The AI produces a revised version meeting the user's constraints, still grounded in the same approved source material.
3. Both versions are visible in the conversation history.

**Acceptance**:
- The AI correctly applies format and tone constraints from the user's instruction.
- The revised content remains grounded in the same source documents — it does not introduce new content not present in those sources.
- Both the original and revised versions are accessible in the session history.

---

### Scenario 6: User Requests Content Referencing a Specific Document

**Actor**: Any authenticated user
**Precondition**: User knows of a specific approved document.

1. User types: *"Based only on the Q3 Campaign Brief, write a summary for an internal stakeholder email."*
2. The platform retrieves specifically the named document (or the closest matching approved document if the exact name is not found).
3. The AI generates the requested content using only that document as its source.
4. The source document is attributed clearly.

**Acceptance**:
- The platform attempts to match the user's named reference to an approved document.
- If the named document is not found, the AI states this clearly and does not substitute a different document silently.
- Content generated from a single specified document is not supplemented with content from other documents unless the user explicitly allows it.

---

### Scenario 7: User Copies Generated Content

**Actor**: Any authenticated user
**Precondition**: A response containing generated content is visible in the chat.

1. User clicks a copy action on the generated content.
2. The Markdown-formatted content is copied to the clipboard.
3. The user can paste it into any external tool.

**Acceptance**:
- Copied content includes the full text without the AI-generated label or source citations (those stay in the UI).
- The copy action is available on every AI-generated message, not just the most recent.
- Copying does not trigger any save or workflow action — it is a read-only operation in MVP.

---

### Scenario 8: Knowledge Base Is Updated After Content Approval

**Actor**: System
**Precondition**: A user has approved one or more processed documents in Epic 3.

1. A document is marked Approved in the review workflow.
2. The platform automatically queues the newly approved document for indexing into the knowledge base.
3. Within a short time, the document is searchable via the chat interface.
4. A previously unanswerable query (Scenario 4) that is now covered by the newly approved content returns a meaningful answer.

**Acceptance**:
- Approved content becomes searchable without any manual action by an Admin.
- The time between a document being approved and it being queryable is no more than 5 minutes under normal system load.
- Content that was previously in the knowledge base and is subsequently un-approved or removed is no longer returned in responses after the index updates.

---

### Scenario 9: User Views and Navigates Chat History

**Actor**: Any authenticated user
**Precondition**: User has had prior chat sessions.

1. User opens the chat interface.
2. A list of recent sessions is visible, identifiable by their first message and date.
3. User selects a prior session to review the conversation.
4. The full exchange, including generated content and source citations, is visible.
5. User can resume the prior session with a new message, which adds to the existing conversation.

**Acceptance**:
- Session history is preserved across logins.
- Sessions are scoped to the individual user — a user cannot see another user's sessions.
- Session history is retained for at least 90 days.
- The user can delete a session from history.

---

## Functional Requirements

### FR-1: Chat Interface

| ID | Requirement |
|----|-------------|
| FR-1.1 | Any authenticated user can access the chat interface. |
| FR-1.2 | The chat interface accepts plain-language text input of up to 2,000 characters per message. |
| FR-1.3 | The AI responds to each message within a reasonable time. For responses that take longer than 5 seconds to begin, a visible processing indicator is shown. |
| FR-1.4 | Responses are streamed progressively rather than displayed all at once, so the user sees the answer forming rather than waiting for a complete response. |
| FR-1.5 | Every session maintains full conversational context for its duration. Follow-up questions are understood in relation to prior exchanges. |
| FR-1.6 | Session history is preserved across logins. Prior sessions are listed and resumable. |
| FR-1.7 | Session history is retained for a minimum of 90 days and is private to the individual user. |
| FR-1.8 | Users can delete their own session history. |

---

### FR-2: Content Retrieval (Retrieval-Augmented Generation)

| ID | Requirement |
|----|-------------|
| FR-2.1 | For every user query, the platform performs a meaning-based search against the approved content knowledge base to identify the most relevant material. |
| FR-2.2 | Every response that draws on retrieved content must identify the specific source documents used, with sufficient detail for the user to locate and open the originals. |
| FR-2.4 | When a query returns no relevant approved content, the AI must clearly state that no relevant content was found. It must not generate an answer from general knowledge as a fallback. |
| FR-2.5 | The "no relevant content" response must include an actionable suggestion (e.g., approve additional documents, rephrase the query). |
| FR-2.6 | The platform retrieves the most relevant portions of approved documents, not necessarily entire documents, so that responses are precise and well-targeted. |
| FR-2.7 | Retrieval considers the full text of approved documents, including their YAML frontmatter metadata (title, author, date, tags). |

---

### FR-3: Content Generation

| ID | Requirement |
|----|-------------|
| FR-3.1 | Users can request the generation of new marketing content — including but not limited to: social media posts, email copy, briefs, summaries, headlines, and calls to action. |
| FR-3.2 | All generated content must be grounded in the organization's approved content. The AI must not introduce product claims, statistics, brand language, or messaging that is not present in the retrieved approved content. |
| FR-3.3 | Users can specify format constraints in their request (e.g., word count, tone, platform, audience) and the AI must respect them. |
| FR-3.4 | Users can request variations or revisions of generated content within the same session. |
| FR-3.5 | Users can explicitly restrict generation to a single named document ("based only on X"). If the named document is not found, the AI must state this rather than substituting silently. |
| FR-3.6 | Every piece of generated content is clearly and persistently labeled as AI-generated in the chat interface. |
| FR-3.7 | Every piece of generated content includes source attribution identifying the approved documents that informed it. |
| FR-3.8 | Generated content can be copied to the clipboard. Copying does not trigger any save or publication workflow. |

---

### FR-4: Brand Compliance & Content Groundedness

| ID | Requirement |
|----|-------------|
| FR-4.1 | The AI's behavior is constrained by the organization's approved content. It operates as a knowledgeable assistant whose knowledge is defined by what has been approved — not a general-purpose AI with unconstrained access to external information. |
| FR-4.2 | When generating content, the AI must reflect the stylistic patterns, vocabulary, and tone found in the retrieved source materials. |
| FR-4.3 | The AI must not present AI-generated content as if it were retrieved from or equivalent to an approved document. The distinction between "found in approved content" and "generated based on approved content" must always be clear to the user. |
| FR-4.4 | If a user's request would require the AI to generate content on a topic for which no approved content exists, it must decline and explain what content would need to be approved to enable the request. |
| FR-4.5 | The AI must not retain information from one user's conversation to influence responses in another user's session. |

---

### FR-5: Knowledge Base Management

| ID | Requirement |
|----|-------------|
| FR-5.1 | The knowledge base is built from approved documents only. Pending, flagged, or rejected documents from the ingestion pipeline are not indexed. |
| FR-5.2 | When a document is approved in Epic 3's review workflow, it is automatically queued for indexing. No manual action is required. |
| FR-5.3 | Newly approved content becomes searchable within 5 minutes of approval under normal system load. |
| FR-5.4 | When an approved document is un-approved or removed, it is removed from the knowledge base. It must not appear in retrieval results after removal. |
| FR-5.5 | Admins can trigger a full re-index of the knowledge base manually (e.g., after bulk content changes). |
| FR-5.6 | The knowledge base status is visible to Admins: total documents indexed, last index update time, and any documents currently queued for indexing. |
| FR-5.7 | The knowledge base contains only the organization's own approved content. No external content source may contribute to or influence the index. |

---

### FR-6: User Session Isolation

| ID | Requirement |
|----|-------------|
| FR-6.1 | Every retrieval and generation operation must require an authenticated session. Unauthenticated requests are rejected. |
| FR-6.2 | Session history is private to the individual user. A user cannot view or resume another user's sessions. |
| FR-6.3 | The AI must not carry context from one user's session into another user's session. Each session is fully isolated from all others. |

---

## Success Criteria

| # | Criterion |
|---|-----------|
| SC-1 | Users receive a first-token response (streaming begins) within 3 seconds of submitting a message for 95% of queries under normal load. |
| SC-2 | For queries where relevant approved content exists, the correct source documents are retrieved and cited in 90% or more of cases, as measured by human evaluation of a representative test set. |
| SC-3 | The AI produces a clear "no relevant content" response (rather than a fabricated answer) for 100% of queries against an empty or unrelated knowledge base. |
| SC-4 | Newly approved content is searchable within 5 minutes of approval for 99% of indexing operations. |
| SC-5 | Generated content that is evaluated by a domain expert is rated as "on-brand" (consistent with approved source style and messaging) in 80% or more of cases in a user acceptance test. |
| SC-6 | Session history from at least 90 days prior is accessible and navigable without performance degradation. |
| SC-7 | 100% of generated content is visibly labeled as AI-generated in the chat interface — zero instances of unlabeled generated output. |

---

## Key Entities

### ChatSession
A single conversation thread between a user and the AI assistant.

| Attribute | Description |
|-----------|-------------|
| id | Unique identifier |
| user_id | The user who owns this session |
| title | Auto-generated from the session's first user message |
| created_at | Session start timestamp |
| last_active_at | Timestamp of the most recent message |
| deleted_at | Soft-delete timestamp (nullable) |

---

### ChatMessage
An individual turn in a ChatSession.

| Attribute | Description |
|-----------|-------------|
| id | Unique identifier |
| session_id | The session this message belongs to |
| role | One of: user, assistant |
| content | The text of the message |
| is_generated_content | Boolean — true if the assistant message contains AI-generated marketing material (as opposed to an informational answer) |
| source_documents | List of approved document references that informed this message (nullable for user messages) |
| created_at | Message timestamp |

---

### KnowledgeBaseDocument
A record representing an approved document that has been indexed into the knowledge base.

| Attribute | Description |
|-----------|-------------|
| id | Unique identifier |
| processed_document_id | Reference to the approved ProcessedDocument from Epic 3 |
| index_status | One of: Queued, Indexed, Removed |
| indexed_at | Timestamp when indexing completed (nullable) |
| removed_at | Timestamp when removed from the index (nullable) |
| chunk_count | Number of searchable segments this document was divided into during indexing |

---

### KnowledgeBaseStatus (Admin View)
An aggregate view visible to Admins reflecting the current state of the tenant's knowledge base.

| Attribute | Description |
|-----------|-------------|
| total_indexed_documents | Count of documents currently in the index |
| documents_queued_for_indexing | Count awaiting indexing |
| last_updated_at | Timestamp of the most recent index change |
| last_full_reindex_at | Timestamp of the most recent full re-index (nullable) |

---

## Dependencies & Assumptions

### Dependencies

- **Epic 1 (IAM)**: Authentication required. All chat operations require a valid, authenticated session.
- **Epic 3 (Ingestion Pipeline)**: The knowledge base is built from approved ProcessedDocuments. This epic depends on the review and approval workflow from Epic 3. Without any approved content, the knowledge base is empty and most queries will return "no relevant content."
- **Epic 2 (GitHub Bridge)**: Not a direct runtime dependency, but the repository serves as the canonical source of approved content. The relationship between the indexed knowledge base and the repository content will need to be defined during planning (i.e., does the index pull from the ProcessedDocument records, from the GitHub repo files, or both?).
- **AI Service**: This epic has a deeper AI service dependency than Epic 3. It requires not only document processing but an ongoing, real-time conversational AI with context window management, streaming responses, and retrieval-augmented generation. The service selection, rate limits, cost model, and fallback behavior must be resolved in plan.md.

### Assumptions

| # | Assumption | Rationale |
|---|-----------|-----------|
| A-1 | All three roles (Admin, Marketing Manager, Marketer) can access the full chat interface, including content generation. | Chat is a core content capability, and all roles have content management rights per Epic 1. |
| A-2 | The AI answers only from approved indexed content. It does not supplement with general world knowledge when indexed content is insufficient. | Brand compliance requires that responses reflect what the team has actually approved, not what an AI assumes is correct. |
| A-3 | Generated content is clipboard-only in MVP. It cannot be directly saved to the repository, submitted as a document, or routed into an approval workflow from the chat interface. | Keeps MVP scope contained. A content save/publish flow from chat is a natural next epic. |
| A-4 | Session history is retained for 90 days then eligible for automated deletion. | Balances utility (users referencing past sessions) against storage costs. Retention policy can be made configurable post-MVP. |
| A-5 | The knowledge base indexes the approved Markdown content from Epic 3's ProcessedDocument records, not directly from the GitHub repository files. | Ensures the knowledge base reflects what the platform has processed and approved, not raw repo state which may include unprocessed content. |
| A-6 | Indexing divides each document into meaningful segments (e.g., by section or paragraph) rather than indexing the document as a single unit. This enables precise retrieval of the relevant portion of a document. | Whole-document retrieval produces imprecise results. Segment-level retrieval is standard practice for effective RAG performance. |
| A-7 | The maximum input message length is 2,000 characters. Large content generation requests requiring more context should be broken into multiple turns. | Prevents abuse and controls token consumption while covering all practical single-message use cases. |
| A-8 | The AI's response is streamed progressively (token by token) to the UI rather than delivered as a complete payload. | Streaming dramatically reduces perceived latency and is the expected UX for conversational AI interfaces. |
| A-9 | In MVP, only one AI conversation can be active per user at a time. Opening a new session suspends but does not delete any in-progress session. | Simplifies context management and resource allocation. |
| A-10 | The system prompt and retrieval instructions that govern the AI's behavior (brand compliance guardrails, content boundaries) are managed by the platform and are not editable by end users. | Prevents users from bypassing brand compliance constraints through prompt manipulation. |

---

## Out of Scope

- Saving AI-generated content directly to the GitHub repository or submitting it to an approval workflow from the chat interface (future epic)
- In-platform editing of AI-generated content before copying (clipboard only in MVP)
- Image, diagram, or multimedia generation
- Voice or audio input to the chat interface
- Multi-user or collaborative chat sessions (each session belongs to one user)
- Connecting the chat interface to external data sources beyond the organization's approved content knowledge base (e.g., live web search, CRM data, analytics)
- User-configurable AI behavior, persona, or system prompt modifications
- Fine-tuning or training a custom AI model on tenant content
- Analytics or reporting on chat usage, query patterns, or generated content volume (future epic)
- Exporting full chat session transcripts (individual content copying is in scope; transcript export is not)
- Content moderation or filtering of user inputs beyond standard platform authentication
- Webhook or API-based access to the chat interface for third-party integrations
- Any content generated by the AI being treated as or promoted to "approved content" without going through Epic 3's ingestion and review workflow
