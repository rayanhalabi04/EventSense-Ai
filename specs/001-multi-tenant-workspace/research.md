# Research: Multi-Tenant Workspace

**Branch**: `001-multi-tenant-workspace` | **Phase**: 0 - Pre-design research

---

## Decision 1: Tenant Isolation Strategy

**Decision**: Use a shared PostgreSQL schema. Every tenant-owned table added by current or future features carries a non-null `tenant_id` UUID foreign key referencing `tenants.id`.

**Rationale**:
- Fits the senior-project MVP and provided FastAPI + SQLAlchemy + PostgreSQL stack.
- Avoids schema-per-tenant or database-per-tenant operational overhead.
- Keeps Alembic migrations straightforward.
- Allows later pgvector/RAG tables to use the same tenant-filter pattern when those features are added.

**Alternatives considered**:
- Schema-per-tenant: stronger isolation but too much routing/migration complexity for MVP.
- Database-per-tenant: strongest isolation but overkill for two demo tenants.

---

## Decision 2: JWT-Derived Tenant Context

**Decision**: Protected routes and services use a `TenantContext` derived from a signed JWT/current authenticated user. The backend never trusts `tenant_id` from request bodies, query strings, or frontend state.

**Rationale**:
- Prevents clients from choosing their tenant.
- Keeps tenant scoping consistent across every feature.
- Matches FastAPI dependency injection patterns.

**Implementation note**: Spec 001 defines the context contract; Spec 002 implements login, refresh, and full JWT issuance.

---

## Decision 3: Canonical Roles

**Decision**: Use `staff`, `manager`, and `platform_admin` from the foundation onward.

**Rationale**:
- Matches the product workflow: staff handle daily messages; managers review higher-risk or administrative tenant work; platform admins operate the demo/platform layer.
- Avoids fragile role-rename migrations later.
- Makes platform-admin content restrictions explicit from the first feature.

---

## Decision 4: Tenant-Scoped Repository/Service Pattern

**Decision**: Use an explicit `TenantScopedRepository` or service-layer helper for tenant-owned models.

**Rationale**:
- Avoids accidental unfiltered queries.
- Is easier to test than magical SQLAlchemy event hooks.
- Keeps service code honest: tenant-owned operations require `tenant_id`.

**Alternatives considered**:
- PostgreSQL Row Level Security: useful hardening later, but not required for the MVP foundation.
- SQLAlchemy event hooks: less explicit and harder to reason about in a senior-project codebase.

---

## Decision 5: Same-Tenant Relationship Validation

**Decision**: Later features must validate same-tenant relationships at the service layer and cover them with integration tests.

**Rationale**:
- Composite foreign keys/check constraints can be added later, but service validation is practical for MVP.
- It directly handles common leak risks such as a Tenant A message being attached to a Tenant B conversation.

Examples:
- message tenant matches conversation tenant
- document chunk tenant matches document tenant
- task assignee/creator/conversation tenants match task tenant
- escalation and suggested reply references stay within one tenant

---

## Decision 6: Cross-Tenant Block/Audit Policy

**Decision**: Audit implementation is deferred, but the policy is defined now. When future audit logging exists, blocked cross-tenant attempts are logged under the actor/requesting user's tenant when available. Victim tenant content is not copied into response or audit detail.

**Rationale**:
- Gives managers visibility into suspicious behavior from their tenant users.
- Avoids leaking victim tenant identifiers or content.
- Leaves platform-wide security review for a later audit/security feature.

---

## Decision 7: Demo Tenant Seeding

**Decision**: Seed Elegant Weddings and Royal Events Agency with deterministic IDs and initial manager users. Optionally seed an EventSense Platform tenant for platform admins.

**Rationale**:
- Makes tests and quickstarts deterministic.
- Avoids relying on self-service signup, which is out of MVP scope.

---

## Deferred Items

| Item | Reason deferred |
|------|-----------------|
| Message simulator | Separate feature 003 |
| Inbox | Separate feature 004 |
| Documents and RAG/pgvector | Later document/RAG features |
| Suggested replies | Later AI replies feature |
| Tasks and escalations | Later workflow features |
| Audit log table/API/UI | Later audit feature |
| Guardrails and evaluation | Later AI quality features |
| Billing, CRM, subscriptions | Out of MVP scope |
