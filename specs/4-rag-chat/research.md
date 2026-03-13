# Research: Epic 4 — Agentic Chat Interface (RAG)

**Date**: 2026-03-13
**Resolved**: All NEEDS CLARIFICATION items

---

## Decision 1: Vector Store — pgvector (no separate vector DB)

**Decision**: pgvector extension on the existing PostgreSQL instance. HNSW index with cosine similarity. No Pinecone, Weaviate, or Qdrant.

**Rationale**: The platform deploys as a single-tenant PostgreSQL container per client. Adding a separate vector DB service doubles infrastructure complexity, adds a new failure surface, and requires a new vendor contract — none of which is justified at the 10K–100K chunk scale of a single-organization marketing content library. pgvector with HNSW delivers sub-200ms p95 query latency at 100K × 1536-dimension vectors on a standard GKE node (e2-standard-4 or larger). HNSW is preferred over IVFFlat because it handles incremental inserts cleanly (no re-training required), which matters since the knowledge base grows continuously as content is approved.

**Index configuration**:
```sql
CREATE INDEX ON content_chunks
  USING hnsw (embedding vector_cosine_ops)
  WITH (m = 24, ef_construction = 64);

-- At query time
SET hnsw.ef_search = 100;  -- ~0.98 recall@10
```

**Library**: `pgvector-python` — supports SQLAlchemy 2.0 async + asyncpg/psycopg3 natively. Register the vector type once at engine startup.

**Memory budget**: HNSW at m=24 over 100K × 1536-dim vectors ≈ 460–700 MB RAM for the index. Standard 4–8 GB GKE node is sufficient.

**Alternatives considered**: Pinecone (separate vendor, cost, added infra), Qdrant (Docker sidecar — violates CONSTITUTION stateless requirement), local FAISS (no persistence, in-memory only — not viable for a persistent knowledge base).

---

## Decision 2: Embedding Model — OpenAI text-embedding-3-small

**Decision**: OpenAI `text-embedding-3-small` (1536 dimensions, $0.02/1M tokens).

**Rationale**:
- Anthropic does **not** offer an embeddings API (confirmed in 2025/2026 docs). Their recommended alternative is Voyage AI.
- `text-embedding-3-small` is the cost-performance optimum for MVP: $0.02/1M tokens, meaning a full corpus of 100K chunks at ~400 tokens average = $0.80 to embed the entire knowledge base.
- 1536 dimensions aligns naturally with pgvector defaults and leaves upgrade headroom (Matryoshka truncation to 256 or 512 dims if storage becomes a concern).
- Adds one `pip install openai` dependency — minimal complexity given we already use the Anthropic SDK.
- API latency: ~50–100ms per embedding call, well within the 3s first-token budget (SC-1).

**Query embedding**: Same model (`text-embedding-3-small`) used at query time. Embedding model consistency between index and query is mandatory — any future migration requires full corpus re-embedding.

**Upgrade path**: If retrieval quality underperforms on marketing-specific vocabulary, migrate to `voyage-3.5-lite` (same price, 1024 dims, Anthropic-maintained, supports `input_type="document"/"query"` asymmetric encoding for better recall). Migration cost: re-embed corpus, update pgvector column dimension from 1536 to 1024, rebuild HNSW index.

**Alternatives considered**: Local `all-MiniLM-L6-v2` (128-token max input cap — too short for marketing sections; 384 dims = lower recall; adds ~300 MB container weight), Vertex AI `text-embedding-004` (768 dims; additional GCP service account complexity), Voyage AI `voyage-3.5` ($0.06/1M tokens — 3× cost premium not justified at MVP scale).

---

## Decision 3: Chunking Strategy — Section-Primary with Overflow Splitting

**Decision**: Split Markdown on `##` section headings (primary boundary). Overflow sections that exceed 512 tokens are split with a 50-token sliding window overlap. YAML frontmatter is prepended to every chunk.

**Rationale**: Marketing Markdown has well-defined structure (YAML frontmatter + `##` headings + body). Exploiting semantic section boundaries outperforms naive fixed-window chunking because sections are the natural unit of meaning (a tone-of-voice section, a key messages section, a product description section). Most marketing sections are 200–600 tokens — within a single embedding context window. Section-boundary splits avoid breaking a message mid-thought.

**Frontmatter prepend** (FR-2.7): The YAML frontmatter (`title`, `author`, `source_date`, `source_type`, campaign tags, etc.) is prepended to every chunk before embedding. This ensures metadata fields are semantically searchable. The structured frontmatter dict is also stored in a `metadata JSONB` column for hard-filtering (e.g., `WHERE metadata->>'campaign' = 'Q1 Enterprise Launch'`).

**Chunk size**: 512 tokens (~2048 characters). Peak retrieval quality (faithfulness + relevancy) benchmarks at 512–1024 tokens for short-form content. 512-token chunks leave headroom to inject 4–6 chunks (~2K–3K tokens) into the generation context window without exceeding Claude's 200K context limit.

**Overlap**: 50 tokens (roughly 2–3 sentences) at section overflow boundaries. Marketing sections rarely have cross-section dependencies requiring large overlap windows.

**Implementation**: Pure Python with `re` and `pyyaml` (already in dependencies). No LangChain or LlamaIndex required — keeps the dependency surface minimal and the chunking logic auditable.

---

## Decision 4: RAG System Prompt Design — Constrained Answer Mode

**Decision**: A fixed, non-user-editable system prompt enforces: (1) answer only from retrieved context, (2) explicitly decline when context is insufficient, (3) never fabricate product claims or statistics. The prompt distinguishes between "retrieval answers" and "generated content" modes.

**Rationale**: FR-4.1, FR-4.4, and SC-3 (100% no-fabrication rate) require the AI's behavior to be platform-controlled. A-10 prohibits user modification. The system prompt is assembled server-side from a template; users cannot inject instructions that override these constraints.

**System prompt structure**:
```
You are the marketing assistant for [organization]. Your knowledge is defined
exclusively by the approved content context provided below. You must:
1. Answer only from the provided context. If the context does not contain
   information relevant to the question, respond: "I don't have approved
   content on this topic. To enable this, approve documents covering [topic]
   through the ingestion workflow."
2. Never introduce product claims, statistics, or brand language absent from
   the context.
3. For generation requests: produce the requested format using only the
   vocabulary, tone, and claims found in the context. Label all generated
   content clearly.
4. For follow-up questions: use the conversation history to understand context.
   Do not retrieve new content unless explicitly asked to search for more.
```

**Context injection format**: Retrieved chunks are injected as a structured block between the system prompt and the user message. Each chunk includes its source document title and chunk index for attribution.

---

## Decision 5: Streaming Architecture — FastAPI SSE + AsyncAnthropic

**Decision**: FastAPI `StreamingResponse` with an `async_generator` function. `AsyncAnthropic.messages.stream()` as an async context manager. Structured SSE events: `delta` (text token), `sources` (after generation), `done` (sentinel).

**Rationale**: FR-1.4 requires progressive token streaming. SC-1 requires first token within 3 seconds. SSE (Server-Sent Events) over HTTP is the correct protocol — it works through standard HTTP/1.1, requires no WebSocket upgrade, and is natively consumable by browser `EventSource` API and `fetch` with `ReadableStream`.

**Wire format (SSE)**:
```
data: {"type": "delta", "text": "Here"}\n\n
data: {"type": "delta", "text": " are"}\n\n
...
data: {"type": "sources", "sources": [{"id": "uuid", "title": "Q1 Brief"}]}\n\n
data: {"type": "done"}\n\n
```

**Critical constraints**:
- `async with client.messages.stream(...) as stream` is mandatory — the context manager handles connection cleanup and cancellation cleanly.
- GKE nginx ingress must set `X-Accel-Buffering: no` and `nginx.ingress.kubernetes.io/proxy-buffering: "off"` annotation to prevent response buffering that would defeat streaming.
- `AsyncAnthropic` client is instantiated once at module level — not per-request.
- First-token latency budget: pgvector HNSW retrieval (~50ms) + OpenAI embedding (~100ms) + Anthropic stream open (~200ms) = ~350ms total pre-stream latency. Well within SC-1's 3s requirement.

**Alternatives considered**: WebSockets (more complex — requires persistent connection state, not necessary for unidirectional streaming), HTTP/2 server push (poor library support in Python ecosystem), polling (unacceptable UX latency).

---

## Decision 6: Indexing Pipeline — Extend Epic 3's Queue Pattern

**Decision**: Extend `utils/queue.py` with a `index_document(kb_doc_id)` function. Trigger indexing automatically when a document is approved in `ingestion.py` (DRY — reuse the PostgreSQL queue pattern).

**Rationale**: FR-5.2 requires automatic indexing on approval. FR-5.3 requires indexing within 5 minutes. The Epic 3 queue infrastructure (PostgreSQL SKIP LOCKED, asyncio worker pool, `startup_recovery`, `_timeout_watchdog`) is already built and proven. Re-using it for KB indexing avoids a new queue system and keeps operational mental model consistent.

**Approval trigger**: When `PATCH /batches/{id}/documents/{id}/review` sets `review_status = approved`, the handler also creates a `KnowledgeBaseDocument` row with `index_status = queued`. A dedicated indexing worker (added to the worker pool in `_lifespan`) picks it up: downloads `markdown_content` from `processed_documents`, chunks it, embeds each chunk via OpenAI, upserts rows into `content_chunks`.

**Un-approval/removal trigger**: When a document is flagged for reprocessing (review set back to `flagged_for_reprocessing`), the corresponding `KnowledgeBaseDocument` row is marked `removed` and all its `content_chunks` are deleted. It will not appear in retrieval until re-approved and re-indexed.

**Full re-index** (FR-5.5): Admin endpoint `POST /admin/knowledge-base/reindex` truncates `content_chunks`, resets all `KnowledgeBaseDocument.index_status` to `queued`, and lets the worker pool re-process all approved documents.

---

## Epic 3 → Epic 4 Data Contract

**Confirmed**: The knowledge base indexes `ProcessedDocument.markdown_content` directly from the PostgreSQL table (Assumption A-5). It does not pull from the GitHub repository.

**Frontmatter contract** (FR-2.7): The YAML frontmatter schema from Epic 3 is a retrieval input. Fields guaranteed to exist: `title`, `source_file`, `source_type`, `ingested_at`, `ingested_by`, `review_status`. Optional fields: `author`, `source_date`, `reprocessing_note`. This schema must not change without a re-indexing migration.

**ProcessedDocument → KnowledgeBaseDocument relationship**: One-to-one. A `ProcessedDocument` may have at most one `KnowledgeBaseDocument`. The UNIQUE constraint on `knowledge_base_documents.processed_document_id` enforces this.

---

## Tenant/User Isolation

**Single-tenant deployment**: Since each client is a separate Docker container with a separate database, cross-tenant isolation is guaranteed at the infrastructure level. No pgvector namespace partitioning is required — the entire database belongs to one organization.

**Per-user session isolation** (FR-6.2, FR-6.3): `chat_sessions.user_id` enforces session ownership. All session and message queries include `WHERE user_id = current_user.id`. The AI receives no cross-user context — conversation history is assembled only from the requesting user's current session.
