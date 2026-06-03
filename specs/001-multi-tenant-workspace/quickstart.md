# Quickstart: Multi-Tenant Workspace

**Branch**: `001-multi-tenant-workspace`

This guide covers how to run the multi-tenant workspace locally, seed demo tenants, and verify isolation.

---

## Prerequisites

- Python 3.11+
- PostgreSQL 15+ with pgvector extension installed
- Node.js 18+ (for frontend)
- `uv` or `pip` for Python deps

---

## Backend Setup

```bash
# 1. Install Python dependencies
cd backend
pip install -r requirements.txt   # or: uv sync

# 2. Configure environment
cp .env.example .env
# Set: DATABASE_URL, JWT_SECRET_KEY, JWT_ALGORITHM=HS256, ACCESS_TOKEN_EXPIRE_MINUTES=60

# 3. Enable pgvector in your database
psql $DATABASE_URL -c "CREATE EXTENSION IF NOT EXISTS vector;"

# 4. Run Alembic migrations (creates all tables + seeds demo tenants)
alembic upgrade head

# 5. Start the FastAPI server
uvicorn app.main:app --reload --port 8000
```

---

## Frontend Setup

```bash
cd frontend
npm install
npm run dev    # starts at http://localhost:5173
```

---

## Demo Tenant Credentials

After running `alembic upgrade head`, two tenants are available:

| Tenant | Email | Password | Role |
|--------|-------|----------|------|
| Elegant Weddings | admin@elegant-weddings.demo | demo-password-1 | tenant_admin |
| Royal Events Agency | admin@royal-events.demo | demo-password-2 | tenant_admin |

---

## Verifying Tenant Isolation

### Manual check

1. Log in as `admin@elegant-weddings.demo` — create a conversation.
2. Log in as `admin@royal-events.demo` — the conversation list must be empty.
3. Copy the conversation UUID from step 1. Authenticated as Royal Events, `GET /api/v1/conversations/{id}` must return **403 Forbidden**.

### Automated test

```bash
cd backend
pytest tests/integration/test_tenant_isolation.py -v
```

Expected output: all 10 isolation tests pass.

---

## Key File Locations (once implemented)

```
backend/
├── app/
│   ├── core/
│   │   ├── tenant_context.py      # TenantContext dataclass + JWT dependency
│   │   └── tenant_repo.py         # TenantScopedRepository base class
│   ├── models/                    # SQLAlchemy ORM models
│   ├── api/v1/
│   │   ├── tenants.py             # /tenants/me, /admin/tenants
│   │   ├── conversations.py
│   │   ├── messages.py
│   │   ├── documents.py
│   │   ├── suggested_replies.py
│   │   ├── tasks.py
│   │   ├── escalations.py
│   │   └── audit_logs.py
│   └── services/
│       └── audit_service.py       # Append-only audit log writer
├── alembic/versions/              # Migration files
└── tests/
    ├── unit/
    │   └── test_tenant_repo.py    # TenantScopedRepository unit tests
    └── integration/
        └── test_tenant_isolation.py   # Cross-tenant access tests

frontend/
├── src/
│   ├── api/
│   │   └── client.ts              # Axios client that never sends tenant_id in body
│   ├── context/
│   │   └── TenantContext.tsx      # React context for current tenant
│   └── pages/
│       └── Dashboard.tsx          # Tenant-scoped dashboard
```
