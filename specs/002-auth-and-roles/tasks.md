# Tasks: Authentication and Roles

**Branch**: `002-auth-and-roles` | **Spec**: [spec.md](./spec.md) | **Plan**: [plan.md](./plan.md)

**Depends on**: Spec 001 Multi-Tenant Workspace — `users`, `tenants`, canonical roles, `TenantContext`, and `require_role` contract are assumed to exist. Tasks here do **not** re-implement that schema.

**Total tasks**: 43 across 8 phases

**Format**: `[ID] [P?] [Story?] Description — file path`
- `[P]` = parallelizable (different files, no incomplete dependency)
- `[US#]` = maps to user story in spec.md
- Setup and Foundational phases carry no story label

---

## Phase 1: Setup

**Purpose**: Add new dependencies, create the schemas package, and prepare demo staff seed helpers. No role-rename migration is needed because Spec 001 already defines canonical roles.

- [ ] T001 Add `python-jose[cryptography]` and `passlib[bcrypt]` to backend dependencies in `backend/requirements.txt` (verify they are not already present from Spec 001)
- [ ] T002 [P] Add `jwt-decode` to frontend dependencies in `frontend/package.json` and run `npm install`
- [ ] T003 [P] Create `backend/app/schemas/` package: add `backend/app/schemas/__init__.py`, empty `backend/app/schemas/auth.py`, and empty `backend/app/schemas/user.py`
- [ ] T004 [P] Create `backend/scripts/seed_staff_users.py`: inserts one `staff`-role user per demo tenant (`staff@elegant-weddings.demo` / `staff-password-1` and `staff@royal-events.demo` / `staff-password-2`) using bcrypt-hashed passwords in `backend/scripts/seed_staff_users.py`
- [ ] T005 [P] Verify Spec 001 seed includes a platform/system tenant and `platform_admin` user; if not, update the Spec 001 seed before continuing rather than adding a second platform seed here

**Checkpoint**: `SELECT unnest(enum_range(NULL::user_role))` returns `staff`, `manager`, `platform_admin`; demo staff seed script can run idempotently.

---

## Phase 2: Foundational — Security Module and Role Infrastructure

**Purpose**: All auth logic depends on this phase. `security.py`, `get_current_tenant_context` completion, `require_role`, audit event constants, and Pydantic schemas must all be in place before any endpoint or test can run.

**⚠️ CRITICAL**: No user story work can begin until this phase is complete.

- [ ] T006 Verify `UserRole` enum in `backend/app/models/user.py` already uses canonical string values `"staff"`, `"manager"`, `"platform_admin"` from Spec 001; do not add a rename migration
- [ ] T007 Implement `hash_password(plain: str) -> str` and `verify_password(plain: str, hashed: str) -> bool` using `passlib.context.CryptContext(schemes=["bcrypt"], deprecated="auto")` in `backend/app/core/security.py`
- [ ] T008 Implement `create_access_token(sub: str, tenant_id: str, role: str, expires_delta: timedelta | None = None) -> str`: builds payload `{sub, tenant_id, role, exp, iat, jti}`, signs with `JWT_SECRET_KEY` using HS256 via `python-jose`, defaults to 60-minute expiry in `backend/app/core/security.py`
- [ ] T009 Implement `decode_jwt(token: str) -> TokenData`: verifies HS256 signature and `exp` claim using `python-jose`; raises `HTTPException(401, {"detail": "Invalid token", "error_code": "INVALID_TOKEN"})` on bad signature and `HTTPException(401, {"detail": "Token expired", "error_code": "TOKEN_EXPIRED"})` on expiry; raises `HTTPException(401, ...)` if `sub`, `tenant_id`, or `role` claims are missing in `backend/app/core/security.py`
- [ ] T010 Complete `get_current_tenant_context` FastAPI dependency (was a stub in Spec 001): call `security.decode_jwt(token)`, construct and return `TenantContext(tenant_id=UUID(data.tenant_id), user_id=UUID(data.sub), role=UserRole(data.role))` in `backend/app/core/tenant_context.py`
- [ ] T011 Implement `require_role(*allowed_roles: UserRole)` dependency factory (completes Spec 001 contract): if `ctx.role not in allowed_roles`, emit/call `insufficient_role` event hook if audit integration exists, then raise `HTTPException(403, {"detail": "forbidden", "error_code": "INSUFFICIENT_ROLE"})` in `backend/app/core/tenant_context.py`
- [ ] T012 [P] Define auth event constants for future audit integration: `login_success`, `login_failure`, `login_failure_inactive`, `insufficient_role`, `platform_admin_content_attempt`, `token_refresh`, `logout`; if the audit-log feature is not implemented yet, keep these as constants/types only in the auth layer
- [ ] T013 [P] Define Pydantic schemas `LoginRequest(email: EmailStr, password: str, tenant_slug: str)`, `TokenResponse(access_token: str, token_type: str = "bearer", expires_in: int)`, `TokenData(sub: UUID, tenant_id: UUID, role: UserRole, exp: int, iat: int, jti: UUID)` in `backend/app/schemas/auth.py`
- [ ] T014 [P] Define Pydantic schema `UserResponse(id: UUID, email: str, full_name: str, role: UserRole, tenant_id: UUID, is_active: bool)` with `model_config = ConfigDict(from_attributes=True)` in `backend/app/schemas/user.py`
- [ ] T015 Update `backend/tests/conftest.py` `make_test_token` helper (Spec 001 stub) to call `security.create_access_token(sub=str(user_id), tenant_id=str(tenant_id), role=role.value)` so all existing integration tests use the real JWT implementation

**Checkpoint**: `from app.core.security import create_access_token, decode_jwt, verify_password` imports cleanly; `decode_jwt(create_access_token("uid", "tid", "staff"))` returns a `TokenData` instance; `verify_password("wrong", hash_password("right"))` returns `False`.

---

## Phase 3: User Story 1 — Staff Login and Authenticated Session (Priority: P1)

**Goal**: A Staff user submits valid credentials and receives a signed JWT with correct `user_id`, `tenant_id`, and `role=staff` claims. Protected routes return 401 without a valid token.

**Independent Test**: POST `/auth/token` with valid Staff credentials → decode token → assert `sub`, `tenant_id`, `role` are correct. Then GET `/api/v1/conversations` without token → assert 401.

- [ ] T016 [US1] Implement `POST /auth/token` login handler in `backend/app/api/auth.py`: (1) query `tenants WHERE slug=:tenant_slug AND is_active=true` — 401 + `login_failure` event if available on miss; (2) query `users WHERE email=:email AND tenant_id=:tenant_id` — 401 + `login_failure` event if available on miss; (3) check `user.is_active` — 401 + `login_failure_inactive` event if not; (4) `security.verify_password(password, user.hashed_password)` — 401 + `login_failure` event on fail; (5) `security.create_access_token(...)` — 200 + `login_success` event if available on success
- [ ] T017 [US1] Implement `GET /auth/me` handler: fetch `User` by `ctx.user_id` from DB, return `UserResponse` in `backend/app/api/auth.py`
- [ ] T018 [US1] Create `auth` `APIRouter` and mount it at `/auth` prefix (without `/api/v1`) in `backend/app/main.py`; also register `POST /auth/refresh` and `POST /auth/logout` as stubs returning 501 for now (to be completed in Phase 5)
- [ ] T019 [P] [US1] Implement `AuthContext` React provider in `frontend/src/context/AuthContext.tsx`: on mount read `sessionStorage.getItem("access_token")` and decode with `jwt-decode`; expose `{ token, user: { userId, tenantId, role, exp }, isAuthenticated }`; `login(email, password, tenantSlug)` calls `POST /auth/token`, stores token in `sessionStorage` + state; `logout()` clears `sessionStorage` + state + navigates to `/login`
- [ ] T020 [P] [US1] Implement `useAuth()` hook in `frontend/src/hooks/useAuth.ts`: consumes `AuthContext`, throws `Error("useAuth must be used within AuthProvider")` if called outside provider
- [ ] T021 [P] [US1] Add Axios 401 interceptor to `frontend/src/api/client.ts`: on any 401 response call `logout()` from `AuthContext` and `navigate("/login")`; ensure the interceptor does **not** retry the request
- [ ] T022 [US1] Build `LoginPage` in `frontend/src/pages/LoginPage.tsx`: form with `email`, `password`, and `tenant_slug` fields; on submit calls `useAuth().login(...)`; shows inline error message on 401; redirects to `/dashboard` on success; redirect to `/dashboard` if already authenticated
- [ ] T023 [US1] Wrap `App` router in `<AuthProvider>` and add `/login` route pointing to `LoginPage`; add a minimal `/dashboard` route (stub page showing "Dashboard — authenticated") in `frontend/src/App.tsx`
- [ ] T024 [P] [US1] Write security unit tests in `backend/tests/unit/test_security.py`: `test_hash_and_verify_password_roundtrip`, `test_wrong_password_fails_verify`, `test_create_access_token_contains_all_required_claims` (sub, tenant_id, role, exp, iat, jti), `test_create_access_token_exp_is_60_minutes_from_now`, `test_decode_jwt_returns_correct_token_data`, `test_decode_jwt_rejects_expired_token`, `test_decode_jwt_rejects_tampered_signature`
- [ ] T025 [US1] Write login integration tests in `backend/tests/integration/test_auth.py`: `test_login_success_returns_token_with_correct_claims` (AC-01), `test_login_failure_wrong_password_returns_401` (AC-02), `test_login_failure_unknown_email_returns_401` (AC-02), `test_login_failure_inactive_user_returns_401` (AC-03), `test_login_failure_inactive_tenant_returns_401` (AC-04), `test_missing_token_returns_401_missing_token_code`, `test_tampered_token_returns_401_invalid_token_code`, `test_get_me_returns_correct_user_profile`, `test_login_failure_emits_event_if_available` (AC-09), `test_body_tenant_id_field_is_ignored_at_login` (AC-12)

**Checkpoint**: `pytest tests/unit/test_security.py tests/integration/test_auth.py::test_login_success_returns_token_with_correct_claims -v` passes; curl login returns a decodable JWT; GET `/auth/me` with valid token returns user profile.

---

## Phase 4: User Story 2 — Role-Based Access Enforcement (Priority: P1)

**Goal**: Staff role cannot access Manager-only routes (403). Manager role can access both Staff and Manager routes. No client-side action can change the role claim.

**Independent Test**: Login as Staff and call a currently implemented Manager-only route or test route → 403 with `error_code: INSUFFICIENT_ROLE`. Login as Manager and call the same route → success. Verify a future-audit event hook is emitted if audit integration exists.

- [ ] T026 [US2] Apply `require_role(UserRole.staff, UserRole.manager)` to any currently implemented tenant content route; later conversations, messages, tasks, escalations, and suggested reply routes must use the same guard when those features are created
- [ ] T027 [US2] Document and test manager-only role guard behavior using any currently implemented manager route or test route; later document, escalation, audit-log, and RAG-management routes must apply `require_role(UserRole.manager)` when those features are created
- [ ] T028 [US2] Apply `require_role(UserRole.platform_admin)` to existing platform metadata/admin routes; later platform admin routes must use the same guard and must not expose tenant content by default
- [ ] T029 [P] [US2] Implement `RoleGuard` component in `frontend/src/components/RoleGuard.tsx`: accepts `allowedRoles: Array<"staff" | "manager" | "platform_admin">` and `children`; if `user.role` not in `allowedRoles` renders `<ForbiddenPage />`; renders children if role matches
- [ ] T030 [P] [US2] Implement `ForbiddenPage` in `frontend/src/pages/ForbiddenPage.tsx`: displays "Access denied — you don't have permission to view this page" with a "Go back" button; no additional logic
- [ ] T031 [US2] Write role enforcement integration tests in `backend/tests/integration/test_roles.py`: staff blocked from one manager-only route that exists in the current codebase, manager allowed on that route, platform_admin blocked from tenant content route, `test_role_violation_response_contains_insufficient_role_error_code`, and `test_role_violation_emits_event_with_required_and_actual_role_if_available` (AC-10)

**Checkpoint**: `pytest tests/integration/test_roles.py -v` passes all 8 tests; a manually crafted token with a modified `role` claim is rejected with 401 (signature check).

---

## Phase 5: User Story 3 — Token Expiry and Re-authentication (Priority: P2)

**Goal**: Expired tokens are rejected with 401. The frontend detects 401 and redirects to `/login`. The refresh endpoint issues a new token without requiring a password.

**Independent Test**: Create a token, monkeypatch its `exp` to a past timestamp, present it to a protected route → 401 with `TOKEN_EXPIRED`. Call `/auth/refresh` with a valid non-expired token → new token with same claims and later `exp`.

- [ ] T032 [US3] Implement `POST /auth/refresh` handler (replaces the 501 stub from T018): validate token via `decode_jwt` (must be non-expired); fetch user and tenant from DB; reject with 401 if either is inactive or missing; build new token with same `sub`, `tenant_id`, `role` claims and reset `exp`; emit/call `token_refresh` event hook if audit integration exists; return `TokenResponse` in `backend/app/api/auth.py`
- [ ] T033 [US3] Implement `POST /auth/logout` handler (replaces the 501 stub from T018): extract `ctx` via `get_current_tenant_context`; emit/call `logout` event hook if audit integration exists; return `{"message": "Logged out"}` 200 in `backend/app/api/auth.py`
- [ ] T034 [P] [US3] Implement `ProtectedRoute` component in `frontend/src/components/ProtectedRoute.tsx`: call `useAuth()`; if `!isAuthenticated` return `<Navigate to="/login" replace />`; otherwise render `children`
- [ ] T035 [US3] Update `frontend/src/App.tsx` router: wrap currently implemented authenticated pages in `<ProtectedRoute>`; wrap current/future manager pages with `<RoleGuard allowedRoles={["manager"]}>`; wrap current/future platform admin pages with `<RoleGuard allowedRoles={["platform_admin"]}>`
- [ ] T036 [US3] Add expiry and refresh tests to `backend/tests/integration/test_auth.py`: `test_expired_token_on_protected_route_returns_401_token_expired_code` (AC-08), `test_token_refresh_returns_new_token_with_same_claims_and_later_expiry` (AC-11), `test_token_refresh_with_expired_token_returns_401`, `test_token_refresh_rejects_inactive_user`, `test_token_refresh_rejects_inactive_tenant`, `test_logout_returns_200_and_emits_event_if_available`

**Checkpoint**: `pytest tests/integration/test_auth.py -v` passes all 14 tests; Axios interceptor correctly clears `sessionStorage` and navigates to `/login` when a 401 is received.

---

## Phase 6: User Story 4 — Manager Role Policy for Future Tools (Priority: P2)

**Goal**: Manager-only route policy is defined and testable on currently implemented routes. Future audit, document, and escalation features must apply this policy when those routes exist.

**Independent Test**: Login as Manager and Staff at the same tenant. Use a currently implemented manager-only route or test route to verify Manager succeeds and Staff receives 403.

- [ ] T037 [US4] Add `test_manager_only_route_allows_manager_and_blocks_staff` using a currently implemented manager-only route or test fixture in `backend/tests/integration/test_roles.py`
- [ ] T038 [US4] Add a role policy note/test helper that later audit, document, and escalation routes must use `require_role(UserRole.manager)` and remain tenant-scoped

**Checkpoint**: Manager-only role policy is test-covered without requiring audit, document, or escalation features to exist yet.

---

## Phase 7: User Story 5 — Platform Admin Boundary (Priority: P3)

**Goal**: Platform Admin can access existing platform/demo metadata routes and cannot access any tenant content. Staff and Manager are blocked from platform admin routes.

**Independent Test**: Login as Platform Admin, GET an existing `/api/v1/admin/tenants` metadata route from Spec 001 → success. GET `/api/v1/conversations` as Platform Admin → 403. Login as Manager, GET `/api/v1/admin/tenants` → 403.

- [ ] T039 [US5] Verify the Spec 001 platform/system tenant seed provides `platform-admin@eventsense.demo` / `platform-password` with `role=platform_admin`; do not seed platform admin from the staff-user script
- [ ] T040 [US5] Apply or verify `require_role(UserRole.platform_admin)` on currently implemented platform metadata/admin routes only; do not add tenant provisioning or tenant deactivation endpoints in Spec 002
- [ ] T041 [US5] Add platform admin boundary tests to `backend/tests/integration/test_roles.py`: `test_platform_admin_can_list_tenants_metadata_if_route_exists`, `test_platform_admin_cannot_access_tenant_content_route`, `test_staff_cannot_access_admin_tenants_route_returns_403`, `test_manager_cannot_access_admin_tenants_route_returns_403`

**Checkpoint**: Existing `/admin/*` routes return 403 for Staff and Manager tokens; Platform Admin can access platform metadata only; Platform Admin remains blocked from tenant content.

---

## Phase 8: Polish — Auth Event and Quickstart Verification

**Purpose**: Confirm auth event naming, quickstart accuracy, and end-to-end auth behavior.

- [ ] T042 Add a shared auth-event assertion helper if audit infrastructure exists; otherwise assert event constants are emitted/called through a test seam without requiring a database audit table
- [ ] T043 [P] Apply `alembic upgrade head`, run `python backend/scripts/seed_staff_users.py`, and execute the curl commands in `specs/002-auth-and-roles/quickstart.md` end-to-end; update the quickstart if any command output differs from documented expected output in `specs/002-auth-and-roles/quickstart.md`

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
        │                 ├── Phase 6 (US4: Manager Role Policy)
        │                 └── Phase 7 (US5: Platform Admin Boundary)
        │                         └── Phase 8 (Polish)
```

### User Story Dependencies

| Story | Depends on | Notes |
|-------|-----------|-------|
| US1 (Login) | Phase 2 complete | Requires `decode_jwt`, `create_access_token`, schemas |
| US2 (Role Enforcement) | US1 + Phase 2 | Requires working tokens to test role rules |
| US3 (Expiry + Refresh) | US1 | Refresh endpoint uses same `create_access_token` |
| US4 (Manager Role Policy) | US2 | Depends on `require_role(manager)` being wired |
| US5 (Platform Admin Boundary) | US2 | Depends on `require_role(platform_admin)` being wired |

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
  T012  auth event constants
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
  T026  current tenant content routes plus policy for later content routes
  T027  manager-only routes that currently exist
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
5. **STOP and VALIDATE**: Staff/Manager/Platform Admin role gates enforced; 403 returned and future-audit hooks emitted if available

### Incremental Delivery

| Milestone | Phases complete | Verifiable outcome |
|-----------|----------------|--------------------|
| Auth foundation | 1–2 | `decode_jwt` + `verify_password` tested; canonical roles verified |
| Login works | + 3 | Demo tenant users can log in; JWT claims verified |
| Roles enforced | + 4 | Staff blocked from manager routes; 403 event hook emitted if available |
| Session expiry | + 5 | Expired tokens rejected; refresh endpoint working |
| Manager role policy | + 6 | Manager-only guard policy test-covered for future tools |
| Platform Admin boundary | + 7 | Existing platform metadata routes gated to platform_admin; tenant content blocked |
| Verified | + 8 | All 30 tests pass; quickstart validated end-to-end |

---

## Notes

- Spec 001 database tables (`users`, `tenants`) and tenant context contracts are **assumed to exist** — not re-implemented here
- `[P]` tasks write to different files — safe to run concurrently with no conflicts
- `[US#]` label maps every task back to a testable user story in `spec.md`
- No WhatsApp integration, calendar syncing, AI classifier, RAG, full dashboard, document upload pipeline, message inbox, task workflow, escalation workflow, audit-log persistence, tenant provisioning, or tenant deactivation tasks are included
- The `jti` claim is included in the JWT for future revocation support but is not validated against a store in this feature
- Role values (`staff`, `manager`, `platform_admin`) are the canonical identifiers from this point forward — all code written after this feature must use these values
