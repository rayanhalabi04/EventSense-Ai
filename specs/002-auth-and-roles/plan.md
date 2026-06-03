# Implementation Plan: Authentication and Roles

**Branch**: `002-auth-and-roles` | **Date**: 2026-06-03 | **Spec**: [spec.md](./spec.md)

**Input**: Feature specification from `specs/002-auth-and-roles/spec.md`

**Depends on**: [Spec 001 — Multi-Tenant Workspace](../001-multi-tenant-workspace/plan.md) — users table, tenants table, audit_logs table, AuditService, TenantContext dependency, require_role dependency

---

## Summary

Implement the email/password login flow, JWT issuance, and role-based access enforcement for EventSense AI. A signed token containing `user_id`, `tenant_id`, and `role` is issued on every successful login. Backend dependencies (`get_current_tenant_context`, `require_role`) — stubbed in Spec 001 — are now fully wired. The `UserRole` enum values are renamed to their canonical forms (`staff`, `manager`, `platform_admin`). Frontend `AuthContext`, `ProtectedRoute`, and `RoleGuard` components guard all pages. Audit events are written for login success, login failure, role violations, and token refresh.

---

## Technical Context

**Language/Version**: Python 3.11 (backend), TypeScript 5.x (frontend)

**Primary Dependencies**:
- Backend: FastAPI, SQLAlchemy 2.x, Alembic, python-jose[cryptography] (JWT), passlib[bcrypt] (password hashing), pydantic[email] (email validation)
- Frontend: React 18, Vite 5, Tailwind CSS, shadcn/ui, axios, jwt-decode

**Storage**: PostgreSQL 15 — no new tables; adds one Alembic migration (role enum rename + seed update)

**Testing**: pytest + pytest-asyncio (backend), Vitest (frontend)

**Target Platform**: Linux server (backend), browser (frontend)

**Project Type**: Web application — FastAPI REST backend + React SPA frontend

**Performance Goals**: Login endpoint responds within standard web expectations. No special throughput requirements.

**Constraints**:
- `tenant_id` and `role` must come from the signed JWT only — never from request body or query string
- Expired tokens return 401; insufficient role returns 403
- Audit log writes are synchronous and append-only (Spec 001 `AuditService` pattern)
- Token lifetime: access token 60 minutes; no separate refresh token for MVP

**Scale/Scope**: Two demo tenants, two roles per tenant (manager + staff), one platform admin for MVP.

---

## Constitution Check

Constitution file is a blank template (not yet ratified). No governance gates apply. Proceeding without violations.

---

## Project Structure

### Documentation (this feature)

```
specs/002-auth-and-roles/
├── plan.md              # This file
├── research.md          # Phase 0: 8 design decisions
├── data-model.md        # Phase 1: JWT structure, role enum rename, Pydantic schemas, permission matrix
├── quickstart.md        # Phase 1: local setup + curl test guide
├── contracts/
│   └── api-contracts.md # Phase 1: auth endpoint contracts + role enforcement table
└── tasks.md             # Phase 2 output (created by /speckit-tasks)
```

### Source Code Layout

New files added by this feature:

```
backend/
├── app/
│   ├── core/
│   │   └── security.py            # COMPLETE: create_access_token, verify_password,
│   │                              #           hash_password, decode_jwt, is_token_expired
│   ├── api/
│   │   └── auth.py                # NEW: /auth/token, /auth/refresh, /auth/logout, /auth/me
│   └── schemas/
│       ├── auth.py                # NEW: LoginRequest, TokenResponse, TokenData
│       └── user.py                # NEW: UserResponse
├── alembic/versions/
│   └── 0009_rename_user_roles.py  # NEW: ALTER TYPE user_role RENAME VALUE ...
├── scripts/
│   └── seed_staff_users.py        # NEW: staff users for both demo tenants
└── tests/
    ├── integration/
    │   ├── test_auth.py           # NEW: 14 auth tests covering all AC
    │   └── test_roles.py          # NEW: 9 role enforcement tests
    └── unit/
        └── test_security.py       # NEW: 7 security unit tests

frontend/
└── src/
    ├── context/
    │   └── AuthContext.tsx         # NEW: token store, decoded claims, isAuthenticated
    ├── hooks/
    │   └── useAuth.ts              # NEW: consume AuthContext with safety check
    ├── components/
    │   ├── ProtectedRoute.tsx      # NEW: redirect to /login if !isAuthenticated
    │   └── RoleGuard.tsx           # NEW: show ForbiddenPage if role not in allowedRoles
    ├── pages/
    │   ├── LoginPage.tsx           # NEW: email/password/tenant-slug form
    │   └── ForbiddenPage.tsx       # NEW: 403 error page
    └── api/
        └── auth.ts                 # NEW: login(), refresh(), logout(), getMe()
```

Existing files modified:

```
backend/app/core/tenant_context.py  # WIRE: get_current_tenant_context calls decode_jwt (was stub)
backend/app/main.py                 # ADD: mount auth router at /auth prefix
frontend/src/App.tsx                # ADD: AuthProvider wrap, /login route, ProtectedRoute wrappers
frontend/src/api/client.ts          # ADD: Axios 401 interceptor → clear token + redirect
```

---

## In Scope for This Feature

| Area | What is built |
|------|--------------|
| `security.py` | `create_access_token`, `verify_password`, `hash_password`, `decode_jwt`, `is_token_expired` |
| `get_current_tenant_context` | Wired to `decode_jwt`; completes the stub from Spec 001 |
| `require_role(*roles)` | Fully implemented; completes the stub from Spec 001 |
| `POST /auth/token` | Login — validates credentials, resolves tenant from slug, issues JWT, audit logs |
| `POST /auth/refresh` | Issues a new token for a still-valid token |
| `POST /auth/logout` | Audit logs logout; returns 200; client clears token |
| `GET /auth/me` | Returns current user profile from DB |
| Role enum rename | Migration `0009` renames values to `staff`, `manager`, `platform_admin` |
| Pydantic schemas | `LoginRequest`, `TokenResponse`, `TokenData`, `UserResponse` |
| Staff seed users | `seed_staff_users.py` for both demo tenants |
| `AuthContext` + `useAuth` | Token store, decoded claims, `isAuthenticated`, login/logout actions |
| `ProtectedRoute` | Redirects to `/login` if no valid token |
| `RoleGuard` | Renders `ForbiddenPage` if role not in allowed list |
| `LoginPage` | Form with email, password, tenant-slug |
| `ForbiddenPage` | 403 error page shown by `RoleGuard` |
| Axios 401 interceptor | Clears token + redirects to `/login` on any 401 |
| Auth integration tests | `test_auth.py` (14 tests) + `test_roles.py` (9 tests) |
| Security unit tests | `test_security.py` (7 tests) |
| Audit logging | login_success, login_failure, login_failure_inactive, insufficient_role, token_refresh, logout |

---

## Deferred to Later Features

| Item | Target |
|------|--------|
| Separate refresh token (httpOnly cookie) | Auth Enhancement (post-MVP) |
| Token revocation blocklist (jti) | Auth Enhancement (post-MVP) |
| MFA | Auth Enhancement (post-MVP) |
| OAuth2 / SSO | Auth Enhancement (post-MVP) |
| Password reset via email | Auth Enhancement (post-MVP) |
| Per-user permission overrides | RBAC Enhancement (post-MVP) |
| Session management UI | Auth Enhancement (post-MVP) |
| Application-layer rate limiting on login | Platform Operations feature |

---

## Login Flow (Step-by-Step)

```
POST /auth/token  { email, password, tenant_slug }
  │
  ├─ 1. Resolve tenant:  SELECT FROM tenants WHERE slug=:slug AND is_active=true
  │       → Not found → 401 INVALID_CREDENTIALS + audit(login_failure)
  │
  ├─ 2. Resolve user:    SELECT FROM users WHERE email=:email AND tenant_id=:tid
  │       → Not found → 401 INVALID_CREDENTIALS + audit(login_failure)
  │
  ├─ 3. Check active:    user.is_active AND tenant.is_active
  │       → Inactive → 401 INVALID_CREDENTIALS + audit(login_failure_inactive)
  │
  ├─ 4. Verify password: passlib.verify(plain, user.hashed_password)
  │       → Wrong → 401 INVALID_CREDENTIALS + audit(login_failure)
  │
  ├─ 5. Issue token:     create_access_token(sub=user.id, tenant_id, role, exp=now+3600, jti=uuid())
  │
  ├─ 6. Audit log:       AuditService.log(tenant_id, login_success, allowed, actor=user.id, ip=req.client.host)
  │
  └─ 7. Return:          { access_token, token_type: "bearer", expires_in: 3600 }
```

---

## JWT Dependency Flow (Every Protected Request)

```
Authorization: Bearer <token>
  │
  decode_jwt(token)
    → Invalid signature → 401 INVALID_TOKEN
    → Expired           → 401 TOKEN_EXPIRED
    → Missing claims    → 401 INVALID_TOKEN
  │
  TenantContext(tenant_id=payload.tenant_id, user_id=payload.sub, role=payload.role)
  │
  If route uses require_role("manager"):
    ctx.role not in ["manager"] → 403 INSUFFICIENT_ROLE + audit(insufficient_role)
  │
  Handler executes; all DB queries use ctx.tenant_id
```

---

## Role Enforcement Design

`require_role(*allowed_roles)` is a FastAPI dependency factory in `backend/app/core/tenant_context.py`:

```python
def require_role(*allowed_roles: UserRole):
    def dependency(ctx: TenantContext = Depends(get_current_tenant_context)):
        if ctx.role not in allowed_roles:
            audit_service.log(
                tenant_id=ctx.tenant_id,
                action=AuditAction.insufficient_role,
                outcome=AuditOutcome.blocked,
                actor_user_id=ctx.user_id,
                detail={"required": [r.value for r in allowed_roles], "actual": ctx.role.value},
            )
            raise HTTPException(
                status_code=403,
                detail={"detail": "forbidden", "error_code": "INSUFFICIENT_ROLE"}
            )
        return ctx
    return dependency
```

Route usage:
```python
# Staff and Manager can access
@router.get("/conversations")
async def list_conversations(ctx = Depends(require_role(UserRole.staff, UserRole.manager))):
    ...

# Manager only
@router.get("/audit-logs")
async def get_audit_logs(ctx = Depends(require_role(UserRole.manager))):
    ...

# Platform Admin only
@router.post("/admin/tenants")
async def provision_tenant(ctx = Depends(require_role(UserRole.platform_admin))):
    ...
```

---

## Frontend Auth State Management

`AuthContext` lifecycle:

1. **On mount**: read `sessionStorage.getItem("access_token")` → decode with `jwt-decode` → check `exp > Date.now()/1000` → set `isAuthenticated`
2. **On `login(email, password, tenantSlug)`**: POST `/auth/token` → store raw token in `sessionStorage` + decoded claims in React state
3. **On Axios 401 interceptor**: call `logout()` → clear `sessionStorage` → set `{ token: null, user: null }` → `navigate("/login")`
4. **On `logout()`**: POST `/auth/logout` (fire-and-forget) → clear `sessionStorage` + state → `navigate("/login")`
5. **On `refreshToken()`**: POST `/auth/refresh` with current token → replace stored token

`ProtectedRoute`: wraps all authenticated pages; redirects to `/login` if `!isAuthenticated`.

`RoleGuard`: wraps role-restricted pages; renders `<ForbiddenPage />` if `user.role` not in `allowedRoles`.

---

## Audit Logging Hooks

New `AuditAction` constants added to `backend/app/services/audit_service.py`:

| Constant | Trigger |
|----------|---------|
| `login_success` | `POST /auth/token` success |
| `login_failure` | `POST /auth/token` — bad credentials |
| `login_failure_inactive` | `POST /auth/token` — inactive user or tenant |
| `insufficient_role` | `require_role()` check fails |
| `platform_admin_content_attempt` | Platform Admin hits a content route (subset of `insufficient_role`) |
| `token_refresh` | `POST /auth/refresh` success |
| `logout` | `POST /auth/logout` |

---

## Test Coverage

### `tests/integration/test_auth.py` (14 tests → AC-01 through AC-12)

| Test | Acceptance Criterion |
|------|---------------------|
| `test_login_success_returns_token_with_correct_claims` | AC-01 |
| `test_login_failure_wrong_password_returns_401` | AC-02 |
| `test_login_failure_unknown_email_returns_401` | AC-02 |
| `test_login_failure_inactive_user_returns_401` | AC-03 |
| `test_login_failure_inactive_tenant_returns_401` | AC-04 |
| `test_expired_token_on_protected_route_returns_401` | AC-08 |
| `test_missing_token_returns_401` | SR-02 |
| `test_tampered_token_returns_401` | US2 AC-04 |
| `test_token_refresh_returns_new_token_same_claims` | AC-11 |
| `test_token_refresh_with_expired_token_returns_401` | AC-08 |
| `test_logout_returns_200_and_writes_audit_log` | SR-06 |
| `test_get_me_returns_correct_user_profile` | contract |
| `test_login_failure_writes_audit_log_entry` | AC-09 |
| `test_body_tenant_id_ignored_session_value_used` | AC-12 |

### `tests/integration/test_roles.py` (9 tests → AC-05 through AC-10)

| Test | Acceptance Criterion |
|------|---------------------|
| `test_staff_cannot_access_audit_logs_returns_403` | AC-05 |
| `test_staff_cannot_upload_documents_returns_403` | AC-05 |
| `test_manager_can_access_audit_logs` | AC-06 |
| `test_manager_can_access_conversations` | AC-06 |
| `test_platform_admin_cannot_access_conversations` | AC-07 |
| `test_platform_admin_cannot_access_documents` | AC-07 |
| `test_platform_admin_can_provision_tenant` | US5 |
| `test_role_violation_writes_audit_log_with_required_and_actual_role` | AC-10 |
| `test_insufficient_role_response_contains_error_code` | contract |

### `tests/unit/test_security.py` (7 tests)

| Test | Purpose |
|------|---------|
| `test_hash_and_verify_password_roundtrip` | bcrypt hash/verify |
| `test_wrong_password_fails_verify` | Negative case |
| `test_create_access_token_contains_all_required_claims` | sub, tenant_id, role, exp, iat, jti |
| `test_create_access_token_exp_is_60_minutes_from_now` | Expiry value |
| `test_decode_jwt_returns_correct_token_data` | Happy path decode |
| `test_decode_jwt_rejects_expired_token` | Expiry enforcement |
| `test_decode_jwt_rejects_tampered_signature` | Signature enforcement |
