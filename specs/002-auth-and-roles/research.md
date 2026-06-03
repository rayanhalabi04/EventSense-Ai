# Research: Authentication and Roles

**Branch**: `002-auth-and-roles` | **Phase**: 0 — Pre-design research

All technical choices below are resolved from the provided stack (FastAPI + SQLAlchemy + PostgreSQL + JWT + passlib/bcrypt + React). No `NEEDS CLARIFICATION` items remain.

---

## Decision 1: JWT Structure and Claims

**Decision**: Access tokens are signed JWTs (HS256) containing exactly these claims:

```json
{
  "sub":       "<user_id as UUID string>",
  "tenant_id": "<tenant_id as UUID string>",
  "role":      "staff" | "manager" | "platform_admin",
  "exp":       <unix timestamp>,
  "iat":       <unix timestamp>,
  "jti":       "<uuid — unique token ID, for future revocation support>"
}
```

**Rationale**:
- `sub` = user identity (standard JWT claim)
- `tenant_id` embedded directly avoids a DB round-trip on every request (no per-request tenant lookup)
- `role` embedded avoids a separate permissions DB query per request
- `jti` is cheap to include now and enables a revocation blocklist later without changing the token shape
- HS256 with a strong server-side secret is appropriate for MVP single-server deployment; RS256 can be adopted when a separate auth service is introduced

**Token lifetimes**:
- Access token: 60 minutes
- Refresh: the `/auth/refresh` endpoint accepts a still-valid access token and issues a new one with a reset expiry — no separate refresh token for MVP (reduces client-side storage complexity)
- If the access token is expired, the user must log in again (no silent refresh for MVP)

**Alternatives considered**:
- Opaque tokens + server-side sessions: requires session store (Redis), adds infrastructure for MVP. Deferred.
- RS256 with a JWKS endpoint: appropriate for multi-service auth; overkill for a monolith MVP. Deferred.
- Separate refresh token (httpOnly cookie): the gold standard. Deferred to post-MVP when a persistent session UX is required.

---

## Decision 2: Role Naming and Enum Values

**Decision**: Align role names between Spec 001 and this spec. The `UserRole` enum in `backend/app/models/user.py` (defined in Spec 001) uses the names below. Spec 002 adopts them as the canonical identifiers:

| Spec 002 name | Enum value | Spec 001 placeholder | Description |
|---------------|-----------|----------------------|-------------|
| Staff | `staff` | `tenant_agent` | Day-to-day planner |
| Manager | `manager` | `tenant_admin` | Senior / document manager |
| Platform Admin | `platform_admin` | `super_admin` | Internal operator |

**Rationale**: The Spec 001 plan used provisional names (`tenant_agent`, `tenant_admin`, `super_admin`). Spec 002 finalises them as `staff`, `manager`, `platform_admin` — cleaner and domain-appropriate for a wedding/event agency product. The Alembic migration for the enum is part of Spec 002 (an `ALTER TYPE` migration that renames the values).

---

## Decision 3: Password Hashing

**Decision**: Use `passlib[bcrypt]` with `CryptContext(schemes=["bcrypt"], deprecated="auto")`. Hash passwords with `pwd_context.hash(plain)`, verify with `pwd_context.verify(plain, hashed)`.

**Rationale**:
- passlib is already listed as a dependency in Spec 001's plan
- bcrypt has an appropriate work factor for authentication (cost factor 12 default)
- `deprecated="auto"` allows seamless migration to a stronger scheme without code changes

**Alternatives considered**:
- argon2: superior algorithm, but requires `argon2-cffi` and is not in the existing dependency list. Deferred to post-MVP.
- scrypt: available in Python stdlib but not in passlib's default schemes. Deferred.

---

## Decision 4: Token Storage on the Frontend

**Decision** (MVP): Store the access token in React component state (in-memory via `AuthContext`). Persist to `sessionStorage` so a page refresh within the same browser tab does not force re-login. Do **not** use `localStorage` (persists across tabs and survives browser restart — increases credential theft window).

**Rationale**:
- In-memory + `sessionStorage` balances usability (survives F5) and security (cleared when tab closes)
- No XSS-safe httpOnly cookie approach is needed for MVP since there is no refresh token
- The access token is short-lived (60 min), limiting the blast radius of theft

**Alternatives considered**:
- `localStorage`: too persistent; rejected on security grounds
- httpOnly cookie: best practice for refresh tokens; deferred to when a separate refresh token is introduced
- In-memory only (no sessionStorage): forces re-login on every page refresh; too disruptive for MVP UX

---

## Decision 5: Role Permission Matrix

**Decision**: Roles are mapped to route-level access using the `require_role()` dependency from Spec 001. The canonical permission matrix is:

| Route category | Staff | Manager | Platform Admin |
|----------------|-------|---------|----------------|
| `GET /conversations`, `GET /conversations/{id}` | ✓ | ✓ | ✗ |
| `POST /conversations`, `POST /conversations/{id}/messages` | ✓ | ✓ | ✗ |
| `POST /conversations/{id}/escalate` | ✓ | ✓ | ✗ |
| `PATCH /tasks/{id}` (status update) | ✓ | ✓ | ✗ |
| `GET /tasks`, `POST /tasks` | ✓ | ✓ | ✗ |
| `GET /suggested-replies` | ✓ | ✓ | ✗ |
| `PATCH /suggested-replies/{id}` (accept/reject) | ✓ | ✓ | ✗ |
| `POST /documents`, `GET /documents` | ✗ | ✓ | ✗ |
| `GET /documents/{id}` | ✗ | ✓ | ✗ |
| `GET /audit-logs` | ✗ | ✓ | ✗ |
| `POST /escalations/{id}/resolve` | ✗ | ✓ | ✗ |
| `POST /admin/tenants`, `GET /admin/tenants` | ✗ | ✗ | ✓ |
| `PATCH /admin/tenants/{id}` (deactivate) | ✗ | ✗ | ✓ |
| `GET /admin/audit-logs` (cross-tenant) | ✗ | ✗ | ✓ |

**Note**: Manager inherits all Staff permissions. Platform Admin has no access to tenant content routes (conversations, messages, documents, tasks, escalations, suggested replies).

---

## Decision 6: Audit Events for Auth

**Decision**: The following auth events are written to `audit_logs` via `AuditService.log()`:

| Event | `action` value | `outcome` | Notes |
|-------|---------------|-----------|-------|
| Successful login | `login_success` | `allowed` | Includes IP, user_id, tenant_id |
| Failed login (bad creds) | `login_failure` | `blocked` | Includes email, IP; no user_id (not resolved) |
| Failed login (inactive user/tenant) | `login_failure_inactive` | `blocked` | Includes user_id if resolvable |
| Role violation (403) | `insufficient_role` | `blocked` | Includes user_id, endpoint, required role, actual role |
| Platform Admin content access attempt | `platform_admin_content_attempt` | `blocked` | Subset of `insufficient_role` |
| Token refresh | `token_refresh` | `allowed` | Optional for MVP; include for auditability |

**Rationale**: Token expiry events (401 from expired token) are not individually audit-logged — the volume would be excessive and they provide no security signal beyond what login events already capture.

---

## Decision 7: Tenant Resolution at Login

**Decision**: The login request body includes a `tenant_slug` field alongside `email` and `password`. The backend resolves `tenant_id` from the slug, then queries `users` with `WHERE email = :email AND tenant_id = :resolved_tenant_id`. This avoids multi-tenant email collisions.

**Rationale**:
- Aligns with the spec assumption that a tenant identifier is present at login time
- Slug is URL-safe, user-friendly, and already defined on the `tenants` table
- Avoids the complexity of an email-first flow (look up all matching users, then ask tenant)

**Alternatives considered**:
- Subdomain-based tenant resolution (e.g., `elegant-weddings.eventsense.io`): good UX but requires DNS/infra changes. Deferred.
- Email-first + tenant picker: better UX when email is in multiple tenants; deferred to post-MVP since MVP users each belong to exactly one tenant.

---

## Decision 8: Deferred Items

| Item | Reason deferred |
|------|----------------|
| Separate refresh token (httpOnly cookie) | Adds infra; MVP access token expiry is acceptable |
| Token revocation (jti blocklist) | Requires Redis; jti is included in token for future use |
| MFA | Out of scope per spec |
| OAuth2 / SSO | Out of scope per spec |
| Password reset via email | Out of scope per spec; demo passwords set via seeding |
| Rate limiting on login endpoint | Handled at infra level (nginx/proxy); not in application code |
| Granular per-user permission overrides | Out of scope per spec |
