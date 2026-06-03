# Tasks: Authentication and Roles

**Branch**: `002-auth-and-roles` | **Spec**: [spec.md](./spec.md) | **Plan**: [plan.md](./plan.md)

**Depends on**: Spec 001 Multi-Tenant Workspace — `users`, `tenants`, `audit_logs` tables, `AuditService`, `TenantContext`, `require_role` stubs are assumed to exist. Tasks here do **not** re-implement that schema.

**Total tasks**: 44 across 8 phases

**Format**: `[ID] [P?] [Story?] Description — file path`
- `[P]` = parallelizable (different files, no incomplete dependency)
- `[US#]` = maps to user story in spec.md
- Setup and Foundational phases carry no story label

---

## Phase 1: Setup

**Purpose**: Add new dependencies, create the schemas package, and write the role-rename migration. No logic.

- [ ] T001 Add `python-jose[cryptography]` and `passlib[bcrypt]` to backend dependencies in `backend/requirements.txt` (verify they are not already present from Spec 001)
- [ ] T002 [P] Add `jwt-decode` to frontend dependencies in `frontend/package.json` and run `npm install`
- [ ] T003 [P] Create `backend/app/schemas/` package: add `backend/app/schemas/__init__.py`, empty `backend/app/schemas/auth.py`, and empty `backend/app/schemas/user.py`
- [ ] T004 Write Alembic migration `0009_rename_user_roles`: use raw SQL to `ALTER TYPE user_role RENAME VALUE 'tenant_agent' TO 'staff'`, `'tenant_admin' TO 'manager'`, `'super_admin' TO 'platform_admin'`; also `UPDATE users SET role='manager' WHERE role='tenant_admin'` for the two seeded admin users in `backend/alembic/versions/0009_rename_user_roles.py`
- [ ] T005 [P] Create `backend/scripts/seed_staff_users.py`: inserts one `staff`-role user per demo tenant (`staff@elegant-weddings.demo` / `staff-password-1` and `staff@royal-events.demo` / `staff-password-2`) using bcrypt-hashed passwords in `backend/scripts/seed_staff_users.py`

**Checkpoint**: `alembic upgrade head` applies migration 0009 without error; `SELECT unnest(enum_range(NULL::user_role))` returns `staff`, `manager`, `platform_admin`.

---

## Phase 2: Foundational — Security Module and Role Infrastructure

**Purpose**: All auth logic depends on this phase. `security.py`, the role enum update, `get_current_tenant_context` completion, `require_role`, audit constants, and Pydantic schemas must all be in place before any endpoint or test can run.

**⚠️ CRITICAL**: No user story work can begin until this phase is complete.

- [ ] T006 Update `UserRole` enum in `backend/app/models/user.py` to use canonical string values `"staff"`, `"manager"`, `"platform_admin"` — replacing the Spec 001 placeholder values `"tenant_agent"`, `"tenant_admin"`, `"super_admin"`
- [ ] T007 Implement `hash_password(plain: str) -> str` and `verify_password(plain: str, hashed: str) -> bool` using `passlib.context.CryptContext(schemes=["bcrypt"], deprecated="auto")` in `backend/app/core/security.py`
- [ ] T008 Implement `create_access_token(sub: str, tenant_id: str, role: str, expires_delta: timedelta | None = None) -> str`: builds payload `{sub, tenant_id, role, exp, iat, jti}`, signs with `JWT_SECRET_KEY` using HS256 via `python-jose`, defaults to 60-minute expiry in `backend/app/core/security.py`
- [ ] T009 Implement `decode_jwt(token: str) -> TokenData`: verifies HS256 signature and `exp` claim using `python-jose`; raises `HTTPException(401, {"detail": "Invalid token", "error_code": "INVALID_TOKEN"})` on bad signature and `HTTPException(401, {"detail": "Token expired", "error_code": "TOKEN_EXPIRED"})` on expiry; raises `HTTPException(401, ...)` if `sub`, `tenant_id`, or `role` claims are missing in `backend/app/core/security.py`
- [ ] T010 Complete `get_current_tenant_context` FastAPI dependency (was a stub in Spec 001): call `security.decode_jwt(token)`, construct and return `TenantContext(tenant_id=UUID(data.tenant_id), user_id=UUID(data.sub), role=UserRole(data.role))` in `backend/app/core/tenant_context.py`
- [ ] T011 Implement `require_role(*allowed_roles: UserRole)` dependency factory (completes Spec 001 stub): if `ctx.role not in allowed_roles` call `AuditService.log(...)` with `action=AuditAction.insufficient_role` then raise `HTTPException(403, {"detail": "forbidden", "error_code": "INSUFFICIENT_ROLE"})` in `backend/app/core/tenant_context.py`
- [ ] T012 [P] Add auth-specific `AuditAction` constants to `backend/app/services/audit_service.py`: `login_success`, `login_failure`, `login_failure_inactive`, `insufficient_role`, `platform_admin_content_attempt`, `token_refresh`, `logout`
- [ ] T013 [P] Define Pydantic schemas `LoginRequest(email: EmailStr, password: str, tenant_slug: str)`, `TokenResponse(access_token: str, token_type: str = "bearer", expires_in: int)`, `TokenData(sub: UUID, tenant_id: UUID, role: UserRole, exp: int, iat: int, jti: UUID)` in `backend/app/schemas/auth.py`
- [ ] T014 [P] Define Pydantic schema `UserResponse(id: UUID, email: str, full_name: str, role: UserRole, tenant_id: UUID, is_active: bool)` with `model_config = ConfigDict(from_attributes=True)` in `backend/app/schemas/user.py`
- [ ] T015 Update `backend/tests/conftest.py` `make_test_token` helper (Spec 001 stub) to call `security.create_access_token(sub=str(user_id), tenant_id=str(tenant_id), role=role.value)` so all existing integration tests use the real JWT implementation

**Checkpoint**: `from app.core.security import create_access_token, decode_jwt, verify_password` imports cleanly; `decode_jwt(create_access_token("uid", "tid", "staff"))` returns a `TokenData` instance; `verify_password("wrong", hash_password("right"))` returns `False`.

---

## Phase 3: User Story 1 — Staff Login and Authenticated Session (Priority: P1)

**Goal**: A Staff user submits valid credentials and receives a signed JWT with correct `user_id`, `tenant_id`, and `role=staff` claims. Protected routes return 401 without a valid token.

**Independent Test**: POST `/auth/token` with valid Staff credentials → decode token → assert `sub`, `tenant_id`, `role` are correct. Then GET `/api/v1/conversations` without token → assert 401.

- [ ] T016 [US1] Implement `POST /auth/token` login handler in `backend/app/api/auth.py`: (1) query `tenants WHERE slug=:tenant_slug AND is_active=true` — 401 + `login_failure` audit on miss; (2) query `users WHERE email=:email AND tenant_id=:tenant_id` — 401 + `login_failure` audit on miss; (3) check `user.is_active` — 401 + `login_failure_inactive` audit if not; (4) `security.verify_password(password, user.hashed_password)` — 401 + `login_failure` audit on fail; (5) `security.create_access_token(...)` — 200 + `login_success` audit on success
- [ ] T017 [US1] Implement `GET /auth/me` handler: fetch `User` by `ctx.user_id` from DB, return `UserResponse` in `backend/app/api/auth.py`
- [ ] T018 [US1] Create `auth` `APIRouter` and mount it at `/auth` prefix (without `/api/v1`) in `backend/app/main.py`; also register `POST /auth/refresh` and `POST /auth/logout` as stubs returning 501 for now (to be completed in Phase 5)
- [ ] T019 [P] [US1] Implement `AuthContext` React provider in `frontend/src/context/AuthContext.tsx`: on mount read `sessionStorage.getItem("access_token")` and decode with `jwt-decode`; expose `{ token, user: { userId, tenantId, role, exp }, isAuthenticated }`; `login(email, password, tenantSlug)` calls `POST /auth/token`, stores token in `sessionStorage` + state; `logout()` clears `sessionStorage` + state + navigates to `/login`
- [ ] T020 [P] [US1] Implement `useAuth()` hook in `frontend/src/hooks/useAuth.ts`: consumes `AuthContext`, throws `Error("useAuth must be used within AuthProvider")` if called outside provider
- [ ] T021 [P] [US1] Add Axios 401 interceptor to `frontend/src/api/client.ts`: on any 401 response call `logout()` from `AuthContext` and `navigate("/login")`; ensure the interceptor does **not** retry the request
- [ ] T022 [US1] Build `LoginPage` in `frontend/src/pages/LoginPage.tsx`: form with `email`, `password`, and `tenant_slug` fields; on submit calls `useAuth().login(...)`; shows inline error message on 401; redirects to `/dashboard` on success; redirect to `/dashboard` if already authenticated
- [ ] T023 [US1] Wrap `App` router in `<AuthProvider>` and add `/login` route pointing to `LoginPage`; add a minimal `/dashboard` route (stub page showing "Dashboard — authenticated") in `frontend/src/App.tsx`
- [ ] T024 [P] [US1] Write security unit tests in `backend/tests/unit/test_security.py`: `test_hash_and_verify_password_roundtrip`, `test_wrong_password_fails_verify`, `test_create_access_token_contains_all_required_claims` (sub, tenant_id, role, exp, iat, jti), `test_create_access_token_exp_is_60_minutes_from_now`, `test_decode_jwt_returns_correct_token_data`, `test_decode_jwt_rejects_expired_token`, `test_decode_jwt_rejects_tampered_signature`
- [ ] T025 [US1] Write login integration tests in `backend/tests/integration/test_auth.py`: `test_login_success_returns_token_with_correct_claims` (AC-01), `test_login_failure_wrong_password_returns_401` (AC-02), `test_login_failure_unknown_email_returns_401` (AC-02), `test_login_failure_inactive_user_returns_401` (AC-03), `test_login_failure_inactive_tenant_returns_401` (AC-04), `test_missing_token_returns_401_missing_token_code`, `test_tampered_token_returns_401_invalid_token_code`, `test_get_me_returns_correct_user_profile`, `test_login_failure_writes_audit_log_entry` (AC-09), `test_body_tenant_id_field_is_ignored_at_login` (AC-12)

**Checkpoint**: `pytest tests/unit/test_security.py tests/integration/test_auth.py::test_login_success_returns_token_with_correct_claims -v` passes; curl login returns a decodable JWT; GET `/auth/me` with valid token returns user profile.

---

## Phase 4: User Story 2 — Role-Based Access Enforcement (Priority: P1)

**Goal**: Staff role cannot access Manager-only routes (403). Manager role can access both Staff and Manager routes. No client-side action can change the role claim.

**Independent Test**: Login as Staff, GET `/api/v1/audit-logs` → 403 with `error_code: INSUFFICIENT_ROLE`. Login as Manager, same route → 200. Verify audit log has one entry for the Staff 403.

- [ ] T026 [US2] Apply `require_role(UserRole.staff, UserRole.manager)` to all Staff+Manager routes in Spec 001 routers: replace `Depends(get_current_tenant_context)` with `Depends(require_role(UserRole.staff, UserRole.manager))` on all handlers in `backend/app/api/v1/conversations.py`, `backend/app/api/v1/messages.py`, `backend/app/api/v1/tasks.py`, `backend/app/api/v1/escalations.py`, `backend/app/api/v1/suggested_replies.py`
- [ ] T027 [US2] Apply `require_role(UserRole.manager)` to Manager-only routes: `GET /api/v1/audit-logs` in `backend/app/api/v1/audit_logs.py`, `POST /api/v1/documents`, `GET /api/v1/documents`, `GET /api/v1/documents/{id}` in `backend/app/api/v1/documents.py`, and `POST /api/v1/escalations/{id}/resolve` in `backend/app/api/v1/escalations.py`
- [ ] T028 [US2] Apply `require_role(UserRole.platform_admin)` to all platform admin routes: `POST /api/v1/admin/tenants`, `GET /api/v1/admin/tenants`, `PATCH /api/v1/admin/tenants/{id}`, `GET /api/v1/admin/audit-logs` in `backend/app/api/v1/tenants.py`
- [ ] T029 [P] [US2] Implement `RoleGuard` component in `frontend/src/components/RoleGuard.tsx`: accepts `allowedRoles: Array<"staff" | "manager" | "platform_admin">` and `children`; if `user.role` not in `allowedRoles` renders `<ForbiddenPage />`; renders children if role matches
- [ ] T030 [P] [US2] Implement `ForbiddenPage` in `frontend/src/pages/ForbiddenPage.tsx`: displays "Access denied — you don't have permission to view this page" with a "Go back" button; no additional logic
- [ ] T031 [US2] Write role enforcement integration tests in `backend/tests/integration/test_roles.py`: `test_staff_cannot_access_audit_logs_returns_403` (AC-05), `test_staff_cannot_access_documents_returns_403` (AC-05), `test_manager_can_access_audit_logs_returns_200` (AC-06), `test_manager_can_access_conversations_returns_200` (AC-06), `test_platform_admin_cannot_access_conversations_returns_403` (AC-07), `test_platform_admin_cannot_access_documents_returns_403` (AC-07), `test_role_violation_response_contains_insufficient_role_error_code`, `test_role_violation_writes_audit_log_with_required_and_actual_role` (AC-10)

**Checkpoint**: `pytest tests/integration/test_roles.py -v` passes all 8 tests; a manually crafted token with a modified `role` claim is rejected with 401 (signature check).

---

## Phase 5: User Story 3 — Token Expiry and Re-authentication (Priority: P2)

**Goal**: Expired tokens are rejected with 401. The frontend detects 401 and redirects to `/login`. The refresh endpoint issues a new token without requiring a password.

**Independent Test**: Create a token, monkeypatch its `exp` to a past timestamp, present it to a protected route → 401 with `TOKEN_EXPIRED`. Call `/auth/refresh` with a valid non-expired token → new token with same claims and later `exp`.

- [ ] T032 [US3] Implement `POST /auth/refresh` handler (replaces the 501 stub from T018): validate token via `decode_jwt` (must be non-expired); build new token with same `sub`, `tenant_id`, `role` claims and reset `exp`; write `token_refresh` audit log entry; return `TokenResponse` in `backend/app/api/auth.py`
- [ ] T033 [US3] Implement `POST /auth/logout` handler (replaces the 501 stub from T018): extract `ctx` via `get_current_tenant_context`; write `logout` audit log entry; return `{"message": "Logged out"}` 200 in `backend/app/api/auth.py`
- [ ] T034 [P] [US3] Implement `ProtectedRoute` component in `frontend/src/components/ProtectedRoute.tsx`: call `useAuth()`; if `!isAuthenticated` return `<Navigate to="/login" replace />`; otherwise render `children`
- [ ] T035 [US3] Update `frontend/src/App.tsx` router: wrap `/dashboard` in `<ProtectedRoute>`; wrap `/documents` in `<ProtectedRoute><RoleGuard allowedRoles={["manager"]}>...</RoleGuard></ProtectedRoute>`; wrap `/audit-logs` in `<ProtectedRoute><RoleGuard allowedRoles={["manager"]}>...</RoleGuard></ProtectedRoute>`; wrap `/admin/tenants` in `<ProtectedRoute><RoleGuard allowedRoles={["platform_admin"]}>...</RoleGuard></ProtectedRoute>` in `frontend/src/App.tsx`
- [ ] T036 [US3] Add expiry and refresh tests to `backend/tests/integration/test_auth.py`: `test_expired_token_on_protected_route_returns_401_token_expired_code` (AC-08), `test_token_refresh_returns_new_token_with_same_claims_and_later_expiry` (AC-11), `test_token_refresh_with_expired_token_returns_401`, `test_logout_returns_200_and_writes_audit_log_entry`

**Checkpoint**: `pytest tests/integration/test_auth.py -v` passes all 14 tests; Axios interceptor correctly clears `sessionStorage` and navigates to `/login` when a 401 is received.

---

## Phase 6: User Story 4 — Manager Access to Audit Log and Escalations (Priority: P2)

**Goal**: Manager-only routes are enforced end-to-end. Manager sees their own tenant's audit log; Staff is blocked. Manager can resolve an escalation; Staff cannot.

**Independent Test**: Login as Manager at Elegant Weddings, GET `/api/v1/audit-logs` → 200. Login as Staff at same tenant, same route → 403. Login as Manager at Royal Events Agency, same route → 200 (their own log, not Elegant Weddings').

- [ ] T037 [US4] Verify GET `/api/v1/audit-logs` with `require_role(UserRole.manager)` returns the correct tenant-scoped audit log; add targeted test `test_manager_sees_own_tenant_audit_log_not_other_tenant` confirming cross-tenant isolation still applies on top of role guard in `backend/tests/integration/test_roles.py`
- [ ] T038 [US4] Verify `POST /api/v1/escalations/{id}/resolve` enforces `require_role(UserRole.manager)`; add test `test_staff_cannot_resolve_escalation_returns_403` and `test_manager_can_resolve_escalation_returns_200` in `backend/tests/integration/test_roles.py`

**Checkpoint**: 10 total tests in `test_roles.py`; all pass; audit log endpoint returns only the authenticated manager's tenant events.

---

## Phase 7: User Story 5 — Platform Admin Provisions a Tenant (Priority: P3)

**Goal**: Platform Admin can provision/deactivate tenants and list them. Cannot access any tenant content. Staff and Manager are blocked from all `/admin/*` routes.

**Independent Test**: Login as Platform Admin, POST `/api/v1/admin/tenants` → 201 with new `tenant_id`. GET `/api/v1/conversations` as Platform Admin → 403. Login as Manager, POST `/api/v1/admin/tenants` → 403.

- [ ] T039 [US5] Add a Platform Admin seed user in `backend/scripts/seed_staff_users.py`: `platform-admin@eventsense.demo` / `platform-password` with `role=platform_admin` associated with the internal platform tenant (or create a lightweight `platform` tenant record in the seed script)
- [ ] T040 [US5] Implement `PATCH /api/v1/admin/tenants/{id}` tenant deactivation endpoint (sets `tenant.is_active = False`) gated with `require_role(UserRole.platform_admin)` in `backend/app/api/v1/tenants.py`
- [ ] T041 [US5] Add platform admin tests to `backend/tests/integration/test_roles.py`: `test_platform_admin_can_list_tenants`, `test_platform_admin_can_provision_new_tenant` (US5 AC-01), `test_platform_admin_cannot_access_conversations_after_provision`, `test_tenant_deactivation_blocks_user_login` (US5 AC-03), `test_staff_cannot_access_admin_tenants_route_returns_403`, `test_manager_cannot_access_admin_tenants_route_returns_403`

**Checkpoint**: All `/admin/*` routes return 403 for Staff and Manager tokens; Platform Admin can create and deactivate tenants; deactivated tenant users cannot log in.

---

## Phase 8: Polish — Audit Validation and Quickstart Verification

**Purpose**: Confirm all audit events are reliably written, quickstart is accurate, and CLAUDE.md points to the right plan.

- [ ] T042 Add a shared audit-log assertion helper `assert_audit_event(session, tenant_id, action, outcome)` to `backend/tests/conftest.py`; use it in at least 3 existing tests (`test_login_failure_writes_audit_log_entry`, `test_role_violation_writes_audit_log...`, `test_logout_returns_200_and_writes_audit_log_entry`) to verify consistent audit coverage
- [ ] T043 [P] Apply `alembic upgrade head`, run `python backend/scripts/seed_staff_users.py`, and execute the curl commands in `specs/002-auth-and-roles/quickstart.md` end-to-end; update the quickstart if any command output differs from documented expected output in `specs/002-auth-and-roles/quickstart.md`
- [ ] T044 [P] Confirm `CLAUDE.md` plan reference between `<!-- SPECKIT START -->` and `<!-- SPECKIT END -->` markers points to `specs/002-auth-and-roles/plan.md` in `CLAUDE.md`

**Checkpoint**: `pytest tests/ -v` passes all tests (unit + integration across both Spec 001 and Spec 002 test files); quickstart curl commands produce the documented output.

---

## Dependencies & Execution Order

### Phase Dependencies

```
Phase 1 (Setup — deps, migration, schemas skeleton)
  └── Phase 2 (Foundational — security.py, UserRole, require_role, audit constants)
        ├── Phase 3 (US1: Login + Protected Routes)  ←── P1, start here
        │     └── Phase 4 (US2: Role Enforcement)   ←── P1, depends on US1 tokens
        │           └── Phase 5 (US3: Expiry + Refresh)
        │                 ├── Phase 6 (US4: Manager Audit)
        │                 └── Phase 7 (US5: Platform Admin)
        │                         └── Phase 8 (Polish)
```

### User Story Dependencies

| Story | Depends on | Notes |
|-------|-----------|-------|
| US1 (Login) | Phase 2 complete | Requires `decode_jwt`, `create_access_token`, schemas |
| US2 (Role Enforcement) | US1 + Phase 2 | Requires working tokens to test role rules |
| US3 (Expiry + Refresh) | US1 | Refresh endpoint uses same `create_access_token` |
| US4 (Manager Audit) | US2 | Depends on `require_role(manager)` being wired |
| US5 (Platform Admin) | US2 | Depends on `require_role(platform_admin)` being wired |

### Within Each Phase

- All `[P]`-tagged tasks write to different files — safe to run concurrently
- `T016` (login endpoint) must complete before `T025` (login tests)
- `T026–T028` (require_role wiring) must complete before `T031` (role tests)
- `T032–T033` (refresh/logout endpoints) must complete before `T036` (expiry tests)

---

## Parallel Execution Examples

### Phase 2 — Security foundations in parallel

```
Parallel group 1 (all write to different files):
  T007  security.py → hash_password + verify_password
  T008  security.py → create_access_token         (same file; do T007 then T008)
  T009  security.py → decode_jwt                  (same file; do T008 then T009)
  T012  audit_service.py → AuditAction constants
  T013  schemas/auth.py
  T014  schemas/user.py

Then sequential:
  T010  tenant_context.py → complete get_current_tenant_context (needs T009)
  T011  tenant_context.py → complete require_role (needs T010)
  T015  tests/conftest.py → update make_test_token (needs T008)
```

### Phase 3 (US1) — Backend and frontend in parallel

```
Backend (sequential):
  T016 → T017 → T018  (login endpoint, /me endpoint, mount router)

Frontend (parallel once backend is mounted):
  T019  AuthContext.tsx
  T020  useAuth.ts
  T021  client.ts (401 interceptor)

Then sequential:
  T022  LoginPage.tsx (needs AuthContext + useAuth)
  T023  App.tsx updates (needs LoginPage + ProtectedRoute)
```

### Phase 4 (US2) — Role wiring and frontend in parallel

```
Parallel:
  T026  conversations/messages/tasks/escalations/suggested_replies routers
  T027  audit_logs/documents routers
  T028  tenants admin routes
  T029  RoleGuard.tsx
  T030  ForbiddenPage.tsx

Then sequential:
  T031  test_roles.py (needs T026–T028 complete)
```

---

## Implementation Strategy

### MVP First (User Stories 1 + 2 Only)

1. Complete Phase 1 (Setup) + Phase 2 (Foundational) → ~15 tasks
2. Complete Phase 3 (US1: Login) → ~10 tasks
3. **STOP and VALIDATE**: Login works; protected routes return 401 without token
4. Complete Phase 4 (US2: Role Enforcement) → ~6 tasks
5. **STOP and VALIDATE**: Staff/Manager/Platform Admin role gates enforced; 403 returned and audit-logged

### Incremental Delivery

| Milestone | Phases complete | Verifiable outcome |
|-----------|----------------|--------------------|
| Auth foundation | 1–2 | `decode_jwt` + `verify_password` tested; role enum renamed |
| Login works | + 3 | Demo tenant users can log in; JWT claims verified |
| Roles enforced | + 4 | Staff blocked from manager routes; 403 audit-logged |
| Session expiry | + 5 | Expired tokens rejected; refresh endpoint working |
| Manager tools | + 6 | Audit log + escalation resolution gated to manager |
| Platform Admin | + 7 | Tenant provisioning/deactivation gated to platform_admin |
| Verified | + 8 | All 30 tests pass; quickstart validated end-to-end |

---

## Notes

- Spec 001 database tables (`users`, `tenants`, `audit_logs`) and `AuditService` are **assumed to exist** — not re-implemented here
- `[P]` tasks write to different files — safe to run concurrently with no conflicts
- `[US#]` label maps every task back to a testable user story in `spec.md`
- No WhatsApp integration, calendar syncing, AI classifier, RAG, full dashboard, document upload pipeline, or message inbox tasks are included
- The `jti` claim is included in the JWT for future revocation support but is not validated against a store in this feature
- Role values (`staff`, `manager`, `platform_admin`) are the canonical identifiers from this point forward — all code written after this feature must use these values
