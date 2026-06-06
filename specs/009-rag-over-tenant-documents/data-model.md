# Data Model: RAG Over Tenant Documents

**Branch**: `009-rag-over-tenant-documents` | **Phase**: 1 — Design

---

## Schema Changes

Enable the **pgvector** extension and add **three new tables**: `document_chunks`, `rag_queries`, `rag_retrieval_results`. One Alembic migration. No column changes to existing tables — this feature reads `documents` (Spec 008) and writes the document `status` (`processed`/`failed`) via the Spec 008 column.

```sql
CREATE EXTENSION IF NOT EXISTS vector;
```

---

## Enums

### `RetrievalStatus`

```python
class RetrievalStatus(str, Enum):
    grounded     = "grounded"      # ≥1 source above threshold
    no_source    = "no_source"     # candidates existed but none above threshold -> refuse
    no_documents = "no_documents"  # tenant has no processed/enabled documents
    failed       = "failed"        # embedding/query error
```

**Document status interplay (Spec 008 `DocumentStatus`)**: this feature advances `processing_pending`/`uploaded` → `processed` on success, → `failed` on error. Retrieval only considers documents with `status = processed` AND `enabled = true`.

---

## Existing Entities Used

### `tenants` (Spec 001)
`id` → scopes chunks, queries, results.

### `users` (Spec 002)
`role` gates: `manager` processes; `manager`+`staff` query/view.

### `documents` (Spec 008)

| Column | Used for |
|--------|----------|
| `id` | `document_chunks.document_id` FK |
| `tenant_id` | inherited onto chunks |
| `title`, `document_type` | source metadata returned with results |
| `content` | input to the chunker |
| `enabled` | excluded from processing/retrieval when false |
| `status` | advanced to `processed`/`failed` by this feature; retrieval gate |

---

## New Entity: `DocumentChunk`

### Table `document_chunks`

| Column | Type | Constraints | Notes |
|--------|------|-------------|-------|
| `id` | UUID | PK | |
| `tenant_id` | UUID | NOT NULL, FK → `tenants.id`, indexed | inherited from document; **mandatory retrieval filter** |
| `document_id` | UUID | NOT NULL, FK → `documents.id`, `ON DELETE CASCADE`, indexed | source document |
| `chunk_text` | TEXT | NOT NULL | the chunk content |
| `chunk_index` | INTEGER | NOT NULL | order within the document (0-based) |
| `embedding` | `vector(RAG_EMBEDDING_DIM)` | NOT NULL | pgvector embedding |
| `metadata` | JSONB | NOT NULL default `{}` | embedding model/version, char span, source title/type snapshot |
| `created_at` | TIMESTAMPTZ | NOT NULL, default now | |

### Constraints & Indexes

- `UNIQUE (document_id, chunk_index)` — stable ordering; idempotent replace.
- `INDEX (tenant_id, document_id)` — list a document's chunks; tenant scoping.
- pgvector ANN index on `embedding` (cosine ops), e.g. `ivfflat (embedding vector_cosine_ops)` — **always queried together with the `tenant_id` predicate**.

### SQLAlchemy model (`backend/app/models/document_chunk.py`)

```python
from pgvector.sqlalchemy import Vector

class DocumentChunk(Base):
    __tablename__ = "document_chunks"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    tenant_id: Mapped[UUID] = mapped_column(ForeignKey("tenants.id"), nullable=False, index=True)
    document_id: Mapped[UUID] = mapped_column(
        ForeignKey("documents.id", ondelete="CASCADE"), nullable=False, index=True
    )
    chunk_text: Mapped[str] = mapped_column(Text, nullable=False)
    chunk_index: Mapped[int] = mapped_column(Integer, nullable=False)
    embedding: Mapped[list[float]] = mapped_column(Vector(settings.RAG_EMBEDDING_DIM), nullable=False)
    metadata_: Mapped[dict] = mapped_column("metadata", JSONB, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    document: Mapped["Document"] = relationship()

    __table_args__ = (
        UniqueConstraint("document_id", "chunk_index", name="uq_chunk_doc_index"),
        Index("ix_chunk_tenant_document", "tenant_id", "document_id"),
    )
```

---

## New Entity: `RagQuery`

### Table `rag_queries`

| Column | Type | Constraints | Notes |
|--------|------|-------------|-------|
| `id` | UUID | PK | |
| `tenant_id` | UUID | NOT NULL, FK → `tenants.id`, indexed | scopes the query |
| `message_id` | UUID | NULL, FK → `messages.id`, indexed | links to a message for detail display |
| `query_text` | TEXT | NOT NULL | the query (client message or free text) |
| `top_k` | INTEGER | NOT NULL | requested max sources |
| `threshold` | DOUBLE PRECISION | NOT NULL | similarity cutoff used |
| `status` | VARCHAR(20) | NOT NULL | one of `RetrievalStatus` |
| `embedding_model` | VARCHAR(64) | NOT NULL | model/version used |
| `created_at` | TIMESTAMPTZ | NOT NULL, default now | |

Index: `(tenant_id, message_id)` — fetch latest results for a message.

---

## New Entity: `RagRetrievalResult`

### Table `rag_retrieval_results`

| Column | Type | Constraints | Notes |
|--------|------|-------------|-------|
| `id` | UUID | PK | |
| `rag_query_id` | UUID | NOT NULL, FK → `rag_queries.id`, `ON DELETE CASCADE` | parent query |
| `tenant_id` | UUID | NOT NULL, FK → `tenants.id` | redundant tenant guard |
| `document_id` | UUID | NOT NULL, FK → `documents.id` | source document |
| `chunk_id` | UUID | NOT NULL, FK → `document_chunks.id` | matched chunk |
| `snippet` | TEXT | NOT NULL | bounded slice of `chunk_text` for display |
| `score` | DOUBLE PRECISION | NOT NULL | similarity score |
| `rank` | INTEGER | NOT NULL | 1-based position in the result set |
| `created_at` | TIMESTAMPTZ | NOT NULL, default now | |

Index: `(rag_query_id, rank)` — ordered fetch.

---

## Entity Relationships

```
Tenant 1──* Document 1──* DocumentChunk
                  ▲                 ▲
                  │                 │ (matched)
Tenant 1──* RagQuery 1──* RagRetrievalResult ──> DocumentChunk
                  │
              Message 0..1 (optional link)
```

- A `DocumentChunk` belongs to one `Document` and one `Tenant`.
- A `RagQuery` belongs to one `Tenant`, optionally one `Message`, and has many `RagRetrievalResult`s.
- Every `RagRetrievalResult` references a chunk + its document, all within the same tenant.

---

## Pydantic Schemas (`backend/app/schemas/rag.py`)

```python
class ProcessResponse(BaseModel):
    document_id: UUID
    status: str                 # Spec 008 DocumentStatus: "processed" | "failed"
    chunk_count: int
    embedding_model: str

class ChunkResponse(BaseModel):
    id: UUID
    document_id: UUID
    chunk_index: int
    chunk_text: str
    metadata: dict
    created_at: datetime
    model_config = ConfigDict(from_attributes=True)
    # NOTE: embedding vector is NOT serialised to clients

class RagQueryRequest(BaseModel):
    query: str = Field(min_length=1, max_length=2000)
    message_id: UUID | None = None
    top_k: int = Field(default=4, ge=1, le=20)
    threshold: float | None = Field(default=None, ge=0.0, le=1.0)

    @field_validator("query")
    @classmethod
    def query_not_blank(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("Query must not be blank")
        return v.strip()

class RagSource(BaseModel):
    document_id: UUID
    document_title: str
    document_type: str
    chunk_id: UUID
    snippet: str
    score: float
    rank: int

class RagQueryResponse(BaseModel):
    status: RetrievalStatus
    sources: list[RagSource]    # empty unless status == grounded
    query_id: UUID
    embedding_model: str

class MessageRagResultsResponse(BaseModel):
    message_id: UUID
    status: RetrievalStatus
    sources: list[RagSource]
    query_id: UUID | None
    created_at: datetime | None
```

---

## Service / Pipeline Logic (`backend/app/services/rag_service.py`)

```python
async def process_document(session, tenant_id, document_id) -> ProcessResponse:
    doc = await _resolve_document_or_raise(session, tenant_id, document_id)   # 404/403
    if not doc.enabled:
        raise DocumentDisabledError()                                        # 422 DOCUMENT_DISABLED
    try:
        chunks = chunk_text(doc.content, settings.RAG_CHUNK_SIZE, settings.RAG_CHUNK_OVERLAP)
        vectors = embedder.embed(chunks)                                      # may raise EmbeddingUnavailable
        await _replace_chunks(session, tenant_id, doc, chunks, vectors)      # delete old + insert new (txn)
        doc.status = DocumentStatus.processed.value
        await session.commit()
        return ProcessResponse(document_id=doc.id, status=doc.status,
                               chunk_count=len(chunks), embedding_model=embedder.model_version)
    except EmbeddingUnavailable:
        doc.status = DocumentStatus.failed.value
        await session.commit()
        raise ModelUnavailableError()                                        # 503 MODEL_UNAVAILABLE


async def query(session, tenant_id, query_text, top_k, threshold, message_id=None) -> RagQueryResponse:
    threshold = threshold if threshold is not None else settings.RAG_SCORE_THRESHOLD
    # candidate existence check (no processed+enabled docs -> no_documents)
    if not await _tenant_has_searchable_chunks(session, tenant_id):
        return await _persist_and_return(session, tenant_id, query_text, top_k, threshold,
                                         message_id, RetrievalStatus.no_documents, [])
    try:
        qvec = embedder.embed([query_text])[0]
    except EmbeddingUnavailable:
        return await _persist_and_return(..., RetrievalStatus.failed, [])

    hits = retriever.search(session, tenant_id, qvec, top_k, threshold)       # tenant-filtered, ordered
    status = RetrievalStatus.grounded if hits else RetrievalStatus.no_source
    sources = build_sources(hits)                                            # join doc title/type, snippet, rank
    return await _persist_and_return(session, tenant_id, query_text, top_k, threshold,
                                     message_id, status, sources)


async def list_chunks(session, tenant_id, document_id) -> list[DocumentChunk]:
    await _resolve_document_or_raise(session, tenant_id, document_id)         # 404/403
    stmt = (select(DocumentChunk)
            .where(DocumentChunk.tenant_id == tenant_id,
                   DocumentChunk.document_id == document_id)
            .order_by(DocumentChunk.chunk_index.asc()))
    return (await session.execute(stmt)).scalars().all()


async def get_message_rag_results(session, tenant_id, message_id) -> MessageRagResultsResponse:
    await _resolve_message_or_raise(session, tenant_id, message_id)           # 404/403
    q = await _latest_query_for_message(session, tenant_id, message_id)
    if q is None:
        return MessageRagResultsResponse(message_id=message_id, status=RetrievalStatus.no_source,
                                         sources=[], query_id=None, created_at=None)  # "not retrieved yet" handled in UI
    return MessageRagResultsResponse(...)
```

### Retriever (the single tenant-filtered search path) — `backend/app/rag/retriever.py`

```python
def search(session, tenant_id, query_vector, top_k, threshold):
    # cosine distance (<=>) -> similarity = 1 - distance
    stmt = (
        select(
            DocumentChunk,
            (1 - DocumentChunk.embedding.cosine_distance(query_vector)).label("score"),
        )
        .join(Document, Document.id == DocumentChunk.document_id)
        .where(
            DocumentChunk.tenant_id == tenant_id,           # SR-02: ALWAYS present
            Document.enabled.is_(True),                      # SR-07
            Document.status == DocumentStatus.processed.value,
        )
        .order_by(text("score DESC"), DocumentChunk.document_id, DocumentChunk.chunk_index)
        .limit(top_k)
    )
    rows = session.execute(stmt).all()
    return [(chunk, score) for (chunk, score) in rows if score >= threshold]
```

> There is no `search` variant without `tenant_id`. Isolation is structural (SR-02, SR-08).

### Error → HTTP mapping

| Service raises | HTTP | error_code |
|----------------|------|-----------|
| `NotFoundError` (document/message) | 404 | `DOCUMENT_NOT_FOUND` / `MESSAGE_NOT_FOUND` |
| `ForbiddenError` (cross-tenant) | 403 | `CROSS_TENANT_FORBIDDEN` |
| `DocumentDisabledError` | 422 | `DOCUMENT_DISABLED` |
| `ModelUnavailableError` | 503 | `MODEL_UNAVAILABLE` |
| invalid/empty query / bad params | 422 | validation detail |
| (role guard) | 403 | `INSUFFICIENT_ROLE` |
| (auth) | 401 | `MISSING_TOKEN` / `INVALID_TOKEN` / `TOKEN_EXPIRED` |

---

## Frontend Types (`frontend/src/types/rag.ts`)

```typescript
type RetrievalStatus = "grounded" | "no_source" | "no_documents" | "failed";

interface RagSource {
  document_id: string;
  document_title: string;
  document_type: string;
  chunk_id: string;
  snippet: string;
  score: number;
  rank: number;
}

interface RagQueryResult {
  status: RetrievalStatus;
  sources: RagSource[];
  query_id: string;
  embedding_model: string;
}

interface MessageRagResults {
  message_id: string;
  status: RetrievalStatus;
  sources: RagSource[];
  query_id: string | null;
  created_at: string | null;
}

interface DocumentChunk {
  id: string;
  document_id: string;
  chunk_index: number;
  chunk_text: string;
  metadata: Record<string, unknown>;
  created_at: string;
}
```
