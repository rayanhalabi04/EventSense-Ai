# Quickstart: Authentication and Roles

**Branch**: `002-auth-and-roles`

This guide covers how to test the auth layer locally against the demo tenants seeded in Spec 001.

---

## Prerequisites

- Spec 001 migrations applied (`alembic upgrade head` through migration `0008`)
- Backend running on `http://localhost:8000`
- Frontend running on `http://localhost:5173`
- `jq` installed (for JWT decoding in terminal)

---

## Verify Canonical Roles

```bash
cd backend
alembic upgrade head
```

Verify:
```bash
psql $DATABASE_URL -c "SELECT unnest(enum_range(NULL::user_role));"
# Expected: staff, manager, platform_admin
```

---

## Demo Credentials

| Tenant | Email | Password | Role |
|--------|-------|----------|------|
| Elegant Weddings | admin@elegant-weddings.demo | demo-password-1 | manager |
| Royal Events Agency | admin@royal-events.demo | demo-password-2 | manager |
| Platform/System | platform-admin@eventsense.demo | platform-password | platform_admin |

Seed additional Staff users by running:
```bash
python backend/scripts/seed_staff_users.py
```
This creates:
- `staff@elegant-weddings.demo` / `staff-password-1` (role: staff)
- `staff@royal-events.demo` / `staff-password-2` (role: staff)

---

## Test Login Flow (curl)

```bash
# Login as Elegant Weddings manager
TOKEN=$(curl -s -X POST http://localhost:8000/auth/token \
  -H "Content-Type: application/json" \
  -d '{"email":"admin@elegant-weddings.demo","password":"demo-password-1","tenant_slug":"elegant-weddings"}' \
  | jq -r .access_token)

echo "Token: $TOKEN"

# Decode claims (without verifying signature)
echo $TOKEN | cut -d. -f2 | base64 --decode 2>/dev/null | jq .
# Expected: { "sub": "...", "tenant_id": "a1b2c3...001", "role": "manager", "exp": ... }
```

---

## Test Protected Route

```bash
# Access a protected route with the token
curl -s http://localhost:8000/auth/me \
  -H "Authorization: Bearer $TOKEN" | jq .
# Expected: user profile with role=manager and correct tenant_id

# Try without token — should return 401
curl -s http://localhost:8000/api/v1/conversations \
  | jq .error_code
# Expected: "MISSING_TOKEN"
```

---

## Test Role Enforcement

```bash
# Login as Staff
STAFF_TOKEN=$(curl -s -X POST http://localhost:8000/auth/token \
  -H "Content-Type: application/json" \
  -d '{"email":"staff@elegant-weddings.demo","password":"staff-password-1","tenant_slug":"elegant-weddings"}' \
  | jq -r .access_token)

# Staff CAN access conversations
curl -s http://localhost:8000/api/v1/conversations \
  -H "Authorization: Bearer $STAFF_TOKEN" | jq .total
# Expected: 0 (empty) or a number
```

Manager-only routes such as document management, escalation resolution, and audit-log review are future features. Until one exists in the current codebase, validate Manager-only role policy through the integration tests described in `tasks.md`.

```bash
# Login as Platform Admin using the platform/system tenant slug from Spec 001
PLATFORM_TOKEN=$(curl -s -X POST http://localhost:8000/auth/token \
  -H "Content-Type: application/json" \
  -d '{"email":"platform-admin@eventsense.demo","password":"platform-password","tenant_slug":"platform"}' \
  | jq -r .access_token)

# Platform Admin cannot access tenant content
curl -s http://localhost:8000/api/v1/conversations \
  -H "Authorization: Bearer $PLATFORM_TOKEN" | jq .error_code
# Expected: "INSUFFICIENT_ROLE"
```

---

## Test Token Refresh

```bash
# Refresh the manager token
NEW_TOKEN=$(curl -s -X POST http://localhost:8000/auth/refresh \
  -H "Authorization: Bearer $TOKEN" | jq -r .access_token)

# Decode and verify expiry is later than original
echo $NEW_TOKEN | cut -d. -f2 | base64 --decode 2>/dev/null | jq .exp
```

---

## Run Auth Tests

```bash
cd backend
pytest tests/integration/test_auth.py tests/integration/test_roles.py -v
# Expected: all tests pass
```

---

## Key File Locations (once implemented)

```
backend/
├── app/
│   ├── core/
│   │   └── security.py            # create_access_token, verify_password, hash_password, decode_jwt
│   ├── api/
│   │   └── auth.py                # /auth/token, /auth/refresh, /auth/logout, /auth/me
│   └── schemas/
│       ├── auth.py                # LoginRequest, TokenResponse, TokenData
│       └── user.py                # UserResponse
└── tests/
    ├── integration/
    │   ├── test_auth.py           # Login, 401, expiry, refresh tests
    │   └── test_roles.py          # Role enforcement tests (staff/manager/platform_admin)
    └── unit/
        └── test_security.py       # verify_password, create_access_token, decode_jwt unit tests

frontend/
└── src/
    ├── context/
    │   └── AuthContext.tsx         # Token state, login/logout actions
    ├── hooks/
    │   └── useAuth.ts              # Auth state hook
    ├── components/
    │   ├── ProtectedRoute.tsx      # Redirects to /login if not authenticated
    │   └── RoleGuard.tsx           # Shows 403 if role insufficient
    ├── pages/
    │   └── LoginPage.tsx           # Login form
    └── api/
        └── auth.ts                 # login(), refresh(), logout(), getMe() API calls
```
