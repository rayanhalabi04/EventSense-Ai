# Feature Specification: RAG Over Tenant Documents

**Feature Branch**: `009-rag-over-tenant-documents`

**Created**: 2026-06-06

**Status**: Draft

**Connects to**:
- [Spec 001 — Multi-Tenant Workspace](../001-multi-tenant-workspace/spec.md)
- [Spec 002 — Authentication and Roles](../002-auth-and-roles/spec.md)
- [Spec 003 — WhatsApp-Style Message Simulator](../003-message-simulator/spec.md)
- [Spec 004 — Message Inbox](../004-message-inbox/spec.md)
- [Spec 005 — Message Detail Page](../005-message-detail-page/spec.md)
- [Spec 008 — Document Upload](../008-document-upload/spec.md)

**Input**: User description: "The system should retrieve relevant tenant-specific document content for a client message so the AI can later generate grounded suggested replies. RAG must only retrieve documents belonging to the current tenant. If no relevant source is found, the system must refuse to provide unsupported information."

---

## Goal

Turn a tenant's uploaded business documents (Spec 008) into a searchable knowledge base and, for a given client message or query, retrieve the most relevant document chunks **from that tenant only**, with source metadata and relevance scores. This is the retrieval ("R") half of RAG: it chunks documents, creates embeddings, stores them in a tenant-scoped vector store, and answers queries with grounded evidence. When nothing relevant is found, it returns an explicit "no supported source" result so the downstream reply feature can refuse to invent unsupported information. This feature **prepares evidence** for the later suggested-reply feature — it does **not** generate or send replies. Tenant isolation is absolute: every retrieval is filtered by `tenant_id`, and Tenant A can never retrieve Tenant B content.

---

## Retrieval Status

| Status | Meaning |
|--------|---------|
| `grounded` | At least one chunk scored at/above the relevance threshold; sources returned |
| `no_source` | No chunk met the relevance threshold; no supported source — downstream must refuse to answer from documents |
| `no_documents` | The tenant has no processed/enabled documents to search |
| `failed` | Retrieval errored (embedding/query failure) |

---

## Main Users

| Role | Description |
|------|-------------|
| **Staff** | Views the retrieved sources (title, type, snippet, score) on the message detail page to understand what evidence a future reply would be grounded in. |
| **Manager** | Verifies that retrieval pulls from the tenant's own documents and curates the corpus (via Spec 008) so replies will be well-grounded; may trigger document processing. |
| **System / RAG service** | Chunks documents, creates embeddings, stores chunks in the vector store, retrieves the most relevant chunks for a query, and returns sources. Not a human actor. |

Platform Admin has no access to tenant documents, chunks, or retrieval.

---

## User Stories

### User Story 1 — Process Documents into Searchable Chunks (Priority: P1)

A manager triggers processing of an uploaded document. The system splits the document content into chunks, creates an embedding for each chunk, stores the chunks (with embeddings + metadata) scoped to the tenant, and advances the document status to `processed`. Chunks belong to exactly one tenant via the document.

**Why this priority**: Without chunking + embedding there is nothing to retrieve. This is the indexing step that makes RAG possible; retrieval (US2) depends entirely on it.

**Independent Test**: As an Elegant Weddings manager, upload a "Deposit Policy" (Spec 008) and process it. Verify chunks are created for that document, each with a non-empty `chunk_text`, an `embedding`, a `chunk_index`, and `tenant_id` = Elegant Weddings; verify the document status becomes `processed`. Verify no chunks are created under Royal Events Agency.

**Acceptance Scenarios**:

1. **Given** an `uploaded` (or `processing_pending`) enabled document in the manager's tenant, **When** processing runs, **Then** the content is split into ≥ 1 chunk, each chunk gets an embedding + `chunk_index` + tenant scoping, and the document status becomes `processed`.
2. **Given** processing succeeds, **When** it completes, **Then** each chunk records `document_id`, `tenant_id`, `chunk_text`, `chunk_index`, `embedding`, `metadata`, and `created_at`.
3. **Given** a document is re-processed (content changed → status reset to `uploaded` by Spec 008), **When** processing runs again, **Then** the document's old chunks are removed and replaced with fresh chunks (no stale chunks remain).
4. **Given** processing of a Tenant A document, **When** chunks are stored, **Then** they are scoped to Tenant A and never visible to Tenant B.
5. **Given** a document is disabled (`enabled = false`), **When** processing is attempted, **Then** it is skipped/rejected (disabled documents are excluded from the knowledge base).

---

### User Story 2 — Retrieve Tenant-Scoped Sources for a Query (Priority: P1)

The system accepts a query (a client message or free text) and returns the most relevant chunks **from the current tenant only**, each with source document title, document type, chunk snippet, and a relevance score, ordered by relevance. If nothing is relevant enough, it returns an explicit no-source result.

**Why this priority**: Retrieval is the core deliverable — the evidence that grounds future replies. It is the feature's reason to exist and the part that must enforce tenant isolation.

**Independent Test**: With both tenants' policies processed, query "Is the deposit refundable if I cancel?" as Elegant Weddings — verify only Elegant Weddings deposit/cancellation chunks are returned with scores. Run the same query as Royal Events Agency — verify only Royal Events refund/policy chunks are returned. Confirm neither tenant ever sees the other's chunks.

**Acceptance Scenarios**:

1. **Given** a tenant with processed documents, **When** a query is submitted, **Then** the system returns the top-k most relevant chunks from that tenant only, each with `document_id`, document title, document type, `chunk_text`/snippet, and a relevance `score`, ordered by score descending.
2. **Given** a query, **When** retrieval runs, **Then** the vector search is unconditionally filtered by the session `tenant_id` — chunks from other tenants are never candidates.
3. **Given** no chunk meets the relevance threshold, **When** retrieval completes, **Then** the result `status` is `no_source` with an empty source list (downstream must refuse to answer from documents).
4. **Given** the tenant has no processed/enabled documents, **When** a query is submitted, **Then** the result `status` is `no_documents`.
5. **Given** the same query is asked by Tenant A and Tenant B, **When** both retrievals run, **Then** each returns only its own tenant's sources and the result sets do not overlap.

---

### User Story 3 — View Retrieved Sources on the Message Detail Page (Priority: P2)

A staff planner opens a message and sees the RAG sources retrieved for that message: the source document title, type, a snippet of the matched chunk, and the relevance score. If no source was found, a clear "no supported source" state is shown. This replaces the Spec 005 "Knowledge Sources" placeholder.

**Why this priority**: Surfacing the evidence builds trust — staff and managers can see exactly which tenant documents would ground a reply. Lower than P1 because indexing + retrieval deliver the core capability; the detail-page view consumes it.

**Independent Test**: For a message in Elegant Weddings, run/attach RAG retrieval, open the message detail page, and verify the Knowledge Sources panel lists the retrieved Elegant Weddings sources (title, type, snippet, score). For a message with no relevant source, verify the panel shows the "no supported source" state.

**Acceptance Scenarios**:

1. **Given** a message has RAG results, **When** the detail page renders, **Then** the Knowledge Sources panel shows each source's document title, document type, chunk snippet, and relevance score, ordered by score.
2. **Given** a message's RAG result is `no_source` or `no_documents`, **When** the detail page renders, **Then** the panel shows a clear "no supported source found" message (no fabricated content).
3. **Given** RAG results exist for a message, **When** they are displayed, **Then** every source belongs to the message's tenant (verified by the tenant-scoped retrieval).
4. **Given** RAG has not been run for a message, **When** the detail page renders, **Then** the panel shows a neutral "not retrieved yet" state.

---

### Edge Cases

- **Empty / whitespace query**: rejected with a validation error (nothing to embed).
- **Very long document**: split into many chunks with a bounded chunk size + overlap; all chunks embedded.
- **Very short document** (< one chunk): stored as a single chunk.
- **Query with no good match** (e.g., "what's the weather?"): below threshold → `no_source` (the refuse path).
- **Tenant with zero processed documents**: `no_documents` (distinct from `no_source`).
- **Disabled document**: excluded from retrieval candidates even if previously chunked; re-enabling makes it retrievable again (after processing).
- **Document edited after processing** (Spec 008 resets status to `uploaded`): its old chunks must be considered stale — re-processing replaces them; until re-processed, stale chunks should not be served (gate retrieval on `enabled` + `processed`).
- **Embedding model unavailable**: processing/query fails gracefully → `failed`; no partial/garbage chunks stored.
- **Identical scores / ties**: deterministic secondary ordering (e.g., by `document_id`, `chunk_index`) for stable results.
- **Cross-tenant id guessing**: requesting chunks/results for another tenant's document or message → 404/403; never leaks chunks.
- **Duplicate processing**: re-processing is idempotent at the document level (old chunks replaced, not duplicated).

---

## Requirements

### Functional Requirements

- **FR-001**: The system MUST split an enabled document's content into ordered chunks with a bounded size and overlap.
- **FR-002**: The system MUST create an embedding vector for each chunk and store it in a tenant-scoped vector store.
- **FR-003**: Each chunk MUST record `id`, `tenant_id`, `document_id`, `chunk_text`, `chunk_index`, `embedding`, `metadata`, and `created_at`.
- **FR-004**: Processing MUST set the document status to `processed` on success and `failed` on error (the Spec 008 status field).
- **FR-005**: Re-processing a document MUST remove its existing chunks and replace them (no stale or duplicate chunks).
- **FR-006**: Disabled documents MUST be excluded from processing and from retrieval candidates.
- **FR-007**: The system MUST accept a query and return the top-k most relevant chunks for the **current tenant only**, ordered by relevance score.
- **FR-008**: Every retrieval query MUST be filtered by the session `tenant_id`; cross-tenant chunks MUST never be candidates.
- **FR-009**: Each retrieved source MUST include the source document title, document type, chunk snippet/text, and a relevance score.
- **FR-010**: When no chunk meets the relevance threshold, the system MUST return `no_source` (empty sources) — it MUST NOT fabricate or return unsupported content.
- **FR-011**: When the tenant has no processed/enabled documents, the system MUST return `no_documents`.
- **FR-012**: The system MUST persist RAG results linked to a message so they can be displayed and consumed by the later reply feature.
- **FR-013**: The system MUST expose retrieved sources for a message and surface them on the message detail page.
- **FR-014**: The system MUST NOT generate or send any suggested reply — it only prepares evidence.
- **FR-015**: Retrieval MUST be deterministic for a fixed corpus, embedding model, and query (stable ordering, including tie-breaks).
- **FR-016**: Staff MAY view RAG results; manager MAY trigger document processing and view results; Platform Admin is blocked.

### Key Entities

- **Tenant** (existing, Spec 001): owns documents, chunks, queries, and results; scopes everything.
- **User** (existing, Spec 002): triggers processing (manager) or views results (staff/manager).
- **Document** (existing, Spec 008): the source of content; provides `enabled` + `status`; title + type used as source metadata.
- **DocumentChunk** (new): one embedded slice of a document — `id`, `tenant_id`, `document_id`, `chunk_text`, `chunk_index`, `embedding`, `metadata`, `created_at`.
- **RagQuery** (new): a retrieval request — query text, tenant, optional linked message, top-k, threshold, status, created_at.
- **RagRetrievalResult** (new): one retrieved source for a query — links to chunk + document, snippet, score, rank.
- **RetrievalStatus** (enum): `grounded`, `no_source`, `no_documents`, `failed`.

---

## Inputs

| Input | Source | Description |
|-------|--------|-------------|
| Authenticated session | JWT | Provides `tenant_id` and `role`; never supplied by the client |
| Document to process | `POST /documents/{id}/process` | The uploaded document to chunk + embed |
| Query text | `POST /rag/query` | Client message text or free-text query to retrieve against |
| Linked message (optional) | `POST /rag/query` | A `message_id` to associate the retrieval with (for detail-page display) |
| top-k / threshold | Query params / config | Number of chunks to return; minimum relevance score |
| Message id | `GET /messages/{id}/rag-results` | The message whose stored RAG results to fetch |

---

## Outputs

| Output | Description |
|--------|-------------|
| Document chunks | Stored, embedded, tenant-scoped chunks for a processed document |
| Retrieval result | Ranked list of sources (title, type, snippet, score) for a query, tenant-scoped |
| Retrieval status | `grounded` / `no_source` / `no_documents` / `failed` |
| Stored RAG results | Results linked to a message for detail-page display + future reply grounding |
| Knowledge Sources panel | Detail-page display of retrieved sources (replaces Spec 005 placeholder) |
| 403 / 404 | Cross-tenant / platform-admin / missing document or message |
| 422 | Invalid/empty query or invalid parameters |

---

## Main Workflow

1. **Manager uploads documents** (Spec 008) for their tenant.
2. **Manager processes a document** — `POST /documents/{id}/process`: content is chunked, each chunk embedded, chunks stored tenant-scoped, document status → `processed`.
3. **A query is made** — `POST /rag/query` with the client message text (and optionally a `message_id`); the session `tenant_id` scopes the search.
4. **Tenant-scoped vector search** — the query is embedded and compared only against the current tenant's enabled+processed chunks; the top-k above threshold are selected.
5. **Sources returned** — ranked sources (title, type, snippet, score) with status `grounded`; or `no_source` / `no_documents` when appropriate.
6. **Results persisted + surfaced** — results are linked to the message and shown in the detail page's Knowledge Sources panel.
7. **Handoff to reply feature** — the stored grounded sources are the evidence the future suggested-reply feature will use. This feature generates no reply.

---

## Alternative Workflows

### No Relevant Source (Refuse Path)

1. A query has no chunk above the relevance threshold.
2. Retrieval returns `status = no_source`, empty sources.
3. The detail page shows "No supported source found."
4. The future reply feature, seeing `no_source`, must refuse to answer from documents (no fabrication).

### Tenant Has No Documents

1. A query is made in a tenant with zero processed/enabled documents.
2. Retrieval returns `status = no_documents`.
3. The detail page prompts the manager to upload/process documents.

### Re-Processing After a Content Edit

1. A manager edits a processed document (Spec 008 resets status to `uploaded`).
2. Until re-processed, its stale chunks are excluded from retrieval (gate on `enabled` + `processed`).
3. The manager re-processes; old chunks are deleted and replaced with fresh ones.

### Cross-Tenant Retrieval Attempt

1. An Elegant Weddings session queries; the search is filtered to Elegant Weddings chunks only.
2. Even if a Royal Events `document_id`/`message_id` is supplied, the tenant resolution returns 404/403 and no Royal Events chunk is ever a candidate.
3. No cross-tenant content is returned.

### Embedding/Model Failure

1. The embedding model is unavailable during processing or query.
2. Processing sets the document status `failed`; a query returns `status = failed`.
3. No partial/garbage chunks are stored; the operation can be retried.

---

## Acceptance Criteria

| # | Criterion | Verification Method |
|---|-----------|---------------------|
| AC-01 | Processing a document creates ≥1 tenant-scoped chunk with text, index, embedding, metadata, created_at | Integration test: process → assert chunk fields |
| AC-02 | Processing sets document status `processed` (and `failed` on error) | Integration test: assert status transitions |
| AC-03 | Re-processing replaces old chunks (no stale/duplicates) | Integration test: process twice → assert chunk set replaced |
| AC-04 | Disabled documents are excluded from processing and retrieval | Integration test: disable → process skipped; not a retrieval candidate |
| AC-05 | A query returns top-k tenant chunks ordered by score with source metadata | Integration test: assert ordered sources + title/type/snippet/score |
| AC-06 | Retrieval is always tenant-filtered; cross-tenant chunks never returned | Integration test: A vs B same query → disjoint, own-tenant only |
| AC-07 | Elegant Weddings "deposit refundable?" returns only Elegant Weddings deposit/cancellation sources | Integration test (demo): assert source titles ∈ EW docs |
| AC-08 | Royal Events same query returns only Royal Events refund/policy sources | Integration test (demo): assert source titles ∈ RE docs |
| AC-09 | No relevant match → `no_source` with empty sources (no fabrication) | Integration test: off-topic query → status no_source, sources=[] |
| AC-10 | Tenant with no processed docs → `no_documents` | Integration test: empty corpus → status no_documents |
| AC-11 | RAG results are persisted linked to a message and fetchable | Integration test: query with message_id → GET rag-results returns them |
| AC-12 | `GET /messages/{id}/rag-results` is tenant-scoped (cross-tenant → 404/403) | Integration test: other-tenant message → 404/403 |
| AC-13 | `GET /documents/{id}/chunks` returns only that in-tenant document's chunks | Integration test: assert chunks; cross-tenant → 403 |
| AC-14 | Platform Admin blocked from all RAG endpoints (403) | Integration test: admin token → 403 INSUFFICIENT_ROLE |
| AC-15 | Staff can query/view results; only manager can trigger processing | Integration test: staff process → 403; staff query/view → 200 |
| AC-16 | The feature generates no suggested reply and sends nothing | Code/integration test: assert no reply generation/sending |
| AC-17 | Retrieval is deterministic (stable order incl. tie-breaks) for a fixed corpus + query | Integration test: repeat query → identical ordering |
| AC-18 | Detail page Knowledge Sources panel shows sources or the no-source state | Frontend test: assert panel rendering for both cases |

---

## Dependencies

| Dependency | Type | Notes |
|------------|------|-------|
| Spec 001 — Multi-Tenant Workspace | Required | Tenants, `tenant_id` isolation, cross-tenant blocking |
| Spec 002 — Authentication and Roles | Required | JWT auth; `manager` (process) + `staff` (view) roles; Platform Admin blocked |
| Spec 003 — Message Simulator | Required | Provides messages that queries can be linked to |
| Spec 004 — Message Inbox | Required (light) | Entry point to the message; not modified here |
| Spec 005 — Message Detail Page | Required | Surface for the Knowledge Sources panel (replaces the placeholder) |
| Spec 008 — Document Upload | Required | Source documents, `enabled` flag, `status` field that this feature advances to `processed`/`failed` |
| pgvector | Required | Vector column + similarity search in PostgreSQL |
| Embedding model | Required | Produces chunk + query embeddings (local/deterministic for MVP) |

---

## AI / RAG Behavior

- **Chunking**: documents are split into bounded, overlapping chunks (size + overlap configurable) so semantically coherent passages can be retrieved with surrounding context.
- **Embeddings**: each chunk and each query is embedded into the same vector space with a single, versioned embedding model. The model is deterministic at inference for MVP (same input → same vector).
- **Vector store**: embeddings are stored in pgvector; similarity search (cosine/inner-product) returns nearest chunks. The search query **always** carries `WHERE tenant_id = :tenant_id` (and `enabled = true`, document `status = processed`).
- **Relevance threshold**: a configurable minimum score gates "grounded" vs "no_source". Below threshold → refuse (no fabrication). This is the safety mechanism that prevents unsupported answers.
- **Top-k**: a configurable number of sources is returned, ordered by score, with deterministic tie-breaking.
- **No generation**: this feature retrieves and ranks evidence only. It does **not** call an LLM to write a reply, does not summarise into an answer, and never sends anything. The suggested-reply feature consumes these sources later.
- **Grounding contract**: the output is the evidence (sources + scores + status). `no_source`/`no_documents` are first-class outcomes that the downstream reply feature must honour by refusing to answer from documents.
- **Versioning**: chunks record the embedding model/version (in metadata) so re-embedding on a model change is well-defined.

---

## Security Rules

| Rule | Description |
|------|-------------|
| **SR-01: Tenant context from session only** | `tenant_id` is always derived from the JWT. No client-supplied tenant is accepted for processing or retrieval. |
| **SR-02: Tenant-scoped retrieval (non-negotiable)** | Every vector search includes `WHERE tenant_id = :tenant_id`. Retrieval without a tenant filter is forbidden — there is no code path that searches across tenants. |
| **SR-03: Chunk tenancy** | Each `DocumentChunk` inherits and stores the `tenant_id` of its document. Tenant A can never read Tenant B chunks, results, or sources. |
| **SR-04: Role restriction** | Only `manager` may trigger processing. `manager` and `staff` may query and view results. Platform Admin → 403. Unauthenticated → 401. |
| **SR-05: Not Found vs Forbidden** | A document/message not in the caller's tenant → 404; one in another tenant → 403 (consistent with Specs 005–008). Endpoints never confirm cross-tenant content. |
| **SR-06: No unsupported answers** | When no source meets the threshold, the system returns `no_source` and never fabricates content — the refuse path is mandatory. |
| **SR-07: Disabled/unprocessed exclusion** | Disabled or non-`processed` documents are never retrieval candidates, preventing stale or withdrawn content from grounding replies. |
| **SR-08: No cross-tenant embedding leakage** | Query embeddings are compared only within the tenant partition; one tenant's vectors are never used to answer another tenant's query. |

---

## Failure Cases

| Failure | System behavior |
|---------|-----------------|
| Empty/whitespace query | 422 validation error; nothing embedded |
| Embedding model unavailable (processing) | Document status `failed`; no chunks stored; retry allowed |
| Embedding model unavailable (query) | Retrieval `status = failed`; no partial results |
| Query in tenant with no processed docs | `status = no_documents` |
| Query with no match above threshold | `status = no_source`, empty sources |
| Process a disabled document | Skipped/rejected (422 `DOCUMENT_DISABLED`) |
| Process a non-existent / cross-tenant document | 404 / 403 per SR-05 |
| `GET chunks`/`rag-results` cross-tenant | 404 / 403; no chunk/source leaked |
| Staff triggers processing | 403 `INSUFFICIENT_ROLE` |
| Platform Admin calls any endpoint | 403 `INSUFFICIENT_ROLE` |
| Re-processing mid-retrieval | Old chunks replaced atomically; retrieval sees a consistent set |

---

## Edge Cases (summary)

- Empty query → 422.
- Long doc → many chunks (size + overlap); short doc → single chunk.
- Off-topic query → `no_source` (refuse).
- Zero processed docs → `no_documents`.
- Disabled/edited-but-unprocessed docs → excluded from candidates.
- Model unavailable → `failed`, no garbage stored.
- Score ties → deterministic secondary ordering.
- Cross-tenant id guessing → 404/403, never leaks.
- Re-processing → idempotent (replace, not duplicate).

---

## Out of Scope

- **Suggested reply generation** — separate, later feature; this feature only prepares evidence.
- **Auto-sending replies** — never; nothing is sent.
- **LLM answer synthesis / summarisation of sources into prose** — out of scope; only ranked sources are returned.
- **Cross-tenant or global knowledge bases** — explicitly forbidden.
- **Re-ranking models / hybrid BM25+vector** — out of scope for MVP (pure vector similarity + threshold); a future enhancement.
- **Streaming/real-time re-indexing on every edit** — processing is an explicit action; the status field gates staleness.
- **Document upload/CRUD** — owned by Spec 008; not re-implemented here.
- **Audit logging** — added by the later audit-log feature; RAG events are logged there, not here.
- **External vector databases** (Pinecone, etc.) — pgvector only for MVP.
- **Real WhatsApp API, calendar syncing, full CRM** — out of scope entirely.

---

## Assumptions

- Retrieval operates only over documents from Spec 008 that are `enabled = true` and `status = processed`.
- Chunks store the embedding vector in a pgvector column; similarity is cosine (or inner product) with a configurable threshold + top-k.
- A single embedding model/version is used for both chunks and queries; its identifier is recorded in chunk metadata for re-embedding on change.
- Processing is an explicit manager-triggered action (synchronous for MVP, wrapped so failure sets `failed` without corrupting data); a background queue is a post-MVP optimisation.
- RAG results are persisted per query and, when a `message_id` is supplied, linked to that message for detail-page display and future reply grounding.
- The relevance threshold and top-k have documented defaults and are configurable.
- The detail page's "Knowledge Sources" placeholder from Spec 005 is replaced by the real sources display in this feature; remaining placeholders (Suggested Reply, Create Task, Escalate) stay placeholders.
- Determinism assumes a fixed corpus + embedding model; tie-breaks use `(score desc, document_id, chunk_index)`.

---

## Advanced Requirements Update (Updated Brief — 2026-06)

The updated brief requires at least one **advanced retrieval improvement beyond basic dense (single-vector cosine) retrieval**. EventSense AI adopts **two**: tenant- and document-aware **metadata filtering** and **improved, structure-aware chunking**. Storage stays pgvector; tenant-scoped retrieval, source grounding, and the `no_source` refuse path are unchanged.

### Functional Requirements (additional)

- **FR-017**: Retrieval MUST support **metadata filtering** alongside vector similarity: candidates may be narrowed by structured chunk/document metadata (`document_type`, `enabled`, `status = processed`, optional tags such as `pricing`/`policy`/`availability`) **with** the tenant filter, so similarity search runs over the relevant, allowed subset only. The `tenant_id` filter remains mandatory and non-bypassable.
- **FR-018**: Chunking MUST use an **improved, structure-aware strategy** (sentence/section-boundary-aware splitting with bounded size + overlap, avoiding mid-sentence cuts) rather than naive fixed-character slicing, and MUST persist chunk metadata (section/heading, `document_type`) used by FR-017.
- **FR-019**: Each retrieved source MUST carry the metadata used for filtering so the detail page and downstream grounding can show *why* a source matched; metadata MUST never include another tenant's data.
- **FR-020**: The advanced retrieval path MUST remain **deterministic** for a fixed corpus + embedding model + query + filter set (stable ordering incl. tie-breaks), preserving existing AC-17.

### Acceptance Criteria (additional)

| # | Criterion | Verification Method |
|---|-----------|---------------------|
| AC-19 | Metadata filtering narrows candidates (e.g., `document_type=policy`) while still tenant-scoped; off-type chunks excluded | Integration test |
| AC-20 | Structure-aware chunking yields boundary-aligned chunks with persisted section/type metadata (no mid-sentence splits beyond overlap) | Unit test on the chunker |
| AC-21 | A metadata-filtered query returns only same-tenant, in-filter sources; zero cross-tenant chunks | Integration test |
| AC-22 | Advanced retrieval remains deterministic for a fixed corpus + query + filter | Integration test |

> This supersedes the prior "re-ranking / hybrid BM25+vector — out of scope" note **only** to the extent of adding metadata filtering + improved chunking; learned re-rankers and external vector DBs remain out of scope.
