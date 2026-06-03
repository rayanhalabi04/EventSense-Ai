# Tasks: Multi-Tenant Workspace

**Branch**: `001-multi-tenant-workspace` | **Spec**: [spec.md](./spec.md) | **Plan**: [plan.md](./plan.md)

**Input**: Design documents from `specs/001-multi-tenant-workspace/`

**Total tasks**: 76 across 13 phases

**Format**: `[ID] [P?] [Story?] Description — file path`
- `[P]` = parallelizable (different files, no incomplete dependency)
- `[US#]` = maps to user story in spec.md (US1–US5)
- Setup and Foundational phases carry no story label

---

## Phase 1: Project & Backend Foundation

**Purpose**: Scaffold the project layout exactly as defined in `plan.md`. No logic — structure only.

- [ ] T001 Create backend directory structure: `backend/app/{core,models,api/v1,services}/`, `backend/alembic/versions/`, `backend/tests/{unit,integration}/` — as per plan.md Project Structure
- [ ] T002 Initialize FastAPI application entry point with CORS and router registration in `backend/app/main.py`
- [ ] T003 [P] Configure SQLAlchemy 2.x async engine, `AsyncSession` factory, and `get_db` dependency in `backend/app/core/database.py`
- [ ] T004 [P] Initialize Alembic with `alembic init` and configure `env.py` to use `DATABASE_URL` from environment in `backend/alembic/env.py`
- [ ] T005 [P] Create pydantic-settings config class reading `DATABASE_URL`, `JWT_SECRET_KEY`, `JWT_ALGORITHM`, `ACCESS_TOKEN_EXPIRE_MINUTES` in `backend/app/core/config.py`
- [ ] T006 [P] Create frontend project scaffold with `npm create vite@latest frontend -- --template react-ts` and install Tailwind CSS + shadcn/ui in `frontend/`
- [ ] T007 [P] Configure Tailwind CSS (`tailwind.config.ts`) and add base shadcn/ui theme tokens in `frontend/src/index.css`

**Checkpoint**: `uvicorn app.main:app --reload` starts without error; `npm run dev` serves a blank page; `alembic current` outputs current revision.

---

## Phase 2: Database Models & Migrations

**Purpose**: Define all 10 SQLAlchemy models and write the 8 Alembic migration files. No service or endpoint logic. Models are the ground truth for the schema.

**⚠️ CRITICAL**: Complete this phase before Phase 3. All tenant context and repo code depends on these models being importable.

### SQLAlchemy Models

- [ ] T008 [P] Create `Tenant` model with `id` (UUID PK), `name`, `slug` (UNIQUE), `is_active`, `created_at`, `updated_at` in `backend/app/models/tenant.py`
- [ ] T009 [P] Create `UserRole` enum (`super_admin`, `tenant_admin`, `tenant_agent`) and `User` model with `tenant_id` FK, `email`, `hashed_password`, `role`, `full_name`, `is_active` — UNIQUE constraint on `(tenant_id, email)` in `backend/app/models/user.py`
- [ ] T010 [P] Create `ConversationStatus` enum and `Conversation` model with `tenant_id` FK, `client_name`, `client_contact`, `status` in `backend/app/models/conversation.py`
- [ ] T011 [P] Create `MessageDirection` enum and `Message` model with `tenant_id` FK (denormalised), `conversation_id` FK, `direction`, `body`, `sender_user_id`, `sent_at` in `backend/app/models/message.py`
- [ ] T012 [P] Create `DocumentStatus` enum and `Document` model with `tenant_id` FK, `uploaded_by_user_id`, `filename`, `mime_type`, `storage_path`, `status`, `chunk_count` in `backend/app/models/document.py`
- [ ] T013 [P] Create `DocumentChunk` model with `tenant_id` FK, `document_id` FK, `chunk_index`, `content`, `embedding` (`Vector(1536)` from pgvector-sqlalchemy), `token_count` in `backend/app/models/document_chunk.py`
- [ ] T014 [P] Create `SuggestedReplyStatus` enum and `SuggestedReply` model with `tenant_id` FK, `conversation_id` FK, `message_id` FK (nullable), `body`, `source_chunk_ids` (UUID array), `status`, `generated_at`, `acted_on_at`, `acted_on_by_user_id` in `backend/app/models/suggested_reply.py`
- [ ] T015 [P] Create `TaskStatus` enum and `Task` model with `tenant_id` FK, `conversation_id` FK (nullable), `assigned_to_user_id`, `title`, `description`, `status`, `due_at`, `created_by_user_id` in `backend/app/models/task.py`
- [ ] T016 [P] Create `EscalationStatus` enum and `Escalation` model with `tenant_id` FK, `conversation_id` FK, `escalated_by_user_id` (nullable), `reason`, `status`, `resolved_by_user_id`, `resolved_at` in `backend/app/models/escalation.py`
- [ ] T017 [P] Create `AuditOutcome` enum and `AuditLog` model with `tenant_id` FK, `actor_user_id` (nullable), `action`, `resource_type`, `resource_id`, `resource_tenant_id`, `outcome`, `detail` (JSONB), `ip_address`, `created_at` (DEFAULT now(), never set by app code) in `backend/app/models/audit_log.py`

### Alembic Migrations

- [ ] T018 Write migration `0001_create_tenants`: create `tenants` table with all columns and indexes in `backend/alembic/versions/0001_create_tenants.py`
- [ ] T019 Write migration `0002_create_users`: create `user_role` enum, `users` table, UNIQUE index on `(tenant_id, email)` in `backend/alembic/versions/0002_create_users.py`
- [ ] T020 Write migration `0003_create_conversations_messages`: create `conversations` and `messages` tables with all indexes in `backend/alembic/versions/0003_create_conversations_messages.py`
- [ ] T021 Write migration `0004_create_documents_chunks`: run `CREATE EXTENSION IF NOT EXISTS vector`, create `documents` and `document_chunks` tables, add B-tree index on `document_chunks.tenant_id`, add `USING hnsw (embedding vector_cosine_ops)` index in `backend/alembic/versions/0004_create_documents_chunks.py`
- [ ] T022 Write migration `0005_create_suggested_replies`: create `suggested_replies` table with UUID array column for `source_chunk_ids` in `backend/alembic/versions/0005_create_suggested_replies.py`
- [ ] T023 Write migration `0006_create_tasks_escalations`: create `tasks` and `escalations` tables with all indexes in `backend/alembic/versions/0006_create_tasks_escalations.py`
- [ ] T024 Write migration `0007_create_audit_logs`: create `audit_outcome` enum, `audit_logs` table; revoke `UPDATE` and `DELETE` privileges on `audit_logs` from the app DB role in `backend/alembic/versions/0007_create_audit_logs.py`

**Checkpoint**: `alembic upgrade 0007` applies cleanly; `\dt` in psql lists all 9 tables (excluding seed); `\d document_chunks` shows `embedding vector(1536)` column and hnsw index.

---

## Phase 3: Tenant Context & Auth Dependency (Foundational)

**Purpose**: Establish the JWT extraction layer. This is the single source of truth for `tenant_id` on every request — no user story endpoint may proceed without it.

**⚠️ CRITICAL**: Complete before any API endpoint work (Phases 7–11).

- [ ] T025 Define `TenantContext` dataclass with fields `tenant_id: UUID`, `user_id: UUID`, `role: UserRole` in `backend/app/core/tenant_context.py`
- [ ] T026 [P] Implement `decode_jwt(token: str) -> dict` that validates signature, expiry, and required claims (`sub`, `tenant_id`, `role`); raises `HTTPException(401)` on any failure in `backend/app/core/security.py`
- [ ] T027 Implement `get_current_tenant_context` FastAPI dependency: calls `decode_jwt`, constructs `TenantContext`; raises `HTTPException(401)` if claims are missing in `backend/app/core/tenant_context.py`
- [ ] T028 Implement `require_role(*roles: UserRole)` dependency factory that raises `HTTPException(403)` when `ctx.role not in roles` in `backend/app/core/tenant_context.py`
- [ ] T029 Create `backend/tests/conftest.py` with: test `AsyncSession` fixture (rolls back after each test), `make_test_token(tenant_id, user_id, role)` helper that produces a valid signed JWT, `demo_tenants` fixture returning the two seeded tenant UUIDs
- [ ] T030 [P] Implement `TenantContext` React provider: decodes JWT from `localStorage` (client-side only, for display), exposes `{ tenantId, tenantName, role }` via context in `frontend/src/context/TenantContext.tsx`
- [ ] T031 [P] Create `useTenantContext()` hook that reads from `TenantContext` and throws if used outside provider in `frontend/src/hooks/useTenantContext.ts`
- [ ] T032 [P] Create Axios API client: attaches `Authorization: Bearer <token>` header on every request; interceptor that explicitly strips any `tenant_id` field from request body before sending in `frontend/src/api/client.ts`

**Checkpoint**: Import `get_current_tenant_context` from a Python REPL; assert it raises `401` when given an expired token and returns a valid `TenantContext` when given a token from `make_test_token`.

---

## Phase 4: Repository Tenant Filtering (Foundational)

**Purpose**: Wrap all database reads and writes in a single enforcement point. After this phase, no service code can accidentally issue an unfiltered query.

**⚠️ CRITICAL**: Complete before any API endpoint work (Phases 7–11).

- [ ] T033 Implement `ForbiddenError(resource_type, resource_id, actor_tenant_id, resource_tenant_id)` exception class in `backend/app/core/exceptions.py`
- [ ] T034 Implement `TenantScopedRepository(Generic[T])` base class with methods: `get(id, tenant_id) -> T | None`, `get_or_403(id, tenant_id, audit_service) -> T`, `list(tenant_id, **filters) -> list[T]`, `create(tenant_id, **data) -> T`, `update(id, tenant_id, **data) -> T`, `delete(id, tenant_id) -> None` — all methods enforce `tenant_id` equality; `get_or_403` calls `audit_service.log(...)` then raises `ForbiddenError` on mismatch in `backend/app/core/tenant_repo.py`
- [ ] T035 Add `ForbiddenError` exception handler to FastAPI app that returns `{ "detail": "forbidden", "error_code": "CROSS_TENANT_ACCESS" }` with HTTP 403 in `backend/app/main.py`
- [ ] T036 Add body inspection in a FastAPI middleware: if request body contains a `tenant_id` field that differs from `ctx.tenant_id`, log `tenant_id_override_attempt` via `AuditService` and discard the client value in `backend/app/core/tenant_context.py`

**Checkpoint**: Unit test confirms `get_or_403` raises `ForbiddenError` (and does not return data) when `record.tenant_id != ctx.tenant_id`; FastAPI returns `403` + `CROSS_TENANT_ACCESS` error code in response.

---

## Phase 5: Audit Logging (Foundational)

**Purpose**: Implement the append-only audit service. Called by the repo layer (Phase 4) and route handlers for security events.

- [ ] T037 Define `AuditAction` string enum constants: `cross_tenant_access_attempt`, `document_upload`, `reply_generated`, `tenant_id_override_attempt`, `insufficient_role`, `tenant_provisioned` in `backend/app/services/audit_service.py`
- [ ] T038 Implement `AuditService.log(tenant_id, action, outcome, *, actor_user_id=None, resource_type=None, resource_id=None, resource_tenant_id=None, detail=None, ip_address=None)` — issues only `INSERT` against `audit_logs`; never `UPDATE` or `DELETE` in `backend/app/services/audit_service.py`
- [ ] T039 Wire `AuditService` call inside `TenantScopedRepository.get_or_403()`: on `tenant_id` mismatch, call `audit_service.log(actor_tenant_id, AuditAction.cross_tenant_access_attempt, AuditOutcome.blocked, ...)` before raising `ForbiddenError` in `backend/app/core/tenant_repo.py`

**Checkpoint**: Trigger a deliberate `tenant_id` mismatch in a unit test; confirm exactly one `audit_logs` row is inserted with `outcome=blocked` and `action=cross_tenant_access_attempt`.

---

## Phase 6: Seed Demo Tenants (Foundational)

**Purpose**: Provision the two demo tenants with fixed deterministic UUIDs so tests and the quickstart can reference them without a lookup step.

- [ ] T040 Write migration `0008_seed_demo_tenants`: insert `Elegant Weddings` (UUID `a1b2c3d4-0000-0000-0000-000000000001`, slug `elegant-weddings`) and `Royal Events Agency` (UUID `a1b2c3d4-0000-0000-0000-000000000002`, slug `royal-events-agency`); insert one `tenant_admin` user per tenant with bcrypt-hashed demo passwords in `backend/alembic/versions/0008_seed_demo_tenants.py`

**Checkpoint**: `alembic upgrade head`; `SELECT name, slug FROM tenants` returns exactly two rows; `SELECT email, role FROM users` returns two tenant admin users; both rows have non-null `tenant_id`.

---

## Phase 7: User Story 1 — Tenant-Isolated Login & Dashboard

**Goal**: Authenticated planners see only their own tenant's conversations and tasks. Navigating to another tenant's resource returns 403.

**Independent Test**: Log in as `admin@elegant-weddings.demo`, create a conversation. Log in as `admin@royal-events.demo`, confirm conversation list is empty; attempt to `GET /api/v1/conversations/{id}` from the first tenant — expect 403.

- [ ] T041 [US1] Implement `GET /api/v1/tenants/me` returning current user's tenant metadata (name, slug, is_active) from `ctx.tenant_id` in `backend/app/api/v1/tenants.py`
- [ ] T042 [US1] Implement `GET /api/v1/conversations` with `TenantScopedRepository` list, pagination (`page`, `page_size`), optional `status` filter in `backend/app/api/v1/conversations.py`
- [ ] T043 [US1] Implement `POST /api/v1/conversations` — injects `tenant_id` from JWT, never from body in `backend/app/api/v1/conversations.py`
- [ ] T044 [US1] Implement `GET /api/v1/conversations/{conversation_id}` — calls `repo.get_or_403()`, returns 403 + audit log on mismatch in `backend/app/api/v1/conversations.py`
- [ ] T045 [US1] Implement `GET /api/v1/tasks`, `POST /api/v1/tasks`, `PATCH /api/v1/tasks/{task_id}` — all tenant-filtered via `TenantScopedRepository` in `backend/app/api/v1/tasks.py`
- [ ] T046 [P] [US1] Register all v1 routers (`tenants`, `conversations`, `tasks`) on the FastAPI app with `/api/v1` prefix in `backend/app/main.py`
- [ ] T047 [P] [US1] Implement `Dashboard` page: fetches conversations via `GET /api/v1/conversations`, renders list; fetches tasks via `GET /api/v1/tasks`, renders list — uses `useTenantContext()` for display header in `frontend/src/pages/Dashboard.tsx`
- [ ] T048 [P] [US1] Implement `ConversationList` component with loading, empty-state, and error handling in `frontend/src/components/ConversationList.tsx`
- [ ] T049 [P] [US1] Implement `TaskList` component with status badge and due-date display in `frontend/src/components/TaskList.tsx`

**Checkpoint**: Dashboard renders with tenant name in header; creating a conversation in Tenant A is invisible in Tenant B's list; `GET /api/v1/conversations/{tenant_A_id}` while authenticated as Tenant B returns 403.

---

## Phase 8: User Story 2 — Document Upload & RAG Tenant Filtering Stub

**Goal**: Planners upload documents scoped to their tenant. The vector retrieval function enforces `tenant_id` as a mandatory pre-filter. No embedding or chunking logic yet — that is a separate feature.

**Independent Test**: Upload a document as Tenant A (status becomes `pending`). Authenticated as Tenant B, `GET /api/v1/documents/{id}` returns 403. Call `search_chunks(tenant_id=tenant_b_id, ...)` — returns an empty list (no Tenant A chunks ever surface).

- [ ] T050 [US2] Implement `GET /api/v1/documents`, `POST /api/v1/documents` (202 Accepted, sets `status=pending`, injects `tenant_id` from JWT — never from form body), `GET /api/v1/documents/{document_id}` with `get_or_403` in `backend/app/api/v1/documents.py`
- [ ] T051 [US2] Implement `search_chunks(tenant_id: UUID, query_embedding: list[float], k: int = 5) -> list[DocumentChunk]` stub: issues `SELECT ... WHERE tenant_id = :tenant_id ORDER BY embedding <=> :vec LIMIT :k`; raises `ValueError` if `tenant_id` is `None` in `backend/app/core/vector_search.py`
- [ ] T052 [US2] Register documents router on FastAPI app at `/api/v1` prefix in `backend/app/main.py`
- [ ] T053 [P] [US2] Implement `DocumentList` component with status badge (`pending`, `processing`, `ready`, `failed`) in `frontend/src/components/DocumentList.tsx`
- [ ] T054 [P] [US2] Implement `DocumentUpload` component with `multipart/form-data` POST to `/api/v1/documents`; confirms API client never adds `tenant_id` to form data in `frontend/src/components/DocumentUpload.tsx`

**Checkpoint**: `POST /api/v1/documents` returns `{ document_id, status: "pending" }` with `tenant_id` set from JWT; `search_chunks(tenant_id=None, ...)` raises `ValueError`; cross-tenant document GET returns 403.

---

## Phase 9: User Story 4 — Cross-Tenant Blocking & Audit Log Endpoint

**Goal**: All cross-tenant access attempts are blocked at the API layer and appear in the tenant's audit log. Tenant Admin can read their own log; Super Admin can read any tenant's log.

**Independent Test**: Authenticated as Tenant A, request a Tenant B conversation — expect 403. Query `GET /api/v1/audit-logs` as Tenant A admin — the blocked entry appears. Query as Tenant B admin — the entry does not appear.

- [ ] T055 [US4] Implement `POST /api/v1/conversations/{conversation_id}/messages` — tenant-guarded, writes `direction=outbound`; calls `AuditService.log` for the outbound send in `backend/app/api/v1/messages.py`
- [ ] T056 [US4] Implement `POST /api/v1/conversations/{conversation_id}/escalate` — tenant-guarded, creates `Escalation` record in `backend/app/api/v1/escalations.py`
- [ ] T057 [US4] Implement `GET /api/v1/audit-logs` (requires `tenant_admin` role, returns only `ctx.tenant_id` rows) and `GET /api/v1/admin/audit-logs` (requires `super_admin` role, accepts `?tenant_id=uuid`) in `backend/app/api/v1/audit_logs.py`
- [ ] T058 [US4] Register messages, escalations, and audit_logs routers on FastAPI app in `backend/app/main.py`

**Checkpoint**: Trigger a cross-tenant access attempt; verify `audit_logs` row exists with `outcome=blocked`; `GET /api/v1/audit-logs` as the attacker's Tenant Admin shows the row; the victim tenant's admin sees nothing.

---

## Phase 10: User Story 5 — Tenant Provisioning (Super Admin)

**Goal**: Super Admin provisions a new tenant with an initial Tenant Admin user. The new workspace is empty and isolated.

**Independent Test**: `POST /api/v1/admin/tenants` as Super Admin — receives `{ tenant_id, admin_user_id }` 201. Log in as the new admin — all lists return empty. Cross-tenant checks still apply.

- [ ] T059 [US5] Implement `POST /api/v1/admin/tenants` (requires `super_admin` role): creates tenant row, creates Tenant Admin user with bcrypt-hashed password, calls `AuditService.log(..., action=tenant_provisioned)`; returns 409 on duplicate slug/email in `backend/app/api/v1/tenants.py`
- [ ] T060 [US5] Implement `GET /api/v1/admin/tenants` (requires `super_admin` role): returns all tenants with metadata only (no content data) in `backend/app/api/v1/tenants.py`

**Checkpoint**: `POST /api/v1/admin/tenants` by a `tenant_agent` returns 403; by a Super Admin returns 201; new tenant appears in `GET /api/v1/admin/tenants`; new admin's `GET /api/v1/conversations` returns `{ items: [], total: 0 }`.

---

## Phase 11: User Story 3 — Suggested Replies Schema & Stub Endpoints

**Goal**: The `suggested_replies` table and CRUD endpoints exist. AI generation is deferred — this phase only enables manual inspection and status updates.

**Independent Test**: `GET /api/v1/conversations/{id}/suggested-replies` returns an empty list. `PATCH /api/v1/suggested-replies/{id}` for a cross-tenant reply returns 403.

- [ ] T061 [US3] Implement `GET /api/v1/conversations/{conversation_id}/suggested-replies` — tenant-guarded, returns list of reply drafts for the conversation in `backend/app/api/v1/suggested_replies.py`
- [ ] T062 [US3] Implement `PATCH /api/v1/suggested-replies/{reply_id}` — accepts `{ "status": "accepted" | "rejected" }`, calls `get_or_403`, updates `status`, `acted_on_at`, `acted_on_by_user_id` in `backend/app/api/v1/suggested_replies.py`
- [ ] T063 [US3] Register suggested_replies router on FastAPI app in `backend/app/main.py`
- [ ] T064 [P] [US3] Implement `SuggestedRepliesList` component (read-only, shows empty state with "AI generation coming soon" notice) in `frontend/src/components/SuggestedRepliesList.tsx`

**Checkpoint**: All suggested_replies endpoints return valid responses; cross-tenant `PATCH` returns 403; no AI generation code exists in this phase.

---

## Phase 12: Tenant Isolation Tests

**Purpose**: Automated verification of all 10 acceptance criteria from `spec.md`. Each test is independent and uses the `conftest.py` fixtures from T029.

- [ ] T065 [P] Write `test_cross_tenant_conversation_returns_403`: create conversation as Tenant A user; authenticated as Tenant B user, `GET /api/v1/conversations/{id}` → assert 403 (AC-01) in `backend/tests/integration/test_tenant_isolation.py`
- [ ] T066 [P] Write `test_all_records_have_nonnull_tenant_id`: after seed, query each of the 9 tenant-owned tables; assert zero rows with `tenant_id IS NULL` (AC-02) in `backend/tests/integration/test_tenant_isolation.py`
- [ ] T067 [P] Write `test_rag_query_returns_only_own_tenant_chunks`: insert a `DocumentChunk` for Tenant A; call `search_chunks(tenant_id=tenant_b_id, ...)` with a matching embedding; assert result list is empty (AC-03) in `backend/tests/integration/test_tenant_isolation.py`
- [ ] T068 [P] Write `test_body_tenant_id_is_ignored`: `POST /api/v1/conversations` with body `{ "client_name": "X", "tenant_id": "<tenant_b_uuid>" }` authenticated as Tenant A; assert created conversation has `tenant_id == tenant_a_id` (AC-04) in `backend/tests/integration/test_tenant_isolation.py`
- [ ] T069 [P] Write `test_suggested_reply_has_no_cross_tenant_sources`: insert `DocumentChunk` for Tenant A; insert `SuggestedReply` for Tenant B with `source_chunk_ids=[]`; assert no Tenant A chunk IDs appear in any Tenant B reply's `source_chunk_ids` (AC-05) in `backend/tests/integration/test_tenant_isolation.py`
- [ ] T070 [P] Write `test_blocked_request_creates_audit_log_entry`: trigger a cross-tenant `GET`; assert one `audit_logs` row exists with `outcome=blocked`, `action=cross_tenant_access_attempt`, non-null `actor_user_id` and `resource_id` (AC-06) in `backend/tests/integration/test_tenant_isolation.py`
- [ ] T071 [P] Write `test_tenant_admin_cannot_read_other_tenant_audit_log`: insert audit row for Tenant A; `GET /api/v1/audit-logs` authenticated as Tenant B admin; assert response `total == 0` (AC-07) in `backend/tests/integration/test_tenant_isolation.py`
- [ ] T072 [P] Write `test_new_tenant_workspace_is_empty`: provision new tenant via `POST /api/v1/admin/tenants`; call all list endpoints authenticated as the new admin; assert every list returns `total == 0` (AC-08) in `backend/tests/integration/test_tenant_isolation.py`
- [ ] T073 [P] Write `test_partial_upload_leaves_no_chunks`: simulate a document upload that fails mid-write (raise exception after document row created, before chunk insert); assert zero `document_chunks` rows for that `document_id` (AC-09) in `backend/tests/integration/test_tenant_isolation.py`
- [ ] T074 [P] Write `test_demo_tenants_are_seeded_and_isolated`: verify both demo tenants exist in `tenants` table with correct UUIDs; verify each admin can access their own `GET /api/v1/tenants/me`; verify cross-tenant resource access returns 403 (AC-10) in `backend/tests/integration/test_tenant_isolation.py`
- [ ] T075 [P] Write `TenantScopedRepository` unit tests: `get_or_403` raises `ForbiddenError` on mismatch, returns record on match; `create` injects `tenant_id` from argument (not from model default); `list` never returns records from other tenants in `backend/tests/unit/test_tenant_repo.py`
- [ ] T076 [P] Write `AuditService` unit tests: `log()` produces exactly one `INSERT`; calling `log()` twice produces two rows (not an upsert); `created_at` is set by DB default (not by test call time) in `backend/tests/unit/test_audit_service.py`

**Checkpoint**: `pytest tests/ -v` passes all 12 tests with zero failures. No test leaks data to another test (transaction rollback fixture in conftest).

---

## Phase 13: Documentation & Quickstart Validation

**Purpose**: Confirm that `quickstart.md` is accurate end-to-end and that the agent context pointer in `CLAUDE.md` is correct.

- [ ] T077 Run `alembic upgrade head` against a local PostgreSQL instance with pgvector installed; confirm all 8 migrations apply cleanly and `\dt` shows all 10 tables in `backend/alembic/`
- [ ] T078 Execute the `quickstart.md` setup steps end-to-end: start backend, start frontend, verify both demo tenant admin logins work, verify cross-tenant isolation manually with curl
- [ ] T079 [P] Update `quickstart.md` with any corrections discovered during T078 (wrong commands, missing env vars, index creation notes) in `specs/001-multi-tenant-workspace/quickstart.md`
- [ ] T080 [P] Confirm `CLAUDE.md` plan reference points to `specs/001-multi-tenant-workspace/plan.md` and is accurate in `CLAUDE.md`

**Checkpoint**: A developer following `quickstart.md` from scratch can reach a running system with both demo tenants operational and isolated, verified by the manual curl test.

---

## Dependencies & Execution Order

### Phase Dependencies

```
Phase 1 (Foundation)
  └── Phase 2 (Models & Migrations)
        └── Phase 3 (Tenant Context)
              └── Phase 4 (Repo Filtering)
                    └── Phase 5 (Audit Logging)
                          └── Phase 6 (Seed)
                                ├── Phase 7  (US1: Dashboard)
                                ├── Phase 8  (US2: Documents & RAG Stub)
                                ├── Phase 9  (US4: Blocking & Audit API)
                                ├── Phase 10 (US5: Provisioning)
                                └── Phase 11 (US3: Reply Schema)
                                      └── Phase 12 (Isolation Tests)
                                            └── Phase 13 (Quickstart Validation)
```

### User Story Dependencies

| Story | Depends on | Parallel with |
|-------|-----------|---------------|
| US1 (Dashboard) | Phases 1–6 | US2, US4, US5, US3 |
| US2 (Documents & RAG) | Phases 1–6 | US1, US4, US5, US3 |
| US4 (Blocking & Audit) | Phases 1–6 + US1 routes (for cross-tenant trigger) | US2, US5, US3 |
| US5 (Provisioning) | Phases 1–6 | US1, US2, US3 |
| US3 (Reply Schema) | Phases 1–6 | US1, US2, US4, US5 |

### Within Each Phase

- All `[P]`-marked tasks within a phase can run in parallel (they write to different files)
- Sequential tasks within a phase must complete before the next sequential task begins
- Models (T008–T017) are all fully parallel — independent files, no cross-model imports at creation time
- Migrations (T018–T024) must be written sequentially in version order (Alembic chain)

---

## Parallel Execution Examples

### Phase 2 — All models at once

```
Parallel:
  T008 tenant.py
  T009 user.py
  T010 conversation.py
  T011 message.py
  T012 document.py
  T013 document_chunk.py
  T014 suggested_reply.py
  T015 task.py
  T016 escalation.py
  T017 audit_log.py

Then sequential:
  T018 → T019 → T020 → T021 → T022 → T023 → T024 (migrations, in version order)
```

### Phase 7 (US1) — Backend and frontend in parallel

```
Parallel (once T041-T045 backend tasks complete):
  T047 Dashboard.tsx
  T048 ConversationList.tsx
  T049 TaskList.tsx
```

### Phase 12 — All isolation tests in parallel

```
Parallel:
  T065 test AC-01   T069 test AC-05   T073 test AC-09
  T066 test AC-02   T070 test AC-06   T074 test AC-10
  T067 test AC-03   T071 test AC-07   T075 unit: repo
  T068 test AC-04   T072 test AC-08   T076 unit: audit
```

---

## Implementation Strategy

### MVP First (User Story 1 Only)

1. Complete Phases 1–6 (Foundation → Seed) — ~20 tasks
2. Complete Phase 7 (US1: Dashboard) — ~9 tasks
3. **STOP and VALIDATE**: Both demo tenants load isolated dashboards; cross-tenant 403 confirmed
4. Deploy demo if ready

### Incremental Delivery

| Milestone | Phases | Verifiable outcome |
|-----------|--------|--------------------|
| Foundation | 1–6 | Migrations apply; seed tenants exist |
| MVP | + 7 | Isolated dashboard for both demo tenants |
| Documents | + 8 | Document upload scoped to tenant; RAG stub enforces pre-filter |
| Security audit | + 9 | Audit log surfaced in UI; all blocking events logged |
| Provisioning | + 10 | New tenants can be created without code change |
| Reply schema | + 11 | Reply endpoints ready for AI feature to wire into |
| Verified | + 12 | All 10 AC tests pass |
| Shipped | + 13 | Quickstart validated end-to-end |

---

## Notes

- `[P]` = different files, no incomplete dependency — safe to run concurrently
- `[US#]` label maps each task to a user story for traceability back to `spec.md`
- Foundational phases (1–6) carry no story label — they are prerequisites for all stories
- The suggested replies AI generation engine is explicitly **not** in this task list (deferred to AI feature)
- No WhatsApp integration, calendar syncing, or AI classifier tasks are included
- Each phase checkpoint can be used as a demo/review gate before proceeding
