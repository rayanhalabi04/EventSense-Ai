# Data Model: Multi-Tenant Workspace

**Branch**: `001-multi-tenant-workspace` | **Phase**: 1 - Design

---

## Schema Scope

Spec 001 defines only the foundation tables:

```
tenants
  └── users (tenant_id FK)
```

Later features add conversations, messages, documents, document chunks, suggested replies, tasks, escalations, audit logs, RAG/evaluation rows, and related indexes. Those later tables must follow the tenant rules defined here.

---

## `tenants`

One row per agency or system tenant.

| Column | Type | Constraints | Notes |
|--------|------|-------------|-------|
| `id` | UUID | PK, default generated UUID | Stable tenant identifier |
| `name` | VARCHAR(255) | NOT NULL, UNIQUE | Display name, e.g. "Elegant Weddings" |
| `slug` | VARCHAR(100) | NOT NULL, UNIQUE | URL-safe identifier |
| `kind` | ENUM | NOT NULL, DEFAULT `customer` | `customer` or `platform` |
| `is_active` | BOOLEAN | NOT NULL, DEFAULT true | Soft-disable without deleting |
| `created_at` | TIMESTAMPTZ | NOT NULL, DEFAULT now() | |
| `updated_at` | TIMESTAMPTZ | NOT NULL, DEFAULT now() | |

**Indexes**: PK on `id`; UNIQUE on `slug`; optional index on `kind`.

**Notes**:
- Customer tenants own event-business data.
- A platform/system tenant may be seeded for `platform_admin` users.
- Platform tenant users do not gain access to customer tenant content by default.

---

## `users`

One row per platform user. Each user belongs to exactly one tenant for the MVP.

| Column | Type | Constraints | Notes |
|--------|------|-------------|-------|
| `id` | UUID | PK, default generated UUID | |
| `tenant_id` | UUID | NOT NULL, FK -> tenants.id | Immutable after creation for MVP |
| `email` | VARCHAR(320) | NOT NULL | Unique within a tenant |
| `hashed_password` | VARCHAR(255) | NOT NULL | bcrypt hash |
| `role` | ENUM | NOT NULL | `staff`, `manager`, `platform_admin` |
| `full_name` | VARCHAR(255) | NOT NULL | |
| `is_active` | BOOLEAN | NOT NULL, DEFAULT true | |
| `created_at` | TIMESTAMPTZ | NOT NULL, DEFAULT now() | |
| `updated_at` | TIMESTAMPTZ | NOT NULL, DEFAULT now() | |

**Indexes**: PK on `id`; UNIQUE on `(tenant_id, email)`; index on `tenant_id`.

**Role rules**:
- `staff` and `manager` belong to customer tenants.
- `platform_admin` belongs to the platform/system tenant.
- Content routes added later must reject `platform_admin` unless a future feature explicitly grants read access.

---

## UserRole Enum

```
staff
manager
platform_admin
```

These are canonical from Spec 001 onward. No role-rename migration should be needed in Spec 002.

---

## Alembic Migration Plan

| Migration | Description |
|-----------|-------------|
| `0001_create_tenants` | Create `tenant_kind` enum and `tenants` table |
| `0002_create_users` | Create `user_role` enum and `users` table |
| `0003_seed_demo_tenants` | Insert demo tenants, demo manager users, and optional platform tenant/admin |

---

## Seed Data

```
Tenant: Elegant Weddings
  id:   a1b2c3d4-0000-0000-0000-000000000001
  slug: elegant-weddings
  kind: customer

Manager user:
  email: admin@elegant-weddings.demo
  role: manager

Tenant: Royal Events Agency
  id:   a1b2c3d4-0000-0000-0000-000000000002
  slug: royal-events-agency
  kind: customer

Manager user:
  email: admin@royal-events.demo
  role: manager

Tenant: EventSense Platform
  id:   a1b2c3d4-0000-0000-0000-0000000000ff
  slug: platform
  kind: platform

Platform admin user:
  email: platform-admin@eventsense.demo
  role: platform_admin
```

Platform tenant seed is useful for demos and auth tests. It must not be treated as a customer tenant.

---

## Future Tenant-Owned Tables

Later features must add `tenant_id UUID NOT NULL` to tenant-owned tables. Examples:

- `conversations`
- `messages`
- `documents`
- `document_chunks`
- `suggested_replies`
- `tasks`
- `escalations`
- `audit_logs`
- RAG/evaluation tables

Same-tenant relationship checks are required in services/tests. Composite database constraints can be added later if needed, but are not required for this MVP foundation.

---

## Same-Tenant Integrity Rules

| Future relationship | Rule |
|---------------------|------|
| `messages.conversation_id` | message tenant must match conversation tenant |
| `document_chunks.document_id` | chunk tenant must match document tenant |
| task assignee/creator/conversation | all referenced rows must match task tenant |
| escalation conversation/message/users | all referenced rows must match escalation tenant |
| suggested reply conversation/message/chunks/users | all referenced rows must match suggested reply tenant |
| audit logs | actor tenant owns blocked-attempt log; victim tenant content is not copied into detail |

Service-layer validation plus integration tests is acceptable for MVP.
