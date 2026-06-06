# Implementation Plan: RAG Over Tenant Documents

**Branch**: `009-rag-over-tenant-documents` | **Date**: 2026-06-06 | **Spec**: [spec.md](./spec.md)

**Input**: Feature specification from `specs/009-rag-over-tenant-documents/spec.md`

**Depends on**:
- [Spec 001 — Multi-Tenant Workspace](../001-multi-tenant-workspace/plan.md): tenants, `tenant_id` isolation, cross-tenant blocking
- [Spec 002 — Authentication and Roles](../002-auth-and-roles/plan.md): JWT auth; `manager` (process) + `staff` (view) roles; `require_role`
- [Spec 003 — Message Simulator](../003-message-simulator/plan.md): messages a query can link to
- [Spec 005 — Message Detail Page](../005-message-detail-page/plan.md): Knowledge Sources panel (replaces the placeholder)
- [Spec 008 — Document Upload](../008-document-upload/plan.md): source `documents` (`enabled`, `status`, `content`, title, type) — this feature advances status to `processed`/`failed`

**Downstream consumer**: the future suggested-reply feature reads the persisted grounded sources as evidence. Not built here.

---

## Summary

Build the retrieval half of RAG over Spec 008 documents using pgvector. A processing step chunks an enabled document, embeds each chunk with a versioned embedding model, and stores chunks (`chunk_text`, `chunk_index`, `embedding vector`, `metadata`, `tenant_id`, `document_id`) in a new `document_chunks` table, advancing the document to `processed`. A retrieval step embeds a query and runs a pgvector similarity search **unconditionally filtered by `tenant_id`** (and `enabled = true`, doc `status = processed`), returning the top-k sources (title, type, snippet, score) above a relevance threshold — or `no_source` / `no_documents` when appropriate. Queries and their results are persisted (`rag_queries`, `rag_retrieval_results`) and, when linked to a message, surfaced in the detail page's Knowledge Sources panel. The feature retrieves evidence only — it generates no replies and sends nothing. Tenant isolation is absolute and has no cross-tenant code path.

---

## Technical Approach

- **Indexing pipeline**: `chunk(content) → embed(chunks) → store(chunks)` in one transactional, idempotent processing operation per document (re-process deletes prior chunks first).
- **Retrieval pipeline**: `embed(query) → pgvector ANN/exact search WHERE tenant_id=… AND enabled AND processed → threshold + top-k → rank → persist results`.
- **Tenant isolation by construction**: the only query builder for chunk search injects `tenant_id` from the JWT; there is no function that searches chunks without it (SR-02). Single-resource endpoints resolve the document/message tenant first (404/403, Specs 005–008 pattern).
- **Refuse path is first-class**: below-threshold → `no_source`; empty corpus → `no_documents`. These are explicit statuses the downstream reply feature must honour (SR-06).
- **Deterministic**: one versioned embedding model; tie-breaking `(score desc, document_id, chunk_index)` for stable ordering (FR-015, AC-17).
- **Embedding abstraction**: an `Embedder` interface (model + version) so the MVP can use a local deterministic model and later swap models cleanly; version recorded in chunk metadata.

---

## Backend Tasks

1. **`schemas/rag.py`** — Pydantic models: `ProcessResponse`, `ChunkResponse`, `RagQueryRequest`, `RagSource`, `RagQueryResponse`, `MessageRagResultsResponse`, plus `RetrievalStatus` enum.
2. **`rag/chunker.py`** — `chunk_text(content, size, overlap) -> list[str]`: bounded, overlapping, order-preserving splitter (token/char based). Pure + unit-testable.
3. **`rag/embedder.py`** — `Embedder.embed(texts) -> list[vector]` + `model_version`; deterministic local model for MVP; typed `EmbeddingUnavailable`.
4. **`rag/retriever.py`** — `search(session, tenant_id, query_vector, top_k, threshold) -> list[(chunk, score)]`: builds the pgvector query with mandatory tenant + enabled + processed filters; applies threshold + tie-break ordering.
5. **`services/rag_service.py`**:
   - `process_document(session, tenant_id, document_id)` — resolve doc (404/403), reject disabled (422), chunk + embed + replace chunks, set status `processed`/`failed`.
   - `query(session, tenant_id, query_text, top_k, threshold, message_id=None)` — embed, retrieve, classify status, persist `RagQuery` + `RagRetrievalResult`s, return sources.
   - `list_chunks(session, tenant_id, document_id)` — tenant-resolve, return chunks.
   - `get_message_rag_results(session, tenant_id, message_id)` — tenant-resolve message, return latest stored results.
6. **`api/v1/rag.py`** — four endpoints with `require_role` per method + error→HTTP mapping.
7. **Config** — `RAG_CHUNK_SIZE`, `RAG_CHUNK_OVERLAP`, `RAG_TOP_K`, `RAG_SCORE_THRESHOLD`, `RAG_EMBEDDING_MODEL`, `RAG_EMBEDDING_DIM` in settings.
8. **Router mount** — register the RAG router at `/api` in `main.py`.
9. **Surface in detail** — extend the Spec 005 conversation/message detail response (or a dedicated fetch) so the Knowledge Sources panel can read message RAG results.

---

## Database Tasks

1. **Enable pgvector** — Alembic migration runs `CREATE EXTENSION IF NOT EXISTS vector;`.
2. **`document_chunks` table**:
   - `id` UUID PK
   - `tenant_id` UUID NOT NULL FK → tenants, indexed
   - `document_id` UUID NOT NULL FK → documents, `ON DELETE CASCADE`, indexed
   - `chunk_text` TEXT NOT NULL
   - `chunk_index` INTEGER NOT NULL
   - `embedding` `vector(RAG_EMBEDDING_DIM)` NOT NULL
   - `metadata` JSONB (embedding model/version, char span, source title/type snapshot)
   - `created_at` TIMESTAMPTZ
   - UNIQUE `(document_id, chunk_index)`
3. **`rag_queries` table**: `id`, `tenant_id` (FK, indexed), `message_id` (FK nullable), `query_text`, `top_k`, `threshold`, `status` (RetrievalStatus), `embedding_model`, `created_at`.
4. **`rag_retrieval_results` table**: `id`, `rag_query_id` (FK → rag_queries, cascade), `tenant_id`, `document_id`, `chunk_id` (FK → document_chunks), `snippet`, `score` (double), `rank` (int), `created_at`.
5. **Indexes**:
   - pgvector ANN index on `document_chunks.embedding` (e.g., `ivfflat`/`hnsw` with cosine ops) — **paired with the `tenant_id` filter at query time**.
   - `(tenant_id, document_id)` on chunks; `(tenant_id, message_id)` on `rag_queries`; `(rag_query_id, rank)` on results.
6. **SQLAlchemy models** — `DocumentChunk`, `RagQuery`, `RagRetrievalResult` with relationships; pgvector type via `pgvector.sqlalchemy.Vector`.

---

## pgvector / Vector Storage Tasks

1. **Extension + column** — install `pgvector`; define `embedding vector(dim)` sized to `RAG_EMBEDDING_DIM`.
2. **Distance op** — use cosine distance (`<=>`) consistently for chunk + query; convert distance → similarity score for the threshold/UI.
3. **ANN index** — create an `ivfflat`/`hnsw` index for scale; ensure queries still apply the `tenant_id` (+ `enabled`/`processed`) predicate so isolation holds regardless of the index.
4. **Dimension guard** — validate embedding length == `RAG_EMBEDDING_DIM` before insert; mismatch → fail processing cleanly.
5. **Idempotent replace** — on re-process, `DELETE FROM document_chunks WHERE document_id=… AND tenant_id=…` then insert fresh (single transaction).

---

## Document Chunking Tasks

1. **Bounded chunks** — split `content` into chunks of `RAG_CHUNK_SIZE` with `RAG_CHUNK_OVERLAP` overlap; preserve order via `chunk_index`.
2. **Boundary awareness** — prefer splitting on paragraph/sentence boundaries where feasible to keep chunks coherent (fallback to hard size cap).
3. **Short docs** — content smaller than one chunk → a single chunk.
4. **Metadata** — record char span + source title/type snapshot in chunk `metadata` for source display + provenance.
5. **Unit tests** — size/overlap correctness, ordering, short/long inputs, determinism.

---

## Embedding Tasks

1. **Embedder interface** — `embed(texts) -> vectors`, exposes `model_version` + `dim`; deterministic local model for MVP.
2. **Batch embedding** — embed all chunks of a document in one batched call for efficiency.
3. **Query embedding** — same model/space for queries; cache not required for MVP.
4. **Version stamping** — store `model_version` in chunk metadata + `rag_queries.embedding_model`.
5. **Failure handling** — `EmbeddingUnavailable` → processing sets doc `failed`; query returns `status=failed`; no partial writes.

---

## Retrieval Tasks

1. **Tenant-filtered search** — single retriever that always applies `tenant_id` + `enabled` + `processed`; cosine top-k.
2. **Threshold + statuses** — apply `RAG_SCORE_THRESHOLD`: results above → `grounded`; none → `no_source`; empty corpus (no candidate chunks) → `no_documents`.
3. **Ranking + tie-break** — order `(score desc, document_id, chunk_index)`; assign `rank`.
4. **Source assembly** — join chunk → document for title + type; build snippet (bounded slice of `chunk_text`).
5. **Persistence** — write `RagQuery` + `RagRetrievalResult` rows; link to `message_id` when provided.
6. **Determinism test** — repeat query → identical ordering (AC-17).

---

## API Tasks

| Endpoint | Method | Role | Purpose |
|----------|--------|------|---------|
| `/api/documents/{document_id}/process` | POST | manager | Chunk + embed + store; set status `processed`/`failed` |
| `/api/documents/{document_id}/chunks` | GET | manager, staff | List a document's chunks (tenant-scoped) |
| `/api/rag/query` | POST | manager, staff | Retrieve tenant-scoped sources for a query (optionally link a message) |
| `/api/messages/{message_id}/rag-results` | GET | manager, staff | Fetch stored RAG results for a message |

- All resolve tenant first (404/403) per SR-05; `tenant_id` from JWT only.
- Pydantic validation (non-empty query, valid top-k/threshold).
- Consistent `error_code` payloads (see contracts).

---

## Frontend Integration Tasks

1. **`api/rag.ts`** — typed client: `processDocument(id)`, `listChunks(id)`, `ragQuery(payload)`, `getMessageRagResults(messageId)`.
2. **`types/rag.ts`** — `RetrievalStatus`, `RagSource`, `RagQueryResult`, `DocumentChunk` TS types.
3. **Detail integration (Spec 005)** — replace the "Knowledge Sources" placeholder with a real `KnowledgeSourcesPanel`: lists sources (title, type badge, snippet, score), shows `no_source`/`no_documents`/`not-retrieved` states.
4. **`components/rag/SourceCard.tsx`** — one source: document title + type badge + snippet + score bar.
5. **Documents page (Spec 008) hook** — add a "Process" action + chunk-count/status indicator for managers (manager-only).
6. **States** — processing in-progress, processed (chunk count), failed; retrieval grounded/no_source/no_documents/failed.

---

## Testing Tasks

**Backend integration** — `tests/integration/test_rag.py`:
- Process creates chunks + sets status (AC-01, AC-02); re-process replaces (AC-03); disabled excluded (AC-04)
- Query returns ordered tenant sources (AC-05); tenant isolation A vs B (AC-06)
- Demo queries: EW deposit/cancellation (AC-07); RE refund (AC-08)
- `no_source` (AC-09); `no_documents` (AC-10)
- Results persisted + fetchable (AC-11); message rag-results tenant-scoped (AC-12); chunks endpoint tenant-scoped (AC-13)
- Platform Admin 403 (AC-14); staff cannot process / can query+view (AC-15)
- No reply generation/sending (AC-16); determinism (AC-17)

**Unit** — `tests/unit/test_chunker.py` (size/overlap/order/short-long), `tests/unit/test_retriever.py` (threshold→status, tie-break ordering, tenant-filter present), `tests/unit/test_embedder.py` (determinism, dim, unavailable).

**Frontend** — render tests: Knowledge Sources panel for grounded vs no_source; source card fields (AC-18).

**Evaluation** — `tests/eval/test_rag_eval.py`: a small labelled set (the demo policies + expected sources per query) measuring retrieval precision@k and confirming the refuse path triggers on off-topic queries.

---

## Build Order

1. **DB + pgvector** — migration: enable extension; create `document_chunks`, `rag_queries`, `rag_retrieval_results`; models.
2. **Chunker** — `rag/chunker.py` + unit tests (pure, build first).
3. **Embedder** — `rag/embedder.py` + unit tests (deterministic local model, dim, failure).
4. **Retriever** — `rag/retriever.py` + unit tests (tenant filter mandatory, threshold→status, tie-break).
5. **Service** — `rag_service` (process / query / list_chunks / message results) with tenant + role + idempotent replace.
6. **API** — four endpoints + router mount + error mapping; integration tests.
7. **Detail surfacing** — wire message RAG results into the Spec 005 detail panel.
8. **Frontend** — types + API client → KnowledgeSourcesPanel + SourceCard → Documents "Process" action → states.
9. **Validation + eval** — run the two-tenant quickstart (upload → process → query T1 → isolation → query T2 → isolation → unsupported → refuse); run the eval set; confirm all 18 ACs.

---

## Constitution Check

Constitution file is a blank template. No governance gates apply. Proceeding.

---

## Project Structure

### Documentation (this feature)

```
specs/009-rag-over-tenant-documents/
├── plan.md
├── research.md
├── data-model.md
├── quickstart.md
├── contracts/
│   └── api-contracts.md
├── checklists/
│   └── requirements.md
└── tasks.md            # Phase 2 output (created by /speckit-tasks)
```

### Source Code Layout

New files:

```
backend/
├── app/
│   ├── api/v1/
│   │   └── rag.py                       # 4 endpoints
│   ├── services/
│   │   └── rag_service.py               # process / query / list_chunks / message results
│   ├── rag/
│   │   ├── chunker.py                   # bounded overlapping splitter (pure)
│   │   ├── embedder.py                  # Embedder interface + local deterministic model
│   │   └── retriever.py                 # tenant-filtered pgvector search + threshold + ranking
│   ├── models/
│   │   ├── document_chunk.py            # DocumentChunk (pgvector embedding)
│   │   └── rag.py                       # RagQuery, RagRetrievalResult
│   └── schemas/
│       └── rag.py                       # Pydantic + RetrievalStatus enum
├── alembic/versions/
│   └── 00xx_create_rag_tables.py        # enable pgvector + 3 tables + indexes
└── tests/
    ├── integration/
    │   └── test_rag.py
    ├── unit/
    │   ├── test_chunker.py
    │   ├── test_embedder.py
    │   └── test_retriever.py
    └── eval/
        └── test_rag_eval.py

frontend/
└── src/
    ├── api/
    │   └── rag.ts
    ├── types/
    │   └── rag.ts
    └── components/rag/
        ├── KnowledgeSourcesPanel.tsx    # replaces Spec 005 "Knowledge Sources" placeholder
        └── SourceCard.tsx
```

Modified files:

```
backend/app/main.py                          # mount RAG router
backend/app/core/config.py                   # RAG_* settings
backend/app/services/conversation_service.py # include message rag-results in detail (or dedicated fetch)
frontend/src/pages/ConversationDetailPage    # render KnowledgeSourcesPanel (replace placeholder)
frontend/src/pages/DocumentsPage (Spec 008)  # add manager "Process" action + status
```

**Structure Decision**: Web application — FastAPI backend + React SPA frontend, matching Specs 001–008. A dedicated `backend/app/rag/` package isolates the pure pipeline pieces (chunker, embedder, retriever) from the service/API/persistence layers, keeping tenant-filtered retrieval the single search path and allowing the embedding model to evolve without touching CRUD or the API.
