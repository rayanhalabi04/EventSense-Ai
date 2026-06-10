# Feature Specification: Multi-Tenant Workspace

**Feature Branch**: `001-multi-tenant-workspace`

**Created**: 2026-06-03

**Status**: Draft

---

## Goal

Establish the foundational multi-tenant workspace model for EventSense AI. The platform must support multiple independent wedding/event businesses in one shared application while ensuring tenant data is isolated by default.

This feature creates the tenant foundation only: tenant records, tenant-owned users, authenticated tenant context, tenant-scoped data access rules, demo tenant seeds, and isolation tests. Later features will add messages, documents, RAG, suggested replies, tasks, escalations, audit logs, and guardrails on top of this foundation.

The MVP must support at least two demo tenants: **Elegant Weddings** and **Royal Events Agency**.

---

## Main Users

| Role | Description |
|------|-------------|
| **staff** | Planner or agency staff member. Uses tenant-scoped operational features in later specs. |
| **manager** | Senior tenant user. Has staff capabilities plus manager-only tools in later specs. |
| **platform_admin** | Internal EventSense AI operator for platform/demo administration. Cannot access tenant content routes by default. |

---

## User Stories

### User Story 1 - Tenant Context Is Established from Authentication (Priority: P1)

An authenticated user belongs to exactly one tenant for the current MVP session. Every protected request derives `tenant_id`, `user_id`, and role from the authenticated session/JWT, not from request bodies, query strings, or frontend state.

**Independent Test**: Create users for two tenants, issue test JWTs, and verify protected foundation routes use only the tenant from the token.

**Acceptance Scenarios**:

1. **Given** a user belongs to Elegant Weddings, **When** they authenticate, **Then** the session context contains Elegant Weddings' tenant ID.
2. **Given** a request body includes a `tenant_id`, **When** the backend handles the request, **Then** the client-supplied value cannot override the authenticated tenant.
3. **Given** a missing, invalid, or expired token, **When** a protected route is called, **Then** the system returns 401.

### User Story 2 - Tenant-Scoped Data Access Pattern (Priority: P1)

Backend services use a tenant-scoped repository/service pattern so all tenant-owned reads and writes require an explicit authenticated tenant context.

**Independent Test**: Insert records for Tenant A and Tenant B in a tenant-owned test model or seeded table. Verify list/get operations for Tenant A never return Tenant B records.

**Acceptance Scenarios**:

1. **Given** records exist for multiple tenants, **When** a tenant-scoped list operation runs for Tenant A, **Then** only Tenant A records are returned.
2. **Given** a user requests a record from another tenant by ID, **When** the service detects the tenant mismatch, **Then** the request is blocked with 403 and no tenant content is returned.
3. **Given** a create operation is called with a client-supplied `tenant_id`, **When** the record is saved, **Then** the service uses the authenticated tenant or rejects the supplied field according to the endpoint contract.

### User Story 3 - Demo Tenants Are Seeded (Priority: P1)

The local/demo environment starts with two isolated tenants and initial manager users so later features can be tested without manual setup.

**Independent Test**: Run migrations/seeds, then confirm both tenants and their manager users exist with canonical roles.

**Acceptance Scenarios**:

1. **Given** migrations have run, **When** the seed is checked, **Then** Elegant Weddings and Royal Events Agency exist with stable UUIDs/slugs.
2. **Given** each demo tenant has an initial user, **When** that user is queried, **Then** their role is `manager` and their `tenant_id` is non-null.
3. **Given** a platform admin seed is needed for demo administration, **When** it is created, **Then** it belongs to a platform/system tenant and cannot access tenant content routes by default.

### User Story 4 - Foundation Supports Future Tenant-Owned Entities (Priority: P2)

Future features can safely add tenant-owned entities such as conversations, messages, documents, document chunks, suggested replies, tasks, escalations, and audit logs without changing the core tenant isolation model.

**Independent Test**: Review future entity contracts and confirm each can include a non-null `tenant_id` and same-tenant relationship validation.

**Acceptance Scenarios**:

1. **Given** a future tenant-owned table is added, **When** it is implemented, **Then** it includes a non-null `tenant_id` and uses the tenant-scoped service pattern.
2. **Given** a future child record references a parent record, **When** it is created, **Then** service-layer validation ensures both records belong to the same tenant.
3. **Given** a future cross-tenant access attempt is blocked, **When** audit logging exists, **Then** the blocked attempt is logged under the actor/requesting user's tenant without leaking victim tenant content.

---

## MVP Scope

- `tenants` table
- `users` table with canonical roles: `staff`, `manager`, `platform_admin`
- User belongs to exactly one tenant for MVP
- Optional platform/system tenant for `platform_admin` users
- Tenant context extracted from authenticated JWT/session
- Tenant-scoped repository/service pattern
- Demo tenant seed data
- Tests for tenant context, tenant-scoped reads/writes, client-supplied `tenant_id` override prevention, and same-tenant relationship rules
- Future compatibility guidance for tenant-owned entities

---

## Out of Scope

- Real WhatsApp API integration
- Calendar syncing
- Auto-sending replies
- Full CRM, billing, subscriptions, or complex permissions
- Document upload and document processing
- pgvector/RAG/vector search implementation
- Intent classifier and risk detection
- Suggested reply generation or reply review
- Follow-up task implementation
- Escalation implementation
- Audit log UI/API implementation
- Dashboard/inbox implementation beyond foundation compatibility
- PostgreSQL Row Level Security hardening

---

## Tenant Isolation Rules

| Rule | Description |
|------|-------------|
| Tenant from auth only | `tenant_id` is derived from JWT/current user. Client-provided `tenant_id` is ignored or rejected by endpoint contract. |
| Non-null tenant ownership | Every tenant-owned future entity must have a non-null `tenant_id`. |
| Tenant-scoped queries | Tenant-owned reads always include `WHERE tenant_id = current_tenant_id` or equivalent service filtering. |
| Cross-tenant IDs | Requests targeting another tenant's record return 403 without exposing record content. |
| Actor-tenant audit policy | When future audit logging is available, blocked cross-tenant attempts are logged under the actor/requesting user's tenant. Victim tenant details are not exposed. |
| Platform admin boundary | `platform_admin` can use platform/demo administration routes only. Tenant content routes reject `platform_admin` unless a future platform-level feature explicitly grants access. |

---

## Same-Tenant Integrity Rules for Later Features

PostgreSQL composite constraints are optional for the MVP, but service-layer validation and integration tests are required when these entities are added:

- `message.tenant_id` must match `conversation.tenant_id`
- `document_chunk.tenant_id` must match `document.tenant_id`
- task `assigned_to_user_id` and `created_by_user_id` must belong to the same tenant as the task
- escalation conversation, triggering message, resolver, and assignee references must belong to the same tenant
- suggested reply conversation, source message, actor user, and source chunks must belong to the same tenant
- audit log actor/resource references must be written without leaking another tenant's content

---

## Acceptance Criteria

| # | Criterion | Verification Method |
|---|-----------|---------------------|
| AC-01 | Demo tenants are seeded with stable IDs/slugs | Migration/seed test |
| AC-02 | Users have non-null `tenant_id` and canonical roles | Schema + seed test |
| AC-03 | JWT/session-derived tenant context is available to protected services | Auth dependency test |
| AC-04 | Client-supplied `tenant_id` cannot override authenticated tenant | Integration test |
| AC-05 | Tenant-scoped list/read operations do not return other-tenant data | Repository/service test |
| AC-06 | Cross-tenant record access returns 403 without content exposure | Integration test |
| AC-07 | Tenant-owned creates inject authenticated tenant context | Repository/service test |
| AC-08 | Same-tenant relationship validation is documented and covered by foundation tests/stubs | Test/spec review |
| AC-09 | `platform_admin` cannot access tenant content routes by default | Role/security test in auth/content specs |
| AC-10 | Future features can add tenant-owned entities without changing the core isolation model | Architecture review |

---

## Dependencies

| Dependency | Type | Notes |
|------------|------|-------|
| JWT authentication | Required | Implemented in Spec 002; this feature defines the tenant context contract it must satisfy. |
| PostgreSQL + SQLAlchemy + Alembic | Required | Shared schema with row-level tenant ownership columns. |
| Later tenant-owned features | Future | Must use the rules in this spec when adding conversations, messages, documents, tasks, escalations, suggested replies, audit logs, RAG, and evaluation data. |

---

## Advanced Requirements Update (Updated Brief — 2026-06)

These requirements harden the tenant-isolation foundation per the updated brief. They do not change the MVP isolation model; they make the existing guarantees explicit and add an optional future-hardening path.

### Functional Requirements (additional)

- **FR-011**: Tenant context MUST be derived **exclusively** from the authenticated JWT for every tenant-owned operation; no endpoint, service, or background job may accept `tenant_id` from a request body, query string, header, or frontend state.
- **FR-012**: Every tenant-owned table MUST carry a non-null `tenant_id`, and tenant filtering MUST be enforced at the **repository/service layer** via a shared tenant-scoped query helper — not left to individual call sites.
- **FR-013**: Vector retrieval (pgvector, Spec 009) MUST apply the same repository-level `tenant_id` filter as relational reads; no retrieval path, including similarity search, can return another tenant's rows.
- **FR-014**: The test suite MUST include explicit **cross-tenant tests** for every tenant-owned entity (read, write, ID-guess, and vector retrieval) asserting Tenant A can never reach Tenant B data (404/403, empty result sets, zero cross-tenant chunks).
- **FR-015** (future hardening, optional): PostgreSQL **Row-Level Security (RLS)** policies MAY be added as defense-in-depth beneath the application-level filter. RLS is **not required** for the MVP; repository filtering remains the primary boundary. When added, policies key on a per-session `tenant_id` GUC set from the JWT.

### Acceptance Criteria (additional)

| # | Criterion | Verification Method |
|---|-----------|---------------------|
| AC-11 | A centralized repository/service tenant filter is applied to all tenant-owned reads/writes | Code review + repository test |
| AC-12 | pgvector retrieval is tenant-filtered; a Tenant A query returns zero Tenant B chunks | Integration test (Spec 009) |
| AC-13 | Cross-tenant tests exist for every tenant-owned entity (incl. vector retrieval) and pass | Test-suite review |
| AC-14 | Optional RLS, when enabled, blocks cross-tenant rows even if the app filter is bypassed; disabled by default, documented as future hardening | Migration/integration test (only when RLS flag on) |

> RLS is recorded here as **future hardening** (previously under Out of Scope); the MVP boundary stays at the JWT-derived, repository-level tenant filter.
