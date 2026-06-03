# Research: Multi-Tenant Workspace

**Branch**: `001-multi-tenant-workspace` | **Phase**: 0 — Pre-design research

All technical choices below are resolved from the provided stack (FastAPI + SQLAlchemy + PostgreSQL + pgvector + JWT). No `NEEDS CLARIFICATION` items remain.

---

## Decision 1: Tenant Isolation Strategy

**Decision**: Row-level isolation — every tenant-owned table carries a `tenant_id` UUID foreign key referencing the `tenants` table. All queries are filtered by `tenant_id` via a SQLAlchemy dependency injected at the service layer.

**Rationale**:
- Fits naturally with a single PostgreSQL instance and SQLAlchemy ORM.
- Avoids per-tenant schema creation complexity (schema-per-tenant requires dynamic connection routing or `SET search_path` manipulation, which is fragile with pgvector).
- pgvector's `ivfflat` and `hnsw` indexes work across a shared table; a `WHERE tenant_id = :tid` pre-filter is supported and keeps the index warm for all tenants.
- Alembic migrations apply once to the shared schema — simpler than maintaining per-tenant migration state.

**Alternatives considered**:
- Schema-per-tenant: stronger isolation, but pgvector index management per schema is operationally costly. Rejected for MVP.
- Database-per-tenant: maximum isolation, but requires separate connection pools and Alembic migration runs per tenant. Rejected — overkill for two demo tenants.

---

## Decision 2: JWT Tenant Claim

**Decision**: The JWT access token includes `tenant_id` (UUID) and `user_role` as first-class claims. FastAPI extracts these via a `get_current_tenant_context` dependency on every protected route. The backend never reads `tenant_id` from the request body or query parameters for authorization purposes.

**Rationale**:
- Aligns with SR-01: session is the source of truth.
- FastAPI's `Depends()` system makes it trivial to inject `TenantContext` (a dataclass carrying `tenant_id` + `user_id` + `role`) into every route handler.
- JWT signing with a shared secret (HS256) or RS256 key ensures the claim cannot be forged by the client.

**How it works**:
```
POST /auth/token  →  JWT payload: { sub: user_id, tenant_id: uuid, role: "tenant_agent", exp: ... }
Every API call    →  Depends(get_current_tenant_context) extracts tenant_id from token
Service layer     →  Always appends .filter(Model.tenant_id == ctx.tenant_id)
```

**Alternatives considered**:
- Lookup `tenant_id` from DB on every request using `user_id`: adds a DB round-trip per request; unnecessary since the claim is already in the token. Rejected.

---

## Decision 3: SQLAlchemy Tenant Filter Enforcement

**Decision**: A `TenantScopedRepository` base class (or mixin) wraps all SQLAlchemy query methods and automatically appends `.filter(Model.tenant_id == tenant_id)` before execution. Direct model queries outside this abstraction are disallowed in service code.

**Rationale**:
- Prevents accidental unfiltered queries ("forgot to add `.filter`") from exposing cross-tenant data.
- Centralises the enforcement point — audited in one place rather than scattered across every route.
- SQLAlchemy 2.x's `select()` + `.where()` style makes this clean to wrap.

**Pattern**:
```python
class TenantRepo(Generic[T]):
    def get(self, id: UUID, tenant_id: UUID) -> T | None:
        return session.get(T, id, where=[T.tenant_id == tenant_id])

    def list(self, tenant_id: UUID, **filters) -> list[T]:
        q = select(T).where(T.tenant_id == tenant_id)
        for k, v in filters.items():
            q = q.where(getattr(T, k) == v)
        return session.execute(q).scalars().all()
```

**Alternatives considered**:
- PostgreSQL Row Level Security (RLS): excellent isolation guarantee, but requires `SET app.current_tenant_id` on every connection, complicating connection pool reuse. Deferred to post-MVP as an additional hardening layer.
- SQLAlchemy event hooks (`before_execute`): more magical, harder to test. Rejected in favour of explicit repo wrapping.

---

## Decision 4: pgvector Tenant Filtering

**Decision**: The `document_chunks` table includes a `tenant_id` UUID column. Every vector similarity search includes a `WHERE tenant_id = :tenant_id` clause **before** the `ORDER BY embedding <=> :query_vec LIMIT :k` clause. This is a pre-filter, not post-filter.

**Rationale**:
- SR-05 mandates pre-filtering. Post-retrieval filtering (fetch top-K globally, then discard wrong-tenant results) would leak tenant chunk counts and degrade result quality for small tenants.
- pgvector supports combined index scans with WHERE filters on indexed columns. Adding a B-tree index on `tenant_id` alongside the `ivfflat`/`hnsw` index is standard practice.
- SQLAlchemy + pgvector (`pgvector-sqlalchemy`) allows expressing this as: `session.execute(select(DocumentChunk).where(DocumentChunk.tenant_id == tid).order_by(DocumentChunk.embedding.l2_distance(query_vec)).limit(k))`.

**Index strategy**:
- `CREATE INDEX ON document_chunks USING hnsw (embedding vector_cosine_ops)` — shared across all tenants (acceptable for MVP scale).
- `CREATE INDEX ON document_chunks (tenant_id)` — B-tree for the pre-filter.

---

## Decision 5: Audit Log Design

**Decision**: A dedicated `audit_logs` table with append-only semantics enforced at the application layer. No `UPDATE` or `DELETE` statements are ever issued against this table. Rows are written by a shared `AuditService` called from route handlers and middleware.

**Fields**: `id`, `tenant_id`, `actor_user_id`, `action`, `resource_type`, `resource_id`, `outcome` (allowed/blocked), `detail` (JSON), `ip_address`, `created_at`.

**Rationale**:
- Simpler than an event-streaming solution for MVP scale.
- PostgreSQL's MVCC guarantees that concurrent audit writes don't block each other.
- The `tenant_id` on every row allows Tenant Admins to read only their own logs (same `TenantRepo` pattern).
- `created_at` has a `DEFAULT now()` and is never set by application code, preventing timestamp forgery.

**Alternatives considered**:
- Separate append-only audit database: stronger immutability guarantee, but operationally complex for MVP. Deferred.
- Kafka / event stream: appropriate at scale, out of scope for MVP.

---

## Decision 6: Demo Tenant Seeding

**Decision**: Two demo tenants (Elegant Weddings, Royal Events Agency) are created by an Alembic data migration (`versions/XXXX_seed_demo_tenants.py`) that runs at deployment time. Each tenant gets a deterministic UUID so tests can reference them.

**Rationale**:
- Alembic tracks whether the seed has run (via its version table), so it is idempotent.
- Using fixed UUIDs (`uuid5(NAMESPACE_DNS, "elegant-weddings")` etc.) means tests and documentation can reference stable IDs without a lookup step.

---

## Decision 7: Deferred Items (Not in This Feature)

| Item | Reason deferred |
|------|----------------|
| Redis caching | No cache layer needed until RAG and reply generation are implemented |
| AI suggested replies | Depends on document ingestion pipeline (next feature) |
| Document chunking pipeline | Separate feature; this feature only defines the `documents` and `document_chunks` schema |
| Self-service tenant sign-up UI | Out of scope per spec |
| PostgreSQL Row Level Security | Post-MVP hardening layer |
| Per-tenant rate limiting | Out of scope per spec |
| SSO / federated identity | Out of scope per spec |
