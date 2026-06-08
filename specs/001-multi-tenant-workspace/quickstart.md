# Quickstart: Multi-Tenant Workspace

**Branch**: `001-multi-tenant-workspace`

This guide covers the foundation only: tenant/user schema, demo seeds, and tenant isolation checks.

---

## Prerequisites

- Python 3.11+
- PostgreSQL 15+
- `uv` or `pip` for Python dependencies

pgvector is not required for Spec 001. It is introduced by the later RAG feature.

---

## Backend Setup

```bash
cd backend
pip install -r requirements.txt   # or: uv sync

cp .env.example .env
# Set: DATABASE_URL, JWT_SECRET_KEY, JWT_ALGORITHM=HS256, ACCESS_TOKEN_EXPIRE_MINUTES=60

alembic upgrade head

uvicorn app.main:app --reload --port 8000
```

---

## Demo Tenant Credentials

After running `alembic upgrade head`, the foundation seed should provide:

| Tenant | Slug | Email | Password | Role |
|--------|------|-------|----------|------|
| Elegant Weddings | `elegant-weddings` | `admin@elegant-weddings.demo` | `demo-password-1` | `manager` |
| Royal Events Agency | `royal-events-agency` | `admin@royal-events.demo` | `demo-password-2` | `manager` |
| EventSense Platform | `platform` | `platform-admin@eventsense.demo` | `platform-password` | `platform_admin` |

The platform tenant is for platform/demo administration only. It is not a customer workspace.

---

## Verifying Tenant Foundation

### Database checks

```bash
psql $DATABASE_URL -c "SELECT name, slug, kind, is_active FROM tenants ORDER BY slug;"
psql $DATABASE_URL -c "SELECT email, role, tenant_id FROM users ORDER BY email;"
```

Expected:
- two customer tenants: Elegant Weddings and Royal Events Agency
- optional platform tenant: EventSense Platform
- customer users have role `manager`
- platform user has role `platform_admin`
- every user has a non-null `tenant_id`

### API checks

Once Spec 002 auth is implemented, log in as each demo manager and call:

```bash
curl -s http://localhost:8000/api/v1/tenants/me \
  -H "Authorization: Bearer $TOKEN" | jq .
```

Expected: tenant metadata for the authenticated user's tenant only.

---

## Automated Tests

```bash
cd backend
pytest tests/integration/test_tenant_foundation.py tests/unit/test_tenant_repo.py -v
```

Expected: tenant seed, tenant context, repository filtering, client `tenant_id` override prevention, and same-tenant validation tests pass.

---

## Key File Locations

```
backend/
├── app/
│   ├── core/
│   │   ├── tenant_context.py
│   │   ├── tenant_repo.py
│   │   └── security.py
│   ├── models/
│   │   ├── tenant.py
│   │   └── user.py
│   └── api/v1/
│       └── tenants.py
├── alembic/versions/
│   ├── 0001_create_tenants.py
│   ├── 0002_create_users.py
│   └── 0003_seed_demo_tenants.py
└── tests/
    ├── unit/
    │   └── test_tenant_repo.py
    └── integration/
        └── test_tenant_foundation.py
```
