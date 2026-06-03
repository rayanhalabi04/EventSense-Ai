# Implementation Plan: Multi-Tenant Workspace

**Branch**: `001-multi-tenant-workspace` | **Date**: 2026-06-03 | **Spec**: [spec.md](./spec.md)

**Input**: Feature specification from `specs/001-multi-tenant-workspace/spec.md`

---

## Summary

Implement the foundational multi-tenant data isolation layer for EventSense AI. Every tenant-owned entity (conversations, messages, documents, chunks, replies, tasks, escalations, audit logs) carries a non-nullable `tenant_id`. The authenticated user's JWT is the sole source of tenant context — the backend never trusts a `tenant_id` supplied by the client. A `TenantScopedRepository` base class enforces the filter on all reads; an `AuditService` records every security-relevant event. pgvector similarity searches pre-filter by `tenant_id` before ranking. Two demo tenants are seeded via Alembic at startup.

---

## Technical Context

**Language/Version**: Python 3.11 (backend), TypeScript 5.x (frontend)

**Primary Dependencies**: FastAPI, SQLAlchemy 2.x, Alembic, pgvector-sqlalchemy, python-jose (JWT), passlib (bcrypt), React 18, Vite 5, Tailwind CSS, shadcn/ui

**Storage**: PostgreSQL 15 + pgvector extension (single shared database, row-level tenant isolation)

**Testing**: pytest + pytest-asyncio (backend), Vitest (frontend)

**Target Platform**: Linux server (backend), browser (frontend)

**Project Type**: Web application — FastAPI REST backend + React SPA frontend

**Performance Goals**: Standard web app targets. No special throughput requirements for MVP.

**Constraints**: `tenant_id` must be a non-nullable FK on every tenant-owned table. Cross-tenant queries must return 403, never 404 or 200. Audit log rows are never updated or deleted.

**Scale/Scope**: Two demo tenants for MVP. Schema designed to support ~100 tenants without structural changes.

---

## Constitution Check

The project constitution file is a blank template (not yet ratified). No governance gates apply. This plan will proceed without constitution violations.

*Post-MVP recommendation*: Ratify a constitution before the second feature to establish principles around data access patterns, test-first requirements, and security review gates.

---

## Project Structure

### Documentation (this feature)

```
specs/001-multi-tenant-workspace/
├── plan.md              # This file
├── research.md          # Phase 0: design decisions
├── data-model.md        # Phase 1: entity definitions + Alembic migration plan
├── quickstart.md        # Phase 1: local setup guide
├── contracts/
│   └── api-contracts.md # Phase 1: API endpoint contracts
└── tasks.md             # Phase 2 output (created by /speckit-tasks)
```

### Source Code Layout

```
backend/
├── app/
│   ├── core/
│   │   ├── tenant_context.py      # TenantContext dataclass; get_current_tenant_context dependency
│   │   ├── tenant_repo.py         # TenantScopedRepository[T] base class
│   │   └── security.py            # JWT decode helpers
│   ├── models/
│   │   ├── tenant.py
│   │   ├── user.py
│   │   ├── conversation.py
│   │   ├── message.py
│   │   ├── document.py
│   │   ├── document_chunk.py
│   │   ├── suggested_reply.py
│   │   ├── task.py
│   │   ├── escalation.py
│   │   └── audit_log.py
│   ├── api/
│   │   └── v1/
│   │       ├── tenants.py
│   │       ├── conversations.py
│   │       ├── messages.py
│   │       ├── documents.py
│   │       ├── suggested_replies.py
│   │       ├── tasks.py
│   │       ├── escalations.py
│   │       └── audit_logs.py
│   ├── services/
│   │   └── audit_service.py
│   └── main.py
├── alembic/
│   └── versions/
│       ├── 0001_create_tenants.py
│       ├── 0002_create_users.py
│       ├── 0003_create_conversations_messages.py
│       ├── 0004_create_documents_chunks.py
│       ├── 0005_create_suggested_replies.py
│       ├── 0006_create_tasks_escalations.py
│       ├── 0007_create_audit_logs.py
│       └── 0008_seed_demo_tenants.py
└── tests/
    ├── unit/
    │   ├── test_tenant_repo.py
    │   └── test_audit_service.py
    └── integration/
        └── test_tenant_isolation.py

frontend/
├── src/
│   ├── api/
│   │   └── client.ts              # Axios; never sends tenant_id in body
│   ├── context/
│   │   └── TenantContext.tsx      # React context for decoded JWT claims
│   ├── hooks/
│   │   └── useTenantContext.ts
│   └── pages/
│       └── Dashboard.tsx
└── tests/
    └── unit/
        └── TenantContext.test.tsx
```

---

## In Scope for This Feature

| Area | What is built |
|------|--------------|
| Database schema | All 10 tables with `tenant_id` enforcement, indexes, pgvector extension |
| Alembic migrations | Migrations 0001–0008 including demo tenant seed |
| Tenant context | `TenantContext` dataclass + `get_current_tenant_context` FastAPI dependency |
| Tenant-scoped repository | `TenantScopedRepository[T]` base class used by all service code |
| Audit service | `AuditService.log()` — appends to `audit_logs`, called from routes on security events |
| Cross-tenant blocking | Middleware / route logic: detects `tenant_id` mismatch → 403 + audit log |
| API endpoints | All endpoints listed in `contracts/api-contracts.md` (CRUD for all entities) |
| JWT tenant claim extraction | `get_current_tenant_context` reads `tenant_id` from JWT — never from request body |
| pgvector pre-filter | `document_chunks` queries always include `WHERE tenant_id = :tid` before vector sort |
| Frontend tenant context | React `TenantContext` provider; API client that never sends `tenant_id` in body |
| Dashboard scaffold | Tenant-scoped dashboard page (data lists only — no AI features yet) |
| Tenant isolation tests | `test_tenant_isolation.py` covering all 10 acceptance criteria |
| Demo seed | Two tenants with known UUIDs and admin users |

---

## Deferred to Later Features

| Item | Target feature |
|------|---------------|
| Document chunking and embedding pipeline | Document Ingestion feature |
| AI suggested reply generation | AI Reply Generation feature |
| Redis caching | Performance / caching feature |
| Self-service tenant sign-up | Tenant Onboarding feature |
| PostgreSQL Row Level Security | Security hardening (post-MVP) |
| Per-tenant rate limiting | Platform Operations feature |
| SSO / federated identity | Auth Enhancement feature |
| GDPR deletion / data export | Compliance feature |
| Tenant branding / themes | UI Customisation feature |

---

## Backend Components

### 1. `TenantContext` and JWT Dependency (`app/core/tenant_context.py`)

```python
@dataclass
class TenantContext:
    tenant_id: UUID
    user_id: UUID
    role: UserRole

async def get_current_tenant_context(token: str = Depends(oauth2_scheme), db: Session = Depends(get_db)) -> TenantContext:
    payload = decode_jwt(token)          # raises 401 if invalid/expired
    return TenantContext(
        tenant_id=UUID(payload["tenant_id"]),
        user_id=UUID(payload["sub"]),
        role=UserRole(payload["role"]),
    )
```

All protected routes declare `ctx: TenantContext = Depends(get_current_tenant_context)`.

---

### 2. `TenantScopedRepository` (`app/core/tenant_repo.py`)

Generic base class. All service layer database access goes through this — never raw `session.query()` for tenant-owned models.

Key methods:
- `get(id, tenant_id) -> T | None` — returns None (not raises) if `tenant_id` mismatches
- `get_or_403(id, tenant_id) -> T` — raises `ForbiddenError` + writes audit log if mismatched
- `list(tenant_id, **filters) -> list[T]`
- `create(tenant_id, **data) -> T` — injects `tenant_id` on create; rejects if caller tries to supply a different value
- `update(id, tenant_id, **data) -> T` — calls `get_or_403` first
- `delete(id, tenant_id) -> None` — calls `get_or_403` first

---

### 3. `AuditService` (`app/services/audit_service.py`)

Single method: `log(tenant_id, action, outcome, actor_user_id=None, resource_type=None, resource_id=None, resource_tenant_id=None, detail=None, ip_address=None)`.

Always appends — never updates existing rows. Called:
- On every `get_or_403` mismatch (`action=cross_tenant_access_attempt`, `outcome=blocked`)
- On document uploads (`action=document_upload`, `outcome=allowed`)
- On AI reply generation (`action=reply_generated`, `outcome=allowed`)
- When a body-supplied `tenant_id` differs from the JWT claim (`action=tenant_id_override_attempt`, `outcome=blocked`)

---

### 4. FastAPI Route Handlers (`app/api/v1/`)

Each router:
- Declares `ctx: TenantContext = Depends(get_current_tenant_context)`
- Passes `ctx.tenant_id` to the repo — never reads `tenant_id` from the request body
- Uses `repo.get_or_403()` for single-resource reads to enforce isolation + audit logging
- Returns 403 with `{ "detail": "forbidden", "error_code": "CROSS_TENANT_ACCESS" }` on mismatch

---

### 5. pgvector Query Pattern (`app/core/vector_search.py`)

```python
def search_chunks(tenant_id: UUID, query_embedding: list[float], k: int = 5) -> list[DocumentChunk]:
    return session.execute(
        select(DocumentChunk)
        .where(DocumentChunk.tenant_id == tenant_id)          # pre-filter — mandatory
        .order_by(DocumentChunk.embedding.cosine_distance(query_embedding))
        .limit(k)
    ).scalars().all()
```

The `tenant_id` filter is applied before the vector sort. This function is a stub for this feature — it will be wired to actual embedding calls in the AI feature.

---

## Tenant Isolation Tests (`tests/integration/test_tenant_isolation.py`)

Tests map 1:1 to spec acceptance criteria:

| Test | AC |
|------|----|
| `test_cross_tenant_conversation_returns_403` | AC-01 |
| `test_all_records_have_nonnull_tenant_id` | AC-02 |
| `test_rag_query_returns_only_own_tenant_chunks` | AC-03 |
| `test_body_tenant_id_is_ignored` | AC-04 |
| `test_suggested_reply_has_no_cross_tenant_sources` | AC-05 |
| `test_blocked_request_creates_audit_log_entry` | AC-06 |
| `test_tenant_admin_cannot_read_other_tenant_audit_log` | AC-07 |
| `test_new_tenant_workspace_is_empty` | AC-08 |
| `test_partial_upload_leaves_no_chunks` | AC-09 |
| `test_demo_tenants_are_seeded_and_isolated` | AC-10 |

Each test uses a fresh transaction rolled back after the test (no shared state between tests).

---

## Authentication Dependency Assumptions

This feature **does not implement** the auth token issuance flow. It assumes:

1. `POST /auth/token` exists and returns a JWT with claims `{ sub, tenant_id, role, exp }`.
2. The JWT is signed with a secret available to the backend as `JWT_SECRET_KEY` in the environment.
3. `tenant_id` in the JWT is validated at login time — the auth system verifies the user belongs to that tenant before issuing the token.
4. If auth is not yet built, a test helper `make_test_token(tenant_id, user_id, role)` is provided in `tests/conftest.py` to generate valid JWTs for integration tests.

---

## RAG Tenant Filtering Requirements

For this feature, `document_chunks` schema and the `search_chunks` stub function are implemented. The full embedding pipeline (OpenAI API call, chunk splitting) is deferred. The filtering contract is:

- `WHERE document_chunks.tenant_id = :tenant_id` MUST appear before `ORDER BY embedding <=> :query_vec`.
- This is enforced by wrapping vector searches in `search_chunks(tenant_id, ...)` — callers cannot issue a vector search without supplying a `tenant_id`.
- The function raises `ValueError` if `tenant_id` is `None`.

---

## Audit Logging Requirements

- `AuditService.log()` is called synchronously in the same request cycle (no background task for MVP).
- `created_at` is set by PostgreSQL `DEFAULT now()` — never by application code.
- The `audit_logs` table has no `UPDATE` or `DELETE` grants in the application DB user's role (enforced at DB level in the migration).
- Tenant Admin access to audit logs is gated by `[admin_required]` on the endpoint + `TenantScopedRepository` filter.
- Super Admin can query any tenant's logs via `GET /api/v1/admin/audit-logs?tenant_id=uuid`.

---

## Frontend Contract

- The Axios client (`src/api/client.ts`) attaches `Authorization: Bearer <token>` on every request.
- It **never** reads `tenant_id` from local state or appends it to request bodies or query parameters.
- `TenantContext.tsx` decodes the JWT (client-side, for display purposes only) and exposes `{ tenantId, tenantName, role }` to components.
- The Dashboard page fetches conversations, tasks, and documents using the tenant context from the API — it never constructs URLs with hardcoded tenant IDs.
