# Research: RAG Over Tenant Documents

**Branch**: `009-rag-over-tenant-documents` | **Phase**: 0 — Pre-design research

All technical choices are resolved from the provided stack and prior spec context. No `NEEDS CLARIFICATION` items remain.

---

## Decision 1: pgvector in PostgreSQL (no external vector DB)

**Decision**: Store chunk embeddings in a `vector` column via the `pgvector` extension and run similarity search in PostgreSQL. No external vector database.

**Rationale**:
- The project's stated stack uses PostgreSQL + pgvector — one datastore, one transaction boundary, one place to enforce `tenant_id`.
- Tenant isolation is trivially correct: the same `WHERE tenant_id = :tid` that protects every other table protects vector search. An external store would add a second isolation boundary to get right.
- Chunks + their embeddings + source documents live together, so joins for source metadata (title/type) are local and cheap.

**Alternatives considered**:
- Pinecone/Weaviate/Qdrant: more scale/features but adds infra, network calls, and a separate tenant-isolation surface — unjustified at demo scale. Rejected for MVP.
- In-process FAISS: fast but not multi-tenant-persistent or transactional with the metadata; rejected.

---

## Decision 2: Cosine Similarity + Threshold for the Refuse Path

**Decision**: Use cosine distance (`<=>`) for chunk/query comparison, convert to a similarity score, and apply a configurable `RAG_SCORE_THRESHOLD`. Above threshold → `grounded`; none above → `no_source`; no candidate chunks at all → `no_documents`.

**Rationale**:
- Cosine is the standard, scale-invariant choice for text embeddings.
- The threshold is the safety mechanism that implements "refuse to provide unsupported information" (SR-06, FR-010). Making `no_source` and `no_documents` distinct first-class statuses lets the downstream reply feature behave correctly (refuse vs prompt-to-upload).

**Alternatives considered**:
- Always return top-k regardless of score: would feed weak/irrelevant evidence to the reply feature and break the refuse guarantee. Rejected.
- Inner product / L2: viable, but cosine is the most robust default for normalised text embeddings; chosen for consistency.

**Resolved defaults**:

| Setting | Default | Purpose |
|---------|---------|---------|
| `RAG_TOP_K` | `4` | Max sources returned |
| `RAG_SCORE_THRESHOLD` | `0.25` (cosine similarity) | Below → `no_source` |

> Threshold is tuned against the demo eval set; it is configurable without code changes.

---

## Decision 3: Bounded Overlapping Chunks

**Decision**: Split document content into chunks of `RAG_CHUNK_SIZE` with `RAG_CHUNK_OVERLAP` overlap, preferring paragraph/sentence boundaries, preserving order via `chunk_index`.

**Rationale**:
- Bounded chunks keep each embedding focused; overlap prevents losing context that straddles a boundary (e.g., a refund clause split mid-sentence).
- Order + index allow stable display and deterministic tie-breaking.

**Resolved defaults**:

| Setting | Default | Purpose |
|---------|---------|---------|
| `RAG_CHUNK_SIZE` | `800` chars (~150–200 tokens) | Chunk length cap |
| `RAG_CHUNK_OVERLAP` | `150` chars | Context carry-over |

**Alternatives considered**:
- Whole-document embedding (no chunking): poor recall for long docs; a single vector blurs distinct clauses. Rejected.
- Token-based chunking with a tokenizer: more precise but adds a dependency; char-based with boundary preference is sufficient for MVP business docs.

---

## Decision 4: Single Versioned Embedding Model (deterministic for MVP)

**Decision**: One embedding model/version embeds both chunks and queries into the same space. For MVP it is deterministic at inference (same input → same vector). The model identifier is stored in chunk `metadata` and `rag_queries.embedding_model`.

**Rationale**:
- Chunks and queries must share a space for comparison to be meaningful.
- Determinism makes retrieval reproducible and tests stable (FR-015, AC-17).
- Recording the version makes a future model change well-defined: re-embed on version bump.

**Alternatives considered**:
- Hosted embedding API (OpenAI, etc.): higher quality but adds network dependency, cost, and non-determinism; the abstraction (`Embedder`) lets us swap to it later without touching retrieval. Deferred.
- Mixing models for chunks vs queries: breaks the shared space; forbidden.

---

## Decision 5: Tenant Isolation Is a Single, Unavoidable Code Path

**Decision**: There is exactly one chunk-search function and it **requires** a `tenant_id`, injecting `WHERE tenant_id = :tid AND enabled AND status='processed'`. No code path searches chunks without a tenant filter. Single-resource endpoints resolve the document/message tenant first (404/403, Specs 005–008).

**Rationale**:
- The spec's hardest guarantee (Tenant A never retrieves Tenant B) is enforced structurally, not by discipline — there is no "search all" variant to misuse (SR-02, SR-08).
- pgvector ANN indexes don't break this: the tenant predicate is applied regardless of index usage.

**Alternatives considered**:
- Per-tenant separate tables/schemas: stronger physical isolation but heavy operationally and complicates the shared embedding index; the row-level `tenant_id` filter (already the project's model) is sufficient and consistent.

---

## Decision 6: Idempotent Re-Processing (delete-then-insert)

**Decision**: Processing a document deletes its existing chunks, then inserts fresh ones, in one transaction. Re-processing is idempotent at the document level (replace, never duplicate). A Spec 008 content edit resets the doc to `uploaded`, so stale chunks are excluded from retrieval until re-processed.

**Rationale**:
- Guarantees no stale or duplicate chunks (FR-005, AC-03) — critical because stale embeddings would ground replies in outdated policy.
- Gating retrieval on `status='processed'` + `enabled` means edited-but-unreprocessed docs simply drop out until refreshed (SR-07).

---

## Decision 7: Persist Queries + Results, Link to Messages

**Decision**: Each retrieval persists a `RagQuery` and its `RagRetrievalResult` rows; when a `message_id` is supplied, the query links to it so the detail page can show the message's sources and the future reply feature can read the grounded evidence.

**Rationale**:
- The detail-page display (US3) and the downstream reply feature both need the stored evidence — persisting avoids re-running retrieval and gives a stable record of what grounded a given message.
- Keeping `RagQuery` separate from `RagRetrievalResult` cleanly models one query → many ranked sources and records status + parameters (top-k, threshold, model) for provenance.

**Alternatives considered**:
- Stateless retrieval (compute on every view): simpler but loses provenance and re-runs cost; the reply feature would have no stable evidence record. Rejected.

---

## Decision 8: Retrieval Only — No Generation, No Sending

**Decision**: This feature returns ranked sources + status. It never calls an LLM to synthesise an answer, never summarises sources into prose, and never sends anything. The suggested-reply feature consumes the stored sources later.

**Rationale**:
- Explicit scope boundary. Separating retrieval from generation lets each evolve independently (re-chunk/re-embed/re-rank without touching reply logic) and keeps the refuse guarantee (`no_source`) as a clean contract the reply feature honours.
- AC-16 asserts the absence of any generation/sending.

---

## Decision 9: Role Split — Manager Processes, Both Query/View

**Decision**: Only `manager` triggers document processing; `manager` and `staff` may query and view results; Platform Admin blocked. Per-method `require_role`.

**Rationale**:
- Processing mutates the knowledge base (chunks) and is a curation action — manager-owned, consistent with Spec 008's manager-write model.
- Querying/viewing is read-side and useful to staff handling messages.

---

## Decision 10: Determinism & Tie-Breaking

**Decision**: With a fixed corpus + embedding model + query, results are deterministic. Ordering is `(score desc, document_id, chunk_index)`.

**Rationale**:
- Reproducible retrieval is required for trustworthy display and stable tests (FR-015, AC-17). A total order via the tie-break removes ANN/score-tie nondeterminism in the returned set.

---

## Decision 11: Evaluation Harness for the Demo Corpus

**Decision**: Ship a small eval set: the demo policies (both tenants) + expected source(s) per query, measuring precision@k and verifying the refuse path fires on off-topic queries.

**Rationale**:
- RAG quality and the refuse threshold need to be measurable, not asserted. A tiny labelled set lets the threshold/top-k be tuned and guards against regressions when the embedding model or chunking changes.

**Resolved eval expectations** (illustrative):

| Query | Tenant | Expected top source(s) |
|-------|--------|------------------------|
| "Is the deposit refundable if I cancel?" | Elegant Weddings | Deposit Policy, Cancellation Policy |
| "Is the deposit refundable if I cancel?" | Royal Events | Refund Policy |
| "What's the weather tomorrow?" | either | none → `no_source` |
