# Tasks: Multi-Tenant Workspace

**Branch**: `001-multi-tenant-workspace` | **Spec**: [spec.md](./spec.md) | **Plan**: [plan.md](./plan.md)

**Total tasks**: 32 across 7 phases

**Format**: `[ID] [P?] [Story?] Description - file path`

---

## Phase 1: Backend Foundation

**Purpose**: Create the minimal backend structure needed for tenant foundation work.

- [ ] T001 Create backend directories `backend/app/{core,models,api/v1}/`, `backend/alembic/versions/`, and `backend/tests/{unit,integration}/`
- [ ] T002 Initialize FastAPI app and v1 router registration in `backend/app/main.py`
- [ ] T003 [P] Configure SQLAlchemy 2.x async engine, `AsyncSession`, and `get_db` dependency in `backend/app/core/database.py`
- [ ] T004 [P] Configure Alembic to read `DATABASE_URL` from environment in `backend/alembic/env.py`
- [ ] T005 [P] Create settings class for `DATABASE_URL`, `JWT_SECRET_KEY`, `JWT_ALGORITHM`, and token expiry in `backend/app/core/config.py`

**Checkpoint**: App imports cleanly; Alembic can connect to the configured database.

---

## Phase 2: Tenant and User Schema

**Purpose**: Create only the foundation schema. Later feature tables are not part of Spec 001.

- [ ] T006 [P] Create `TenantKind` enum (`customer`, `platform`) and `Tenant` model in `backend/app/models/tenant.py`
- [ ] T007 [P] Create `UserRole` enum (`staff`, `manager`, `platform_admin`) and `User` model with non-null `tenant_id` in `backend/app/models/user.py`
- [ ] T008 Write migration `0001_create_tenants` for `tenants` and `tenant_kind` in `backend/alembic/versions/0001_create_tenants.py`
- [ ] T009 Write migration `0002_create_users` for `users`, `user_role`, `(tenant_id, email)` uniqueness, and indexes in `backend/alembic/versions/0002_create_users.py`

**Checkpoint**: `alembic upgrade 0002` applies; `tenants` and `users` exist with canonical roles.

---

## Phase 3: Tenant Context and Role Contract

**Purpose**: Establish the tenant context contract that Spec 002 auth will complete.

- [ ] T010 Define `TenantContext(tenant_id: UUID, user_id: UUID, role: UserRole)` in `backend/app/core/tenant_context.py`
- [ ] T011 Implement `decode_jwt(token: str) -> dict` placeholder/utility that validates required claims for tests in `backend/app/core/security.py`
- [ ] T012 Implement `get_current_tenant_context` dependency that builds context from JWT claims in `backend/app/core/tenant_context.py`
- [ ] T013 Implement `require_role(*roles: UserRole)` dependency factory in `backend/app/core/tenant_context.py`
- [ ] T014 Create test helpers: `make_test_token`, `demo_tenants`, and rollback session fixture in `backend/tests/conftest.py`

**Checkpoint**: Protected dependency returns `TenantContext` from a valid token and 401 for invalid tokens.

---

## Phase 4: Tenant-Scoped Repository and Validation Helpers

**Purpose**: Provide a reusable access pattern for later tenant-owned models.

- [ ] T015 Implement `ForbiddenError` with `CROSS_TENANT_ACCESS` response metadata in `backend/app/core/exceptions.py`
- [ ] T016 Implement `TenantScopedRepository` with `get`, `get_or_403`, `list`, `create`, `update`, and `delete` methods in `backend/app/core/tenant_repo.py`
- [ ] T017 Ensure `create()` injects authenticated `tenant_id` and rejects conflicting client-provided `tenant_id` in `backend/app/core/tenant_repo.py`
- [ ] T018 Implement `validate_same_tenant(*records)` helper for future relationship checks in `backend/app/core/tenant_repo.py`
- [ ] T019 Register `ForbiddenError` handler in `backend/app/main.py`

**Checkpoint**: Unit tests can prove tenant filtering and same-tenant validation without implementing future feature tables.

---

## Phase 5: Demo Tenant Seeds

**Purpose**: Seed the demo tenant identities used by specs 002-004.

- [ ] T020 Write migration `0003_seed_demo_tenants` inserting Elegant Weddings and Royal Events Agency with stable UUIDs/slugs in `backend/alembic/versions/0003_seed_demo_tenants.py`
- [ ] T021 In the same seed migration, insert one `manager` user per demo tenant with bcrypt-hashed demo passwords
- [ ] T022 In the same seed migration, insert optional platform/system tenant (`slug=platform`, `kind=platform`) and `platform_admin` user for demo administration

**Checkpoint**: `alembic upgrade head` seeds two customer tenants, two manager users, and optional platform admin.

---

## Phase 6: Foundation API

**Purpose**: Add only metadata endpoints required for tenant context and demo administration.

- [ ] T023 [US1] Implement `GET /api/v1/tenants/me` for `staff` and `manager` in `backend/app/api/v1/tenants.py`
- [ ] T024 [US3] Implement `GET /api/v1/admin/tenants` for `platform_admin`, returning metadata only in `backend/app/api/v1/tenants.py`
- [ ] T025 Register tenants router in `backend/app/main.py`
- [ ] T026 Add explicit contract validation that client-supplied `tenant_id` is not accepted by foundation endpoints in `backend/app/api/v1/tenants.py`

**Checkpoint**: Customer users can fetch their tenant metadata; platform admin can list tenant metadata but not tenant content.

---

## Phase 7: Tests and Documentation Validation

**Purpose**: Prove the foundation is safe before generating later feature tasks.

- [ ] T027 [P] Write `test_demo_tenants_seeded` in `backend/tests/integration/test_tenant_foundation.py`
- [ ] T028 [P] Write `test_tenant_context_from_jwt` in `backend/tests/integration/test_tenant_foundation.py`
- [ ] T029 [P] Write `test_client_tenant_id_cannot_override_context` in `backend/tests/integration/test_tenant_foundation.py`
- [ ] T030 [P] Write `test_repo_list_filters_by_tenant` and `test_repo_get_or_403_blocks_cross_tenant` in `backend/tests/unit/test_tenant_repo.py`
- [ ] T031 [P] Write `test_create_injects_authenticated_tenant` and `test_validate_same_tenant_rejects_mismatch` in `backend/tests/unit/test_tenant_repo.py`
- [ ] T032 Validate `quickstart.md` against the narrowed Spec 001 scope and update commands/expected output if needed

**Checkpoint**: Foundation tests pass; Spec 001 no longer includes document, RAG, suggested reply, task, escalation, inbox, or audit-log implementation tasks.

---

## Dependencies and Order

```
Phase 1 -> Phase 2 -> Phase 3 -> Phase 4 -> Phase 5 -> Phase 6 -> Phase 7
```

Later specs can start only after this foundation is implemented or consciously stubbed:

- Spec 002 auth completes login/refresh and role enforcement.
- Spec 003 message simulator adds conversations/messages.
- Spec 004 inbox reads conversations/messages.
- Later specs add documents, RAG, suggested replies, tasks, escalations, audit logs, guardrails, and evaluation.
