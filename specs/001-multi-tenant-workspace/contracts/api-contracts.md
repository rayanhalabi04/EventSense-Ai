# API Contracts: Multi-Tenant Workspace

**Branch**: `001-multi-tenant-workspace` | **Phase**: 1 - Design

All endpoints are prefixed with `/api/v1`. All protected endpoints require a valid JWT Bearer token. Authentication endpoints themselves are defined in Spec 002.

`tenant_id` is never accepted as an authorization source. It is extracted from the authenticated context.

---

## Authentication Assumptions

- Spec 002 issues JWTs containing `{ sub: user_id, tenant_id: uuid, role: string, exp: int }`.
- `get_current_tenant_context` validates the token and returns `TenantContext(tenant_id, user_id, role)`.
- Canonical roles are `staff`, `manager`, and `platform_admin`.

---

## Tenant Context

### `GET /api/v1/tenants/me`

Returns the current user's tenant metadata.

**Auth**: Any authenticated customer tenant user (`staff` or `manager`). `platform_admin` is not a customer tenant user.

**Response 200**:

```json
{
  "id": "a1b2c3d4-0000-0000-0000-000000000001",
  "name": "Elegant Weddings",
  "slug": "elegant-weddings",
  "kind": "customer",
  "is_active": true
}
```

**Failure responses**:

| Status | Condition | `error_code` |
|--------|-----------|--------------|
| 401 | Missing/invalid/expired token | `MISSING_TOKEN` / `INVALID_TOKEN` / `TOKEN_EXPIRED` |
| 403 | `platform_admin` attempts customer tenant context route | `INSUFFICIENT_ROLE` |

---

## Platform Tenant Metadata

### `GET /api/v1/admin/tenants`

Lists tenant metadata for platform/demo administration. Does not return tenant content, messages, documents, audit logs, or counts.

**Auth**: `platform_admin` only.

**Response 200**:

```json
{
  "items": [
    {
      "id": "a1b2c3d4-0000-0000-0000-000000000001",
      "name": "Elegant Weddings",
      "slug": "elegant-weddings",
      "kind": "customer",
      "is_active": true,
      "created_at": "2026-06-03T10:00:00Z"
    }
  ],
  "total": 2
}
```

**Notes**:
- Tenant provisioning can remain seed-only for the senior-project MVP unless a later platform-admin feature adds create/deactivate endpoints.
- Platform admin cannot call tenant content routes by default.

---

## Cross-Cutting Security Behaviour

| Scenario | HTTP Status | Behaviour |
|----------|-------------|-----------|
| Missing/invalid token | 401 | No tenant context established |
| Valid token, customer tenant route | 200 | Uses `ctx.tenant_id` |
| Client sends `tenant_id` in body/query | 400/422 or ignored by contract | Cannot override `ctx.tenant_id` |
| Valid token, role insufficient | 403 | No tenant content returned |
| Valid token, cross-tenant resource ID in later feature | 403 | No tenant content returned |
| Cross-tenant blocked attempt when audit exists later | 403 | Log under actor tenant; do not leak victim tenant content |

---

## Error Response Shape

```json
{
  "detail": "forbidden",
  "error_code": "INSUFFICIENT_ROLE"
}
```

Relevant error codes:

| Code | Meaning |
|------|---------|
| `MISSING_TOKEN` | No bearer token supplied |
| `INVALID_TOKEN` | Token cannot be validated |
| `TOKEN_EXPIRED` | Token expiry has passed |
| `INSUFFICIENT_ROLE` | Role cannot access route |
| `CROSS_TENANT_ACCESS` | Resource belongs to another tenant |
| `TENANT_ID_NOT_ALLOWED` | Endpoint rejects client-supplied `tenant_id` |

---

## Later Feature Contract Requirements

When later specs add tenant-owned routes, their contracts must state:

- request bodies do not accept `tenant_id` unless explicitly rejected as invalid
- created records use `ctx.tenant_id`
- referenced parent/child records are validated to belong to the same tenant
- `platform_admin` cannot access tenant content routes by default
- cross-tenant blocked attempts follow the actor-tenant audit policy once audit logging exists
