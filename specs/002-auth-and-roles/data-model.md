# Data Model: Authentication and Roles

**Branch**: `002-auth-and-roles` | **Phase**: 1 — Design

---

## Schema Changes from Spec 001

This feature introduces **no new tables**. Required foundation tables (`users`, `tenants`) were defined in Spec 001. Audit log storage is a later feature; this spec only names audit events for future integration. This feature delivers:

1. **Pydantic schemas** for request/response validation
2. **JWT payload structure** (documented below)
3. The **role permission matrix** enforced via FastAPI dependencies
4. Demo staff/platform auth seed assumptions that use Spec 001 canonical roles

---

## Role Enum

Spec 001 creates the canonical `user_role` enum:

```text
staff
manager
platform_admin
```

Spec 002 must not add a role-rename migration. It only uses these existing values for JWT claims and route guards.

---

## JWT Payload Structure

The access token is a signed JWT. This is not a database entity but is the central data structure of this feature.

```
Header:  { "alg": "HS256", "typ": "JWT" }

Payload: {
  "sub":       "<user_id>",         # UUID string — user identity
  "tenant_id": "<tenant_id>",       # UUID string — tenant context (read-only by client)
  "role":      "staff",             # "staff" | "manager" | "platform_admin"
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

The `require_role(*roles)` dependency from Spec 001 is called at route definition. The implemented routes in Spec 002 are auth routes only. Tenant content, documents, RAG, suggested replies, tasks, escalations, and audit logs are future features; their rows below are role-policy examples for later specs, not APIs implemented here.

### Tenant content route policy examples

| Route | Required roles |
|-------|---------------|
| Current tenant content routes from Specs 003+ | `staff`, `manager` |
| Future message detail / suggested reply review routes | `staff`, `manager` |
| Future task creation/status routes | `staff`, `manager` |
| Future staff-initiated escalation creation routes | `staff`, `manager` |
| Future document and RAG-management routes | `manager` only |
| Future audit-log review routes | `manager` only |
| Future escalation resolution routes | `manager` only |

### Platform/admin route policy examples

| Route | Required roles |
|-------|---------------|
| Existing Spec 001 platform tenant metadata route, e.g. `GET /api/v1/admin/tenants` | `platform_admin` only |
| Future platform/demo administration routes | `platform_admin` only |

### Auth routes (this feature — no auth required)

| Route | Auth required |
|-------|--------------|
| `POST /auth/token` | No — this IS the login |
| `POST /auth/refresh` | Yes — valid (non-expired) token required |
| `POST /auth/logout` | Yes — emits future-audit hook if available; effectively always succeeds |
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
/documents                 → Future policy example: ProtectedRoute + RoleGuard(["manager"])
/audit-logs                → Future policy example: ProtectedRoute + RoleGuard(["manager"])
/admin/tenants             → ProtectedRoute + RoleGuard(["platform_admin"])
```

`ProtectedRoute`: redirects to `/login` if `!isAuthenticated`.
`RoleGuard`: renders a 403 message (or redirects) if `user.role` not in allowed roles.
