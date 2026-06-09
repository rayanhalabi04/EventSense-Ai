---
description: "Task list for RAG Over Tenant Documents feature implementation"
---

# Tasks: RAG Over Tenant Documents

**Branch**: `009-rag-over-tenant-documents` | **Date**: 2026-06-08 | **Spec**: [spec.md](./spec.md) | **Plan**: [plan.md](./plan.md)

**Input**: Design documents from `specs/009-rag-over-tenant-documents/` (spec.md, plan.md, research.md, data-model.md, contracts/api-contracts.md, quickstart.md, checklists/requirements.md)

**Depends on** (assumed complete — do not re-implement):
- Spec 001 — Multi-Tenant Workspace: `tenants` table, `tenant_id` isolation, cross-tenant 403 contract, `NotFoundError`/`ForbiddenError` → HTTP mapping, `TenantScopedRepository`, `get_current_tenant_context`
- Spec 002 — Authentication and Roles: JWT auth; `staff`/`manager`/`platform_admin` roles; `require_role`; Platform Admin block; `users` table; consistent `error_code` payload shape
- Spec 003 — Message Simulator: `messages` table; provides messages a `RagQuery` can link to
- Spec 005 — Message Detail Page: conversation/message detail page with the "Knowledge Sources" placeholder this feature replaces
- Spec 008 — Document Upload: `documents` table with `content`, `title`, `document_type`, `enabled`, `status` (`DocumentStatus`: `uploaded`/`processing_pending`/`processed`/`failed`); this feature advances `status` → `processed`/`failed`

**Tech stack**: FastAPI + SQLAlchemy 2.x async + Alembic + pydantic v2 + pgvector (backend) · React 18 + TypeScript + react-router-dom v6 + Vite + Tailwind + shadcn/ui (frontend)

**New schema**: enable the `pgvector` extension + three tables (`document_chunks`, `rag_queries`, `rag_retrieval_results`) in one Alembic migration. `RetrievalStatus` persisted as a constrained string (VARCHAR + app-boundary validation), not a native PG enum (consistent with Spec 008).

**Config defaults** (research.md Decisions 2 & 3): `RAG_CHUNK_SIZE=800`, `RAG_CHUNK_OVERLAP=150`, `RAG_TOP_K=4`, `RAG_SCORE_THRESHOLD=0.25`, `RAG_EMBEDDING_MODEL="local-minilm-v1"`, `RAG_EMBEDDING_DIM` (sized to the local model).

## Format: `[ID] [P?] [Story?] Description`

- **[P]**: Can run in parallel (different files, no blocking dependency on in-progress tasks)
- **[Story]**: Which user story this task belongs to (`[US1]`–`[US3]`)
- File paths are exact targets from plan.md

---

## Phase 1: Setup & Spec Alignment

**Purpose**: Confirm reused 001–008 dependencies, add config, and confirm test infrastructure. No feature code yet.

- [ ] T001 Confirm reused dependencies exist and record import paths: `Tenant` model + `tenants` table (Spec 001), `User` model + role enum (Spec 002), `require_role` + `get_current_tenant_context` (Spec 002), `Message` model + `messages` table (Spec 003), `Document` model + `DocumentStatus` enum + `documents` table (Spec 008), `NotFoundError`/`ForbiddenError` (Spec 001) and their error→HTTP mapping, and the shared `error_code` response envelope. Do NOT redefine any of these.
- [ ] T002 Add `RAG_CHUNK_SIZE` (800), `RAG_CHUNK_OVERLAP` (150), `RAG_TOP_K` (4), `RAG_SCORE_THRESHOLD` (0.25), `RAG_EMBEDDING_MODEL` (`"local-minilm-v1"`), and `RAG_EMBEDDING_DIM` (the local model's vector dimension) to `backend/app/core/config.py` with documented defaults (research.md Decisions 2 & 3)
- [ ] T003 Add the `pgvector` Python package to backend dependencies (e.g. `pyproject.toml`/`requirements.txt`) and confirm `pgvector` is installable in the PostgreSQL instance used by dev + CI/test (the test DB must support `CREATE EXTENSION vector`)
- [ ] T004 Verify `backend/tests/unit/`, `backend/tests/integration/`, and `backend/tests/eval/` exist with `__init__.py`; create the missing ones (the `eval/` dir is new for this feature)

**Checkpoint**: Dependencies confirmed reused; config + pgvector dependency in place; test dirs exist.

---

## Phase 2: Database, pgvector & Models (Foundational — Blocking)

**Purpose**: The pgvector extension, three tables, and ORM models underpin every service, endpoint, and test. **BLOCKS all user stories.**

**⚠️ CRITICAL**: Phases 6–8 cannot run without this phase.

- [ ] T005 [P] Create the `RetrievalStatus` string enum (`grounded`, `no_source`, `no_documents`, `failed`) in `backend/app/schemas/rag.py` (shared by service + API layers) — per data-model.md
- [ ] T006 [P] Create the `DocumentChunk` SQLAlchemy model in `backend/app/models/document_chunk.py`: `id` UUID PK; `tenant_id` UUID FK→`tenants.id` NOT NULL indexed; `document_id` UUID FK→`documents.id` `ON DELETE CASCADE` NOT NULL indexed; `chunk_text` TEXT NOT NULL; `chunk_index` Integer NOT NULL; `embedding` `pgvector.sqlalchemy.Vector(settings.RAG_EMBEDDING_DIM)` NOT NULL; `metadata_` JSONB (mapped to column `metadata`) NOT NULL default `{}`; `created_at` TIMESTAMPTZ server_default now; `document` relationship; `UniqueConstraint("document_id", "chunk_index", name="uq_chunk_doc_index")`; `Index("ix_chunk_tenant_document", "tenant_id", "document_id")` — per data-model.md
- [ ] T007 [P] Create the `RagQuery` SQLAlchemy model in `backend/app/models/rag.py`: `id` UUID PK; `tenant_id` UUID FK→`tenants.id` NOT NULL indexed; `message_id` UUID FK→`messages.id` NULLABLE indexed; `query_text` TEXT NOT NULL; `top_k` Integer NOT NULL; `threshold` DOUBLE PRECISION NOT NULL; `status` VARCHAR(20) NOT NULL; `embedding_model` VARCHAR(64) NOT NULL; `created_at` TIMESTAMPTZ server_default now; `Index("ix_ragquery_tenant_message", "tenant_id", "message_id")`; relationship to `results` — per data-model.md
- [ ] T008 [P] Create the `RagRetrievalResult` SQLAlchemy model in `backend/app/models/rag.py`: `id` UUID PK; `rag_query_id` UUID FK→`rag_queries.id` `ON DELETE CASCADE` NOT NULL; `tenant_id` UUID FK→`tenants.id` NOT NULL; `document_id` UUID FK→`documents.id` NOT NULL; `chunk_id` UUID FK→`document_chunks.id` NOT NULL; `snippet` TEXT NOT NULL; `score` DOUBLE PRECISION NOT NULL; `rank` Integer NOT NULL; `created_at` TIMESTAMPTZ server_default now; `Index("ix_ragresult_query_rank", "rag_query_id", "rank")` — per data-model.md (depends on T007)
- [ ] T009 Create Alembic migration `backend/alembic/versions/00xx_create_rag_tables.py`: (1) `op.execute("CREATE EXTENSION IF NOT EXISTS vector")`; (2) create `document_chunks`, `rag_queries`, `rag_retrieval_results` with all columns, FKs, defaults, the `embedding vector(RAG_EMBEDDING_DIM)` column, the `UNIQUE(document_id, chunk_index)` constraint, and the `(tenant_id, document_id)`, `(tenant_id, message_id)`, `(rag_query_id, rank)` composite indexes; (3) a pgvector ANN index on `document_chunks.embedding` using cosine ops (e.g. `ivfflat (embedding vector_cosine_ops)`); provide a correct `downgrade()` dropping the three tables + indexes (the extension may be left in place). Depends on T005–T008

**Checkpoint**: `alembic upgrade head` enables pgvector and creates all three tables + indexes; ORM models importable.

---

## Phase 3: RAG Schemas (Foundational — Blocking)

**Purpose**: Pydantic request/response models shared by the service and endpoints. **Embedding vectors are never serialised to clients.**

- [ ] T010 Add Pydantic models to `backend/app/schemas/rag.py` (alongside `RetrievalStatus` from T005) per data-model.md: `ProcessRequest` (optional `force: bool = False`), `ProcessResponse` (`document_id`, `status`, `chunk_count`, `embedding_model`), `ChunkResponse` (`id`, `document_id`, `chunk_index`, `chunk_text`, `metadata`, `created_at`; `from_attributes=True`; **no `embedding` field**), `ChunkListResponse` (`document_id`, `chunks: list[ChunkResponse]`, `total: int`), `RagQueryRequest` (`query` 1–2000 + `field_validator` stripping/rejecting blank, `message_id: UUID | None = None`, `top_k: int = Field(default=4, ge=1, le=20)`, `threshold: float | None = Field(default=None, ge=0.0, le=1.0)`), `RagSource` (`document_id`, `document_title`, `document_type`, `chunk_id`, `snippet`, `score`, `rank`), `RagQueryResponse` (`status`, `sources: list[RagSource]`, `query_id`, `embedding_model`), `MessageRagResultsResponse` (`message_id`, `status`, `sources`, `query_id: UUID | None`, `created_at: datetime | None`)

**Checkpoint**: Schemas importable — pipeline and service phases can begin.

---

## Phase 4: RAG Pipeline Primitives (Foundational — Blocking, pure + unit-tested)

**Purpose**: The chunker, embedder, and retriever are the pure pipeline pieces. Build and fully unit-test them in isolation before any service/API wiring (plan.md Build Order). The **retriever is the linchpin of tenant isolation** — it has no tenant-less search variant. **BLOCKS US1 + US2.**

### Chunker

- [ ] T011 [P] Implement `chunk_text(content: str, size: int, overlap: int) -> list[str]` in `backend/app/rag/chunker.py`: bounded, overlapping, order-preserving splitter; prefer paragraph/sentence boundaries with a hard `size` cap fallback; content shorter than one chunk → a single chunk; empty/whitespace content → empty list. Pure, no DB/I/O (research.md Decision 3, FR-001)
- [ ] T012 [P] Write `backend/tests/unit/test_chunker.py`: correct chunk count/size for long content; overlap carries `RAG_CHUNK_OVERLAP` chars between consecutive chunks; order preserved; short doc → single chunk; very long doc → many chunks; determinism (same input → identical chunks) (plan.md Testing; FR-001, FR-015) (depends on T011)

### Embedder

- [ ] T013 [P] Implement the `Embedder` abstraction in `backend/app/rag/embedder.py`: `embed(texts: list[str]) -> list[list[float]]` (batched), exposes `model_version: str` (= `RAG_EMBEDDING_MODEL`) and `dim: int` (= `RAG_EMBEDDING_DIM`); a deterministic local model for MVP (same input → same vector, vectors normalised for cosine); raise typed `EmbeddingUnavailable` on model failure. Provide a module-level singleton `embedder` (research.md Decision 4, FR-002)
- [ ] T014 [P] Write `backend/tests/unit/test_embedder.py`: determinism (same text → identical vector across calls); output dimension == `RAG_EMBEDDING_DIM`; batch length == input length; `EmbeddingUnavailable` raised + propagated when the model is forced unavailable (plan.md Testing) (depends on T013)

### Retriever (single tenant-filtered search path — SR-02/SR-08)

- [ ] T015 Implement `search(session, tenant_id, query_vector, top_k, threshold) -> list[tuple[DocumentChunk, float]]` in `backend/app/rag/retriever.py`: a single pgvector query joining `DocumentChunk`→`Document`, with the **mandatory** predicates `DocumentChunk.tenant_id == tenant_id`, `Document.enabled.is_(True)`, `Document.status == DocumentStatus.processed.value`; score = `1 - embedding.cosine_distance(query_vector)`; order by `(score DESC, document_id, chunk_index)`; `limit(top_k)`; return only rows with `score >= threshold`. There is **no** variant of this function without `tenant_id` (SR-02, SR-08, FR-008, FR-015) (depends on T006)
- [ ] T016 Write `backend/tests/unit/test_retriever.py`: the `tenant_id` predicate is always present in the compiled statement (assert isolation cannot be bypassed); threshold gates inclusion (below-threshold rows dropped); tie-break ordering `(score desc, document_id, chunk_index)` is deterministic; `top_k` limit honoured (plan.md Testing; SR-02, FR-015, AC-17) (depends on T015)

**Checkpoint**: Chunker, embedder, retriever are correct and deterministic; all unit tests pass. Tenant filter proven mandatory in the retriever.

---

## Phase 5: RAG Service (Foundational — Blocking)

**Purpose**: Orchestrate process / query / list-chunks / message-results with tenant resolution, role-gated callers, idempotent replace, and the refuse path. **BLOCKS the API in Phase 6.**

- [ ] T017 Define typed errors `DocumentDisabledError` (→422 `DOCUMENT_DISABLED`) and `ModelUnavailableError` (→503 `MODEL_UNAVAILABLE`) in `backend/app/services/rag_service.py` (or the shared errors module); reuse existing `NotFoundError`/`ForbiddenError` from Spec 001 for 404/403 (data-model.md error→HTTP mapping)
- [ ] T018 Implement `_resolve_document_or_raise(session, tenant_id, document_id)` and `_resolve_message_or_raise(session, tenant_id, message_id)` helpers in `backend/app/services/rag_service.py`: load the row, `NotFoundError` (404) if it does not exist, `ForbiddenError` (403) if it exists in another tenant — mirroring Specs 005–008 SR-05 (depends on T017)
- [ ] T019 Implement `_replace_chunks(session, tenant_id, doc, chunks, vectors)` in `backend/app/services/rag_service.py`: validate every vector length == `RAG_EMBEDDING_DIM` (mismatch → fail cleanly, no insert); `DELETE FROM document_chunks WHERE document_id=:id AND tenant_id=:tid`; insert fresh chunks with `chunk_index`, `embedding`, and `metadata` (embedding model/version, char span, source title/type snapshot) — all in one transaction (idempotent replace) (FR-005, research.md Decision 6, plan.md pgvector tasks) (depends on T006, T011, T013)
- [ ] T020 [US1] Implement `process_document(session, tenant_id, document_id, force=False) -> ProcessResponse` in `backend/app/services/rag_service.py`: resolve doc (404/403); reject `enabled == False` → `DocumentDisabledError`; chunk `doc.content` → embed (catch `EmbeddingUnavailable` → set `doc.status = failed`, commit, raise `ModelUnavailableError`) → `_replace_chunks` → set `doc.status = processed` → commit; return `ProcessResponse(document_id, status, chunk_count, embedding_model)` (FR-001..FR-006, AC-01..AC-04) (depends on T018, T019)
- [ ] T021 [US2] Implement `_tenant_has_searchable_chunks(session, tenant_id) -> bool` in `backend/app/services/rag_service.py`: true iff the tenant has ≥1 chunk whose document is `enabled` and `status == processed` (distinguishes `no_documents` from `no_source`) (FR-011, AC-10) (depends on T006)
- [ ] T022 [US2] Implement `_persist_and_return(session, tenant_id, query_text, top_k, threshold, message_id, status, sources)` in `backend/app/services/rag_service.py`: insert a `RagQuery` row (status, params, `embedding_model`, optional `message_id`) + one `RagRetrievalResult` per source (chunk_id, document_id, snippet, score, rank), commit, return `RagQueryResponse` (FR-012, AC-11) (depends on T007, T008)
- [ ] T023 [US2] Implement `query(session, tenant_id, query_text, top_k, threshold=None, message_id=None) -> RagQueryResponse` in `backend/app/services/rag_service.py`: default threshold from config; if `message_id` provided, resolve it (404/403); if `not _tenant_has_searchable_chunks` → persist + return `no_documents`; embed query (catch `EmbeddingUnavailable` → persist + return `failed`); `retriever.search(...)`; `grounded` if hits else `no_source`; build `RagSource`s (join doc title/type, bounded snippet, rank) → persist + return (FR-007..FR-011, AC-05, AC-09, AC-10) (depends on T015, T018, T021, T022)
- [ ] T024 [US2] Implement `build_sources(hits) -> list[RagSource]` in `backend/app/services/rag_service.py`: map each `(chunk, score)` to a `RagSource` with the source document `title`/`document_type`, a bounded `snippet` slice of `chunk_text`, and a 1-based `rank` following the retriever's order (FR-009) (depends on T015)
- [ ] T025 [US3] Implement `list_chunks(session, tenant_id, document_id) -> list[DocumentChunk]` in `backend/app/services/rag_service.py`: resolve doc (404/403); return chunks `WHERE tenant_id AND document_id ORDER BY chunk_index ASC` (AC-13) (depends on T018)
- [ ] T026 [US3] Implement `get_message_rag_results(session, tenant_id, message_id) -> MessageRagResultsResponse` in `backend/app/services/rag_service.py`: resolve message (404/403); fetch the latest `RagQuery` for the message (tenant-scoped) + its ordered results; if none, return `status=no_source, query_id=None, created_at=None` (the UI "not retrieved yet" state) (FR-012, FR-013, AC-11, AC-12) (depends on T018, T022)

**Checkpoint**: Service layer complete; tenant resolution, idempotent replace, refuse path, and persistence all in place.

---

## Phase 6: API Endpoints (User Story 1 + 2 + 3)

**Purpose**: Expose the four endpoints with per-method role guards and error→HTTP mapping. `tenant_id` is always derived from the JWT (`get_current_tenant_context`); any client-supplied tenant is ignored. **🎯 MVP backend deliverable.**

- [ ] T027 [US1] Implement `POST /api/documents/{document_id}/process` in `backend/app/api/v1/rag.py`: `require_role("manager")`; parse optional `ProcessRequest`; call `rag_service.process_document`; return `ProcessResponse` (200). Map `DocumentDisabledError`→422 `DOCUMENT_DISABLED`, `ModelUnavailableError`→503 `MODEL_UNAVAILABLE`, `NotFoundError`→404 `DOCUMENT_NOT_FOUND`, `ForbiddenError`→403 `CROSS_TENANT_FORBIDDEN` (contracts §1) (depends on T020)
- [ ] T028 [US3] Implement `GET /api/documents/{document_id}/chunks` in `backend/app/api/v1/rag.py`: `require_role("manager", "staff")`; call `rag_service.list_chunks`; return `ChunkListResponse` (`{document_id, chunks, total}`) — **embedding vectors omitted**; cross-tenant → 404/403 (contracts §2, AC-13) (depends on T025)
- [ ] T029 [US2] Implement `POST /api/rag/query` in `backend/app/api/v1/rag.py`: `require_role("manager", "staff")`; validate `RagQueryRequest`; call `rag_service.query`; return `RagQueryResponse` (200 for `grounded`/`no_source`/`no_documents` — the refuse path is **not** an error); 422 on empty query / bad `top_k`/`threshold`; cross-tenant `message_id` → 404/403 (contracts §3, AC-05, AC-09, AC-10) (depends on T023)
- [ ] T030 [US3] Implement `GET /api/messages/{message_id}/rag-results` in `backend/app/api/v1/rag.py`: `require_role("manager", "staff")`; call `rag_service.get_message_rag_results`; return `MessageRagResultsResponse` (200); cross-tenant → 404/403 (contracts §4, AC-11, AC-12) (depends on T026)
- [ ] T031 Mount the RAG router at `/api` in `backend/app/main.py` so all four routes resolve (plan.md Backend Tasks #8) (depends on T027–T030)
- [ ] T032 [US3] Surface message RAG results to the detail page: extend `backend/app/services/conversation_service.py` (or expose the dedicated `GET .../rag-results` fetch) so the Spec 005 detail response can carry/trigger the message's stored RAG sources (plan.md Backend Tasks #9, FR-013) (depends on T026)

**Checkpoint**: All four endpoints return per the contract; role matrix + tenant resolution enforced. Backend MVP complete.

---

## Phase 7: Frontend Integration (User Story 3)

**Purpose**: Replace the Spec 005 "Knowledge Sources" placeholder with the real sources display, plus a manager "Process" action on the Documents page.

- [ ] T033 [P] [US3] Add TS types to `frontend/src/types/rag.ts`: `RetrievalStatus`, `RagSource`, `RagQueryResult`, `MessageRagResults`, `DocumentChunk` (data-model.md Frontend Types)
- [ ] T034 [P] [US3] Add the typed API client `frontend/src/api/rag.ts`: `processDocument(documentId, force?)`, `listChunks(documentId)`, `ragQuery(payload)`, `getMessageRagResults(messageId)` — calling the four endpoints with the auth header (depends on T033)
- [ ] T035 [US3] Implement `frontend/src/components/rag/SourceCard.tsx`: renders one `RagSource` — document title, a `document_type` badge, the snippet, and a score indicator (bar/number) (plan.md Frontend #4, AC-18) (depends on T033)
- [ ] T036 [US3] Implement `frontend/src/components/rag/KnowledgeSourcesPanel.tsx`: consumes `MessageRagResults`; `grounded` → list of `SourceCard`s ordered by rank; `no_source`/`no_documents` → clear "No supported source found" / "no documents" state; `query_id == null` → "not retrieved yet"; plus loading + error states (FR-013, AC-18; spec US3) (depends on T034, T035)
- [ ] T037 [US3] Wire `KnowledgeSourcesPanel` into the Spec 005 conversation/message detail page (`frontend/src/pages/ConversationDetailPage`), **replacing** the "Knowledge Sources" placeholder; leave the Suggested Reply / Create Task / Escalate placeholders untouched (plan.md Frontend #3, spec Assumptions) (depends on T036)
- [ ] T038 [US1] Add a manager-only "Process" action + status/chunk-count indicator to the Spec 008 Documents page (`frontend/src/pages/DocumentsPage`): calls `processDocument`, shows processing in-progress / processed (chunk count) / failed states; hidden or disabled for staff (plan.md Frontend #5/#6) (depends on T034)

**Checkpoint**: Detail page shows real RAG sources (or the no-source state); managers can trigger processing from the UI.

---

## Phase 8: Frontend Tests

**Purpose**: Render tests for the sources panel states and the source card.

- [ ] T039 [P] [US3] `KnowledgeSourcesPanel` render tests in `frontend/src/components/rag/__tests__/KnowledgeSourcesPanel.test.tsx`: `grounded` renders a `SourceCard` per source (title/type/snippet/score) in rank order; `no_source` and `no_documents` render the no-supported-source state; `query_id == null` renders "not retrieved yet"; loading + error states render (AC-18) (depends on T036)
- [ ] T040 [P] [US3] `SourceCard` render test: asserts document title, type badge, snippet, and score are all displayed for a given `RagSource` (AC-18) (depends on T035)

**Checkpoint**: Frontend states verified.

---

## Phase 9: Tenant Isolation & Role Security Tests (cross-cutting)

**Purpose**: Prove the hardest guarantees — Tenant A never sees Tenant B, `tenant_id` comes only from the JWT, and the role matrix holds. `backend/tests/integration/test_rag.py`.

- [ ] T041 [P] Manager processes their **own** tenant's document → 200, chunks created, status `processed`; chunks carry the manager's `tenant_id` only (AC-01, AC-02, SR-03)
- [ ] T042 [P] Tenant A cannot process a Tenant B document: A's manager → `POST /process` on a B document → 403/404; no Tenant A chunk created for it (SR-05, spec Cross-Tenant workflow)
- [ ] T043 [P] Tenant A cannot read Tenant B chunks: A → `GET /documents/{B_doc}/chunks` → 403/404 (AC-13; quickstart "Explicit cross-tenant proof")
- [ ] T044 [P] Retrieval is tenant-filtered: same query run as Tenant A and Tenant B returns **disjoint**, own-tenant-only source sets (AC-06; FR-008, SR-02)
- [ ] T045 [P] Cross-tenant `message_id` on `POST /rag/query` → 403/404; no result persisted (contracts §3; AC-12)
- [ ] T046 [P] `GET /messages/{id}/rag-results` for another tenant's message → 403/404, no source leaked (AC-12)
- [ ] T047 [P] Client-supplied `tenant_id` is ignored: a `tenant_id` injected into the request body/query does not change ownership — retrieval/processing still scopes to the JWT tenant (SR-01)
- [ ] T048 [P] Platform Admin → 403 `INSUFFICIENT_ROLE` on **all four** endpoints (process, chunks, query, rag-results) (AC-14, SR-04)
- [ ] T049 [P] Staff → 403 on `POST /process`; staff → 200 on `POST /rag/query` and `GET .../chunks` and `GET .../rag-results` (AC-15, SR-04); unauthenticated → 401 on each

**Checkpoint**: Tenant isolation and the role matrix are proven; no cross-tenant bypass exists.

---

## Phase 10: RAG Behaviour & Integration Tests

**Purpose**: Verify the retrieval pipeline, statuses, persistence, idempotency, determinism, and the demo-corpus expectations. `backend/tests/integration/test_rag.py` + `backend/tests/eval/test_rag_eval.py`.

- [ ] T050 [P] Re-processing replaces chunks (idempotent): process a document twice → the second run deletes the old chunks and inserts fresh ones; no stale/duplicate chunks; `(document_id, chunk_index)` stays unique (FR-005, AC-03)
- [ ] T051 [P] Disabled document excluded: disabling a document then processing → skipped/rejected (422 `DOCUMENT_DISABLED`); a disabled document's chunks are never retrieval candidates (FR-006, AC-04, SR-07)
- [ ] T052 [P] Query returns top-k tenant sources ordered by score with `document_title`, `document_type`, `snippet`, `score`, `rank` (AC-05, FR-009)
- [ ] T053 [P] No-source refuse path: an off-topic query (e.g. "What is the weather forecast for next Tuesday?") against a populated tenant → `status=no_source`, `sources=[]`, `RagQuery` persisted with no results (FR-010, AC-09, SR-06)
- [ ] T054 [P] No-documents path: a query in a tenant with zero processed/enabled documents → `status=no_documents`, `sources=[]` (FR-011, AC-10)
- [ ] T055 [P] Processing failure: force `EmbeddingUnavailable` during processing → document status set `failed`, no chunks stored; the operation can be retried (FR-004, spec Embedding/Model Failure)
- [ ] T056 [P] Results persisted + fetchable: `POST /rag/query` with `message_id` → `GET /messages/{id}/rag-results` returns the same `grounded` sources + `query_id` (AC-11, FR-012)
- [ ] T057 [P] Determinism: repeating an identical query over a fixed corpus returns an identical ordered source set (tie-break `(score, document_id, chunk_index)`) (AC-17, FR-015)
- [ ] T058 No suggested reply is generated or sent: assert no reply-generation/sending code path is exercised by any endpoint; the output is ranked evidence + status only (AC-16, FR-014)
- [ ] T059 [P] Demo fixtures: load the two-tenant demo corpus (Elegant Weddings: Deposit Policy, Cancellation Policy, Premium Wedding Package, Decoration Rules; Royal Events Agency: Refund Policy, Luxury Wedding Package, Catering Policy, Bridal Entrance Setup Policy) from quickstart.md into a reusable fixture for the behaviour + eval tests
- [ ] T060 [P] Demo: Elegant Weddings "Is the deposit refundable if I cancel?" → only Elegant Weddings deposit/cancellation sources (no Royal Events doc appears) (AC-07) (depends on T059)
- [ ] T061 [P] Demo: Royal Events Agency same query → only the Royal Events Refund Policy source (no Elegant Weddings doc appears) — same question, each tenant's own policy only (AC-08; quickstart Step 6–7) (depends on T059)
- [ ] T062 [P] Demo: a pricing/package question retrieves the tenant's package document; a cancellation/refund question retrieves the tenant's refund/cancellation document (research.md eval table) (depends on T059)
- [ ] T063 [P] Demo unsupported service question (e.g. fireworks / drones / celebrity singer) → `no_source` (refuse), no fabricated source (AC-09, SR-06) (depends on T059)
- [ ] T064 Evaluation harness `backend/tests/eval/test_rag_eval.py`: a small labelled set (demo policies + expected source(s) per query) measuring precision@k (relevant source ranked in top-k), confirming the refuse path fires on off-topic queries, and confirming per-tenant isolation in eval; repeatable via the deterministic embedding model; tune + document `RAG_SCORE_THRESHOLD`/`RAG_TOP_K` against it (research.md Decision 11; checklist Evaluation Requirements) (depends on T059)

**Checkpoint**: All 18 acceptance criteria covered by tests; demo corpus retrieves correctly per tenant; refuse path verified; eval set passes.

---

## Phase 11: Quickstart & Manual Validation

**Purpose**: Execute the two-tenant quickstart end to end (quickstart.md).

- [ ] T065 Run migrations (`alembic upgrade head`) → confirm pgvector enabled + the three tables created; log in as managers of both demo tenants
- [ ] T066 Upload + process the Elegant Weddings documents (Deposit + Cancellation policies); confirm each → `status: processed`, `chunk_count >= 1`; inspect `GET .../chunks` → `chunk_text` present, **no embedding vector** in the output
- [ ] T067 Upload + process the Royal Events Agency documents (Refund Policy); confirm processed
- [ ] T068 Query "Is the deposit refundable if I cancel?" as Elegant Weddings → `grounded`, only Elegant Weddings deposit/cancellation sources
- [ ] T069 Query the same question as Royal Events Agency → `grounded`, only the Royal Events Refund Policy; confirm Tenant 1 never retrieves a Tenant 2 source and vice-versa (run the explicit cross-tenant `GET .../chunks` → 403 check)
- [ ] T070 Query an unsupported question (weather / fireworks) as Elegant Weddings → `no_source`, `sources: []`; confirm the empty-corpus case (fresh tenant) → `no_documents`
- [ ] T071 Link a query to a message (`message_id`), then open the conversation detail page → the Knowledge Sources panel shows the retrieved Elegant Weddings sources (title, type, snippet, score); a no-source message shows the no-supported-source state
- [ ] T072 Role/tenant checks: staff `POST /process` → 403, staff `POST /rag/query` → 200; Platform Admin on `POST /rag/query` → `INSUFFICIENT_ROLE`

**Checkpoint**: Quickstart passes end to end; tenant isolation + refuse path demonstrated live.

---

## Phase 12: Acceptance Checklist

**Purpose**: Tick off the acceptance criteria and the requirements checklist.

- [ ] T073 Verify AC-01..AC-18 (spec.md Acceptance Criteria) are each covered by a passing test or the quickstart; record the mapping
- [ ] T074 Walk `checklists/requirements.md` Functional / RAG / Tenant Isolation / Security / API / Data / Testing / Evaluation sections and tick each implemented item
- [ ] T075 Confirm Out-of-Scope items remain **unbuilt**: no suggested-reply generation, no auto-send, no LLM answer synthesis/summarisation, no cross-tenant/global KB, no re-ranking/hybrid search, no document CRUD (Spec 008 owns it), no audit-log persistence/API/UI, no external vector DB, no short-term memory, no WhatsApp/calendar (spec Out of Scope; checklist Out-of-Scope Confirmation)

**Checkpoint**: 009 verified against spec + checklist; ready to hand grounded evidence to 010-suggested-replies.

---

## Dependencies & Execution Order

- **Phase 1 (Setup)** → no deps; do first.
- **Phase 2 (DB/pgvector/models)** → depends on Phase 1; **BLOCKS everything**.
- **Phase 3 (Schemas)** → depends on T005; blocks service + API.
- **Phase 4 (Chunker/Embedder/Retriever)** → depends on Phases 2–3; pure + unit-tested; **blocks the service**. Chunker (T011–T012), Embedder (T013–T014), and Retriever (T015–T016) are independent of each other and run in parallel.
- **Phase 5 (Service)** → depends on Phase 4; blocks the API.
- **Phase 6 (API)** → depends on Phase 5; **MVP backend deliverable**.
- **Phase 7 (Frontend)** → depends on Phase 6 (consumes the endpoints).
- **Phase 8 (Frontend tests)** → depends on Phase 7.
- **Phase 9 (Isolation/role tests)** + **Phase 10 (Behaviour/eval tests)** → depend on Phase 6 (and the demo fixture T059); run after the backend is wired.
- **Phase 11 (Quickstart)** → depends on Phases 6–7.
- **Phase 12 (Acceptance)** → last.

---

## Implementation Strategy

### MVP First (User Stories 1 + 2 — the core capability)

1. Phase 1: Setup (config + pgvector dependency)
2. Phase 2: DB + pgvector + 3 models + migration (**CRITICAL**)
3. Phase 3: Schemas
4. Phase 4: Chunker → Embedder → Retriever (pure, unit-tested in isolation — the retriever is the isolation linchpin)
5. Phase 5: Service (process / query / list-chunks / message-results)
6. Phase 6: API (four endpoints + router mount + error mapping)
7. **STOP and VALIDATE**: run unit + isolation tests; confirm tenant scoping, refuse path (`no_source`/`no_documents`), role matrix, client-tenant override ignored
8. Phase 9 + 10: full isolation + behaviour + eval coverage (AC-01..AC-17)

### Incremental Delivery

1. Setup + DB/pgvector + pipeline + schemas → foundation ready
2. US1 (process) → documents become a searchable, tenant-scoped index (**indexing MVP**)
3. US2 (query) → tenant-scoped retrieval with the refuse path (**retrieval MVP — the feature's reason to exist**)
4. US3 (detail surfacing) → Knowledge Sources panel + manager Process action (frontend)
5. Tests + quickstart + eval + acceptance → all 18 ACs confirmed

---

## Notes

- `[P]` tasks write to different files (or distinct test functions) with no dependency on in-progress parallel tasks
- `[USn]` label maps each task to a user story for traceability and independent testing
- `tenant_id` is **always** derived from the JWT (`get_current_tenant_context`) — never from client input (SR-01); any `tenant_id` in the request body/query is ignored (T047)
- **The retriever has no tenant-less search variant** — isolation is structural, not by discipline (SR-02, SR-08). T015/T016 prove the `tenant_id` predicate is mandatory
- 404 (document/message not in tenant) vs 403 (exists in another tenant) mirrors Specs 005–008 SR-05 via the `_resolve_*_or_raise` helpers
- `RetrievalStatus` persists as a constrained string (VARCHAR + app-boundary validation), not a native PG enum, for evolvability (consistent with Spec 008)
- `no_source` and `no_documents` are **200 OK** outcomes — the refuse path is a normal result, not an error; the downstream 010 reply feature must honour them by refusing to answer from documents (FR-010, FR-011, SR-06)
- **Embedding vectors are never serialised to clients** — `ChunkResponse` omits the `embedding` field (T010, T028)
- Re-processing is **idempotent** (delete-then-insert in one transaction); a Spec 008 content edit resets the doc to `uploaded`, so stale chunks drop out of retrieval until re-processed (FR-005, SR-07)
- A single **versioned** embedding model embeds both chunks and queries (same space); the version is recorded in chunk `metadata` + `rag_queries.embedding_model` for well-defined re-embedding on change
- This feature **generates no suggested reply and sends nothing** (FR-014, AC-16) — it only prepares ranked evidence for 010-suggested-replies
- **Audit logging is out of scope for 009** — deferred to the later audit-log feature (013). If a post-action event hook is added, it is a no-op/future-integration stub only; build no audit persistence, API, or UI here
- External vector DBs, re-ranking/hybrid search, LLM answer synthesis, short-term memory, real WhatsApp API, and calendar syncing are all **out of scope** (spec Out of Scope)
