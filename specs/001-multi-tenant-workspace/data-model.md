# Data Model: Multi-Tenant Workspace

**Branch**: `001-multi-tenant-workspace` | **Phase**: 1 — Design

---

## Entity Overview

```
tenants
  └── users (tenant_id FK)
  └── conversations (tenant_id FK)
        └── messages (tenant_id FK, conversation_id FK)
        └── suggested_replies (tenant_id FK, conversation_id FK)
  └── documents (tenant_id FK)
        └── document_chunks (tenant_id FK, document_id FK, pgvector)
  └── tasks (tenant_id FK)
  └── escalations (tenant_id FK)
  └── audit_logs (tenant_id FK)
```

All entities except `tenants` carry `tenant_id` as a non-nullable FK with a DB-level NOT NULL constraint and a CHECK constraint ensuring it is never the nil UUID.

---

## Entity Definitions

### `tenants`

The root entity. One row per agency.

| Column | Type | Constraints | Notes |
|--------|------|-------------|-------|
| `id` | UUID | PK, default gen_random_uuid() | Stable identifier |
| `name` | VARCHAR(255) | NOT NULL, UNIQUE | Display name, e.g. "Elegant Weddings" |
| `slug` | VARCHAR(100) | NOT NULL, UNIQUE | URL-safe identifier, e.g. "elegant-weddings" |
| `is_active` | BOOLEAN | NOT NULL, DEFAULT true | Soft-disable without deleting |
| `created_at` | TIMESTAMPTZ | NOT NULL, DEFAULT now() | |
| `updated_at` | TIMESTAMPTZ | NOT NULL, DEFAULT now() | Auto-updated via trigger |

**Indexes**: PK on `id`, UNIQUE on `slug`.

**Notes**: Super Admin operations only. No tenant-scoped access.

---

### `users`

One row per platform user. Each user belongs to exactly one tenant (MVP assumption).

| Column | Type | Constraints | Notes |
|--------|------|-------------|-------|
| `id` | UUID | PK, default gen_random_uuid() | |
| `tenant_id` | UUID | NOT NULL, FK → tenants.id | Immutable after creation |
| `email` | VARCHAR(320) | NOT NULL | Unique within a tenant (not globally) |
| `hashed_password` | VARCHAR(255) | NOT NULL | bcrypt hash |
| `role` | ENUM | NOT NULL | `super_admin`, `tenant_admin`, `tenant_agent` |
| `full_name` | VARCHAR(255) | NOT NULL | |
| `is_active` | BOOLEAN | NOT NULL, DEFAULT true | |
| `created_at` | TIMESTAMPTZ | NOT NULL, DEFAULT now() | |
| `updated_at` | TIMESTAMPTZ | NOT NULL, DEFAULT now() | |

**Indexes**: PK on `id`; UNIQUE on `(tenant_id, email)`; index on `tenant_id`.

**Notes**: `super_admin` role users are associated with a platform-level sentinel tenant (or `tenant_id = NULL` for super admins — see note below). For MVP simplicity, super admins are assigned to a dedicated internal `platform` tenant that has no content data.

---

### `conversations`

A conversation thread between a client and the agency.

| Column | Type | Constraints | Notes |
|--------|------|-------------|-------|
| `id` | UUID | PK, default gen_random_uuid() | |
| `tenant_id` | UUID | NOT NULL, FK → tenants.id | |
| `client_name` | VARCHAR(255) | NOT NULL | Name of the external client |
| `client_contact` | VARCHAR(320) | | Email or phone |
| `status` | ENUM | NOT NULL, DEFAULT 'open' | `open`, `closed`, `escalated` |
| `created_at` | TIMESTAMPTZ | NOT NULL, DEFAULT now() | |
| `updated_at` | TIMESTAMPTZ | NOT NULL, DEFAULT now() | |

**Indexes**: PK on `id`; index on `tenant_id`; index on `(tenant_id, status)`.

---

### `messages`

Individual messages within a conversation.

| Column | Type | Constraints | Notes |
|--------|------|-------------|-------|
| `id` | UUID | PK, default gen_random_uuid() | |
| `tenant_id` | UUID | NOT NULL, FK → tenants.id | Denormalised for efficient filtering |
| `conversation_id` | UUID | NOT NULL, FK → conversations.id | |
| `direction` | ENUM | NOT NULL | `inbound` (client), `outbound` (agent) |
| `body` | TEXT | NOT NULL | |
| `sender_user_id` | UUID | FK → users.id, NULLABLE | NULL for inbound client messages |
| `sent_at` | TIMESTAMPTZ | NOT NULL, DEFAULT now() | |

**Indexes**: PK on `id`; index on `(tenant_id, conversation_id)`; index on `tenant_id`.

**Notes**: `tenant_id` is denormalised here (it could be derived via `conversation_id → conversations.tenant_id`) to avoid a join on every message query and to ensure the tenant filter is always a direct column check.

---

### `documents`

Uploaded files associated with a tenant's knowledge base.

| Column | Type | Constraints | Notes |
|--------|------|-------------|-------|
| `id` | UUID | PK, default gen_random_uuid() | |
| `tenant_id` | UUID | NOT NULL, FK → tenants.id | |
| `uploaded_by_user_id` | UUID | NOT NULL, FK → users.id | |
| `filename` | VARCHAR(500) | NOT NULL | Original filename |
| `mime_type` | VARCHAR(100) | NOT NULL | e.g. `application/pdf` |
| `storage_path` | VARCHAR(1000) | NOT NULL | Internal storage reference |
| `status` | ENUM | NOT NULL, DEFAULT 'pending' | `pending`, `processing`, `ready`, `failed` |
| `chunk_count` | INTEGER | NULLABLE | Populated after successful processing |
| `created_at` | TIMESTAMPTZ | NOT NULL, DEFAULT now() | |
| `updated_at` | TIMESTAMPTZ | NOT NULL, DEFAULT now() | |

**Indexes**: PK on `id`; index on `tenant_id`; index on `(tenant_id, status)`.

---

### `document_chunks`

Chunks of text extracted from documents, with vector embeddings for RAG retrieval.

| Column | Type | Constraints | Notes |
|--------|------|-------------|-------|
| `id` | UUID | PK, default gen_random_uuid() | |
| `tenant_id` | UUID | NOT NULL, FK → tenants.id | Mandatory pre-filter column for pgvector queries |
| `document_id` | UUID | NOT NULL, FK → documents.id | |
| `chunk_index` | INTEGER | NOT NULL | Ordinal position within the document |
| `content` | TEXT | NOT NULL | Raw chunk text |
| `embedding` | VECTOR(1536) | NOT NULL | Embedding dimension matches chosen model |
| `token_count` | INTEGER | NOT NULL | For context window budgeting |
| `created_at` | TIMESTAMPTZ | NOT NULL, DEFAULT now() | |

**Indexes**:
- PK on `id`
- B-tree index on `tenant_id`
- B-tree index on `document_id`
- `USING hnsw (embedding vector_cosine_ops)` — shared across tenants, pre-filtered by `tenant_id` in queries

**Notes**: The embedding dimension (1536) matches OpenAI `text-embedding-3-small`; update if a different model is chosen. No partial chunks may exist — the document ingestion transaction writes all chunks for a document atomically or rolls back entirely.

---

### `suggested_replies`

AI-generated reply drafts attached to a conversation.

| Column | Type | Constraints | Notes |
|--------|------|-------------|-------|
| `id` | UUID | PK, default gen_random_uuid() | |
| `tenant_id` | UUID | NOT NULL, FK → tenants.id | |
| `conversation_id` | UUID | NOT NULL, FK → conversations.id | |
| `message_id` | UUID | NULLABLE, FK → messages.id | The inbound message this replies to |
| `body` | TEXT | NOT NULL | Generated reply text |
| `source_chunk_ids` | UUID[] | NOT NULL, DEFAULT '{}' | IDs of document_chunks used as context |
| `status` | ENUM | NOT NULL, DEFAULT 'pending' | `pending`, `accepted`, `rejected` |
| `generated_at` | TIMESTAMPTZ | NOT NULL, DEFAULT now() | |
| `acted_on_at` | TIMESTAMPTZ | NULLABLE | When agent accepted/rejected |
| `acted_on_by_user_id` | UUID | NULLABLE, FK → users.id | |

**Indexes**: PK on `id`; index on `(tenant_id, conversation_id)`; index on `tenant_id`.

---

### `tasks`

Follow-up tasks created by agents, associated with a conversation.

| Column | Type | Constraints | Notes |
|--------|------|-------------|-------|
| `id` | UUID | PK, default gen_random_uuid() | |
| `tenant_id` | UUID | NOT NULL, FK → tenants.id | |
| `conversation_id` | UUID | NULLABLE, FK → conversations.id | |
| `assigned_to_user_id` | UUID | NULLABLE, FK → users.id | |
| `title` | VARCHAR(500) | NOT NULL | |
| `description` | TEXT | NULLABLE | |
| `status` | ENUM | NOT NULL, DEFAULT 'open' | `open`, `in_progress`, `done`, `cancelled` |
| `due_at` | TIMESTAMPTZ | NULLABLE | |
| `created_by_user_id` | UUID | NOT NULL, FK → users.id | |
| `created_at` | TIMESTAMPTZ | NOT NULL, DEFAULT now() | |
| `updated_at` | TIMESTAMPTZ | NOT NULL, DEFAULT now() | |

**Indexes**: PK on `id`; index on `tenant_id`; index on `(tenant_id, status)`.

---

### `escalations`

Conversations escalated for human review.

| Column | Type | Constraints | Notes |
|--------|------|-------------|-------|
| `id` | UUID | PK, default gen_random_uuid() | |
| `tenant_id` | UUID | NOT NULL, FK → tenants.id | |
| `conversation_id` | UUID | NOT NULL, FK → conversations.id | |
| `escalated_by_user_id` | UUID | NULLABLE, FK → users.id | NULL if auto-escalated |
| `reason` | TEXT | NOT NULL | |
| `status` | ENUM | NOT NULL, DEFAULT 'open' | `open`, `resolved` |
| `resolved_by_user_id` | UUID | NULLABLE, FK → users.id | |
| `created_at` | TIMESTAMPTZ | NOT NULL, DEFAULT now() | |
| `resolved_at` | TIMESTAMPTZ | NULLABLE | |

**Indexes**: PK on `id`; index on `tenant_id`; index on `(tenant_id, status)`.

---

### `audit_logs`

Immutable security and activity log. Append-only at the application layer.

| Column | Type | Constraints | Notes |
|--------|------|-------------|-------|
| `id` | UUID | PK, default gen_random_uuid() | |
| `tenant_id` | UUID | NOT NULL, FK → tenants.id | |
| `actor_user_id` | UUID | NULLABLE, FK → users.id | NULL for system-generated events |
| `action` | VARCHAR(100) | NOT NULL | e.g. `cross_tenant_access_attempt`, `document_upload`, `reply_generated` |
| `resource_type` | VARCHAR(100) | NULLABLE | e.g. `conversation`, `document`, `message` |
| `resource_id` | UUID | NULLABLE | The targeted resource |
| `resource_tenant_id` | UUID | NULLABLE | Tenant of the targeted resource (for cross-tenant events) |
| `outcome` | ENUM | NOT NULL | `allowed`, `blocked`, `error` |
| `detail` | JSONB | NULLABLE | Structured extra context |
| `ip_address` | INET | NULLABLE | |
| `created_at` | TIMESTAMPTZ | NOT NULL, DEFAULT now() | Set by DB, never by application |

**Indexes**: PK on `id`; index on `tenant_id`; index on `(tenant_id, action)`; index on `created_at DESC`.

**Immutability enforcement**: No `UPDATE` or `DELETE` is ever issued against this table. A PostgreSQL rule or trigger can enforce this as a post-MVP hardening step.

---

## Alembic Migration Plan

| Migration | Description |
|-----------|-------------|
| `0001_create_tenants` | `tenants` table |
| `0002_create_users` | `users` table + role enum |
| `0003_create_conversations_messages` | `conversations` + `messages` tables |
| `0004_create_documents_chunks` | `documents` + `document_chunks` tables + pgvector extension + hnsw index |
| `0005_create_suggested_replies` | `suggested_replies` table |
| `0006_create_tasks_escalations` | `tasks` + `escalations` tables |
| `0007_create_audit_logs` | `audit_logs` table + outcome enum |
| `0008_seed_demo_tenants` | Insert Elegant Weddings + Royal Events Agency with fixed UUIDs |

---

## Seed Data

```
Tenant: Elegant Weddings
  id:   a1b2c3d4-0000-0000-0000-000000000001
  slug: elegant-weddings

Tenant: Royal Events Agency
  id:   a1b2c3d4-0000-0000-0000-000000000002
  slug: royal-events-agency

Tenant Admin — Elegant Weddings:
  email: admin@elegant-weddings.demo
  role: tenant_admin

Tenant Admin — Royal Events Agency:
  email: admin@royal-events.demo
  role: tenant_admin
```
