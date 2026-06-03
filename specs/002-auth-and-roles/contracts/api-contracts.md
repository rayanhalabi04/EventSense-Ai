# API Contracts: Authentication and Roles

**Branch**: `002-auth-and-roles` | **Phase**: 1 — Design

Auth endpoints are prefixed with `/auth`. They sit outside the `/api/v1` prefix used by tenant-scoped routes.

---

## Authentication Endpoints

### `POST /auth/token`

Login. Issues a signed access token.

**Auth**: None required.

**Request body** (`application/json`):
```json
{
  "email": "alice@elegant-weddings.demo",
  "password": "••••••••",
  "tenant_slug": "elegant-weddings"
}
```

**Success — Response 200**:
```json
{
  "access_token": "<signed JWT>",
  "token_type": "bearer",
  "expires_in": 3600
}
```

**Failure responses**:

| Status | Condition | Body |
|--------|-----------|------|
| 401 | Wrong password, unknown email, or unknown tenant slug | `{ "detail": "Invalid credentials", "error_code": "INVALID_CREDENTIALS" }` |
| 401 | User account is inactive | `{ "detail": "Invalid credentials", "error_code": "INVALID_CREDENTIALS" }` — same message as wrong password (no enumeration) |
| 401 | Tenant is inactive | `{ "detail": "Invalid credentials", "error_code": "INVALID_CREDENTIALS" }` |
| 422 | Missing or malformed fields | Standard FastAPI validation error |

**Audit log**: Written on every call with outcome `allowed` (success) or `blocked` (failure). Fields: `action`, `outcome`, `ip_address`, `detail.email`, `detail.tenant_slug`. No password is logged.

**Security notes**:
- Generic error message prevents email enumeration
- `tenant_id` is **never** accepted as a body field — resolved from `tenant_slug` server-side
- Password field is consumed and not stored in any log, trace, or audit record

---

### `POST /auth/refresh`

Exchange a still-valid access token for a new one with a reset expiry. The token must not be expired.

**Auth**: Bearer token (valid, non-expired).

**Request body**: None required — token is read from the `Authorization` header.

**Response 200**:
```json
{
  "access_token": "<new signed JWT>",
  "token_type": "bearer",
  "expires_in": 3600
}
```

**Failure responses**:

| Status | Condition |
|--------|-----------|
| 401 | Token is missing, invalid, or expired |

**Audit log**: `action=token_refresh`, `outcome=allowed`, `user_id`, `tenant_id`.

**Notes**: The same `user_id`, `tenant_id`, and `role` claims are carried forward — no re-lookup against the database. If the user's role changed since the token was issued, the new token will not reflect the change until the next login.

---

### `POST /auth/logout`

Signals a logout. For MVP, this is a client-initiated action — the server has no session state to destroy. The endpoint exists to write an audit log entry and return a clean 200.

**Auth**: Bearer token (any valid token).

**Request body**: None.

**Response 200**:
```json
{ "message": "Logged out" }
```

**Audit log**: `action=logout`, `outcome=allowed`, `user_id`, `tenant_id`.

**Notes**: The frontend clears the token from `sessionStorage` and React state after receiving 200. There is no server-side token revocation in the MVP.

---

### `GET /auth/me`

Returns the current authenticated user's profile, decoded from the token.

**Auth**: Bearer token required.

**Response 200**:
```json
{
  "id": "uuid",
  "email": "alice@elegant-weddings.demo",
  "full_name": "Alice Johnson",
  "role": "staff",
  "tenant_id": "a1b2c3d4-0000-0000-0000-000000000001",
  "is_active": true
}
```

**Response 401**: Missing or invalid token.

**Notes**: Data is fetched from the database using `user_id` from the token — not constructed from claims alone. This ensures the response reflects current DB state (e.g., `is_active` changes).

---

## Role-Enforcement Behaviour (Cross-Cutting)

These rules apply to all routes in the system (Spec 001 + Spec 002):

| Scenario | HTTP Status | `error_code` | Audit log written |
|----------|-------------|--------------|-------------------|
| No `Authorization` header | 401 | `MISSING_TOKEN` | No |
| Malformed or unsigned token | 401 | `INVALID_TOKEN` | No |
| Valid token, but expired | 401 | `TOKEN_EXPIRED` | No |
| Valid token, role insufficient for route | 403 | `INSUFFICIENT_ROLE` | Yes — `action=insufficient_role` |
| Valid token, resource belongs to different tenant | 403 | `CROSS_TENANT_ACCESS` | Yes — `action=cross_tenant_access_attempt` |
| Valid Platform Admin token on content route | 403 | `INSUFFICIENT_ROLE` | Yes — `action=platform_admin_content_attempt` |

**Error response shape** (all errors):
```json
{
  "detail": "<human-readable message>",
  "error_code": "<machine-readable constant>"
}
```

---

## Frontend Route → Role Mapping

Documented here so frontend routing logic and backend guards stay in sync.

| Frontend path | Auth required | Allowed roles | Redirect on failure |
|---------------|--------------|--------------|---------------------|
| `/login` | No | — | — |
| `/dashboard` | Yes | `staff`, `manager` | → `/login` if unauthenticated |
| `/conversations` | Yes | `staff`, `manager` | → `/login` if unauth; 403 page if wrong role |
| `/tasks` | Yes | `staff`, `manager` | → `/login` |
| `/documents` | Yes | `manager` | 403 page |
| `/audit-logs` | Yes | `manager` | 403 page |
| `/admin/tenants` | Yes | `platform_admin` | 403 page |

---

## Token Claim Reference

Quick reference for backend developers wiring `get_current_tenant_context` and `require_role`:

| Claim | Type | Used for |
|-------|------|----------|
| `sub` | UUID string | `user_id` in `TenantContext` |
| `tenant_id` | UUID string | `tenant_id` in `TenantContext` — the source of truth |
| `role` | enum string | Role-based access checks via `require_role()` |
| `exp` | int (unix) | Expiry validation on every request |
| `jti` | UUID string | Future revocation; not validated in MVP |
