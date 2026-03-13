# Quickstart: Epic 4 — Agentic Chat Interface (RAG)

**Prerequisites**: Epic 1 (IAM), Epic 3 (Ingestion) complete and running.

---

## Environment Setup

```bash
# Add to .env
OPENAI_API_KEY=sk-...                    # Required: text-embedding-3-small
KB_SIMILARITY_THRESHOLD=0.3              # Cosine similarity floor (0–1; lower = more permissive)
KB_RETRIEVAL_TOP_K=6                     # Chunks retrieved per query
CHAT_MODEL=claude-opus-4-6               # Generation model (fallback: claude-sonnet-4-6)
CHAT_MAX_TOKENS=1024                     # Max tokens per response
KB_INDEX_CONCURRENCY=2                   # Indexing workers (separate from processing workers)
```

---

## Database Setup

```bash
# Enable pgvector + create RAG tables
cd marketing-platform
alembic upgrade head

# Verify pgvector is active
psql $DATABASE_URL -c "SELECT extname, extversion FROM pg_extension WHERE extname = 'vector';"
# Expected: vector | 0.8.0 (or current version)

# Verify tables
psql $DATABASE_URL -c "\dt chat_sessions chat_messages knowledge_base_documents content_chunks"
```

---

## Smoke Test: Indexing Pipeline

```bash
# 1. Approve a document via the review endpoint (Epic 3)
curl -X PATCH http://localhost:8000/api/v1/ingestion/batches/{batch_id}/documents/{doc_id}/review \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"review_status": "approved"}'
# Expected: 200, review_status=approved

# 2. Verify KnowledgeBaseDocument row created (queued)
psql $DATABASE_URL -c "
  SELECT index_status, chunk_count, indexed_at
  FROM knowledge_base_documents kd
  JOIN processed_documents pd ON pd.id = kd.processed_document_id
  ORDER BY kd.created_at DESC LIMIT 1;"
# Expected: index_status=queued initially, then indexed within ~30 seconds

# 3. Verify content_chunks populated
psql $DATABASE_URL -c "
  SELECT COUNT(*), AVG(length(content_text)) as avg_chunk_chars
  FROM content_chunks;"

# 4. Check KB status (admin)
curl http://localhost:8000/api/v1/admin/knowledge-base/status \
  -H "Authorization: Bearer $ADMIN_TOKEN" \
  -H "X-Admin-Token: $ADMIN_TOKEN"
# Expected: total_indexed_documents >= 1
```

---

## Smoke Test: Chat + RAG

```bash
# 1. Create a session
SESSION=$(curl -sX POST http://localhost:8000/api/v1/chat/sessions \
  -H "Authorization: Bearer $TOKEN" | jq -r '.data.session_id')
echo "Session: $SESSION"

# 2. Send a message and stream response
curl -N http://localhost:8000/api/v1/chat/sessions/$SESSION/messages \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"content": "What key messages do we have approved?"}' \
  --no-buffer
# Expected: stream of SSE events ending with sources and done

# 3. Verify message persisted in DB
curl http://localhost:8000/api/v1/chat/sessions/$SESSION \
  -H "Authorization: Bearer $TOKEN" | jq '.data.messages | length'
# Expected: 2 (user message + assistant message)

# 4. Send a follow-up (tests conversation context)
curl -N http://localhost:8000/api/v1/chat/sessions/$SESSION/messages \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"content": "Can you turn that into a one-paragraph summary?"}'
# Expected: AI uses context from prior exchange without re-retrieving

# 5. Test no-content response
curl -N http://localhost:8000/api/v1/chat/sessions/$SESSION/messages \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"content": "What is our strategy for the consumer segment?"}'
# Expected: SSE event type=no_content (if no consumer content approved)

# 6. Delete session
curl -X DELETE http://localhost:8000/api/v1/chat/sessions/$SESSION \
  -H "Authorization: Bearer $TOKEN"
# Expected: 200, deleted=true

# 7. Verify session no longer listed
curl http://localhost:8000/api/v1/chat/sessions \
  -H "Authorization: Bearer $TOKEN" | jq '.data | length'
# Expected: 0 (or prior count minus 1)
```

---

## Admin: Trigger Full Re-Index

```bash
curl -X POST http://localhost:8000/api/v1/admin/knowledge-base/reindex \
  -H "Authorization: Bearer $ADMIN_TOKEN" \
  -H "X-Admin-Token: $ADMIN_TOKEN"
# Expected: 202, documents_queued > 0
```

---

## Local pgvector Setup (docker-compose)

pgvector requires a PostgreSQL image with the extension pre-installed. Update `docker-compose.yml`:

```yaml
services:
  db:
    image: pgvector/pgvector:pg16   # Replace plain postgres:16
    ...
```

The Alembic migration runs `CREATE EXTENSION IF NOT EXISTS vector` — this will succeed on the pgvector image and fail gracefully if already installed.

---

## Testing SSE Locally

```bash
# httpie (streaming-friendly)
http --stream POST http://localhost:8000/api/v1/chat/sessions/$SESSION/messages \
  "Authorization: Bearer $TOKEN" \
  content="What are our enterprise key messages?"
```
