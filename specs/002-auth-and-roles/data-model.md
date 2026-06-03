# Data Model: Authentication and Roles

**Branch**: `002-auth-and-roles` | **Phase**: 1 — Design

---

## Schema Changes from Spec 001

This feature introduces **no new tables**. All required tables (`users`, `tenants`, `audit_logs`) were defined in Spec 001. This feature delivers:

1. A **role enum rename migration** — renames Spec 001's provisional enum values to the canonical names
2. **Pydantic schemas** for request/response validation
3. **JWT payload structure** (documented below)
4. The **role permission matrix** enforced via FastAPI dependencies

---

## Alembic Migration

### `0009_rename_user_roles`

Rename the `user_role` PostgreSQL enum values to match the canonical names established by this feature:

| Old value (Spec 001 placeholder) | New value (Spec 002 canonical) |
|----------------------------------|-------------------------------|
| `tenant_agent` | `staff` |
| `tenant_admin` | `manager` |
| `super_admin` | `platform_admin` |

```sql
-- PostgreSQL does not support ALTER TYPE ... RENAME VALUE directly in older versions.
-- Use a sequence of ALTER TYPE ... ADD VALUE + UPDATE + ALTER TYPE ... RENAME VALUE (PG 15+)
-- or drop-and-recreate with a temporary column approach for earlier versions.
-- Alembic migration handles this with raw SQL.

ALTER TYPE user_role RENAME VALUE 'tenant_agent' TO 'staff';
ALTER TYPE user_role RENAME VALUE 'tenant_admin' TO 'manager';
ALTER TYPE user_role RENAME VALUE 'super_admin' TO 'platform_admin';
```

**Seed data update** (same migration): Update the two demo tenant admin users from `tenant_admin` → `manager`.

---

## JWT Payload Structure

The access token is a signed JWT. This is not a database entity but is the central data structure of this feature.

```
Header:  { "alg": "HS256", "typ": "JWT" }

Payload: {
  "sub":       "<user_id>",         # UUID string — user identity
  "tenant_id": "<tenant_id>",       # UUID string — tenant context (read-only by client)
  "role":      "staff"              # | "manager" | "platform_admin"
               | "manager"
               | "platform_admin",
  "exp":       1748995200,          # Unix timestamp — token expiry (now + 60 min)
  "iat":       1748991600,          # Unix timestamp — issued at
  "jti":       "<uuid>"             # Unique token ID (for future revocation)
}
```

**Rules**:
- `sub`, `tenant_id`, `role` are the three claims the backend uses for every authorization decision
- `exp` is validated on every protected request; expired tokens return 401
- `jti` is stored in the token but not validated against a store in MVP (included for future use)
- The secret used to sign tokens is `JWT_SECRET_KEY` from environment — never hardcoded

---

## Pydantic Schemas (backend/app/schemas/)

### `auth.py`

```python
class LoginRequest(BaseModel):
    email: EmailStr
    password: str          # plain text; never logged or stored
    tenant_slug: str       # used to resolve tenant_id before credential check

class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int        # seconds until expiry (3600)

class TokenData(BaseModel):
    sub: UUID              # user_id
    tenant_id: UUID
    role: UserRole
    exp: int
    iat: int
    jti: UUID
```

### `user.py`

```python
class UserResponse(BaseModel):
    id: UUID
    email: str
    full_name: str
    role: UserRole
    tenant_id: UUID
    is_active: bool
```

---

## Role → Permission Mapping (enforced via `require_role`)

The `require_role(*roles)` dependency from Spec 001 is called at route definition. The mapping below is the authoritative permission table for this feature.

### Content routes (tenant-scoped, Spec 001)

| Route | Required roles |
|-------|---------------|
| `GET /api/v1/conversations` | `staff`, `manager` |
| `POST /api/v1/conversations` | `staff`, `manager` |
| `GET /api/v1/conversations/{id}` | `staff`, `manager` |
| `POST /api/v1/conversations/{id}/messages` | `staff`, `manager` |
| `POST /api/v1/conversations/{id}/escalate` | `staff`, `manager` |
| `GET /api/v1/tasks` | `staff`, `manager` |
| `POST /api/v1/tasks` | `staff`, `manager` |
| `PATCH /api/v1/tasks/{id}` | `staff`, `manager` |
| `GET /api/v1/suggested-replies` | `staff`, `manager` |
| `PATCH /api/v1/suggested-replies/{id}` | `staff`, `manager` |
| `POST /api/v1/documents` | `manager` only |
| `GET /api/v1/documents` | `manager` only |
| `GET /api/v1/documents/{id}` | `manager` only |
| `GET /api/v1/audit-logs` | `manager` only |
| `POST /api/v1/escalations/{id}/resolve` | `manager` only |

### Admin routes (platform-level, Spec 001)

| Route | Required roles |
|-------|---------------|
| `POST /api/v1/admin/tenants` | `platform_admin` only |
| `GET /api/v1/admin/tenants` | `platform_admin` only |
| `PATCH /api/v1/admin/tenants/{id}` | `platform_admin` only |
| `GET /api/v1/admin/audit-logs` | `platform_admin` only |

### Auth routes (this feature — no auth required)

| Route | Auth required |
|-------|--------------|
| `POST /auth/token` | No — this IS the login |
| `POST /auth/refresh` | Yes — valid (non-expired) token required |
| `POST /auth/logout` | Yes — for audit logging; effectively always succeeds |
| `GET /auth/me` | Yes — returns current user info |

---

## Frontend Auth State Shape

The `AuthContext` React context holds:

```typescript
interface AuthState {
  token: string | null;           // raw JWT string
  user: {
    userId: string;               // decoded sub
    tenantId: string;             // decoded tenant_id
    role: "staff" | "manager" | "platform_admin";
    exp: number;                  // decoded exp (unix timestamp)
  } | null;
  isAuthenticated: boolean;       // token != null && !isExpired(token)
}
```

The `AuthContext` is populated by:
1. On app load: read from `sessionStorage` and validate expiry
2. On login: store token from API response
3. On logout / 401: clear token and redirect to `/login`
4. On refresh: replace token with new value

---

## Frontend Route Protection

Protected routes use a `<ProtectedRoute>` wrapper component:

```
/login                     → Public (no auth required)
/dashboard                 → ProtectedRoute (any authenticated user)
/documents                 → ProtectedRoute + RoleGuard(["manager"])
/audit-logs                → ProtectedRoute + RoleGuard(["manager"])
/admin/tenants             → ProtectedRoute + RoleGuard(["platform_admin"])
```

`ProtectedRoute`: redirects to `/login` if `!isAuthenticated`.
`RoleGuard`: renders a 403 message (or redirects) if `user.role` not in allowed roles.
