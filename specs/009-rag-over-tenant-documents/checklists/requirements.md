# Requirements Checklist: RAG Over Tenant Documents

**Purpose**: Validate specification completeness and implementation readiness before/while building the feature
**Created**: 2026-06-06
**Feature**: [spec.md](../spec.md) · [plan.md](../plan.md)

---

## Specification Quality (gate before planning)

- [x] No implementation details leak into the spec's user-facing sections
- [x] Focused on user value (grounded evidence) and the EventSense AI workflow
- [x] All mandatory sections present (Goal, Users, Stories, Inputs, Outputs, Workflow, AC, Dependencies, AI/RAG behavior, Security, Failure/Edge, Out of scope)
- [x] No `[NEEDS CLARIFICATION]` markers remain
- [x] Requirements are testable and unambiguous
- [x] Scope is clearly bounded; out-of-scope items explicitly listed

---

## Functional Requirements

- [ ] Document content is split into ordered chunks with bounded size + overlap (FR-001)
- [ ] Each chunk gets an embedding stored in a tenant-scoped vector store (FR-002)
- [ ] Each chunk records id, tenant_id, document_id, chunk_text, chunk_index, embedding, metadata, created_at (FR-003)
- [ ] Processing sets document status `processed` on success, `failed` on error (FR-004)
- [ ] Re-processing replaces old chunks (no stale/duplicate) (FR-005, AC-03)
- [ ] Disabled documents excluded from processing and retrieval (FR-006, AC-04)
- [ ] Query returns top-k most relevant chunks for the current tenant, ordered by score (FR-007, AC-05)
- [ ] Each retrieved source includes document title, type, snippet, score (FR-009)
- [ ] Results persisted linked to a message and fetchable (FR-012, AC-11)
- [ ] Retrieved sources surfaced on the message detail page (FR-013, AC-18)
- [ ] No suggested reply generated or sent (FR-014, AC-16)
- [ ] Staff may view; manager may process; Platform Admin blocked (FR-016, AC-14, AC-15)

---

## RAG Requirements

- [ ] Chunking uses configurable size + overlap, preserves order via chunk_index
- [ ] Single versioned embedding model embeds both chunks and queries (same space)
- [ ] Embedding model/version recorded in chunk metadata + rag_queries
- [ ] Similarity uses cosine distance; distance converted to a similarity score
- [ ] Configurable relevance threshold gates grounded vs no_source
- [ ] Below threshold → `no_source` with empty sources (refuse path, no fabrication) (FR-010, AC-09)
- [ ] Tenant with no processed/enabled docs → `no_documents` (FR-011, AC-10)
- [ ] Top-k configurable; sources ordered by score
- [ ] Retrieval is deterministic for fixed corpus + model + query; tie-break `(score, document_id, chunk_index)` (FR-015, AC-17)
- [ ] Embedding/model failure → `failed`; no partial/garbage chunks stored
- [ ] No LLM answer synthesis/summarisation; ranked sources only

---

## Tenant Isolation Requirements

- [ ] Every vector search includes `WHERE tenant_id = :tenant_id` (SR-02)
- [ ] There is no code path that searches chunks without a tenant filter (SR-02, SR-08)
- [ ] Each DocumentChunk inherits + stores its document's tenant_id (SR-03)
- [ ] Tenant A query returns only Tenant A sources; Tenant B only Tenant B (AC-06)
- [ ] Demo: EW "deposit refundable?" → EW deposit/cancellation only (AC-07)
- [ ] Demo: RE same query → RE refund policy only (AC-08)
- [ ] Same query by A and B yields disjoint, own-tenant-only results
- [ ] Cross-tenant document_id/message_id → 404/403; no chunk/source leaked (AC-12, AC-13)
- [ ] Query embeddings compared only within the tenant partition (SR-08)
- [ ] No cross-tenant or global knowledge base exists

---

## Security Requirements

- [ ] `tenant_id` always derived from JWT — never from the client (SR-01)
- [ ] Only `manager` may trigger processing; `manager`+`staff` query/view; Platform Admin → 403 (SR-04)
- [ ] Unauthenticated requests → 401
- [ ] Non-existent document/message → 404; cross-tenant → 403 (SR-05)
- [ ] No unsupported answers: below threshold → refuse (`no_source`) (SR-06, AC-09)
- [ ] Disabled / non-`processed` documents never retrieval candidates (SR-07)
- [ ] Embedding vectors are not serialised to clients (chunks endpoint omits them)

---

## API Requirements

- [ ] `POST /api/documents/{id}/process` chunks+embeds+stores, sets status; manager only (AC-01, AC-02)
- [ ] Process rejects disabled doc (422 DOCUMENT_DISABLED); model down → 503 + status failed
- [ ] `GET /api/documents/{id}/chunks` lists tenant chunks (no vectors); cross-tenant → 403 (AC-13)
- [ ] `POST /api/rag/query` returns grounded/no_source/no_documents (200) with sources/status (AC-05, AC-09, AC-10)
- [ ] Query validates non-empty query, top_k 1–20, threshold 0–1 (422 otherwise)
- [ ] Query with cross-tenant message_id → 404/403
- [ ] `GET /api/messages/{id}/rag-results` returns stored results; tenant-scoped (AC-11, AC-12)
- [ ] Role matrix enforced per endpoint; Platform Admin 403 everywhere (AC-14)
- [ ] Error responses use consistent `error_code` values per the contract
- [ ] `no_source`/`no_documents` are 200 outcomes, not errors

---

## Data Requirements

- [ ] pgvector extension enabled via migration
- [ ] `document_chunks` table with `embedding vector(dim)` + tenant_id/document_id FKs
- [ ] UNIQUE `(document_id, chunk_index)`; index `(tenant_id, document_id)`; ANN index on embedding
- [ ] `rag_queries` table: tenant_id, message_id (nullable), query_text, top_k, threshold, status, embedding_model, created_at
- [ ] `rag_retrieval_results` table: rag_query_id, tenant_id, document_id, chunk_id, snippet, score, rank
- [ ] `RetrievalStatus` enum: grounded, no_source, no_documents, failed
- [ ] Chunk metadata records embedding model/version + char span + source title/type
- [ ] Re-processing deletes prior chunks then inserts (transactional, idempotent)
- [ ] Embedding dimension validated == configured dim before insert

---

## Testing Requirements

- [ ] Unit: chunker (size/overlap/order, short/long, determinism)
- [ ] Unit: embedder (determinism, dimension, unavailable)
- [ ] Unit: retriever (tenant filter always present, threshold→status, tie-break ordering)
- [ ] Integration: process creates chunks + status (AC-01, AC-02); re-process replaces (AC-03); disabled excluded (AC-04)
- [ ] Integration: query ordered tenant sources (AC-05); isolation A vs B (AC-06)
- [ ] Integration: demo EW (AC-07) and RE (AC-08) queries
- [ ] Integration: no_source (AC-09); no_documents (AC-10)
- [ ] Integration: results persisted/fetchable (AC-11); message + chunks tenant-scoped (AC-12, AC-13)
- [ ] Integration: Platform Admin 403 (AC-14); staff can't process / can query+view (AC-15)
- [ ] Integration: no reply generation/sending (AC-16); determinism (AC-17)
- [ ] Frontend: Knowledge Sources panel grounded vs no_source (AC-18)

---

## Evaluation Requirements

- [ ] A labelled eval set exists: demo policies (both tenants) + expected source(s) per query
- [ ] Precision@k measured on the demo corpus (relevant source ranked in top-k)
- [ ] Refuse-path verified: off-topic queries produce `no_source`
- [ ] Tenant-isolation verified in eval: each tenant's query retrieves only its own sources
- [ ] Threshold + top-k tuned against the eval set; defaults documented in research
- [ ] Eval is repeatable (deterministic embedding model) and guards against regressions on model/chunking changes

---

## Out-of-Scope Confirmation (must remain unbuilt in this feature)

- [ ] No suggested reply generation
- [ ] No auto-sending of any reply
- [ ] No LLM answer synthesis / summarisation of sources into prose
- [ ] No cross-tenant or global knowledge base
- [ ] No re-ranking model / hybrid BM25+vector (pure vector + threshold for MVP)
- [ ] No document upload/CRUD (owned by Spec 008)
- [ ] No audit-log system (RAG events logged by the later audit feature)
- [ ] No external vector database (pgvector only)
- [ ] No real WhatsApp API, no calendar syncing, no full CRM

---

## Notes

- Spec quality items are checked (`x`) — the spec is ready for `/speckit-tasks`.
- Implementation items are left unchecked (`[ ]`) for the build phase to tick off.
- Build order is defined in [plan.md](../plan.md#build-order); build chunker → embedder → retriever (pure, unit-tested) before the service/API.
- The single tenant-filtered retriever is the linchpin of isolation — verify SR-02 has no bypass.
