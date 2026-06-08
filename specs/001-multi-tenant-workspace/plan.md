# Implementation Plan: Multi-Tenant Workspace

**Branch**: `001-multi-tenant-workspace` | **Date**: 2026-06-03 | **Spec**: [spec.md](./spec.md)

---

## Summary

Implement the multi-tenant foundation for EventSense AI. This feature creates the root `tenants` table, the `users` table with canonical roles, a JWT-derived `TenantContext`, a tenant-scoped repository/service pattern, demo tenant seeds, and isolation tests. It does not implement documents, RAG, suggested replies, tasks, escalations, inbox, dashboards, or audit-log APIs.

Every later tenant-owned feature must use this foundation: `tenant_id` comes from authenticated context, tenant-owned queries are scoped by `tenant_id`, and related records are validated to belong to the same tenant.

---

## Technical Context

**Language/Version**: Python 3.11 (backend), TypeScript 5.x (frontend)

**Primary Dependencies**: FastAPI, SQLAlchemy 2.x, Alembic, python-jose (JWT), passlib (bcrypt), React 18, Vite 5

**Storage**: PostgreSQL 15 shared schema with row-level tenant ownership

**Testing**: pytest + pytest-asyncio (backend), Vitest where frontend context is added

**Constraints**:
- `tenant_id` is derived from JWT/current user, never trusted from request data.
- Tenant-owned records must have a non-null `tenant_id`.
- Cross-tenant record access returns 403 without content exposure.
- Platform admins cannot access tenant content routes by default.
- Full audit logging is deferred to `013-audit-logs`; this feature only defines the policy for later integration.

---

## Project Structure

### Documentation

```
specs/001-multi-tenant-workspace/
├── spec.md
├── plan.md
├── research.md
├── data-model.md
├── quickstart.md
├── contracts/
│   └── api-contracts.md
└── tasks.md
```

### Source Code Layout

```
backend/
├── app/
│   ├── core/
│   │   ├── database.py
│   │   ├── security.py
│   │   ├── tenant_context.py
│   │   ├── tenant_repo.py
│   │   └── exceptions.py
│   ├── models/
│   │   ├── tenant.py
│   │   └── user.py
│   ├── api/
│   │   └── v1/
│   │       └── tenants.py
│   └── main.py
├── alembic/
│   └── versions/
│       ├── 0001_create_tenants.py
│       ├── 0002_create_users.py
│       └── 0003_seed_demo_tenants.py
└── tests/
    ├── unit/
    │   └── test_tenant_repo.py
    └── integration/
        └── test_tenant_foundation.py
```

Frontend work in this feature is limited to optional display helpers for current tenant context. Full dashboard/inbox UI belongs to later specs.

---

## In Scope

| Area | What is built |
|------|--------------|
| Database schema | `tenants`, `users`, canonical `user_role` enum |
| Demo seed | Elegant Weddings, Royal Events Agency, optional platform/system tenant |
| Tenant context | `TenantContext(tenant_id, user_id, role)` contract derived from JWT |
| Tenant repository | Shared pattern for tenant-owned reads/writes |
| Tenant metadata endpoint | `GET /api/v1/tenants/me` |
| Admin metadata endpoint | Optional `GET /api/v1/admin/tenants` for platform/demo administration metadata only |
| Isolation tests | Tenant context, tenant-scoped query behavior, client `tenant_id` override prevention |
| Future rules | Same-tenant relationship validation requirements for later features |

---

## Deferred to Later Features

| Item | Later feature |
|------|---------------|
| Login, refresh, role guards | 002-auth-and-roles |
| Message simulator | 003-message-simulator |
| Inbox | 004-message-inbox |
| Conversation detail/message thread | Later conversation feature |
| Documents and document ingestion | Later document/RAG feature |
| pgvector/RAG retrieval | Later RAG feature |
| Intent classifier and risk detection | Later ML/risk features |
| Suggested replies | Later AI replies feature |
| Tasks | Later task feature |
| Escalations | Later escalation feature |
| Audit log table/API/UI | 013-audit-logs |
| Guardrails/evaluation | Later AI quality features |

---

## Backend Components

### `TenantContext`

Spec 001 defines the contract. Spec 002 completes the actual login/token issuance.

```python
@dataclass
class TenantContext:
    tenant_id: UUID
    user_id: UUID
    role: UserRole
```

All protected services receive `TenantContext` or explicit `tenant_id` from it.

### `TenantScopedRepository`

The repository is the default pattern for tenant-owned models.

Required behavior:
- `list(tenant_id, **filters)` always filters by tenant.
- `get(id, tenant_id)` returns only records owned by that tenant.
- `get_or_403(id, tenant_id)` raises a forbidden error on tenant mismatch.
- `create(tenant_id, **data)` injects authenticated tenant and rejects conflicting `tenant_id` input.
- `update/delete` first confirm ownership.

### Client-Supplied `tenant_id`

No body-inspection middleware is used. Each route/schema either:
- omits `tenant_id` entirely and services inject `ctx.tenant_id`, or
- rejects a request containing `tenant_id` if the endpoint contract forbids it.

Tests must prove a client-supplied `tenant_id` cannot override authenticated context.

### Cross-Tenant Block Policy

For MVP documentation and future audit integration:
- blocked attempts are associated with the actor/requesting user's tenant when available
- response is 403
- response and future audit details do not expose victim tenant content
- platform/system-level review can be added in `013-audit-logs`

---

## Same-Tenant Relationship Validation

This feature does not implement the later entities, but it requires future services to validate related records before write:

| Later relationship | Required validation |
|--------------------|--------------------|
| message -> conversation | both tenant IDs match |
| document_chunk -> document | both tenant IDs match |
| task -> assignee/creator/conversation | all tenant IDs match |
| escalation -> conversation/message/users | all tenant IDs match |
| suggested_reply -> conversation/message/source_chunks/users | all tenant IDs match |
| audit_log -> actor/resource metadata | actor tenant is used; victim content is not leaked |

Service-layer validation plus integration tests is acceptable for the senior-project MVP.

---

## Testing Plan

| Test | Purpose |
|------|---------|
| `test_demo_tenants_seeded` | Both demo tenants and manager users exist |
| `test_platform_tenant_seed_optional` | Platform admin belongs to platform/system tenant if seeded |
| `test_tenant_context_from_jwt` | Context is built from token claims |
| `test_client_tenant_id_cannot_override_context` | Request data cannot change tenant scope |
| `test_repo_list_filters_by_tenant` | Tenant A list excludes Tenant B rows |
| `test_repo_get_or_403_blocks_cross_tenant` | Cross-tenant ID returns forbidden |
| `test_create_injects_authenticated_tenant` | Create uses context tenant |
| `test_same_tenant_validation_helper` | Helper detects mismatched related tenants |

---

## Notes

- Canonical roles are `staff`, `manager`, and `platform_admin` from the start.
- Platform admin routes are metadata/admin only and do not expose tenant content.
- pgvector is intentionally not required by this feature; it is introduced with RAG.
